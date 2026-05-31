# -*- coding: utf-8 -*-
"""VentilationPanel — таблица расходов воздуха по помещениям + сводка."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableView, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.theme import tokens
from hvac.ui_qt.widgets.card import Card


_VENT_HEADER_KEYS = [
    "panel.ventilation.col.number", "panel.ventilation.col.name",
    "panel.ventilation.col.level",  "panel.ventilation.col.type",
    "panel.ventilation.col.area",   "panel.ventilation.col.supply",
    "panel.ventilation.col.exhaust","panel.ventilation.col.hood",
    "panel.ventilation.col.ach",    "panel.ventilation.col.imbal",
]


class VentilationModel(QAbstractTableModel):

    def __init__(self, project: HVACProject, bridge: ProjectBridge):
        super().__init__()
        self.project = project
        self.bridge = bridge
        bridge.dataLoaded.connect(self._reset)
        bridge.projectLoaded.connect(self._reset)
        bridge.ventilationDone.connect(self._reset)

    def _reset(self, *args: Any) -> None:
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.project.spaces)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_VENT_HEADER_KEYS)

    def headerData(self, section, orient, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orient == Qt.Horizontal:
            return _t(_VENT_HEADER_KEYS[section])
        return None

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        sp: Space = self.project.spaces[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole,):
            if col == 0: return sp.number
            if col == 1: return sp.name
            if col == 2: return sp.level
            if col == 3: return sp.room_type
            if col == 4: return f"{sp.area_m2:.1f}"
            if col == 5: return f"{sp.supply_m3h:.0f}" if sp.supply_m3h else ""
            if col == 6: return f"{sp.exhaust_m3h:.0f}" if sp.exhaust_m3h else ""
            if col == 7: return f"{sp.hood_m3h:.0f}" if sp.hood_m3h else ""
            if col == 8: return f"{sp.ach_calculated:.1f}" if sp.ach_calculated else ""
            if col == 9:
                diff = sp.supply_m3h - (sp.exhaust_m3h + sp.hood_m3h)
                return f"{diff:+.0f}" if (sp.supply_m3h or sp.exhaust_m3h) else ""
        if role == Qt.TextAlignmentRole and col >= 4:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and col == 9:
            if not (sp.supply_m3h or sp.exhaust_m3h):
                return None
            diff = sp.supply_m3h - (sp.exhaust_m3h + sp.hood_m3h)
            if abs(diff) > 50:
                return QBrush(QColor(tokens()["warning"]))
        return None


class VentilationPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.ventilation.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)

        self.run_btn = QPushButton(_t("panel.ventilation.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self._run)
        head.addWidget(self.run_btn)
        outer.addLayout(head)

        # Сводка-карточки
        self.summary_card = Card(_t("panel.ventilation.summary_card.title"),
                                  _t("panel.ventilation.summary_card.subtitle"))
        self.summary_lbl = QLabel(_t("common.not_yet"))
        self.summary_lbl.setProperty("role", "muted")
        self.summary_lbl.setTextFormat(Qt.RichText)
        self.summary_card.body().addWidget(self.summary_lbl)
        outer.addWidget(self.summary_card)

        # Поиск
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        outer.addWidget(self.search)

        # Таблица
        from PySide6.QtCore import QSortFilterProxyModel
        self.model = VentilationModel(project, bridge)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        widths = [80, 200, 110, 130, 70, 100, 100, 90, 80, 100]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        outer.addWidget(self.table, stretch=1)

        bridge.dataLoaded.connect(self._refresh_summary)
        bridge.projectLoaded.connect(self._refresh_summary)
        bridge.ventilationDone.connect(self._refresh_summary)
        self._refresh_summary()

    def _run(self) -> None:
        if not self.project.spaces:
            return
        # Делегируем CalculationPanel — там async-обёртка
        from hvac.ui_qt.panels.calculation_panel import CalculationPanel
        parent = self.parent()
        while parent and not isinstance(parent, type(None)):
            # Пытаемся найти MainWindow и через него CalculationPanel
            if hasattr(parent, "_panels"):
                cp = parent._panels.get("calculation")
                if isinstance(cp, CalculationPanel):
                    cp._run_vent()  # noqa: SLF001
                    return
            parent = parent.parent()
        # Fallback: синхронно
        self.project.calculate_ventilation()

    def _refresh_summary(self, *args: Any) -> None:
        spaces = self.project.spaces
        if not spaces:
            self.summary_lbl.setText(_t("common.empty_no_spaces"))
            return
        sup = sum(s.supply_m3h for s in spaces)
        exh = sum(s.exhaust_m3h for s in spaces)
        hood = sum(s.hood_m3h for s in spaces)
        if not (sup or exh):
            self.summary_lbl.setText(_t("panel.ventilation.summary_not_yet"))
            return
        diff = sup - exh - hood
        # Цифры форматируются вне строки чтобы пробельный разделитель
        # тысяч одинаково работал во всех локалях.
        def _fmt(v: float, plus: bool = False) -> str:
            fmt = f"{v:+,.0f}" if plus else f"{v:,.0f}"
            return fmt.replace(",", " ")
        self.summary_lbl.setText(
            _t("panel.ventilation.summary_html").format(
                sup=_fmt(sup), exh=_fmt(exh),
                hood=_fmt(hood), diff=_fmt(diff, plus=True))
        )

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.ventilation.title"))
        self.run_btn.setText(_t("panel.ventilation.btn_run"))
        self.summary_card.set_title(_t("panel.ventilation.summary_card.title"))
        self.summary_card.set_subtitle(
            _t("panel.ventilation.summary_card.subtitle"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.model.columnCount() - 1)
        self._refresh_summary()
