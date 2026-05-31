# -*- coding: utf-8 -*-
"""_FancoilsTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _FancoilsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.fc.col.no", "panel.eng.fc.col.space",
        "panel.eng.fc.col.qc", "panel.eng.fc.col.qh",
        "panel.eng.fc.col.model", "panel.eng.fc.col.family",
        "panel.eng.fc.col.pipes", "panel.eng.fc.col.qc_fact",
        "panel.eng.fc.col.margin", "panel.eng.fc.col.air",
        "panel.eng.fc.col.noise",
    )
    PIPES = (
        ("panel.eng.fc.pipes.any", None),
        ("panel.eng.fc.pipes.2", 2),
        ("panel.eng.fc.pipes.4", 4),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        toolbar = QHBoxLayout()
        self._lbl_fam = QLabel(_t("panel.eng.fc.family"))
        toolbar.addWidget(self._lbl_fam)
        self.family_combo = QComboBox()
        self.family_combo.addItem(_t("panel.eng.fc.family.all"), userData=None)
        for fam in ("Кассетный 600×600", "Кассетный 600×600 (Roundflow)",
                     "Канальный низконапорный",
                     "Канальный среднего напора", "Настенный",
                     "Напольно-потолочный"):
            self.family_combo.addItem(fam, userData=fam)
        toolbar.addWidget(self.family_combo)
        toolbar.addSpacing(12)
        self._lbl_pipes = QLabel(_t("panel.eng.fc.pipes"))
        toolbar.addWidget(self._lbl_pipes)
        self.pipes_combo = QComboBox()
        for key, code in self.PIPES:
            self.pipes_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.pipes_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.fc.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_fam.setText(_t("panel.eng.fc.family"))
        self._lbl_pipes.setText(_t("panel.eng.fc.pipes"))
        prev_fam = self.family_combo.currentData()
        self.family_combo.blockSignals(True)
        self.family_combo.clear()
        self.family_combo.addItem(_t("panel.eng.fc.family.all"), userData=None)
        for fam in ("Кассетный 600×600", "Кассетный 600×600 (Roundflow)",
                     "Канальный низконапорный",
                     "Канальный среднего напора", "Настенный",
                     "Напольно-потолочный"):
            self.family_combo.addItem(fam, userData=fam)
        for i in range(self.family_combo.count()):
            if self.family_combo.itemData(i) == prev_fam:
                self.family_combo.setCurrentIndex(i)
                break
        self.family_combo.blockSignals(False)

        prev_pipes = self.pipes_combo.currentData()
        self.pipes_combo.blockSignals(True)
        self.pipes_combo.clear()
        for key, code in self.PIPES:
            self.pipes_combo.addItem(_t(key), userData=code)
        for i in range(self.pipes_combo.count()):
            if self.pipes_combo.itemData(i) == prev_pipes:
                self.pipes_combo.setCurrentIndex(i)
                break
        self.pipes_combo.blockSignals(False)

        self.run_btn.setText(_t("panel.eng.fc.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        fam = self.family_combo.currentData()
        family_filter = [fam] if fam else None
        pipes = self.pipes_combo.currentData()
        try:
            self.project.select_fancoils_for_project(
                family_filter=family_filter, pipes_filter=pipes,
            )
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.fc.status"), 3000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "fancoil_picks", {}) or {}
        rows = []
        for sp in self.project.spaces:
            pick = data.get(sp.space_id)
            if pick is None:
                continue
            rows.append([
                sp.number, sp.name,
                round(sp.heat_gain_w, 0),
                round(sp.heat_loss_w, 0),
                pick.model.name, pick.model.family,
                pick.model.pipes,
                round(pick.actual_cool_w, 0),
                round(pick.cool_margin_pct, 1),
                round(pick.model.air_flow_m3_h, 0),
                round(pick.model.noise_db_a, 0),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


