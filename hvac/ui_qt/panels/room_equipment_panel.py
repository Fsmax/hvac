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
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.room_equipment import (
    COOLING_TERMINAL_TYPES, EXHAUST_TERMINAL_TYPES, HEATING_TERMINAL_TYPES,
    SUPPLY_TERMINAL_TYPES, RoomEquipment,
    serialize_room_equipment, deserialize_room_equipment,
)
from hvac.ui_qt.bridge import ProjectBridge


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


class RoomEquipmentPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._clip: dict | None = None          # буфер: скопированное оборудование
        self._undo: list[dict] = []             # стек снимков для отмены

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.room_eq.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.apply_btn = QPushButton(_t("panel.room_eq.btn.apply_sel"))
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_to_selected)
        head.addWidget(self.apply_btn)
        self.clear_btn = QPushButton(_t("panel.room_eq.btn.clear"))
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_selected)
        head.addWidget(self.clear_btn)
        outer.addLayout(head)

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
        # Множественное выделение строк (Ctrl/Shift) для групповых операций.
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._edit_row)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        widths = [80, 200, 100, 200, 100, 80, 200, 80, 120, 120, 120]
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
        self.apply_btn.setText(_t("panel.room_eq.btn.apply_sel"))
        self.clear_btn.setText(_t("panel.room_eq.btn.clear"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])

    # ---------- Выбор / снимки / отмена ----------
    def _selected_rows(self) -> list[int]:
        """Индексы выделенных строк (= индексы в project.spaces)."""
        sel = self.table.selectionModel()
        if sel is None:
            return []
        return sorted({idx.row() for idx in sel.selectedRows()})

    def _ids_for(self, rows: list[int]) -> list[str]:
        return [self.project.spaces[r].space_id for r in rows
                if 0 <= r < len(self.project.spaces)]

    def _warn_no_selection(self) -> None:
        QMessageBox.information(self, _t("panel.room_eq.title"),
                                _t("panel.room_eq.msg.no_selection"))

    def _push_undo(self, space_ids: list[str]) -> None:
        """Снимок оборудования И привязок к контурам перед изменением."""
        eq_snap: dict = {}
        for sid in space_ids:
            sp = self.project._space_by_id.get(sid)
            eq = sp.room_equipment if sp else None
            eq_snap[sid] = serialize_room_equipment(eq) if eq else None
        self._undo.append({
            "eq": eq_snap,
            "zoning": self.project.snapshot_zoning(space_ids),
        })
        del self._undo[:-50]                       # ограничиваем глубину

    def _apply_undo(self) -> None:
        if not self._undo:
            return
        snap = self._undo.pop()
        for sid, data in snap["eq"].items():
            sp = self.project._space_by_id.get(sid)
            if sp is None:
                continue
            sp.room_equipment = deserialize_room_equipment(data) if data else None
        self.project.restore_zoning(snap["zoning"])
        self.project.emit("equipment_changed")
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _apply_connection(self, ids: list[str], conn: dict) -> None:
        """Записывает привязки помещений к контурам/AHU (через зонирование)."""
        if not conn:
            return
        ch = conn.get("circuit_heating", "")
        if ch:
            self.project.assign_rooms_to_circuit("heating", ids, ch)
        else:
            self.project.clear_rooms_assignment("heating", ids, "circuit")
        cc = conn.get("circuit_cooling", "")
        if cc:
            self.project.assign_rooms_to_circuit("cooling", ids, cc)
        else:
            self.project.clear_rooms_assignment("cooling", ids, "circuit")
        sv = conn.get("system_ventilation", "")
        if sv:
            self.project.assign_rooms_to_system("ventilation", ids, sv)
        else:
            self.project.clear_rooms_assignment("ventilation", ids, "system")

    # ---------- Операции ----------
    def _edit_row(self, row: int, _col: int = 0) -> None:
        if row < 0 or row >= len(self.project.spaces):
            return
        sp = self.project.spaces[row]
        dlg = RoomEquipmentDialog(sp, self, project=self.project)
        if dlg.exec() == QDialog.Accepted:
            self._push_undo([sp.space_id])
            self.project.set_room_equipment(sp.space_id, **dlg.values())
            self._apply_connection([sp.space_id], dlg.connection())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _apply_to_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._warn_no_selection()
            return
        anchor = self.project.spaces[rows[0]]
        dlg = RoomEquipmentDialog(
            anchor, self, show_loads=False, project=self.project,
            title=_t("panel.room_eq.dlg.apply_title").format(n=len(rows)))
        if dlg.exec() != QDialog.Accepted:
            return
        ids = self._ids_for(rows)
        self._push_undo(ids)
        n = self.project.apply_room_equipment(ids, dlg.values())
        self._apply_connection(ids, dlg.connection())
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.applied").format(n=n), 4000)

    def _copy(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._warn_no_selection()
            return
        eq = self.project.spaces[rows[0]].room_equipment
        if eq is None:
            self.bridge.statusMessage.emit(
                _t("panel.room_eq.status.nothing_copy"), 3000)
            return
        self._clip = serialize_room_equipment(eq)
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.copied").format(
                room=self.project.spaces[rows[0]].number), 3000)

    def _paste(self) -> None:
        if self._clip is None:
            return
        rows = self._selected_rows()
        if not rows:
            self._warn_no_selection()
            return
        ids = self._ids_for(rows)
        self._push_undo(ids)
        n = self.project.apply_room_equipment(ids, dict(self._clip))
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.pasted").format(n=n), 4000)

    def _clear_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._warn_no_selection()
            return
        ids = self._ids_for(rows)
        self._push_undo(ids)
        n = self.project.clear_room_equipment(ids)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.room_eq.status.cleared").format(n=n), 4000)

    def _show_context_menu(self, pos) -> None:
        if not self.project.spaces:
            return
        rows = self._selected_rows()
        has_sel = bool(rows)
        menu = QMenu(self)
        act_edit = menu.addAction(_t("panel.room_eq.ctx.edit"))
        act_apply = menu.addAction(_t("panel.room_eq.ctx.apply_sel"))
        menu.addSeparator()
        act_copy = menu.addAction(_t("panel.room_eq.ctx.copy"))
        act_paste = menu.addAction(_t("panel.room_eq.ctx.paste"))
        act_clear = menu.addAction(_t("panel.room_eq.ctx.clear"))
        menu.addSeparator()
        act_undo = menu.addAction(_t("panel.room_eq.ctx.undo"))

        act_edit.setEnabled(len(rows) == 1)
        act_apply.setEnabled(has_sel)
        act_copy.setEnabled(len(rows) == 1)
        act_paste.setEnabled(has_sel and self._clip is not None)
        act_clear.setEnabled(has_sel)
        act_undo.setEnabled(bool(self._undo))

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_edit:
            self._edit_row(rows[0])
        elif chosen is act_apply:
            self._apply_to_selected()
        elif chosen is act_copy:
            self._copy()
        elif chosen is act_paste:
            self._paste()
        elif chosen is act_clear:
            self._clear_selected()
        elif chosen is act_undo:
            self._apply_undo()

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
                sp.circuit_heating or "",
                sp.circuit_cooling or "",
                sp.system_ventilation or "",
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
