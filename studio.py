from playlite.theme import colour
"""Native icon crop and frame editor."""
import tempfile
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QPen, QColor, QPixmap
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel, QSlider, QComboBox, QDialogButtonBox


class IconStudio(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Icon Studio')
        self.source = QImage(str(source))
        self.output = None
        self.cache = tempfile.TemporaryDirectory(prefix='playlite-icon-')
        layout = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)
        form = QFormLayout()
        layout.addLayout(form)
        self.controls = {}
        for name, low, high, initial in [('Zoom', 100, 300, 100), ('Horizontal', -100, 100, 0), ('Vertical', -100, 100, 0), ('Border', 0, 12, 3)]:
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(initial)
            slider.valueChanged.connect(self.render)
            self.controls[name] = slider
            form.addRow(name, slider)
        self.shape = QComboBox()
        self.shape.addItems(['Circle', 'Rounded square', 'Square'])
        self.shape.currentIndexChanged.connect(self.render)
        form.addRow('Shape', self.shape)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.render()

    def render(self):
        self.image = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
        self.image.fill(Qt.GlobalColor.transparent)
        if self.source.isNull():
            return
        painter = QPainter(self.image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        area = QRectF(8, 8, 240, 240)
        clip = QPainterPath()
        radius = [120, 30, 0][self.shape.currentIndex()]
        clip.addRoundedRect(area, radius, radius)
        scale = max(240 / self.source.width(), 240 / self.source.height()) * self.controls['Zoom'].value() / 100
        width, height = self.source.width() * scale, self.source.height() * scale
        x = 8 - (width - 240) * (self.controls['Horizontal'].value() / 100 + 1) / 2
        y = 8 - (height - 240) * (self.controls['Vertical'].value() / 100 + 1) / 2
        painter.save()
        painter.setClipPath(clip)
        painter.drawImage(QRectF(x, y, width, height), self.source)
        painter.restore()
        border = self.controls['Border'].value()
        if border:
            painter.setPen(QPen(QColor(colour('#b8b8b8')), border))
            painter.drawPath(clip)
        painter.end()
        self.preview.setPixmap(QPixmap.fromImage(self.image))

    def save(self):
        self.output = str(Path(self.cache.name) / 'icon.png')
        if self.image.save(self.output):
            self.accept()
