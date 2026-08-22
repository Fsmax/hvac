# -*- coding: utf-8 -*-
"""ProblemsPanel — сводный список проверок проекта (validate_detailed).

Показывает ошибки/предупреждения/инфо с категорией и сообщением. Двойной
клик по строке с привязкой к помещению переходит к нему в разделе
«Помещения». Данные берутся из HVACProject.validate_detailed().
"""
from __future__ import annotations

from typing import Any, Callable, List

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.service_coverage import (
    MISSING, NOT_REQUIRED, UNKNOWN, ServiceCoverageRow,
    build_service_coverage, coverage_issue_records,
)
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
            data = list(self.project.validate_detailed())
        except Exception:
            import traceback
            traceback.print_exc()
            data = []
        try:
            data.extend(coverage_issue_records(self.project))
        except Exception:
            import traceback
            traceback.print_exc()
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


class CoverageModel(QAbstractTableModel):
    """Матрица назначения инженерных систем по каждому помещению."""

    _COL_KEYS = [
        "panel.coverage.col.number", "panel.coverage.col.name",
        "panel.coverage.col.level", "panel.coverage.col.heating",
        "panel.coverage.col.cooling", "panel.coverage.col.ventilation",
        "panel.coverage.col.smoke", "panel.coverage.col.status",
    ]

    def __init__(self, project: HVACProject):
        super().__init__()
        self.project = project
        self._rows: list[ServiceCoverageRow] = []

    def refresh(self) -> None:
        self.beginResetModel()
        try:
            self._rows = build_service_coverage(self.project)
        except Exception:
            import traceback
            traceback.print_exc()
            self._rows = []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._COL_KEYS)

    def headerData(self, section, orient, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orient == Qt.Horizontal:
            return _t(self._COL_KEYS[section])
        return None

    @staticmethod
    def _system_text(state: str, name: str, via_air: bool = False) -> str:
        if state == NOT_REQUIRED:
            return _t("panel.coverage.not_required")
        if state == MISSING:
            return _t("panel.coverage.not_assigned")
        if state == UNKNOWN:
            return _t("panel.coverage.unknown_system").format(
                name=name or "—")
        if via_air:
            return _t("panel.coverage.air_prefix").format(name=name)
        return name or _t("panel.coverage.not_assigned")

    def _ventilation_text(self, row: ServiceCoverageRow) -> str:
        parts = []
        if row.supply_required:
            value = self._system_text(row.supply_state, row.supply_system)
            parts.append(_t("panel.coverage.supply").format(value=value))
        if row.exhaust_required:
            value = self._system_text(row.exhaust_state, row.exhaust_system)
            parts.append(_t("panel.coverage.exhaust").format(value=value))
        return "; ".join(parts) if parts else _t("panel.coverage.no_flow")

    def _display_value(self, row: ServiceCoverageRow, col: int) -> str:
        if col == 0:
            return row.number
        if col == 1:
            return row.name
        if col == 2:
            return row.level
        if col == 3:
            return self._system_text(
                row.heating_state, row.heating_system, row.heating_via_air)
        if col == 4:
            return self._system_text(
                row.cooling_state, row.cooling_system, row.cooling_via_air)
        if col == 5:
            return self._ventilation_text(row)
        if col == 6:
            if row.smoke_state == UNKNOWN:
                return self._system_text(UNKNOWN, ", ".join(row.smoke_systems))
            if row.smoke_systems:
                return ", ".join(row.smoke_systems)
            return _t("panel.coverage.not_required")
        if col == 7:
            key = ("panel.coverage.problem" if row.has_blockers
                   else "panel.coverage.ready")
            return _t(key)
        return ""

    @staticmethod
    def _column_has_blocker(row: ServiceCoverageRow, col: int) -> bool:
        bad = (MISSING, UNKNOWN)
        if col == 3:
            return row.heating_state in bad
        if col == 4:
            return row.cooling_state in bad
        if col == 5:
            return row.supply_state in bad or row.exhaust_state in bad
        if col == 6:
            return row.smoke_state == UNKNOWN
        if col == 7:
            return row.has_blockers
        return False

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return self._display_value(row, col)
        if role == Qt.ForegroundRole:
            if self._column_has_blocker(row, col):
                return QBrush(QColor(tokens()["danger"]))
            if col == 7:
                return QBrush(QColor(tokens()["success"]))
            if ((col == 3 and row.heating_state == NOT_REQUIRED)
                    or (col == 4 and row.cooling_state == NOT_REQUIRED)
                    or (col == 5 and not row.supply_required
                        and not row.exhaust_required)
                    or (col == 6 and row.smoke_state == NOT_REQUIRED)):
                return QBrush(QColor(tokens()["text_muted"]))
        return None

    def space_id_at(self, row: int) -> str:
        if 0 <= row < len(self._rows):
            return self._rows[row].space_id
        return ""

    def has_blockers_at(self, row: int) -> bool:
        return 0 <= row < len(self._rows) and self._rows[row].has_blockers

    def counts(self) -> dict[str, int]:
        missing = sum(row.has_blockers for row in self._rows)
        total = len(self._rows)
        return {"total": total, "missing": missing, "ready": total - missing}


class CoverageFilterProxy(QSortFilterProxyModel):
    """Поиск по всем столбцам плюс фильтр только проблемных помещений."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._missing_only = False

    def set_missing_only(self, enabled: bool) -> None:
        self._missing_only = bool(enabled)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex
                         ) -> bool:
        model = self.sourceModel()
        if (self._missing_only and isinstance(model, CoverageModel)
                and not model.has_blockers_at(source_row)):
            return False
        return super().filterAcceptsRow(source_row, source_parent)


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

        self.tabs = QTabWidget()

        issues_tab = QWidget()
        issues_layout = QVBoxLayout(issues_tab)
        issues_layout.setContentsMargins(0, 10, 0, 0)
        issues_layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        issues_layout.addWidget(self.search)

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
        issues_layout.addWidget(self.table, stretch=1)
        self.tabs.addTab(issues_tab, _t("panel.problems.tab.issues"))

        coverage_tab = QWidget()
        coverage_layout = QVBoxLayout(coverage_tab)
        coverage_layout.setContentsMargins(0, 10, 0, 0)
        coverage_layout.setSpacing(8)

        coverage_head = QHBoxLayout()
        self.coverage_summary_lbl = QLabel()
        self.coverage_summary_lbl.setProperty("role", "muted")
        coverage_head.addWidget(self.coverage_summary_lbl)
        coverage_head.addStretch(1)
        self.coverage_missing_only = QCheckBox(
            _t("panel.coverage.only_missing"))
        coverage_head.addWidget(self.coverage_missing_only)
        coverage_layout.addLayout(coverage_head)

        self.coverage_search = QLineEdit()
        self.coverage_search.setPlaceholderText(_t("panel.coverage.search"))
        self.coverage_search.setClearButtonEnabled(True)
        coverage_layout.addWidget(self.coverage_search)

        self.coverage_model = CoverageModel(project)
        self.coverage_proxy = CoverageFilterProxy(self)
        self.coverage_proxy.setSourceModel(self.coverage_model)
        self.coverage_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.coverage_proxy.setFilterKeyColumn(-1)
        self.coverage_search.textChanged.connect(
            self.coverage_proxy.setFilterFixedString)
        self.coverage_missing_only.toggled.connect(
            self.coverage_proxy.set_missing_only)

        self.coverage_table = QTableView()
        self.coverage_table.setModel(self.coverage_proxy)
        self.coverage_table.setSortingEnabled(True)
        self.coverage_table.setAlternatingRowColors(True)
        self.coverage_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.coverage_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.coverage_table.verticalHeader().setVisible(False)
        self.coverage_table.verticalHeader().setDefaultSectionSize(26)
        self.coverage_table.horizontalHeader().setHighlightSections(False)
        self.coverage_table.horizontalHeader().setStretchLastSection(True)
        self.coverage_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        for i, width in enumerate([90, 220, 130, 220, 220, 360, 220, 190]):
            self.coverage_table.setColumnWidth(i, width)
        self.coverage_table.doubleClicked.connect(
            self._on_coverage_double_click)
        install_copy(self.coverage_table)
        coverage_layout.addWidget(self.coverage_table, stretch=1)
        self.tabs.addTab(coverage_tab, _t("panel.problems.tab.coverage"))

        outer.addWidget(self.tabs, stretch=1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.constructionsChanged, bridge.zonesChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ---- Логика ----
    def _refresh(self, *args: Any) -> None:
        self.model.refresh()
        self.coverage_model.refresh()
        coverage = self.coverage_model.counts()
        self.coverage_summary_lbl.setText(
            _t("panel.coverage.summary").format(**coverage))
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

    def _on_coverage_double_click(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid() or self._navigate is None:
            return
        src = self.coverage_proxy.mapToSource(proxy_index)
        space_id = self.coverage_model.space_id_at(src.row())
        if space_id:
            self._navigate(space_id)

    # ---- Локализация ----
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.problems.title"))
        self.refresh_btn.setText(_t("btn.refresh"))
        self.summary_card.set_title(_t("panel.problems.title"))
        self.summary_card.set_subtitle(_t("panel.problems.hint"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.tabs.setTabText(0, _t("panel.problems.tab.issues"))
        self.tabs.setTabText(1, _t("panel.problems.tab.coverage"))
        self.coverage_missing_only.setText(_t("panel.coverage.only_missing"))
        self.coverage_search.setPlaceholderText(_t("panel.coverage.search"))
        self.model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.model.columnCount() - 1)
        self.coverage_model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.coverage_model.columnCount() - 1)
        self._refresh()
