# -*- coding: utf-8 -*-
"""Расчёт воздушно-тепловых завес шиберующего типа.

Методика — СНиП 2.04.05-91* прил. 20 (наследована СП 60.13330,
КМК 2.04.05): завеса подбирается по расчётной разности давлений на
проёме (гравитационная составляющая + ветер), относительному расходу
q̄ = G_завесы/G_проёма и коэффициенту расхода проёма μ при работе
завесы.

    Δp   = g·h_р·(ρ_н − ρ_в) + 0,5·c_в·ρ_н·v²          [Па]
    G_з  = 5100·q̄·μ·F_пр·√(Δp·ρ_см)                    [кг/ч]
    t_з  = t_н + (t_см − t_н)/q̄          (баланс смеси у проёма)
    Q_з  = 0,28·G_з·(t_з − t_нач)·c                     [Вт]

где h_р — расстояние от центра проёма до нейтральной зоны (принято
половина высоты здания), t_см — нормируемая температура смеси у проёма
(СП 60.13330 п.7.7: 5 °C — произв. без постоянных рабочих мест,
12 °C — производственные при лёгкой работе, 14 °C — общественные и
административно-бытовые), t_нач — температура забираемого воздуха.

Табличные q̄ и μ зависят от конструкции завесы — заданы значениями
по умолчанию и редактируются (уточнять по данным изготовителя).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

G_ACCEL = 9.81
C_AIR_KJ = 1.005          # теплоёмкость воздуха, кДж/(кг·К)

# Нормируемая температура смеси у проёма, °C (СП 60.13330 п.7.7)
T_MIX_NORMS = {
    "public": 14.0,        # общественные, административно-бытовые
    "industrial_light": 12.0,   # производственные, лёгкая работа
    "industrial_none": 5.0,     # производственные без пост. раб. мест
}

# Максимальная температура подачи завесы, °C (СП 60.13330 п.7.7)
T_SUPPLY_MAX_DOOR = 50.0   # наружные двери
T_SUPPLY_MAX_GATE = 70.0   # ворота и технологические проёмы

# Рекомендуемая скорость выпуска, м/с (СП 60.13330 п.7.7)
V_SLOT_MAX_DOOR = 8.0
V_SLOT_MAX_GATE = 25.0


def air_density(t_c: float) -> float:
    """Плотность воздуха при атмосферном давлении, кг/м³."""
    return 353.0 / (273.15 + t_c)


@dataclass
class AirCurtainInput:
    """Исходные данные проёма с завесой."""
    name: str = ""
    is_gate: bool = False        # ворота (иначе — наружная дверь)
    width_m: float = 1.5         # ширина проёма
    height_m: float = 2.2        # высота проёма
    building_height_m: float = 9.0   # высота здания (до нейтральной зоны)
    t_outside_c: float = -15.0   # расчётная зимняя (параметры Б)
    t_inside_c: float = 18.0     # температура в помещении/вестибюле
    t_mix_c: float = 14.0        # нормируемая температура смеси у проёма
    wind_speed_ms: float = 3.0   # расчётная скорость ветра (январь)
    wind_c: float = 0.8          # аэродинамический коэффициент фасада
    q_ratio: float = 0.7         # q̄ = G_завесы / G_проёма
    mu_flow: float = 0.25        # μ — коэф. расхода проёма при завесе
    intake_inside: bool = True   # забор воздуха изнутри (иначе снаружи)
    slot_area_m2: float = 0.0    # площадь щелей выпуска (0 — не проверять)


@dataclass
class AirCurtainResult:
    """Результат подбора завесы."""
    opening_area_m2: float = 0.0
    dp_pa: float = 0.0           # расчётная разность давлений
    g_kg_h: float = 0.0          # массовый расход завесы
    l_m3_h: float = 0.0          # объёмный расход (при t подачи)
    t_supply_c: float = 0.0      # требуемая температура подачи
    q_heat_w: float = 0.0        # тепловая мощность калорифера
    v_slot_ms: float = 0.0       # скорость выпуска (если задана щель)
    warnings: List[str] = field(default_factory=list)


def calc_air_curtain(inp: AirCurtainInput) -> AirCurtainResult:
    """Подбор воздушно-тепловой завесы шиберующего типа."""
    if inp.width_m <= 0 or inp.height_m <= 0:
        raise ValueError("Размеры проёма должны быть положительными")
    if not 0.1 <= inp.q_ratio <= 1.0:
        raise ValueError("q̄ должен быть в диапазоне 0,1…1,0")
    if inp.mu_flow <= 0:
        raise ValueError("μ должен быть положительным")

    res = AirCurtainResult()
    res.opening_area_m2 = inp.width_m * inp.height_m

    rho_out = air_density(inp.t_outside_c)
    rho_in = air_density(inp.t_inside_c)
    rho_mix = air_density(inp.t_mix_c)

    # Центр проёма → нейтральная зона (половина высоты здания)
    h_calc = max(inp.building_height_m / 2.0 - inp.height_m / 2.0, 0.2)
    dp_gravity = G_ACCEL * h_calc * (rho_out - rho_in)
    dp_wind = 0.5 * inp.wind_c * rho_out * inp.wind_speed_ms ** 2
    res.dp_pa = max(dp_gravity + dp_wind, 1.0)

    # Расход завесы, кг/ч (5100 ≈ 3600·√2)
    res.g_kg_h = (5100.0 * inp.q_ratio * inp.mu_flow * res.opening_area_m2
                  * math.sqrt(res.dp_pa * rho_mix))

    # Температура подачи из баланса смеси: q̄·t_з + (1−q̄)·t_н = t_см
    t_supply = inp.t_outside_c + (inp.t_mix_c - inp.t_outside_c) / inp.q_ratio
    res.t_supply_c = t_supply

    t_max = T_SUPPLY_MAX_GATE if inp.is_gate else T_SUPPLY_MAX_DOOR
    if t_supply > t_max:
        res.warnings.append(
            f"t подачи {t_supply:.1f} °C выше допустимой {t_max:.0f} °C "
            f"(СП 60.13330 п.7.7) — увеличьте q̄ или расход")

    # Мощность калорифера: подогрев от t забора до t подачи
    t_intake = inp.t_inside_c if inp.intake_inside else inp.t_outside_c
    res.q_heat_w = max(
        0.0, 0.28 * res.g_kg_h * C_AIR_KJ * (t_supply - t_intake))

    # Объёмный расход при температуре подачи
    res.l_m3_h = res.g_kg_h / air_density(t_supply)

    # Скорость выпуска из щели
    if inp.slot_area_m2 > 0:
        res.v_slot_ms = res.l_m3_h / 3600.0 / inp.slot_area_m2
        v_max = V_SLOT_MAX_GATE if inp.is_gate else V_SLOT_MAX_DOOR
        if res.v_slot_ms > v_max:
            res.warnings.append(
                f"Скорость выпуска {res.v_slot_ms:.1f} м/с выше "
                f"рекомендуемой {v_max:.0f} м/с (СП 60.13330 п.7.7)")

    if inp.t_outside_c >= inp.t_inside_c:
        res.warnings.append(
            "t наружного воздуха не ниже внутренней — гравитационный "
            "перепад отсутствует, проверьте исходные данные")
    return res
