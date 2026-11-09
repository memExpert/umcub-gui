"""Settings dialog: board name files (a later file wins), the plugin folder with what failed to load, and the
keepalive interval of connected devices."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QSpinBox, QVBoxLayout)

from ..app.extensions import load_extensions


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(self.tr("Settings"))
        self.names = QListWidget()
        self.names.addItems(settings.board_name_files())
        add = QPushButton(self.tr("Add..."), clicked=self._add_names)
        remove = QPushButton(self.tr("Remove"), clicked=lambda: self.names.takeItem(self.names.currentRow()))
        self.plugins = QLineEdit(settings.plugins_folder())
        browse = QPushButton("...", clicked=self._pick_folder)
        self.keepalive = QSpinBox(minimum=5, maximum=19, suffix=" s", value=settings.keepalive_s())
        self.keepalive.setToolTip(self.tr("Under 20 s: after 20 s without traffic the next request logs in again"))
        self.errors = QLabel(wordWrap=True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)

        name_buttons = QVBoxLayout()
        name_buttons.addWidget(add)
        name_buttons.addWidget(remove)
        name_buttons.addStretch()
        names = QHBoxLayout()
        names.addWidget(self.names)
        names.addLayout(name_buttons)
        folder = QHBoxLayout()
        folder.addWidget(self.plugins)
        folder.addWidget(browse)
        form = QFormLayout(self)
        form.addRow(self.tr("Board names (JSON, a later file wins)"), names)
        form.addRow(self.tr("Plugin folder"), folder)
        form.addRow(self.tr("Keep connected devices alive every"), self.keepalive)
        form.addRow(self.errors)
        form.addRow(buttons)

    def _add_names(self):
        files, _ = QFileDialog.getOpenFileNames(self, filter="*.json")
        self.names.addItems(files)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self)
        if d:
            self.plugins.setText(d)

    def apply(self):
        """Save and load; stays open showing what failed."""
        self.settings.set_board_name_files([self.names.item(i).text() for i in range(self.names.count())])
        self.settings.set_plugins_folder(self.plugins.text().strip())
        self.settings.set_keepalive_s(self.keepalive.value())
        errors = load_extensions(self.settings)
        if errors:
            self.errors.setText("\n".join(errors))
        else:
            self.accept()

