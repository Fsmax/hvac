# -*- coding: utf-8 -*-
"""RoomEquipmentPanel — конечное оборудование, установленное в помещениях.

Показывает таблицу: помещение → радиатор/фанкойл/диффузор. Заполняется
вручную после расчёта нагрузок.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


_HEADER_KEYS = [
    "panel.room_eq.col.number", "panel.room_eq.col.name",
    "panel.room_eq.col.q_heat", "panel.room_eq.col.terminal",
    "panel.room_eq.col.power",  "panel.room_eq.col.qty",
    "panel.room_eq.col.diffuser", "panel.room_eq.col.diff_qty",
]


class RoomEquipmentPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.title_lbl = QLabel(_t("panel.room_eq.title"))
        self.title_lbl.setProperty("role", "h1")
        outer.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel(_t("panel.room_eq.subtitle"))
        self.subtitle_lbl.setProperty("role", "muted")
        outer.addWidget(self.subtitle_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        outer.addWidget(self.search)

        self.table = QTableWidget(0, len(_HEADER_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        widths = [80, 200, 100, 200, 100, 80, 200, 80]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.room_eq.title"))
        self.subtitle_lbl.setText(_t("panel.room_eq.subtitle"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])

    def _refresh(self, *args: Any) -> None:
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            eq = sp.room_equipment
            cells = [
                sp.number, sp.name,
                f"{sp.heat_loss_w/1000:.2f}" if sp.heat_loss_w else "",
                (eq.heating_terminal_type or "") if eq else "",
                f"{eq.heating_terminal_power_w:.0f}" if eq and eq.heating_terminal_power_w else "",
                f"{eq.heating_terminal_qty:.0f}" if eq and eq.heating_terminal_qty else "",
                (getattr(eq, 'diffuser_type', '') or "") if eq else "",
                f"{getattr(eq, 'diffuser_qty', 0):.0f}" if eq and getattr(eq, 'diffuser_qty', 0) else "",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c in (2, 4, 5, 7):
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(r, c, item)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            visible = True
            if t:
                row_text = " ".join(
                    (self.table.item(r, c).text()
                     if self.table.item(r, c) else "")
                    for c in range(self.table.columnCount())
                ).lower()
                visible = t in row_text
            self.table.setRowHidden(r, not visible)
