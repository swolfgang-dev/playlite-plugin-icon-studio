"""Native image composition editor with crop, pan, zoom and layered overlays."""
import tempfile
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QColor, QPen
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSizePolicy, QGroupBox, QCheckBox, QLabel, QComboBox, QPushButton, QDialogButtonBox, QListWidget,
    QListWidgetItem, QLineEdit, QColorDialog, QInputDialog, QScrollArea)
from playlite.lifecycle import choose_file, run_dialog
from .model import PRESETS, image_layer, render_scene
from .number_slider import NumberSlider


class Canvas(QWidget):
    pan = pyqtSignal(float, float)
    zoom = pyqtSignal(int)
    dragStarted = pyqtSignal()

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.frame = QRectF()
        self.last_position = None
        self.setMinimumSize(320, 280)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#121212'))
        if self.studio.preview_image is None:
            return
        image = self.studio.preview_image
        scale = min((self.width() - 32) / image.width(), (self.height() - 32) / image.height())
        w, h = image.width() * scale, image.height() * scale
        self.frame = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        painter.save()
        painter.setClipRect(self.frame)
        for y in range(int(self.frame.top()), int(self.frame.bottom()) + 1, 16):
            for x in range(int(self.frame.left()), int(self.frame.right()) + 1, 16):
                alternate = ((x - int(self.frame.left())) // 16 + (y - int(self.frame.top())) // 16) % 2
                painter.fillRect(x, y, 16, 16, QColor('#444444' if alternate else '#333333'))
        painter.drawImage(self.frame, image)
        painter.restore()
        painter.setPen(QPen(QColor('#2196f3'), 1))
        painter.drawRect(self.frame)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.frame.contains(event.position()):
            self.last_position = event.position()
            self.dragStarted.emit()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.last_position is not None:
            delta = event.position() - self.last_position
            self.last_position = event.position()
            self.pan.emit(delta.x() / self.frame.width(), delta.y() / self.frame.height())
            event.accept()

    def mouseReleaseEvent(self, event):
        self.last_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        steps = event.angleDelta().y() // 120
        if steps:
            self.zoom.emit(steps * 10)
            event.accept()


class ImageStudio(QDialog):
    def __init__(self, source=None, image_type='Icon', parent=None, pick_overlay=None, pick_source=None):
        super().__init__(parent)
        self.setWindowTitle('Image Studio')
        self.resize(1150, 820)
        image = QImage(str(source)) if source else QImage(*PRESETS[image_type], QImage.Format.Format_ARGB32)
        if not source:
            image.fill(Qt.GlobalColor.transparent)
        self.scene = dict(size=PRESETS[image_type], shape='Rectangle', fit='Fill',
            background='transparent', image_size=100, border_size=100, border=0, border_enabled=False, border_color='#ffffff', border_shape='Follow crop', border_style='Solid colour', border_radius=0, transparent_outside=False,
            layers=[image_layer(image, 'Source image', True)])
        self.image_type = image_type
        self.pick_overlay = pick_overlay
        self.pick_source = pick_source
        self.output = None
        self.cache = tempfile.TemporaryDirectory(prefix='playlite-image-studio-')
        self.undo_states, self.redo_states = [], []
        self.preview_image = None
        self.syncing = False
        self.dragging_slider = False
        layout = QVBoxLayout(self)
        help_text = QLabel('Start with your image, then add an optional border and overlays. Drag to position; scroll to scale. Apply returns the result to the game editor; save the game to keep it.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        self.canvas = Canvas(self)
        body.addWidget(self.canvas, 1)
        self.canvas.dragStarted.connect(self.remember)
        self.canvas.pan.connect(self.pan_layer)
        self.canvas.zoom.connect(lambda delta: (self.source_transform if self.layer()['base'] else self.transform)['zoom'].setValue(self.layer()['zoom'] + delta))
        content = QWidget()
        controls = QVBoxLayout(content)
        content.setContentsMargins(12, 0, 12, 0)
        scroll = self.controls_scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(370)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(scroll)
        def section(title):
            group = QGroupBox(title)
            box = QVBoxLayout(group)
            box.setSpacing(10)
            controls.addWidget(group)
            return group, box

        def form_in(box):
            form = QFormLayout()
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            box.addLayout(form)
            return form

        def transforms(form, source=False):
            result = {}
            for name, title, low, high in [('zoom', 'Zoom (%)', 10, 800), ('x', 'Position X (%)', -100, 200),
                                          ('y', 'Position Y (%)', -100, 200), ('rotation', 'Rotation (°)', -180, 180),
                                          ('opacity', 'Opacity (%)', 0, 100)]:
                slider = NumberSlider()
                slider.setRange(low, high)
                callback = self.source_layer_change if source else self.layer_change
                slider.valueChanged.connect(lambda value, key=name, callback=callback: callback(key, value / 100 if key in ('x', 'y') else value))
                result[name] = slider
                form.addRow(title, slider)
            return result

        self.image_group, image_box = section('Image')
        self.replace_button = QPushButton('Replace image…')
        self.replace_button.clicked.connect(self.download_source)
        image_box.addWidget(self.replace_button)
        image_form = form_in(image_box)
        self.fit = QComboBox()
        self.fit.addItems(['Fill', 'Fit'])
        self.fit.currentTextChanged.connect(lambda value: self.scene_change('fit', value))
        image_form.addRow('Image sizing', self.fit)
        self.image_size = NumberSlider()
        self.image_size.setRange(1, 100)
        self.image_size.valueChanged.connect(lambda value: self.scene_change('image_size', value))
        image_form.addRow('Image size (%)', self.image_size)
        self.shape = QComboBox(self)
        self.shape.addItems(['Rectangle', 'Rounded rectangle', 'Circle'])
        self.shape.currentTextChanged.connect(lambda value: self.scene_change('shape', value))
        self.shape.hide()
        self.border_radius = NumberSlider()
        self.border_radius.setRange(0, min(self.scene['size']) // 2)
        self.border_radius.valueChanged.connect(self.change_border_radius)
        image_form.addRow('Corner radius (px)', self.border_radius)
        self.source_transform = transforms(image_form, source=True)
        colors = QHBoxLayout()
        background = QPushButton('Background…')
        background.clicked.connect(lambda: self.choose_scene_color('background'))
        clear = QPushButton('Transparent')
        clear.clicked.connect(lambda: self.scene_change('background', 'transparent'))
        colors.addWidget(background)
        colors.addWidget(clear)
        image_box.addLayout(colors)
        reset_image = QPushButton('Reset image position / scale')
        reset_image.clicked.connect(self.reset_source)
        image_box.addWidget(reset_image)

        self.border_group, border_box = section('Border · optional')
        self.enable_border = QCheckBox('Enable border')
        self.enable_border.toggled.connect(self.toggle_border)
        border_box.addWidget(self.enable_border)
        self.border_settings = QWidget()
        border_box.addWidget(self.border_settings)
        border_layout = QVBoxLayout(self.border_settings)
        border_layout.setContentsMargins(0, 0, 0, 0)
        border_form = form_in(border_layout)
        self.border_shape = QComboBox()
        self.border_shape.addItems(['None', 'Follow crop', 'Circle', 'Square', 'Rounded square'])
        self.border_shape.currentTextChanged.connect(self.set_border_shape)
        border_form.addRow('Shape', self.border_shape)
        self.border_style = QComboBox()
        self.border_style.addItems(['Silver', 'Gold', 'Dark metal', 'Solid colour', 'None'])
        self.border_style.currentTextChanged.connect(self.set_border_style)
        frame_row = QHBoxLayout()
        frame_row.addWidget(self.border_style)
        self.border_picker_button = QPushButton('Choose…')
        self.border_picker_button.clicked.connect(self.choose_border)
        frame_row.addWidget(self.border_picker_button)
        border_form.addRow('Style', frame_row)
        self.border_size = NumberSlider()
        self.border_size.setRange(1, 100)
        self.border_size.valueChanged.connect(lambda value: self.scene_change('border_size', value))
        border_form.addRow('Border size (%)', self.border_size)
        self.border = NumberSlider()
        self.border.setRange(0, 100)
        self.border.valueChanged.connect(lambda value: self.scene_change('border', value))
        border_form.addRow('Thickness (px)', self.border)
        self.border_color_button = QPushButton('Colour…')
        self.border_color_button.clicked.connect(lambda: self.choose_scene_color('border_color'))
        border_form.addRow(self.border_color_button)
        self.transparent_outside = QCheckBox('Trim image outside border')
        self.transparent_outside.toggled.connect(lambda value: self.scene_change('transparent_outside', value))
        border_form.addRow(self.transparent_outside)
        border_hint = QLabel('Overlays can extend beyond the border.')
        border_hint.setWordWrap(True)
        border_layout.addWidget(border_hint)

        self.overlays_group, overlay_box = section('Overlays · optional')
        self.layers = QListWidget()
        self.layers.setMaximumHeight(130)
        self.layers.currentRowChanged.connect(self.sync_layer)
        self.layers.itemChanged.connect(self.change_visibility)
        overlay_box.addWidget(self.layers)
        self.overlay_empty = QLabel('No overlays. Add a logo, image, or text.')
        self.overlay_empty.setWordWrap(True)
        overlay_box.addWidget(self.overlay_empty)
        add_row = QHBoxLayout()
        for title, callback in [('Add image…', self.add_image), ('Add text…', self.add_text)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            add_row.addWidget(button)
        overlay_box.addLayout(add_row)
        self.overlay_settings = QWidget()
        overlay_box.addWidget(self.overlay_settings)
        overlay_layout = QVBoxLayout(self.overlay_settings)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        for title, callback in [('Raise', lambda: self.move_layer(1)), ('Lower', lambda: self.move_layer(-1)), ('Remove', self.remove_layer)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        overlay_layout.addLayout(row)
        transform_form = form_in(overlay_layout)
        self.transform = transforms(transform_form)
        self.text_settings = QWidget()
        overlay_layout.addWidget(self.text_settings)
        text_layout = QVBoxLayout(self.text_settings)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_form = form_in(text_layout)
        self.text = QLineEdit()
        self.text.textEdited.connect(lambda value: self.layer_change('text', value))
        text_form.addRow('Text', self.text)
        self.text_size = NumberSlider()
        self.text_size.setRange(1, 512)
        self.text_size.valueChanged.connect(lambda value: self.layer_change('text_size', value))
        text_form.addRow('Text size (px)', self.text_size)
        self.text_color = QPushButton('Text colour…')
        self.text_color.clicked.connect(self.choose_text_color)
        text_form.addRow(self.text_color)
        reset = QPushButton('Reset overlay transforms')
        reset.clicked.connect(self.reset_layer)
        overlay_layout.addWidget(reset)

        self.output_group, output_box = section('Output')
        output_form = form_in(output_box)
        self.preset = QComboBox()
        self.preset.addItems(['Icon · 1:1', 'Cover · 2:3', 'Header · 96:31', 'Background · 16:9', 'Original size', 'Custom'])
        self.preset.setCurrentIndex(list(PRESETS).index(image_type))
        self.preset.currentIndexChanged.connect(self.set_preset)
        output_form.addRow('Aspect / size', self.preset)
        self.width_control, self.height_control = NumberSlider(), NumberSlider()
        for control, value in zip((self.width_control, self.height_control), self.scene['size']):
            control.setRange(1, 4096)
            control.setValue(value)
            control.valueChanged.connect(self.change_size)
        output_form.addRow('Width (px)', self.width_control)
        output_form.addRow('Height (px)', self.height_control)
        controls.addStretch()
        self.drag_target = QLabel()
        layout.addWidget(self.drag_target)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.save)
        buttons.rejected.connect(self.reject)
        buttons.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        footer = QHBoxLayout()
        self.undo_button, self.redo_button = QPushButton('Undo'), QPushButton('Redo')
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        footer.addWidget(self.undo_button)
        footer.addWidget(self.redo_button)
        footer.addStretch()
        self.download_button = QPushButton('Download image…')
        self.download_button.clicked.connect(self.download_source)
        footer.addWidget(self.download_button)
        footer.addWidget(buttons)
        layout.addLayout(footer)
        for slider in content.findChildren(NumberSlider):
            slider.sliderPressed.connect(self.begin_slider_drag)
            slider.sliderReleased.connect(self.end_slider_drag)
        controls.activate()
        panel_width = max(370, content.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 2 * scroll.frameWidth())
        scroll.setMinimumWidth(panel_width)
        scroll.setMaximumWidth(panel_width)
        self.sync_scene()
        self.render()

    def snapshot(self):
        return dict(self.scene, layers=[dict(layer) for layer in self.scene['layers']])

    def begin_slider_drag(self):
        self.remember()
        self.dragging_slider = True

    def end_slider_drag(self):
        self.dragging_slider = False

    def remember(self):
        if self.syncing or self.dragging_slider:
            return
        self.undo_states.append(self.snapshot())
        self.undo_states = self.undo_states[-100:]
        self.redo_states.clear()

    def layer_index(self):
        item = self.layers.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else 0

    def layer(self):
        return self.scene['layers'][self.layer_index()]

    def render(self):
        w, h = self.scene['size']
        scale = min(1, 900 / max(w, h))
        self.preview_image = render_scene(self.scene, max(1, round(w * scale)), max(1, round(h * scale)))
        self.canvas.update()
        self.undo_button.setEnabled(bool(self.undo_states))
        self.redo_button.setEnabled(bool(self.redo_states))

    def scene_change(self, key, value):
        if self.syncing or self.scene[key] == value:
            return
        self.remember()
        self.scene[key] = value
        if key == 'shape' and value == 'Circle':
            self.scene['border_radius'] = min(self.scene['size']) // 2
        if key == 'shape':
            self.sync_scene()
        self.render()

    def source_layer_change(self, key, value):
        if self.syncing or self.scene['layers'][0][key] == value:
            return
        self.remember()
        self.scene['layers'][0][key] = value
        self.layers.setCurrentRow(-1)
        self.sync_layer()
        self.render()

    def reset_source(self):
        self.remember()
        self.scene['layers'][0].update(x=.5, y=.5, zoom=100, rotation=0, opacity=100)
        self.layers.setCurrentRow(-1)
        self.sync_layer()
        self.render()

    def toggle_border(self, enabled):
        if self.syncing:
            return
        self.remember()
        self.scene['border_enabled'] = enabled
        if enabled:
            if self.scene['border_shape'] == 'None':
                self.scene['border_shape'] = 'Follow crop'
            if self.scene['border_style'] == 'None':
                self.scene['border_style'] = 'Solid colour'
            if not self.scene['border']:
                self.scene['border'] = 8
        self.sync_scene()
        self.render()

    def layer_change(self, key, value):
        if self.syncing or self.layer()[key] == value:
            return
        self.remember()
        self.layer()[key] = value
        self.render()

    def pan_layer(self, x, y):
        layer = self.layer()
        if layer['base']:
            scale = self.scene.get('image_size', 100) / 100
            x, y = x / scale, y / scale
        layer['x'] = max(-1, min(2, layer['x'] + x))
        layer['y'] = max(-1, min(2, layer['y'] + y))
        self.sync_layer()
        self.render()

    def sync_layer(self, *_):
        self.syncing = True
        layer = self.layer()
        selected = self.layer_index() > 0
        self.overlay_settings.setVisible(selected)
        self.overlay_empty.setVisible(len(self.scene['layers']) == 1)
        self.layers.setVisible(len(self.scene['layers']) > 1)
        self.drag_target.setText('Drag / wheel edits: ' + (layer['name'] if selected else 'Image'))
        for key, control in self.source_transform.items():
            source = self.scene['layers'][0]
            control.setValue(round(source[key] * 100 if key in ('x', 'y') else source[key]))
        for key, control in self.transform.items():
            control.setValue(round(layer[key] * 100 if key in ('x', 'y') else layer[key]))
        self.text_settings.setVisible(selected and layer['image'] is None)
        self.text.setText(layer['text'])
        self.text.setEnabled(layer['image'] is None)
        self.text_size.setValue(layer['text_size'])
        self.text_size.setEnabled(layer['image'] is None)
        self.text_color.setEnabled(layer['image'] is None)
        self.syncing = False

    def rebuild_layers(self, selected):
        self.layers.blockSignals(True)
        self.layers.clear()
        for index, layer in enumerate(self.scene['layers'][1:], 1):
            item = QListWidgetItem(layer['name'])
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer['visible'] else Qt.CheckState.Unchecked)
            self.layers.addItem(item)
        self.layers.setCurrentRow(selected - 1)
        self.layers.blockSignals(False)
        self.sync_layer()

    def change_visibility(self, item):
        self.remember()
        self.scene['layers'][item.data(Qt.ItemDataRole.UserRole)]['visible'] = item.checkState() == Qt.CheckState.Checked
        self.render()

    def change_border_radius(self, value):
        if self.syncing or self.scene['border_radius'] == value:
            return
        self.remember()
        self.scene['border_radius'] = value
        self.scene['shape'] = 'Rounded rectangle' if value else 'Rectangle'
        if self.scene['border_shape'] in ('Circle', 'Square'):
            self.scene['border_shape'] = 'Rounded square'
        self.sync_scene()
        self.render()

    def choose_border(self):
        from .border_picker import BorderPicker
        picker = BorderPicker(self.scene, self)
        if run_dialog(picker) == QDialog.DialogCode.Accepted:
            changes = picker.selected
            if any(self.scene.get(key) != value for key, value in changes.items()):
                self.remember()
                self.scene.update(changes)
                self.scene['border_enabled'] = changes['border_shape'] != 'None' and changes['border_style'] != 'None'
                self.sync_scene()
                self.render()

    def set_border_style(self, style):
        if self.syncing:
            return
        self.remember()
        self.scene['border_style'] = style
        self.scene['border_enabled'] = style != 'None'
        if style != 'None' and not self.scene['border']:
            self.scene['border'] = 8
        self.sync_scene()
        self.render()

    def set_border_shape(self, shape):
        if self.syncing:
            return
        self.remember()
        self.scene['border_shape'] = shape
        self.scene['border_enabled'] = shape != 'None'
        if shape == 'Circle':
            self.scene['border_radius'] = min(self.scene['size']) // 2
        elif shape == 'Square':
            self.scene['border_radius'] = 0
        elif shape == 'Rounded square' and not self.scene['border_radius']:
            self.scene['border_radius'] = min(32, min(self.scene['size']) // 2)
        if shape not in ('None', 'Follow crop') and not self.scene['border']:
            self.scene['border'] = 8
        self.sync_scene()
        self.render()

    def set_preset(self, index):
        if self.syncing or index == 5:
            return
        source = self.scene['layers'][0]['image']
        scale = min(1, 4096 / max(source.width(), source.height()))
        size = list(PRESETS.values())[index] if index < 4 else (max(1, round(source.width() * scale)), max(1, round(source.height() * scale)))
        self.remember()
        self.scene['size'] = size
        self.sync_scene()
        self.render()

    def change_size(self, *_):
        if self.syncing:
            return
        self.remember()
        self.scene['size'] = (self.width_control.value(), self.height_control.value())
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(5)
        self.preset.blockSignals(False)
        self.sync_scene()
        self.render()

    def sync_scene(self):
        self.syncing = True
        self.width_control.setValue(self.scene['size'][0])
        self.height_control.setValue(self.scene['size'][1])
        self.fit.setCurrentText(self.scene['fit'])
        self.shape.setCurrentText(self.scene['shape'])
        self.border_shape.setCurrentText(self.scene.get('border_shape', 'Follow crop'))
        self.border_style.setCurrentText(self.scene.get('border_style', 'Solid colour'))
        self.image_size.setValue(self.scene.get('image_size', 100))
        self.border_size.setValue(self.scene.get('border_size', 100))
        self.border.setValue(self.scene['border'])
        enabled = self.scene.get('border_enabled', False)
        self.enable_border.setChecked(enabled)
        self.border_settings.setVisible(enabled)
        has_shape = enabled and self.scene.get('border_shape') != 'None'
        self.border_style.setEnabled(has_shape)
        self.border.setEnabled(has_shape and self.scene.get('border_style') != 'None')
        self.border_color_button.setEnabled(has_shape and self.scene.get('border_style') == 'Solid colour')
        limit = min(self.scene['size']) // 2
        self.border_radius.setRange(0, limit)
        self.scene['border_radius'] = min(self.scene.get('border_radius', 0), limit)
        self.border_radius.setValue(self.scene['border_radius'])
        self.transparent_outside.setEnabled(has_shape)
        self.transparent_outside.setChecked(self.scene.get('transparent_outside', False))
        self.border_radius.setEnabled(True)
        self.border_radius.setToolTip('Corner radius in output pixels. Changing it turns circles or squares into rounded shapes.')
        source = self.scene['layers'][0]['image']
        scale = min(1, 4096 / max(source.width(), source.height()))
        original = (max(1, round(source.width() * scale)), max(1, round(source.height() * scale)))
        index = next((i for i, size in enumerate(PRESETS.values()) if size == self.scene['size']),
                     4 if self.scene['size'] == original else 5)
        self.preset.setCurrentIndex(index)
        self.syncing = False
        self.rebuild_layers(min(self.layer_index(), len(self.scene['layers']) - 1))

    def choose_scene_color(self, key):
        color = QColorDialog.getColor(QColor(self.scene[key]) if self.scene[key] != 'transparent' else QColor('black'), self)
        if color.isValid():
            self.scene_change(key, color.name())

    def choose_text_color(self):
        color = QColorDialog.getColor(QColor(self.layer()['color']), self)
        if color.isValid():
            self.layer_change('color', color.name())

    def download_source(self):
        if self.pick_source:
            path = self.pick_source(self)
        else:
            path, _ = choose_file(self, 'Source image', '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp *.ico)')
        if not path:
            return
        try:
            layer = image_layer(QImage(str(path)), 'Source image', True)
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.remember()
        self.scene['layers'][0] = layer
        self.error.clear()
        self.sync_scene()
        self.render()

    def add_image(self):
        if self.pick_overlay:
            path = self.pick_overlay(self)
        else:
            path, _ = choose_file(self, 'Overlay image', '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp *.ico)')
        if not path:
            return
        try:
            layer = image_layer(QImage(str(path)), Path(path).name)
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.remember()
        self.scene['layers'].append(layer)
        self.rebuild_layers(len(self.scene['layers']) - 1)
        self.render()

    def add_text(self):
        text, accepted = QInputDialog.getText(self, 'Text overlay', 'Text')
        if accepted and text.strip():
            self.remember()
            layer = dict(self.scene['layers'][0], image=None, base=False, name='Text: ' + text, text=text,
                         zoom=100, rotation=0, opacity=100, x=.5, y=.5, visible=True)
            self.scene['layers'].append(layer)
            self.rebuild_layers(len(self.scene['layers']) - 1)
            self.render()

    def move_layer(self, direction):
        row = self.layer_index()
        target = row + direction
        if row <= 0 or not 1 <= target < len(self.scene['layers']):
            return
        self.remember()
        layers = self.scene['layers']
        layers[row], layers[target] = layers[target], layers[row]
        self.rebuild_layers(target)
        self.render()

    def remove_layer(self):
        row = self.layer_index()
        if row <= 0:
            return
        self.remember()
        del self.scene['layers'][row]
        self.rebuild_layers(row - 1)
        self.render()

    def reset_layer(self):
        self.remember()
        self.layer().update(x=.5, y=.5, zoom=100, rotation=0, opacity=100)
        self.sync_layer()
        self.render()

    def undo(self):
        if self.undo_states:
            self.redo_states.append(self.snapshot())
            self.scene = self.undo_states.pop()
            self.sync_scene()
            self.render()

    def redo(self):
        if self.redo_states:
            self.undo_states.append(self.snapshot())
            self.scene = self.redo_states.pop()
            self.sync_scene()
            self.render()

    def save(self):
        output = str(Path(self.cache.name) / (self.image_type + '.png'))
        if render_scene(self.scene).save(output, 'PNG'):
            self.output = output
            self.accept()
        else:
            self.error.setText('Could not save the edited image. Choose Apply to try again.')


class IconStudio(ImageStudio):
    """Compatibility for earlier callers; new editor defaults to a rectangular crop."""
    def __init__(self, source, parent=None):
        super().__init__(source, 'Icon', parent)
        self.shape.setCurrentText('Circle')
