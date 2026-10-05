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

    def test_image_and_border_sizes_are_independent_and_overlays_stay_put(self):
        studio = self.studio()
        studio.border_shape.setCurrentText('Square')
        studio.image_size.setValue(50)
        self.assertEqual(studio.border_size.value(), 100)
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(30, 128).alpha(), 0)
        self.assertGreater(result.pixelColor(4, 128).green(), 200)
        self.assertEqual(result.pixelColor(80, 128), QColor('red'))

        studio.image_size.setValue(100)
        studio.border_size.setValue(50)
        self.assertEqual(studio.image_size.value(), 100)
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(30, 128), QColor('red'))
        self.assertGreater(result.pixelColor(68, 128).green(), 200)
        studio.transparent_outside.setChecked(True)
        overlay = QImage(20, 20, QImage.Format.Format_ARGB32)
        overlay.fill(QColor('lime'))
        layer = image_layer(overlay, 'Overlay')
        layer.update(x=.1, y=.1, zoom=30)
        studio.scene['layers'].append(layer)
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(30, 128).alpha(), 0)
        self.assertEqual(result.pixelColor(25, 25), QColor('lime'))
        studio.border_size.setValue(75)
        studio.undo()
        self.assertEqual(studio.border_size.value(), 50)
        self.assertEqual(studio.image_size.value(), 100)

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
        studio.layers.setCurrentRow(-1)
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

    def test_transparent_outside_border_masks_background_and_source(self):
        studio = self.studio('HeaderImage')
        studio.border_shape.setCurrentText('Circle')
        studio.scene_change('background', '#00ff00')
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

    def test_playnite_frame_styles_render_distinct_gradients_and_none(self):
        studio = self.studio()
        studio.border_shape.setCurrentText('Square')
        pixels = {}
        for style in ('Silver', 'Gold', 'Dark metal', 'Solid colour'):
            studio.border_style.setCurrentText(style)
            pixels[style] = render_scene(studio.scene).pixelColor(128, 5)
            self.assertEqual(studio.border_color_button.isEnabled(), style == 'Solid colour')
        self.assertGreater(pixels['Gold'].red(), pixels['Gold'].blue())
        self.assertGreater(pixels['Silver'].red(), pixels['Dark metal'].red())
        self.assertEqual(pixels['Solid colour'].name(), '#ffffff')
        studio.border_style.setCurrentText('None')
        self.assertFalse(studio.border.isEnabled())
        self.assertEqual(render_scene(studio.scene).pixelColor(128, 5).green(), 0)
        studio.undo()
        self.assertEqual(studio.border_style.currentText(), 'Solid colour')
        self.assertTrue(studio.border.isEnabled())

    def test_border_picker_previews_cancel_and_apply_as_one_undo_step(self):
        from playlite_plugins.iconstudio.border_picker import BorderPicker, STYLES
        studio = self.studio()
        before = studio.snapshot()
        module = importlib.import_module(ImageStudio.__module__)
        def cancel(picker):
            self.assertIsInstance(picker, BorderPicker)
            self.assertEqual(picker.styles.count(), len(STYLES))
            self.assertTrue(all(not picker.styles.item(i).icon().isNull() for i in range(len(STYLES))))
            picker.shape.setCurrentText('Rounded square')
            picker.width.setValue(12)
            picker.radius.setValue(60)
            picker.styles.setCurrentRow(STYLES.index('Gold'))
            self.assertEqual(studio.scene, before)
            return QDialog.DialogCode.Rejected
        with patch.object(module, 'run_dialog', side_effect=cancel):
            studio.choose_border()
        self.assertEqual(studio.scene, before)
        self.assertEqual(len(studio.undo_states), 0)
        def apply(picker):
            cancel(picker)
            return QDialog.DialogCode.Accepted
        with patch.object(module, 'run_dialog', side_effect=apply):
            studio.choose_border()
        self.assertEqual(studio.scene['border_style'], 'Gold')
        self.assertEqual(studio.scene['border_shape'], 'Rounded square')
        self.assertEqual(studio.scene['border'], 12)
        self.assertEqual(studio.scene['border_radius'], 60)
        self.assertEqual(len(studio.undo_states), 1)
        studio.undo()
        self.assertEqual(studio.scene, before)

    def test_controls_fit_scroll_viewport_with_large_font(self):
        original_font = APP.font()
        larger_font = APP.font()
        larger_font.setPointSize(18)
        APP.setFont(larger_font)
        self.addCleanup(APP.setFont, original_font)
        studio = self.studio()
        studio.show()
        APP.processEvents()
        scroll = studio.controls_scroll
        content = scroll.widget()
        self.assertLessEqual(content.width(), scroll.viewport().width())
        for button in content.findChildren(QPushButton):
            if button.parentWidget() is content:
                self.assertLessEqual(button.geometry().right(), content.width(), button.text())
        self.assertGreaterEqual(studio.border_picker_button.width(), studio.border_picker_button.minimumSizeHint().width())

    def test_stock_border_none_removes_frame_and_outside_mask(self):
        studio = self.studio()
        studio.border_shape.setCurrentText('Circle')
        studio.transparent_outside.setChecked(True)
        studio.border_style.setCurrentText('Gold')
        self.assertEqual(render_scene(studio.scene).pixelColor(0, 0).alpha(), 0)
        studio.border_shape.setCurrentText('None')
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(0, 0).alpha(), 255)
        self.assertEqual(result.pixelColor(128, 5).green(), 0)
        self.assertFalse(studio.border.isEnabled())
        self.assertFalse(studio.transparent_outside.isEnabled())
        studio.undo()
        self.assertEqual(studio.border_shape.currentText(), 'Circle')
        self.assertEqual(studio.border_style.currentText(), 'Gold')
        self.assertEqual(render_scene(studio.scene).pixelColor(0, 0).alpha(), 0)

    def test_radius_is_editable_and_updates_follow_crop_rectangle(self):
        studio = self.studio()
        self.assertTrue(studio.border_radius.isEnabled())
        studio.border_radius.setValue(100)
        self.assertEqual(studio.scene['shape'], 'Rounded rectangle')
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 0)
        studio.border_radius.setValue(0)
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 255)
        studio.undo()
        self.assertEqual(studio.border_radius.value(), 100)

    def test_follow_crop_circle_radius_changes_actual_crop(self):
        studio = self.studio()
        studio.shape.setCurrentText('Circle')
        self.assertTrue(studio.border_radius.isEnabled())
        studio.border_radius.setValue(0)
        self.assertEqual(studio.shape.currentText(), 'Rectangle')
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 255)
        studio.undo()
        self.assertEqual(studio.shape.currentText(), 'Circle')

    def test_image_and_text_overlays_escape_crop_and_border(self):
        studio = self.studio()
        studio.shape.setCurrentText('Circle')
        studio.border_shape.setCurrentText('Circle')
        studio.transparent_outside.setChecked(True)
        overlay = QImage(40, 40, QImage.Format.Format_ARGB32)
        overlay.fill(QColor('lime'))
        image = image_layer(overlay, 'Logo')
        image.update(x=.08, y=.08)
        studio.scene['layers'].append(image)
        result = render_scene(studio.scene)
        self.assertEqual(result.pixelColor(20, 20).name(), '#00ff00')
        self.assertEqual(result.pixelColor(250, 250).alpha(), 0)
        image.update(x=.5, y=.02)
        self.assertEqual(render_scene(studio.scene).pixelColor(128, 5).name(), '#00ff00')
        image['visible'] = False
        text = dict(image, image=None, text='TEXT', x=.18, y=.09, visible=True, color='#ffffff', text_size=30)
        studio.scene['layers'].append(text)
        result = render_scene(studio.scene)
        self.assertTrue(any(result.pixelColor(x, y).alpha() for x in range(0, 65) for y in range(0, 30)))

    def test_editor_opens_current_image_without_downloader(self):
        editor = MetadataEditor(dict(Id='test', Name='Example'), self.root)
        self.addCleanup(editor.reject)
        editor.media['HeaderImage'].setText(str(self.source))
        plugin = require_plugin('IconStudio')
        module = importlib.import_module(plugin.__class__.__module__)
        def inspect(studio):
            self.assertEqual(studio.image_type, 'HeaderImage')
            self.assertEqual(studio.scene['layers'][0]['image'].width(), 400)
            self.assertEqual(studio.scene['layers'][0]['image'].pixelColor(0, 0).name(), '#ff0000')
            self.assertEqual(studio.download_button.text(), 'Download image…')
            return QDialog.DialogCode.Rejected
        with patch.object(plugin, 'pick_image') as picker, patch.object(module, 'run_dialog', side_effect=inspect):
            plugin.open_studio(editor, 'HeaderImage')
            picker.assert_not_called()
        self.assertEqual(editor.media['HeaderImage'].text(), str(self.source))

    def test_download_source_preserves_overlays_and_is_undoable(self):
        studio = self.studio()
        overlay = image_layer(QImage(str(self.source)), 'Logo')
        studio.scene['layers'].append(overlay)
        studio.border_shape.setCurrentText('Circle')
        before = studio.snapshot()
        studio.pick_source = lambda parent: None
        studio.download_source()
        self.assertEqual(studio.scene, before)
        new_source = self.root / 'replacement.png'
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor('lime'))
        image.save(str(new_source))
        studio.pick_source = lambda parent: str(new_source)
        studio.download_button.click()
        self.assertEqual(studio.scene['layers'][0]['image'].pixelColor(0, 0).name(), '#00ff00')
        self.assertEqual(studio.scene['layers'][1], overlay)
        self.assertEqual(studio.scene['border_shape'], 'Circle')
        self.assertEqual(studio.scene['size'], before['size'])
        studio.undo()
        self.assertEqual(studio.scene, before)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_number_sliders_replace_fields_and_radius_controls_crop_without_border(self):
        from playlite_plugins.iconstudio.number_slider import NumberSlider
        from PyQt6.QtWidgets import QSpinBox
        studio = self.studio()
        self.assertTrue(studio.shape.isHidden())
        self.assertTrue(studio.findChildren(QSpinBox))
        self.assertIsInstance(studio.width_control, NumberSlider)
        studio.border_shape.setCurrentText('None')
        self.assertTrue(studio.border_radius.isEnabled())
        studio.border_radius.setValue(128)
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 0)
        studio.border_radius.setValue(0)
        self.assertEqual(render_scene(studio.scene).pixelColor(8, 8).alpha(), 255)
        self.assertEqual(studio.border_radius.number.text(), '0')
        studio.begin_slider_drag()
        count = len(studio.undo_states)
        for value in (20, 40, 60):
            studio.border_radius.setValue(value)
        studio.end_slider_drag()
        self.assertEqual(len(studio.undo_states), count)
        studio.undo()
        self.assertEqual(studio.border_radius.value(), 0)

    def test_editable_numbers_sync_and_wheel_does_not_scroll_page(self):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QWheelEvent
        from PyQt6.QtWidgets import QScrollArea
        studio = self.studio()
        studio.show()
        APP.processEvents()
        control = studio.image_size
        control.number.setFocus()
        control.number.selectAll()
        QTest.keyClicks(control.number, '65')
        QTest.keyClick(control.number, Qt.Key.Key_Return)
        self.assertEqual(control.value(), 65)
        self.assertEqual(studio.scene['image_size'], 65)
        studio.undo()
        self.assertEqual(control.number.value(), 100)
        control.setValue(50)
        self.assertEqual(control.number.value(), 50)
        scroll = studio.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(10)
        for widget in (control.slider, control.number):
            for value in (50, 100):
                control.setValue(value)
                before = scroll.verticalScrollBar().value()
                event = QWheelEvent(QPointF(widget.rect().center()),
                                    QPointF(widget.mapToGlobal(widget.rect().center())),
                                    QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                APP.sendEvent(widget, event)
                self.assertTrue(event.isAccepted())
                self.assertEqual(scroll.verticalScrollBar().value(), before)
                self.assertEqual(control.number.value(), control.value())
                if value == 50:
                    self.assertGreater(control.value(), 50)

    def test_source_and_overlay_controls_are_separate_and_border_toggle_preserves_design(self):
        studio = self.studio()
        self.assertFalse(studio.enable_border.isChecked())
        self.assertTrue(studio.border_settings.isHidden())
        self.assertEqual(studio.layers.count(), 0)
        self.assertTrue(studio.overlay_settings.isHidden())
        overlay = image_layer(QImage(str(self.source)), 'Logo')
        studio.scene['layers'].append(overlay)
        studio.rebuild_layers(1)
        self.assertEqual(studio.layers.count(), 1)
        studio.transform['zoom'].setValue(140)
        self.assertEqual(studio.scene['layers'][1]['zoom'], 140)
        self.assertEqual(studio.scene['layers'][0]['zoom'], 100)
        studio.source_transform['zoom'].setValue(175)
        self.assertEqual(studio.scene['layers'][0]['zoom'], 175)
        self.assertEqual(studio.scene['layers'][1]['zoom'], 140)
        self.assertEqual(studio.layer_index(), 0)
        self.assertIn('Image', studio.drag_target.text())
        studio.enable_border.setChecked(True)
        self.assertTrue(studio.scene['border_enabled'])
        self.assertEqual(studio.scene['border_shape'], 'Follow crop')
        studio.border_style.setCurrentText('Gold')
        studio.border.setValue(12)
        studio.enable_border.setChecked(False)
        self.assertEqual(studio.scene['border'], 12)
        self.assertEqual(studio.scene['border_style'], 'Gold')
        studio.enable_border.setChecked(True)
        self.assertEqual(studio.scene['border'], 12)
        self.assertEqual(studio.scene['border_style'], 'Gold')
        studio.undo()
        self.assertFalse(studio.enable_border.isChecked())
