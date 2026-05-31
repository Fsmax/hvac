# -*- coding: utf-8 -*-
"""Диалоги для ручного ввода помещений: одно помещение и массовый шаблон."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.catalogs.room_types import get_all_room_types
from hvac.i18n import t as _t


@dataclass
class SpaceFormResult:
    number: str
    name: str
    level: str
    area_m2: float
    height_m: float
    room_type: str


class SpaceDialog(QDialog):
    """Создание / редактирование одного помещения."""

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 initial: Optional[SpaceFormResult] = None,
                 known_levels: Optional[List[str]] = None,
                 title: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle(title if title is not None
                              else _t("dlg.space.title_new"))
        self.setMinimumWidth(420)

        form = QFormLayout(self)

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText(_t("dlg.space.number_ph"))
        form.addRow(_t("dlg.space.number"), self.number_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(_t("dlg.space.name_ph"))
        form.addRow(_t("dlg.space.name"), self.name_edit)

        self.level_combo = QComboBox()
        self.level_combo.setEditable(True)
        for lvl in (known_levels or []):
            self.level_combo.addItem(lvl)
        if not (known_levels and len(known_levels)):
            for key in ("dlg.space.lvl_1", "dlg.space.lvl_2", "dlg.space.lvl_3"):
                self.level_combo.addItem(_t(key))
        form.addRow(_t("dlg.space.level"), self.level_combo)

        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.1, 10000.0)
        self.area_spin.setDecimals(2)
        self.area_spin.setSuffix(" м²")
        self.area_spin.setValue(20.0)
        form.addRow(_t("dlg.space.area"), self.area_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1.5, 15.0)
        self.height_spin.setDecimals(2)
        self.height_spin.setSuffix(" м")
        self.height_spin.setValue(3.0)
        form.addRow(_t("dlg.space.height"), self.height_spin)

        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(get_all_room_types())
        form.addRow(_t("dlg.space.type"), self.type_combo)

        # Заполнить если initial
        if initial:
            self.number_edit.setText(initial.number)
            self.name_edit.setText(initial.name)
            self.level_combo.setCurrentText(initial.level)
            self.area_spin.setValue(initial.area_m2)
            self.height_spin.setValue(initial.height_m or 3.0)
            self.type_combo.setCurrentText(initial.room_type)

        # OK / Отмена
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def result_value(self) -> SpaceFormResult:
        return SpaceFormResult(
            number=self.number_edit.text().strip(),
            name=self.name_edit.text().strip(),
            level=self.level_combo.currentText().strip(),
            area_m2=float(self.area_spin.value()),
            height_m=float(self.height_spin.value()),
            room_type=(self.type_combo.currentText().strip()
                       or _t("dlg.space.default_type")),
        )


# ===========================================================================
# Массовый шаблон жилого дома
# ===========================================================================
@dataclass
class BuildingTemplateRoom:
    name: str
    room_type: str
    area_m2: float


@dataclass
class BuildingTemplateResult:
    n_floors: int
    first_floor_number: int           # 1 — обычно
    apartments_per_floor: int
    rooms_per_apartment: List[BuildingTemplateRoom]
    height_m: float
    level_prefix: str                  # «Этаж », «Floor », …


def _default_apt_rooms() -> List[BuildingTemplateRoom]:
    """Дефолтный состав квартиры. Считается лениво, чтобы локаль успела
    инициализироваться к моменту построения диалога."""
    return [
        BuildingTemplateRoom(_t("dlg.bldg.tpl.living"),
                               _t("dlg.bldg.default_type"), 22.0),
        BuildingTemplateRoom(_t("dlg.bldg.tpl.bedroom1"),
                               _t("dlg.bldg.default_type"), 14.0),
        BuildingTemplateRoom(_t("dlg.bldg.tpl.bedroom2"),
                               _t("dlg.bldg.default_type"), 12.0),
        BuildingTemplateRoom(_t("dlg.bldg.tpl.kitchen"),
                               "Ресторан / кухня", 10.0),
        BuildingTemplateRoom(_t("dlg.bldg.tpl.bathroom"),
                               "Санузел", 4.0),
        BuildingTemplateRoom(_t("dlg.bldg.tpl.corridor"),
                               "Коридор", 6.0),
    ]


class BuildingTemplateDialog(QDialog):
    """Шаблон «N этажей × M квартир × K комнат»."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(_t("dlg.bldg.title"))
        self.resize(640, 520)

        root = QVBoxLayout(self)

        # Верх — параметры
        top = QFormLayout()
        self.floors_spin = QSpinBox()
        self.floors_spin.setRange(1, 60)
        self.floors_spin.setValue(5)
        top.addRow(_t("dlg.bldg.floors"), self.floors_spin)

        self.first_floor_spin = QSpinBox()
        self.first_floor_spin.setRange(-5, 60)
        self.first_floor_spin.setValue(1)
        top.addRow(_t("dlg.bldg.first_floor"), self.first_floor_spin)

        self.apt_spin = QSpinBox()
        self.apt_spin.setRange(1, 50)
        self.apt_spin.setValue(4)
        top.addRow(_t("dlg.bldg.apts"), self.apt_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(2.0, 6.0)
        self.height_spin.setDecimals(2)
        self.height_spin.setSuffix(" м")
        self.height_spin.setValue(3.0)
        top.addRow(_t("dlg.bldg.height"), self.height_spin)

        self.prefix_edit = QLineEdit(_t("dlg.bldg.level_prefix"))
        top.addRow(_t("dlg.bldg.prefix"), self.prefix_edit)
        root.addLayout(top)

        # Таблица комнат
        lbl = QLabel(_t("dlg.bldg.composition"))
        lbl.setTextFormat(Qt.RichText)
        root.addWidget(lbl)

        self.rooms_table = QTableWidget(0, 3)
        self.rooms_table.setHorizontalHeaderLabels([
            _t("dlg.bldg.col_name"),
            _t("dlg.bldg.col_type"),
            _t("dlg.bldg.col_area"),
        ])
        self.rooms_table.verticalHeader().setVisible(False)
        self.rooms_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.rooms_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        root.addWidget(self.rooms_table, stretch=1)

        # Кнопки таблицы
        bar = QHBoxLayout()
        b_add = QPushButton(_t("dlg.bldg.btn_add"))
        b_del = QPushButton(_t("dlg.bldg.btn_delete"))
        bar.addWidget(b_add)
        bar.addWidget(b_del)
        bar.addStretch(1)
        self.total_lbl = QLabel("")
        bar.addWidget(self.total_lbl)
        root.addLayout(bar)

        b_add.clicked.connect(lambda: self._add_row(
            BuildingTemplateRoom(_t("dlg.bldg.default_room"),
                                   _t("dlg.bldg.default_type"), 10.0)))
        b_del.clicked.connect(self._del_row)

        # OK/Отмена
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        # Заполнить дефолтным составом
        for r in _default_apt_rooms():
            self._add_row(r)

        for w in (self.floors_spin, self.apt_spin):
            w.valueChanged.connect(self._refresh_total)
        self.rooms_table.itemChanged.connect(lambda *_: self._refresh_total())
        self._refresh_total()

    def _add_row(self, r: BuildingTemplateRoom) -> None:
        row = self.rooms_table.rowCount()
        self.rooms_table.insertRow(row)
        self.rooms_table.setItem(row, 0, QTableWidgetItem(r.name))

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(get_all_room_types())
        combo.setCurrentText(r.room_type)
        self.rooms_table.setCellWidget(row, 1, combo)

        area_item = QTableWidgetItem(f"{r.area_m2:g}")
        area_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.rooms_table.setItem(row, 2, area_item)
        self._refresh_total()

    def _del_row(self) -> None:
        row = self.rooms_table.currentRow()
        if row >= 0:
            self.rooms_table.removeRow(row)
            self._refresh_total()

    def _collect_rooms(self) -> List[BuildingTemplateRoom]:
        out: List[BuildingTemplateRoom] = []
        default_type = _t("dlg.space.default_type")
        for row in range(self.rooms_table.rowCount()):
            name_item = self.rooms_table.item(row, 0)
            combo = self.rooms_table.cellWidget(row, 1)
            area_item = self.rooms_table.item(row, 2)
            try:
                area = float((area_item.text() if area_item else "0")
                             .replace(",", "."))
            except (TypeError, ValueError):
                area = 0.0
            name = (name_item.text() if name_item else "").strip()
            rtype = (combo.currentText() if combo else default_type).strip() or default_type
            if name and area > 0:
                out.append(BuildingTemplateRoom(name, rtype, area))
        return out

    def _refresh_total(self) -> None:
        rooms = self._collect_rooms()
        total = (self.floors_spin.value() * self.apt_spin.value()
                 * len(rooms))
        area = (self.floors_spin.value() * self.apt_spin.value()
                * sum(r.area_m2 for r in rooms))
        self.total_lbl.setText(_t("dlg.bldg.total").format(n=total, area=area))
        self.total_lbl.setTextFormat(Qt.RichText)

    def result_value(self) -> BuildingTemplateResult:
        return BuildingTemplateResult(
            n_floors=self.floors_spin.value(),
            first_floor_number=self.first_floor_spin.value(),
            apartments_per_floor=self.apt_spin.value(),
            rooms_per_apartment=self._collect_rooms(),
            height_m=self.height_spin.value(),
            level_prefix=self.prefix_edit.text() or _t("dlg.bldg.level_prefix"),
        )
