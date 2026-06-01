# -*- coding: utf-8 -*-
"""ZonesPanel — единый рабочий стол «Зоны и системы».

Ручное зонирование: слева дерево Система → Контур (создать / переименовать /
удалить), справа таблица помещений с массовым назначением. Помещение можно
отнести к системе или контуру тремя способами: кнопкой над таблицей,
перетаскиванием выделенных строк на узел дерева или из контекстного меню.

Три домена (Отопление / Холод / Вентиляция) переключаются вкладками сверху:
у каждого свои системы, контуры (для вентиляции — зоны воздуховодов) и
своя колонка нагрузки. Авто-присвоение из прежней версии оставлено как
необязательный «Помощник» — основной упор на ручную работу.

Логика CRUD и назначения живёт в ядре (`hvac/_project_zoning.py`,
`ZoningMixin`); панель — только представление + отмена на снимках полей
зонирования (как в RoomEquipmentPanel).
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


# Порядок и подписи доменов (вкладки сверху).
_DOMAIN_ORDER = ("heating", "cooling", "ventilation")
_DOMAIN_KEY = {
    "heating": "panel.zones.domain.heating",
    "cooling": "panel.zones.domain.cooling",
    "ventilation": "panel.zones.domain.ventilation",
}
_LOAD_KEY = {
    "heating": "panel.zones.load.heating",
    "cooling": "panel.zones.load.cooling",
    "ventilation": "panel.zones.load.ventilation",
}
_ROOM_COL_KEYS = [
    "panel.zones.rcol.number", "panel.zones.rcol.name", "panel.zones.rcol.area",
    "panel.zones.rcol.load", "panel.zones.rcol.system", "panel.zones.rcol.circuit",
]


def _ctype_label(ctype: str) -> str:
    """Человекочитаемое имя типа контура (radiator → «Радиаторы»)."""
    if not ctype:
        return ""
    return _t("panel.zones.ctype." + ctype, default=ctype)


def _load_value(domain: str, sp) -> float:
    """Нагрузка помещения, релевантная домену (для колонки и сводки)."""
    if domain == "heating":
        return sp.heat_loss_w / 1000.0
    if domain == "cooling":
        return sp.heat_gain_w / 1000.0
    return sp.supply_m3h


class _ZoneTree(QTreeWidget):
    """Дерево систем/контуров, принимающее drop помещений из таблицы.

    Полезной нагрузки в drag нет — при drop панель берёт текущее выделение
    своей таблицы. Узел хранит (kind, name) в Qt.UserRole.
    """

    def __init__(self, on_drop) -> None:
        super().__init__()
        self._on_drop = on_drop
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def _point(self, event) -> Any:
        pos = getattr(event, "position", None)
        return pos().toPoint() if pos is not None else event.pos()

    def dragEnterEvent(self, event) -> None:
        if event.source() is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        item = self.itemAt(self._point(event))
        if item is not None and event.source() is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        item = self.itemAt(self._point(event))
        if item is not None and event.source() is not None:
            self._on_drop(item)
            event.acceptProposedAction()
        else:
            event.ignore()


class _CircuitDialog(QDialog):
    """Диалог создания контура: имя + тип + родительская система."""

    def __init__(self, parent: QWidget, *, domain: str, types: list[str],
                 systems: list[str], preset_system: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("panel.zones.dlg.add_circuit_title"))
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.name_edit = QLineEdit()
        form.addRow(_t("panel.zones.dlg.circuit_name"), self.name_edit)

        self.type_combo: Optional[QComboBox] = None
        if types:
            self.type_combo = QComboBox()
            for ct in types:
                self.type_combo.addItem(_ctype_label(ct), userData=ct)
            form.addRow(_t("panel.zones.dlg.circuit_type"), self.type_combo)

        self.sys_combo = QComboBox()
        self.sys_combo.setEditable(True)
        self.sys_combo.addItems(systems)
        if preset_system:
            self.sys_combo.setCurrentText(preset_system)
        form.addRow(_t("panel.zones.dlg.parent_system"), self.sys_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("btn.ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        ctype = (self.type_combo.currentData()
                 if self.type_combo is not None else "")
        return {
            "name": self.name_edit.text().strip(),
            "circuit_type": ctype or "",
            "parent_system": self.sys_combo.currentText().strip(),
        }


class ZonesPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._domain = "heating"
        self._undo: list[dict] = []        # стек снимков полей зонирования

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ----- Заголовок + переключатель доменов + помощник/отмена -----
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.zones.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addSpacing(16)

        self.domain_group = QButtonGroup(self)
        self.domain_group.setExclusive(True)
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
        self.undo_btn = QPushButton(_t("panel.zones.btn.undo"))
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self._apply_undo)
        head.addWidget(self.undo_btn)
        outer.addLayout(head)

        self.hint_lbl = QLabel(_t("panel.zones.hint"))
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setWordWrap(True)
        outer.addWidget(self.hint_lbl)

        # ----- Сплиттер: дерево слева, таблица справа -----
        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, stretch=1)

        # Левая колонка
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        self.tree_title_lbl = QLabel(_t("panel.zones.tree.title"))
        self.tree_title_lbl.setProperty("role", "h2")
        left_l.addWidget(self.tree_title_lbl)

        tree_bar = QHBoxLayout()
        self.add_sys_btn = QPushButton(_t("panel.zones.btn.add_system"))
        self.add_sys_btn.clicked.connect(self._add_system)
        tree_bar.addWidget(self.add_sys_btn)
        self.add_circ_btn = QPushButton(_t("panel.zones.btn.add_circuit"))
        self.add_circ_btn.clicked.connect(self._add_circuit)
        tree_bar.addWidget(self.add_circ_btn)
        self.rename_btn = QPushButton(_t("panel.zones.btn.rename"))
        self.rename_btn.clicked.connect(self._rename_node)
        tree_bar.addWidget(self.rename_btn)
        self.del_btn = QPushButton(_t("panel.zones.btn.delete"))
        self.del_btn.clicked.connect(self._delete_node)
        tree_bar.addWidget(self.del_btn)
        tree_bar.addStretch(1)
        left_l.addLayout(tree_bar)

        self.tree = _ZoneTree(self._on_rooms_dropped)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([
            _t("panel.zones.tree.col.name"), _t("panel.zones.tree.col.count")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(lambda *_: self._rename_node())
        left_l.addWidget(self.tree, stretch=1)
        splitter.addWidget(left)

        # Правая колонка
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        self.rooms_title_lbl = QLabel(_t("panel.zones.rooms.title"))
        self.rooms_title_lbl.setProperty("role", "h2")
        right_l.addWidget(self.rooms_title_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        right_l.addWidget(self.search)

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
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        for i, w in enumerate([70, 220, 80, 110, 150, 150]):
            self.table.setColumnWidth(i, w)
        right_l.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        self.assign_sys_btn = QPushButton(_t("panel.zones.btn.assign_system"))
        self.assign_sys_btn.setProperty("role", "primary")
        self.assign_sys_btn.setCursor(Qt.PointingHandCursor)
        self.assign_sys_btn.clicked.connect(self._show_assign_system_menu)
        btn_row.addWidget(self.assign_sys_btn)
        self.assign_circ_btn = QPushButton(_t("panel.zones.btn.assign_circuit"))
        self.assign_circ_btn.setCursor(Qt.PointingHandCursor)
        self.assign_circ_btn.clicked.connect(self._show_assign_circuit_menu)
        btn_row.addWidget(self.assign_circ_btn)
        self.clear_btn = QPushButton(_t("panel.zones.btn.clear"))
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_selected)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "muted")
        btn_row.addWidget(self.summary_lbl)
        right_l.addLayout(btn_row)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.zonesChanged, bridge.calculationDone,
                    bridge.ventilationDone):
            sig.connect(self._refresh)
        self._refresh()

    # ================= helpers =================
    def _room_headers(self) -> list[str]:
        heads = [_t(k) for k in _ROOM_COL_KEYS]
        heads[3] = _t(_LOAD_KEY[self._domain])     # колонка нагрузки по домену
        return heads

    def _selected_rows(self) -> list[int]:
        sel = self.table.selectionModel()
        if sel is None:
            return []
        return sorted({idx.row() for idx in sel.selectedRows()})

    def _ids_for(self, rows: list[int]) -> list[str]:
        return [self.project.spaces[r].space_id for r in rows
                if 0 <= r < len(self.project.spaces)]

    def _selected_ids(self) -> list[str]:
        return self._ids_for(self._selected_rows())

    def _warn_no_selection(self) -> None:
        QMessageBox.information(self, _t("panel.zones.title"),
                                _t("panel.zones.msg.no_selection"))

    def _push_undo(self, ids: list[str]) -> None:
        self._undo.append(self.project.snapshot_zoning(ids))
        del self._undo[:-50]

    def _apply_undo(self) -> None:
        if not self._undo:
            return
        snap = self._undo.pop()
        n = self.project.restore_zoning(snap)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.undone").format(n=n), 3000)

    # ================= домен =================
    def _switch_domain(self, domain: str) -> None:
        if domain == self._domain:
            return
        self._domain = domain
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self._refresh()

    # ================= системы / контуры (CRUD) =================
    def _systems_sorted(self) -> list[str]:
        return sorted(self.project.systems_of(self._domain).keys())

    def _add_system(self) -> None:
        name, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.add_system_title"),
            _t("panel.zones.dlg.system_name"))
        if ok and name.strip():
            self.project.add_zone_system(self._domain, name.strip())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _add_circuit(self) -> None:
        systems = self._systems_sorted()
        sel = self.tree.currentItem()
        preset = ""
        if sel is not None:
            kind, name = sel.data(0, Qt.UserRole) or ("", "")
            preset = name if kind == "system" else self.project.circuit_parent(
                self._domain, name)
        dlg = _CircuitDialog(
            self, domain=self._domain,
            types=self.project.circuit_types_for(self._domain),
            systems=systems, preset_system=preset)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if not v["name"] or not v["parent_system"]:
            return
        self.project.add_zone_circuit(
            self._domain, v["name"], v["parent_system"],
            circuit_type=v["circuit_type"])
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _rename_node(self) -> None:
        sel = self.tree.currentItem()
        if sel is None:
            return
        kind, name = sel.data(0, Qt.UserRole) or ("", "")
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
        sel = self.tree.currentItem()
        if sel is None:
            return
        kind, name = sel.data(0, Qt.UserRole) or ("", "")
        if not kind:
            return
        msg = (_t("panel.zones.confirm.delete_system")
               if kind == "system"
               else _t("panel.zones.confirm.delete_circuit")).format(name=name)
        if QMessageBox.question(
                self, _t("panel.zones.confirm.title"), msg) != \
                QMessageBox.Yes:
            return
        if kind == "system":
            self.project.remove_zone_system(self._domain, name)
        else:
            self.project.remove_zone_circuit(self._domain, name)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

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

    # ================= меню =================
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
        menu.addAction(_t("panel.zones.menu.new_circuit"), self._add_circuit_assign)
        menu.exec(self.assign_circ_btn.mapToGlobal(
            self.assign_circ_btn.rect().bottomLeft()))

    def _add_circuit_assign(self) -> None:
        """Создать контур и сразу назначить ему выделенные помещения."""
        dlg = _CircuitDialog(
            self, domain=self._domain,
            types=self.project.circuit_types_for(self._domain),
            systems=self._systems_sorted())
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if not v["name"] or not v["parent_system"]:
            return
        name = self.project.add_zone_circuit(
            self._domain, v["name"], v["parent_system"],
            circuit_type=v["circuit_type"])
        self._assign_to_circuit(name)

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
        all_ids = [sp.space_id for sp in self.project.spaces]
        self._push_undo(all_ids)
        n = self.project.auto_assign_zones(
            mode=mode, overwrite=True, system=self._domain)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.zones.status.assigned_sys").format(n=n), 4000)

    def _show_context_menu(self, pos) -> None:
        if not self.project.spaces:
            return
        if not self._selected_rows():
            return
        menu = QMenu(self)
        menu.addAction(_t("panel.zones.btn.assign_system"),
                       self._show_assign_system_menu)
        menu.addAction(_t("panel.zones.btn.assign_circuit"),
                       self._show_assign_circuit_menu)
        menu.addAction(_t("panel.zones.btn.clear"), self._clear_selected)
        menu.addSeparator()
        act_undo = menu.addAction(_t("panel.zones.btn.undo"), self._apply_undo)
        act_undo.setEnabled(bool(self._undo))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ================= отрисовка =================
    def _refresh(self, *args: Any) -> None:
        self._refresh_tree()
        self._refresh_table()
        self._refresh_summary()
        self.undo_btn.setEnabled(bool(self._undo))

    def _refresh_tree(self) -> None:
        self.tree.clear()
        domain = self._domain
        systems = self.project.systems_of(domain)
        sys_field, circ_field = self.project.zoning_space_fields(domain)
        # счётчики помещений по системе/контуру
        sys_count: dict[str, int] = {}
        circ_count: dict[str, int] = {}
        for sp in self.project.spaces:
            sv = getattr(sp, sys_field, "")
            cv = getattr(sp, circ_field, "")
            if sv:
                sys_count[sv] = sys_count.get(sv, 0) + 1
            if cv:
                circ_count[cv] = circ_count.get(cv, 0) + 1

        for sname in sorted(systems.keys()):
            sitem = QTreeWidgetItem([sname, str(sys_count.get(sname, 0))])
            sitem.setData(0, Qt.UserRole, ("system", sname))
            self.tree.addTopLevelItem(sitem)
            for cname in self.project.circuits_of_system(domain, sname):
                c = self.project.circuits_of(domain).get(cname)
                ctype = getattr(c, "circuit_type", "") if c else ""
                label = cname if not ctype else f"{cname}  ·  {_ctype_label(ctype)}"
                citem = QTreeWidgetItem([label, str(circ_count.get(cname, 0))])
                citem.setData(0, Qt.UserRole, ("circuit", cname))
                sitem.addChild(citem)
            sitem.setExpanded(True)

    def _refresh_table(self) -> None:
        domain = self._domain
        sys_field, circ_field = self.project.zoning_space_fields(domain)
        is_flow = domain == "ventilation"
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            load = _load_value(domain, sp)
            load_txt = f"{load:.0f}" if is_flow else f"{load:.2f}"
            cells = [
                sp.number, sp.name, f"{sp.area_m2:.0f}",
                load_txt if load else "",
                getattr(sp, sys_field, "") or "",
                getattr(sp, circ_field, "") or "",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c in (2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self._filter(self.search.text())

    def _refresh_summary(self) -> None:
        domain = self._domain
        sys_field, _ = self.project.zoning_space_fields(domain)
        n_sys = len(self.project.systems_of(domain))
        n_rooms = len(self.project.spaces)
        n_assigned = sum(1 for sp in self.project.spaces
                         if getattr(sp, sys_field, ""))
        self.summary_lbl.setText(_t("panel.zones.summary.line").format(
            systems=n_sys, assigned=n_assigned, rooms=n_rooms))

    def _filter(self, text: str) -> None:
        t = (text or "").lower().strip()
        for r in range(self.table.rowCount()):
            visible = True
            if t:
                row_text = " ".join(
                    (it.text() if (it := self.table.item(r, c)) is not None else "")
                    for c in range(self.table.columnCount())
                ).lower()
                visible = t in row_text
            self.table.setRowHidden(r, not visible)

    # ================= локализация =================
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.zones.title"))
        for dk, btn in self._domain_buttons.items():
            btn.setText(_t(_DOMAIN_KEY[dk]))
        self.assistant_btn.setText(_t("panel.zones.btn.assistant"))
        self.undo_btn.setText(_t("panel.zones.btn.undo"))
        self.hint_lbl.setText(_t("panel.zones.hint"))
        self.tree_title_lbl.setText(_t("panel.zones.tree.title"))
        self.add_sys_btn.setText(_t("panel.zones.btn.add_system"))
        self.add_circ_btn.setText(_t("panel.zones.btn.add_circuit"))
        self.rename_btn.setText(_t("panel.zones.btn.rename"))
        self.del_btn.setText(_t("panel.zones.btn.delete"))
        self.tree.setHeaderLabels([
            _t("panel.zones.tree.col.name"), _t("panel.zones.tree.col.count")])
        self.rooms_title_lbl.setText(_t("panel.zones.rooms.title"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.assign_sys_btn.setText(_t("panel.zones.btn.assign_system"))
        self.assign_circ_btn.setText(_t("panel.zones.btn.assign_circuit"))
        self.clear_btn.setText(_t("panel.zones.btn.clear"))
        self.table.setHorizontalHeaderLabels(self._room_headers())
        self._refresh()
