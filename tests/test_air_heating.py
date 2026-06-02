# -*- coding: utf-8 -*-
"""Тесты воздушного отопления/охлаждения (hvac.air_heating).

Проверяют:
  - формулу подбора расхода L = Q/(0.28·ρ·c·Δt);
  - что итоговый расход = max(вентиляция, отопление, охлаждение);
  - идемпотентность apply_air_heating;
  - повышение температуры подачи AHU и рост мощности калорифера/охладителя;
  - что непомеченные помещения не затрагиваются.
"""

import pytest

from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment import VentilationSystem
from hvac.ahu_load import aggregate_ahus
from hvac.air_heating import (
    required_air_flow, compute_air_heating, apply_air_heating,
    effective_ahu_supply_temps,
)
from hvac.engine.base import air_density


def _add_space(p, sid, number, **kw):
    sp = Space(space_id=sid, number=number, name="Room", level="L1",
               area_m2=20.0, volume_m3=60.0, height_m=3.0, room_type="Офис")
    for k, v in kw.items():
        setattr(sp, k, v)
    p.spaces.append(sp)
    p._space_by_id[sid] = sp
    return sp


# ------------------------------------------------------------ формула расхода
class TestRequiredAirFlow:
    def test_basic(self):
        # Q=2000 Вт, Δt=20K, ρ при 20°C ≈ 1.205
        rho = air_density(20.0)
        L = required_air_flow(2000.0, 20.0, rho)
        # обратная проверка: Q = 0.28·L·ρ·c·Δt
        q_back = 0.28 * L * rho * 1.005 * 20.0
        assert q_back == pytest.approx(2000.0, rel=1e-6)
        assert 290 < L < 305

    def test_zero_load(self):
        assert required_air_flow(0.0, 20.0, 1.2) == 0.0

    def test_nonpositive_dt(self):
        assert required_air_flow(2000.0, 0.0, 1.2) == 0.0
        assert required_air_flow(2000.0, -5.0, 1.2) == 0.0

    def test_smaller_dt_more_air(self):
        rho = air_density(20.0)
        assert required_air_flow(2000.0, 10.0, rho) > required_air_flow(2000.0, 20.0, rho)


# ------------------------------------------------ эффективная t подачи AHU
class TestEffectiveSupplyTemps:
    def test_neutral_when_no_flags(self):
        ahu = VentilationSystem(name="П1")
        sp = Space("1", "R", "n", "L1", 10, 30)
        tw, ts = effective_ahu_supply_temps(ahu, [sp], 1.3, 1.15)
        assert tw == ahu.t_supply_winter   # 16
        assert ts == ahu.t_supply_summer   # 18

    def test_heating_temp_from_load(self):
        # подача = t_помещения + ΣQ/(0.28·L·ρ·c), не выше предела
        ahu = VentilationSystem(name="П1", t_supply_air_heating=45.0)
        sp = Space("1", "R", "n", "L1", 20, 60, air_heating=True, t_in_heat=20.0)
        sp.heat_loss_w = 3000.0
        sp.supply_m3h = 500.0
        rho = 1.37
        tw, ts = effective_ahu_supply_temps(ahu, [sp], rho, 1.15)
        rise = 3000.0 / (0.28 * 500.0 * rho * 1.005)
        assert tw == pytest.approx(min(45.0, 20.0 + rise))
        assert ts == ahu.t_supply_summer

    def test_heating_temp_capped(self):
        # огромная нагрузка → подача упирается в предел t_supply_air_heating
        ahu = VentilationSystem(name="П1", t_supply_air_heating=40.0)
        sp = Space("1", "R", "n", "L1", 20, 60, air_heating=True, t_in_heat=20.0)
        sp.heat_loss_w = 50_000.0
        sp.supply_m3h = 100.0
        tw, _ = effective_ahu_supply_temps(ahu, [sp], 1.37, 1.15)
        assert tw == 40.0

    def test_cooling_temp_from_load(self):
        ahu = VentilationSystem(name="П1", t_supply_air_cooling=14.0)
        sp = Space("1", "R", "n", "L1", 20, 60, air_cooling=True, t_in_cool=24.0)
        sp.heat_gain_w = 4000.0
        sp.supply_m3h = 600.0
        rho = 1.14
        _, ts = effective_ahu_supply_temps(ahu, [sp], 1.3, rho)
        drop = 4000.0 / (0.28 * 600.0 * rho * 1.005)
        assert ts == pytest.approx(max(14.0, 24.0 - drop))


# ------------------------------------------------------- подбор по проекту
def _project_with_ahu(**ahu_kw):
    p = HVACProject()
    p.ventilation_systems["П1"] = VentilationSystem(name="П1", **ahu_kw)
    return p


class TestComputeAirHeating:
    def test_only_flagged_rooms(self):
        p = _project_with_ahu()
        _add_space(p, "1", "R-1", system_ventilation="П1",
                   heat_loss_w=3000, air_heating=True)
        _add_space(p, "2", "R-2", system_ventilation="П1", heat_loss_w=3000)
        res = compute_air_heating(p)
        assert set(res) == {"1"}     # только помеченное

    def test_heating_flow_covers_loss(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=3000, t_in_heat=20.0, air_heating=True)
        # вентиляционная база — мала, ведущей должна стать нагрузка
        sp.ventilation_breakdown = {"supply_m3h": 50.0}
        sp.supply_m3h = 50.0
        row = compute_air_heating(p)["1"]
        dt = 40.0 - 20.0
        rho = air_density(20.0)
        assert row.req_heat_m3h == pytest.approx(required_air_flow(3000, dt, rho))
        assert row.governed_by == "heating"
        assert row.design_supply_m3h == pytest.approx(row.req_heat_m3h)

    def test_ventilation_governs_when_larger(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=500, t_in_heat=20.0, air_heating=True)
        sp.ventilation_breakdown = {"supply_m3h": 800.0}
        sp.supply_m3h = 800.0
        row = compute_air_heating(p)["1"]
        assert row.governed_by == "ventilation"
        assert row.design_supply_m3h == pytest.approx(800.0)

    def test_cooling_flow(self):
        p = _project_with_ahu(t_supply_air_cooling=16.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_gain_w=4000, t_in_cool=24.0, air_cooling=True)
        sp.ventilation_breakdown = {"supply_m3h": 60.0}
        sp.supply_m3h = 60.0
        row = compute_air_heating(p)["1"]
        dt = 24.0 - 16.0
        rho = air_density(24.0)
        assert row.req_cool_m3h == pytest.approx(required_air_flow(4000, dt, rho))
        assert row.governed_by == "cooling"

    def test_warns_when_no_ahu(self):
        p = HVACProject()
        _add_space(p, "1", "R-1", heat_loss_w=3000, air_heating=True)
        row = compute_air_heating(p)["1"]
        assert any("установк" in w for w in row.warnings)

    def test_warns_when_supply_not_above_room(self):
        # подача 16°C ниже tвн 20°C — отопление воздухом невозможно
        p = _project_with_ahu(t_supply_air_heating=16.0)
        _add_space(p, "1", "R-1", system_ventilation="П1",
                   heat_loss_w=3000, t_in_heat=20.0, air_heating=True)
        row = compute_air_heating(p)["1"]
        assert row.req_heat_m3h == 0.0
        assert any("невозможно" in w for w in row.warnings)


# --------------------------------------------------------- apply + AHU power
class TestApplyAirHeating:
    def test_boosts_supply(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=5000, t_in_heat=20.0, air_heating=True)
        sp.ventilation_breakdown = {"supply_m3h": 50.0}
        sp.supply_m3h = 50.0
        n = apply_air_heating(p)
        assert n == 1
        assert sp.supply_m3h > 50.0
        assert sp.ach_calculated == pytest.approx(sp.supply_m3h / sp.volume_m3)

    def test_idempotent(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=5000, t_in_heat=20.0, air_heating=True)
        sp.ventilation_breakdown = {"supply_m3h": 50.0}
        sp.supply_m3h = 50.0
        apply_air_heating(p)
        first = sp.supply_m3h
        apply_air_heating(p)              # повторный вызов
        assert sp.supply_m3h == pytest.approx(first)

    def test_unflagged_untouched(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=5000, t_in_heat=20.0)
        sp.ventilation_breakdown = {"supply_m3h": 50.0}
        sp.supply_m3h = 50.0
        apply_air_heating(p)
        assert sp.supply_m3h == 50.0

    def test_unboost_when_flag_removed(self):
        # включили воздушное отопление → расход поднят; выключили → вернулся
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=5000, t_in_heat=20.0, air_heating=True)
        sp.ventilation_breakdown = {"supply_m3h": 50.0}
        sp.supply_m3h = 50.0
        apply_air_heating(p)
        assert sp.supply_m3h > 50.0
        sp.air_heating = False
        apply_air_heating(p)
        assert sp.supply_m3h == pytest.approx(50.0)

    def test_ahu_heater_power_rises_with_air_heating(self):
        # Та же установка/расход, но с воздушным отоплением подача поднимается
        # выше нейтральной (16°C) ровно настолько, чтобы покрыть нагрузку
        # помещения — мощность калорифера больше.
        def build(air):
            p = _project_with_ahu(t_supply_winter=16.0, t_supply_air_heating=45.0)
            p.params.t_out_heating = -16.0
            sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                            heat_loss_w=6000, t_in_heat=20.0, air_heating=air)
            sp.supply_m3h = 1000.0
            return p
        load_plain = aggregate_ahus(build(False))["П1"]
        load_air = aggregate_ahus(build(True))["П1"]
        assert load_air.q_heater_w > load_plain.q_heater_w
        assert load_air.t_supply_winter > 16.0      # подача поднята под нагрузку
        assert load_air.t_supply_winter <= 45.0     # но не выше предела
        assert load_plain.t_supply_winter == 16.0

    def test_ahu_heater_not_oversized(self):
        # Расход задан охлаждением (большой), нагрузка отопления мала: калорифер
        # НЕ должен греть весь поток до предела — только до нужного.
        p = _project_with_ahu(t_supply_winter=16.0, t_supply_air_heating=45.0)
        p.params.t_out_heating = -16.0
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        heat_loss_w=2000, t_in_heat=20.0, air_heating=True)
        sp.supply_m3h = 5000.0                       # большой расход (от охлаждения)
        load = aggregate_ahus(p)["П1"]
        # подача чуть выше t помещения, далеко от предела 45°C
        assert 20.0 < load.t_supply_winter < 25.0


# --------------------------------------------------- интеграция с пайплайном
class TestVentilationPipeline:
    def test_calculate_ventilation_applies_boost(self):
        p = _project_with_ahu(t_supply_air_heating=40.0)
        sp = _add_space(p, "1", "R-1", system_ventilation="П1",
                        room_type="Офис", t_in_heat=20.0, air_heating=True)
        sp.heat_loss_w = 8000.0
        p.calculate_ventilation()
        vent_only = sp.ventilation_breakdown.get("supply_m3h", 0.0)
        # расход поднят выше вентиляционной нормы
        assert sp.supply_m3h >= vent_only
        row = p.compute_air_heating()["1"]
        assert sp.supply_m3h == pytest.approx(row.design_supply_m3h)
