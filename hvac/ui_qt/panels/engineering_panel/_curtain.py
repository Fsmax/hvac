# -*- coding: utf-8 -*-
"""_CurtainTab — подбор воздушно-тепловых завес (СНиП 2.04.05 прил. 20)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
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


class _CurtainTab(QWidget):
    """Калькулятор воздушно-тепловой завесы для проёма."""
    HEADER_KEYS = ("panel.eng.cu.col.param", "panel.eng.cu.col.value")
    PURPOSE_KEYS = (
        ("panel.eng.cu.purpose_public", 14.0),
        ("panel.eng.cu.purpose_ind_light", 12.0),
        ("panel.eng.cu.purpose_ind_none", 5.0),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.cu.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        # Две колонки формы: геометрия/климат и параметры завесы
        cols = QHBoxLayout()
        left = QFormLayout()
        right = QFormLayout()
        cols.addLayout(left, 1)
        cols.addSpacing(16)
        cols.addLayout(right, 1)
        outer.addLayout(cols)

        self.type_combo = QComboBox()
        self.type_combo.addItem(_t("panel.eng.cu.type_door"))
        self.type_combo.addItem(_t("panel.eng.cu.type_gate"))
        left.addRow(QLabel(_t("panel.eng.cu.type")), self.type_combo)

        self.width_spin = _spin(0.5, 30.0, 1.5, 2, " м")
        left.addRow(QLabel(_t("panel.eng.cu.width")), self.width_spin)
        self.height_spin = _spin(0.5, 12.0, 2.2, 2, " м")
        left.addRow(QLabel(_t("panel.eng.cu.height")), self.height_spin)
        self.bld_spin = _spin(3.0, 150.0, 9.0, 1, " м")
        left.addRow(QLabel(_t("panel.eng.cu.bld_height")), self.bld_spin)

        t_out_default = getattr(
            getattr(project, "params", None), "t_out_heating", -15.0)
        self.t_out_spin = _spin(-50.0, 10.0, t_out_default, 1, " °C")
        left.addRow(QLabel(_t("panel.eng.cu.t_out")), self.t_out_spin)
        self.t_in_spin = _spin(5.0, 30.0, 18.0, 1, " °C")
        left.addRow(QLabel(_t("panel.eng.cu.t_in")), self.t_in_spin)
        self.wind_spin = _spin(0.0, 20.0, 3.0, 1, " м/с")
        left.addRow(QLabel(_t("panel.eng.cu.wind")), self.wind_spin)

        self.purpose_combo = QComboBox()
        for key, _tmix in self.PURPOSE_KEYS:
            self.purpose_combo.addItem(_t(key))
        self.purpose_combo.currentIndexChanged.connect(self._purpose_changed)
        right.addRow(QLabel(_t("panel.eng.cu.purpose")), self.purpose_combo)

        self.t_mix_spin = _spin(0.0, 20.0, 14.0, 1, " °C")
        right.addRow(QLabel(_t("panel.eng.cu.t_mix")), self.t_mix_spin)
        self.q_spin = _spin(0.1, 1.0, 0.7, 2, "")
        right.addRow(QLabel(_t("panel.eng.cu.q_ratio")), self.q_spin)
        self.mu_spin = _spin(0.05, 0.9, 0.25, 2, "")
        right.addRow(QLabel(_t("panel.eng.cu.mu")), self.mu_spin)
        self.slot_spin = _spin(0.0, 5.0, 0.0, 3, " м²")
        right.addRow(QLabel(_t("panel.eng.cu.slot")), self.slot_spin)
        self.intake_check = QCheckBox(_t("panel.eng.cu.intake_inside"))
        self.intake_check.setChecked(True)
        right.addRow(QLabel(""), self.intake_check)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.cu.btn_run"))
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
        self._info.setText(_t("panel.eng.cu.info"))
        self.run_btn.setText(_t("panel.eng.cu.btn_run"))
        self.intake_check.setText(_t("panel.eng.cu.intake_inside"))
        i = self.type_combo.currentIndex()
        self.type_combo.setItemText(0, _t("panel.eng.cu.type_door"))
        self.type_combo.setItemText(1, _t("panel.eng.cu.type_gate"))
        self.type_combo.setCurrentIndex(i)
        for idx, (key, _tmix) in enumerate(self.PURPOSE_KEYS):
            self.purpose_combo.setItemText(idx, _t(key))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])

    def _purpose_changed(self, idx: int) -> None:
        self.t_mix_spin.setValue(self.PURPOSE_KEYS[idx][1])

    def _run(self):
        from hvac.air_curtain import AirCurtainInput, calc_air_curtain
        inp = AirCurtainInput(
            is_gate=self.type_combo.currentIndex() == 1,
            width_m=self.width_spin.value(),
            height_m=self.height_spin.value(),
            building_height_m=self.bld_spin.value(),
            t_outside_c=self.t_out_spin.value(),
            t_inside_c=self.t_in_spin.value(),
            t_mix_c=self.t_mix_spin.value(),
            wind_speed_ms=self.wind_spin.value(),
            q_ratio=self.q_spin.value(),
            mu_flow=self.mu_spin.value(),
            intake_inside=self.intake_check.isChecked(),
            slot_area_m2=self.slot_spin.value(),
        )
        try:
            res = calc_air_curtain(inp)
        except ValueError as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return

        rows = [
            [_t("panel.eng.cu.row.area"), f"{res.opening_area_m2:.2f}"],
            [_t("panel.eng.cu.row.dp"), f"{res.dp_pa:.1f}"],
            [_t("panel.eng.cu.row.g"), f"{res.g_kg_h:,.0f}".replace(",", " ")],
            [_t("panel.eng.cu.row.l"), f"{res.l_m3_h:,.0f}".replace(",", " ")],
            [_t("panel.eng.cu.row.t_supply"), f"{res.t_supply_c:+.1f}"],
            [_t("panel.eng.cu.row.q"), f"{res.q_heat_w / 1000:.1f}"],
        ]
        if res.v_slot_ms > 0:
            rows.append([_t("panel.eng.cu.row.v_slot"),
                         f"{res.v_slot_ms:.1f}"])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)
        self.warn_lbl.setText("\n".join(res.warnings))
        self.bridge.statusMessage.emit(_t("panel.eng.cu.status"), 4000)
