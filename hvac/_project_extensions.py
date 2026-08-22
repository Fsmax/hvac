# -*- coding: utf-8 -*-
"""V37ExtensionsMixin — фасадные методы для расширений v3.7:
проверка точки росы, ГВС, энергопаспорт, подбор воздуховодов и труб.

Сами расчёты живут в отдельных модулях (dew_point, dhw, energy,
duct_sizing, pipe_sizing); миксин лишь связывает их с HVACProject.
"""

from __future__ import annotations
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.dhw import DHWSystem
    from hvac.duct_sizing import DuctNetwork
    from hvac.pipe_sizing import PipeNetwork
    from hvac.ahu_process import AHUProcess
    from hvac.heating_hydraulics import HeatingHydraulicsResult
    from hvac.radiator_catalog import RadiatorPick
    from hvac.acoustics import AcousticAnalysis
    from hvac.underfloor import UnderfloorLoop
    from hvac.fancoil_catalog import FancoilPick
    from hvac.vrf import VRFSystem
    from hvac.energy_simulation import EnergySimulationResult
    from hvac.specification import Specification
    from hvac.grille_catalog import GrilleRoomPick


class V37ExtensionsMixin:
    """Фасады расчётных модулей v3.7: dew_point, dhw, energy, ducts, pipes."""

    def check_condensation_risk(self,
                                rh_override: Optional[float] = None
                                ) -> List:
        """Проверка ограждений на риск конденсации (СП 50.13330 Прил. Е).

        Параметры
        ---------
        rh_override : если задано — используется для всех помещений
                      (например 55%). Иначе из ROOM_TYPE_RH_DESIGN.

        Возвращает
        ----------
        List[CondensationCheck] — по элементу на каждый внешний.
        """
        from hvac import dew_point as dp
        results = dp.analyze_project(self, rh_override=rh_override)
        self.condensation_results = results
        self.emit("condensation_checked")
        return results

    def calculate_dhw(self, strategy: str = "single") -> Dict[str, "DHWSystem"]:
        """Расчёт горячего водоснабжения по СП 30.13330.

        Параметры
        ---------
        strategy : "single"   — одна система на проект (дефолт),
                   "by_type"  — отдельно жильё / гостиница / офис / питание,
                   "by_zone"  — по полю system_heating.
        """
        from hvac import dhw
        result = dhw.calculate_project_dhw(self, system_strategy=strategy)
        self.dhw_systems = result
        self.emit("dhw_calculated")
        return result

    def calculate_energy_passport(self,
                                  building_type: Optional[str] = None,
                                  k_regulation: float = 1.0,
                                  k_internal_use: float = 0.8,
                                  internal_gain_w_m2: float = 10.0):
        """Энергетический паспорт здания (СП 50.13330 Прил. Г).

        Должно быть выполнено: recalculate() и желательно calculate_ahu_loads().

        Параметры
        ---------
        building_type      : "офис" / "гостиница" / "жилое 4-5 этажей" / ...
                             None → автоопределение по составу помещений.
        k_regulation       : 1.0 без авт., 0.85 при ИТП с погодной автоматикой.
        k_internal_use     : коэф. использования внутр. теплопост. (СП 50 — 0.8).
        internal_gain_w_m2 : усреднённые внутр. теплопост., Вт/м² (17 для жилья,
                             10 для общественных).
        """
        from hvac import energy
        result = energy.calculate_passport(
            self,
            building_type=building_type,
            k_regulation=k_regulation,
            k_internal_use=k_internal_use,
            internal_gain_w_m2=internal_gain_w_m2,
        )
        self.energy_passport = result
        self.emit("energy_passport_calculated")
        return result

    def size_ducts(self, shape: str = "round",
                   building_type: str = "public") -> Dict[str, "DuctNetwork"]:
        """Подбор сечений воздуховодов для всех вент. систем.

        Должно быть выполнено: calculate_ventilation().

        Параметры
        ---------
        shape         : "round" (круглые) или "rect" (прямоугольные).
        building_type : "public" / "residential" / "industrial" — для выбора
                        рекомендованных скоростей.
        """
        from hvac import duct_sizing
        result = duct_sizing.size_project_ducts(
            self, shape=shape, building_type=building_type,
        )
        self.duct_networks = result
        self.emit("ducts_sized")
        return result

    def size_pipes(self, pipe_material: str = "steel"
                   ) -> Dict[str, "PipeNetwork"]:
        """Гидравлический расчёт труб отопления — по контурам.

        Должно быть выполнено: recalculate() и auto_assign_zones() (system_heating).
        Если для AHU задан heating_circuit и выполнен calculate_ahu_loads() —
        нагрузка калорифера AHU добавляется в соответствующий контур.

        Параметры
        ---------
        pipe_material : "steel" (стальные ГОСТ 3262) или "pex" (PEX-Al-PEX).
        """
        from hvac import pipe_sizing
        result = pipe_sizing.size_project_pipes(
            self, pipe_material=pipe_material,
        )
        self.pipe_networks = result
        for name, net in result.items():
            circuit = self.heating_circuits.get(name)
            if circuit is None:
                continue
            circuit.pump_model = net.pump_model
            circuit.pump_flow_m3_h = net.pump_flow_m3_h
            circuit.pump_head_m = net.pump_head_m
            circuit.pump_working_units = net.pump_working_units
            circuit.pump_reserve_units = net.pump_reserve_units
            circuit.pump_catalog_covered = net.pump_catalog_covered
        self.emit("pipes_sized")
        return result

    def size_cooling_pipes(self, pipe_material: str = "steel"
                           ) -> Dict[str, "PipeNetwork"]:
        """Гидравлический расчёт труб холодоснабжения (фанкойлы / охладители AHU).

        Должно быть выполнено: recalculate() (для теплопоступлений) и
        желательно calculate_ahu_loads().

        Группировка по cooling_circuits / system_cooling. Нагрузка =
        полное теплопоступление помещения (sensible + latent), плюс
        нагрузки охладителей AHU, привязанных через cooling_circuit.
        """
        from hvac import pipe_sizing
        result = pipe_sizing.size_project_cooling_pipes(
            self, pipe_material=pipe_material,
        )
        self.cooling_pipe_networks = result
        for name, net in result.items():
            circuit = self.cooling_circuits.get(name)
            if circuit is None:
                continue
            circuit.pump_model = net.pump_model
            circuit.pump_flow_m3_h = net.pump_flow_m3_h
            circuit.pump_head_m = net.pump_head_m
            circuit.pump_working_units = net.pump_working_units
            circuit.pump_reserve_units = net.pump_reserve_units
            circuit.pump_catalog_covered = net.pump_catalog_covered
        self.emit("cooling_pipes_sized")
        return result

    def recompute_pipe_networks(self) -> None:
        """Пересчитывает Δp всех сохранённых сетей по текущим length_m
        и local_zeta_sum (после ручного редактирования участков).
        Расход и DN не меняются."""
        from hvac import pipe_sizing
        for net in self.pipe_networks.values():
            pipe_sizing.recompute_pipe_network(net)
        for net in self.cooling_pipe_networks.values():
            pipe_sizing.recompute_pipe_network(net)
        self.emit("pipes_recomputed")

    # ========================================================================
    # v4.1 — детальная инженерия
    # ========================================================================

    def compute_ahu_processes(
        self,
        modes=("winter", "summer", "transitional"),
        **process_kwargs,
    ) -> Dict[str, Dict[str, "AHUProcess"]]:
        """Психрометрический расчёт точек процесса для каждой AHU.

        Должно быть выполнено calculate_ahu_loads() (для получения AHULoad).
        Сохраняет результаты в self.ahu_processes: {ahu_name: {mode: process}}.

        process_kwargs пробрасываются в compute_ahu_process: параметры
        наружного RH, эффективности рекуператора по влаге, рециркуляции,
        целевой RH увлажнителя и т.д.
        """
        from hvac.ahu_load import aggregate_ahus
        from hvac.ahu_process import compute_ahu_process

        loads = aggregate_ahus(self)
        result: Dict[str, Dict[str, "AHUProcess"]] = {}
        for name, load in loads.items():
            result[name] = {}
            for m in modes:
                result[name][m] = compute_ahu_process(
                    load, self.params, mode=m, **process_kwargs)
        self.ahu_processes = result
        self.emit("ahu_processes_computed")
        return result

    def design_heating_hydraulics(
        self,
        *,
        static_height_m: float = 10.0,
        pump_reserve_factor: float = 1.30,
    ) -> Dict[str, "HeatingHydraulicsResult"]:
        """Подбор насосов и расширительных баков для всех контуров отопления.

        Должно быть выполнено size_pipes() (для total_pressure_loss_pa и
        total_flow_kg_h в pipe_networks).
        """
        from hvac.heating_hydraulics import design_hydraulics_for_network

        result: Dict[str, "HeatingHydraulicsResult"] = {}
        for name, net in self.pipe_networks.items():
            circuit = self.heating_circuits.get(name)
            circuit_type = (circuit.circuit_type if circuit
                              else "radiator")
            result[name] = design_hydraulics_for_network(
                net, circuit_type=circuit_type,
                static_height_m=static_height_m,
                pump_reserve_factor=pump_reserve_factor,
            )
            # Записываем подобранный насос обратно в HeatingCircuit (если есть)
            if circuit is not None:
                circuit.pump_model = result[name].pump.selected_model
                circuit.pump_flow_m3_h = result[name].pump.selected_flow_m3_h
                circuit.pump_head_m = result[name].pump.selected_head_m
                circuit.pump_working_units = result[name].pump.working_units
                circuit.pump_reserve_units = result[name].pump.reserve_units
                circuit.pump_catalog_covered = result[name].pump.catalog_covered
        self.heating_hydraulics_results = result
        self.emit("heating_hydraulics_designed")
        return result

    def select_radiators_for_all_spaces(
        self,
        *,
        t_supply: float = None,
        t_return: float = None,
        family_filter: Optional[List[str]] = None,
        prefer_sectional: bool = False,
    ) -> Dict[str, "RadiatorPick"]:
        """Подбор радиатора каждому помещению с heat_loss_w > 0.

        Если t_supply/t_return не заданы — берётся t_supply/t_return от
        первой подходящей HeatingSystem (или 80/60 по умолчанию).
        Результат записывается в self.radiator_picks и в каждый Space
        через get_or_create_equipment().
        """
        from hvac.radiator_catalog import select_radiator

        ts = t_supply if t_supply is not None else 80.0
        tr = t_return if t_return is not None else 60.0
        if t_supply is None and self.heating_systems:
            first = next(iter(self.heating_systems.values()))
            ts, tr = first.t_supply, first.t_return

        picks: Dict[str, "RadiatorPick"] = {}
        for sp in self.spaces:
            q = sp.heat_loss_w
            if q <= 0:
                continue
            pick = select_radiator(
                q, t_supply=ts, t_return=tr,
                t_room=sp.t_in_heat,
                family_filter=family_filter,
                prefer_sectional=prefer_sectional,
            )
            if pick is not None:
                picks[sp.space_id] = pick
        self.radiator_picks = picks
        self.emit("radiators_selected")
        return picks

    def select_grilles_for_all_spaces(
        self,
        *,
        max_lwa: float = 35.0,
        mount: Optional[str] = None,
        families: Optional[List[str]] = None,
        max_velocity: Optional[float] = None,
        max_dp: Optional[float] = None,
        max_a_mm: Optional[int] = None,
        max_b_mm: Optional[int] = None,
    ) -> Dict[str, "GrilleRoomPick"]:
        """Подбор приточной и вытяжной решётки каждому помещению.

        Берётся вентрасход помещения (Space.supply_m3h / exhaust_m3h);
        для каждого ненулевого направления подбирается решётка по расходу
        с ограничением шума LwA ≤ max_lwa (и опц. скорости/ΔP). Семейство
        и тип монтажа фильтруются параметрами mount/families.

        Результат пишется в self.grille_picks {space_id: GrilleRoomPick}
        для помещений, где подобрана хотя бы одна решётка.
        """
        from hvac.grille_catalog import select_grilles_for_room

        picks: Dict[str, "GrilleRoomPick"] = {}
        for sp in self.spaces:
            sup = getattr(sp, "supply_m3h", 0.0) or 0.0
            exh = getattr(sp, "exhaust_m3h", 0.0) or 0.0
            if sup <= 0 and exh <= 0:
                continue
            rp = select_grilles_for_room(
                sup, exh, max_lwa=max_lwa, mount=mount, families=families,
                max_velocity=max_velocity, max_dp=max_dp,
                max_a_mm=max_a_mm, max_b_mm=max_b_mm,
            )
            if rp.supply is not None or rp.exhaust is not None:
                picks[sp.space_id] = rp
        self.grille_picks = picks
        self.emit("grilles_selected")
        return picks

    def design_underfloor_loops(
        self,
        *,
        pitch_mm: int = 150,
        cover: str = "tile",
        zone: str = "habitable",
        t_supply_c: float = 45.0,
        t_return_c: float = 35.0,
        coverage_ratio: float = 0.85,
    ) -> Dict[str, "UnderfloorLoop"]:
        """Расчёт контуров тёплого пола для всех помещений с heat_loss_w > 0.

        Сохраняет результат в self.underfloor_loops.
        """
        from hvac.underfloor import design_for_project_spaces
        result = design_for_project_spaces(
            self.spaces,
            pitch_mm=pitch_mm, cover=cover, zone=zone,
            t_supply_c=t_supply_c, t_return_c=t_return_c,
            coverage_ratio=coverage_ratio,
        )
        self.underfloor_loops = result
        self.emit("underfloor_designed")
        return result

    def select_fancoils_for_project(
        self,
        *,
        family_filter: Optional[List[str]] = None,
        pipes_filter: Optional[int] = None,
    ) -> Dict[str, "FancoilPick"]:
        """Подбор фанкойлов на каждое помещение с heat_gain_w > 0.

        Сохраняет в self.fancoil_picks.
        """
        from hvac.fancoil_catalog import select_fancoils_for_spaces
        result = select_fancoils_for_spaces(
            self.spaces,
            family_filter=family_filter, pipes_filter=pipes_filter,
        )
        self.fancoil_picks = result
        self.emit("fancoils_selected")
        return result

    def build_vrf_systems(
        self,
        *,
        indoor_family: Optional[str] = None,
        group_by: str = "level",
        main_pipe_length_m: float = 30.0,
        max_pipe_length_m: float = 60.0,
        max_height_m: float = 15.0,
    ) -> Dict[str, "VRFSystem"]:
        """Строит VRF-системы для проекта.

        group_by:
            "level"  — одна VRF-система на каждый уровень здания
            "all"    — одна общая система на все помещения

        Сохраняет в self.vrf_systems как {name: VRFSystem}.
        """
        from collections import defaultdict
        from hvac.vrf import build_vrf_system, check_constraints

        groups = defaultdict(list)
        if group_by == "level":
            for sp in self.spaces:
                if getattr(sp, "heat_gain_w", 0.0) > 0:
                    groups[sp.level or "L1"].append(sp)
        else:
            groups["all"] = [sp for sp in self.spaces
                              if getattr(sp, "heat_gain_w", 0.0) > 0]

        result: Dict[str, "VRFSystem"] = {}
        for key, spaces_group in groups.items():
            if not spaces_group:
                continue
            sys_name = f"VRV-{key}"
            sys = build_vrf_system(
                spaces_group, name=sys_name,
                indoor_family=indoor_family,
                main_pipe_length_m=main_pipe_length_m,
                max_pipe_length_m=max_pipe_length_m,
                max_height_m=max_height_m,
            )
            # Прикрепим результат проверки в note системы для UI
            check = check_constraints(sys)
            if not check.ok:
                # Сохраним как метаданные — не трогая dataclass
                sys._check_issues = check.issues   # type: ignore[attr-defined]
            result[sys_name] = sys
        self.vrf_systems = result
        self.emit("vrf_systems_built")
        return result

    def load_weather(self, path: str):
        """Загружает EPW-файл с реальным почасовым климатом.

        После загрузки simulate_annual_energy() использует реальные
        температуры вместо синтетического профиля. Файлы EPW —
        climate.onebuilding.org / energyplus.net/weather.

        Сохраняет в self.weather_data, возвращает WeatherData.
        """
        from hvac.weather import load_epw
        self.weather_data = load_epw(path)
        self.emit("weather_loaded")
        return self.weather_data

    def clear_weather(self) -> None:
        """Убирает загруженный EPW — симуляция вернётся к синтетике."""
        self.weather_data = None
        self.emit("weather_loaded")

    def simulate_annual_energy(
        self,
        *,
        keep_hourly: bool = True,
        thermal_mass_tau_h: float = 12.0,
        heating_setpoint_offset: float = 0.0,
        cooling_setpoint_offset: float = 0.0,
    ) -> "EnergySimulationResult":
        """Прогон 8760-часовой симуляции для всего проекта.

        Если загружен EPW (load_weather) — наружная температура берётся
        из него. Сохраняет результат в self.energy_simulation_result.
        """
        from hvac.energy_simulation import simulate_year
        result = simulate_year(
            self,
            keep_hourly=keep_hourly,
            thermal_mass_tau_h=thermal_mass_tau_h,
            heating_setpoint_offset=heating_setpoint_offset,
            cooling_setpoint_offset=cooling_setpoint_offset,
            weather=getattr(self, "weather_data", None),
        )
        self.energy_simulation_result = result
        self.emit("energy_simulated")
        return result

    def calculate_comfort(
        self,
        seasons=("heating", "cooling"),
        *,
        met: float = 1.2,
        clo=None,
        v_air_ms: float = 0.1,
        rh_override=None,
    ) -> Dict[str, Dict]:
        """Оценка теплового комфорта PMV/PPD по ISO 7730 (метод Фангера).

        Считает по расчётным уставкам помещений (t_in_heat / t_in_cool);
        влажность — rh_design помещения или пресет по типу.

        Параметры
        ---------
        seasons     : какие сезоны считать ("heating", "cooling").
        met         : метаболизм, met (1.2 — офисная работа).
        clo         : одежда, clo; None → 1.0 зимой / 0.5 летом.
        v_air_ms    : подвижность воздуха, м/с.
        rh_override : общая влажность % для всех помещений (иначе по типу).

        Сохраняет в self.comfort_results: {season: {space_id: ComfortResult}}.
        """
        from hvac import comfort
        result = {
            season: comfort.assess_project(
                self, season, met=met, clo=clo,
                v_air_ms=v_air_ms, rh_override=rh_override)
            for season in seasons
        }
        self.comfort_results = result
        self.emit("comfort_calculated")
        return result

    def build_equipment_specification(self) -> "Specification":
        """Формирует спецификацию по ГОСТ 21.110 по текущему составу проекта.

        Сохраняет в self.equipment_specification.
        """
        from hvac.specification import build_specification
        spec = build_specification(self)
        self.equipment_specification = spec
        self.emit("specification_built")
        return spec

    def analyze_acoustics_for_ahus(
        self,
        *,
        duct_length_m: float = 12.0,
        elbows_per_path: int = 3,
        room_volume_default_m3: float = 40.0,
        room_distance_m: float = 1.5,
    ) -> Dict[str, "AcousticAnalysis"]:
        """Подбор шумоглушителей для каждой AHU.

        Считает «типовой» путь от вентилятора до самой шумоухочуствительной
        зоны (наименьший норматив LpA среди обслуживаемых помещений).
        Для детального расчёта по веткам используйте select_silencer
        напрямую с явным duct_segments.
        """
        from hvac.acoustics import (
            fan_lw_estimate_beranek, required_noise_level, select_silencer,
        )
        from hvac.ahu_load import aggregate_ahus

        loads = aggregate_ahus(self)
        result: Dict[str, "AcousticAnalysis"] = {}
        for name, load in loads.items():
            # Самая «строгая» норма среди обслуживаемых помещений
            served = [sp for sp in self.spaces
                      if sp.system_ventilation == name and sp.area_m2 > 0]
            if served:
                norm = min(required_noise_level(sp.room_type) for sp in served)
                vol = sum(sp.volume_m3 for sp in served) / max(len(served), 1)
            else:
                norm = 50.0
                vol = room_volume_default_m3
            # Lw — оценка по Beranek через расход и Δp (по умолчанию 300 Па).
            # Если есть детальная сеть — взяли бы её Δp.
            lw = fan_lw_estimate_beranek(load.supply_m3_h, 350.0)
            analysis = select_silencer(
                fan_lw_dba=lw, room_norm_dba=norm,
                duct_segments=[(duct_length_m, 400, False)],
                elbows_90_count=elbows_per_path,
                room_volume_m3=vol,
                room_distance_m=room_distance_m,
            )
            result[name] = analysis
        self.acoustics_results = result
        self.emit("acoustics_analyzed")
        return result
