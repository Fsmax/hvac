# -*- coding: utf-8 -*-
"""AirBalancePanel — раздел «Баланс воздуха».

Наглядная балансировка приточно-вытяжного воздуха по этажам (или по
системам). Дерево: группа (этаж / система) → помещения. На строке группы —
суммы и баланс с цветовой подсветкой дисбаланса; в строках-помещениях
редактируются расходы (Приток / Вытяжка / Зонт) прямо здесь.

    Удаление = Вытяжка + Зонт
    Баланс   = Приток − Удаление        (+ подпор / − разрежение)
    Дисбаланс % = |Баланс| / max(Приток, Удаление)

Правка расхода ставит `vent_user_modified=True` и пересчитывает
`ach_calculated` (как раздел «Вентиляция»), поэтому «Пересчитать» её не
затрёт. Физику панель не считает — только агрегирует и правит расходы.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QStyledItemDelegate, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge

# Колонки дерева.
COL_NODE, COL_SUP, COL_EXH, COL_HOOD, COL_EXTRACT, COL_BAL, COL_PCT = range(7)
COL_COUNT = 7
_EDIT_COLS = {COL_SUP: "supply_m3h", COL_EXH: "exhaust_m3h", COL_HOOD: "hood_m3h"}

# Пороги дисбаланса (доля) и цвета (читаемы в тёмной и светлой теме).
_OK, _WARN = 0.05, 0.15
_C_OK = QColor("#3BA55D")
_C_WARN = QColor("#D99A00")
_C_BAD = QColor("#E25C5C")


def _level_num(level: str) -> float:
    m = re.search(r"-?\d+", level or "")
    return float(m.group()) if m else 1e9


def _block_of_sp(sp) -> str:
    """Блок помещения: назначенный/канонический (hvac.blocks)."""
    from hvac.blocks import block_of
    return block_of(sp)


def _bal_color(supply: float, extract: float) -> QColor:
    denom = max(supply, extract, 1.0)
    r = abs(supply - extract) / denom
    return _C_OK if r <= _OK else (_C_WARN if r <= _WARN else _C_BAD)


class _FlowDelegate(QStyledItemDelegate):
    """Редактор только для расходов (кол. Приток/Вытяжка/Зонт) у помещений."""

    def createEditor(self, parent, option, index):
        if index.column() not in _EDIT_COLS or not index.parent().isValid():
            return None
        ed = QLineEdit(parent)
        ed.setValidator(QDoubleValidator(0.0, 1e7, 0, ed))
        return ed


class AirBalancePanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._loading = False
        self._group_mode = "level"          # 'level' | 'system'

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ---------- заголовок + переключатель пивота ----------
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.airbalance.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addSpacing(16)
        self._mode_group = QButtonGroup(self)
        for key, tkey in (("level", "panel.airbalance.group.level"),
                          ("system", "panel.airbalance.group.system")):
            b = QPushButton(_t(tkey))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == self._group_mode)
            b.clicked.connect(lambda _c=False, k=key: self._set_mode(k))
            self._mode_group.addButton(b)
            head.addWidget(b)
            setattr(self, f"_mode_btn_{key}", b)
        head.addStretch(1)
        self.expand_btn = QPushButton(_t("panel.airbalance.btn.expand"))
        self.expand_btn.clicked.connect(self._expand_all)
        head.addWidget(self.expand_btn)
        self.collapse_btn = QPushButton(_t("panel.airbalance.btn.collapse"))
        self.collapse_btn.clicked.connect(self._collapse_all)
        head.addWidget(self.collapse_btn)
        outer.addLayout(head)

        self.hint_lbl = QLabel(_t("panel.airbalance.hint"))
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setWordWrap(True)
        outer.addWidget(self.hint_lbl)

        # ---------- фильтры ----------
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._rebuild())
        bar.addWidget(self.search, stretch=1)
        self._sys_lbl = QLabel(_t("panel.airbalance.filter.system"))
        bar.addWidget(self._sys_lbl)
        self.sys_filter = QComboBox()
        self.sys_filter.setMinimumWidth(150)
        self.sys_filter.currentTextChanged.connect(lambda *_: self._rebuild())
        bar.addWidget(self.sys_filter)
        self._blk_lbl = QLabel(_t("panel.airbalance.filter.block"))
        bar.addWidget(self._blk_lbl)
        self.block_filter = QComboBox()
        self.block_filter.setMinimumWidth(90)
        self.block_filter.currentTextChanged.connect(lambda *_: self._rebuild())
        bar.addWidget(self.block_filter)
        outer.addLayout(bar)

        # ---------- дерево ----------
        self.tree = QTreeWidget()
        self.tree.setColumnCount(COL_COUNT)
        self.tree.setHeaderLabels(self._headers())
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.tree.setItemDelegate(_FlowDelegate(self.tree))
        self.tree.itemChanged.connect(self._on_item_changed)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(COL_NODE, QHeaderView.Stretch)
        for c in range(1, COL_COUNT):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(COL_NODE, 240)
        outer.addWidget(self.tree, stretch=1)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "h2")
        outer.addWidget(self.summary_lbl)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.ahuLoadsCalculated, bridge.zonesChanged,
                    bridge.equipmentChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ================= helpers =================
    def _headers(self) -> list[str]:
        return [_t(k) for k in (
            "panel.airbalance.col.node", "panel.airbalance.col.supply",
            "panel.airbalance.col.exhaust", "panel.airbalance.col.hood",
            "panel.airbalance.col.extract", "panel.airbalance.col.balance",
            "panel.airbalance.col.pct")]

    def _group_key(self, sp) -> str:
        if self._group_mode == "system":
            return getattr(sp, "system_ventilation", "") or _t("panel.airbalance.none")
        return sp.level or "—"

    def _filtered_spaces(self) -> list:
        text = self.search.text().lower().strip()
        all_lbl = _t("filter.all")
        sysf = self.sys_filter.currentText()
        sysf = "" if sysf == all_lbl else sysf
        blkf = self.block_filter.currentText()
        blkf = "" if blkf == all_lbl else blkf
        out = []
        for sp in self.project.spaces:
            if sysf and (getattr(sp, "system_ventilation", "") or "") != sysf:
                continue
            if blkf and _block_of_sp(sp) != blkf:
                continue
            if text and text not in (
                    f"{sp.number} {sp.name} {sp.level or ''} "
                    f"{getattr(sp, 'system_ventilation', '') or ''}").lower():
                continue
            out.append(sp)
        return out

    # ================= наполнение =================
    def _refresh(self) -> None:
        self._reload_filters()
        self._rebuild()

    def _reload_filters(self) -> None:
        all_lbl = _t("filter.all")
        systems = sorted({getattr(s, "system_ventilation", "") for s in
                          self.project.spaces if getattr(s, "system_ventilation", "")})
        from hvac.blocks import blocks_in_project
        blocks = blocks_in_project(self.project)
        for combo, items in ((self.sys_filter, systems),
                             (self.block_filter, blocks)):
            cur = combo.currentText() or all_lbl
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_lbl)
            combo.addItems(items)
            i = combo.findText(cur)
            combo.setCurrentIndex(max(0, i))
            combo.blockSignals(False)

    def _rebuild(self) -> None:
        self._loading = True
        self.tree.clear()
        groups: dict[str, list] = {}
        for sp in self._filtered_spaces():
            groups.setdefault(self._group_key(sp), []).append(sp)

        key = (_level_num if self._group_mode == "level" else (lambda s: s))
        for gname in sorted(groups, key=key):
            rooms = groups[gname]
            top = QTreeWidgetItem([gname])
            f = top.font(COL_NODE)
            f.setBold(True)
            top.setFont(COL_NODE, f)
            self.tree.addTopLevelItem(top)
            for sp in sorted(rooms, key=lambda x: x.number):
                child = QTreeWidgetItem(top)
                child.setData(COL_NODE, Qt.UserRole, sp)
                child.setFlags(child.flags() | Qt.ItemIsEditable)
                self._fill_room_item(child, sp)
            self._recompute_group_item(top)
            top.setExpanded(self._group_mode == "level"
                            and len(groups) <= 8)
        self._loading = False
        self._update_summary()

    def _fill_room_item(self, item: QTreeWidgetItem, sp) -> None:
        extract = (sp.exhaust_m3h or 0) + (sp.hood_m3h or 0)
        bal = (sp.supply_m3h or 0) - extract
        item.setText(COL_NODE, f"{sp.number}  {sp.name}")
        item.setText(COL_SUP, f"{sp.supply_m3h:.0f}" if sp.supply_m3h else "")
        item.setText(COL_EXH, f"{sp.exhaust_m3h:.0f}" if sp.exhaust_m3h else "")
        item.setText(COL_HOOD, f"{sp.hood_m3h:.0f}" if sp.hood_m3h else "")
        item.setText(COL_EXTRACT, f"{extract:.0f}" if extract else "")
        item.setText(COL_BAL, f"{bal:+.0f}" if (sp.supply_m3h or extract) else "")
        item.setText(COL_PCT, "")
        for c in (COL_SUP, COL_EXH, COL_HOOD, COL_EXTRACT, COL_BAL):
            item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        if sp.supply_m3h or extract:
            item.setForeground(COL_BAL, QBrush(_bal_color(sp.supply_m3h or 0, extract)))

    def _recompute_group_item(self, top: QTreeWidgetItem) -> None:
        sup = exh = hood = 0.0
        for i in range(top.childCount()):
            sp = top.child(i).data(COL_NODE, Qt.UserRole)
            if sp is None:
                continue
            sup += sp.supply_m3h or 0
            exh += sp.exhaust_m3h or 0
            hood += sp.hood_m3h or 0
        extract = exh + hood
        bal = sup - extract
        denom = max(sup, extract, 1.0)
        pct = abs(bal) / denom * 100
        base = top.text(COL_NODE).split("  (")[0]
        top.setText(COL_NODE, f"{base}  ({top.childCount()})")
        top.setText(COL_SUP, f"{sup:.0f}")
        top.setText(COL_EXH, f"{exh:.0f}")
        top.setText(COL_HOOD, f"{hood:.0f}" if hood else "")
        top.setText(COL_EXTRACT, f"{extract:.0f}")
        top.setText(COL_BAL, f"{bal:+.0f}")
        top.setText(COL_PCT, f"{pct:.0f}%")
        col = _bal_color(sup, extract)
        for c in (COL_SUP, COL_EXH, COL_HOOD, COL_EXTRACT, COL_BAL, COL_PCT):
            top.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        top.setForeground(COL_BAL, QBrush(col))
        top.setForeground(COL_PCT, QBrush(col))

    def _update_summary(self) -> None:
        sup = sum(s.supply_m3h or 0 for s in self.project.spaces)
        exh = sum(s.exhaust_m3h or 0 for s in self.project.spaces)
        hood = sum(s.hood_m3h or 0 for s in self.project.spaces)
        extract = exh + hood
        bal = sup - extract
        denom = max(sup, extract, 1.0)
        self.summary_lbl.setText(_t("panel.airbalance.summary").format(
            sup=f"{sup:,.0f}".replace(",", " "),
            ext=f"{extract:,.0f}".replace(",", " "),
            bal=f"{bal:+,.0f}".replace(",", " "),
            pct=f"{abs(bal) / denom * 100:.1f}"))

    # ================= правка =================
    def _on_item_changed(self, item: QTreeWidgetItem, col: int) -> None:
        if self._loading or col not in _EDIT_COLS:
            return
        top = item.parent()
        if top is None:
            return
        sp = item.data(COL_NODE, Qt.UserRole)
        if sp is None:
            return
        raw = item.text(col).replace(" ", "").replace(",", ".")
        attr = _EDIT_COLS[col]
        try:
            v = max(float(raw), 0.0)
        except ValueError:
            v = getattr(sp, attr, 0.0)
        setattr(sp, attr, v)
        sp.vent_user_modified = True
        if sp.volume_m3 > 0:
            sp.ach_calculated = max(sp.supply_m3h, sp.exhaust_m3h) / sp.volume_m3
        self._loading = True
        self._fill_room_item(item, sp)
        self._recompute_group_item(top)
        self._loading = False
        self._update_summary()
        self.bridge.dirtyChanged.emit(True)

    # ================= домен / i18n =================
    def _expand_all(self) -> None:
        self.tree.expandAll()

    def _collapse_all(self) -> None:
        self.tree.collapseAll()

    def _set_mode(self, mode: str) -> None:
        if mode == self._group_mode:
            return
        self._group_mode = mode
        self._rebuild()

    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.airbalance.title"))
        self.hint_lbl.setText(_t("panel.airbalance.hint"))
        self._mode_btn_level.setText(_t("panel.airbalance.group.level"))
        self._mode_btn_system.setText(_t("panel.airbalance.group.system"))
        self.expand_btn.setText(_t("panel.airbalance.btn.expand"))
        self.collapse_btn.setText(_t("panel.airbalance.btn.collapse"))
        self._sys_lbl.setText(_t("panel.airbalance.filter.system"))
        self._blk_lbl.setText(_t("panel.airbalance.filter.block"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.tree.setHeaderLabels(self._headers())
        self._refresh()
