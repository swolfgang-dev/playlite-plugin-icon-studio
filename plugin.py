from PyQt6.QtWidgets import QPushButton, QDialog
from playlite.providers import GenericPlugin
from playlite.lifecycle import choose_file, run_dialog
from .studio import IconStudio


class Plugin(GenericPlugin):
    def augment_editor(self, editor):
        button = QPushButton('Icon Studio…')
        button.clicked.connect(lambda: self.open_studio(editor))
        editor.artwork_layout.addWidget(button)

    def open_studio(self, editor):
        source = editor.media['Icon'].text() or editor.media['CoverImage'].text()
        if not source:
            source, _ = choose_file(editor, 'Choose icon artwork', str(editor.data),
                                    'Images (*.png *.jpg *.jpeg *.webp *.ico)')
        if not source:
            return
        dialog = IconStudio(source, editor)
        if run_dialog(dialog) == QDialog.DialogCode.Accepted:
            editor.media['Icon'].setText(dialog.output)
            editor.download_caches.append(dialog.cache)
        else:
            dialog.cache.cleanup()
