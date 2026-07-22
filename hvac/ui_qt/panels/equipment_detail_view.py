# -*- coding: utf-8 -*-
"""EquipmentDetailView — полная карточка оборудования/источника (просмотр+правка).

Используется панелью «Оборудование»: выбрал установку слева — справа полная
информация и редактируемые параметры с ЖИВЫМ пересчётом.

- Вентиляция (AHU / вытяжной / приточный / местный отсос): температуры подачи,
  КПД рекуператора, давление и КПД вентилятора → калорифер/охладитель (воздух +
  вода) и вентилятор.
- Источник тепла/холода (котёл / чиллер): график, КПД/COP, ручной подбор
  мощности → требуемая мощность, подобранные агрегаты, контуры, помещения.

Физику считают ядра `hvac.equipment_detail` и `hvac.equipment_sizing`.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QLabel, QPushButton, QSpinBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from hvac.equipment import VENT_KIND_SIDE
from hvac.equipment_detail import compute_equipment_detail
from hvac.i18n import t as _t
from hvac.ui_qt.panels.equipment_panel import _spin


def _src_label(src: str) -> str:
    return _t("panel.detail.src." + src, default=src)


class EquipmentDetailView(QWidget):
    def __init__(self, project, bridge, on_changed=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._on_changed = on_changed       # колбэк: обновить дерево/сводку
        self._loading = False
        self._vname: Optional[str] = None   # имя редактируемой вентсистемы
        self._sname: Optional[str] = None   # имя источника тепла/холода
        self._sdomain: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.header = QLabel(_t("panel.detail.none"))
        self.header.setProperty("role", "h2")
        self.header.setWordWrap(True)
        outer.addWidget(self.header)

        # ---- параметры вентиляции ----
        self.params_box = QGroupBox(_t("panel.detail.params"))
        vform = QFormLayout(self.params_box)
        self.t_in_w = _spin(20.0, 5, 60, 1)
        self.t_in_s = _spin(16.0, 5, 40, 1)
        self.eta_w = _spin(0.0, 0.0, 0.95, 0.05, 2)
        self.eta_s = _spin(0.0, 0.0, 0.95, 0.05, 2)
        self.fan_dp = _spin(0.0, 0, 5000, 50, 0)
        self.fan_eff = _spin(0.65, 0.3, 0.9, 0.05, 2)
        self._vrows = [
            ("panel.detail.f.t_supply_w", self.t_in_w),
            ("panel.detail.f.t_supply_s", self.t_in_s),
            ("panel.detail.f.eta_w", self.eta_w),
            ("panel.detail.f.eta_s", self.eta_s),
            ("panel.detail.f.fan_pressure", self.fan_dp),
            ("panel.detail.f.fan_eff", self.fan_eff),
        ]
        self._vlabels = {}
        for key, w in self._vrows:
            lbl = QLabel(_t(key))
            self._vlabels[key] = lbl
            vform.addRow(lbl, w)
            w.valueChanged.connect(self._on_param_changed)
        outer.addWidget(self.params_box)

        # ---- параметры источника тепла/холода ----
        self.src_box = QGroupBox(_t("panel.detail.params"))
        sform = QFormLayout(self.src_box)
        self.s_t_sup = _spin(0.0, 0, 150, 1)
        self.s_t_ret = _spin(0.0, 0, 150, 1)
        self.s_effcop = _spin(0.0, 0.0, 8.0, 0.1, 2)
        self.s_cap = _spin(0.0, 0, 100000, 10, 0)
        self.s_units = QSpinBox()
        self.s_units.setRange(0, 50)
        self._effcop_lbl = QLabel(_t("panel.detail.f.eff"))
        sform.addRow(QLabel(_t("panel.detail.f.t_sup")), self.s_t_sup)
        sform.addRow(QLabel(_t("panel.detail.f.t_ret")), self.s_t_ret)
        sform.addRow(self._effcop_lbl, self.s_effcop)
        sform.addRow(QLabel(_t("panel.detail.f.capacity")), self.s_cap)
        sform.addRow(QLabel(_t("panel.detail.f.units")), self.s_units)
        for w in (self.s_t_sup, self.s_t_ret, self.s_effcop, self.s_cap):
            w.valueChanged.connect(self._on_src_changed)
        self.s_units.valueChanged.connect(self._on_src_changed)
        self.s_catalog_btn = QPushButton(_t("panel.detail.btn.catalog"))
        self.s_catalog_btn.clicked.connect(self._pick_from_catalog)
        sform.addRow(self.s_catalog_btn)
        outer.addWidget(self.src_box)

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(False)
        outer.addWidget(self.body, stretch=1)

        self.clear()

    # -------------------------------------------------- состояние «ничего»
    def clear(self) -> None:
        self._vname = self._sname = self._sdomain = None
        self.header.setText(_t("panel.detail.none"))
        self.params_box.setVisible(False)
        self.src_box.setVisible(False)
        self.body.clear()

    # ------------------------------------------------------- маршрутизация
    def show_node(self, domain: str, kind: str, name: str) -> None:
        """kind: 'system' | 'circuit'; domain — heating/cooling/ventilation."""
        if not name:
            self.clear()
            return
        if domain == "ventilation" and kind == "system":
            self._show_ventilation(name)
        elif kind == "system":
            self._show_source(domain, name)
        elif kind == "circuit":
            self._show_circuit(domain, name)
        else:
            self.clear()

    # =================================================== вентиляция (правка)
    def _show_ventilation(self, name: str) -> None:
        sysobj = self.project.ventilation_systems.get(name)
        if sysobj is None:
            self.clear()
            return
        self._vname = name
        self._sname = None
        vkind = getattr(sysobj, "kind", "ahu")
        self.header.setText("{} · {}".format(
            name, _t("panel.detail.kind." + vkind, default=vkind)))

        self._loading = True
        self.t_in_w.setValue(float(getattr(sysobj, "t_supply_winter", 20.0)))
        self.t_in_s.setValue(float(getattr(sysobj, "t_supply_summer", 16.0)))
        self.eta_w.setValue(float(getattr(sysobj, "recovery_efficiency_winter", 0.0)))
        self.eta_s.setValue(float(getattr(sysobj, "recovery_efficiency_summer", 0.0)))
        self.fan_dp.setValue(float(getattr(sysobj, "fan_pressure_pa", 0.0)))
        self.fan_eff.setValue(float(getattr(sysobj, "fan_efficiency", 0.65)))
        side = VENT_KIND_SIDE.get(vkind, "supply")
        has_coils = side == "supply" and (
            getattr(sysobj, "has_heater", True) or getattr(sysobj, "has_cooler", True))
        for key in ("panel.detail.f.t_supply_w", "panel.detail.f.t_supply_s",
                    "panel.detail.f.eta_w", "panel.detail.f.eta_s"):
            self._vlabels[key].setVisible(has_coils)
            dict(self._vrows)[key].setVisible(has_coils)
        self.src_box.setVisible(False)
        self.params_box.setVisible(True)
        self._loading = False
        self._render_ventilation()

    def _on_param_changed(self) -> None:
        if self._loading or self._vname is None:
            return
        self.project.update_zone_system(
            "ventilation", self._vname,
            t_supply_winter=self.t_in_w.value(),
            t_supply_summer=self.t_in_s.value(),
            recovery_efficiency_winter=self.eta_w.value(),
            recovery_efficiency_summer=self.eta_s.value(),
            has_recovery=(self.eta_w.value() > 0 or self.eta_s.value() > 0),
            fan_pressure_pa=self.fan_dp.value(),
            fan_efficiency=self.fan_eff.value(),
        )
        self.bridge.dirtyChanged.emit(True)
        self._render_ventilation()
        if self._on_changed:
            self._on_changed()

    def _render_ventilation(self) -> None:
        if self._vname is None:
            self.body.clear()
            return
        det = compute_equipment_detail(self.project, self._vname)
        if det is None:
            self.body.clear()
            return
        rows = [_t("panel.detail.flows").format(
            n=det.n_spaces, sup=f"{det.supply_m3_h:.0f}",
            exh=f"{det.exhaust_m3_h:.0f}")]

        def _coil_html(title_key: str, c) -> str:
            if c is None:
                return ""
            air = _t("panel.detail.coil_air").format(
                q=f"{c.q_air_kw:.1f}", tin=f"{c.t_air_in:.1f}",
                tout=f"{c.t_air_out:.1f}", dt=f"{c.dt_air:.1f}")
            water = _t("panel.detail.coil_water").format(
                ts=f"{c.water_supply_c:.0f}", tr=f"{c.water_return_c:.0f}",
                dtw=f"{c.dt_water:.0f}", g=f"{c.water_flow_kg_h:.0f}",
                gm=f"{c.water_flow_m3_h:.2f}", dn=c.dn_mm,
                v=f"{c.water_velocity_m_s:.2f}")
            extra = ""
            if c.role == "cooler":
                extra = "<br>" + _t("panel.detail.cooler_extra").format(
                    qs=f"{c.q_sensible_w / 1000:.1f}",
                    ql=f"{c.q_latent_w / 1000:.1f}",
                    cond=f"{c.condensate_kg_h:.1f}")
            return "<p><b>{}</b><br>{}<br>{}{}</p>".format(
                _t(title_key), air, water, extra)

        rows.append(_coil_html("panel.detail.heater", det.heater))
        rows.append(_coil_html("panel.detail.cooler", det.cooler))

        def _fan_html(title_key: str, f) -> str:
            if f is None:
                return ""
            return "<p><b>{}</b><br>{}</p>".format(
                _t(title_key),
                _t("panel.detail.fan_line").format(
                    flow=f"{f.flow_m3_h:.0f}", dp=f"{f.pressure_pa:.0f}",
                    src=_src_label(f.pressure_source),
                    kw=f"{f.power_kw:.2f}", sfp=f"{f.sfp_w_m3_s:.0f}"))

        rows.append(_fan_html("panel.detail.fan_supply", det.fan_supply))
        rows.append(_fan_html("panel.detail.fan_exhaust", det.fan_exhaust))
        for w in det.warnings:
            rows.append(f"<p style='color:#c0392b'>⚠ {w}</p>")
        self.body.setHtml("".join(r for r in rows if r))

    # =================================================== источник (правка)
    def _show_source(self, domain: str, name: str) -> None:
        sysobj = self.project.systems_of(domain).get(name)
        if sysobj is None:
            self.clear()
            return
        self._sname = name
        self._sdomain = domain
        self._vname = None
        kind_key = ("panel.detail.kind.boiler" if domain == "heating"
                    else "panel.detail.kind.chiller")
        self.header.setText("{} · {}".format(name, _t(kind_key)))

        self._loading = True
        self.s_t_sup.setValue(float(getattr(sysobj, "t_supply", 0.0)))
        self.s_t_ret.setValue(float(getattr(sysobj, "t_return", 0.0)))
        if domain == "heating":
            self._effcop_lbl.setText(_t("panel.detail.f.eff"))
            self.s_effcop.setRange(0.3, 1.2)
            self.s_effcop.setSingleStep(0.01)
            self.s_effcop.setValue(float(getattr(sysobj, "efficiency", 0.92)))
        else:
            self._effcop_lbl.setText(_t("panel.detail.f.cop"))
            self.s_effcop.setRange(1.0, 8.0)
            self.s_effcop.setSingleStep(0.1)
            self.s_effcop.setValue(float(getattr(sysobj, "cop", 3.5)))
        self.s_cap.setValue(float(getattr(sysobj, "design_capacity_kw", 0.0)))
        self.s_units.setValue(int(getattr(sysobj, "unit_count", 0) or 0))
        self.params_box.setVisible(False)
        self.src_box.setVisible(True)
        self._loading = False
        self._render_source()

    def _on_src_changed(self) -> None:
        if self._loading or self._sname is None:
            return
        kw = dict(t_supply=self.s_t_sup.value(), t_return=self.s_t_ret.value(),
                  design_capacity_kw=self.s_cap.value(),
                  unit_count=self.s_units.value())
        kw["efficiency" if self._sdomain == "heating" else "cop"] = self.s_effcop.value()
        self.project.update_zone_system(self._sdomain, self._sname, **kw)
        self.bridge.dirtyChanged.emit(True)
        self._render_source()
        if self._on_changed:
            self._on_changed()

    def pick_from_catalog(self) -> None:
        """Каталожный подбор для текущего источника (и из меню дерева)."""
        self._pick_from_catalog()

    def _pick_from_catalog(self) -> None:
        """Каталожный подбор: заполняет мощность/кол-во/модель источника."""
        if self._sname is None or self._sdomain is None:
            return
        from hvac.equipment_sizing import select_equipment
        from hvac.ui_qt.panels.source_pick_dialog import SourcePickDialog
        sel = select_equipment(self.project)
        src = next((s for s in sel.sources(self._sdomain)
                    if s.name == self._sname), None)
        req = src.required_kw if src else 0.0
        dlg = SourcePickDialog(
            self, domain=self._sdomain, required_kw=req,
            context=_t("panel.srcpick.ctx.system").format(
                name=self._sname, q=f"{req:.0f}"))
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if not vals:
            return
        self.project.update_zone_system(self._sdomain, self._sname, **vals)
        self.bridge.dirtyChanged.emit(True)
        self._show_source(self._sdomain, self._sname)   # обновить спины+рендер
        if self._on_changed:
            self._on_changed()

    def _render_source(self) -> None:
        if self._sdomain is None or self._sname is None:
            self.body.clear()
            return
        from hvac.equipment_sizing import select_equipment
        sel = select_equipment(self.project)
        src = next((s for s in sel.sources(self._sdomain)
                    if s.name == self._sname), None)
        if src is None:
            self.body.clear()
            return
        margin = getattr(src, "margin", 1.0)
        q_base = getattr(src, "q_base_w", src.q_total_w)
        rows = [_t("panel.detail.src.required").format(
            req=f"{src.required_kw:.1f}", q=f"{q_base / 1000:.1f}",
            m=f"{margin:.2f}")]
        # тепловой баланс блока источника (помещения + установки + ГВС)
        if getattr(src, "block", ""):
            key = ("panel.detail.src.block_heat"
                   if self._sdomain == "heating"
                   else "panel.detail.src.block_cool")
            q_blk = (src.q_block_rooms_w + src.q_block_ahu_w
                     + src.q_block_dhw_w)
            rows.append(_t(key).format(
                block=src.block,
                rooms=f"{src.q_block_rooms_w / 1000:.1f}",
                ahu=f"{src.q_block_ahu_w / 1000:.1f}",
                dhw=f"{src.q_block_dhw_w / 1000:.1f}",
                q=f"{q_blk / 1000:.1f}"))
        pick_key = ("panel.detail.src.picked_manual" if src.manual
                    else "panel.detail.src.picked_auto")
        rows.append(_t(pick_key).format(
            unit=f"{src.unit_kw:g}", n=src.units,
            working=src.working_units, reserve=src.reserve_units,
            model=src.selected_model or "—"))
        if src.q_ahu_w > 0:
            rows.append(_t("panel.detail.src.ahu").format(
                q=f"{src.q_ahu_w / 1000:.1f}"))
        if src.n_direct_rooms:
            rows.append(_t("panel.detail.src.direct").format(
                n=src.n_direct_rooms, q=f"{src.q_direct_w / 1000:.1f}"))
        for c in src.circuits:
            rows.append(_t("panel.detail.source_circ").format(
                name=c.name, q=f"{c.q_total_w / 1000:.1f}", rooms=c.n_rooms,
                dn=f"{c.dn_mm:.0f}" if c.dn_mm else "—",
                pump=c.pump_display))
        self.body.setHtml("<br>".join(rows))

    def _show_circuit(self, domain: str, name: str) -> None:
        self._vname = self._sname = None
        self.params_box.setVisible(False)
        self.src_box.setVisible(False)
        from hvac.equipment_sizing import select_equipment
        sel = select_equipment(self.project)
        cs = next((c for s in sel.sources(domain) for c in s.circuits
                   if c.name == name), None)
        self.header.setText(name)
        if cs is None:
            self.body.clear()
            return
        self.body.setHtml(_t("panel.detail.circuit_head").format(
            q=f"{cs.q_total_w / 1000:.1f}", rooms=cs.n_rooms,
            qa=f"{cs.q_ahu_w / 1000:.1f}",
            dn=f"{cs.dn_mm:.0f}" if cs.dn_mm else "—",
            dp=f"{cs.dp_pa / 1000:.1f}" if cs.dp_pa else "—",
            pump=cs.pump_display))

    # ----------------------------------------------------------- i18n
    def retranslate_ui(self) -> None:
        self.params_box.setTitle(_t("panel.detail.params"))
        self.src_box.setTitle(_t("panel.detail.params"))
        self.s_catalog_btn.setText(_t("panel.detail.btn.catalog"))
        for key, lbl in self._vlabels.items():
            lbl.setText(_t(key))
        if self._vname:
            self._show_ventilation(self._vname)
        elif self._sname and self._sdomain:
            self._show_source(self._sdomain, self._sname)
        else:
            self.header.setText(_t("panel.detail.none"))
