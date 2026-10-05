"""Native image composition editor with crop, pan, zoom and layered overlays."""
import tempfile
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QColor, QPen
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QCheckBox, QLabel, QSlider, QComboBox, QSpinBox, QPushButton, QDialogButtonBox, QListWidget,
    QListWidgetItem, QLineEdit, QColorDialog, QInputDialog, QScrollArea)
from playlite.lifecycle import choose_file
from .model import PRESETS, image_layer, render_scene


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
    def __init__(self, source, image_type='Icon', parent=None, pick_overlay=None):
        super().__init__(parent)
        self.setWindowTitle('Image Studio')
        self.resize(1150, 820)
        image = QImage(str(source))
        self.scene = dict(size=PRESETS[image_type], shape='Rectangle', fit='Fill',
            background='transparent', border=0, border_color='#ffffff', border_shape='Follow crop', border_style='Solid colour', border_radius=32, transparent_outside=False,
            layers=[image_layer(image, 'Source image', True)])
        self.image_type = image_type
        self.pick_overlay = pick_overlay
        self.output = None
        self.cache = tempfile.TemporaryDirectory(prefix='playlite-image-studio-')
        self.undo_states, self.redo_states = [], []
        self.preview_image = None
        self.syncing = False
        layout = QVBoxLayout(self)
        help_text = QLabel('Drag to pan the selected layer; use the mouse wheel to zoom. The blue frame is the crop and exported image. Edits stay in this window until Apply, then save the game to keep them.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        self.canvas = Canvas(self)
        body.addWidget(self.canvas, 1)
        self.canvas.dragStarted.connect(self.remember)
        self.canvas.pan.connect(self.pan_layer)
        self.canvas.zoom.connect(lambda delta: self.transform['zoom'].setValue(self.layer()['zoom'] + delta))
        content = QWidget()
        controls = QVBoxLayout(content)
        content.setContentsMargins(12, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(370)
        scroll.setMaximumWidth(400)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(scroll)
        controls.addWidget(QLabel('Crop / output'))
        form = QFormLayout()
        controls.addLayout(form)
        self.preset = QComboBox()
        self.preset.addItems(['Icon · 1:1', 'Cover · 2:3', 'Header · 96:31', 'Background · 16:9', 'Original size', 'Custom'])
        self.preset.setCurrentIndex(list(PRESETS).index(image_type))
        self.preset.currentIndexChanged.connect(self.set_preset)
        form.addRow('Aspect / size', self.preset)
        size_row = QHBoxLayout()
        self.width_control, self.height_control = QSpinBox(), QSpinBox()
        for control, value in zip((self.width_control, self.height_control), self.scene['size']):
            control.setRange(1, 4096)
            control.setValue(value)
            control.valueChanged.connect(self.change_size)
            size_row.addWidget(control)
        form.addRow('Pixels (W × H)', size_row)
        self.fit = QComboBox()
        self.fit.addItems(['Fill', 'Fit'])
        self.fit.currentTextChanged.connect(lambda value: self.scene_change('fit', value))
        form.addRow('Source sizing', self.fit)
        self.shape = QComboBox()
        self.shape.addItems(['Rectangle', 'Rounded rectangle', 'Circle'])
        self.shape.currentTextChanged.connect(lambda value: self.scene_change('shape', value))
        form.addRow('Crop shape', self.shape)
        colors = QHBoxLayout()
        background = QPushButton('Background…')
        background.clicked.connect(lambda: self.choose_scene_color('background'))
        clear = QPushButton('Transparent')
        clear.clicked.connect(lambda: self.scene_change('background', 'transparent'))
        colors.addWidget(background)
        colors.addWidget(clear)
        form.addRow(colors)
        self.border_shape = QComboBox()
        self.border_shape.addItems(['Follow crop', 'Circle', 'Square', 'Rounded square'])
        self.border_shape.currentTextChanged.connect(self.set_border_shape)
        form.addRow('Stock border', self.border_shape)
        self.border_style = QComboBox()
        self.border_style.addItems(['Silver', 'Gold', 'Dark metal', 'Solid colour', 'None'])
        self.border_style.currentTextChanged.connect(self.set_border_style)
        form.addRow('Frame style', self.border_style)
        self.border = QSpinBox()
        self.border.setRange(0, 100)
        self.border.valueChanged.connect(lambda value: self.scene_change('border', value))
        border_row = QHBoxLayout()
        border_row.addWidget(self.border)
        border_color = self.border_color_button = QPushButton('Color…')
        border_color.clicked.connect(lambda: self.choose_scene_color('border_color'))
        border_row.addWidget(border_color)
        form.addRow('Border (px)', border_row)
        self.border_radius = QSpinBox()
        self.border_radius.setRange(0, 2048)
        self.border_radius.valueChanged.connect(lambda value: self.scene_change('border_radius', value))
        form.addRow('Border radius (px)', self.border_radius)
        self.transparent_outside = QCheckBox('Transparent outside border')
        self.transparent_outside.toggled.connect(lambda value: self.scene_change('transparent_outside', value))
        form.addRow(self.transparent_outside)
        controls.addWidget(QLabel('Layers · select a layer to edit it'))
        self.layers = QListWidget()
        self.layers.setMaximumHeight(130)
        self.layers.currentRowChanged.connect(self.sync_layer)
        self.layers.itemChanged.connect(self.change_visibility)
        controls.addWidget(self.layers)
        for entries in ([('Add image…', self.add_image), ('Add text…', self.add_text)],
                        [('Raise', lambda: self.move_layer(1)), ('Lower', lambda: self.move_layer(-1)), ('Remove', self.remove_layer)]):
            row = QHBoxLayout()
            for title, callback in entries:
                button = QPushButton(title)
                button.clicked.connect(callback)
                row.addWidget(button)
            controls.addLayout(row)
        transform_form = QFormLayout()
        controls.addLayout(transform_form)
        self.transform = {}
        for name, title, low, high in [('zoom', 'Zoom (%)', 10, 800), ('x', 'Pan X (%)', -100, 200),
                                      ('y', 'Pan Y (%)', -100, 200), ('rotation', 'Rotation (°)', -180, 180),
                                      ('opacity', 'Opacity (%)', 0, 100)]:
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.valueChanged.connect(lambda value, key=name: self.layer_change(key, value / 100 if key in ('x', 'y') else value))
            self.transform[name] = spin
            transform_form.addRow(title, spin)
        self.text = QLineEdit()
        self.text.textEdited.connect(lambda value: self.layer_change('text', value))
        transform_form.addRow('Text', self.text)
        self.text_size = QSpinBox()
        self.text_size.setRange(1, 512)
        self.text_size.valueChanged.connect(lambda value: self.layer_change('text_size', value))
        transform_form.addRow('Text size (px)', self.text_size)
        self.text_color = QPushButton('Text color…')
        self.text_color.clicked.connect(self.choose_text_color)
        transform_form.addRow(self.text_color)
        reset = QPushButton('Reset selected layer position / zoom')
        reset.clicked.connect(self.reset_layer)
        controls.addWidget(reset)
        history = QHBoxLayout()
        self.undo_button, self.redo_button = QPushButton('Undo'), QPushButton('Redo')
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        history.addWidget(self.undo_button)
        history.addWidget(self.redo_button)
        controls.addLayout(history)
        controls.addStretch()
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.rebuild_layers(0)
        self.render()

    def snapshot(self):
        return dict(self.scene, layers=[dict(layer) for layer in self.scene['layers']])

    def remember(self):
        if self.syncing:
            return
        self.undo_states.append(self.snapshot())
        self.undo_states = self.undo_states[-100:]
        self.redo_states.clear()

    def layer(self):
        return self.scene['layers'][max(0, self.layers.currentRow())]

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
        if key == 'shape':
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
        layer['x'] = max(-1, min(2, layer['x'] + x))
        layer['y'] = max(-1, min(2, layer['y'] + y))
        self.sync_layer()
        self.render()

    def sync_layer(self, *_):
        self.syncing = True
        layer = self.layer()
        for key, control in self.transform.items():
            control.setValue(round(layer[key] * 100 if key in ('x', 'y') else layer[key]))
        self.text.setText(layer['text'])
        self.text.setEnabled(layer['image'] is None)
        self.text_size.setValue(layer['text_size'])
        self.text_size.setEnabled(layer['image'] is None)
        self.text_color.setEnabled(layer['image'] is None)
        self.syncing = False

    def rebuild_layers(self, selected):
        self.layers.blockSignals(True)
        self.layers.clear()
        for layer in self.scene['layers']:
            item = QListWidgetItem(layer['name'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if layer['visible'] else Qt.CheckState.Unchecked)
            self.layers.addItem(item)
        self.layers.setCurrentRow(selected)
        self.layers.blockSignals(False)
        self.sync_layer()

    def change_visibility(self, item):
        self.remember()
        self.scene['layers'][self.layers.row(item)]['visible'] = item.checkState() == Qt.CheckState.Checked
        self.render()

    def set_border_style(self, style):
        if self.syncing:
            return
        self.remember()
        self.scene['border_style'] = style
        if style != 'None' and not self.scene['border']:
            self.scene['border'] = 8
        self.sync_scene()
        self.render()

    def set_border_shape(self, shape):
        if self.syncing:
            return
        self.remember()
        self.scene['border_shape'] = shape
        if shape != 'Follow crop' and not self.scene['border']:
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
        self.render()

    def sync_scene(self):
        self.syncing = True
        self.width_control.setValue(self.scene['size'][0])
        self.height_control.setValue(self.scene['size'][1])
        self.fit.setCurrentText(self.scene['fit'])
        self.shape.setCurrentText(self.scene['shape'])
        self.border_shape.setCurrentText(self.scene.get('border_shape', 'Follow crop'))
        self.border_style.setCurrentText(self.scene.get('border_style', 'Solid colour'))
        self.border.setValue(self.scene['border'])
        self.border.setEnabled(self.scene.get('border_style') != 'None')
        self.border_color_button.setEnabled(self.scene.get('border_style') == 'Solid colour')
        self.border_radius.setValue(self.scene.get('border_radius', 32))
        self.transparent_outside.setChecked(self.scene.get('transparent_outside', False))
        rounded = self.scene.get('border_shape') == 'Rounded square' or (self.scene.get('border_shape') == 'Follow crop' and self.scene['shape'] == 'Rounded rectangle')
        self.border_radius.setEnabled(rounded)
        source = self.scene['layers'][0]['image']
        scale = min(1, 4096 / max(source.width(), source.height()))
        original = (max(1, round(source.width() * scale)), max(1, round(source.height() * scale)))
        index = next((i for i, size in enumerate(PRESETS.values()) if size == self.scene['size']),
                     4 if self.scene['size'] == original else 5)
        self.preset.setCurrentIndex(index)
        self.syncing = False
        self.rebuild_layers(min(max(0, self.layers.currentRow()), len(self.scene['layers']) - 1))

    def choose_scene_color(self, key):
        color = QColorDialog.getColor(QColor(self.scene[key]) if self.scene[key] != 'transparent' else QColor('black'), self)
        if color.isValid():
            self.scene_change(key, color.name())

    def choose_text_color(self):
        color = QColorDialog.getColor(QColor(self.layer()['color']), self)
        if color.isValid():
            self.layer_change('color', color.name())

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
        row = self.layers.currentRow()
        target = row + direction
        if row <= 0 or not 1 <= target < len(self.scene['layers']):
            return
        self.remember()
        layers = self.scene['layers']
        layers[row], layers[target] = layers[target], layers[row]
        self.rebuild_layers(target)
        self.render()

    def remove_layer(self):
        row = self.layers.currentRow()
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
