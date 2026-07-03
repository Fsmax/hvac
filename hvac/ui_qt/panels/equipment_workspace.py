# -*- coding: utf-8 -*-
"""EquipmentWorkspacePanel — раздел «Оборудование».

Отдельно от «Системы» (зонирование): здесь видно ВСЁ оборудование,
СГРУППИРОВАННОЕ ПО БЛОКАМ здания — работа ведётся по-блочно:

    категория (тепло / холод / вентиляция)
      └─ блок («HOTEL», …, «(без блока)»)
           └─ установка (→ контур)

Фильтр «Блок» сужает дерево до одного блока; новое оборудование
наследует блок выбранной группы (или активного фильтра). Правый клик
по установке — каталожный подбор (котлы/чиллеры) и смена блока; по
группе блока — добавить оборудование сразу в блок.

По выбору установки справа — ПОЛНАЯ карточка (просмотр + правка
параметров с живым пересчётом). Карточку строит `EquipmentDetailView`,
физику — `equipment_detail` / `equipment_sizing`. Создание/переименование/
удаление — через `ZoningMixin` ядра.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QMenu, QMessageBox, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.blocks import blocks_in_project
from hvac.equipment import VENTILATION_KINDS, make_ventilation_defaults
from hvac.equipment_sizing import EquipmentSelection, select_equipment
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.equipment_detail_view import EquipmentDetailView

# Qt.UserRole — (domain, "system"|"circuit", name) у установок/контуров;
# Qt.UserRole+2 — (domain, block) у строк-групп блока.
GROUP_ROLE = int(Qt.UserRole) + 2


# (категория, домен, ключ заголовка)
_CATEGORIES = [
    ("heating", "panel.equipws.cat.heat"),
    ("cooling", "panel.equipws.cat.cool"),
    ("ventilation", "panel.equipws.cat.vent"),
]


class EquipmentWorkspacePanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._sel: Optional[EquipmentSelection] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.equipws.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.compute_btn = QPushButton(_t("panel.equipment.btn.compute"))
        self.compute_btn.setProperty("role", "primary")
        self.compute_btn.setCursor(Qt.PointingHandCursor)
        self.compute_btn.clicked.connect(self._compute)
        head.addWidget(self.compute_btn)
        outer.addLayout(head)

        self.hint_lbl = QLabel(_t("panel.equipws.hint"))
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setWordWrap(True)
        outer.addWidget(self.hint_lbl)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, stretch=1)

        # ---------- LEFT: дерево + панель кнопок ----------
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.add_btn = QPushButton(_t("panel.equipws.btn.add"))
        self.add_btn.clicked.connect(self._show_add_menu)
        bar.addWidget(self.add_btn)
        self.rename_btn = QPushButton(_t("panel.zones.btn.rename"))
        self.rename_btn.clicked.connect(self._rename)
        bar.addWidget(self.rename_btn)
        self.del_btn = QPushButton(_t("panel.zones.btn.delete"))
        self.del_btn.clicked.connect(self._delete)
        bar.addWidget(self.del_btn)
        bar.addSpacing(12)
        self._blk_lbl = QLabel(_t("panel.blocks.filter.block"))
        bar.addWidget(self._blk_lbl)
        self.block_filter = QComboBox()
        self.block_filter.setMinimumWidth(120)
        self.block_filter.currentTextChanged.connect(
            lambda *_: self._refresh())
        bar.addWidget(self.block_filter)
        bar.addStretch(1)
        left_l.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([
            _t("panel.equipws.col.name"), _t("panel.equipws.col.power")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(lambda *_: self._on_select())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        left_l.addWidget(self.tree, stretch=1)
        splitter.addWidget(left)

        # ---------- RIGHT: карточка ----------
        self.detail = EquipmentDetailView(
            self.project, self.bridge, on_changed=self._on_detail_changed)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        for sig in (bridge.dataLoaded, bridge.projectLoaded, bridge.zonesChanged,
                    bridge.calculationDone, bridge.ventilationDone,
                    bridge.ahuLoadsCalculated, bridge.equipmentChanged):
            sig.connect(self._refresh)
        self._refresh()

    # ============================================== вспомогательное
    def _current(self):
        it = self.tree.currentItem()
        if it is None:
            return None
        return it.data(0, Qt.UserRole)        # (domain, kind, name) | None

    def _picked_kw(self, domain: str) -> dict:
        out: dict[str, str] = {}
        if self._sel is None or domain == "ventilation":
            return out
        for s in self._sel.sources(domain):
            if s.units:
                out[s.name] = _t("panel.equipment.fmt.units").format(
                    kw=f"{s.unit_kw:g}", n=s.units)
        return out

    # ============================================== блоки
    def _filter_block(self) -> Optional[str]:
        """None — все блоки; '' — «(без блока)»; иначе имя блока."""
        t = self.block_filter.currentText()
        if not t or t == _t("filter.all"):
            return None
        return "" if t == _t("panel.blocks.none") else t

    def _refresh_block_filter(self) -> None:
        all_label = _t("filter.all")
        items = ([all_label] + list(blocks_in_project(self.project))
                 + [_t("panel.blocks.none")])
        current = self.block_filter.currentText() or all_label
        self.block_filter.blockSignals(True)
        self.block_filter.clear()
        self.block_filter.addItems(items)
        idx = self.block_filter.findText(current)
        self.block_filter.setCurrentIndex(max(0, idx))
        self.block_filter.blockSignals(False)

    def _grouped(self, domain: str) -> Dict[str, List[str]]:
        """{блок: [имена систем]} — по явному полю block."""
        groups: Dict[str, List[str]] = {}
        for name, obj in self.project.systems_of(domain).items():
            groups.setdefault(getattr(obj, "block", "") or "", []).append(name)
        for names in groups.values():
            names.sort()
        return groups

    def _block_order(self, groups: Dict[str, List[str]]) -> List[str]:
        """Порядок реестра блоков; прочие по алфавиту; «(без блока)» в конце."""
        order = [b for b in blocks_in_project(self.project) if b in groups]
        order += sorted(b for b in groups if b and b not in order)
        if "" in groups:
            order.append("")
        return order

    def _group_power(self, domain: str, names: List[str]) -> str:
        """Подпись группы: Σ подобранных кВт (источники) или счётчик."""
        if domain != "ventilation" and self._sel is not None:
            nameset = set(names)
            kw = sum(s.unit_kw * s.units for s in self._sel.sources(domain)
                     if s.name in nameset and s.units)
            if kw > 0:
                return _t("panel.equipws.grp.kw").format(kw=f"{kw:g}")
        return str(len(names))

    # ============================================== отрисовка дерева
    def _refresh(self, *args: Any) -> None:
        self._sel = select_equipment(self.project)
        keep = self._current()
        self._refresh_block_filter()
        flt = self._filter_block()
        self.tree.blockSignals(True)
        self.tree.clear()
        for domain, key in _CATEGORIES:
            cat = QTreeWidgetItem([_t(key), ""])
            cat.setData(0, Qt.UserRole, None)
            f = cat.font(0)
            f.setBold(True)
            cat.setFont(0, f)
            self.tree.addTopLevelItem(cat)
            picked = self._picked_kw(domain)
            groups = self._grouped(domain)
            for blk in self._block_order(groups):
                if flt is not None and blk != flt:
                    continue
                names = groups[blk]
                grp = QTreeWidgetItem([blk or _t("panel.blocks.none"),
                                       self._group_power(domain, names)])
                grp.setData(0, Qt.UserRole, None)
                grp.setData(0, GROUP_ROLE, (domain, blk))
                if not blk:
                    fi = grp.font(0)
                    fi.setItalic(True)
                    grp.setFont(0, fi)
                cat.addChild(grp)
                for name in names:
                    node = QTreeWidgetItem([self._unit_label(domain, name),
                                            picked.get(name, "")])
                    node.setData(0, Qt.UserRole, (domain, "system", name))
                    grp.addChild(node)
                    for cname in self.project.circuits_of_system(domain, name):
                        child = QTreeWidgetItem([cname, ""])
                        child.setData(0, Qt.UserRole,
                                      (domain, "circuit", cname))
                        node.addChild(child)
                grp.setExpanded(True)
            cat.setExpanded(True)
        self.tree.blockSignals(False)
        self._reselect(keep)

    def _unit_label(self, domain: str, name: str) -> str:
        if domain == "ventilation":
            v = self.project.ventilation_systems.get(name)
            kind = getattr(v, "kind", "ahu") if v else "ahu"
            return f"{name}  ·  {_t('panel.detail.kind.' + kind, default=kind)}"
        return name

    def _reselect(self, data) -> None:
        if data is None:
            self.detail.clear()
            return
        it = self._find(data)
        if it is not None:
            self.tree.setCurrentItem(it)
        else:
            self.detail.clear()

    def _find(self, data) -> Optional[QTreeWidgetItem]:
        def walk(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            for i in range(item.childCount()):
                ch = item.child(i)
                if ch.data(0, Qt.UserRole) == data:
                    return ch
                found = walk(ch)
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            if cat is not None:
                found = walk(cat)
                if found is not None:
                    return found
        return None

    def _on_select(self) -> None:
        data = self._current()
        if not data:
            self.detail.clear()
            return
        domain, kind, name = data
        self.detail.show_node(domain, kind, name)

    def _on_detail_changed(self) -> None:
        self._sel = select_equipment(self.project)
        # обновляем подписи мощности в дереве, не сбрасывая карточку
        picked = {d: self._picked_kw(d) for d, _k in _CATEGORIES}
        self.tree.blockSignals(True)

        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                ch = item.child(i)
                d = ch.data(0, Qt.UserRole)
                grp = ch.data(0, GROUP_ROLE)
                if d and d[1] == "system":
                    ch.setText(1, picked.get(d[0], {}).get(d[2], ""))
                elif grp:
                    names = [ch.child(j).data(0, Qt.UserRole)[2]
                             for j in range(ch.childCount())
                             if ch.child(j).data(0, Qt.UserRole)]
                    ch.setText(1, self._group_power(grp[0], names))
                walk(ch)

        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            if cat is not None:
                walk(cat)
        self.tree.blockSignals(False)

    # ============================================== CRUD
    def _show_add_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(_t("panel.equipws.add.boiler"),
                       lambda: self._add_source("heating"))
        menu.addAction(_t("panel.equipws.add.chiller"),
                       lambda: self._add_source("cooling"))
        menu.addSeparator()
        for kind in VENTILATION_KINDS:
            menu.addAction(_t("panel.detail.kind." + kind),
                           lambda _c=False, k=kind: self._add_vent(k))
        menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))

    def _ask_name(self) -> str:
        name, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.add_system_title"),
            _t("panel.zones.dlg.system_name"))
        return name.strip() if ok else ""

    def _target_block(self) -> str:
        """Блок для нового оборудования: выбранная группа или фильтр."""
        it = self.tree.currentItem()
        while it is not None:
            grp = it.data(0, GROUP_ROLE)
            if grp:
                return grp[1]
            data = it.data(0, Qt.UserRole)
            if data:                    # установка/контур → её блок
                obj = self.project.systems_of(data[0]).get(data[2])
                if obj is not None:
                    return getattr(obj, "block", "") or ""
            it = it.parent()
        return self._filter_block() or ""

    def _add_source(self, domain: str, block: Optional[str] = None) -> None:
        name = self._ask_name()
        if name:
            self.project.add_zone_system(domain, name)
            blk = self._target_block() if block is None else block
            if blk:
                self.project.update_zone_system(domain, name, block=blk)
            self.bridge.dirtyChanged.emit(True)
            self._refresh()
            self._select_unit(domain, name)

    def _add_vent(self, kind: str, block: Optional[str] = None) -> None:
        name = self._ask_name()
        if name:
            self.project.add_zone_system("ventilation", name,
                                         **make_ventilation_defaults(kind))
            blk = self._target_block() if block is None else block
            if blk:
                self.project.update_zone_system("ventilation", name,
                                                block=blk)
            self.bridge.dirtyChanged.emit(True)
            self._refresh()
            self._select_unit("ventilation", name)

    def _select_unit(self, domain: str, name: str) -> None:
        it = self._find((domain, "system", name))
        if it is not None:
            self.tree.setCurrentItem(it)

    def _rename(self) -> None:
        data = self._current()
        if not data:
            return
        domain, kind, name = data
        new, ok = QInputDialog.getText(
            self, _t("panel.zones.dlg.rename_title"),
            _t("panel.zones.dlg.new_name"), text=name)
        if not ok or not new.strip() or new.strip() == name:
            return
        if kind == "system":
            self.project.rename_zone_system(domain, name, new.strip())
        else:
            self.project.rename_zone_circuit(domain, name, new.strip())
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _delete(self) -> None:
        data = self._current()
        if not data:
            return
        domain, kind, name = data
        msg = (_t("panel.zones.confirm.delete_system") if kind == "system"
               else _t("panel.zones.confirm.delete_circuit")).format(name=name)
        if QMessageBox.question(self, _t("panel.zones.confirm.title"),
                                msg) != QMessageBox.Yes:
            return
        if kind == "system":
            self.project.remove_zone_system(domain, name)
        else:
            self.project.remove_zone_circuit(domain, name)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    # ============================================== контекстное меню
    def _tree_menu(self, pos) -> None:
        it = self.tree.itemAt(pos)
        if it is None:
            return
        data = it.data(0, Qt.UserRole)
        grp = it.data(0, GROUP_ROLE)
        menu = QMenu(self)
        if data and data[1] == "system":
            domain, _kind, name = data
            if domain in ("heating", "cooling"):
                menu.addAction(_t("panel.detail.btn.catalog"),
                               lambda: self._pick_catalog_for(it))
                menu.addSeparator()
            sub = menu.addMenu(_t("panel.equipws.menu.block"))
            sub.addAction(_t("panel.blocks.none"),
                          lambda _c=False: self._set_block(domain, name, ""))
            for b in blocks_in_project(self.project):
                sub.addAction(b, lambda _c=False, blk=b:
                              self._set_block(domain, name, blk))
        elif grp:
            domain, blk = grp
            if domain == "heating":
                menu.addAction(_t("panel.equipws.add.boiler"),
                               lambda: self._add_source(domain, block=blk))
            elif domain == "cooling":
                menu.addAction(_t("panel.equipws.add.chiller"),
                               lambda: self._add_source(domain, block=blk))
            else:
                for kind in VENTILATION_KINDS:
                    menu.addAction(_t("panel.detail.kind." + kind),
                                   lambda _c=False, k=kind:
                                   self._add_vent(k, block=blk))
        else:
            return
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_block(self, domain: str, name: str, blk: str) -> None:
        self.project.update_zone_system(domain, name, block=blk)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _pick_catalog_for(self, item: QTreeWidgetItem) -> None:
        self.tree.setCurrentItem(item)      # карточка покажет источник
        self.detail.pick_from_catalog()

    # ============================================== пересчёт
    def _compute(self) -> None:
        from hvac.air_heating import apply_air_heating
        apply_air_heating(self.project)
        for step in (self.project.calculate_ahu_loads, self.project.size_pipes,
                     self.project.design_heating_hydraulics,
                     self.project.size_cooling_pipes):
            try:
                step()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "equipment: step %s failed", getattr(step, "__name__", "?"))
        self._refresh()
        self.bridge.statusMessage.emit(_t("panel.equipment.status.computed"), 4000)

    # ============================================== i18n
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.equipws.title"))
        self.hint_lbl.setText(_t("panel.equipws.hint"))
        self.compute_btn.setText(_t("panel.equipment.btn.compute"))
        self.add_btn.setText(_t("panel.equipws.btn.add"))
        self.rename_btn.setText(_t("panel.zones.btn.rename"))
        self.del_btn.setText(_t("panel.zones.btn.delete"))
        self._blk_lbl.setText(_t("panel.blocks.filter.block"))
        self.tree.setHeaderLabels([
            _t("panel.equipws.col.name"), _t("panel.equipws.col.power")])
        self.detail.retranslate_ui()
        self._refresh()
