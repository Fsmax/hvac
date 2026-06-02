# -*- coding: utf-8 -*-
"""Диалог создания / редактирования одной конструкции каталога.

Поля: категория, семейство, тип, толщина, U, SHGC, примечание. R
показывается справочно (= 1/U) и обновляется по мере правки U.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QWidget,
)

from hvac.i18n import t as _t


_CATEGORIES = ("Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол")


@dataclass
class ConstructionFormResult:
    category: str
    family: str
    type_name: str
    thickness_mm: float
    u_value: float
    shgc: float
    note: str


class ConstructionDialog(QDialog):
    """Создание/редактирование конструкции. При is_new=False заголовок —
    «Изменить», иначе «Новая конструкция»."""

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 initial: Optional[ConstructionFormResult] = None,
                 is_new: bool = True):
        super().__init__(parent)
        self.setWindowTitle(
            _t("panel.constructions.dlg.new_title") if is_new
            else _t("panel.constructions.dlg.edit_title"))
        self.setMinimumWidth(440)

        form = QFormLayout(self)

        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)
        self.cat_combo.addItems(_CATEGORIES)
        form.addRow(_t("panel.constructions.dlg.category"), self.cat_combo)

        self.family_edit = QLineEdit()
        form.addRow(_t("panel.constructions.dlg.family"), self.family_edit)

        self.type_edit = QLineEdit()
        form.addRow(_t("panel.constructions.dlg.type"), self.type_edit)

        self.th_spin = QDoubleSpinBox()
        self.th_spin.setRange(0.0, 5000.0)
        self.th_spin.setDecimals(0)
        self.th_spin.setSuffix(" мм")
        form.addRow(_t("panel.constructions.dlg.thickness"), self.th_spin)

        self.u_spin = QDoubleSpinBox()
        self.u_spin.setRange(0.0, 10.0)
        self.u_spin.setDecimals(3)
        self.u_spin.setSingleStep(0.05)
        self.u_spin.valueChanged.connect(self._refresh_r)
        form.addRow(_t("panel.constructions.dlg.u"), self.u_spin)

        self.r_lbl = QLabel("")
        self.r_lbl.setProperty("role", "muted")
        form.addRow("", self.r_lbl)

        self.shgc_spin = QDoubleSpinBox()
        self.shgc_spin.setRange(0.0, 1.0)
        self.shgc_spin.setDecimals(2)
        self.shgc_spin.setSingleStep(0.05)
        form.addRow(_t("panel.constructions.dlg.shgc"), self.shgc_spin)

        self.note_edit = QLineEdit()
        form.addRow(_t("panel.constructions.dlg.note"), self.note_edit)

        if initial:
            self.cat_combo.setCurrentText(initial.category)
            self.family_edit.setText(initial.family)
            self.type_edit.setText(initial.type_name)
            self.th_spin.setValue(initial.thickness_mm)
            self.u_spin.setValue(initial.u_value)
            self.shgc_spin.setValue(initial.shgc)
            self.note_edit.setText(initial.note)
        self._refresh_r()

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def _refresh_r(self) -> None:
        u = self.u_spin.value()
        r = f"{1.0 / u:.3f}" if u > 0 else "—"
        self.r_lbl.setText(_t("panel.constructions.dlg.r_hint").format(r=r))

    def result_value(self) -> ConstructionFormResult:
        return ConstructionFormResult(
            category=self.cat_combo.currentText().strip(),
            family=self.family_edit.text().strip(),
            type_name=self.type_edit.text().strip(),
            thickness_mm=float(self.th_spin.value()),
            u_value=float(self.u_spin.value()),
            shgc=float(self.shgc_spin.value()),
            note=self.note_edit.text().strip(),
        )
