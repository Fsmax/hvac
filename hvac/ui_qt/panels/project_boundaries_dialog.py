# -*- coding: utf-8 -*-
"""ProjectBoundariesDialog — общепроектный редактор ограждений.

Плоская таблица ВСЕХ стен/проёмов всех помещений с фильтрами (этаж, тип,
ориентация, наружн./внутр., поиск) и массовой пометкой выделенных строк
внутренними/наружными. Нужен, когда Revit/Dynamo ошибочно выгрузил почти
все стены наружными: вместо обхода каждого помещения по отдельности можно
отфильтровать и пометить пачкой. После правки — пересчёт теплопотерь.

Открывается из раздела «Помещения» (кнопка «Ограждения проекта…»).
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from hvac.data_loader import is_excluded_category
from hvac.i18n import t as _t
from hvac.models import BoundaryElement
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.zones_panel import _NumTableItem


_COL_ROOM, _COL_LEVEL, _COL_CAT, _COL_AREA = 0, 1, 2, 3
_COL_ORIENT, _COL_U, _COL_EXT = 4, 5, 6
_COL_COUNT = 7

# Тип ограждения, который имеет смысл переключать (стены/проёмы);
# пол по грунту / покрытие управляются флагами помещения, не is_exterior.
_EDITABLE_ROW_TYPES = ("external_wall", "opening")


def _level_key(level: str) -> float:
    import re
    m = re.search(r"-?\d+", level or "")
    return float(m.group()) if m else 1e9


class ProjectBoundariesDialog(QDialog):
    """Общепроектная таблица ограждений с фильтрами и массовой правкой."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self.setWindowTitle(_t("dlg.projbnd.title"))
        self.setModal(False)
        self.resize(1040, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self.hint = QLabel(_t("dlg.projbnd.hint"))
        self.hint.setProperty("role", "muted")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        # ---------- фильтры ----------
        flt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._reload())
        flt.addWidget(self.search, stretch=1)

        self._lvl_lbl = QLabel(_t("panel.spaces.filter.level"))
        flt.addWidget(self._lvl_lbl)
        self.level_filter = QComboBox()
        self.level_filter.setMinimumWidth(90)
        self.level_filter.currentTextChanged.connect(lambda *_: self._reload())
        flt.addWidget(self.level_filter)

        self._cat_lbl = QLabel(_t("panel.spaces.filter.type"))
        flt.addWidget(self._cat_lbl)
        self.cat_filter = QComboBox()
        self.cat_filter.setMinimumWidth(110)
        self.cat_filter.currentTextChanged.connect(lambda *_: self._reload())
        flt.addWidget(self.cat_filter)

        self._or_lbl = QLabel(_t("dlg.projbnd.f.orient"))
        flt.addWidget(self._or_lbl)
        self.orient_filter = QComboBox()
        self.orient_filter.setMinimumWidth(70)
        self.orient_filter.currentTextChanged.connect(lambda *_: self._reload())
        flt.addWidget(self.orient_filter)

        self._ext_lbl = QLabel(_t("dlg.projbnd.f.ext"))
        flt.addWidget(self._ext_lbl)
        self.ext_filter = QComboBox()
        self.ext_filter.setMinimumWidth(110)
        self.ext_filter.currentIndexChanged.connect(lambda *_: self._reload())
        flt.addWidget(self.ext_filter)
        root.addLayout(flt)

        # ---------- таблица ----------
        self.table = QTableWidget(0, _COL_COUNT)
        self.table.setHorizontalHeaderLabels(self._headers())
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSortingEnabled(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_ROOM, QHeaderView.Stretch)
        for i, w in enumerate([220, 70, 110, 80, 70, 64, 90]):
            self.table.setColumnWidth(i, w)
        root.addWidget(self.table, stretch=1)

        # ---------- низ: счётчик + массовые кнопки ----------
        bar = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("role", "muted")
        bar.addWidget(self.count_lbl)
        bar.addStretch(1)
        self.internal_btn = QPushButton(_t("panel.boundaries.btn_internal"))
        self.internal_btn.clicked.connect(lambda: self._apply_exterior(False))
        bar.addWidget(self.internal_btn)
        self.external_btn = QPushButton(_t("panel.boundaries.btn_external"))
        self.external_btn.clicked.connect(lambda: self._apply_exterior(True))
        bar.addWidget(self.external_btn)
        self.close_btn = QPushButton(_t("btn.close"))
        self.close_btn.clicked.connect(self.accept)
        bar.addWidget(self.close_btn)
        root.addLayout(bar)

        self._refresh_filter_options()
        self._reload()

    # ================= helpers =================
    def _headers(self) -> List[str]:
        return [
            _t("dlg.projbnd.col.room"), _t("panel.zones.rcol.level"),
            _t("panel.boundaries.col.category"), _t("panel.zones.rcol.area"),
            _t("panel.boundaries.col.orient"), _t("panel.boundaries.col.u"),
            _t("panel.boundaries.col.ext"),
        ]

    def _all_elements(self) -> List[BoundaryElement]:
        return [e for e in self.project.elements
                if e.row_type in _EDITABLE_ROW_TYPES
                and not is_excluded_category(e.category)]

    def _refresh_filter_options(self) -> None:
        elems = self._all_elements()
        by_id = self.project._space_by_id
        level_set = set()
        for e in elems:
            sp = by_id.get(e.space_id)
            if sp is not None and sp.level:
                level_set.add(sp.level)
        levels = sorted(level_set, key=_level_key)
        cats = sorted({e.category for e in elems if e.category})
        orients = sorted({e.orientation for e in elems if e.orientation})
        all_label = _t("filter.all")
        specs = [
            (self.level_filter, levels),
            (self.cat_filter, cats),
            (self.orient_filter, orients),
        ]
        for combo, items in specs:
            current = combo.currentText() or all_label
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(items)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)
        # фильтр наружн/внутр — фиксированные варианты
        if self.ext_filter.count() == 0:
            self.ext_filter.blockSignals(True)
            self.ext_filter.addItem(all_label, "all")
            self.ext_filter.addItem(_t("dlg.projbnd.ext.only_ext"), "ext")
            self.ext_filter.addItem(_t("dlg.projbnd.ext.only_int"), "int")
            self.ext_filter.blockSignals(False)

    def _passes(self, e: BoundaryElement, sp, text, lvl, cat, orient,
                ext_mode) -> bool:
        if lvl and (sp.level if sp else "") != lvl:
            return False
        if cat and e.category != cat:
            return False
        if orient and (e.orientation or "") != orient:
            return False
        if ext_mode == "ext" and not e.is_exterior:
            return False
        if ext_mode == "int" and e.is_exterior:
            return False
        if text:
            hay = " ".join((
                sp.number if sp else "", sp.name if sp else "",
                e.category, e.orientation or "")).lower()
            if text not in hay:
                return False
        return True

    def _reload(self) -> None:
        all_label = _t("filter.all")
        text = self.search.text().lower().strip()
        lvl = self.level_filter.currentText()
        lvl = "" if lvl == all_label else lvl
        cat = self.cat_filter.currentText()
        cat = "" if cat == all_label else cat
        orient = self.orient_filter.currentText()
        orient = "" if orient == all_label else orient
        ext_mode = self.ext_filter.currentData() or "all"

        by_id = self.project._space_by_id
        rows = [(e, by_id.get(e.space_id)) for e in self._all_elements()]
        rows = [(e, sp) for (e, sp) in rows
                if self._passes(e, sp, text, lvl, cat, orient, ext_mode)]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        yes = _t("panel.boundaries.ext_yes")
        no = _t("panel.boundaries.ext_no")
        for r, (e, sp) in enumerate(rows):
            room = f"{sp.number} · {sp.name}" if sp else e.space_id
            it = QTableWidgetItem(room)
            it.setData(Qt.UserRole, e)        # ссылка на элемент
            self.table.setItem(r, _COL_ROOM, it)
            self.table.setItem(r, _COL_LEVEL,
                               QTableWidgetItem(sp.level if sp else ""))
            self.table.setItem(r, _COL_CAT, QTableWidgetItem(e.category))
            area = e.net_area_m2 or e.element_area_m2
            ai = _NumTableItem(f"{area:.2f}", area)
            ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, _COL_AREA, ai)
            self.table.setItem(r, _COL_ORIENT,
                               QTableWidgetItem(e.orientation or ""))
            ui = _NumTableItem(f"{e.u_value:.3f}" if e.u_value else "",
                               e.u_value)
            ui.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, _COL_U, ui)
            ext = QTableWidgetItem(yes if e.is_exterior else no)
            ext.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, _COL_EXT, ext)
        self.table.setSortingEnabled(True)
        self.count_lbl.setText(_t("dlg.projbnd.count").format(
            n=len(rows), total=len(self._all_elements())))

    def _selected_elements(self) -> List[BoundaryElement]:
        sel = self.table.selectionModel()
        if not sel:
            return []
        out = []
        for idx in sel.selectedRows():
            it = self.table.item(idx.row(), _COL_ROOM)
            e = it.data(Qt.UserRole) if it else None
            if isinstance(e, BoundaryElement):
                out.append(e)
        return out

    def _apply_exterior(self, is_exterior: bool) -> None:
        elems = self._selected_elements()
        if not elems:
            self.bridge.statusMessage.emit(
                _t("dlg.projbnd.no_selection"), 3000)
            return
        pairs = {(e.space_id, e.element_id) for e in elems}
        n = self.project.set_elements_exterior(pairs, is_exterior)
        if not n:
            self.bridge.statusMessage.emit(
                _t("panel.boundaries.status.ext_noop"), 3000)
            return
        self.project.recalculate()
        self.bridge.dirtyChanged.emit(True)
        self._reload()
        self.bridge.statusMessage.emit(
            _t("panel.boundaries.status.ext").format(n=n), 4000)
