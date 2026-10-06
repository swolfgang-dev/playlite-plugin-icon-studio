from plugin_test_support import require_plugin
require_plugin('ImageStudio')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication
from playlite_plugins.imagestudio.studio import IconStudio

APP = QApplication.instance() or QApplication([])

class StudioTests(unittest.TestCase):
    def test_generated_icon_is_square_and_keeps_transparent_corners(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source.png'
            image = QImage(600, 900, QImage.Format.Format_ARGB32)
            image.fill(QColor('red'))
            image.save(str(source))
            studio = IconStudio(source)
            studio.save()
            icon = QImage(studio.output)
            self.assertEqual((icon.width(), icon.height()), (256, 256))
            self.assertEqual(icon.pixelColor(0, 0).alpha(), 0)
            studio.cache.cleanup()
