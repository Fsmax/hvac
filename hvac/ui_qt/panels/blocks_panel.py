# -*- coding: utf-8 -*-
"""BlocksPanel — раздел «Блоки».

Рабочее место разделения проекта на блоки, РУЧНОЕ прежде всего:

    сверху  — сводка по блокам (сортируемое дерево): строка блока =
              помещения блока + итоги; дети = установки блока ЦЕЛИКОМ
              (правый клик по установке — сменить её блок вручную);
    снизу   — таблица помещений (сортировка по любой колонке, поиск,
              фильтр по блоку): выделить строки → «Назначить блок»
              (существующий / новый с любым именем / снять).

Кнопки автоопределения («1. Помещения…», «2. Системы…») — помощники,
они заполняют только пустое и не трогают ручные назначения.
Панель ничего не считает сама — агрегация в hvac/blocks.py.
"""
from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from hvac.blocks import level_sort_key
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge

# Колонки дерева сводки.
(COL_NAME, COL_ROOMS, COL_AREA, COL_QH_ROOMS, COL_QC_ROOMS,
 COL_QH_AHU, COL_QC_AHU, COL_QH_TOTAL, COL_QC_TOTAL, COL_DHW,
 COL_SUP, COL_EXH) = range(12)
COL_COUNT = 12

_COL_KEYS = (
    "panel.blocks.col.name", "panel.blocks.col.rooms", "panel.blocks.col.area",
    "panel.blocks.col.qh_rooms", "panel.blocks.col.qc_rooms",
    "panel.blocks.col.qh_ahu", "panel.blocks.col.qc_ahu",
    "panel.blocks.col.qh_total", "panel.blocks.col.qc_total",
    "panel.blocks.col.dhw",
    "panel.blocks.col.supply", "panel.blocks.col.exhaust",
)

# Колонки таблицы помещений.
(RC_NUM, RC_NAME, RC_LEVEL, RC_TYPE, RC_BLOCK, RC_AREA,
 RC_SUP, RC_EXH) = range(8)
RC_COUNT = 8

_ROOM_COL_KEYS = (
    "panel.blocks.rooms.col.number", "panel.blocks.rooms.col.name",
    "panel.blocks.rooms.col.level", "panel.blocks.rooms.col.type",
    "panel.blocks.rooms.col.block", "panel.blocks.rooms.col.area",
    "panel.blocks.rooms.col.supply", "panel.blocks.rooms.col.exhaust",
)


def _kw(w: float) -> str:
    return f"{w / 1000.0:.1f}" if w else ""


def _m3(v: float) -> str:
    return f"{v:.0f}" if v else ""


class _NumTreeItem(QTreeWidgetItem):
    """Сортировка дерева: по числу из Qt.UserRole+1, иначе по тексту."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:  # type: ignore[override]
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a = self.data(col, Qt.UserRole + 1)
        b = other.data(col, Qt.UserRole + 1)
        if a is not None and b is not None:
            return float(a) < float(b)
        return self.text(col) < other.text(col)


class _NumTableItem(QTableWidgetItem):
    """Сортировка таблицы: по числу из Qt.UserRole+1, иначе по тексту."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        a = self.data(Qt.UserRole + 1)
        b = other.data(Qt.UserRole + 1)
        if a is not None and b is not None:
            return float(a) < float(b)
        return self.text() < other.text()


def _num_item(text: str, value: float, align_right: bool = True) -> _NumTableItem:
    it = _NumTableItem(text)
    it.setData(Qt.UserRole + 1, value)
    if align_right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


class _DhwDialog(QDialog):
    """Нагрузка ГВС блока — вводится готовой цифрой (считает ВК-программа)."""

    def __init__(self, parent: QWidget, blk: str, *,
                 kw: float = 0.0, v_daily: float = 0.0):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.blocks.dlg.dhw_title").format(block=blk))
        self.setMinimumWidth(380)
        from PySide6.QtWidgets import (QDialogButtonBox, QDoubleSpinBox,
                                       QFormLayout)
        form = QFormLayout(self)
        hint = QLabel(_t("panel.blocks.dlg.dhw_hint"))
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.kw = QDoubleSpinBox()
        self.kw.setRange(0.0, 100_000.0)
        self.kw.setDecimals(0)
        self.kw.setSingleStep(10.0)
        self.kw.setValue(max(0.0, kw))
        form.addRow(_t("panel.blocks.dlg.dhw_kw"), self.kw)
        self.v_daily = QDoubleSpinBox()
        self.v_daily.setRange(0.0, 10_000.0)
        self.v_daily.setDecimals(1)
        self.v_daily.setSingleStep(1.0)
        self.v_daily.setValue(max(0.0, v_daily))
        form.addRow(_t("panel.blocks.dlg.dhw_v"), self.v_daily)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_t("btn.ok"))
        bb.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        return (self.kw.value(), self.v_daily.value())


class BlocksPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel(_t("panel.blocks.title"))
        title.setProperty("role", "h2")
        head.addWidget(title)
        head.addStretch(1)

        self.assign_btn = QPushButton(_t("panel.blocks.btn.assign_rooms"))
        self.assign_btn.clicked.connect(self._assign_rooms_auto)
        head.addWidget(self.assign_btn)

        self.assign_sys_btn = QPushButton(_t("panel.blocks.btn.assign_systems"))
        self.assign_sys_btn.clicked.connect(self._assign_systems_auto)
        head.addWidget(self.assign_sys_btn)

        self.reassign_btn = QPushButton(_t("panel.blocks.btn.reassign"))
        self.reassign_btn.clicked.connect(self._reassign)
        head.addWidget(self.reassign_btn)

        self.recalc_btn = QPushButton(_t("panel.blocks.btn.recalc_ahu"))
        self.recalc_btn.clicked.connect(self._recalc_ahu)
        head.addWidget(self.recalc_btn)
        outer.addLayout(head)

        hint = QLabel(_t("panel.blocks.hint"))
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        split = QSplitter(Qt.Vertical)
        outer.addWidget(split, stretch=1)

        # ---------- сводка по блокам ----------
        self.tree = QTreeWidget()
        self.tree.setColumnCount(COL_COUNT)
        self.tree.setHeaderLabels([_t(k) for k in _COL_KEYS])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(COL_ROOMS, Qt.DescendingOrder)
        # Явные ширины: колонка имени НЕ должна схлопываться, когда
        # числовым колонкам тесно (Stretch+ResizeToContents так делали).
        for c, w in enumerate([230, 70, 80, 105, 105, 100, 100,
                               120, 120, 90, 95, 95]):
            self.tree.setColumnWidth(c, w)
        hdr = self.tree.header()
        hdr.setMinimumSectionSize(60)
        hdr.setStretchLastSection(False)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        # двойной клик по строке блока — переименовать
        self.tree.itemDoubleClicked.connect(self._tree_double_clicked)
        split.addWidget(self.tree)

        # ---------- таблица помещений (ручное разделение) ----------
        rooms_box = QWidget()
        rl = QVBoxLayout(rooms_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        flt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("panel.spaces.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._filter_rooms())
        flt.addWidget(self.search, stretch=2)
        self._level_filter_lbl = QLabel(_t("panel.spaces.filter.level"))
        flt.addWidget(self._level_filter_lbl)
        self.level_filter = QComboBox()
        self.level_filter.setMinimumWidth(130)
        self.level_filter.currentTextChanged.connect(
            lambda *_: self._filter_rooms())
        flt.addWidget(self.level_filter)
        self._block_filter_lbl = QLabel(_t("panel.blocks.filter.block"))
        flt.addWidget(self._block_filter_lbl)
        self.block_filter = QComboBox()
        self.block_filter.setMinimumWidth(110)
        self.block_filter.currentTextChanged.connect(
            lambda *_: self._filter_rooms())
        flt.addWidget(self.block_filter)
        self.rooms_count = QLabel("")
        self.rooms_count.setProperty("role", "muted")
        flt.addWidget(self.rooms_count)
        flt.addStretch(1)

        self.new_block_btn = QPushButton(_t("panel.blocks.btn.new_block"))
        self.new_block_btn.clicked.connect(self._create_block)
        flt.addWidget(self.new_block_btn)

        self.set_block_btn = QPushButton(_t("panel.blocks.btn.set_block"))
        self.set_block_btn.setProperty("role", "primary")
        self.set_block_btn.clicked.connect(self._show_set_block_menu)
        flt.addWidget(self.set_block_btn)
        rl.addLayout(flt)

        self.table = QTableWidget(0, RC_COUNT)
        self.table.setHorizontalHeaderLabels([_t(k) for k in _ROOM_COL_KEYS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        for i, w in enumerate([90, 220, 150, 150, 70, 70, 80, 80]):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        rl.addWidget(self.table, stretch=1)
        split.addWidget(rooms_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)

        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")
        outer.addWidget(self.summary)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.zonesChanged, bridge.ahuLoadsCalculated,
                    bridge.spacesChanged):
            sig.connect(self._rebuild)
        self._rebuild()

    # ================= ручное назначение помещениям =================
    def _selected_ids(self) -> List[str]:
        sel = self.table.selectionModel()
        if not sel:
            return []
        out = []
        for idx in sel.selectedRows():
            if self.table.isRowHidden(idx.row()):
                continue          # скрытые фильтром не назначаем
            it = self.table.item(idx.row(), RC_NUM)
            if it is not None and it.data(Qt.UserRole):
                out.append(it.data(Qt.UserRole))
        return out

    def _known_blocks(self) -> List[str]:
        from hvac.blocks import blocks_in_project
        return list(blocks_in_project(self.project))

    def _show_set_block_menu(self) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, _t("panel.blocks.title"),
                                    _t("panel.zones.msg.no_selection"))
            return
        menu = QMenu(self)
        for b in self._known_blocks():
            menu.addAction(b, lambda _c=False, blk=b: self._set_rooms_block(blk))
        menu.addSeparator()
        menu.addAction(_t("panel.blocks.menu.new_block"), self._new_block)
        menu.addAction(_t("panel.blocks.menu.clear_block"),
                       lambda: self._set_rooms_block(""))
        menu.exec(self.set_block_btn.mapToGlobal(
            self.set_block_btn.rect().bottomLeft()))

    def _new_block(self) -> None:
        """Из меню назначения: новый блок + сразу назначить выделенным."""
        name, ok = QInputDialog.getText(
            self, _t("panel.blocks.title"), _t("panel.blocks.dlg.block_name"))
        if ok and name.strip():
            self.project.create_block(name.strip())
            self._set_rooms_block(name.strip())

    def _create_block(self) -> None:
        """Кнопка «➕ Блок»: создать блок (может оставаться пустым)."""
        name, ok = QInputDialog.getText(
            self, _t("panel.blocks.title"), _t("panel.blocks.dlg.block_name"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if self.project.create_block(name):
            self.bridge.dirtyChanged.emit(True)
            self._rebuild()
            self.bridge.statusMessage.emit(
                _t("panel.blocks.status.block_created").format(name=name), 4000)
        else:
            self.bridge.statusMessage.emit(
                _t("panel.blocks.status.block_exists").format(name=name), 4000)

    def _rename_block(self, old: str) -> None:
        new, ok = QInputDialog.getText(
            self, _t("panel.blocks.title"),
            _t("panel.blocks.dlg.block_name"), text=old)
        new = (new or "").strip()
        if not ok or not new or new == old:
            return
        stats = self.project.rename_block(old, new)
        self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.block_renamed").format(
                old=old, new=new, rooms=stats["rooms"], sys=stats["systems"]),
            5000)

    def _delete_block(self, name: str) -> None:
        n_rooms = sum(1 for sp in self.project.spaces
                      if getattr(sp, "block", "") == name)
        n_sys = sum(1 for vs in self.project.ventilation_systems.values()
                    if getattr(vs, "block", "") == name)
        if QMessageBox.question(
                self, _t("panel.blocks.title"),
                _t("panel.blocks.confirm.delete_block").format(
                    name=name, rooms=n_rooms, sys=n_sys)) != QMessageBox.Yes:
            return
        stats = self.project.delete_block(name)
        self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.block_deleted").format(
                name=name, rooms=stats["rooms"], sys=stats["systems"]), 5000)

    def _set_rooms_block(self, block: str) -> None:
        ids = set(self._selected_ids())
        n = 0
        for sp in self.project.spaces:
            if sp.space_id in ids and getattr(sp, "block", "") != block:
                sp.block = block
                n += 1
        if n:
            self.bridge.dirtyChanged.emit(True)
            self.project.emit("zones_changed")   # обновит фильтры всех панелей
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.rooms_set").format(
                b=block or _t("panel.blocks.none"), n=n), 4000)

    # ================= автопомощники =================
    def _assign_rooms_auto(self) -> None:
        n = self.project.assign_blocks(overwrite=False)
        if n:
            self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.assigned").format(n=n), 4000)

    def _assign_systems_auto(self) -> None:
        n = self.project.assign_system_blocks(overwrite=False)
        if n:
            self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.assigned_sys").format(n=n), 4000)

    def _reassign(self) -> None:
        if QMessageBox.question(
                self, _t("panel.blocks.title"),
                _t("panel.blocks.confirm.reassign")) != QMessageBox.Yes:
            return
        n = (self.project.assign_blocks(overwrite=True)
             + self.project.assign_system_blocks(overwrite=True))
        if n:
            self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.assigned").format(n=n), 4000)

    def _recalc_ahu(self) -> None:
        self.project.calculate_ahu_loads()
        self._rebuild()
        self.bridge.statusMessage.emit(_t("panel.equipment.status.computed"), 4000)

    def _edit_block_dhw(self, blk: str) -> None:
        """Ручной ввод нагрузки ГВС блока (расход считает ВК-программа)."""
        from hvac.dhw import DHWSystem
        sys_name = _t("panel.blocks.dhw.sys_name").format(block=blk)
        cur = self.project.dhw_systems.get(sys_name)
        dlg = _DhwDialog(
            self, blk,
            kw=(getattr(cur, "q_with_circulation_w", 0.0) / 1000.0
                if cur else 0.0),
            v_daily=(getattr(cur, "v_daily_total_m3", 0.0) if cur else 0.0))
        if dlg.exec() != QDialog.Accepted:
            return
        kw, v_daily = dlg.values()
        if kw <= 0:
            if sys_name in self.project.dhw_systems:
                del self.project.dhw_systems[sys_name]
                self.bridge.dirtyChanged.emit(True)
                self.bridge.statusMessage.emit(
                    _t("panel.blocks.status.dhw_removed").format(block=blk),
                    4000)
            self._rebuild()
            return
        s = cur if cur is not None else DHWSystem(name=sys_name)
        s.block = blk
        s.q_peak_w = kw * 1000.0
        s.q_with_circulation_w = kw * 1000.0
        s.v_daily_total_m3 = v_daily
        s.note = _t("panel.blocks.dhw.manual_note")
        self.project.dhw_systems[sys_name] = s
        self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.dhw_set").format(block=blk, kw=f"{kw:g}"),
            4000)

    # ================= контекстное меню дерева =================
    def _tree_double_clicked(self, item, col: int) -> None:
        # переименование — только двойной клик по ИМЕНИ блока; по числовым
        # колонкам двойной клик оставляем стандартному сворачиванию.
        if col == 0 and item is not None and item.parent() is None:
            blk = item.data(0, Qt.UserRole)
            if blk:
                self._rename_block(blk)

    def _tree_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        if item.parent() is None:
            # строка БЛОКА: переименовать / удалить
            blk = item.data(0, Qt.UserRole)
            if not blk:
                return          # «(без блока)» не переименовывается
            menu = QMenu(self)
            menu.addAction(_t("panel.blocks.menu.block_actions").format(
                name=blk)).setEnabled(False)
            menu.addSeparator()
            menu.addAction(_t("panel.blocks.menu.rename_block"),
                           lambda: self._rename_block(blk))
            menu.addAction(_t("panel.blocks.menu.delete_block"),
                           lambda: self._delete_block(blk))
            menu.addSeparator()
            menu.addAction(_t("panel.blocks.menu.dhw"),
                           lambda: self._edit_block_dhw(blk))
            menu.addAction(_t("panel.blocks.menu.pick_boilers"),
                           lambda: self._pick_block_source(blk, "heating"))
            menu.addAction(_t("panel.blocks.menu.pick_chillers"),
                           lambda: self._pick_block_source(blk, "cooling"))
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        # строка УСТАНОВКИ: сменить её блок
        sys_name = item.data(0, Qt.UserRole)
        vs = self.project.ventilation_systems.get(sys_name or "")
        if vs is None:
            return
        menu = QMenu(self)
        menu.addAction(_t("panel.blocks.menu.set_block").format(name=sys_name)
                       ).setEnabled(False)
        menu.addSeparator()
        menu.addAction(_t("panel.blocks.menu.auto"),
                       lambda: self._set_system_block(vs, ""))
        for b in self._known_blocks():
            menu.addAction(b, lambda _c=False, blk=b:
                           self._set_system_block(vs, blk))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_system_block(self, vs, block: str) -> None:
        if getattr(vs, "block", "") == block:
            return
        vs.block = block
        self.bridge.dirtyChanged.emit(True)
        self._rebuild()

    # ================= подбор котлов/чиллеров по блоку =================
    def _pick_block_source(self, blk: str, domain: str) -> None:
        """Каталожный подбор источника под итоговую нагрузку блока.

        Создаёт (или обновляет) Heating/CoolingSystem «Котлы <блок>» /
        «Чиллеры <блок>» с блоком и ручным подбором — дальше источник
        виден в разделе «Оборудование».
        """
        from hvac.ui_qt.panels.source_pick_dialog import SourcePickDialog
        row = self.project.get_block_summary().get(blk) or {}
        q_w = (row.get("q_heat_total_w", 0.0) if domain == "heating"
               else row.get("q_cool_total_w", 0.0))
        # ГВС блока висит на котельной — прибавляем к теплу
        dhw_w = row.get("q_dhw_w", 0.0) if domain == "heating" else 0.0
        margin = 1.10 if domain == "heating" else 1.15
        q_kw = q_w / 1000.0
        if dhw_w > 0:
            ctx = _t("panel.srcpick.ctx.block_dhw").format(
                block=blk, q=f"{q_kw:.0f}", dhw=f"{dhw_w / 1000.0:.0f}",
                m=f"{margin:.2f}")
        else:
            ctx = _t("panel.srcpick.ctx.block").format(
                block=blk, q=f"{q_kw:.0f}", m=f"{margin:.2f}")
        dlg = SourcePickDialog(
            self, domain=domain,
            required_kw=(q_w + dhw_w) / 1000.0 * margin, context=ctx)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if not vals:
            return
        name_key = ("panel.blocks.src.boiler_name" if domain == "heating"
                    else "panel.blocks.src.chiller_name")
        sys_name = _t(name_key).format(block=blk)
        self.project.add_zone_system(domain, sys_name)   # создаст, если нет
        self.project.update_zone_system(domain, sys_name, block=blk, **vals)
        self.bridge.dirtyChanged.emit(True)
        self._rebuild()
        self.bridge.statusMessage.emit(
            _t("panel.blocks.status.source_set").format(
                sys=sys_name, n=vals["unit_count"],
                kw=f"{vals['design_capacity_kw']:g}",
                model=vals["selected_model"]), 7000)

    # ================= отрисовка =================
    def _rebuild(self, *args: Any) -> None:
        self._loading = True
        self._rebuild_tree()
        self._rebuild_rooms()
        self._refresh_block_filter()
        self._loading = False
        self._filter_rooms()

    def _rebuild_tree(self) -> None:
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        if not self.project.spaces:
            self.summary.setText("")
            self.tree.setSortingEnabled(True)
            return
        summary = self.project.get_block_summary()

        tot = {"rooms": 0, "qh": 0.0, "qc": 0.0, "dhw": 0.0,
               "sup": 0.0, "exh": 0.0}
        no_block = 0
        for blk, r in summary.items():
            label = blk or _t("panel.blocks.none")
            if not blk:
                no_block = r["n_spaces"]
            q_dhw = r.get("q_dhw_w", 0.0)
            top = _NumTreeItem([
                label,
                str(r["n_spaces"]),
                f"{r['area_m2']:.0f}",
                _kw(r["q_heat_rooms_w"]), _kw(r["q_cool_rooms_w"]),
                _kw(r["ahu_q_heater_w"]), _kw(r["ahu_q_cooler_w"]),
                _kw(r["q_heat_total_w"]), _kw(r["q_cool_total_w"]),
                _kw(q_dhw),
                _m3(r["supply_m3h"]),
                _m3(r["exhaust_m3h"] + r["hood_m3h"]),
            ])
            for c, v in ((COL_ROOMS, r["n_spaces"]), (COL_AREA, r["area_m2"]),
                         (COL_QH_ROOMS, r["q_heat_rooms_w"]),
                         (COL_QC_ROOMS, r["q_cool_rooms_w"]),
                         (COL_QH_AHU, r["ahu_q_heater_w"]),
                         (COL_QC_AHU, r["ahu_q_cooler_w"]),
                         (COL_QH_TOTAL, r["q_heat_total_w"]),
                         (COL_QC_TOTAL, r["q_cool_total_w"]),
                         (COL_DHW, q_dhw),
                         (COL_SUP, r["supply_m3h"]),
                         (COL_EXH, r["exhaust_m3h"] + r["hood_m3h"])):
                top.setData(c, Qt.UserRole + 1, float(v))
            top.setData(0, Qt.UserRole, blk)     # код блока (для меню)
            f = top.font(COL_NAME)
            f.setBold(True)
            if not blk:
                f.setItalic(True)                # «(без блока)» — курсивом
            top.setFont(COL_NAME, f)
            for c in range(1, COL_COUNT):
                top.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(top)

            for a in r["ahus"]:
                name = a["name"]
                if a["multi_block"]:
                    served = ", ".join(
                        f"{b} {s + e:.0f}" for b, s, e in a["serves"])
                    name += _t("panel.blocks.ahu.serves").format(list=served)
                cells = [""] * COL_COUNT
                cells[COL_NAME] = name
                cells[COL_QH_AHU] = _kw(a["q_heater_w"])
                cells[COL_QC_AHU] = _kw(a["q_cooler_w"])
                cells[COL_SUP] = _m3(a["supply_m3h"])
                cells[COL_EXH] = _m3(a["exhaust_m3h"])
                child = _NumTreeItem(cells)
                child.setData(0, Qt.UserRole, a["name"])
                for c, v in ((COL_QH_AHU, a["q_heater_w"]),
                             (COL_QC_AHU, a["q_cooler_w"]),
                             (COL_SUP, a["supply_m3h"]),
                             (COL_EXH, a["exhaust_m3h"])):
                    child.setData(c, Qt.UserRole + 1, float(v))
                for c in range(1, COL_COUNT):
                    child.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                top.addChild(child)

            # подобранные котлы/чиллеры блока — мощность в колонках ИТОГО
            for s in r.get("sources", []):
                icon = "\U0001F525 " if s["domain"] == "heating" else "❄ "
                if s["units"] and s["unit_kw"] > 0:
                    txt = icon + _t("panel.blocks.src.pick_fmt").format(
                        name=s["name"], n=s["units"],
                        kw=f"{s['unit_kw']:g}", model=s["model"] or "—")
                else:
                    txt = icon + s["name"]
                col = (COL_QH_TOTAL if s["domain"] == "heating"
                       else COL_QC_TOTAL)
                cells = [""] * COL_COUNT
                cells[COL_NAME] = txt
                cells[col] = _kw(s["total_kw"] * 1000.0)
                child = _NumTreeItem(cells)
                child.setData(col, Qt.UserRole + 1,
                              float(s["total_kw"] * 1000.0))
                for c in range(1, COL_COUNT):
                    child.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                top.addChild(child)

            # системы ГВС блока (расход показываем, если задан)
            for s in r.get("dhw", []):
                if s["v_daily_m3"] > 0:
                    base = _t("panel.blocks.dhw.fmt").format(
                        name=s["name"], v=f"{s['v_daily_m3']:.1f}")
                else:
                    base = s["name"]
                cells = [""] * COL_COUNT
                cells[COL_NAME] = "\U0001F6BF " + base
                cells[COL_DHW] = _kw(s["q_w"])
                child = _NumTreeItem(cells)
                child.setData(COL_DHW, Qt.UserRole + 1, float(s["q_w"]))
                for c in range(1, COL_COUNT):
                    child.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                top.addChild(child)

            tot["rooms"] += r["n_spaces"]
            tot["qh"] += r["q_heat_total_w"]
            tot["qc"] += r["q_cool_total_w"]
            tot["dhw"] += r.get("q_dhw_w", 0.0)
            tot["sup"] += r["supply_m3h"]
            tot["exh"] += r["exhaust_m3h"] + r["hood_m3h"]

        self.tree.setSortingEnabled(True)
        self.summary.setText(_t("panel.blocks.summary.line").format(
            blocks=sum(1 for b in summary if b),
            rooms=tot["rooms"], no_block=no_block,
            qh=f"{tot['qh'] / 1000.0:.0f}", qc=f"{tot['qc'] / 1000.0:.0f}",
            dhw=f"{tot['dhw'] / 1000.0:.0f}",
            sup=f"{tot['sup']:.0f}", exh=f"{tot['exh']:.0f}"))

    def _rebuild_rooms(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            num = QTableWidgetItem(sp.number)
            num.setData(Qt.UserRole, sp.space_id)
            self.table.setItem(r, RC_NUM, num)
            self.table.setItem(r, RC_NAME, QTableWidgetItem(sp.name or ""))
            # уровень сортируется как ЭТАЖ (B2, B1, GFL, MZN, MFL, L02..L28)
            self.table.setItem(
                r, RC_LEVEL,
                _num_item(sp.level or "", level_sort_key(sp.level),
                          align_right=False))
            self.table.setItem(r, RC_TYPE, QTableWidgetItem(sp.room_type or ""))
            self.table.setItem(r, RC_BLOCK,
                               QTableWidgetItem(getattr(sp, "block", "") or ""))
            area = float(sp.area_m2 or 0)
            self.table.setItem(r, RC_AREA, _num_item(f"{area:.1f}", area))
            sup = float(getattr(sp, "supply_m3h", 0) or 0)
            exh = float(getattr(sp, "exhaust_m3h", 0) or 0) + \
                float(getattr(sp, "hood_m3h", 0) or 0)
            self.table.setItem(r, RC_SUP, _num_item(_m3(sup), sup))
            self.table.setItem(r, RC_EXH, _num_item(_m3(exh), exh))
        self.table.setSortingEnabled(True)

    def _refresh_block_filter(self) -> None:
        all_label = _t("filter.all")
        blocks = self._known_blocks()
        if any(not getattr(s, "block", "") for s in self.project.spaces):
            blocks = blocks + [_t("panel.blocks.none")]
        # этажи — в порядке здания (B2, B1, GFL, MZN, MFL, L02..)
        levels = sorted({s.level for s in self.project.spaces if s.level},
                        key=level_sort_key)
        for combo, items in ((self.block_filter, blocks),
                             (self.level_filter, levels)):
            current = combo.currentText() or all_label
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(items)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    def _filter_rooms(self) -> None:
        if self._loading:
            return
        text = self.search.text().lower().strip()
        blk = self.block_filter.currentText()
        blk = "" if blk == _t("filter.all") else blk
        lvl = self.level_filter.currentText()
        lvl = "" if lvl == _t("filter.all") else lvl
        none_label = _t("panel.blocks.none")
        by_id = {sp.space_id: sp for sp in self.project.spaces}
        shown = 0
        for r in range(self.table.rowCount()):
            it = self.table.item(r, RC_NUM)
            sp = by_id.get(it.data(Qt.UserRole)) if it else None
            if sp is None:
                self.table.setRowHidden(r, True)
                continue
            visible = True
            if lvl:
                visible = (sp.level or "") == lvl
            if visible and blk:
                b = getattr(sp, "block", "") or none_label
                visible = (b == blk)
            if visible and text:
                hay = " ".join((sp.number, sp.name or "", sp.level or "",
                                sp.room_type or "",
                                getattr(sp, "block", "") or "")).lower()
                visible = text in hay
            self.table.setRowHidden(r, not visible)
            shown += 1 if visible else 0
        self.rooms_count.setText(
            _t("panel.blocks.rooms.count").format(
                visible=shown, total=self.table.rowCount()))
