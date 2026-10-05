from PyQt6.QtWidgets import QPushButton, QDialog, QHBoxLayout
from playlite.providers import GenericPlugin
from playlite.lifecycle import choose_file, run_dialog, show_warning
from .studio import ImageStudio


class Plugin(GenericPlugin):
    def augment_editor(self, editor):
        for key, card in editor.media_cards.items():
            button = QPushButton('✎')
            button.setObjectName('imageStudio' + key)
            button.setToolTip('Edit in Image Studio')
            button.setFixedSize(40, 34)
            from playlite.theme import set_style
            set_style(button, 'padding: 0; font-size: 20px;')
            button.clicked.connect(lambda checked=False, key=key: self.open_studio(editor, key))
            card.actions.insertWidget(card.actions.count() - 1, button)

    def pick_image(self, editor, key, parent=None, caches=None, logos=False):
        from playlite.image_dialog import ImageDownloader
        from PyQt6.QtGui import QImageReader
        picker = ImageDownloader(editor.image_download_context(), parent or editor,
                                 settings_path=editor.data / 'ui.ini', logo_target=key)
        picker.tabs.setCurrentIndex(picker.image_keys.index('Logo' if logos else key))
        picker.apply_button.setText('Use selected image')
        source = editor.media[key].text()
        row = QHBoxLayout()
        if source and QImageReader(source).canRead():
            current = QPushButton('Use current image')
            def use_current():
                picker.applied = {key: source}
                picker.accept()
            current.clicked.connect(use_current)
            row.addWidget(current)
        local = QPushButton('Open image…')
        def open_local():
            path, _ = choose_file(picker, 'Choose image to edit', source or str(editor.data),
                                 'Images (*.png *.jpg *.jpeg *.webp *.bmp *.ico)')
            if path:
                if not QImageReader(path).canRead():
                    show_warning(picker, 'Cannot open image', 'This file could not be opened as an image.')
                    return
                picker.applied = {key: path}
                picker.accept()
        local.clicked.connect(open_local)
        row.addWidget(local)
        row.addStretch()
        picker.layout().insertLayout(picker.layout().count() - 1, row)
        if run_dialog(picker) != QDialog.DialogCode.Accepted:
            return None
        path = picker.applied.get(key) or next(iter(picker.applied.values()), None)
        if path:
            (caches if caches is not None else editor.download_caches).append(picker.cache)
        else:
            picker.cache.cleanup()
        return path

    def open_studio(self, editor, key='Icon'):
        caches = []
        source = self.pick_image(editor, key, caches=caches)
        if not source:
            return
        try:
            studio = ImageStudio(source, key, editor,
                pick_overlay=lambda parent: self.pick_image(editor, key, parent, caches, logos=True))
        except ValueError as error:
            for cache in caches:
                cache.cleanup()
            show_warning(editor, 'Cannot edit image', str(error))
            return
        try:
            if run_dialog(studio) == QDialog.DialogCode.Accepted:
                editor.media[key].setText(studio.output)
                editor.download_caches.append(studio.cache)
            else:
                studio.cache.cleanup()
        finally:
            # Source files remain alive if a downloader is still finishing a request.
            # The editor owns cleanup, as it does for ordinary image downloads.
            editor.download_caches.extend(caches)
