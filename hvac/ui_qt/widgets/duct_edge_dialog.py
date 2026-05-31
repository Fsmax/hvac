# -*- coding: utf-8 -*-
"""Диалог редактирования участка детальной аэродинамической сети.

Позволяет:
    • изменить расход / длину / форму / размеры
    • указать родителя и пометить как терминал
    • управлять списком фитингов (добавить / удалить / тип / количество / ζ)
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.duct_network import DuctEdge, DuctFitting, LOCAL_LOSS_COEFFICIENTS
from hvac.i18n import t as _t


class DuctEdgeDialog(QDialog):
    """Создание / редактирование одного DuctEdge."""

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 edge: Optional[DuctEdge] = None,
                 known_edge_ids: Optional[List[str]] = None,
                 is_new: bool = False):
        super().__init__(parent)
        self.is_new = is_new
        self.known_edge_ids = list(known_edge_ids or [])
        # Работаем с копией
        if edge is None:
            self.edge = DuctEdge(edge_id="")
        else:
            self.edge = DuctEdge(
                edge_id=edge.edge_id,
                parent_id=edge.parent_id,
                flow_m3_h=edge.flow_m3_h,
                length_m=edge.length_m,
                shape=edge.shape,
                diameter_mm=edge.diameter_mm,
                width_mm=edge.width_mm,
                height_mm=edge.height_mm,
                terminal_name=edge.terminal_name,
                is_terminal=edge.is_terminal,
                note=edge.note,
                fittings=[
                    DuctFitting(kind=f.kind, zeta=f.zeta,
                                  extra_pressure_pa=f.extra_pressure_pa,
                                  quantity=f.quantity, note=f.note)
                    for f in edge.fittings
                ],
            )

        self.setWindowTitle(_t("dlg.duct.title_new") if is_new
                              else _t("dlg.duct.title_edit").format(
                                  edge_id=self.edge.edge_id))
        self.setMinimumWidth(640)

        outer = QVBoxLayout(self)

        # ===== Идентификация и связь =====
        head = QGroupBox(_t("dlg.duct.gb_id"))
        head_form = QFormLayout(head)

        self.id_edit = QLineEdit(self.edge.edge_id)
        self.id_edit.setPlaceholderText("trunk, branch_1, …")
        self.id_edit.setEnabled(is_new)
        head_form.addRow(_t("dlg.duct.id"), self.id_edit)

        self.parent_combo = QComboBox()
        self.parent_combo.setEditable(True)
        self.parent_combo.addItem(_t("dlg.duct.parent_root"), userData="")
        for eid in self.known_edge_ids:
            if eid != self.edge.edge_id:
                self.parent_combo.addItem(eid, userData=eid)
        # Восстановить текущий
        for i in range(self.parent_combo.count()):
            if self.parent_combo.itemData(i) == self.edge.parent_id:
                self.parent_combo.setCurrentIndex(i)
                break
        head_form.addRow(_t("dlg.duct.parent"), self.parent_combo)

        self.terminal_edit = QLineEdit(self.edge.terminal_name)
        self.terminal_edit.setPlaceholderText(_t("dlg.duct.terminal_ph"))
        head_form.addRow(_t("dlg.duct.terminal_name"), self.terminal_edit)

        from PySide6.QtWidgets import QCheckBox
        self.is_terminal_check = QCheckBox(_t("dlg.duct.is_terminal"))
        self.is_terminal_check.setChecked(self.edge.is_terminal)
        head_form.addRow("", self.is_terminal_check)

        outer.addWidget(head)

        # ===== Геометрия и поток =====
        geom = QGroupBox(_t("dlg.duct.gb_geom"))
        geom_form = QFormLayout(geom)

        self.flow_spin = QDoubleSpinBox()
        self.flow_spin.setRange(0.0, 1_000_000.0)
        self.flow_spin.setSuffix(" м³/ч")
        self.flow_spin.setDecimals(0)
        self.flow_spin.setValue(self.edge.flow_m3_h)
        geom_form.addRow(_t("dlg.duct.flow"), self.flow_spin)

        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.0, 1000.0)
        self.length_spin.setSuffix(" м")
        self.length_spin.setDecimals(2)
        self.length_spin.setValue(self.edge.length_m)
        geom_form.addRow(_t("dlg.duct.length"), self.length_spin)

        self.shape_combo = QComboBox()
        self.shape_combo.addItem(_t("dlg.duct.shape.round"), userData="round")
        self.shape_combo.addItem(_t("dlg.duct.shape.rect"), userData="rect")
        idx = 0 if self.edge.shape == "round" else 1
        self.shape_combo.setCurrentIndex(idx)
        self.shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        geom_form.addRow(_t("dlg.duct.shape"), self.shape_combo)

        self.diameter_spin = QDoubleSpinBox()
        self.diameter_spin.setRange(50.0, 2500.0)
        self.diameter_spin.setSuffix(" мм")
        self.diameter_spin.setDecimals(0)
        self.diameter_spin.setValue(self.edge.diameter_mm or 200.0)
        geom_form.addRow(_t("dlg.duct.diameter"), self.diameter_spin)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(50.0, 3000.0)
        self.width_spin.setSuffix(" мм")
        self.width_spin.setDecimals(0)
        self.width_spin.setValue(self.edge.width_mm or 400.0)
        geom_form.addRow(_t("dlg.duct.width"), self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(50.0, 3000.0)
        self.height_spin.setSuffix(" мм")
        self.height_spin.setDecimals(0)
        self.height_spin.setValue(self.edge.height_mm or 200.0)
        geom_form.addRow(_t("dlg.duct.height"), self.height_spin)

        outer.addWidget(geom)

        # ===== Фитинги =====
        fits_group = QGroupBox(_t("dlg.duct.gb_fittings"))
        fits_layout = QVBoxLayout(fits_group)

        bar = QHBoxLayout()
        self.add_fit_btn = QPushButton(_t("dlg.duct.btn_add"))
        self.add_fit_btn.clicked.connect(self._add_fitting_row)
        bar.addWidget(self.add_fit_btn)
        self.del_fit_btn = QPushButton(_t("dlg.duct.btn_delete"))
        self.del_fit_btn.clicked.connect(self._delete_fitting_row)
        bar.addWidget(self.del_fit_btn)
        bar.addStretch(1)
        fits_layout.addLayout(bar)

        self.fits_table = QTableWidget(0, 5)
        self.fits_table.setHorizontalHeaderLabels([
            _t("dlg.duct.fit.col_kind"),
            _t("dlg.duct.fit.col_qty"),
            _t("dlg.duct.fit.col_zeta"),
            _t("dlg.duct.fit.col_dp"),
            _t("dlg.duct.fit.col_note"),
        ])
        self.fits_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fits_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.fits_table.verticalHeader().setVisible(False)
        self.fits_table.horizontalHeader().setStretchLastSection(True)
        self.fits_table.setColumnWidth(0, 220)
        self.fits_table.setColumnWidth(1, 50)
        self.fits_table.setColumnWidth(2, 70)
        self.fits_table.setColumnWidth(3, 100)
        fits_layout.addWidget(self.fits_table)

        for f in self.edge.fittings:
            self._add_fitting_row(f)

        outer.addWidget(fits_group)

        # ===== Кнопки =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._on_shape_changed()

    # ---------- Реакции ----------
    def _on_shape_changed(self):
        is_round = self.shape_combo.currentData() == "round"
        self.diameter_spin.setEnabled(is_round)
        self.width_spin.setEnabled(not is_round)
        self.height_spin.setEnabled(not is_round)

    def _add_fitting_row(self, fitting: Optional[DuctFitting] = None):
        row = self.fits_table.rowCount()
        self.fits_table.insertRow(row)

        kind_combo = QComboBox()
        kind_combo.setEditable(True)
        kind_combo.addItem(_t("dlg.duct.fit.empty"), userData="")
        for k in sorted(LOCAL_LOSS_COEFFICIENTS.keys()):
            label = f"{k} (ζ={LOCAL_LOSS_COEFFICIENTS[k]:.2f})"
            kind_combo.addItem(label, userData=k)
        if fitting and fitting.kind:
            for i in range(kind_combo.count()):
                if kind_combo.itemData(i) == fitting.kind:
                    kind_combo.setCurrentIndex(i)
                    break
        self.fits_table.setCellWidget(row, 0, kind_combo)

        qty_item = QTableWidgetItem(str(fitting.quantity if fitting else 1))
        self.fits_table.setItem(row, 1, qty_item)

        zeta_item = QTableWidgetItem(
            "" if not fitting or fitting.zeta is None else f"{fitting.zeta}")
        self.fits_table.setItem(row, 2, zeta_item)

        dp_item = QTableWidgetItem(
            "" if not fitting or not fitting.extra_pressure_pa
            else f"{fitting.extra_pressure_pa}")
        self.fits_table.setItem(row, 3, dp_item)

        note_item = QTableWidgetItem(fitting.note if fitting else "")
        self.fits_table.setItem(row, 4, note_item)

    def _delete_fitting_row(self):
        row = self.fits_table.currentRow()
        if row >= 0:
            self.fits_table.removeRow(row)

    def _collect_fittings(self) -> List[DuctFitting]:
        result = []
        for row in range(self.fits_table.rowCount()):
            kind_combo = self.fits_table.cellWidget(row, 0)
            kind = kind_combo.currentData() if kind_combo else ""
            if not kind and kind_combo:
                # пользователь мог ввести ключ свободно (editable)
                raw = kind_combo.currentText().split(" ")[0]
                kind = raw if raw in LOCAL_LOSS_COEFFICIENTS else ""

            def _float(cell, default):
                item = self.fits_table.item(row, cell)
                if item is None:
                    return default
                txt = item.text().strip().replace(",", ".")
                if not txt:
                    return default
                try:
                    return float(txt)
                except ValueError:
                    return default

            def _int(cell, default):
                item = self.fits_table.item(row, cell)
                if item is None:
                    return default
                try:
                    return int(item.text())
                except ValueError:
                    return default

            qty = max(_int(1, 1), 1)
            zeta_val = _float(2, None)
            dp_val = _float(3, 0.0)
            note_item = self.fits_table.item(row, 4)
            note = note_item.text() if note_item else ""

            if not kind and zeta_val is None and dp_val == 0.0:
                continue   # пустая строка — пропускаем

            result.append(DuctFitting(
                kind=kind or "",
                zeta=zeta_val,
                extra_pressure_pa=dp_val or 0.0,
                quantity=qty,
                note=note,
            ))
        return result

    def _on_ok(self):
        eid = self.id_edit.text().strip()
        if not eid:
            return
        self.edge.edge_id = eid
        self.edge.parent_id = self.parent_combo.currentData() or ""
        self.edge.flow_m3_h = self.flow_spin.value()
        self.edge.length_m = self.length_spin.value()
        self.edge.shape = self.shape_combo.currentData() or "round"
        self.edge.diameter_mm = self.diameter_spin.value()
        self.edge.width_mm = self.width_spin.value()
        self.edge.height_mm = self.height_spin.value()
        self.edge.terminal_name = self.terminal_edit.text().strip()
        self.edge.is_terminal = self.is_terminal_check.isChecked()
        self.edge.fittings = self._collect_fittings()
        self.accept()
