# -*- coding: utf-8 -*-
"""_ComfortTab — тепловой комфорт PMV/PPD по ISO 7730."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QVBoxLayout, QWidget,
)
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _ComfortTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.cf.col.number", "panel.eng.cf.col.name",
        "panel.eng.cf.col.t_w", "panel.eng.cf.col.pmv_w",
        "panel.eng.cf.col.ppd_w", "panel.eng.cf.col.cat_w",
        "panel.eng.cf.col.t_s", "panel.eng.cf.col.pmv_s",
        "panel.eng.cf.col.ppd_s", "panel.eng.cf.col.cat_s",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.cf.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        toolbar = QHBoxLayout()
        self._met_lbl = QLabel(_t("panel.eng.cf.met"))
        toolbar.addWidget(self._met_lbl)
        self.met_spin = QDoubleSpinBox()
        self.met_spin.setRange(0.8, 4.0)
        self.met_spin.setSingleStep(0.1)
        self.met_spin.setValue(1.2)
        toolbar.addWidget(self.met_spin)
        self._vair_lbl = QLabel(_t("panel.eng.cf.vair"))
        toolbar.addWidget(self._vair_lbl)
        self.vair_spin = QDoubleSpinBox()
        self.vair_spin.setRange(0.05, 1.0)
        self.vair_spin.setSingleStep(0.05)
        self.vair_spin.setValue(0.1)
        toolbar.addWidget(self.vair_spin)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.cf.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.cf.info"))
        self._met_lbl.setText(_t("panel.eng.cf.met"))
        self._vair_lbl.setText(_t("panel.eng.cf.vair"))
        self.run_btn.setText(_t("panel.eng.cf.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.calculate_comfort(
                met=self.met_spin.value(),
                v_air_ms=self.vair_spin.value(),
            )
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.cf.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "comfort_results", {}) or {}
        winter = data.get("heating", {})
        summer = data.get("cooling", {})
        rows = []
        for sp in self.project.spaces:
            w = winter.get(sp.space_id)
            s = summer.get(sp.space_id)
            if w is None and s is None:
                continue
            rows.append([
                sp.number, sp.name,
                w.t_air_c if w else "—",
                w.pmv if w else "—",
                w.ppd if w else "—",
                w.category if w else "—",
                s.t_air_c if s else "—",
                s.pmv if s else "—",
                s.ppd if s else "—",
                s.category if s else "—",
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)
