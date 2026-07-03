# -*- coding: utf-8 -*-
"""Диалог конечного оборудования помещения (радиаторы, фанкойлы, диффузоры) — используется systems_workspace.

Мёртвый класс RoomEquipmentPanel удалён при ревизии UI (F11).
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Space
from hvac.room_equipment import (
    COOLING_TERMINAL_TYPES,
    EXHAUST_TERMINAL_TYPES,
    HEATING_TERMINAL_TYPES,
    SUPPLY_TERMINAL_TYPES,
    RoomEquipment,
)


_HEADER_KEYS = [
    "panel.room_eq.col.number", "panel.room_eq.col.name",
    "panel.room_eq.col.q_heat", "panel.room_eq.col.terminal",
    "panel.room_eq.col.power",  "panel.room_eq.col.qty",
    "panel.room_eq.col.diffuser", "panel.room_eq.col.diff_qty",
    "panel.room_eq.col.heat_circ", "panel.room_eq.col.cool_circ",
    "panel.room_eq.col.vent_sys",
]


class _TerminalGroup(QGroupBox):
    """Группа полей одного вида оборудования (тип/модель/мощность/кол-во)."""

    def __init__(self, title: str, types: list[str], value_label: str,
                 type_field: str, model_field: str, value_field: str,
                 qty_field: str, eq: RoomEquipment, design_q: float,
                 is_power: bool, on_change):
        super().__init__(title)
        self._fields = (type_field, model_field, value_field, qty_field)
        self._design_q = design_q
        self._is_power = is_power
        self._on_change = on_change

        form = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems(types)
        cur = getattr(eq, type_field, "—")
        i = self.type_combo.findText(cur)
        if i >= 0:
            self.type_combo.setCurrentIndex(i)

        self.model_edit = QLineEdit(getattr(eq, model_field, "") or "")

        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(0.0, 1_000_000.0)
        self.value_spin.setDecimals(0)
        self.value_spin.setSingleStep(50.0 if is_power else 10.0)
        self.value_spin.setValue(float(getattr(eq, value_field, 0.0) or 0.0))

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 9999)
        self.qty_spin.setValue(int(getattr(eq, qty_field, 0) or 0))

        self.total_lbl = QLabel("")
        self.total_lbl.setProperty("role", "muted")

        form.addRow(_t("dlg.room_eq.f.type"), self.type_combo)
        form.addRow(_t("dlg.room_eq.f.model"), self.model_edit)
        form.addRow(_t(value_label), self.value_spin)
        form.addRow(_t("dlg.room_eq.f.qty"), self.qty_spin)
        form.addRow("", self.total_lbl)

        self.value_spin.valueChanged.connect(self._recalc)
        self.qty_spin.valueChanged.connect(self._recalc)
        self._recalc()

    def _recalc(self) -> None:
        total = self.value_spin.value() * self.qty_spin.value()
        key = "dlg.room_eq.sum_power" if self._is_power else "dlg.room_eq.sum_flow"
        txt = _t(key).format(total=total)
        if self._design_q > 0:
            txt += _t("dlg.room_eq.coverage").format(
                cov=100.0 * total / self._design_q)
        self.total_lbl.setText(txt)
        if self._on_change:
            self._on_change()

    def values(self) -> Dict[str, Any]:
        tf, mf, vf, qf = self._fields
        return {
            tf: self.type_combo.currentText(),
            mf: self.model_edit.text().strip(),
            vf: float(self.value_spin.value()),
            qf: int(self.qty_spin.value()),
        }


class RoomEquipmentDialog(QDialog):
    """Назначение конечного оборудования одному помещению."""

    _NONE = "—"   # «не подключено» (не cyrillic)

    def __init__(self, space: Space, parent: QWidget | None = None,
                 *, title: str | None = None, show_loads: bool = True,
                 project=None):
        super().__init__(parent)
        self.space = space
        self.project = project
        eq = space.room_equipment or RoomEquipment()
        self.setWindowTitle(title or _t("dlg.room_eq.title").format(
            room=f"{space.number} · {space.name}"))
        self.setMinimumWidth(560)

        outer = QVBoxLayout(self)

        if show_loads:
            loads = QLabel(_t("dlg.room_eq.loads").format(
                qh=space.heat_loss_w / 1000.0,
                qc=space.heat_gain_w / 1000.0,
                sup=space.supply_m3h,
                exh=space.exhaust_m3h,
            ))
            loads.setProperty("role", "muted")
            outer.addWidget(loads)

        row = QHBoxLayout()
        self.g_heat = _TerminalGroup(
            _t("dlg.room_eq.sec.heating"), HEATING_TERMINAL_TYPES,
            "dlg.room_eq.f.power", "heating_terminal_type",
            "heating_terminal_model", "heating_terminal_power_w",
            "heating_terminal_qty", eq, space.heat_loss_w, True, None)
        self.g_cool = _TerminalGroup(
            _t("dlg.room_eq.sec.cooling"), COOLING_TERMINAL_TYPES,
            "dlg.room_eq.f.power", "cooling_terminal_type",
            "cooling_terminal_model", "cooling_terminal_power_w",
            "cooling_terminal_qty", eq, space.heat_gain_w, True, None)
        row.addWidget(self.g_heat)
        row.addWidget(self.g_cool)
        outer.addLayout(row)

        row2 = QHBoxLayout()
        self.g_sup = _TerminalGroup(
            _t("dlg.room_eq.sec.supply"), SUPPLY_TERMINAL_TYPES,
            "dlg.room_eq.f.flow", "supply_terminal_type",
            "supply_terminal_model", "supply_terminal_flow_m3h",
            "supply_terminal_qty", eq, space.supply_m3h, False, None)
        self.g_exh = _TerminalGroup(
            _t("dlg.room_eq.sec.exhaust"), EXHAUST_TERMINAL_TYPES,
            "dlg.room_eq.f.flow", "exhaust_terminal_type",
            "exhaust_terminal_model", "exhaust_terminal_flow_m3h",
            "exhaust_terminal_qty", eq, space.exhaust_m3h, False, None)
        row2.addWidget(self.g_sup)
        row2.addWidget(self.g_exh)
        outer.addLayout(row2)

        # ----- Подключение к системам (связь с «Зонами и системами») -----
        # Отопительный прибор → контур отопления (→ котёл), охладитель →
        # контур холода (→ чиллер), диффузор → приточка (AHU).
        self.heat_circ_combo = self.cool_circ_combo = self.vent_combo = None
        if project is not None:
            conn = QGroupBox(_t("dlg.room_eq.sec.connect"))
            cform = QFormLayout(conn)
            self.heat_circ_combo = self._conn_combo(
                project.circuits_of("heating").keys(), space.circuit_heating)
            cform.addRow(_t("dlg.room_eq.f.heat_circ"), self.heat_circ_combo)
            self.cool_circ_combo = self._conn_combo(
                project.circuits_of("cooling").keys(), space.circuit_cooling)
            cform.addRow(_t("dlg.room_eq.f.cool_circ"), self.cool_circ_combo)
            self.vent_combo = self._conn_combo(
                project.systems_of("ventilation").keys(), space.system_ventilation)
            cform.addRow(_t("dlg.room_eq.f.vent_sys"), self.vent_combo)
            outer.addWidget(conn)

        notes_form = QFormLayout()
        self.notes_edit = QPlainTextEdit(eq.notes or "")
        self.notes_edit.setFixedHeight(56)
        notes_form.addRow(_t("dlg.room_eq.f.notes"), self.notes_edit)
        outer.addLayout(notes_form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("btn.ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _conn_combo(self, names, current: str) -> QComboBox:
        box = QComboBox()
        box.addItem(self._NONE)
        box.addItems(sorted(names))
        box.setCurrentText(current or self._NONE)
        return box

    def values(self) -> Dict[str, Any]:
        """Все поля оборудования как kwargs для project.set_room_equipment."""
        out: Dict[str, Any] = {}
        for g in (self.g_heat, self.g_cool, self.g_sup, self.g_exh):
            out.update(g.values())
        out["notes"] = self.notes_edit.toPlainText().strip()
        return out

    def connection(self) -> Dict[str, str]:
        """Выбранные привязки к контурам/AHU (пусто, если без project)."""
        if self.heat_circ_combo is None:
            return {}

        def _v(box: QComboBox | None) -> str:
            if box is None:
                return ""
            t = box.currentText().strip()
            return "" if t == self._NONE else t

        return {
            "circuit_heating": _v(self.heat_circ_combo),
            "circuit_cooling": _v(self.cool_circ_combo),
            "system_ventilation": _v(self.vent_combo),
        }
