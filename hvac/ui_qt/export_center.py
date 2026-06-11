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
    QButtonGroup, QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget,
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


def _docx(project: HVACProject, path: str) -> None:
    from hvac.io_docx import export_to_docx
    export_to_docx(project, path)


def _revit_csv(project: HVACProject, path: str) -> None:
    from hvac.io_revit import export_results_for_revit
    export_results_for_revit(project, path)


def _revit_live(project: HVACProject, path: str) -> None:
    """Запись результатов прямо в открытую модель Revit через живой мост.

    CSV сохраняется в path как артефакт; затем тот же файл читает C#-код
    внутри Revit и пишет значения в Project Parameters категории Spaces.
    """
    from hvac.revit_link import write_results_to_revit
    write_results_to_revit(project, path)


def _equipment_xlsx(project: HVACProject, path: str) -> None:
    from hvac.io_excel_equipment import export_equipment_summary
    export_equipment_summary(project, path)


def _passports(project: HVACProject, path: str) -> None:
    from hvac.io_passport import export_ventilation_passports
    export_ventilation_passports(project, path)


def _specification(project: HVACProject, path: str) -> None:
    from hvac.specification import build_specification, export_specification_xlsx
    spec = build_specification(project)
    project.equipment_specification = spec
    export_specification_xlsx(spec, path)


def _gas_load(project: HVACProject, path: str, **params) -> None:
    from hvac.gas_load import export_project_gas_load_pdf
    export_project_gas_load_pdf(project, path, **params)


def _hlgc(project: HVACProject, path: str, **params) -> None:
    """Заполняет HLGC Design Table. Требует исходный шаблон (source_path).

    Выполняется в фоновом QThread, поэтому для движка Excel COM нужно
    инициализировать COM в этом потоке (CoInitialize). Если pywin32/Excel
    недоступны — io_hlgc сам откатится на openpyxl (CoInitialize безвреден)."""
    from hvac.io_hlgc import export_to_hlgc
    source_path = (params.get("source_path") or "").strip()
    if not source_path or not os.path.exists(source_path):
        raise ValueError(_t("export.hlgc.no_source.msg"))
    mode = params.get("mode", "append")
    overwrite_only_empty = bool(params.get("overwrite_only_empty", False))

    co_inited = False
    try:
        import pythoncom
        pythoncom.CoInitialize()
        co_inited = True
    except Exception:
        co_inited = False
    try:
        export_to_hlgc(
            project, source_path, output_path=path,
            overwrite_only_empty=overwrite_only_empty,
            preserve_formulas=True, engine="auto", mode=mode,
        )
    finally:
        if co_inited:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


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
        "docx", "export.fmt.docx.title", "export.fmt.docx.desc",
        ".docx", "export.fmt.docx.name", _docx,
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
        "revit_live", "export.fmt.revit_live.title", "export.fmt.revit_live.desc",
        ".csv", "export.fmt.revit_live.name", _revit_live,
    ),
    ExportFormat(
        "spec_gost", "export.fmt.spec.title", "export.fmt.spec.desc",
        ".xlsx", "export.fmt.spec.name", _specification,
    ),
    ExportFormat(
        "passports", "export.fmt.passport.title", "export.fmt.passport.desc",
        ".docx", "export.fmt.passport.name", _passports,
    ),
    ExportFormat(
        "gas_load", "export.fmt.gas.title", "export.fmt.gas.desc",
        ".pdf", "export.fmt.gas.name", _gas_load,
    ),
    ExportFormat(
        "hlgc", "export.fmt.hlgc.title", "export.fmt.hlgc.desc",
        ".xlsx", "export.fmt.hlgc.name", _hlgc,
    ),
]


# ---------- worker ----------


class ExportWorker(QObject):
    finished = Signal()
    failed = Signal(str, str)

    def __init__(self, fmt: ExportFormat, project: HVACProject, path: str,
                 params: dict | None = None):
        super().__init__()
        self.fmt = fmt
        self.project = project
        self.path = path
        self.params = params or {}

    def run(self) -> None:
        try:
            self.fmt.runner(self.project, self.path, **self.params)
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

        # Параметры расчёта газа (видны только для формата «gas_load»)
        self.gas_params = self._make_gas_params()
        outer.addWidget(self.gas_params)

        # Параметры HLGC-экспорта (видны только для формата «hlgc»)
        self.hlgc_params = self._make_hlgc_params()
        outer.addWidget(self.hlgc_params)

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
        rb.toggled.connect(
            lambda checked, k=fmt.key: self._on_format_changed(k) if checked else None)
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

    def _make_gas_params(self) -> QGroupBox:
        """Поля параметров для письма-расчёта газа."""
        from hvac.gas_load import (
            NATURAL_GAS_LHV_KCAL_M3, DEFAULT_LOAD_FACTOR,
            DEFAULT_HOURS_PER_DAY, DEFAULT_DAYS_PER_MONTH,
            DEFAULT_HEATING_DAYS, project_efficiency,
        )
        box = QGroupBox(_t("export.gas.params"))
        form = QFormLayout(box)

        self.gas_object = QLineEdit(self.project.params.project_name or "")
        form.addRow(_t("export.gas.object"), self.gas_object)

        self.gas_sign_pos = QLineEdit(_t("export.gas.signatory_default"))
        form.addRow(_t("export.gas.signatory"), self.gas_sign_pos)

        self.gas_sign_name = QLineEdit("")
        form.addRow(_t("export.gas.signatory_name"), self.gas_sign_name)

        self.gas_lhv = QDoubleSpinBox()
        self.gas_lhv.setRange(1000.0, 12000.0)
        self.gas_lhv.setDecimals(0)
        self.gas_lhv.setSingleStep(50.0)
        self.gas_lhv.setValue(NATURAL_GAS_LHV_KCAL_M3)
        form.addRow(_t("export.gas.lhv"), self.gas_lhv)

        self.gas_eff = QDoubleSpinBox()
        self.gas_eff.setRange(0.50, 1.00)
        self.gas_eff.setDecimals(2)
        self.gas_eff.setSingleStep(0.01)
        self.gas_eff.setValue(project_efficiency(self.project))
        form.addRow(_t("export.gas.eff"), self.gas_eff)

        self.gas_k = QDoubleSpinBox()
        self.gas_k.setRange(0.10, 1.00)
        self.gas_k.setDecimals(2)
        self.gas_k.setSingleStep(0.05)
        self.gas_k.setValue(DEFAULT_LOAD_FACTOR)
        form.addRow(_t("export.gas.k"), self.gas_k)

        self.gas_hours = QDoubleSpinBox()
        self.gas_hours.setRange(1.0, 24.0)
        self.gas_hours.setDecimals(0)
        self.gas_hours.setValue(DEFAULT_HOURS_PER_DAY)
        form.addRow(_t("export.gas.hours"), self.gas_hours)

        self.gas_days_month = QSpinBox()
        self.gas_days_month.setRange(28, 31)
        self.gas_days_month.setValue(int(DEFAULT_DAYS_PER_MONTH))
        form.addRow(_t("export.gas.days_month"), self.gas_days_month)

        self.gas_heating_days = QSpinBox()
        self.gas_heating_days.setRange(1, 365)
        self.gas_heating_days.setValue(int(DEFAULT_HEATING_DAYS))
        form.addRow(_t("export.gas.heating_days"), self.gas_heating_days)

        box.setVisible(False)
        return box

    def _collect_gas_params(self) -> dict:
        """Параметры из полей → kwargs для export_project_gas_load_pdf."""
        from hvac.gas_load import kcal_to_kwh
        params: dict = {
            "signatory": (self.gas_sign_pos.text().strip()
                          or _t("export.gas.signatory_default")),
            "signatory_name": self.gas_sign_name.text().strip(),
            "lhv_kwh_m3": kcal_to_kwh(self.gas_lhv.value()),
            "efficiency": self.gas_eff.value(),
            "load_factor": self.gas_k.value(),
            "hours_per_day": self.gas_hours.value(),
            "days_per_month": float(self.gas_days_month.value()),
            "heating_days": float(self.gas_heating_days.value()),
        }
        obj = self.gas_object.text().strip()
        if obj:
            params["object_name"] = obj
        return params

    def _make_hlgc_params(self) -> QGroupBox:
        """Поля для экспорта в HLGC Design Table: шаблон + режим записи."""
        box = QGroupBox(_t("export.hlgc.params"))
        form = QFormLayout(box)

        # Исходная таблица (шаблон) + кнопка обзора
        src_row = QHBoxLayout()
        self.hlgc_source = QLineEdit()
        self.hlgc_source.setPlaceholderText(_t("export.hlgc.source_ph"))
        src_row.addWidget(self.hlgc_source, stretch=1)
        src_browse = QPushButton(_t("export.browse"))
        src_browse.setCursor(QCursor(Qt.PointingHandCursor))
        src_browse.clicked.connect(self._browse_hlgc_source)
        src_row.addWidget(src_browse)
        src_wrap = QWidget()
        src_wrap.setLayout(src_row)
        form.addRow(_t("export.hlgc.source"), src_wrap)

        # Режим записи (radio)
        self._hlgc_mode_group = QButtonGroup(self)
        mode_col = QVBoxLayout()
        mode_col.setSpacing(2)
        self.hlgc_mode_match = QRadioButton(_t("export.hlgc.mode.match"))
        self.hlgc_mode_append = QRadioButton(_t("export.hlgc.mode.append"))
        self.hlgc_mode_rebuild = QRadioButton(_t("export.hlgc.mode.rebuild"))
        self.hlgc_mode_append.setChecked(True)  # безопасный дефолт
        for rb, key in ((self.hlgc_mode_match, "match"),
                        (self.hlgc_mode_append, "append"),
                        (self.hlgc_mode_rebuild, "rebuild")):
            rb.setProperty("hlgc_mode", key)
            self._hlgc_mode_group.addButton(rb)
            mode_col.addWidget(rb)
        mode_wrap = QWidget()
        mode_wrap.setLayout(mode_col)
        form.addRow(_t("export.hlgc.mode"), mode_wrap)

        self.hlgc_only_empty = QCheckBox(_t("export.hlgc.only_empty"))
        form.addRow("", self.hlgc_only_empty)

        box.setVisible(False)
        return box

    def _hlgc_mode(self) -> str:
        for rb in (self.hlgc_mode_match, self.hlgc_mode_append,
                   self.hlgc_mode_rebuild):
            if rb.isChecked():
                return rb.property("hlgc_mode")
        return "append"

    def _collect_hlgc_params(self) -> dict:
        return {
            "source_path": self.hlgc_source.text().strip(),
            "mode": self._hlgc_mode(),
            "overwrite_only_empty": self.hlgc_only_empty.isChecked(),
        }

    def _browse_hlgc_source(self) -> None:
        cur = self.hlgc_source.text().strip()
        path, _f = QFileDialog.getOpenFileName(
            self, _t("export.hlgc.source_dlg"), cur,
            "Excel (*.xlsx *.xls)",
        )
        if path:
            self.hlgc_source.setText(path)
            # Подсказываем путь сохранения: <шаблон>_filled.xlsx
            base, _ext = os.path.splitext(path)
            out = base + "_filled.xlsx"
            self.path_edit.setText(out)

    def _current_format(self) -> ExportFormat:
        for k, rb in self._format_widgets.items():
            if rb.isChecked():
                return next(f for f in FORMATS if f.key == k)
        return FORMATS[0]

    def _on_format_changed(self, key: str) -> None:
        self._suggest_path()
        if hasattr(self, "gas_params"):
            self.gas_params.setVisible(key == "gas_load")
        if hasattr(self, "hlgc_params"):
            self.hlgc_params.setVisible(key == "hlgc")

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
        fmt = self._current_format()
        # Письмо-расчёт газа берёт данные из котлов, помещения не требуются.
        if not self.project.spaces and fmt.key != "gas_load":
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

        # HLGC требует исходный шаблон-таблицу
        if fmt.key == "hlgc":
            src = self.hlgc_source.text().strip()
            if not src or not os.path.exists(src):
                QMessageBox.warning(
                    self, _t("export.hlgc.no_source.title"),
                    _t("export.hlgc.no_source.msg"))
                return

        if fmt.key == "gas_load":
            params = self._collect_gas_params()
        elif fmt.key == "hlgc":
            params = self._collect_hlgc_params()
        else:
            params = {}
        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(True)

        self._thread = QThread(self)
        self._worker = ExportWorker(fmt, self.project, path, params)
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
