"""Synchronized slider and editable number, with wheel events kept local."""
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QSpinBox


class LocalWheelSlider(QSlider):
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class LocalWheelSpinBox(QSpinBox):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.interpretText()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class NumberSlider(QWidget):
    valueChanged = pyqtSignal(int)
    sliderPressed = pyqtSignal()
    sliderReleased = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.slider = LocalWheelSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(100)
        self.number = LocalWheelSpinBox()
        self.number.setKeyboardTracking(False)
        self.number.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.number.setRange(self.slider.minimum(), self.slider.maximum())
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.number)
        self.slider.valueChanged.connect(self.update_value)
        self.number.valueChanged.connect(self.slider.setValue)
        self.slider.sliderPressed.connect(self.sliderPressed.emit)
        self.slider.sliderReleased.connect(self.sliderReleased.emit)

    def update_value(self, value):
        blocker = QSignalBlocker(self.number)
        self.number.setValue(value)
        del blocker
        self.valueChanged.emit(value)

    def setRange(self, minimum, maximum):
        blocker = QSignalBlocker(self.number)
        self.number.setRange(minimum, maximum)
        self.slider.setRange(minimum, maximum)
        self.number.setValue(self.slider.value())
        del blocker

    def setValue(self, value):
        self.slider.setValue(value)

    def value(self):
        return self.slider.value()
