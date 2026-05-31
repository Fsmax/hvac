# -*- coding: utf-8 -*-
"""_HydraulicsTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _HydraulicsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.hyd.col.loop", "panel.eng.hyd.col.q",
        "panel.eng.hyd.col.h", "panel.eng.hyd.col.pump",
        "panel.eng.hyd.col.p", "panel.eng.hyd.col.vtank",
        "panel.eng.hyd.col.tank", "panel.eng.hyd.col.pmax",
        "panel.eng.hyd.col.makeup",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        toolbar = QHBoxLayout()
        self._lbl_h = QLabel(_t("panel.eng.hyd.h_static"))
        toolbar.addWidget(self._lbl_h)
        from PySide6.QtWidgets import QDoubleSpinBox
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.0, 200.0)
        self.height_spin.setSuffix(" м")
        self.height_spin.setValue(10.0)
        toolbar.addWidget(self.height_spin)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.hyd.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.calculationDone):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_h.setText(_t("panel.eng.hyd.h_static"))
        self.run_btn.setText(_t("panel.eng.hyd.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.design_heating_hydraulics(
                static_height_m=self.height_spin.value())
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.hyd.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "heating_hydraulics_results",
                       {}) or {}
        rows = []
        for name, r in data.items():
            rows.append([
                name,
                round(r.pump.flow_m3_h, 2),
                round(r.pump.head_m, 2),
                r.pump.selected_model or "—",
                round(r.pump.selected_power_w, 0),
                round(r.expansion_tank.required_tank_volume_l, 1),
                r.expansion_tank.selected_model or "—",
                round(r.expansion_tank.p_max_bar, 2),
                round(r.makeup.daily_makeup_l, 1),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


