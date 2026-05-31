# -*- coding: utf-8 -*-
"""BoundariesPanel — таблица ограждений выбранного помещения.

Размещается под PropertiesPanel в SpacesPanel. Позволяет вручную
добавлять стены, окна, двери, покрытия, полы. Конструкция выбирается
из каталога проекта; U/SHGC подтягиваются автоматически.
"""
from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.data_loader import is_excluded_category
from hvac.i18n import on_language_change, t as _t
from hvac.models import BoundaryElement, Construction, Space
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


_ORIENTATIONS = ("", "N", "NE", "E", "SE", "S", "SW", "W", "NW")
_CATEGORIES = ("Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол")

_HEADER_KEYS = (
    "panel.boundaries.col.category",
    "panel.boundaries.col.construction",
    "panel.boundaries.col.area",
    "panel.boundaries.col.orient",
    "panel.boundaries.col.u",
    "panel.boundaries.col.ext",
)


class _AddElementDialog(QDialog):
    """Диалог добавления одного элемента ограждения."""

    def __init__(self, project: HVACProject, space: Space,
                 default_category: str = "Стены",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.space = space
        self.setWindowTitle(_t("panel.boundaries.dlg.title").format(
            number=space.number, name=space.name))
        self.setMinimumWidth(440)

        form = QFormLayout(self)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(_CATEGORIES)
        self.cat_combo.setCurrentText(default_category)
        self.cat_combo.currentTextChanged.connect(self._refresh_constructions)
        form.addRow(_t("panel.boundaries.dlg.category"), self.cat_combo)

        self.con_combo = QComboBox()
        self.con_combo.setEditable(True)
        form.addRow(_t("panel.boundaries.dlg.construction"), self.con_combo)

        self.exterior_combo = QComboBox()
        self._ext_label = _t("panel.boundaries.dlg.bnd_ext")
        self.exterior_combo.addItems([
            self._ext_label, _t("panel.boundaries.dlg.bnd_int")])
        form.addRow(_t("panel.boundaries.dlg.bnd_type"), self.exterior_combo)

        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.01, 2000.0)
        self.area_spin.setDecimals(2)
        self.area_spin.setSuffix(" м²")
        self.area_spin.setValue(10.0)
        form.addRow(_t("panel.boundaries.dlg.area"), self.area_spin)

        self.orient_combo = QComboBox()
        self.orient_combo.addItems(_ORIENTATIONS)
        form.addRow(_t("panel.boundaries.dlg.orient"), self.orient_combo)

        self.thick_spin = QDoubleSpinBox()
        self.thick_spin.setRange(0.0, 2000.0)
        self.thick_spin.setDecimals(0)
        self.thick_spin.setSuffix(" мм")
        self.thick_spin.setValue(0.0)
        form.addRow(_t("panel.boundaries.dlg.thickness"), self.thick_spin)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

        self._refresh_constructions(self.cat_combo.currentText())

    def _refresh_constructions(self, category: str) -> None:
        self.con_combo.clear()
        matching = [c for c in self.project.constructions.values()
                    if c.category == category]
        for c in matching:
            label = f"{c.family} / {c.type_name}".strip(" /") or c.key
            self.con_combo.addItem(label, c.key)
        # Заполнить толщину из выбранной конструкции
        if matching:
            self.thick_spin.setValue(matching[0].thickness_mm or 0.0)

    def get_values(self) -> dict:
        return {
            "category": self.cat_combo.currentText(),
            "construction_key": self.con_combo.currentData(),
            "is_exterior": self.exterior_combo.currentText() == self._ext_label,
            "area_m2": self.area_spin.value(),
            "orientation": self.orient_combo.currentText(),
            "thickness_mm": self.thick_spin.value(),
        }


class BoundariesPanel(QWidget):
    """Таблица ограждений выбранного помещения."""

    changed = Signal()

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._space: Optional[Space] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Заголовок
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.boundaries.title"))
        self.title_lbl.setProperty("role", "h2")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "muted")
        head.addWidget(self.summary_lbl)
        root.addLayout(head)

        # Таблица
        self.table = QTableWidget(0, len(_HEADER_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                    | QAbstractItemView.SelectedClicked)
        h = self.table.horizontalHeader()
        # Категория/Площадь/U — фиксированные ширины; Конструкция — Stretch,
        # т.к. в ней самые длинные тексты. Combo-колонки тоже фиксированной
        # ширины, чтобы выпадающие списки не обрезались.
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setSectionResizeMode(3, QHeaderView.Interactive)
        h.setSectionResizeMode(4, QHeaderView.Interactive)
        h.setSectionResizeMode(5, QHeaderView.Interactive)
        widths = [130, 260, 80, 90, 60, 80]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.table.setMinimumWidth(sum(widths) + 30)
        root.addWidget(self.table, stretch=1)
        self.table.itemChanged.connect(self._on_item_changed)

        # Кнопки
        bar = QHBoxLayout()
        self._add_buttons: List[tuple[QPushButton, str]] = []
        for key, category in [
            ("panel.boundaries.btn_wall",   "Стены"),
            ("panel.boundaries.btn_window", "Окна"),
            ("panel.boundaries.btn_door",   "Двери"),
            ("panel.boundaries.btn_roof",   "Покрытие"),
            ("panel.boundaries.btn_floor",  "Пол"),
        ]:
            b = QPushButton(_t(key))
            b.clicked.connect(lambda _checked=False, c=category: self._add(c))
            bar.addWidget(b)
            self._add_buttons.append((b, key))
        bar.addStretch(1)
        self._del_btn = QPushButton(_t("panel.boundaries.btn_delete"))
        self._del_btn.clicked.connect(self._delete_selected)
        bar.addWidget(self._del_btn)
        root.addLayout(bar)

        self._suppress_signal = False
        on_language_change(lambda _lang: self.retranslate_ui())

    # ---------- внешний API ----------
    def show_space(self, space: Optional[Space]) -> None:
        self._space = space
        if space is None:
            self.title_lbl.setText(_t("panel.boundaries.title"))
            self.summary_lbl.setText("")
            self.table.setRowCount(0)
            self.setEnabled(False)
            return
        self.setEnabled(True)
        self.title_lbl.setText(_t("panel.boundaries.title_for").format(
            number=space.number, name=space.name))
        self._reload()

    def retranslate_ui(self) -> None:
        if self._space is None:
            self.title_lbl.setText(_t("panel.boundaries.title"))
        else:
            self.title_lbl.setText(_t("panel.boundaries.title_for").format(
                number=self._space.number, name=self._space.name))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        for btn, key in self._add_buttons:
            btn.setText(_t(key))
        self._del_btn.setText(_t("panel.boundaries.btn_delete"))
        self._reload()

    # ---------- внутреннее ----------
    def _reload(self) -> None:
        if self._space is None:
            return
        self._suppress_signal = True
        self.table.setRowCount(0)
        # Фильтруем служебные категории Revit (разделители помещений,
        # колонны и т. п.) — они не несут теплопередачи.
        elements = [e for e in self.project.elements
                    if e.space_id == self._space.space_id
                    and not is_excluded_category(e.category)]
        for el in elements:
            self._append_row(el)
        # Сводка
        area_ext = sum(e.net_area_m2 or 0 for e in elements if e.is_exterior)
        self.summary_lbl.setText(_t("panel.boundaries.summary").format(
            n=len(elements), area=area_ext))
        self._suppress_signal = False

    def _append_row(self, el: BoundaryElement) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        con = self.project.constructions.get(el.construction_key)
        cat = con.category if con else el.category

        # Колонка 0 — категория (read-only)
        cat_item = QTableWidgetItem(cat)
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsEditable)
        cat_item.setData(Qt.UserRole, el.element_id)
        cat_item.setToolTip(_t("panel.boundaries.tt.element").format(
            cat=cat, family=el.family, type=el.type_name, eid=el.element_id))
        self.table.setItem(row, 0, cat_item)

        # Колонка 1 — конструкция (выпадающий из каталога)
        combo = QComboBox()
        combo.setEditable(False)
        matching = [c for c in self.project.constructions.values()
                    if c.category == cat]
        for c in matching:
            label = f"{c.family} / {c.type_name}".strip(" /") or c.key
            combo.addItem(label, c.key)
        idx = combo.findData(el.construction_key)
        if idx < 0 and matching:
            combo.setCurrentIndex(0)
        else:
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setToolTip(combo.currentText())
        combo.currentIndexChanged.connect(
            lambda *_, r=row: self._on_construction_changed(r))
        combo.currentTextChanged.connect(combo.setToolTip)
        self.table.setCellWidget(row, 1, combo)

        # Колонка 2 — площадь
        area_item = QTableWidgetItem(f"{el.net_area_m2 or el.element_area_m2:.2f}")
        area_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 2, area_item)

        # Колонка 3 — ориентация
        orient_combo = QComboBox()
        orient_combo.addItems(_ORIENTATIONS)
        if el.orientation:
            orient_combo.setCurrentText(el.orientation)
        orient_combo.currentTextChanged.connect(
            lambda txt, r=row: self._on_orient_changed(r, txt))
        self.table.setCellWidget(row, 3, orient_combo)

        # Колонка 4 — U (read-only)
        u_item = QTableWidgetItem(f"{el.u_value:.3f}" if el.u_value else "")
        u_item.setFlags(u_item.flags() & ~Qt.ItemIsEditable)
        u_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 4, u_item)

        # Колонка 5 — наружное
        ext_combo = QComboBox()
        yes_lbl = _t("panel.boundaries.ext_yes")
        no_lbl = _t("panel.boundaries.ext_no")
        ext_combo.addItems([yes_lbl, no_lbl])
        ext_combo.setCurrentIndex(0 if el.is_exterior else 1)
        ext_combo._yes_label = yes_lbl
        ext_combo.currentIndexChanged.connect(
            lambda *_: self._on_exterior_changed(row))
        self.table.setCellWidget(row, 5, ext_combo)

        # Подсветка вручную добавленных элементов
        if el.manual_entry:
            for col in (0,):
                self.table.item(row, col).setForeground(
                    QBrush(QColor("#2978c4")))

    def _element_id_at(self, row: int) -> str:
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else ""

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_signal or self._space is None:
            return
        if item.column() != 2:  # только площадь — text-edit
            return
        try:
            new_area = float(item.text().replace(",", "."))
        except ValueError:
            return
        eid = self._element_id_at(item.row())
        if eid:
            self.project.update_element(
                eid, approx_area_m2=new_area, element_area_m2=new_area,
                net_area_m2=new_area)
            self.bridge.dirtyChanged.emit(True)
            self._reload()

    def _on_orient_changed(self, row: int, text: str) -> None:
        if self._space is None:
            return
        eid = self._element_id_at(row)
        if eid:
            self.project.update_element(eid, orientation=text)
            self.bridge.dirtyChanged.emit(True)

    def _on_exterior_changed(self, row: int) -> None:
        if self._space is None:
            return
        eid = self._element_id_at(row)
        combo = self.table.cellWidget(row, 5)
        if eid and combo:
            self.project.update_element(
                eid, is_exterior=combo.currentText() == combo._yes_label)
            self.bridge.dirtyChanged.emit(True)

    def _on_construction_changed(self, row: int) -> None:
        if self._space is None:
            return
        eid = self._element_id_at(row)
        combo = self.table.cellWidget(row, 1)
        if not eid or not combo:
            return
        new_key = combo.currentData()
        con = self.project.constructions.get(new_key)
        if not con:
            return
        self.project.update_element(
            eid, construction_key=new_key, u_value=con.u_value,
            family=con.family, type_name=con.type_name,
            category=con.category, thickness_mm=con.thickness_mm)
        self.bridge.dirtyChanged.emit(True)
        self._reload()

    def _add(self, category: str) -> None:
        if self._space is None:
            QMessageBox.information(
                self,
                _t("panel.boundaries.msg.pick_space_title"),
                _t("panel.boundaries.msg.pick_space"))
            return
        # Если в каталоге нет ни одной конструкции этой категории —
        # создаём временную дефолтную, чтобы пользователю было что выбрать.
        existing_cat = any(c.category == category
                            for c in self.project.constructions.values())
        if not existing_cat:
            self._create_default_construction(category)
        dlg = _AddElementDialog(self.project, self._space,
                                 default_category=category, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.get_values()
        if not v["construction_key"]:
            QMessageBox.warning(
                self,
                _t("panel.boundaries.msg.no_construction_title"),
                _t("panel.boundaries.msg.no_construction"))
            return
        con = self.project.constructions[v["construction_key"]]
        row_type = "opening" if v["category"] in ("Окна", "Витраж", "Двери") \
            else "external_wall"
        self.project.add_element(
            space_id=self._space.space_id,
            row_type=row_type, category=v["category"],
            family=con.family, type_name=con.type_name,
            area_m2=v["area_m2"], is_exterior=v["is_exterior"],
            orientation=v["orientation"],
            thickness_mm=v["thickness_mm"] or con.thickness_mm,
            u_value=con.u_value, shgc=con.shgc,
        )
        self.bridge.dirtyChanged.emit(True)
        self._reload()
        self.changed.emit()

    def _create_default_construction(self, category: str) -> None:
        """Создаёт минимальную конструкцию в каталоге, чтобы было что выбирать."""
        from hvac.catalogs.constructions import (
            DEFAULT_U_BY_CATEGORY, DEFAULT_SHGC, construction_key,
        )
        key = construction_key(category, "Универсал", "Тип-1", 200)
        if key in self.project.constructions:
            return
        self.project.constructions[key] = Construction(
            key=key, category=category, family="Универсал",
            type_name="Тип-1", thickness_mm=200,
            u_value=DEFAULT_U_BY_CATEGORY.get(category, 0.5),
            shgc=DEFAULT_SHGC.get(category, 0.0),
            note=_t("panel.boundaries.auto_note"),
        )
        self.project.emit("constructions_changed")

    def _delete_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        ids = [self._element_id_at(r) for r in rows]
        for eid in ids:
            if eid:
                self.project.remove_element(eid)
        self.bridge.dirtyChanged.emit(True)
        self._reload()
        self.changed.emit()
