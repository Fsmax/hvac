# -*- coding: utf-8 -*-
"""Компоненты зонирования: сортируемые элементы таблиц/деревьев, дерево систем с drag&drop и диалог контура.

Исторически здесь жила панель «Зоны и системы»; её заменил единый рабочий стол systems_workspace, который импортирует эти компоненты. Мёртвый класс ZonesPanel удалён при ревизии UI (F11).
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from hvac.i18n import t as _t


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


class _NumTableItem(QTableWidgetItem):
    """Ячейка таблицы, сортируемая по числу, а не по тексту («100» > «20»)."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self._value = value

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, _NumTableItem):
            return self._value < other._value
        return super().__lt__(other)


class _NumTreeItem(QTreeWidgetItem):
    """Узел дерева: имя сортируется без учёта регистра, счётчик — численно."""

    def __lt__(self, other: Any) -> bool:
        tree = self.treeWidget()
        col = tree.sortColumn() if tree is not None else 0
        if col == 1:                       # колонка-счётчик помещений
            def _iv(s: str) -> int:
                try:
                    return int(s)
                except ValueError:
                    return 0
            return _iv(self.text(1)) < _iv(other.text(1))
        return self.text(col).lower() < other.text(col).lower()


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
