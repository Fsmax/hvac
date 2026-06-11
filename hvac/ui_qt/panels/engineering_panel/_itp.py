# -*- coding: utf-8 -*-
"""_ITPTab — подбор пластинчатого теплообменника ИТП (LMTD)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget)
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


def _spin(lo: float, hi: float, value: float, decimals: int = 1,
          suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    s.setDecimals(decimals)
    if suffix:
        s.setSuffix(suffix)
    return s


class _ITPTab(QWidget):
    """Калькулятор пластинчатого ТО для ИТП."""
    HEADER_KEYS = ("panel.eng.itp.col.param", "panel.eng.itp.col.value")
    PRESET_KEYS = (
        ("panel.eng.itp.preset_95_70", "heating_95_70"),
        ("panel.eng.itp.preset_80_60", "heating_80_60"),
        ("panel.eng.itp.preset_dhw", "dhw"),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.itp.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        cols = QHBoxLayout()
        left = QFormLayout()
        right = QFormLayout()
        cols.addLayout(left, 1)
        cols.addSpacing(16)
        cols.addLayout(right, 1)
        outer.addLayout(cols)

        self.preset_combo = QComboBox()
        for key, _pid in self.PRESET_KEYS:
            self.preset_combo.addItem(_t(key))
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        left.addRow(QLabel(_t("panel.eng.itp.preset")), self.preset_combo)

        self.q_spin = _spin(1.0, 100000.0, 100.0, 1, " кВт")
        left.addRow(QLabel(_t("panel.eng.itp.q")), self.q_spin)
        self.load_btn = QPushButton(_t("panel.eng.itp.btn_from_project"))
        self.load_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.load_btn.clicked.connect(self._q_from_project)
        left.addRow(QLabel(""), self.load_btn)

        self.k_spin = _spin(500.0, 8000.0, 4500.0, 0, " Вт/(м²·К)")
        left.addRow(QLabel(_t("panel.eng.itp.k")), self.k_spin)
        self.margin_spin = _spin(0.0, 0.5, 0.10, 2, "")
        left.addRow(QLabel(_t("panel.eng.itp.margin")), self.margin_spin)

        self.t_hot_in_spin = _spin(20.0, 200.0, 95.0, 1, " °C")
        right.addRow(QLabel(_t("panel.eng.itp.t_hot_in")), self.t_hot_in_spin)
        self.t_hot_out_spin = _spin(10.0, 150.0, 70.0, 1, " °C")
        right.addRow(QLabel(_t("panel.eng.itp.t_hot_out")), self.t_hot_out_spin)
        self.t_cold_in_spin = _spin(0.0, 120.0, 60.0, 1, " °C")
        right.addRow(QLabel(_t("panel.eng.itp.t_cold_in")), self.t_cold_in_spin)
        self.t_cold_out_spin = _spin(5.0, 150.0, 80.0, 1, " °C")
        right.addRow(QLabel(_t("panel.eng.itp.t_cold_out")), self.t_cold_out_spin)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.itp.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        self.warn_lbl = QLabel("")
        self.warn_lbl.setProperty("role", "muted")
        self.warn_lbl.setWordWrap(True)
        self.warn_lbl.setStyleSheet("color: #CC6600;")
        outer.addWidget(self.warn_lbl)

    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.itp.info"))
        self.run_btn.setText(_t("panel.eng.itp.btn_run"))
        self.load_btn.setText(_t("panel.eng.itp.btn_from_project"))
        i = self.preset_combo.currentIndex()
        for idx, (key, _pid) in enumerate(self.PRESET_KEYS):
            self.preset_combo.setItemText(idx, _t(key))
        self.preset_combo.setCurrentIndex(i)
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])

    def _preset_changed(self, idx: int) -> None:
        from hvac.heat_exchanger import HX_PRESETS
        t1i, t1o, t2i, t2o = HX_PRESETS[self.PRESET_KEYS[idx][1]]
        self.t_hot_in_spin.setValue(t1i)
        self.t_hot_out_spin.setValue(t1o)
        self.t_cold_in_spin.setValue(t2i)
        self.t_cold_out_spin.setValue(t2o)

    def _q_from_project(self) -> None:
        total_w = sum(sp.heat_loss_w for sp in self.project.spaces)
        if total_w > 0:
            self.q_spin.setValue(total_w / 1000.0)
        else:
            QMessageBox.information(
                self, _t("panel.eng.itp.btn_from_project"),
                _t("panel.eng.itp.no_loads"))

    def _run(self):
        from hvac.heat_exchanger import PlateHXInput, calc_plate_hx
        inp = PlateHXInput(
            q_kw=self.q_spin.value(),
            t_hot_in=self.t_hot_in_spin.value(),
            t_hot_out=self.t_hot_out_spin.value(),
            t_cold_in=self.t_cold_in_spin.value(),
            t_cold_out=self.t_cold_out_spin.value(),
            k_w_m2k=self.k_spin.value(),
            margin=self.margin_spin.value(),
        )
        try:
            res = calc_plate_hx(inp)
        except ValueError as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return

        rows = [
            [_t("panel.eng.itp.row.lmtd"), f"{res.lmtd_k:.1f}"],
            [_t("panel.eng.itp.row.area"), f"{res.area_m2:.2f}"],
            [_t("panel.eng.itp.row.g_hot"), f"{res.g_hot_m3h:.2f}"],
            [_t("panel.eng.itp.row.g_cold"), f"{res.g_cold_m3h:.2f}"],
        ]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)
        self.warn_lbl.setText("\n".join(res.warnings))
        self.bridge.statusMessage.emit(_t("panel.eng.itp.status"), 4000)
