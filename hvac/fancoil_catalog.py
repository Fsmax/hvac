# -*- coding: utf-8 -*-
"""Каталог фанкойлов и подбор под нагрузку.

Источники: каталоги Carrier 42N/42GW, Daikin FWC/FWQ, Mitsubishi PCFY,
Lessar, Systemair Topvex FC. Производительности приведены к стандартным
условиям EN 1397:

    Холод:  T_air_in = 27°C DB / 19°C WB, T_water = 7/12 °C
    Тепло:  T_air_in = 20°C, T_water = 70/60 °C (или 60/40 для 4-тр.)

Базовый расчёт пересчёта на фактические условия — линейный по разнице
температур (EN 1397 § 6):

    Q_actual = Q_nominal · (ΔT_actual / ΔT_nominal)

Это упрощение работает в пределах ±20% от номинала; для точного подбора
использовать программы производителей.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FancoilModel:
    """Запись каталога фанкойла."""
    name: str
    family: str = ""                   # «Кассетный», «Канальный», «Настенный»
    pipes: int = 4                     # 2 или 4 трубы

    # Производительность по EN 1397 (на средней скорости вентилятора)
    q_cool_nom_w: float = 0.0          # полная холодопроизводительность
    q_cool_sens_nom_w: float = 0.0     # явная часть холода
    q_heat_nom_w: float = 0.0          # теплопроизводительность

    # Расходы воздуха и воды
    air_flow_m3_h: float = 0.0         # на средней скорости
    air_flow_min_m3_h: float = 0.0
    air_flow_max_m3_h: float = 0.0
    water_flow_cool_l_h: float = 0.0   # при ΔT=5K по воде
    water_flow_heat_l_h: float = 0.0   # при ΔT=10K по воде

    # Электрика и шум
    fan_power_w: float = 0.0
    noise_db_a: float = 0.0            # ср. скорость, 3 м от агрегата

    # Габариты, мм
    width_mm: int = 0
    depth_mm: int = 0
    height_mm: int = 0

    # Расчётные условия (для пересчёта)
    cool_dt_nominal: float = 20.0      # T_air − T_water_avg = 27 − 9.5 ≈ 17.5
    heat_dt_nominal: float = 45.0      # 20 − 65 = -45 (модуль)

    note: str = ""


def correct_cool(q_nom: float, dt_actual: float,
                  dt_nominal: float = 20.0) -> float:
    """Линейная коррекция холодопроизводительности по ΔT."""
    if dt_nominal <= 0 or dt_actual <= 0:
        return 0.0
    return q_nom * (dt_actual / dt_nominal)


def correct_heat(q_nom: float, dt_actual: float,
                  dt_nominal: float = 45.0) -> float:
    """Линейная коррекция теплопроизводительности."""
    if dt_nominal <= 0 or dt_actual <= 0:
        return 0.0
    return q_nom * (dt_actual / dt_nominal)


# ============================================================================
# Каталог — типовые модели Carrier 42N / Daikin FWC / Mitsubishi PCFY
# ============================================================================

FANCOIL_CATALOG: List[FancoilModel] = [
    # ===== Кассетные 4-трубные =====
    FancoilModel("Carrier 42GWC020", "Кассетный 600×600", pipes=4,
                  q_cool_nom_w=2300, q_cool_sens_nom_w=1750,
                  q_heat_nom_w=3300,
                  air_flow_m3_h=350, air_flow_min_m3_h=270,
                  air_flow_max_m3_h=480,
                  water_flow_cool_l_h=395, water_flow_heat_l_h=285,
                  fan_power_w=42, noise_db_a=34,
                  width_mm=575, depth_mm=575, height_mm=265),
    FancoilModel("Carrier 42GWC030", "Кассетный 600×600", pipes=4,
                  q_cool_nom_w=3500, q_cool_sens_nom_w=2650,
                  q_heat_nom_w=4900,
                  air_flow_m3_h=520, air_flow_min_m3_h=400,
                  air_flow_max_m3_h=720,
                  water_flow_cool_l_h=600, water_flow_heat_l_h=420,
                  fan_power_w=58, noise_db_a=38,
                  width_mm=575, depth_mm=575, height_mm=265),
    FancoilModel("Carrier 42GWC045", "Кассетный 600×600", pipes=4,
                  q_cool_nom_w=4900, q_cool_sens_nom_w=3700,
                  q_heat_nom_w=7200,
                  air_flow_m3_h=720, air_flow_min_m3_h=550,
                  air_flow_max_m3_h=1000,
                  water_flow_cool_l_h=840, water_flow_heat_l_h=620,
                  fan_power_w=78, noise_db_a=42,
                  width_mm=575, depth_mm=575, height_mm=265),
    FancoilModel("Daikin FWF02BT", "Кассетный 600×600 (Roundflow)", pipes=4,
                  q_cool_nom_w=2200, q_cool_sens_nom_w=1670,
                  q_heat_nom_w=3000,
                  air_flow_m3_h=360, air_flow_min_m3_h=270,
                  air_flow_max_m3_h=480,
                  water_flow_cool_l_h=378, water_flow_heat_l_h=258,
                  fan_power_w=40, noise_db_a=32,
                  width_mm=840, depth_mm=840, height_mm=246),
    FancoilModel("Daikin FWF05BT", "Кассетный 600×600 (Roundflow)", pipes=4,
                  q_cool_nom_w=5300, q_cool_sens_nom_w=4000,
                  q_heat_nom_w=7000,
                  air_flow_m3_h=780, air_flow_min_m3_h=600,
                  air_flow_max_m3_h=1020,
                  water_flow_cool_l_h=910, water_flow_heat_l_h=600,
                  fan_power_w=86, noise_db_a=42,
                  width_mm=840, depth_mm=840, height_mm=246),

    # ===== Канальные (низкий статический напор) =====
    FancoilModel("Carrier 42NM20", "Канальный низконапорный", pipes=4,
                  q_cool_nom_w=2100, q_cool_sens_nom_w=1600,
                  q_heat_nom_w=3000,
                  air_flow_m3_h=360, air_flow_min_m3_h=280,
                  air_flow_max_m3_h=470,
                  water_flow_cool_l_h=360, water_flow_heat_l_h=260,
                  fan_power_w=45, noise_db_a=32,
                  width_mm=750, depth_mm=480, height_mm=235),
    FancoilModel("Carrier 42NM40", "Канальный низконапорный", pipes=4,
                  q_cool_nom_w=4200, q_cool_sens_nom_w=3200,
                  q_heat_nom_w=6000,
                  air_flow_m3_h=720, air_flow_min_m3_h=560,
                  air_flow_max_m3_h=950,
                  water_flow_cool_l_h=720, water_flow_heat_l_h=520,
                  fan_power_w=85, noise_db_a=40,
                  width_mm=900, depth_mm=480, height_mm=235),
    FancoilModel("Carrier 42NM80", "Канальный среднего напора", pipes=4,
                  q_cool_nom_w=8500, q_cool_sens_nom_w=6500,
                  q_heat_nom_w=12000,
                  air_flow_m3_h=1400, air_flow_min_m3_h=1100,
                  air_flow_max_m3_h=1850,
                  water_flow_cool_l_h=1460, water_flow_heat_l_h=1030,
                  fan_power_w=180, noise_db_a=48,
                  width_mm=1300, depth_mm=580, height_mm=300),

    # ===== Настенные =====
    FancoilModel("Lessar LSF-30HE22", "Настенный", pipes=2,
                  q_cool_nom_w=3050, q_cool_sens_nom_w=2300,
                  q_heat_nom_w=4500,
                  air_flow_m3_h=520, air_flow_min_m3_h=400,
                  air_flow_max_m3_h=680,
                  water_flow_cool_l_h=525, water_flow_heat_l_h=390,
                  fan_power_w=42, noise_db_a=39,
                  width_mm=900, depth_mm=192, height_mm=290),
    FancoilModel("Lessar LSF-50HE22", "Настенный", pipes=2,
                  q_cool_nom_w=5200, q_cool_sens_nom_w=3950,
                  q_heat_nom_w=7400,
                  air_flow_m3_h=820, air_flow_min_m3_h=600,
                  air_flow_max_m3_h=1100,
                  water_flow_cool_l_h=895, water_flow_heat_l_h=640,
                  fan_power_w=78, noise_db_a=45,
                  width_mm=1100, depth_mm=210, height_mm=320),

    # ===== Напольно-потолочные =====
    FancoilModel("Carrier 42N016", "Напольно-потолочный", pipes=4,
                  q_cool_nom_w=1850, q_cool_sens_nom_w=1400,
                  q_heat_nom_w=2700,
                  air_flow_m3_h=320, air_flow_min_m3_h=250,
                  air_flow_max_m3_h=420,
                  water_flow_cool_l_h=320, water_flow_heat_l_h=230,
                  fan_power_w=38, noise_db_a=34,
                  width_mm=940, depth_mm=565, height_mm=225),
    FancoilModel("Carrier 42N025", "Напольно-потолочный", pipes=4,
                  q_cool_nom_w=2900, q_cool_sens_nom_w=2200,
                  q_heat_nom_w=4200,
                  air_flow_m3_h=480, air_flow_min_m3_h=380,
                  air_flow_max_m3_h=640,
                  water_flow_cool_l_h=500, water_flow_heat_l_h=360,
                  fan_power_w=58, noise_db_a=38,
                  width_mm=940, depth_mm=565, height_mm=225),
    FancoilModel("Carrier 42N055", "Напольно-потолочный", pipes=4,
                  q_cool_nom_w=5800, q_cool_sens_nom_w=4400,
                  q_heat_nom_w=8500,
                  air_flow_m3_h=1000, air_flow_min_m3_h=780,
                  air_flow_max_m3_h=1340,
                  water_flow_cool_l_h=1000, water_flow_heat_l_h=730,
                  fan_power_w=110, noise_db_a=44,
                  width_mm=1280, depth_mm=565, height_mm=225),
]


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class FancoilPick:
    model: FancoilModel
    actual_cool_w: float = 0.0
    actual_heat_w: float = 0.0
    cool_margin_pct: float = 0.0
    heat_margin_pct: float = 0.0
    note: str = ""


def select_fancoil(
    required_cool_w: float,
    required_heat_w: float = 0.0,
    *,
    t_air_db: float = 27.0,
    t_water_cool_supply: float = 7.0,
    t_water_cool_return: float = 12.0,
    t_water_heat_supply: float = 60.0,
    t_water_heat_return: float = 40.0,
    t_air_heat: float = 20.0,
    family_filter: Optional[List[str]] = None,
    pipes_filter: Optional[int] = None,
    catalog: Optional[List[FancoilModel]] = None,
    min_margin: float = 0.0,
    max_margin: float = 0.50,
) -> Optional[FancoilPick]:
    """Подбор фанкойла под холодильную (и опц. тепловую) нагрузку.

    Линейный пересчёт от номинала. В фильтре приоритет по семейству.

    Возвращает FancoilPick или None если ничего не подошло.
    """
    cat = catalog if catalog is not None else FANCOIL_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]
    if pipes_filter is not None:
        cat = [m for m in cat if m.pipes == pipes_filter]
    if not cat:
        return None

    # Расчётные ΔT
    t_water_cool_avg = 0.5 * (t_water_cool_supply + t_water_cool_return)
    dt_cool_actual = t_air_db - t_water_cool_avg
    t_water_heat_avg = 0.5 * (t_water_heat_supply + t_water_heat_return)
    dt_heat_actual = t_water_heat_avg - t_air_heat

    picks: List[FancoilPick] = []
    for m in cat:
        q_cool = correct_cool(m.q_cool_nom_w, dt_cool_actual,
                                 m.cool_dt_nominal)
        q_heat = correct_heat(m.q_heat_nom_w, dt_heat_actual,
                                 m.heat_dt_nominal) if required_heat_w > 0 else 0
        if q_cool < required_cool_w * (1.0 + min_margin):
            continue
        if required_heat_w > 0 and q_heat < required_heat_w * (1.0 + min_margin):
            continue
        cool_margin = (q_cool - required_cool_w) / required_cool_w
        heat_margin = ((q_heat - required_heat_w) / required_heat_w
                        if required_heat_w > 0 else 0.0)
        if cool_margin > max_margin:
            continue
        picks.append(FancoilPick(
            model=m, actual_cool_w=q_cool, actual_heat_w=q_heat,
            cool_margin_pct=cool_margin * 100.0,
            heat_margin_pct=heat_margin * 100.0,
        ))

    if not picks:
        return None
    # Минимальный запас — лучший вариант
    picks.sort(key=lambda p: p.cool_margin_pct)
    return picks[0]


def select_fancoils_for_spaces(
    spaces,
    *,
    family_filter: Optional[List[str]] = None,
    pipes_filter: Optional[int] = None,
    **kwargs,
) -> Dict[str, FancoilPick]:
    """Подбор фанкойлов на все помещения с heat_gain_w > 0."""
    result: Dict[str, FancoilPick] = {}
    for sp in spaces:
        q_cool = getattr(sp, "heat_gain_w", 0.0)
        if q_cool <= 0:
            continue
        q_heat = getattr(sp, "heat_loss_w", 0.0) or 0.0
        pick = select_fancoil(
            required_cool_w=q_cool,
            required_heat_w=q_heat,
            t_air_db=getattr(sp, "t_in_cool", 24.0) + 3.0,
            t_air_heat=getattr(sp, "t_in_heat", 20.0),
            family_filter=family_filter,
            pipes_filter=pipes_filter,
            **kwargs,
        )
        if pick is not None:
            result[sp.space_id] = pick
    return result
