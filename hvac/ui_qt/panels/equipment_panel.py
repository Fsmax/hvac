# -*- coding: utf-8 -*-
"""EquipmentPanel — ручной подбор и настройка оборудования.

Связывает цепочку расчётов в одну редактируемую картину:

    Источник (котёл / чиллер)
      └─ Контур  →  нагрузка (помещения + калориферы AHU), DN, Δp, насос
    Σ нагрузок × запас  →  мощность источника + количество агрегатов

Всё настраивается ВРУЧНУЮ (как и зонирование): добавить источник/AHU,
двойным кликом открыть параметры (t°-график, КПД, COP, КПД рекуператора),
прикрепить калорифер/охладитель AHU к контуру, задать мощность и количество
агрегатов вручную (override авто-подбора). Кнопка «Посчитать подбор»
прогоняет нагрузку AHU, гидравлику труб и подбор насосов.

Расчётная свёртка — `hvac.equipment_sizing.select_equipment`; правки —
`HVACProject.update_zone_system/_circuit` (`ZoningMixin`). Системы и контуры
создаются здесь или в «Зонах и системах».
"""
from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.equipment_sizing import SourceSelection, select_equipment
from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.sizing_helpers import suggest_ahu_size
from hvac.ui_qt.bridge import ProjectBridge


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


class EquipmentPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.title_lbl = QLabel(_t("panel.equipment.title"))
        self.title_lbl.setProperty("role", "h1")
        outer.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel(_t("panel.equipment.subtitle"))
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        outer.addWidget(self.subtitle_lbl)

        # ----- управление: добавить / запасы / пересчёт -----
        ctl = QHBoxLayout()
        self.add_boiler_btn = QPushButton(_t("panel.equipment.btn.add_boiler"))
        self.add_boiler_btn.clicked.connect(lambda: self._add_source("heating"))
        ctl.addWidget(self.add_boiler_btn)
        self.add_chiller_btn = QPushButton(_t("panel.equipment.btn.add_chiller"))
        self.add_chiller_btn.clicked.connect(lambda: self._add_source("cooling"))
        ctl.addWidget(self.add_chiller_btn)
        self.add_ahu_btn = QPushButton(_t("panel.equipment.btn.add_ahu"))
        self.add_ahu_btn.clicked.connect(lambda: self._add_source("ventilation"))
        ctl.addWidget(self.add_ahu_btn)
        ctl.addSpacing(16)

        self.margin_h_lbl = QLabel(_t("panel.equipment.lbl.margin_heat"))
        ctl.addWidget(self.margin_h_lbl)
        self.margin_h = _spin(1.10, 1.0, 1.5, 0.05, 2)
        self.margin_h.valueChanged.connect(self._refresh)
        ctl.addWidget(self.margin_h)
        self.margin_c_lbl = QLabel(_t("panel.equipment.lbl.margin_cool"))
        ctl.addWidget(self.margin_c_lbl)
        self.margin_c = _spin(1.15, 1.0, 1.5, 0.05, 2)
        self.margin_c.valueChanged.connect(self._refresh)
        ctl.addWidget(self.margin_c)
        ctl.addStretch(1)
        self.compute_btn = QPushButton(_t("panel.equipment.btn.compute"))
        self.compute_btn.setProperty("role", "primary")
        self.compute_btn.setCursor(Qt.PointingHandCursor)
        self.compute_btn.clicked.connect(self._compute)
        ctl.addWidget(self.compute_btn)
        outer.addLayout(ctl)

        self.hint_lbl = QLabel(_t("panel.equipment.hint.edit"))
        self.hint_lbl.setProperty("role", "muted")
        outer.addWidget(self.hint_lbl)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, stretch=1)

        heat_w = QWidget()
        heat_l = QVBoxLayout(heat_w)
        heat_l.setContentsMargins(0, 0, 0, 0)
        self.heat_tree = self._make_tree("heating")
        heat_l.addWidget(self.heat_tree, stretch=1)
        self.dhw_lbl = QLabel("")
        self.dhw_lbl.setProperty("role", "muted")
        heat_l.addWidget(self.dhw_lbl)
        self.tabs.addTab(heat_w, _t("panel.equipment.tab.heat"))

        self.cool_tree = self._make_tree("cooling")
        self.tabs.addTab(self.cool_tree, _t("panel.equipment.tab.cool"))

        self.ahu_table = QTableWidget(0, len(_AHU_COL_KEYS))
        self.ahu_table.setHorizontalHeaderLabels([_t(k) for k in _AHU_COL_KEYS])
        self.ahu_table.setAlternatingRowColors(True)
        self.ahu_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ahu_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ahu_table.verticalHeader().setVisible(False)
        self.ahu_table.horizontalHeader().setStretchLastSection(True)
        self.ahu_table.cellDoubleClicked.connect(self._edit_ahu_row)
        self.tabs.addTab(self.ahu_table, _t("panel.equipment.tab.ahu"))

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.zonesChanged, bridge.calculationDone,
                    bridge.ventilationDone, bridge.ahuLoadsCalculated):
            sig.connect(self._refresh)
        self._refresh()

    def _make_tree(self, domain: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setProperty("domain", domain)
        tree.setColumnCount(len(_TREE_COL_KEYS))
        tree.setHeaderLabels([_t(k) for k in _TREE_COL_KEYS])
        tree.setAlternatingRowColors(True)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(_TREE_COL_KEYS)):
            tree.header().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        tree.itemDoubleClicked.connect(
            lambda item, _c, d=domain: self._edit_tree_item(d, item))
        return tree

    # ---------- добавление / редактирование ----------
    def _add_source(self, domain: str) -> None:
        title_key = {"heating": "panel.equipment.dlg.add_boiler",
                     "cooling": "panel.equipment.dlg.add_chiller",
                     "ventilation": "panel.equipment.dlg.add_ahu"}[domain]
        name, ok = QInputDialog.getText(
            self, _t(title_key), _t("panel.equipment.f.name"))
        if ok and name.strip():
            self.project.add_zone_system(domain, name.strip())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _edit_tree_item(self, domain: str, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole) or ("", "", "")
        kind, _dom, name = data
        if kind == "source":
            self._edit_source(domain, name)
        elif kind == "circuit":
            self._edit_circuit(domain, name)

    def _edit_source(self, domain: str, name: str) -> None:
        sysobj = self.project.systems_of(domain).get(name)
        if sysobj is None:
            return
        sel = select_equipment(self.project, margin_heating=self.margin_h.value(),
                               margin_cooling=self.margin_c.value())
        req = next((s.required_kw for s in sel.sources(domain)
                    if s.name == name), 0.0)
        dlg = _SourceDialog(self, domain=domain, sysobj=sysobj, required_kw=req)
        if dlg.exec() == QDialog.Accepted:
            self.project.update_zone_system(domain, name, **dlg.values())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _edit_circuit(self, domain: str, name: str) -> None:
        cobj = self.project.circuits_of(domain).get(name)
        if cobj is None:
            return
        dlg = _CircuitDialog(self, domain=domain, cobj=cobj,
                             types=self.project.circuit_types_for(domain))
        if dlg.exec() == QDialog.Accepted:
            self.project.update_zone_circuit(domain, name, **dlg.values())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    def _edit_ahu_row(self, row: int, _col: int = 0) -> None:
        names = sorted(self.project.ventilation_systems.keys())
        if not (0 <= row < len(names)):
            return
        vsys = self.project.ventilation_systems[names[row]]
        dlg = _AHUDialog(
            self, vsys=vsys,
            heating_circuits=sorted(self.project.circuits_of("heating").keys()),
            cooling_circuits=sorted(self.project.circuits_of("cooling").keys()))
        if dlg.exec() == QDialog.Accepted:
            self.project.update_zone_system("ventilation", vsys.name, **dlg.values())
            self.bridge.dirtyChanged.emit(True)
            self._refresh()

    # ---------- пересчёт цепочки ----------
    def _compute(self) -> None:
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

    # ---------- отрисовка ----------
    def _refresh(self, *args: Any) -> None:
        sel = select_equipment(
            self.project, margin_heating=self.margin_h.value(),
            margin_cooling=self.margin_c.value())
        self._fill_source_tree(self.heat_tree, "heating", sel.heating)
        self._fill_source_tree(self.cool_tree, "cooling", sel.cooling)
        self.dhw_lbl.setText(
            _t("panel.equipment.dhw").format(kw=f"{sel.q_dhw_w / 1000:.1f}")
            if sel.q_dhw_w > 0 else "")
        self._fill_ahu_table()

    def _fill_source_tree(self, tree: QTreeWidget, domain: str,
                          sources: List[SourceSelection]) -> None:
        tree.clear()
        for src in sources:
            if src.units:
                pick = _t("panel.equipment.fmt.units").format(
                    kw=f"{src.unit_kw:g}", n=src.units)
                if src.manual:
                    pick = _t("panel.equipment.fmt.manual").format(pick=pick)
            else:
                pick = "—"
            top = QTreeWidgetItem([
                src.name, f"{src.required_kw:.1f}", pick, "", "", ""])
            top.setData(0, Qt.UserRole, ("source", domain, src.name))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            tree.addTopLevelItem(top)

            for c in src.circuits:
                pump = ""
                if c.pump_model:
                    pump = _t("panel.equipment.fmt.pump").format(
                        model=c.pump_model, flow=f"{c.pump_flow_m3_h:.1f}",
                        head=f"{c.pump_head_m:.1f}")
                child = QTreeWidgetItem([
                    f"{c.name}  ({c.n_rooms})", f"{c.q_total_w / 1000:.1f}",
                    _ctype_label(c.circuit_type),
                    f"{c.dn_mm:.0f}" if c.dn_mm else "",
                    f"{c.dp_pa / 1000:.1f}" if c.dp_pa else "", pump])
                child.setData(0, Qt.UserRole, ("circuit", domain, c.name))
                top.addChild(child)

            if src.n_direct_rooms:
                top.addChild(QTreeWidgetItem([
                    f"{_t('panel.equipment.direct')}  ({src.n_direct_rooms})",
                    f"{src.q_direct_w / 1000:.1f}", "", "", "", ""]))
            top.setExpanded(True)

    def _fill_ahu_table(self) -> None:
        loads = self.project.ahu_loads or {}
        names = sorted(self.project.ventilation_systems.keys())
        self.ahu_table.setRowCount(len(names))
        for r, name in enumerate(names):
            vsys = self.project.ventilation_systems[name]
            info = loads.get(name, {})
            flow = info.get("supply_m3h", 0.0)
            q_cool = (info.get("q_cooler_sens_w", 0)
                      + info.get("q_cooler_lat_w", 0)) / 1000
            cells = [
                name, f"{flow:.0f}", suggest_ahu_size(flow),
                f"{info.get('q_heater_w', 0) / 1000:.1f}",
                f"{q_cool:.1f}",
                "✓" if getattr(vsys, "has_recovery", False) else "—",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c >= 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ahu_table.setItem(r, c, item)

    # ---------- локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.equipment.title"))
        self.subtitle_lbl.setText(_t("panel.equipment.subtitle"))
        self.add_boiler_btn.setText(_t("panel.equipment.btn.add_boiler"))
        self.add_chiller_btn.setText(_t("panel.equipment.btn.add_chiller"))
        self.add_ahu_btn.setText(_t("panel.equipment.btn.add_ahu"))
        self.margin_h_lbl.setText(_t("panel.equipment.lbl.margin_heat"))
        self.margin_c_lbl.setText(_t("panel.equipment.lbl.margin_cool"))
        self.compute_btn.setText(_t("panel.equipment.btn.compute"))
        self.hint_lbl.setText(_t("panel.equipment.hint.edit"))
        self.tabs.setTabText(0, _t("panel.equipment.tab.heat"))
        self.tabs.setTabText(1, _t("panel.equipment.tab.cool"))
        self.tabs.setTabText(2, _t("panel.equipment.tab.ahu"))
        for tree in (self.heat_tree, self.cool_tree):
            tree.setHeaderLabels([_t(k) for k in _TREE_COL_KEYS])
        self.ahu_table.setHorizontalHeaderLabels([_t(k) for k in _AHU_COL_KEYS])
        self._refresh()
