"""Slider with a readable value label and the standard numeric-control API."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel


class NumberSlider(QWidget):
    valueChanged = pyqtSignal(int)
    sliderPressed = pyqtSignal()
    sliderReleased = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(100)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.label.setMinimumWidth(self.label.fontMetrics().horizontalAdvance('-4096'))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.label)
        self.slider.valueChanged.connect(self.update_value)
        self.slider.sliderPressed.connect(self.sliderPressed.emit)
        self.slider.sliderReleased.connect(self.sliderReleased.emit)
        self.update_value(self.slider.value())

    def update_value(self, value):
        self.label.setText(str(value))
        self.valueChanged.emit(value)

    def setRange(self, minimum, maximum):
        self.slider.setRange(minimum, maximum)

    def setValue(self, value):
        self.slider.setValue(value)

    def value(self):
        return self.slider.value()
