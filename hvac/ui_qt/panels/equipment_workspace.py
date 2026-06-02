# -*- coding: utf-8 -*-
"""EquipmentWorkspacePanel — раздел «Оборудование».

Отдельно от «Системы» (зонирование): здесь видно ВСЁ оборудование одним
списком по категориям — источники тепла, источники холода, вентиляция, —
а по выбору установки справа показывается ПОЛНАЯ карточка (просмотр + правка
параметров с живым пересчётом).

Левое дерево: категория → установка (→ контур). Карточку строит
`EquipmentDetailView`, физику — `equipment_detail` / `equipment_sizing`.
Создание/переименование/удаление — через `ZoningMixin` ядра.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu,
    QMessageBox, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from hvac.equipment import VENTILATION_KINDS, make_ventilation_defaults
from hvac.equipment_sizing import select_equipment
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.equipment_detail_view import EquipmentDetailView


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
        self._sel = None

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

    # ============================================== отрисовка дерева
    def _refresh(self, *args: Any) -> None:
        self._sel = select_equipment(self.project)
        keep = self._current()
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
            for name in sorted(self.project.systems_of(domain).keys()):
                node = QTreeWidgetItem([self._unit_label(domain, name),
                                        picked.get(name, "")])
                node.setData(0, Qt.UserRole, (domain, "system", name))
                cat.addChild(node)
                for cname in self.project.circuits_of_system(domain, name):
                    child = QTreeWidgetItem([cname, ""])
                    child.setData(0, Qt.UserRole, (domain, "circuit", cname))
                    node.addChild(child)
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
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                node = cat.child(j)
                if node.data(0, Qt.UserRole) == data:
                    return node
                for k in range(node.childCount()):
                    ch = node.child(k)
                    if ch.data(0, Qt.UserRole) == data:
                        return ch
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
        keep = self._current()
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            domain = _CATEGORIES[i][0]
            picked = self._picked_kw(domain)
            for j in range(cat.childCount()):
                node = cat.child(j)
                d = node.data(0, Qt.UserRole)
                if d:
                    node.setText(1, picked.get(d[2], ""))
        self.tree.blockSignals(False)
        keep  # selection unchanged

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

    def _add_source(self, domain: str) -> None:
        name = self._ask_name()
        if name:
            self.project.add_zone_system(domain, name)
            self.bridge.dirtyChanged.emit(True)
            self._refresh()
            self._select_unit(domain, name)

    def _add_vent(self, kind: str) -> None:
        name = self._ask_name()
        if name:
            self.project.add_zone_system("ventilation", name,
                                         **make_ventilation_defaults(kind))
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
        self.tree.setHeaderLabels([
            _t("panel.equipws.col.name"), _t("panel.equipws.col.power")])
        self.detail.retranslate_ui()
        self._refresh()
