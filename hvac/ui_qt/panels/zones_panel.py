# -*- coding: utf-8 -*-
"""ZonesPanel — авто-присвоение зон + сводка по зонам/системам."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card


# Соответствие mode → i18n-ключ. Само значение mode записывается в проект,
# а отображаемая подпись резолвится через _t() при каждой смене языка.
_MODE_KEY = {
    "by_prefix":      "panel.zones.mode.by_prefix",
    "by_level":       "panel.zones.mode.by_level",
    "by_type_family": "panel.zones.mode.by_type",
}
_SYSTEM_KEY = {
    "all":         "panel.zones.system.all",
    "heating":     "panel.zones.system.heating",
    "cooling":     "panel.zones.system.cooling",
    "ventilation": "panel.zones.system.ventilation",
}
_COL_KEYS = [
    "panel.zones.col.zone", "panel.zones.col.n_spaces",
    "panel.zones.col.area", "panel.zones.col.q_heat",
    "panel.zones.col.q_cool", "panel.zones.col.supply",
]


class ZonesPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        self.title_lbl = QLabel(_t("panel.zones.title"))
        self.title_lbl.setProperty("role", "h1")
        outer.addWidget(self.title_lbl)

        # Карточка авто-присвоения
        self.auto_card = Card(_t("panel.zones.auto.title"),
                                _t("panel.zones.auto.desc"))

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._lbl_criterion = QLabel(_t("panel.zones.criterion"))
        row1.addWidget(self._lbl_criterion)
        self.mode_combo = QComboBox()
        for k in _MODE_KEY:
            self.mode_combo.addItem(_t(_MODE_KEY[k]), userData=k)
        self.mode_combo.setMinimumWidth(360)
        row1.addWidget(self.mode_combo, stretch=1)

        self.overwrite_cb = QCheckBox(_t("panel.zones.overwrite"))
        row1.addWidget(self.overwrite_cb)
        self.auto_card.body().addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self._lbl_apply_to = QLabel(_t("panel.zones.apply_to"))
        row2.addWidget(self._lbl_apply_to)
        self.system_combo = QComboBox()
        for k in _SYSTEM_KEY:
            self.system_combo.addItem(_t(_SYSTEM_KEY[k]), userData=k)
        row2.addWidget(self.system_combo)
        row2.addStretch(1)

        self.apply_btn = QPushButton(_t("panel.zones.btn_apply"))
        self.apply_btn.setProperty("role", "primary")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_auto)
        row2.addWidget(self.apply_btn)
        self.auto_card.body().addLayout(row2)
        outer.addWidget(self.auto_card)

        # Карточка сводки
        self.summary_card = Card(_t("panel.zones.summary.title"),
                                   _t("panel.zones.summary.desc"))
        self.summary_combo = QComboBox()
        self.summary_combo.addItems([
            _t("panel.zones.summary.heating"),
            _t("panel.zones.summary.cooling"),
            _t("panel.zones.summary.vent"),
        ])
        self.summary_combo.currentIndexChanged.connect(self._refresh_table)
        self.summary_card.body().addWidget(self.summary_combo)

        self.table = QTableWidget(0, len(_COL_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _COL_KEYS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        widths = [200, 100, 100, 130, 140, 130]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.summary_card.body().addWidget(self.table)

        outer.addWidget(self.summary_card, stretch=1)

        bridge.dataLoaded.connect(self._refresh_table)
        bridge.projectLoaded.connect(self._refresh_table)
        bridge.zonesChanged.connect(self._refresh_table)
        bridge.calculationDone.connect(self._refresh_table)
        bridge.ventilationDone.connect(self._refresh_table)
        self._refresh_table()

    def _apply_auto(self) -> None:
        if not self.project.spaces:
            return
        mode = self.mode_combo.currentData()
        system = self.system_combo.currentData()
        overwrite = self.overwrite_cb.isChecked()
        n = self.project.auto_assign_zones(
            mode=mode, overwrite=overwrite, system=system)
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.assigned").format(n=n), 4000)

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.zones.title"))
        self.auto_card.set_title(_t("panel.zones.auto.title"))
        self.auto_card.set_subtitle(_t("panel.zones.auto.desc"))
        self._lbl_criterion.setText(_t("panel.zones.criterion"))
        self._lbl_apply_to.setText(_t("panel.zones.apply_to"))
        self.overwrite_cb.setText(_t("panel.zones.overwrite"))
        self.apply_btn.setText(_t("panel.zones.btn_apply"))
        # Перезаполнить combobox с сохранением выбранного userData
        cur_mode = self.mode_combo.currentData()
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for k in _MODE_KEY:
            self.mode_combo.addItem(_t(_MODE_KEY[k]), userData=k)
        idx = self.mode_combo.findData(cur_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.blockSignals(False)

        cur_sys = self.system_combo.currentData()
        self.system_combo.blockSignals(True)
        self.system_combo.clear()
        for k in _SYSTEM_KEY:
            self.system_combo.addItem(_t(_SYSTEM_KEY[k]), userData=k)
        idx = self.system_combo.findData(cur_sys)
        if idx >= 0:
            self.system_combo.setCurrentIndex(idx)
        self.system_combo.blockSignals(False)

        self.summary_card.set_title(_t("panel.zones.summary.title"))
        self.summary_card.set_subtitle(_t("panel.zones.summary.desc"))

        cur_sum = self.summary_combo.currentIndex()
        self.summary_combo.blockSignals(True)
        self.summary_combo.clear()
        self.summary_combo.addItems([
            _t("panel.zones.summary.heating"),
            _t("panel.zones.summary.cooling"),
            _t("panel.zones.summary.vent"),
        ])
        self.summary_combo.setCurrentIndex(max(0, cur_sum))
        self.summary_combo.blockSignals(False)

        self.table.setHorizontalHeaderLabels([_t(k) for k in _COL_KEYS])
        self._refresh_table()

    def _refresh_table(self, *args: Any) -> None:
        sys_map = {0: "heating", 1: "cooling", 2: "ventilation"}
        system = sys_map.get(self.summary_combo.currentIndex(), "heating")
        summary = self.project.get_zone_summary(system=system) or {}

        rows = sorted(summary.items(), key=lambda kv: kv[0])
        self.table.setRowCount(len(rows))
        for r, (zone, info) in enumerate(rows):
            cells = [
                zone,
                str(int(info.get("n_spaces", 0))),
                f"{info.get('area_m2', 0):.0f}",
                f"{info.get('q_heating_w', 0)/1000:.1f}",
                f"{info.get('q_cooling_w', 0)/1000:.1f}",
                f"{info.get('supply_m3h', 0):.0f}",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c >= 1:
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(r, c, item)
