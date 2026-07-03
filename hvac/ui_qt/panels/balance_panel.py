# -*- coding: utf-8 -*-
"""BalancePanel — раздел «Тепловой баланс».

Ручная сводка установленной мощности по зданию. Пользователь вручную
отмечает, какие помещения отапливаются и какие охлаждаются (галочки в
таблице или массово по выделению), а панель суммирует:

    Отопление = Σ теплопотерь отмеченных помещений + Σ калориферов AHU
    Холод     = Σ теплопоступлений отмеченных помещений + Σ охладителей AHU

Колонки «Возд.» (О/Х) показывают помещения с воздушным отоплением/
охлаждением: их нагрузка уже заложена в калорифер/охладитель приточной
установки, поэтому при ручной сортировке такие помещения обычно снимают
с галочки «Отапл./Охл.» (чтобы не задвоить). Кнопка «Авто» расставляет
галочки по нагрузке именно с таким правилом.

Нагрузки приточных установок берутся из `project.ahu_loads` (их считает
раздел «Системы и оборудование» / кнопка «Посчитать AHU» здесь же). Панель
ничего не пересчитывает в физике — только агрегирует готовые поля.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from hvac.air_heating import apply_air_heating
from hvac.catalogs.room_types import is_non_cooled_type, is_non_heated_type
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.zones_panel import _NumTableItem


# Колонки таблицы помещений и индексы галочек.
_COL_NUMBER, _COL_LEVEL, _COL_NAME, _COL_AREA, _COL_AIR = 0, 1, 2, 3, 4
_COL_QH, _COL_HEATED, _COL_QC, _COL_COOLED = 5, 6, 7, 8
_COL_COUNT = 9


def _level_num(level: str) -> float:
    """Числовой ключ этажа из строки уровня («L12» → 12, «-1» → -1)."""
    m = re.search(r"-?\d+", level or "")
    return float(m.group()) if m else 1e9


def _air_marker(sp) -> str:
    """Компактная пометка воздушного режима помещения («О» / «Х» / «О·Х»)."""
    marks = []
    if getattr(sp, "air_heating", False):
        marks.append(_t("panel.sysworkspace.air.mark_heat"))
    if getattr(sp, "air_cooling", False):
        marks.append(_t("panel.sysworkspace.air.mark_cool"))
    return "·".join(marks)


class BalancePanel(QWidget):
    """Сводный тепловой баланс с ручной сортировкой помещений."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._loading = False     # гасит itemChanged во время перестройки таблицы

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ---------- заголовок ----------
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.balance.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.auto_btn = QPushButton(_t("panel.balance.btn.auto"))
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        self.auto_btn.clicked.connect(self._auto_classify)
        head.addWidget(self.auto_btn)
        self.compute_btn = QPushButton(_t("panel.balance.btn.compute"))
        self.compute_btn.setProperty("role", "primary")
        self.compute_btn.setCursor(Qt.PointingHandCursor)
        self.compute_btn.clicked.connect(self._compute_ahu)
        head.addWidget(self.compute_btn)
        outer.addLayout(head)

        self.hint_lbl = QLabel(_t("panel.balance.hint"))
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setWordWrap(True)
        outer.addWidget(self.hint_lbl)

        # ---------- фильтры + массовые операции ----------
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._filter())
        bar.addWidget(self.search, stretch=1)

        self._level_lbl = QLabel(_t("panel.spaces.filter.level"))
        bar.addWidget(self._level_lbl)
        self.level_filter = QComboBox()
        self.level_filter.setMinimumWidth(90)
        self.level_filter.currentTextChanged.connect(lambda *_: self._filter())
        bar.addWidget(self.level_filter)

        bar.addSpacing(12)
        self.heat_on_btn = QPushButton(_t("panel.balance.btn.heat_on"))
        self.heat_on_btn.clicked.connect(
            lambda: self._bulk_set(heated=True))
        bar.addWidget(self.heat_on_btn)
        self.heat_off_btn = QPushButton(_t("panel.balance.btn.heat_off"))
        self.heat_off_btn.clicked.connect(
            lambda: self._bulk_set(heated=False))
        bar.addWidget(self.heat_off_btn)
        self.cool_on_btn = QPushButton(_t("panel.balance.btn.cool_on"))
        self.cool_on_btn.clicked.connect(
            lambda: self._bulk_set(cooled=True))
        bar.addWidget(self.cool_on_btn)
        self.cool_off_btn = QPushButton(_t("panel.balance.btn.cool_off"))
        self.cool_off_btn.clicked.connect(
            lambda: self._bulk_set(cooled=False))
        bar.addWidget(self.cool_off_btn)
        outer.addLayout(bar)

        # ---------- splitter: таблица помещений / низ ----------
        splitter = QSplitter(Qt.Vertical)
        outer.addWidget(splitter, stretch=1)

        self.table = QTableWidget(0, _COL_COUNT)
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemChanged.connect(self._on_item_changed)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        for i, w in enumerate([64, 60, 220, 70, 56, 96, 70, 96, 70]):
            self.table.setColumnWidth(i, w)
        splitter.addWidget(self.table)

        # низ: таблица AHU + карточка итога
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)

        ahu_box = QWidget()
        ahu_l = QVBoxLayout(ahu_box)
        ahu_l.setContentsMargins(0, 0, 0, 0)
        self.ahu_title = QLabel(_t("panel.balance.ahu.title"))
        self.ahu_title.setProperty("role", "h2")
        ahu_l.addWidget(self.ahu_title)
        self.ahu_table = QTableWidget(0, 5)
        self.ahu_table.setHorizontalHeaderLabels(self._ahu_headers())
        self.ahu_table.setAlternatingRowColors(True)
        self.ahu_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ahu_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.ahu_table.verticalHeader().setVisible(False)
        self.ahu_table.verticalHeader().setDefaultSectionSize(24)
        self.ahu_table.horizontalHeader().setStretchLastSection(True)
        self.ahu_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        ahu_l.addWidget(self.ahu_table)
        bl.addWidget(ahu_box, stretch=3)

        bl.addWidget(self._build_totals_card(), stretch=2)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.ahuLoadsCalculated, bridge.zonesChanged,
                    bridge.equipmentChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ================= построение карточки итога =================
    def _build_totals_card(self) -> QWidget:
        card = QFrame()
        card.setProperty("role", "card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self.totals_title = QLabel(_t("panel.balance.totals.title"))
        self.totals_title.setProperty("role", "h2")
        lay.addWidget(self.totals_title)

        # Отопление
        self.heat_head = QLabel(_t("panel.balance.totals.heating"))
        self.heat_head.setProperty("role", "muted")
        lay.addWidget(self.heat_head)
        self.heat_rooms_lbl = QLabel("—")
        self.heat_ahu_lbl = QLabel("—")
        lay.addWidget(self.heat_rooms_lbl)
        lay.addWidget(self.heat_ahu_lbl)
        self.heat_total_lbl = QLabel("—")
        f = self.heat_total_lbl.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self.heat_total_lbl.setFont(f)
        lay.addWidget(self.heat_total_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setProperty("role", "muted")
        lay.addWidget(line)

        # Холод
        self.cool_head = QLabel(_t("panel.balance.totals.cooling"))
        self.cool_head.setProperty("role", "muted")
        lay.addWidget(self.cool_head)
        self.cool_rooms_lbl = QLabel("—")
        self.cool_ahu_lbl = QLabel("—")
        lay.addWidget(self.cool_rooms_lbl)
        lay.addWidget(self.cool_ahu_lbl)
        self.cool_total_lbl = QLabel("—")
        self.cool_total_lbl.setFont(f)
        lay.addWidget(self.cool_total_lbl)

        lay.addStretch(1)
        return card

    # ================= helpers =================
    def _room_headers(self) -> list[str]:
        return [
            _t("panel.zones.rcol.number"), _t("panel.zones.rcol.level"),
            _t("panel.zones.rcol.name"), _t("panel.zones.rcol.area"),
            _t("panel.sysworkspace.rcol.air"), _t("panel.balance.col.qh"),
            _t("panel.balance.col.heated"), _t("panel.balance.col.qc"),
            _t("panel.balance.col.cooled"),
        ]

    def _ahu_headers(self) -> list[str]:
        return [
            _t("panel.balance.ahu.name"), _t("panel.balance.ahu.spaces"),
            _t("panel.balance.ahu.flow"), _t("panel.balance.ahu.heater"),
            _t("panel.balance.ahu.cooler"),
        ]

    def _visible_selected_rows(self) -> list[int]:
        """Видимые выделенные строки (скрытые фильтром не трогаем)."""
        sel = self.table.selectionModel()
        if not sel:
            return []
        return sorted({i.row() for i in sel.selectedRows()
                       if not self.table.isRowHidden(i.row())})

    def _space_at(self, row: int):
        it = self.table.item(row, _COL_NUMBER)
        if it is None:
            return None
        return self.project._space_by_id.get(it.data(Qt.UserRole))

    def _check_item(self, checked: bool) -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setTextAlignment(Qt.AlignCenter)
        it.setFlags((Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                     | Qt.ItemIsSelectable))
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return it

    # ================= массовые операции =================
    def _bulk_set(self, heated: Optional[bool] = None,
                  cooled: Optional[bool] = None) -> None:
        rows = self._visible_selected_rows()
        if not rows:
            self.bridge.statusMessage.emit(
                _t("panel.balance.status.no_selection"), 3000)
            return
        for r in rows:
            sp = self._space_at(r)
            if sp is None:
                continue
            if heated is not None:
                sp.is_heated = heated
            if cooled is not None:
                sp.is_cooled = cooled
        self.bridge.dirtyChanged.emit(True)
        self._refresh_table()      # перерисовать галочки + пересчитать итог
        self.bridge.statusMessage.emit(
            _t("panel.balance.status.bulk").format(n=len(rows)), 3000)

    def _auto_classify(self) -> None:
        """Расставляет галочки по нагрузке: помещение отапливается, если есть
        теплопотери и оно НЕ на воздушном отоплении (его нагрузку несёт AHU);
        аналогично для охлаждения.

        Помещения, неотапливаемые/неохлаждаемые по своей природе (лифтовые
        шахты, паркинг, балконы/террасы, венткамеры/техпомещения, а для
        отопления ещё и холодильные камеры — room_types.is_non_heated_type /
        is_non_cooled_type), исключаются соответственно из отопления/охлаждения
        даже при посчитанных теплопотерях/теплопоступлениях через наружные
        стены."""
        if not self.project.spaces:
            return
        n = 0
        for sp in self.project.spaces:
            sp.is_heated = (sp.heat_loss_w > 0
                            and not getattr(sp, "air_heating", False)
                            and not is_non_heated_type(sp.room_type))
            sp.is_cooled = (sp.heat_gain_w > 0
                            and not getattr(sp, "air_cooling", False)
                            and not is_non_cooled_type(sp.room_type))
            n += 1
        self.bridge.dirtyChanged.emit(True)
        self._refresh_table()
        self.bridge.statusMessage.emit(
            _t("panel.balance.status.auto").format(n=n), 4000)

    def _compute_ahu(self) -> None:
        """Поднимает расход приточки по нагрузке и пересчитывает нагрузки AHU."""
        apply_air_heating(self.project)
        try:
            self.project.calculate_ahu_loads()   # эмитит ahu_loads_calculated → _refresh
        except Exception:
            import logging
            logging.getLogger(__name__).exception("balance: AHU loads failed")
            self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.balance.status.computed"), 4000)

    # ================= реакция на галочки =================
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        col = item.column()
        if col not in (_COL_HEATED, _COL_COOLED):
            return
        sp = self._space_at(item.row())
        if sp is None:
            return
        checked = item.checkState() == Qt.Checked
        if col == _COL_HEATED:
            sp.is_heated = checked
        else:
            sp.is_cooled = checked
        self.bridge.dirtyChanged.emit(True)
        self._update_totals()

    def _show_context_menu(self, pos) -> None:
        if not self._visible_selected_rows():
            return
        menu = QMenu(self)
        menu.addAction(_t("panel.balance.btn.heat_on"),
                       lambda: self._bulk_set(heated=True))
        menu.addAction(_t("panel.balance.btn.heat_off"),
                       lambda: self._bulk_set(heated=False))
        menu.addSeparator()
        menu.addAction(_t("panel.balance.btn.cool_on"),
                       lambda: self._bulk_set(cooled=True))
        menu.addAction(_t("panel.balance.btn.cool_off"),
                       lambda: self._bulk_set(cooled=False))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ================= отрисовка =================
    def _refresh(self, *args: Any) -> None:
        self._refresh_table()
        self._refresh_ahu_table()
        self._update_totals()

    def _refresh_table(self) -> None:
        self._loading = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            num = QTableWidgetItem(sp.number)
            num.setData(Qt.UserRole, sp.space_id)
            self.table.setItem(r, _COL_NUMBER, num)
            self.table.setItem(r, _COL_LEVEL,
                               _NumTableItem(sp.level or "", _level_num(sp.level)))
            self.table.setItem(r, _COL_NAME, QTableWidgetItem(sp.name))
            ar = _NumTableItem(f"{sp.area_m2:.0f}", sp.area_m2)
            ar.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, _COL_AREA, ar)
            air = QTableWidgetItem(_air_marker(sp))
            air.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, _COL_AIR, air)

            qh = sp.heat_loss_w / 1000.0
            qh_it = _NumTableItem(f"{qh:.2f}" if qh else "", qh)
            qh_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, _COL_QH, qh_it)
            self.table.setItem(r, _COL_HEATED,
                               self._check_item(bool(sp.is_heated)))

            qc = sp.heat_gain_w / 1000.0
            qc_it = _NumTableItem(f"{qc:.2f}" if qc else "", qc)
            qc_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, _COL_QC, qc_it)
            self.table.setItem(r, _COL_COOLED,
                               self._check_item(bool(sp.is_cooled)))
        self.table.setSortingEnabled(True)
        self._loading = False
        self._refresh_level_options()
        self._filter()
        self._update_totals()

    def _refresh_level_options(self) -> None:
        levels = sorted({s.level for s in self.project.spaces if s.level},
                        key=_level_num)
        all_label = _t("filter.all")
        current = self.level_filter.currentText() or all_label
        self.level_filter.blockSignals(True)
        self.level_filter.clear()
        self.level_filter.addItem(all_label)
        self.level_filter.addItems(levels)
        idx = self.level_filter.findText(current)
        self.level_filter.setCurrentIndex(max(0, idx))
        self.level_filter.blockSignals(False)

    def _refresh_ahu_table(self) -> None:
        loads = self.project.ahu_loads or {}
        self.ahu_table.setRowCount(len(loads))
        for r, (name, info) in enumerate(sorted(loads.items())):
            self.ahu_table.setItem(r, 0, QTableWidgetItem(name))
            n_it = _NumTableItem(str(info.get("n_spaces", 0)),
                                 info.get("n_spaces", 0))
            n_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.ahu_table.setItem(r, 1, n_it)
            flow = info.get("supply_m3h", 0.0)
            fl_it = _NumTableItem(f"{flow:.0f}", flow)
            fl_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.ahu_table.setItem(r, 2, fl_it)
            qh = info.get("q_heater_w", 0.0) / 1000.0
            qh_it = _NumTableItem(f"{qh:.1f}" if qh else "—", qh)
            qh_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.ahu_table.setItem(r, 3, qh_it)
            qc = info.get("q_cooler_total_w", 0.0) / 1000.0
            qc_it = _NumTableItem(f"{qc:.1f}" if qc else "—", qc)
            qc_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.ahu_table.setItem(r, 4, qc_it)

    def _update_totals(self) -> None:
        rooms_heat = sum(sp.heat_loss_w for sp in self.project.spaces
                         if sp.is_heated) / 1000.0
        rooms_cool = sum(sp.heat_gain_w for sp in self.project.spaces
                         if sp.is_cooled) / 1000.0
        loads = self.project.ahu_loads or {}
        ahu_heat = sum(i.get("q_heater_w", 0.0) for i in loads.values()) / 1000.0
        ahu_cool = sum(i.get("q_cooler_total_w", 0.0)
                       for i in loads.values()) / 1000.0

        n_heat = sum(1 for sp in self.project.spaces if sp.is_heated)
        n_cool = sum(1 for sp in self.project.spaces if sp.is_cooled)

        self.heat_rooms_lbl.setText(_t("panel.balance.totals.rooms").format(
            q=f"{rooms_heat:.1f}", n=n_heat))
        self.heat_ahu_lbl.setText(_t("panel.balance.totals.ahu").format(
            q=f"{ahu_heat:.1f}", n=len(loads)))
        self.heat_total_lbl.setText(_t("panel.balance.totals.total").format(
            q=f"{rooms_heat + ahu_heat:.1f}"))

        self.cool_rooms_lbl.setText(_t("panel.balance.totals.rooms").format(
            q=f"{rooms_cool:.1f}", n=n_cool))
        self.cool_ahu_lbl.setText(_t("panel.balance.totals.ahu").format(
            q=f"{ahu_cool:.1f}", n=len(loads)))
        self.cool_total_lbl.setText(_t("panel.balance.totals.total").format(
            q=f"{rooms_cool + ahu_cool:.1f}"))

    def _filter(self) -> None:
        text = self.search.text().lower().strip()
        all_label = _t("filter.all")
        lvl = self.level_filter.currentText()
        lvl = "" if lvl == all_label else lvl
        for r in range(self.table.rowCount()):
            visible = True
            sp = self._space_at(r)
            if sp is not None and lvl and (sp.level or "") != lvl:
                visible = False
            if visible and text:
                row_text = " ".join(
                    (cell.text() if (cell := self.table.item(r, c)) is not None
                     else "")
                    for c in range(_COL_AIR + 1)).lower()
                visible = text in row_text
            self.table.setRowHidden(r, not visible)

    # ================= локализация =================
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.balance.title"))
        self.auto_btn.setText(_t("panel.balance.btn.auto"))
        self.compute_btn.setText(_t("panel.balance.btn.compute"))
        self.hint_lbl.setText(_t("panel.balance.hint"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self._level_lbl.setText(_t("panel.spaces.filter.level"))
        self.heat_on_btn.setText(_t("panel.balance.btn.heat_on"))
        self.heat_off_btn.setText(_t("panel.balance.btn.heat_off"))
        self.cool_on_btn.setText(_t("panel.balance.btn.cool_on"))
        self.cool_off_btn.setText(_t("panel.balance.btn.cool_off"))
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self.ahu_title.setText(_t("panel.balance.ahu.title"))
        self.ahu_table.setHorizontalHeaderLabels(self._ahu_headers())
        self.totals_title.setText(_t("panel.balance.totals.title"))
        self.heat_head.setText(_t("panel.balance.totals.heating"))
        self.cool_head.setText(_t("panel.balance.totals.cooling"))
        self._refresh()
