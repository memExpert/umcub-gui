"""Main window: the device table (one row per device, each with its image) under the shared adapter, key files and
upload options, and the history tab. Device work runs as app jobs."""
import os
import time
from dataclasses import replace

import umcub
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..app.batch import BatchJob, Row
from ..app.jobs import AdaptersJob, ConnectJob, DiscoverJob, FlashOptions, Target
from ..app.settings import Session
from .settings_dialog import SettingsDialog

# ok True / False / None (a warning): green, red, orange
COLORS = {True: "#1a7f37", False: "#cf222e", None: "#bc4c00"}
IMAGE_ROLE = Qt.ItemDataRole.UserRole


class MainWindow(QMainWindow):
    job_finished = Signal(object)       # every job's result once the window has shown it (tests wait on it)
    COL_CHECK, COL_ADAPTER, COL_NODE, COL_UID, COL_BOARD, COL_PROTOCOL, COL_IMAGE, COL_PROGRESS, COL_STATUS = range(9)

    def __init__(self, settings, history):
        super().__init__()
        self.settings, self.history = settings, history
        self.job = None
        self.failed = []                # table rows the last flash run did not finish
        self.identity = None            # of the device the last connect reached
        self.setWindowTitle(self.tr("umcub {0}").format(__version__))
        tabs = QTabWidget()
        tabs.addTab(self._flash_tab(), self.tr("Flash"))
        tabs.addTab(self._history_tab(), self.tr("History"))
        self.setCentralWidget(tabs)
        settings_action = QAction(self.tr("Settings..."), self)
        settings_action.triggered.connect(self.open_settings)
        self.menuBar().addAction(settings_action)
        self.resize(1000, 700)
        self._restore(settings.session())
        self.reload_history()

    # --- widgets -----------------------------------------------------------------------------------------------

    def _flash_tab(self):
        self.adapter = QComboBox(editable=True)
        self.adapter.setMinimumWidth(380)
        self.refresh_button = QPushButton(self.tr("Refresh"), clicked=self.refresh)
        self.discover_button = QPushButton(self.tr("Discover"), clicked=self.discover)
        self.admin_key = QLineEdit(placeholderText=self.tr("SECURE: admin key (PEM, private)"))
        self.device_key = QLineEdit(placeholderText=self.tr("SECURE: device key (PEM, public)"))
        self.slot = QComboBox()
        self.slot.addItem(self.tr("Primary slot"), "primary")
        self.slot.addItem(self.tr("Secondary slot"), "secondary")
        self.mark = QComboBox()
        self.mark.addItem(self.tr("No mark"), "")
        self.mark.addItem(self.tr("Test boot"), "test")
        self.mark.addItem(self.tr("Permanent"), "permanent")
        self.slot.currentIndexChanged.connect(lambda: self.mark.setEnabled(self.slot.currentData() == "secondary"))
        self.reset = QCheckBox(self.tr("Reset after upload"))

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["", self.tr("Adapter"), self.tr("Node"), self.tr("UID"),
                                              self.tr("Board"), self.tr("Protocol"), self.tr("Image"),
                                              self.tr("Progress"), self.tr("Status")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.edit_triggers = self.table.editTriggers()
        header = self.table.horizontalHeader()
        for col in (self.COL_CHECK, self.COL_NODE, self.COL_UID, self.COL_BOARD):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)      # Status fills the rest; the other columns are resized by hand
        self.table.setColumnWidth(self.COL_IMAGE, 220)
        self.table.currentCellChanged.connect(lambda *_: self._show_image())
        self.table.itemChanged.connect(self._item_changed)
        self.add_button = QPushButton(self.tr("Add"), clicked=self.add_row)
        self.remove_button = QPushButton(self.tr("Remove"), clicked=self.remove_rows)
        self.connect_button = QPushButton(self.tr("Connect"), clicked=self.check_device)
        self.device_info = QLabel()
        self.image_info = QLabel()

        self.flash_button = QPushButton(self.tr("Flash checked"), clicked=self.flash)
        self.retry_button = QPushButton(self.tr("Retry failed"), enabled=False, clicked=self.retry)
        self.cancel_button = QPushButton(self.tr("Cancel"), enabled=False, clicked=lambda: self.job.cancel())
        self.result = QLabel()
        self.log = QPlainTextEdit(readOnly=True)

        form = QFormLayout()
        form.addRow(self.tr("Adapter"), _row(self.adapter, self.refresh_button, self.discover_button))
        form.addRow(self.tr("Admin key"), _row(self.admin_key, self._browse(self.admin_key, "*.pem")))
        form.addRow(self.tr("Device key"), _row(self.device_key, self._browse(self.device_key, "*.pem")))
        form.addRow(self.tr("Upload"), _row(self.slot, self.mark, self.reset))
        box = QVBoxLayout()
        box.addLayout(form)
        box.addWidget(_row(self.add_button, self.remove_button, self.connect_button))
        box.addWidget(self.table, 3)
        box.addWidget(self.device_info)
        box.addWidget(self.image_info)
        box.addWidget(_row(self.flash_button, self.retry_button, self.cancel_button))
        box.addWidget(self.result)
        box.addWidget(self.log, 1)
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

    # --- the device table --------------------------------------------------------------------------------------

    def _append(self, r, board=""):
        i = self.table.rowCount()
        self.table.insertRow(i)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        check.setCheckState(Qt.CheckState.Checked if r.checked else Qt.CheckState.Unchecked)
        self.table.setItem(i, self.COL_CHECK, check)
        for col, text in ((self.COL_ADAPTER, r.spec), (self.COL_NODE, "" if r.node is None else str(r.node)),
                          (self.COL_UID, r.uid)):
            self.table.setItem(i, col, QTableWidgetItem(text))
        for col, text in ((self.COL_BOARD, board), (self.COL_IMAGE, ""), (self.COL_STATUS, "")):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == self.COL_IMAGE:       # the path is data: no text drawn under the cell's widget (_image_cell)
                item.setData(IMAGE_ROLE, r.image)
            self.table.setItem(i, col, item)
        protocol = QComboBox()
        protocol.addItem("SMP", "smp")
        protocol.addItem(self.tr("lite"), "lite")
        protocol.setCurrentIndex(max(0, protocol.findData(r.protocol)))
        self.table.setCellWidget(i, self.COL_PROTOCOL, protocol)
        self.table.setCellWidget(i, self.COL_PROGRESS, QProgressBar())
        self._image_cell(i)

    def _image_cell(self, i):
        """No image: a Choose... button over the cell; an image: its file name and a small ... button at the right."""
        path = self._image(i)
        cell = QWidget()
        box = QHBoxLayout(cell)
        box.setContentsMargins(2, 0, 2, 0)
        if path:
            name = QLabel(os.path.basename(path))
            name.setToolTip(path)
            box.addWidget(name, 1)
            button = QPushButton("...")
            button.setFixedWidth(28)
        else:
            button = QPushButton(self.tr("Choose..."))
        button.clicked.connect(lambda: self._pick_image(cell))
        box.addWidget(button)
        self.table.setCellWidget(i, self.COL_IMAGE, cell)

    def image_widget(self, i):
        return self.table.cellWidget(i, self.COL_IMAGE)

    def _pick_image(self, cell):
        path, _ = QFileDialog.getOpenFileName(self, filter="*.bin")
        if path:                # the cell's row now: rows above it may have gone
            self.set_image(next(i for i in range(self.table.rowCount()) if self.image_widget(i) is cell), path)

    def _item_changed(self, item):
        if item.column() == self.COL_IMAGE:
            self._image_cell(item.row())
            self._show_image()

    def rows(self):
        out = []
        for i in range(self.table.rowCount()):
            node = self.table.item(i, self.COL_NODE).text().strip()
            out.append(Row(self.table.item(i, self.COL_ADAPTER).text().strip(), int(node) if node.isdigit() else None,
                           self.table.item(i, self.COL_UID).text().strip(),
                           self.table.cellWidget(i, self.COL_PROTOCOL).currentData(),
                           self._image(i),
                           self.table.item(i, self.COL_CHECK).checkState() == Qt.CheckState.Checked))
        return out

    def set_rows(self, rows):
        self._forget_failed()
        self.table.setRowCount(0)
        for r in rows:
            self._append(r)

    def set_image(self, i, path):
        self.table.item(i, self.COL_IMAGE).setData(IMAGE_ROLE, path)

    def _image(self, i):
        return self.table.item(i, self.COL_IMAGE).data(IMAGE_ROLE) or ""

    def status(self, i):
        return self.table.item(i, self.COL_STATUS).text()

    def _set_status(self, i, ok, text):
        item = self.table.item(i, self.COL_STATUS)
        item.setText(text)
        item.setToolTip(text)                   # the whole text when the cell cuts it
        item.setForeground(QColor(COLORS[ok]))

    def _selected(self):
        return sorted({ix.row() for ix in self.table.selectedIndexes()})

    def add_row(self):
        self._append(Row(self.adapter_spec(), None, "", "smp", ""))

    def remove_rows(self):
        self._forget_failed()
        for i in reversed(self._selected()):
            self.table.removeRow(i)

    def _forget_failed(self):
        """The failed rows are indexes: they mean nothing once rows go."""
        self.failed = []
        self.retry_button.setEnabled(False)

    # --- session -----------------------------------------------------------------------------------------------

    def _restore(self, s):
        self.adapter.setEditText(s.adapter)
        self.admin_key.setText(s.admin_key)
        self.device_key.setText(s.device_key)
        self.slot.setCurrentIndex(max(0, self.slot.findData(s.slot)))
        self.mark.setCurrentIndex(max(0, self.mark.findData(s.mark)))
        self.mark.setEnabled(s.slot == "secondary")
        self.reset.setChecked(s.reset)
        self.set_rows([replace(r, checked=False) for r in s.rows])      # nothing is flashed by accident

    def session(self):
        return Session(adapter=self.adapter_spec(), admin_key=self.admin_key.text(), device_key=self.device_key.text(),
                       slot=self.slot.currentData(), mark=self.mark.currentData() if self.mark.isEnabled() else "",
                       reset=self.reset.isChecked(), rows=self.rows())

    def adapter_spec(self):
        i = self.adapter.findText(self.adapter.currentText())
        return self.adapter.itemData(i) if i >= 0 and self.adapter.itemData(i) else self.adapter.currentText().strip()

    # --- actions -----------------------------------------------------------------------------------------------

    def _set_busy(self, busy, cancellable=False):
        """While a job runs the table keeps its rows: a run refers to them by index."""
        for b in (self.flash_button, self.discover_button, self.connect_button, self.refresh_button,
                  self.add_button, self.remove_button):
            b.setEnabled(not busy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers if busy else self.edit_triggers)
        for i in range(self.table.rowCount()):
            for col in (self.COL_PROTOCOL, self.COL_IMAGE):
                self.table.cellWidget(i, col).setEnabled(not busy)
        self.retry_button.setEnabled(not busy and bool(self.failed))
        self.cancel_button.setEnabled(busy and cancellable)

    def _run(self, job, on_done):
        self.job = job
        self._set_busy(True)
        job.signals.finished.connect(lambda res: self._finished(res, on_done))
        job.start()

    def _finished(self, res, on_done):
        self.job = None
        self._set_busy(False)
        if res.ok:
            on_done(res.value)
        else:
            self.show_result(False, self.tr("Error: {0}").format(res.error_text))
        self.job_finished.emit(res)

    def show_result(self, ok, text):
        self.result.setStyleSheet(f"color: {COLORS[ok]}; font-weight: bold")
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
        spec = self.adapter_spec()

        def done(devices):
            rows = self.rows()
            # a known row: the same node on this adapter, or the same UID for a device without an address
            known = {(r.spec, r.node if r.node is not None else r.uid): i for i, r in enumerate(rows)}
            found = set()
            for d in devices:            # link identities (serial / UDP) or {"addr", "protocol"} (CAN)
                node, uid = (d["addr"] or None if "uid" in d else d["addr"]), d.get("uid", "")
                i = known.get((spec, node if node is not None else uid))
                if i is None:
                    i = self.table.rowCount()
                    self._append(Row(spec, node, uid, d.get("protocol", "smp"), ""))
                elif uid:
                    self.table.item(i, self.COL_UID).setText(uid)
                if "board_type" in d:
                    self.table.item(i, self.COL_BOARD).setText(umcub.board_label(d["board_type"]))
                self._set_status(i, True, self.tr("found") + (f": {_version(d)}" if "version" in d else ""))
                found.add(i)
            for i, r in enumerate(rows):
                if r.spec == spec and i not in found:
                    self._set_status(i, None, self.tr("not found"))
            if devices:
                self.show_result(True, self.tr("{0} device(s)").format(len(devices)))
            else:
                self.show_result(None, self.tr("No device answered on {0}").format(spec))
        self._run(DiscoverJob(spec), done)

    def check_device(self):
        i = self.table.currentRow()
        if i < 0:
            return
        r = self.rows()[i]

        def done(identity):
            self.identity = identity
            if identity:
                self.table.item(i, self.COL_BOARD).setText(umcub.board_label(identity["board_type"]))
            self._set_status(i, True, self.tr("connected") + (f": {_version(identity)}" if identity else ""))
            self.device_info.setText(_describe(identity) if identity else self.tr("connected (no link identity)"))
            self._show_image()
            self.show_result(True, self.tr("Connected"))
        self._run(ConnectJob(Target(r.spec, r.node, r.uid, self.admin_key.text(), self.device_key.text())), done)

    def flash(self):
        checked = [i for i, r in enumerate(self.rows()) if r.checked]
        if checked:
            self._flash(checked)
        else:
            self.show_result(False, self.tr("No device checked: tick the rows to flash"))

    def retry(self):
        self._flash(self.failed)

    def _flash(self, indexes):
        s = self.session()
        self.settings.save_session(s)
        run = []
        for i in indexes:
            self.table.cellWidget(i, self.COL_PROGRESS).setValue(0)
            if s.rows[i].image:
                run.append(i)
                self._set_status(i, True, "")
            else:
                self._set_status(i, False, self.tr("no image"))
        self.failed = [i for i in indexes if i not in run]
        job = BatchJob([s.rows[i] for i in run], s.admin_key, s.device_key,
                       FlashOptions(slot=s.slot, mark=s.mark, reset=s.reset), self.history)
        job.signals.row_progress.connect(lambda k, done, total: _progress(
            self.table.cellWidget(run[k], self.COL_PROGRESS), done, total))
        job.signals.row_finished.connect(lambda k, res: self._row_done(run[k], res))
        job.signals.finished.connect(self._batch_done)
        self.job = job
        self._set_busy(True, cancellable=True)
        job.start()

    def _row_done(self, i, res):
        how = {"verify": self.tr("checked: valid"), "hash": self.tr("checked: SHA-256 matches"),
               None: self.tr("not checked")}
        if res.ok:
            text = self.tr("OK, {0}").format(how[res.value])
        else:
            text = self.tr("cancelled") if res.cancelled else res.error_text
            self.failed.append(i)
        self._set_status(i, res.ok, text)
        r = self.rows()[i]
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')} {r.spec} "
                                 + (f"node {r.node}" if r.node is not None else f"uid {r.uid}") + f": {text}")

    def _batch_done(self, results):
        self.job = None
        self.failed.sort()
        ok = sum(r.ok for r in results)
        cancelled = sum(r.cancelled for r in results)
        failed = len(self.failed) - cancelled
        text = self.tr("{0} ok, {1} failed").format(ok, failed) + \
            (self.tr(", {0} cancelled").format(cancelled) if cancelled else "")
        self.show_result(not self.failed, text)
        self._set_busy(False)
        self.reload_history()
        self.job_finished.emit(results)

    def _show_image(self):
        i = self.table.currentRow()
        path = self._image(i) if i >= 0 else ""
        try:
            img = umcub.Image.load(path)
        except umcub.UmcubError as e:
            self.image_info.setText(str(e) if path else "")
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


def _progress(bar, done, total):
    bar.setMaximum(total)
    bar.setValue(done)


def _version(i):
    """"umcub 1.0.0, addressed" of a link identity."""
    return f"umcub {i['version']}, {umcub.LINK_NAMES.get(i['link'], '?')}"


def _describe(i):
    return (f"node {i['addr']}   uid {i['uid']}   {umcub.board_label(i['board_type'])}   {_version(i)}"
            + ("   SECURE" if i.get("enc") else ""))


def _row(*widgets):
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        h.addWidget(w, 1 if isinstance(w, (QLineEdit, QComboBox)) else 0)     # fields take the width
    w = QWidget()
    w.setLayout(h)
    return w
