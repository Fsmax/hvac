# -*- coding: utf-8 -*-
"""Диалоги оборудования: источник (котёл/чиллер), контур, приточная установка + мелкие фабрики виджетов (_spin, _combo).

Исторически здесь жила панель «Оборудование»; её заменил equipment_workspace. Мёртвый класс EquipmentPanel удалён при ревизии UI (F11).
"""
from __future__ import annotations

from typing import List

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from hvac.i18n import t as _t


_TREE_COL_KEYS = [
    "panel.equipment.tcol.name", "panel.equipment.tcol.load",
    "panel.equipment.tcol.pick", "panel.equipment.tcol.dn",
    "panel.equipment.tcol.dp", "panel.equipment.tcol.pump",
]
_AHU_COL_KEYS = [
    "panel.equipment.acol.ahu", "panel.equipment.acol.flow",
    "panel.equipment.acol.fan", "panel.equipment.acol.q_heater",
    "panel.equipment.acol.q_cooler", "panel.equipment.acol.recovery",
]

# Технические коды типов (данные, не UI-текст — латиница, без i18n).
_HEAT_TYPES = ["boiler_gas", "boiler_electric", "heat_pump", "central"]
_COOL_TYPES = ["chiller_air", "chiller_water", "vrf", "split"]
_VENT_TYPES = ["supply", "exhaust", "supply_exhaust"]
_FUELS = ["gas", "electric", "diesel", "central"]
_PIPE_MATERIALS = ["steel", "pex", "ppr"]


def _ctype_label(ctype: str) -> str:
    return _t("panel.zones.ctype." + ctype, default=ctype) if ctype else ""


def _combo(options: List[str], current: str, editable: bool = False) -> QComboBox:
    box = QComboBox()
    box.setEditable(editable)
    box.addItems(options)
    if current and current not in options:
        box.addItem(current)
    box.setCurrentText(current)
    return box


def _spin(value: float, lo: float, hi: float, step: float = 1.0,
          decimals: int = 1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    return s


def _dialog_buttons(dlg: QDialog, form: QFormLayout) -> None:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(_t("btn.ok"))
    bb.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    form.addRow(bb)


class _SourceDialog(QDialog):
    """Параметры источника (котёл / чиллер) + ручной подбор мощности."""

    def __init__(self, parent: QWidget, *, domain: str, sysobj,
                 required_kw: float):
        super().__init__(parent)
        self.domain = domain
        self.setWindowTitle(_t("panel.equipment.dlg.source_title").format(
            name=sysobj.name))
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        types = _HEAT_TYPES if domain == "heating" else _COOL_TYPES
        self.type_combo = _combo(types, getattr(sysobj, "system_type", ""), True)
        form.addRow(_t("panel.equipment.col.type"), self.type_combo)
        self.t_sup = _spin(getattr(sysobj, "t_supply", 0.0), 0, 150, 1)
        form.addRow(_t("panel.equipment.col.t_sup"), self.t_sup)
        self.t_ret = _spin(getattr(sysobj, "t_return", 0.0), 0, 150, 1)
        form.addRow(_t("panel.equipment.col.t_ret"), self.t_ret)

        if domain == "heating":
            self.fuel = _combo(_FUELS, getattr(sysobj, "fuel", ""), True)
            form.addRow(_t("panel.equipment.col.fuel"), self.fuel)
            self.eff = _spin(getattr(sysobj, "efficiency", 0.92), 0.3, 1.2,
                             0.01, 2)
            form.addRow(_t("panel.equipment.col.eff"), self.eff)
        else:
            self.cop = _spin(getattr(sysobj, "cop", 3.5), 1.0, 8.0, 0.1, 1)
            form.addRow(_t("panel.equipment.col.cop"), self.cop)
            self.refr = QLineEdit(getattr(sysobj, "refrigerant", ""))
            form.addRow(_t("panel.equipment.col.refr"), self.refr)

        hint = QLabel(_t("panel.equipment.hint.required").format(
            kw=f"{required_kw:.1f}"))
        hint.setProperty("role", "muted")
        form.addRow(hint)

        self.cap = _spin(getattr(sysobj, "design_capacity_kw", 0.0), 0, 100000,
                         10, 0)
        form.addRow(_t("panel.equipment.f.capacity"), self.cap)
        self.units = QSpinBox()
        self.units.setRange(0, 50)
        self.units.setValue(int(getattr(sysobj, "unit_count", 0) or 0))
        form.addRow(_t("panel.equipment.f.units"), self.units)
        self.model = QLineEdit(getattr(sysobj, "selected_model", ""))
        form.addRow(_t("panel.equipment.f.model"), self.model)

        _dialog_buttons(self, form)

    def values(self) -> dict:
        out = {
            "system_type": self.type_combo.currentText().strip(),
            "t_supply": self.t_sup.value(),
            "t_return": self.t_ret.value(),
            "design_capacity_kw": self.cap.value(),
            "unit_count": self.units.value(),
            "selected_model": self.model.text().strip(),
        }
        if self.domain == "heating":
            out["fuel"] = self.fuel.currentText().strip()
            out["efficiency"] = self.eff.value()
        else:
            out["cop"] = self.cop.value()
            out["refrigerant"] = self.refr.text().strip()
        return out


class _CircuitDialog(QDialog):
    """Параметры контура: тип, t°-график, материал труб, запас насоса."""

    def __init__(self, parent: QWidget, *, domain: str, cobj,
                 types: List[str]):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.equipment.dlg.circuit_title").format(
            name=cobj.name))
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self._has = {f for f in type(cobj).__dataclass_fields__}

        self.type_combo = None
        if types and "circuit_type" in self._has:
            self.type_combo = QComboBox()
            for ct in types:
                self.type_combo.addItem(_ctype_label(ct), userData=ct)
            cur = getattr(cobj, "circuit_type", "")
            i = self.type_combo.findData(cur)
            if i >= 0:
                self.type_combo.setCurrentIndex(i)
            form.addRow(_t("panel.equipment.col.type"), self.type_combo)

        self.t_sup = self.t_ret = self.pipe = self.reserve = None
        if "t_supply" in self._has:
            self.t_sup = _spin(getattr(cobj, "t_supply", 0.0), 0, 150, 1)
            form.addRow(_t("panel.equipment.col.t_sup"), self.t_sup)
        if "t_return" in self._has:
            self.t_ret = _spin(getattr(cobj, "t_return", 0.0), 0, 150, 1)
            form.addRow(_t("panel.equipment.col.t_ret"), self.t_ret)
        if "pipe_material" in self._has:
            self.pipe = _combo(_PIPE_MATERIALS,
                               getattr(cobj, "pipe_material", "steel"), True)
            form.addRow(_t("panel.equipment.f.pipe_material"), self.pipe)
        if "pump_head_reserve" in self._has:
            self.reserve = _spin(getattr(cobj, "pump_head_reserve", 1.3),
                                 1.0, 2.0, 0.05, 2)
            form.addRow(_t("panel.equipment.f.pump_reserve"), self.reserve)

        _dialog_buttons(self, form)

    def values(self) -> dict:
        out: dict = {}
        if self.type_combo is not None:
            out["circuit_type"] = self.type_combo.currentData()
        if self.t_sup is not None:
            out["t_supply"] = self.t_sup.value()
        if self.t_ret is not None:
            out["t_return"] = self.t_ret.value()
        if self.pipe is not None:
            out["pipe_material"] = self.pipe.currentText().strip()
        if self.reserve is not None:
            out["pump_head_reserve"] = self.reserve.value()
        return out


class _AHUDialog(QDialog):
    """Параметры AHU + прикрепление калорифера/охладителя к контурам."""

    _NONE = "—"   # «—» как «нет контура» (не cyrillic)

    def __init__(self, parent: QWidget, *, vsys,
                 heating_circuits: List[str], cooling_circuits: List[str]):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.equipment.dlg.ahu_title").format(
            name=vsys.name))
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.type_combo = _combo(_VENT_TYPES,
                                 getattr(vsys, "system_type", ""), True)
        form.addRow(_t("panel.equipment.col.type"), self.type_combo)
        self.recovery = QCheckBox()
        self.recovery.setChecked(bool(getattr(vsys, "has_recovery", False)))
        form.addRow(_t("panel.equipment.f.has_recovery"), self.recovery)
        self.eta_w = _spin(getattr(vsys, "recovery_efficiency_winter", 0.0),
                           0.0, 0.95, 0.05, 2)
        form.addRow(_t("panel.equipment.col.eta_w"), self.eta_w)
        self.eta_s = _spin(getattr(vsys, "recovery_efficiency_summer", 0.0),
                           0.0, 0.95, 0.05, 2)
        form.addRow(_t("panel.equipment.col.eta_s"), self.eta_s)
        self.t_in_w = _spin(getattr(vsys, "t_supply_winter", 16.0), 5, 40, 1)
        form.addRow(_t("panel.equipment.col.t_in_w"), self.t_in_w)
        self.t_in_s = _spin(getattr(vsys, "t_supply_summer", 18.0), 5, 40, 1)
        form.addRow(_t("panel.equipment.f.t_in_s"), self.t_in_s)

        self.heat_circ = _combo([self._NONE] + heating_circuits,
                                getattr(vsys, "heating_circuit", "") or self._NONE)
        form.addRow(_t("panel.equipment.f.heating_circuit"), self.heat_circ)
        self.cool_circ = _combo([self._NONE] + cooling_circuits,
                                getattr(vsys, "cooling_circuit", "") or self._NONE)
        form.addRow(_t("panel.equipment.f.cooling_circuit"), self.cool_circ)

        _dialog_buttons(self, form)

    def _circ(self, box: QComboBox) -> str:
        v = box.currentText().strip()
        return "" if v == self._NONE else v

    def values(self) -> dict:
        return {
            "system_type": self.type_combo.currentText().strip(),
            "has_recovery": self.recovery.isChecked(),
            "recovery_efficiency_winter": self.eta_w.value(),
            "recovery_efficiency_summer": self.eta_s.value(),
            "t_supply_winter": self.t_in_w.value(),
            "t_supply_summer": self.t_in_s.value(),
            "heating_circuit": self._circ(self.heat_circ),
            "cooling_circuit": self._circ(self.cool_circ),
        }
