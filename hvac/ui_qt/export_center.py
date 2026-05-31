# -*- coding: utf-8 -*-
"""Export Center — единый диалог экспорта во все форматы."""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject


@dataclass
class ExportFormat:
    key: str
    title_key: str
    desc_key: str
    default_ext: str
    default_name_key: str
    runner: Callable[[HVACProject, str], None]

    @property
    def title(self) -> str:
        return _t(self.title_key)

    @property
    def desc(self) -> str:
        return _t(self.desc_key)

    @property
    def default_name(self) -> str:
        return _t(self.default_name_key)


def _excel(project: HVACProject, path: str) -> None:
    from hvac.io_excel import export_to_excel
    export_to_excel(project, path)


def _pdf(project: HVACProject, path: str) -> None:
    from hvac.io_pdf import export_to_pdf
    export_to_pdf(project, path)


def _revit_csv(project: HVACProject, path: str) -> None:
    from hvac.io_revit import export_results_for_revit
    export_results_for_revit(project, path)


def _equipment_xlsx(project: HVACProject, path: str) -> None:
    from hvac.io_excel_equipment import export_equipment_summary
    export_equipment_summary(project, path)


def _specification(project: HVACProject, path: str) -> None:
    from hvac.specification import build_specification, export_specification_xlsx
    spec = build_specification(project)
    project.equipment_specification = spec
    export_specification_xlsx(spec, path)


FORMATS = [
    ExportFormat(
        "excel", "export.fmt.excel.title", "export.fmt.excel.desc",
        ".xlsx", "export.fmt.excel.name", _excel,
    ),
    ExportFormat(
        "pdf", "export.fmt.pdf.title", "export.fmt.pdf.desc",
        ".pdf", "export.fmt.pdf.name", _pdf,
    ),
    ExportFormat(
        "equipment", "export.fmt.equipment.title", "export.fmt.equipment.desc",
        ".xlsx", "export.fmt.equipment.name", _equipment_xlsx,
    ),
    ExportFormat(
        "revit", "export.fmt.revit.title", "export.fmt.revit.desc",
        ".csv", "export.fmt.revit.name", _revit_csv,
    ),
    ExportFormat(
        "spec_gost", "export.fmt.spec.title", "export.fmt.spec.desc",
        ".xlsx", "export.fmt.spec.name", _specification,
    ),
]


# ---------- worker ----------


class ExportWorker(QObject):
    finished = Signal()
    failed = Signal(str, str)

    def __init__(self, fmt: ExportFormat, project: HVACProject, path: str):
        super().__init__()
        self.fmt = fmt
        self.project = project
        self.path = path

    def run(self) -> None:
        try:
            self.fmt.runner(self.project, self.path)
            self.finished.emit()
        except Exception as e:
            self.failed.emit(str(e), traceback.format_exc())


# ---------- диалог ----------


class ExportCenter(QDialog):
    """Окно «Экспорт». Один диалог вместо 4 пунктов меню."""

    def __init__(self, project: HVACProject, parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

        self.setWindowTitle(_t("export.title"))
        self.setMinimumWidth(640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        h = QLabel(_t("export.h1"))
        h.setProperty("role", "h1")
        outer.addWidget(h)
        sub = QLabel(_t("export.sub"))
        sub.setProperty("role", "muted")
        outer.addWidget(sub)
        outer.addSpacing(4)

        # Радио-список форматов
        self._radio_group = QButtonGroup(self)
        self._format_widgets: dict[str, QRadioButton] = {}
        for i, fmt in enumerate(FORMATS):
            row = self._make_format_row(fmt, default=i == 0)
            outer.addWidget(row)

        outer.addSpacing(4)

        # Путь
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(_t("export.path_ph"))
        path_row.addWidget(self.path_edit, stretch=1)
        browse = QPushButton(_t("export.browse"))
        browse.setCursor(QCursor(Qt.PointingHandCursor))
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        outer.addLayout(path_row)

        self.open_folder_cb = QCheckBox(_t("export.open_folder"))
        self.open_folder_cb.setChecked(True)
        outer.addWidget(self.open_folder_cb)

        # Прогресс
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton(_t("export.btn_close"))
        self.cancel_btn.setProperty("role", "ghost")
        self.cancel_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.export_btn = QPushButton(_t("export.btn_export"))
        self.export_btn.setProperty("role", "primary")
        self.export_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.export_btn.clicked.connect(self._do_export)
        btn_row.addWidget(self.export_btn)
        outer.addLayout(btn_row)

        self._suggest_path()

    def _make_format_row(self, fmt: ExportFormat, default: bool) -> QFrame:
        frame = QFrame()
        frame.setProperty("role", "card")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)

        rb = QRadioButton()
        rb.setChecked(default)
        rb.toggled.connect(lambda checked, k=fmt.key: checked and self._on_format_changed(k))
        self._radio_group.addButton(rb)
        self._format_widgets[fmt.key] = rb
        rb.setProperty("fmt_key", fmt.key)
        lay.addWidget(rb, alignment=Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(fmt.title)
        title.setStyleSheet("font-weight: 600;")
        desc = QLabel(fmt.desc)
        desc.setProperty("role", "muted")
        desc.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(desc)
        lay.addLayout(col, stretch=1)
        return frame

    def _current_format(self) -> ExportFormat:
        for k, rb in self._format_widgets.items():
            if rb.isChecked():
                return next(f for f in FORMATS if f.key == k)
        return FORMATS[0]

    def _on_format_changed(self, key: str) -> None:
        self._suggest_path()

    def _suggest_path(self) -> None:
        fmt = self._current_format()
        name = self.project.params.project_name or _t("export.default_name")
        default = fmt.default_name.replace("{name}", name)
        # Кладём рядом с предыдущим выбором или в Documents
        cur = self.path_edit.text().strip()
        base = Path(cur).parent if cur else Path.home() / "Documents"
        self.path_edit.setText(str(base / default))

    def _browse(self) -> None:
        fmt = self._current_format()
        cur = self.path_edit.text()
        path, _f = QFileDialog.getSaveFileName(
            self, _t("export.dlg_save"), cur,
            f"{fmt.title} (*{fmt.default_ext})",
        )
        if path:
            self.path_edit.setText(path)

    def _do_export(self) -> None:
        if not self.project.spaces:
            QMessageBox.information(
                self, _t("export.no_data.title"),
                _t("export.no_data.msg"))
            return
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(
                self, _t("export.no_path.title"),
                _t("export.no_path.msg"))
            return

        fmt = self._current_format()
        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(True)

        self._thread = QThread(self)
        self._worker = ExportWorker(fmt, self.project, path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(lambda: self._on_finished(path))
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_finished(self, path: str) -> None:
        self._cleanup()
        if self.open_folder_cb.isChecked():
            self._reveal(path)
        self.accept()

    def _on_failed(self, msg: str, tb: str) -> None:
        self._cleanup()
        m = QMessageBox(self)
        m.setIcon(QMessageBox.Critical)
        m.setWindowTitle(_t("export.err.title"))
        m.setText(msg)
        m.setDetailedText(tb)
        m.exec()

    def _cleanup(self) -> None:
        self.progress.setVisible(False)
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        if self._thread is not None:
            self._thread.wait(2000)
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    @staticmethod
    def _reveal(path: str) -> None:
        try:
            if sys.platform == "win32":
                # Открыть проводник и выделить файл
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
        except Exception:
            pass
