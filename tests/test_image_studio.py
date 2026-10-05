from plugin_test_support import require_plugin
PLUGIN = require_plugin('IconStudio')
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QColor, QPainter
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton
from PyQt6.QtTest import QTest
from playlite.editor import MetadataEditor
from playlite_plugins.iconstudio.studio import ImageStudio
from playlite_plugins.iconstudio.model import PRESETS, image_layer, render_scene

APP = QApplication.instance() or QApplication([])


class ImageStudioTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'source.png'
        image = QImage(400, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        painter = QPainter(image)
        painter.fillRect(200, 0, 200, 100, QColor('blue'))
        painter.end()
        image.save(str(self.source))
        self.original = self.source.read_bytes()

    def studio(self, kind='Icon'):
        studio = ImageStudio(self.source, kind)
        self.addCleanup(studio.cache.cleanup)
        self.addCleanup(studio.close)
        return studio

    def test_stock_borders_preserve_canvas_and_undo(self):
        studio = self.studio('HeaderImage')
        original_size = studio.scene['size']
        for shape in ('Circle', 'Square', 'Rounded square'):
            studio.border_shape.setCurrentText(shape)
            self.assertEqual(studio.scene['size'], original_size)
            self.assertEqual(studio.scene['border'], 8)
            result = render_scene(studio.scene, 960, 310)
            self.assertEqual((result.width(), result.height()), (960, 310))
            self.assertGreater(result.pixelColor(480, 2).green(), 150)
        studio.undo()
        self.assertEqual(studio.border_shape.currentText(), 'Square')
        studio.undo()
        studio.undo()
        self.assertEqual(studio.border_shape.currentText(), 'Follow crop')
        self.assertEqual(studio.border.value(), 0)

    def test_all_image_types_export_expected_dimensions_and_leave_source_untouched(self):
        for kind, size in PRESETS.items():
            studio = self.studio(kind)
            studio.save()
            result = QImage(studio.output)
            self.assertEqual((result.width(), result.height()), size)
            self.assertEqual(studio.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_pan_changes_crop_and_fit_preserves_transparency(self):
        studio = self.studio()
        before = render_scene(studio.scene)
        self.assertEqual(before.pixelColor(32, 128).name(), '#ff0000')
        studio.transform['x'].setValue(0)
        moved = render_scene(studio.scene)
        self.assertEqual(moved.pixelColor(32, 128).name(), '#0000ff')
        studio.undo()
        self.assertEqual(studio.layer()['x'], .5)
        studio.fit.setCurrentText('Fit')
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(128, 0).alpha(), 0)
        studio.shape.setCurrentText('Circle')
        self.assertEqual(render_scene(studio.scene).pixelColor(0, 0).alpha(), 0)

    def test_overlays_opacity_layer_order_and_undo_redo(self):
        studio = self.studio()
        overlay = QImage(40, 40, QImage.Format.Format_ARGB32)
        overlay.fill(QColor('lime'))
        studio.remember()
        studio.scene['layers'].append(image_layer(overlay, 'Overlay'))
        studio.rebuild_layers(1)
        studio.render()
        self.assertEqual(render_scene(studio.scene).pixelColor(128, 128).name(), '#00ff00')
        studio.transform['opacity'].setValue(0)
        self.assertNotEqual(render_scene(studio.scene).pixelColor(128, 128).name(), '#00ff00')
        studio.undo()
        self.assertEqual(studio.layer()['opacity'], 100)
        studio.redo()
        self.assertEqual(studio.layer()['opacity'], 0)
        studio.remove_layer()
        self.assertEqual(len(studio.scene['layers']), 1)
        studio.undo()
        self.assertEqual(len(studio.scene['layers']), 2)
        studio.layers.setCurrentRow(0)
        studio.remove_layer()
        self.assertEqual(len(studio.scene['layers']), 2)  # Base source remains.

    def test_text_overlay_and_custom_crop(self):
        studio = self.studio()
        with patch('playlite_plugins.iconstudio.studio.QInputDialog.getText', return_value=('Example', True)):
            studio.add_text()
        self.assertEqual(studio.layer()['text'], 'Example')
        self.assertIsNone(studio.layer()['image'])
        studio.width_control.setValue(500)
        studio.height_control.setValue(250)
        studio.save()
        result = QImage(studio.output)
        self.assertEqual((result.width(), result.height()), (500, 250))
        self.assertEqual(studio.preset.currentText(), 'Custom')

    def test_canvas_drag_pans_selected_layer_and_can_be_undone(self):
        studio = self.studio()
        studio.show()
        QTest.qWait(20)
        center = studio.canvas.frame.center().toPoint()
        QTest.mousePress(studio.canvas, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(studio.canvas, center + QPoint(25, 0))
        QTest.mouseRelease(studio.canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(25, 0))
        self.assertGreater(studio.layer()['x'], .5)
        studio.undo()
        self.assertEqual(studio.layer()['x'], .5)

    def test_buttons_are_next_to_each_image_type_and_cancel_does_not_change_media(self):
        editor = MetadataEditor(dict(Id='test', Name='Example'), self.root)
        self.addCleanup(editor.reject)
        self.assertEqual(set(editor.media_cards), set(PRESETS))
        for key, card in editor.media_cards.items():
            self.assertEqual(len(card.findChildren(QPushButton, 'imageStudio' + key)), 1)
        plugin = require_plugin('IconStudio')
        module = importlib.import_module(plugin.__class__.__module__)
        with patch.object(plugin, 'pick_image', return_value=str(self.source)), patch.object(module, 'run_dialog', return_value=QDialog.DialogCode.Rejected):
            plugin.open_studio(editor, 'HeaderImage')
        self.assertEqual(editor.media['HeaderImage'].text(), '')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_apply_updates_only_target_image_and_keeps_output_until_game_save(self):
        editor = MetadataEditor(dict(Id='test', Name='Example'), self.root)
        self.addCleanup(editor.reject)
        plugin = require_plugin('IconStudio')
        module = importlib.import_module(plugin.__class__.__module__)
        def apply(dialog):
            dialog.save()
            return QDialog.DialogCode.Accepted
        with patch.object(plugin, 'pick_image', return_value=str(self.source)), patch.object(module, 'run_dialog', side_effect=apply):
            plugin.open_studio(editor, 'CoverImage')
        path = editor.media['CoverImage'].text()
        self.assertTrue(Path(path).exists())
        self.assertEqual(editor.media['Icon'].text(), '')
        self.assertEqual(QImage(path).height(), 900)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse((self.root / 'library.json').exists())

    def test_picker_opens_requested_tab_and_uses_current_unsaved_game_name(self):
        editor = MetadataEditor(dict(Id='test', Name='Old name'), self.root)
        self.addCleanup(editor.reject)
        editor.fields['Name'].setText('Updated name')
        plugin = require_plugin('IconStudio')
        module = importlib.import_module(plugin.__class__.__module__)
        def pick(dialog):
            self.assertEqual(dialog.active_key, 'BackgroundImage')
            self.assertEqual(dialog.controls['BackgroundImage'][1].text(), 'Updated name')
            dialog.applied['BackgroundImage'] = str(self.source)
            return QDialog.DialogCode.Accepted
        caches = []
        with patch.object(module, 'run_dialog', side_effect=pick):
            self.assertEqual(plugin.pick_image(editor, 'BackgroundImage', caches=caches), str(self.source))
        self.assertEqual(len(caches), 1)
        for cache in caches:
            cache.cleanup()

    def test_overlay_picker_defaults_to_logos(self):
        editor = MetadataEditor(dict(Id='test', Name='Example'), self.root)
        self.addCleanup(editor.reject)
        plugin = require_plugin('IconStudio')
        module = importlib.import_module(plugin.__class__.__module__)
        def pick(dialog):
            self.assertEqual(dialog.active_key, 'Logo')
            self.assertEqual(dialog.filters['Logo'][0].values(), ['Logo'])
            dialog.show_images({'Logo': ([('Logo', str(self.source), {'Logo'})], [])})
            dialog.select_image(key='Logo')
            self.assertEqual(dialog.applied, {'HeaderImage': str(self.source)})
            return QDialog.DialogCode.Accepted
        caches = []
        with patch.object(module, 'run_dialog', side_effect=pick):
            self.assertEqual(plugin.pick_image(editor, 'HeaderImage', caches=caches, logos=True), str(self.source))
        for cache in caches:
            cache.cleanup()

    def test_transparent_outside_border_masks_background_and_overlays(self):
        studio = self.studio('HeaderImage')
        studio.border_shape.setCurrentText('Circle')
        studio.scene_change('background', '#00ff00')
        studio.scene['layers'].append(image_layer(QImage(str(self.source)), 'Overlay'))
        studio.scene['layers'][-1]['zoom'] = 800
        self.assertEqual(render_scene(studio.scene).pixelColor(0, 0).alpha(), 255)
        studio.transparent_outside.setChecked(True)
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(result.pixelColor(960, 310).alpha(), 255)
        studio.undo()
        self.assertFalse(studio.transparent_outside.isChecked())
        self.assertEqual(render_scene(studio.scene).pixelColor(0, 0).alpha(), 255)

    def test_rounded_border_radius_changes_outline_and_undo_restores_it(self):
        studio = self.studio()
        studio.border_shape.setCurrentText('Rounded square')
        studio.transparent_outside.setChecked(True)
        studio.border_radius.setValue(0)
        self.assertGreater(render_scene(studio.scene).pixelColor(8, 8).alpha(), 200)
        studio.border_radius.setValue(100)
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 0)
        studio.undo()
        self.assertEqual(studio.border_radius.value(), 0)
        self.assertGreater(render_scene(studio.scene).pixelColor(8, 8).alpha(), 200)
