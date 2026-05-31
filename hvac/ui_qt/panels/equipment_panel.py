# -*- coding: utf-8 -*-
"""EquipmentPanel — каталог систем оборудования (отопление/охлаждение/AHU).

Показывает все зарегистрированные в проекте системы. Параметры систем
редактируются построчно (минимально — name + тип + ключевые числа). Для
глубокой настройки контуров можно вернуть отдельный диалог.
"""
from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


# Структура: (header-keys для колонок, tab-key для заголовка вкладки)
_HEAT_COLS = ["panel.equipment.col.name", "panel.equipment.col.type",
              "panel.equipment.col.t_sup", "panel.equipment.col.t_ret",
              "panel.equipment.col.fuel", "panel.equipment.col.eff"]
_COOL_COLS = ["panel.equipment.col.name", "panel.equipment.col.type",
              "panel.equipment.col.t_sup", "panel.equipment.col.t_ret",
              "panel.equipment.col.cop",  "panel.equipment.col.refr"]
_VENT_COLS = ["panel.equipment.col.ahu",  "panel.equipment.col.type",
              "panel.equipment.col.recov","panel.equipment.col.eta_w",
              "panel.equipment.col.eta_s","panel.equipment.col.t_in_w"]
_LOAD_COLS = ["panel.equipment.col.ahu",  "panel.equipment.col.q_win",
              "panel.equipment.col.q_sens","panel.equipment.col.q_lat",
              "panel.equipment.col.flow"]


class EquipmentPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.title_lbl = QLabel(_t("panel.equipment.title"))
        self.title_lbl.setProperty("role", "h1")
        outer.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel(_t("panel.equipment.subtitle"))
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        outer.addWidget(self.subtitle_lbl)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, stretch=1)

        self.heat_table = self._make_table([_t(k) for k in _HEAT_COLS])
        self.tabs.addTab(self.heat_table, _t("panel.equipment.tab.heat"))

        self.cool_table = self._make_table([_t(k) for k in _COOL_COLS])
        self.tabs.addTab(self.cool_table, _t("panel.equipment.tab.cool"))

        self.vent_table = self._make_table([_t(k) for k in _VENT_COLS])
        self.tabs.addTab(self.vent_table, _t("panel.equipment.tab.ahu"))

        self.ahu_load_table = self._make_table([_t(k) for k in _LOAD_COLS])
        self.tabs.addTab(self.ahu_load_table, _t("panel.equipment.tab.load"))

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.zonesChanged, bridge.ahuLoadsCalculated):
            sig.connect(self._refresh)
        self._refresh()

    def _make_table(self, headers: List[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(26)
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        return t

    def _refresh(self, *args: Any) -> None:
        # Отопление
        self._fill(self.heat_table, self.project.heating_systems.values(),
                   lambda s: [s.name, s.system_type, f"{s.t_supply:.0f}",
                              f"{s.t_return:.0f}", s.fuel,
                              f"{s.efficiency:.2f}"])
        # Охлаждение
        self._fill(self.cool_table, self.project.cooling_systems.values(),
                   lambda s: [s.name, s.system_type, f"{s.t_supply:.0f}",
                              f"{s.t_return:.0f}", f"{s.cop:.1f}",
                              s.refrigerant])
        # Вентиляция
        self._fill(self.vent_table, self.project.ventilation_systems.values(),
                   lambda s: [s.name, s.system_type,
                              "✓" if s.has_recovery else "—",
                              f"{s.recovery_efficiency_winter:.2f}",
                              f"{s.recovery_efficiency_summer:.2f}",
                              f"{s.t_supply_winter:.0f}"])
        # Нагрузка AHU
        loads = self.project.ahu_loads or {}
        rows = []
        for name, info in sorted(loads.items()):
            rows.append([
                name,
                f"{info.get('q_heating_w', 0)/1000:.1f}",
                f"{info.get('q_sensible_cooling_w', 0)/1000:.1f}",
                f"{info.get('q_latent_cooling_w', 0)/1000:.1f}",
                f"{info.get('flow_m3h', info.get('supply_m3h', 0)):.0f}",
            ])
        self._fill_rows(self.ahu_load_table, rows)

    def _fill(self, table: QTableWidget, items, formatter) -> None:
        rows = [formatter(it) for it in items]
        self._fill_rows(table, rows)

    def _fill_rows(self, table: QTableWidget, rows: List[List[str]]) -> None:
        table.setRowCount(len(rows))
        for r, cells in enumerate(rows):
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c >= 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, c, item)

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.equipment.title"))
        self.subtitle_lbl.setText(_t("panel.equipment.subtitle"))
        self.tabs.setTabText(0, _t("panel.equipment.tab.heat"))
        self.tabs.setTabText(1, _t("panel.equipment.tab.cool"))
        self.tabs.setTabText(2, _t("panel.equipment.tab.ahu"))
        self.tabs.setTabText(3, _t("panel.equipment.tab.load"))
        self.heat_table.setHorizontalHeaderLabels([_t(k) for k in _HEAT_COLS])
        self.cool_table.setHorizontalHeaderLabels([_t(k) for k in _COOL_COLS])
        self.vent_table.setHorizontalHeaderLabels([_t(k) for k in _VENT_COLS])
        self.ahu_load_table.setHorizontalHeaderLabels(
            [_t(k) for k in _LOAD_COLS])
        self._refresh()
