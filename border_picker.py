"""Preview vector border presets on the current composition before applying."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                            QFormLayout, QListWidget, QListWidgetItem, QDialogButtonBox)
from .model import render_scene
from .number_slider import NumberSlider

STYLES = ('Silver', 'Gold', 'Dark metal', 'Solid colour', 'None')
SHAPES = ('None', 'Follow crop', 'Circle', 'Square', 'Rounded square')


class BorderPicker(QDialog):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose border — Image Studio')
        self.resize(820, 570)
        self.scene = dict(scene, layers=[dict(layer) for layer in scene['layers']])
        layout = QVBoxLayout(self)
        hint = QLabel('Compare borders on your image. Select a style, then Apply.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QFormLayout()
        row.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.shape = QComboBox()
        self.shape.addItems(SHAPES)
        self.shape.setCurrentText(scene.get('border_shape', 'Follow crop'))
        self.size = NumberSlider()
        self.size.setRange(1, 100)
        self.size.setValue(scene.get('border_size', 100))
        self.rotation = NumberSlider()
        self.rotation.setRange(-180, 180)
        self.rotation.setValue(scene.get('border_rotation', 0))
        self.width = NumberSlider()
        self.width.setRange(0, 100)
        self.width.setValue(scene['border'] or 8)
        self.radius = NumberSlider()
        self.radius.setRange(0, min(scene['size']) // 2)
        self.radius.setValue(scene.get('border_radius', 32))
        for label, widget in [('Shape', self.shape), ('Border size (%)', self.size), ('Rotation (°)', self.rotation), ('Thickness (px)', self.width), ('Radius (px)', self.radius)]:
            row.addRow(label, widget)
        layout.addLayout(row)
        self.styles = QListWidget()
        self.styles.setViewMode(QListWidget.ViewMode.IconMode)
        self.styles.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.styles.setMovement(QListWidget.Movement.Static)
        self.styles.setIconSize(QSize(190, 150))
        self.styles.setGridSize(QSize(220, 190))
        self.styles.setSpacing(8)
        for style in STYLES:
            self.styles.addItem(QListWidgetItem(style))
        self.styles.setCurrentRow(STYLES.index(scene.get('border_style', 'Solid colour')))
        layout.addWidget(self.styles, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Apply')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.styles.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(buttons)
        self.shape.currentTextChanged.connect(self.refresh)
        self.size.valueChanged.connect(self.refresh)
        self.rotation.valueChanged.connect(self.refresh)
        self.width.valueChanged.connect(self.refresh)
        self.radius.valueChanged.connect(self.change_radius)
        self.refresh()

    @property
    def selected(self):
        return dict(border_style=self.styles.currentItem().text(), border_shape=self.shape.currentText(),
                    border=self.width.value(), border_size=self.size.value(), border_rotation=self.rotation.value(), border_radius=self.radius.value(), shape=self.scene['shape'])

    def change_radius(self, *_):
        if self.scene['shape'] == 'Circle':
            self.scene['shape'] = 'Rounded rectangle'
        if self.shape.currentText() == 'Follow crop':
            self.scene['shape'] = 'Rounded rectangle'
        elif self.shape.currentText() in ('Circle', 'Square'):
            self.shape.setCurrentText('Rounded square')
        self.refresh()

    def refresh(self, *_):
        self.radius.setEnabled(self.shape.currentText() != 'None')
        scene = dict(self.scene, border_size=self.size.value(), border_rotation=self.rotation.value(), border_enabled=True, border_shape=self.shape.currentText(), border=self.width.value(),
                     border_radius=self.radius.value())
        w, h = scene['size']
        scale = min(190 / w, 150 / h)
        for index, style in enumerate(STYLES):
            scene['border_style'] = style
            result = render_scene(scene, max(1, round(w * scale)), max(1, round(h * scale)))
            preview = QPixmap(190, 150)
            preview.fill(QColor('#303030'))
            painter = QPainter(preview)
            for y in range(0, 150, 10):
                for x in range(0, 190, 10):
                    if (x // 10 + y // 10) % 2:
                        painter.fillRect(x, y, 10, 10, QColor('#454545'))
            painter.drawImage((190 - result.width()) // 2, (150 - result.height()) // 2, result)
            painter.end()
            self.styles.item(index).setIcon(QIcon(preview))
