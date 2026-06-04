# -*- coding: utf-8 -*-
"""SystemsWorkspacePanel — единый рабочий стол «Системы и оборудование».

Объединяет три прежних раздела в один master-detail экран, чтобы не
«мотаться туда-сюда»: вся цепочка Источник → Контур → Помещение → Прибор
в одном месте.

- LEFT (master): дерево Источник → Контур активного домена
  (Отопление / Холод / Вентиляция) с CRUD и подобранной мощностью на узле.
  Двойной клик — правка параметров (диалоги из equipment_panel).
- RIGHT (detail): строка-сводка выбранного узла + мощная таблица помещений
  (мультивыбор, сортировка, drag&drop на узел, массовое назначение) с
  колонкой установленного прибора. Двойной клик по строке — прибор +
  подключение к контуру/AHU (RoomEquipmentDialog).

Логика и виджеты переиспользованы:
- зонирование/CRUD/undo — `ZoningMixin` (`hvac/_project_zoning.py`);
- подбор источников — `equipment_sizing.select_equipment`;
- дерево/сортировка/drag, диалог создания контура — `zones_panel`;
- диалоги правки источника/контура/AHU — `equipment_panel`;
- диалог прибора + подключение — `room_equipment_panel`.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.air_heating import apply_air_heating
from hvac.equipment_sizing import (
    EquipmentSelection, SourceSelection, select_equipment,
)
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.room_equipment import (
    serialize_room_equipment, deserialize_room_equipment,
)
from hvac.sizing_helpers import suggest_ahu_size
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.equipment_panel import (
    _AHUDialog, _CircuitDialog as _EditCircuitDialog, _SourceDialog,
)
from hvac.ui_qt.panels.room_equipment_panel import RoomEquipmentDialog
from hvac.ui_qt.panels.zones_panel import (
    _DOMAIN_KEY, _DOMAIN_ORDER, _LOAD_KEY, _NumTableItem, _NumTreeItem,
    _ZoneTree, _CircuitDialog as _NewCircuitDialog, _ctype_label, _load_value,
)


_ROOM_COL_KEYS = [
    "panel.zones.rcol.number", "panel.zones.rcol.level", "panel.zones.rcol.name",
    "panel.zones.rcol.area", "panel.zones.rcol.load", "panel.zones.rcol.system",
    "panel.zones.rcol.circuit",
    "panel.sysworkspace.rcol.air", "panel.sysworkspace.rcol.device",
]


def _floor_key(sp) -> float:
    """Числовой ключ этажа для сортировки: первое целое из level
    («L12» → 12, «-1 этаж» → -1). Без числа — в конец списка."""
    m = re.search(r"-?\d+", getattr(sp, "level", "") or "")
    return float(m.group()) if m else 1e9


def _air_marker(sp) -> str:
    """Компактная пометка воздушного режима помещения («О» / «Х» / «О·Х»)."""
    marks = []
    if getattr(sp, "air_heating", False):
        marks.append(_t("panel.sysworkspace.air.mark_heat"))
    if getattr(sp, "air_cooling", False):
        marks.append(_t("panel.sysworkspace.air.mark_cool"))
    return "·".join(marks)


def _device_for_domain(domain: str, eq) -> str:
    """Краткое имя установленного прибора для активного домена."""
    if eq is None:
        return ""
    if domain == "heating":
        typ, qty = eq.heating_terminal_type, eq.heating_terminal_qty
    elif domain == "cooling":
        typ, qty = eq.cooling_terminal_type, eq.cooling_terminal_qty
    else:
        typ, qty = eq.supply_terminal_type, eq.supply_terminal_qty
    if not typ or typ == "—" or not qty:
        return ""
    return f"{typ} ×{qty}"


class SystemsWorkspacePanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._domain = "heating"
        self._undo: list[dict] = []
        self._clip: Optional[dict] = None      # буфер копирования прибора
        self._sel: Optional[EquipmentSelection] = None                       # последний select_equipment()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ---------- топбар ----------
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.sysworkspace.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addSpacing(16)

        self.domain_group = QButtonGroup(self)
        self._domain_buttons: dict[str, QPushButton] = {}
        for dk in _DOMAIN_ORDER:
            btn = QPushButton(_t(_DOMAIN_KEY[dk]))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, d=dk: self._switch_domain(d))
            self.domain_group.addButton(btn)
            self._domain_buttons[dk] = btn
            head.addWidget(btn)
        self._domain_buttons["heating"].setChecked(True)

        head.addStretch(1)
        self.assistant_btn = QPushButton(_t("panel.zones.btn.assistant"))
        self.assistant_btn.setCursor(Qt.PointingHandCursor)
        self.assistant_btn.clicked.connect(self._show_assistant_menu)
        head.addWidget(self.assistant_btn)
        self.compute_btn = QPushButton(_t("panel.equipment.btn.compute"))
        self.compute_btn.setProperty("role", "primary")
        self.compute_btn.setCursor(Qt.PointingHandCursor)
        self.compute_btn.clicked.connect(self._compute)
        head.addWidget(self.compute_btn)
        self.undo_btn = QPushButton(_t("panel.zones.btn.undo"))
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self._apply_undo)
        head.addWidget(self.undo_btn)
        outer.addLayout(head)

        self.hint_lbl = QLabel(_t("panel.sysworkspace.hint"))
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setWordWrap(True)
        outer.addWidget(self.hint_lbl)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, stretch=1)

        # ---------- LEFT: дерево ----------
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.add_sys_btn = QPushButton(_t("panel.zones.btn.add_system"))
        self.add_sys_btn.clicked.connect(self._add_system)
        bar.addWidget(self.add_sys_btn)
        self.add_circ_btn = QPushButton(_t("panel.zones.btn.add_circuit"))
        self.add_circ_btn.clicked.connect(self._add_circuit)
        bar.addWidget(self.add_circ_btn)
        self.rename_btn = QPushButton(_t("panel.zones.btn.rename"))
        self.rename_btn.clicked.connect(self._rename_node)
        bar.addWidget(self.rename_btn)
        self.del_btn = QPushButton(_t("panel.zones.btn.delete"))
        self.del_btn.clicked.connect(self._delete_node)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)
        left_l.addLayout(bar)

        self.tree = _ZoneTree(self._on_rooms_dropped)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([
            _t("panel.sysworkspace.tree.name"), _t("panel.sysworkspace.tree.kw")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit_node())
        self.tree.currentItemChanged.connect(lambda *_: self._update_summary())
        left_l.addWidget(self.tree, stretch=1)
        splitter.addWidget(left)

        # ---------- RIGHT: сводка + таблица ----------
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        self.summary_lbl = QLabel(_t("panel.sysworkspace.summary.none"))
        self.summary_lbl.setProperty("role", "muted")
        self.summary_lbl.setWordWrap(True)
        right_l.addWidget(self.summary_lbl)

        flt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._filter())
        flt.addWidget(self.search, stretch=1)
        self.node_filter_cb = QCheckBox(_t("panel.sysworkspace.filter_node"))
        self.node_filter_cb.stateChanged.connect(lambda *_: self._filter())
        flt.addWidget(self.node_filter_cb)
        right_l.addLayout(flt)

        self.table = QTableWidget(0, len(_ROOM_COL_KEYS))
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._edit_room_device)
        for i, w in enumerate([60, 64, 200, 70, 100, 130, 130, 56, 200]):
            self.table.setColumnWidth(i, w)
        right_l.addWidget(self.table, stretch=1)

        brow = QHBoxLayout()
        self.assign_sys_btn = QPushButton(_t("panel.zones.btn.assign_system"))
        self.assign_sys_btn.setProperty("role", "primary")
        self.assign_sys_btn.clicked.connect(self._show_assign_system_menu)
        brow.addWidget(self.assign_sys_btn)
        self.assign_circ_btn = QPushButton(_t("panel.zones.btn.assign_circuit"))
        self.assign_circ_btn.clicked.connect(self._show_assign_circuit_menu)
        brow.addWidget(self.assign_circ_btn)
        self.clear_btn = QPushButton(_t("panel.zones.btn.clear"))
        self.clear_btn.clicked.connect(self._clear_selected)
        brow.addWidget(self.clear_btn)
        self.device_btn = QPushButton(_t("panel.sysworkspace.btn.device"))
        self.device_btn.clicked.connect(self._apply_device_to_selected)
        brow.addWidget(self.device_btn)
        brow.addStretch(1)
        right_l.addLayout(brow)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        for sig in (bridge.dataLoaded, bridge.projectLoaded, bridge.zonesChanged,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.ahuLoadsCalculated, bridge.equipmentChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ================= helpers =================
    def _room_headers(self) -> list[str]:
        heads = [_t(k) for k in _ROOM_COL_KEYS]
        heads[4] = _t(_LOAD_KEY[self._domain])
        return heads

    def _selected_rows(self) -> list[int]:
        sel = self.table.selectionModel()
        return sorted({i.row() for i in sel.selectedRows()}) if sel else []

    def _ids_for(self, rows: list[int]) -> list[str]:
        out = []
        for r in rows:
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole):
                out.append(it.data(Qt.UserRole))
        return out

    def _selected_ids(self) -> list[str]:
        return self._ids_for(self._selected_rows())

    def _warn_no_selection(self) -> None:
        QMessageBox.information(self, _t("panel.sysworkspace.title"),
                                _t("panel.zones.msg.no_selection"))

    def _current_node(self):
        it = self.tree.currentItem()
        if it is None:
            return ("", "")
        return it.data(0, Qt.UserRole) or ("", "")

    # ---- undo (зонирование + приборы) ----
    def _push_undo(self, ids: list[str]) -> None:
        eq_snap = {}
        air_snap = {}
        for sid in ids:
            sp = self.project._space_by_id.get(sid)
            eq = sp.room_equipment if sp else None
            eq_snap[sid] = serialize_room_equipment(eq) if eq else None
            if sp is not None:
                air_snap[sid] = (sp.air_heating, sp.air_cooling,
                                 sp.supply_m3h, sp.ach_calculated)
        self._undo.append({"zoning": self.project.snapshot_zoning(ids),
                           "eq": eq_snap, "air": air_snap})
        del self._undo[:-50]

    def _apply_undo(self) -> None:
        if not self._undo:
            return
        snap = self._undo.pop()
        for sid, data in snap.get("eq", {}).items():
            sp = self.project._space_by_id.get(sid)
            if sp is not None:
                sp.room_equipment = deserialize_room_equipment(data) if data else None
        for sid, (ah, ac, sup, ach) in snap.get("air", {}).items():
            sp = self.project._space_by_id.get(sid)
            if sp is not None:
                sp.air_heating, sp.air_cooling = ah, ac
                sp.supply_m3h, sp.ach_calculated = sup, ach
        self.project.restore_zoning(snap.get("zoning", {}))
        self.project.emit("equipment_changed")
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.undone").format(n=len(snap.get("zoning", {}))), 3000)

    # ---- воздушное отопление / охлаждение ----
    def _set_air_mode(self, heating: Optional[bool], cooling: Optional[bool]) -> None:
        """Переключает воздушный режим у выбранных помещений и пересчитывает
        расход приточки по нагрузке. heating/cooling: True/False/None (не менять)."""
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        for sid in ids:
            sp = self.project._space_by_id.get(sid)
            if sp is None:
                continue
            if heating is not None:
                sp.air_heating = heating
            if cooling is not None:
                sp.air_cooling = cooling
        apply_air_heating(self.project)
        self.project.emit("zones_changed")
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.sysworkspace.air.status").format(n=len(ids)), 4000)

    # ================= домен =================
    def _switch_domain(self, domain: str) -> None:
        if domain == self._domain:
            return
        self._domain = domain
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self._refresh()

    # ================= CRUD дерева =================
    def _systems_sorted(self) -> list[str]:
        return sorted(self.project.systems_of(self._domain).keys())

    def _add_system(self) -> None:
        if self._domain == "ventilation":
            self._add_ventilation_system()
            return
        name, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.add_system_title"),
            _t("panel.zones.dlg.system_name"))
        if ok and name.strip():
            self.project.add_zone_system(self._domain, name.strip())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _add_ventilation_system(self) -> None:
        """Создание вентоборудования с выбором вида (AHU / вытяжной /
        приточный / местный отсос)."""
        from hvac.equipment import VENTILATION_KINDS, make_ventilation_defaults
        labels = [_t("panel.detail.kind." + k) for k in VENTILATION_KINDS]
        label, ok = QInputDialog.getItem(
            self, _t("panel.sysworkspace.dlg.kind_title"),
            _t("panel.sysworkspace.dlg.kind"), labels, 0, False)
        if not ok:
            return
        kind = VENTILATION_KINDS[labels.index(label)]
        name, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.add_system_title"),
            _t("panel.zones.dlg.system_name"))
        if ok and name.strip():
            self.project.add_zone_system("ventilation", name.strip(),
                                         **make_ventilation_defaults(kind))
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _add_circuit(self) -> None:
        kind, name = self._current_node()
        preset = name if kind == "system" else (
            self.project.circuit_parent(self._domain, name) if kind == "circuit"
            else "")
        dlg = _NewCircuitDialog(
            self, domain=self._domain,
            types=self.project.circuit_types_for(self._domain),
            systems=self._systems_sorted(), preset_system=preset)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if v["name"] and v["parent_system"]:
            self.project.add_zone_circuit(self._domain, v["name"],
                                          v["parent_system"],
                                          circuit_type=v["circuit_type"])
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _rename_node(self) -> None:
        kind, name = self._current_node()
        if not kind:
            return
        new, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.rename_title"),
            _t("panel.zones.dlg.new_name"), text=name)
        if not ok or not new.strip() or new.strip() == name:
            return
        if kind == "system":
            self.project.rename_zone_system(self._domain, name, new.strip())
        else:
            self.project.rename_zone_circuit(self._domain, name, new.strip())
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _delete_node(self) -> None:
        kind, name = self._current_node()
        if not kind:
            return
        msg = (_t("panel.zones.confirm.delete_system") if kind == "system"
               else _t("panel.zones.confirm.delete_circuit")).format(name=name)
        if QMessageBox.question(self, _t("panel.zones.confirm.title"),
                                msg) != QMessageBox.Yes:
            return
        if kind == "system":
            self.project.remove_zone_system(self._domain, name)
        else:
            self.project.remove_zone_circuit(self._domain, name)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _edit_node(self) -> None:
        """Двойной клик — правка параметров узла."""
        kind, name = self._current_node()
        domain = self._domain
        if kind == "system":
            if domain == "ventilation":
                vsys = self.project.systems_of(domain).get(name)
                if vsys is None:
                    return
                dlg: QDialog = _AHUDialog(
                    self, vsys=vsys,
                    heating_circuits=sorted(self.project.circuits_of("heating")),
                    cooling_circuits=sorted(self.project.circuits_of("cooling")))
                if dlg.exec() == QDialog.Accepted:
                    self.project.update_zone_system(domain, name, **dlg.values())
            else:
                sysobj = self.project.systems_of(domain).get(name)
                if sysobj is None:
                    return
                req = self._required_kw(name)
                dlg = _SourceDialog(self, domain=domain, sysobj=sysobj,
                                    required_kw=req)
                if dlg.exec() == QDialog.Accepted:
                    self.project.update_zone_system(domain, name, **dlg.values())
        elif kind == "circuit":
            cobj = self.project.circuits_of(domain).get(name)
            if cobj is None:
                return
            dlg = _EditCircuitDialog(self, domain=domain, cobj=cobj,
                                     types=self.project.circuit_types_for(domain))
            if dlg.exec() == QDialog.Accepted:
                self.project.update_zone_circuit(domain, name, **dlg.values())
        else:
            return
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _required_kw(self, system_name: str) -> float:
        if self._sel is None:
            return 0.0
        return next((s.required_kw for s in self._sel.sources(self._domain)
                     if s.name == system_name), 0.0)

    # ================= назначение помещений =================
    def _assign_to_system(self, system_name: str) -> None:
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        n = self.project.assign_rooms_to_system(self._domain, ids, system_name)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.assigned_sys").format(n=n), 4000)

    def _assign_to_circuit(self, circuit_name: str) -> None:
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        n = self.project.assign_rooms_to_circuit(self._domain, ids, circuit_name)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.assigned_circ").format(n=n), 4000)

    def _clear_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        n = self.project.clear_rooms_assignment(self._domain, ids, what="all")
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.cleared").format(n=n), 4000)

    def _on_rooms_dropped(self, item: QTreeWidgetItem) -> None:
        kind, name = item.data(0, Qt.UserRole) or ("", "")
        if kind == "system":
            self._assign_to_system(name)
        elif kind == "circuit":
            self._assign_to_circuit(name)

    def _show_assign_system_menu(self) -> None:
        if not self._selected_rows():
            self._warn_no_selection()
            return
        menu = QMenu(self)
        for s in self._systems_sorted():
            menu.addAction(s, lambda _c=False, n=s: self._assign_to_system(n))
        menu.addSeparator()
        menu.addAction(_t("panel.zones.menu.new_system"), self._assign_new_system)
        menu.exec(self.assign_sys_btn.mapToGlobal(
            self.assign_sys_btn.rect().bottomLeft()))

    def _assign_new_system(self) -> None:
        name, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.add_system_title"),
            _t("panel.zones.dlg.system_name"))
        if ok and name.strip():
            self._assign_to_system(name.strip())

    def _show_assign_circuit_menu(self) -> None:
        if not self._selected_rows():
            self._warn_no_selection()
            return
        menu = QMenu(self)
        for s in self._systems_sorted():
            children = self.project.circuits_of_system(self._domain, s)
            if not children:
                continue
            sub = menu.addMenu(s)
            for c in children:
                sub.addAction(c, lambda _c=False, n=c: self._assign_to_circuit(n))
        if menu.isEmpty():
            menu.addAction(_t("panel.zones.menu.no_circuits")).setEnabled(False)
        menu.addSeparator()
        menu.addAction(_t("panel.zones.menu.unassign_circuit"),
                       lambda: self._assign_to_circuit(""))
        menu.exec(self.assign_circ_btn.mapToGlobal(
            self.assign_circ_btn.rect().bottomLeft()))

    # ================= помощник + подбор =================
    def _show_assistant_menu(self) -> None:
        menu = QMenu(self)
        for mode, key in (("by_prefix", "panel.zones.mode.by_prefix"),
                          ("by_level", "panel.zones.mode.by_level"),
                          ("by_type_family", "panel.zones.mode.by_type")):
            menu.addAction(_t(key),
                           lambda _c=False, m=mode: self._run_assistant(m))
        menu.exec(self.assistant_btn.mapToGlobal(
            self.assistant_btn.rect().bottomLeft()))

    def _run_assistant(self, mode: str) -> None:
        if not self.project.spaces:
            return
        self._push_undo([sp.space_id for sp in self.project.spaces])
        n = self.project.auto_assign_zones(mode=mode, overwrite=True,
                                           system=self._domain)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.assigned_sys").format(n=n), 4000)

    def _compute(self) -> None:
        # Сначала поднимаем расход приточки по нагрузке (воздушное отопление/
        # охлаждение), чтобы нагрузка AHU считалась на актуальный расход.
        apply_air_heating(self.project)
        for step in (self.project.calculate_ahu_loads, self.project.size_pipes,
                     self.project.design_heating_hydraulics,
                     self.project.size_cooling_pipes):
            try:
                step()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "systems: step %s failed", getattr(step, "__name__", "?"))
        self._refresh()
        self.bridge.statusMessage.emit(_t("panel.equipment.status.computed"), 4000)

    # ================= приборы (room equipment) =================
    def _edit_room_device(self, row: int, _col: int = 0) -> None:
        ids = self._ids_for([row])
        if not ids:
            return
        sp = self.project._space_by_id.get(ids[0])
        if sp is None:
            return
        dlg = RoomEquipmentDialog(sp, self, project=self.project)
        if dlg.exec() == QDialog.Accepted:
            self._push_undo([sp.space_id])
            self.project.set_room_equipment(sp.space_id, **dlg.values())
            self._apply_room_connection([sp.space_id], dlg.connection())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _apply_device_to_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._warn_no_selection()
            return
        ids = self._ids_for(rows)
        anchor = self.project._space_by_id.get(ids[0])
        if anchor is None:
            return
        dlg = RoomEquipmentDialog(
            anchor, self, show_loads=False, project=self.project,
            title=_t("panel.room_eq.dlg.apply_title").format(n=len(ids)))
        if dlg.exec() != QDialog.Accepted:
            return
        self._push_undo(ids)
        n = self.project.apply_room_equipment(ids, dlg.values())
        self._apply_room_connection(ids, dlg.connection())
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.applied").format(n=n), 4000)

    def _apply_room_connection(self, ids: list[str], conn: dict) -> None:
        if not conn:
            return
        ch = conn.get("circuit_heating", "")
        (self.project.assign_rooms_to_circuit("heating", ids, ch) if ch
         else self.project.clear_rooms_assignment("heating", ids, "circuit"))
        cc = conn.get("circuit_cooling", "")
        (self.project.assign_rooms_to_circuit("cooling", ids, cc) if cc
         else self.project.clear_rooms_assignment("cooling", ids, "circuit"))
        sv = conn.get("system_ventilation", "")
        (self.project.assign_rooms_to_system("ventilation", ids, sv) if sv
         else self.project.clear_rooms_assignment("ventilation", ids, "system"))

    def _copy_device(self) -> None:
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        eq = self.project._space_by_id[ids[0]].room_equipment
        if eq is None:
            self.bridge.statusMessage.emit(
                _t("panel.room_eq.status.nothing_copy"), 3000)
            return
        self._clip = serialize_room_equipment(eq)
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.copied").format(
                room=self.project._space_by_id[ids[0]].number), 3000)

    def _paste_device(self) -> None:
        if self._clip is None:
            return
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        n = self.project.apply_room_equipment(ids, dict(self._clip))
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.pasted").format(n=n), 4000)

    def _clear_device(self) -> None:
        ids = self._selected_ids()
        if not ids:
            self._warn_no_selection()
            return
        self._push_undo(ids)
        n = self.project.clear_room_equipment(ids)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.cleared").format(n=n), 4000)

    def _show_context_menu(self, pos) -> None:
        if not self._selected_rows():
            return
        menu = QMenu(self)
        menu.addAction(_t("panel.zones.btn.assign_system"),
                       self._show_assign_system_menu)
        menu.addAction(_t("panel.zones.btn.assign_circuit"),
                       self._show_assign_circuit_menu)
        menu.addAction(_t("panel.zones.btn.clear"), self._clear_selected)
        menu.addSeparator()
        air = menu.addMenu(_t("panel.sysworkspace.air.menu"))
        air.addAction(_t("panel.sysworkspace.air.heat_on"),
                      lambda: self._set_air_mode(True, None))
        air.addAction(_t("panel.sysworkspace.air.cool_on"),
                      lambda: self._set_air_mode(None, True))
        air.addAction(_t("panel.sysworkspace.air.both_on"),
                      lambda: self._set_air_mode(True, True))
        air.addAction(_t("panel.sysworkspace.air.off"),
                      lambda: self._set_air_mode(False, False))
        menu.addSeparator()
        menu.addAction(_t("panel.sysworkspace.btn.device"),
                       self._apply_device_to_selected)
        menu.addAction(_t("panel.room_eq.ctx.copy"), self._copy_device)
        act_paste = menu.addAction(_t("panel.room_eq.ctx.paste"), self._paste_device)
        act_paste.setEnabled(self._clip is not None)
        menu.addAction(_t("panel.room_eq.ctx.clear"), self._clear_device)
        menu.addSeparator()
        act_undo = menu.addAction(_t("panel.zones.btn.undo"), self._apply_undo)
        act_undo.setEnabled(bool(self._undo))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ================= отрисовка =================
    def _refresh(self, *args: Any) -> None:
        self._sel = select_equipment(self.project)
        self._refresh_tree()
        self._refresh_table()
        self._update_summary()
        self.undo_btn.setEnabled(bool(self._undo))

    def _refresh_tree(self) -> None:
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        domain = self._domain
        sys_field, circ_field = self.project.zoning_space_fields(domain)
        sys_count: dict[str, int] = {}
        circ_count: dict[str, int] = {}
        for sp in self.project.spaces:
            sv = getattr(sp, sys_field, "")
            cv = getattr(sp, circ_field, "")
            if sv:
                sys_count[sv] = sys_count.get(sv, 0) + 1
            if cv:
                circ_count[cv] = circ_count.get(cv, 0) + 1
        # подобранная мощность по источникам (тепло/холод)
        picked: dict[str, str] = {}
        if domain in ("heating", "cooling") and self._sel is not None:
            for s in self._sel.sources(domain):
                if s.units:
                    picked[s.name] = _t("panel.equipment.fmt.units").format(
                        kw=f"{s.unit_kw:g}", n=s.units)

        for sname in sorted(self.project.systems_of(domain).keys()):
            kw = picked.get(sname, "")
            top = _NumTreeItem([f"{sname}  ({sys_count.get(sname, 0)})", kw])
            top.setData(0, Qt.UserRole, ("system", sname))
            fnt = top.font(0)
            fnt.setBold(True)
            top.setFont(0, fnt)
            self.tree.addTopLevelItem(top)
            for cname in self.project.circuits_of_system(domain, sname):
                c = self.project.circuits_of(domain).get(cname)
                ctype = getattr(c, "circuit_type", "") if c else ""
                label = cname if not ctype else f"{cname}  ·  {_ctype_label(ctype)}"
                child = _NumTreeItem([
                    f"{label}  ({circ_count.get(cname, 0)})", ""])
                child.setData(0, Qt.UserRole, ("circuit", cname))
                top.addChild(child)
            top.setExpanded(True)
        self.tree.setSortingEnabled(True)

    def _refresh_table(self) -> None:
        domain = self._domain
        sys_field, circ_field = self.project.zoning_space_fields(domain)
        is_flow = domain == "ventilation"
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            load = _load_value(domain, sp)
            load_txt = (f"{load:.0f}" if is_flow else f"{load:.2f}") if load else ""
            num = QTableWidgetItem(sp.number)
            num.setData(Qt.UserRole, sp.space_id)
            self.table.setItem(r, 0, num)
            self.table.setItem(r, 1, _NumTableItem(sp.level or "", _floor_key(sp)))
            self.table.setItem(r, 2, QTableWidgetItem(sp.name))
            ar = _NumTableItem(f"{sp.area_m2:.0f}", sp.area_m2)
            ar.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 3, ar)
            ld = _NumTableItem(load_txt, load)
            ld.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 4, ld)
            self.table.setItem(r, 5, QTableWidgetItem(getattr(sp, sys_field, "") or ""))
            self.table.setItem(r, 6, QTableWidgetItem(getattr(sp, circ_field, "") or ""))
            air = QTableWidgetItem(_air_marker(sp))
            air.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 7, air)
            self.table.setItem(r, 8, QTableWidgetItem(
                _device_for_domain(domain, sp.room_equipment)))
        self.table.setSortingEnabled(True)
        self._filter()

    def _update_summary(self) -> None:
        kind, name = self._current_node()
        domain = self._domain
        if not kind:
            self.summary_lbl.setText(_t("panel.sysworkspace.summary.none"))
            return
        if kind == "system" and domain == "ventilation":
            info = (self.project.ahu_loads or {}).get(name, {})
            flow = info.get("supply_m3h", 0.0)
            qc = (info.get("q_cooler_sens_w", 0) + info.get("q_cooler_lat_w", 0)) / 1000
            self.summary_lbl.setText(_t("panel.sysworkspace.sum.ahu").format(
                name=name, flow=f"{flow:.0f}", fan=suggest_ahu_size(flow),
                qh=f"{info.get('q_heater_w', 0) / 1000:.1f}", qc=f"{qc:.1f}"))
        elif kind == "system":
            src = next((s for s in self._sel.sources(domain) if s.name == name),
                       None) if self._sel else None
            if src is None:
                self.summary_lbl.setText(name)
                return
            pick = (_t("panel.equipment.fmt.units").format(
                kw=f"{src.unit_kw:g}", n=src.units) if src.units else "—")
            self.summary_lbl.setText(_t("panel.sysworkspace.sum.source").format(
                name=name, req=f"{src.required_kw:.1f}", pick=pick))
        else:  # circuit
            src_list: list[SourceSelection] = (
                self._sel.sources(domain) if self._sel else [])
            cs = next((c for s in src_list for c in s.circuits if c.name == name),
                      None)
            if cs is None:
                self.summary_lbl.setText(name)
                return
            pump = cs.pump_model or "—"
            self.summary_lbl.setText(_t("panel.sysworkspace.sum.circuit").format(
                name=name, load=f"{cs.q_total_w / 1000:.1f}",
                dn=f"{cs.dn_mm:.0f}" if cs.dn_mm else "—",
                dp=f"{cs.dp_pa / 1000:.1f}" if cs.dp_pa else "—", pump=pump))

    def _filter(self) -> None:
        text = self.search.text().lower().strip()
        kind, node = self._current_node()
        only = self.node_filter_cb.isChecked()
        sys_field, circ_field = self.project.zoning_space_fields(self._domain)
        by_id = {sp.space_id: sp for sp in self.project.spaces}
        for r in range(self.table.rowCount()):
            visible = True
            it = self.table.item(r, 0)
            sp = by_id.get(it.data(Qt.UserRole)) if it else None
            if only and kind and sp is not None:
                if kind == "system":
                    visible = getattr(sp, sys_field, "") == node
                else:
                    visible = getattr(sp, circ_field, "") == node
            if visible and text:
                row_text = " ".join(
                    (cell.text() if (cell := self.table.item(r, c)) is not None
                     else "")
                    for c in range(self.table.columnCount())).lower()
                visible = text in row_text
            self.table.setRowHidden(r, not visible)

    # ================= локализация =================
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.sysworkspace.title"))
        for dk, btn in self._domain_buttons.items():
            btn.setText(_t(_DOMAIN_KEY[dk]))
        self.assistant_btn.setText(_t("panel.zones.btn.assistant"))
        self.compute_btn.setText(_t("panel.equipment.btn.compute"))
        self.undo_btn.setText(_t("panel.zones.btn.undo"))
        self.hint_lbl.setText(_t("panel.sysworkspace.hint"))
        self.add_sys_btn.setText(_t("panel.zones.btn.add_system"))
        self.add_circ_btn.setText(_t("panel.zones.btn.add_circuit"))
        self.rename_btn.setText(_t("panel.zones.btn.rename"))
        self.del_btn.setText(_t("panel.zones.btn.delete"))
        self.tree.setHeaderLabels([
            _t("panel.sysworkspace.tree.name"), _t("panel.sysworkspace.tree.kw")])
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.node_filter_cb.setText(_t("panel.sysworkspace.filter_node"))
        self.assign_sys_btn.setText(_t("panel.zones.btn.assign_system"))
        self.assign_circ_btn.setText(_t("panel.zones.btn.assign_circuit"))
        self.clear_btn.setText(_t("panel.zones.btn.clear"))
        self.device_btn.setText(_t("panel.sysworkspace.btn.device"))
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self._refresh()
