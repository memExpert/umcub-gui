"""Main window: one form (connection, image, upload) and the history tab. Device work runs as app jobs."""
import time

import umcub
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIntValidator
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..app.jobs import AdaptersJob, ConnectJob, DiscoverJob, FlashJob, FlashOptions, Target
from ..app.settings import Session
from .settings_dialog import SettingsDialog

OK_STYLE, ERROR_STYLE = "color: #1a7f37; font-weight: bold", "color: #cf222e; font-weight: bold"


class MainWindow(QMainWindow):
    job_finished = Signal(object)       # every job's Result once the window has shown it (tests wait on it)

    def __init__(self, settings, history):
        super().__init__()
        self.settings, self.history = settings, history
        self.job = None
        self.identity = None            # of the device the last connect / flash reached
        self.setWindowTitle(self.tr("umcub {0}").format(__version__))
        tabs = QTabWidget()
        tabs.addTab(self._flash_tab(), self.tr("Flash"))
        tabs.addTab(self._history_tab(), self.tr("History"))
        self.setCentralWidget(tabs)
        settings_action = QAction(self.tr("Settings..."), self)
        settings_action.triggered.connect(self.open_settings)
        self.menuBar().addAction(settings_action)
        self.resize(820, 640)
        self._restore(settings.session())
        self.reload_history()

    # --- widgets -----------------------------------------------------------------------------------------------

    def _flash_tab(self):
        self.adapter = QComboBox(editable=True)
        self.adapter.setMinimumWidth(380)
        self.refresh_button = QPushButton(self.tr("Refresh"), clicked=self.refresh)
        self.discover_button = QPushButton(self.tr("Discover"), clicked=self.discover)
        self.devices = QComboBox()
        self.devices.currentIndexChanged.connect(self._device_chosen)
        self.node = QLineEdit(placeholderText=self.tr("link node / CAN node"))
        self.node.setValidator(QIntValidator(0, 65535))
        self.uid = QLineEdit(placeholderText=self.tr("UID of an unassigned link device (hex)"))
        self.admin_key = QLineEdit(placeholderText=self.tr("SECURE: admin key (PEM, private)"))
        self.device_key = QLineEdit(placeholderText=self.tr("SECURE: device key (PEM, public)"))
        self.protocol_smp = QRadioButton("SMP")
        self.protocol_lite = QRadioButton(self.tr("lite (bootloaders without SMP)"))
        group = QButtonGroup(self)
        group.addButton(self.protocol_smp)
        group.addButton(self.protocol_lite)
        self.connect_button = QPushButton(self.tr("Connect"), clicked=self.check_device)
        self.device_info = QLabel()
        self.image = QLineEdit()
        self.image.textChanged.connect(self._show_image)
        self.image_info = QLabel()
        self.slot = QComboBox()
        self.slot.addItem(self.tr("Primary slot"), "primary")
        self.slot.addItem(self.tr("Secondary slot"), "secondary")
        self.mark = QComboBox()
        self.mark.addItem(self.tr("No mark"), "")
        self.mark.addItem(self.tr("Test boot"), "test")
        self.mark.addItem(self.tr("Permanent"), "permanent")
        self.slot.currentIndexChanged.connect(lambda: self.mark.setEnabled(self.slot.currentData() == "secondary"))
        self.reset = QCheckBox(self.tr("Reset after upload"))
        self.flash_button = QPushButton(self.tr("Flash"), clicked=self.flash)
        self.cancel_button = QPushButton(self.tr("Cancel"), enabled=False, clicked=lambda: self.job.cancel())
        self.progress = QProgressBar()
        self.result = QLabel()
        self.log = QPlainTextEdit(readOnly=True)

        form = QFormLayout()
        form.addRow(self.tr("Adapter"), _row(self.adapter, self.refresh_button))
        form.addRow(self.tr("Devices"), _row(self.devices, self.discover_button))
        form.addRow(self.tr("Node"), _row(self.node, QLabel(self.tr("UID")), self.uid))
        form.addRow(self.tr("Admin key"), _row(self.admin_key, self._browse(self.admin_key, "*.pem")))
        form.addRow(self.tr("Device key"), _row(self.device_key, self._browse(self.device_key, "*.pem")))
        form.addRow(self.tr("Protocol"), _row(self.protocol_smp, self.protocol_lite, self.connect_button))
        form.addRow(self.tr("Device"), self.device_info)
        form.addRow(self.tr("Image"), _row(self.image, self._browse(self.image, "*.bin")))
        form.addRow("", self.image_info)
        form.addRow(self.tr("Upload"), _row(self.slot, self.mark, self.reset))
        form.addRow("", _row(self.flash_button, self.cancel_button))
        box = QVBoxLayout()
        box.addLayout(form)
        box.addWidget(self.progress)
        box.addWidget(self.result)
        box.addWidget(self.log)
        w = QWidget()
        w.setLayout(box)
        return w

    def _history_tab(self):
        self.history_table = QTableWidget(0, 10)
        self.history_table.setHorizontalHeaderLabels([self.tr(h) for h in (
            "Time", "Result", "Board", "UID", "Node", "Adapter", "Image", "Version", "Checked", "Error")])
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return self.history_table

    def _browse(self, edit, pattern):
        def pick():
            path, _ = QFileDialog.getOpenFileName(self, filter=pattern)
            if path:
                edit.setText(path)
        return QPushButton("...", clicked=pick)

    # --- session -----------------------------------------------------------------------------------------------

    def _restore(self, s):
        self.adapter.setEditText(s.adapter)
        self.node.setText("" if s.node is None else str(s.node))
        self.uid.setText(s.uid)
        self.admin_key.setText(s.admin_key)
        self.device_key.setText(s.device_key)
        (self.protocol_lite if s.protocol == "lite" else self.protocol_smp).setChecked(True)
        self.image.setText(s.image)
        self.slot.setCurrentIndex(max(0, self.slot.findData(s.slot)))
        self.mark.setCurrentIndex(max(0, self.mark.findData(s.mark)))
        self.mark.setEnabled(s.slot == "secondary")
        self.reset.setChecked(s.reset)

    def session(self):
        return Session(adapter=self.adapter_spec(), node=int(self.node.text()) if self.node.text() else None,
                       uid=self.uid.text().strip(), admin_key=self.admin_key.text(), device_key=self.device_key.text(),
                       protocol="lite" if self.protocol_lite.isChecked() else "smp", image=self.image.text(),
                       slot=self.slot.currentData(), mark=self.mark.currentData() if self.mark.isEnabled() else "",
                       reset=self.reset.isChecked())

    def adapter_spec(self):
        i = self.adapter.findText(self.adapter.currentText())
        return self.adapter.itemData(i) if i >= 0 and self.adapter.itemData(i) else self.adapter.currentText().strip()

    def target(self):
        s = self.session()
        return Target(s.adapter, s.node, s.uid, s.admin_key, s.device_key)

    # --- actions -----------------------------------------------------------------------------------------------

    def _set_busy(self, busy, cancellable=False):
        for b in (self.flash_button, self.discover_button, self.connect_button, self.refresh_button):
            b.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and cancellable)

    def _run(self, job, on_done):
        self.job = job
        self._set_busy(True, isinstance(job, FlashJob))
        job.signals.log.connect(self.log.appendPlainText)
        job.signals.finished.connect(lambda res: self._finished(res, on_done))
        job.start()

    def _finished(self, res, on_done):
        self._set_busy(False)
        if res.ok:
            on_done(res.value)
        else:
            self.show_result(False, self.tr("Cancelled") if res.cancelled else self.tr("Error: {0}").format(res.error_text))
        self.job = None
        self.job_finished.emit(res)

    def show_result(self, ok, text):
        self.result.setStyleSheet(OK_STYLE if ok else ERROR_STYLE)
        self.result.setText(text)
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')} {text}")

    def refresh(self):
        def done(adapters):
            text = self.adapter.currentText()
            self.adapter.clear()
            for a in adapters:
                self.adapter.addItem(f"{a.spec or a.name}   {a.name}   {a.description}", a.spec)
                if not a.spec:          # e.g. a network port without link: shown, not selectable
                    self.adapter.model().item(self.adapter.count() - 1).setEnabled(False)
            self.adapter.setEditText(text)
            self.show_result(True, self.tr("{0} adapter(s)").format(len(adapters)))
        self._run(AdaptersJob(), done)

    def discover(self):
        def done(devices):
            self.devices.clear()
            for d in devices:
                self.devices.addItem(f"node {d['addr']}   uid {d['uid']}   {umcub.board_label(d['board_type'])}", d)
            self.show_result(True, self.tr("{0} device(s)").format(len(devices)))
        self._run(DiscoverJob(self.adapter_spec()), done)

    def _device_chosen(self, i):
        d = self.devices.itemData(i)
        if d:
            self.node.setText(str(d["addr"]) if d["addr"] else "")
            self.uid.setText("" if d["addr"] else d["uid"])

    def check_device(self):
        def done(identity):
            self.identity = identity
            self.device_info.setText(_describe(identity) if identity else self.tr("connected (no link identity)"))
            self._show_image()
            self.show_result(True, self.tr("Connected"))
        self.settings.save_session(self.session())
        self._run(ConnectJob(self.target()), done)

    def flash(self):
        s = self.session()
        self.settings.save_session(s)
        self.progress.setValue(0)
        job = FlashJob(self.target(), s.image, FlashOptions(s.protocol, s.slot, s.mark, s.reset), self.history)
        job.signals.progress.connect(self._progress)

        def done(checked):
            self.identity = job.identity
            if job.identity:
                self.device_info.setText(_describe(job.identity))
            how = {"verify": self.tr("checked: valid (MCUboot validation on the device)"),
                   "hash": self.tr("checked: SHA-256 matches"),
                   None: self.tr("not checked (lite upload, or the bootloader cannot check this image)")}[checked]
            self.show_result(True, self.tr("OK: {0} uploaded, {1}").format(job.img.version, how))

        job.signals.finished.connect(lambda res: self.reload_history())
        self._run(job, done)

    def _progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _show_image(self):
        try:
            img = umcub.Image.load(self.image.text())
        except umcub.UmcubError as e:
            self.image_info.setText(str(e) if self.image.text() else "")
            return
        text = f"{img.version}   " + (self.tr("board {0}").format(umcub.board_label(img.board_type))
                                      if img.board_type is not None else self.tr("no board type"))
        if self.identity:
            try:
                img.check_board(self.identity["board_type"])
            except umcub.UmcubError as e:
                text += "   " + str(e)
        self.image_info.setText(text)

    def reload_history(self):
        rows = self.history.records()
        self.history_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.started)), r.result, r.board, r.uid,
                     "" if r.node is None else str(r.node), r.adapter, r.image_name, r.image_version,
                     r.checked or "", r.error_text)
            for j, c in enumerate(cells):
                self.history_table.setItem(i, j, QTableWidgetItem(c))
        self.history_table.resizeColumnsToContents()

    def open_settings(self):
        if SettingsDialog(self.settings, self).exec():
            self._show_image()

    def closeEvent(self, e):
        self.settings.save_session(self.session())
        super().closeEvent(e)


def _describe(i):
    return (f"node {i['addr']}   uid {i['uid']}   {umcub.board_label(i['board_type'])}   umcub {i['version']}"
            + ("   SECURE" if i.get("enc") else ""))


def _row(*widgets):
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        h.addWidget(w, 1 if isinstance(w, (QLineEdit, QComboBox)) else 0)     # fields take the width
    w = QWidget()
    w.setLayout(h)
    return w
