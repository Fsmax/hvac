# -*- coding: utf-8 -*-
"""RoomEquipmentPanel — конечное оборудование, установленное в помещениях.

Показывает таблицу: помещение → радиатор/фанкойл/диффузор. Двойной клик по
строке открывает диалог назначения оборудования (отопление / охлаждение /
приток / вытяжка) с контролем покрытия расчётной нагрузки.
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.room_equipment import (
    COOLING_TERMINAL_TYPES, EXHAUST_TERMINAL_TYPES, HEATING_TERMINAL_TYPES,
    SUPPLY_TERMINAL_TYPES, RoomEquipment,
)
from hvac.ui_qt.bridge import ProjectBridge


_HEADER_KEYS = [
    "panel.room_eq.col.number", "panel.room_eq.col.name",
    "panel.room_eq.col.q_heat", "panel.room_eq.col.terminal",
    "panel.room_eq.col.power",  "panel.room_eq.col.qty",
    "panel.room_eq.col.diffuser", "panel.room_eq.col.diff_qty",
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

    def __init__(self, space: Space, parent: QWidget | None = None):
        super().__init__(parent)
        self.space = space
        eq = space.room_equipment or RoomEquipment()
        self.setWindowTitle(
            _t("dlg.room_eq.title").format(room=f"{space.number} · {space.name}"))
        self.setMinimumWidth(560)

        outer = QVBoxLayout(self)

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

    def values(self) -> Dict[str, Any]:
        """Все поля оборудования как kwargs для project.set_room_equipment."""
        out: Dict[str, Any] = {}
        for g in (self.g_heat, self.g_cool, self.g_sup, self.g_exh):
            out.update(g.values())
        out["notes"] = self.notes_edit.toPlainText().strip()
        return out


class RoomEquipmentPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.title_lbl = QLabel(_t("panel.room_eq.title"))
        self.title_lbl.setProperty("role", "h1")
        outer.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel(_t("panel.room_eq.subtitle"))
        self.subtitle_lbl.setProperty("role", "muted")
        outer.addWidget(self.subtitle_lbl)
        self.hint_lbl = QLabel(_t("panel.room_eq.hint"))
        self.hint_lbl.setProperty("role", "muted")
        outer.addWidget(self.hint_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        outer.addWidget(self.search)

        self.table = QTableWidget(0, len(_HEADER_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._edit_row)
        widths = [80, 200, 100, 200, 100, 80, 200, 80]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.equipmentChanged):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.room_eq.title"))
        self.subtitle_lbl.setText(_t("panel.room_eq.subtitle"))
        self.hint_lbl.setText(_t("panel.room_eq.hint"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])

    def _edit_row(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self.project.spaces):
            return
        sp = self.project.spaces[row]
        dlg = RoomEquipmentDialog(sp, self)
        if dlg.exec() == QDialog.Accepted:
            self.project.set_room_equipment(sp.space_id, **dlg.values())
            self.bridge.dirtyChanged.emit(True)
            # set_room_equipment эмитит equipment_changed → _refresh через мост,
            # но обновим сразу на случай, если мост ещё не подключён.
            self._refresh()

    def _refresh(self, *args: Any) -> None:
        self.table.setRowCount(len(self.project.spaces))
        for r, sp in enumerate(self.project.spaces):
            eq = sp.room_equipment
            diff_type = getattr(eq, 'supply_terminal_type', '') if eq else ''
            diff_qty = getattr(eq, 'supply_terminal_qty', 0) if eq else 0
            cells = [
                sp.number, sp.name,
                f"{sp.heat_loss_w/1000:.2f}" if sp.heat_loss_w else "",
                (eq.heating_terminal_type or "") if eq else "",
                f"{eq.heating_terminal_power_w:.0f}" if eq and eq.heating_terminal_power_w else "",
                f"{eq.heating_terminal_qty:.0f}" if eq and eq.heating_terminal_qty else "",
                (diff_type or "") if eq else "",
                f"{diff_qty:.0f}" if eq and diff_qty else "",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c in (2, 4, 5, 7):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            visible = True
            if t:
                row_text = " ".join(
                    (it.text() if (it := self.table.item(r, c)) is not None else "")
                    for c in range(self.table.columnCount())
                ).lower()
                visible = t in row_text
            self.table.setRowHidden(r, not visible)
