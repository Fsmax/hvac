# -*- coding: utf-8 -*-
"""_RadiatorsTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _RadiatorsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.rad.col.no", "panel.eng.rad.col.space",
        "panel.eng.rad.col.q", "panel.eng.rad.col.model",
        "panel.eng.rad.col.height", "panel.eng.rad.col.size",
        "panel.eng.rad.col.qfact", "panel.eng.rad.col.margin",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        toolbar = QHBoxLayout()
        self._lbl_fam = QLabel(_t("panel.eng.rad.family"))
        toolbar.addWidget(self._lbl_fam)
        self.family_combo = QComboBox()
        self.family_combo.addItem(_t("panel.eng.rad.family.all"), userData=None)
        for fam in [
            "Стальной панельный 11", "Стальной панельный 22",
            "Стальной панельный 33", "Алюминий",
            "Биметалл", "Биметалл (моноблок)", "Чугун",
        ]:
            self.family_combo.addItem(fam, userData=fam)
        toolbar.addWidget(self.family_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.rad.btn_run"))
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
        self._lbl_fam.setText(_t("panel.eng.rad.family"))
        prev_data = self.family_combo.currentData()
        self.family_combo.blockSignals(True)
        self.family_combo.clear()
        self.family_combo.addItem(_t("panel.eng.rad.family.all"), userData=None)
        for fam in [
            "Стальной панельный 11", "Стальной панельный 22",
            "Стальной панельный 33", "Алюминий",
            "Биметалл", "Биметалл (моноблок)", "Чугун",
        ]:
            self.family_combo.addItem(fam, userData=fam)
        for i in range(self.family_combo.count()):
            if self.family_combo.itemData(i) == prev_data:
                self.family_combo.setCurrentIndex(i)
                break
        self.family_combo.blockSignals(False)
        self.run_btn.setText(_t("panel.eng.rad.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        fam = self.family_combo.currentData()
        filter_list = [fam] if fam else None
        try:
            self.project.select_radiators_for_all_spaces(
                family_filter=filter_list)
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.rad.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "radiator_picks", {}) or {}
        rows = []
        for sp in self.project.spaces:
            pick = data.get(sp.space_id)
            if pick is None:
                continue
            length_or_sect = (
                _t("panel.eng.rad.sect").format(n=pick.sections)
                if pick.model.is_sectional
                else _t("panel.eng.rad.mm").format(n=pick.model.length_mm))
            rows.append([
                sp.number, sp.name,
                round(sp.heat_loss_w, 0),
                pick.model.name,
                pick.model.height_mm,
                length_or_sect,
                round(pick.actual_power_w, 0),
                round(pick.margin_pct, 1),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


