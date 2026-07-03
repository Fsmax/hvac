# -*- coding: utf-8 -*-
"""ProblemsPanel — сводный список проверок проекта (validate_detailed).

Показывает ошибки/предупреждения/инфо с категорией и сообщением. Двойной
клик по строке с привязкой к помещению переходит к нему в разделе
«Помещения». Данные берутся из HVACProject.validate_detailed().
"""
from __future__ import annotations

from typing import Any, Callable, List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableView, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.theme import tokens
from hvac.ui_qt.widgets.card import Card
from hvac.ui_qt.widgets.table_clipboard import install_copy


# Порядок сортировки по важности.
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_SEVERITY_KEY = {
    "error": "panel.problems.severity.error",
    "warning": "panel.problems.severity.warning",
    "info": "panel.problems.severity.info",
}
_SEVERITY_TOKEN = {"error": "danger", "warning": "warning",
                   "info": "text_muted"}
_SEVERITY_ICON = {"error": "⛔", "warning": "⚠", "info": "ℹ"}


class ProblemsModel(QAbstractTableModel):
    _COL_KEYS = [
        "panel.problems.col.severity", "panel.problems.col.category",
        "panel.problems.col.space", "panel.problems.col.message",
    ]

    def __init__(self, project: HVACProject):
        super().__init__()
        self.project = project
        self._rows: List[dict] = []

    def refresh(self) -> None:
        self.beginResetModel()
        try:
            data = self.project.validate_detailed()
        except Exception:
            import traceback
            traceback.print_exc()
            data = []
        data.sort(key=lambda d: _SEVERITY_ORDER.get(d.get("severity", ""), 9))
        self._rows = data
        self.endResetModel()

    # ---- Qt API ----
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._COL_KEYS)

    def headerData(self, section, orient, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orient == Qt.Horizontal:
            return _t(self._COL_KEYS[section])
        return None

    def _space_label(self, space_id: str) -> str:
        if not space_id:
            return ""
        sp = self.project.get_space(space_id)
        if sp is None:
            return space_id
        return f"{sp.number} {sp.name}".strip()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        rec = self._rows[index.row()]
        col = index.column()
        sev = rec.get("severity", "info")
        if role == Qt.DisplayRole:
            if col == 0:
                return f"{_SEVERITY_ICON.get(sev, '')} {_t(_SEVERITY_KEY.get(sev, ''))}".strip()
            if col == 1:
                return rec.get("category", "")
            if col == 2:
                return self._space_label(rec.get("space_id", ""))
            if col == 3:
                return rec.get("msg", "")
        if role == Qt.ForegroundRole and col == 0:
            return QBrush(QColor(
                tokens()[_SEVERITY_TOKEN.get(sev, "text_muted")]))
        return None

    def space_id_at(self, row: int) -> str:
        if 0 <= row < len(self._rows):
            return self._rows[row].get("space_id", "")
        return ""

    def counts(self) -> dict:
        c = {"error": 0, "warning": 0, "info": 0}
        for r in self._rows:
            sev = r.get("severity", "info")
            c[sev] = c.get(sev, 0) + 1
        return c


class ProblemsPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 navigate: Callable[[str], None] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._navigate = navigate

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.problems.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.refresh_btn = QPushButton(_t("btn.refresh"))
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        head.addWidget(self.refresh_btn)
        outer.addLayout(head)

        self.summary_card = Card(_t("panel.problems.title"),
                                  _t("panel.problems.hint"))
        self.summary_lbl = QLabel(_t("common.not_yet"))
        self.summary_lbl.setProperty("role", "muted")
        self.summary_card.body().addWidget(self.summary_lbl)
        outer.addWidget(self.summary_card)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        outer.addWidget(self.search)

        from PySide6.QtCore import QSortFilterProxyModel
        self.model = ProblemsModel(project)
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
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        for i, w in enumerate([130, 130, 240, 560]):
            self.table.setColumnWidth(i, w)
        self.table.doubleClicked.connect(self._on_double_click)
        install_copy(self.table)
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.constructionsChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ---- Логика ----
    def _refresh(self, *args: Any) -> None:
        self.model.refresh()
        if not self.project.spaces:
            self.summary_lbl.setText(_t("panel.problems.not_calculated"))
            return
        c = self.model.counts()
        total = c["error"] + c["warning"] + c["info"]
        if total == 0:
            self.summary_lbl.setText(_t("panel.problems.empty"))
            return
        self.summary_lbl.setText(_t("panel.problems.summary").format(
            e=c["error"], w=c["warning"], i=c["info"]))

    def _on_double_click(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid() or self._navigate is None:
            return
        src = self.proxy.mapToSource(proxy_index)
        space_id = self.model.space_id_at(src.row())
        if space_id:
            self._navigate(space_id)

    # ---- Локализация ----
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.problems.title"))
        self.refresh_btn.setText(_t("btn.refresh"))
        self.summary_card.set_title(_t("panel.problems.title"))
        self.summary_card.set_subtitle(_t("panel.problems.hint"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.model.columnCount() - 1)
        self._refresh()
