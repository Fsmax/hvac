# -*- coding: utf-8 -*-
"""Расчёт водяного тёплого пола.

Источники
---------
EN 1264 (Surface embedded heating and cooling systems with water)
СП 60.13330.2020 Прил. Г (тепловой поток греющих поверхностей)
КМК 2.04.05-22 раздел 4 (отопление жилых и общественных зданий)
Uponor / REHAU / Valtec / KAN Therm — методики проектирования

Удельный тепловой поток q [Вт/м²] зависит от:
    Δθ_H = (t_supply + t_return)/2 − t_room   — средний температурный
                                                  напор греющего пола
    шаг между трубами s, расстояние от верха трубы до поверхности пола,
    тип покрытия (плитка / ламинат / ковролин).

В качестве практической формулы используется:

    q = (B / Δθ_H_0) · (Δθ_H)^1   ·  K_step · K_cover · K_pipe

где B и Δθ_H_0 — расчётные константы EN 1264, K_* — поправки. На практике
для шага 15 см и плитки q ≈ 60-100 Вт/м² при Δθ_H = 15-25°C.

Допустимая температура поверхности пола (EN 1264-2 / СП 60):
    • Жилые помещения: 29°C
    • Ванные / краевые зоны: 35°C
    • Постоянно проходные: 27°C

Длина петли L_loop = площадь_контура / шаг_трубы (приближённо).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ============================================================================
# Каталог трубок
# ============================================================================

@dataclass
class UnderfloorPipe:
    """Трубка тёплого пола."""
    name: str
    inner_diameter_mm: float
    outer_diameter_mm: float
    wall_mm: float
    material: str = "PEX-AL-PEX"
    lambda_w_mk: float = 0.41          # PEX ~ 0.41, PE-RT ~ 0.45, AL-PEX ~ 0.45
    max_length_m: float = 120.0        # рекомендация производителя
    pressure_drop_per_m_pa: float = 250.0   # справочно при v=0.3 м/с


PIPE_CATALOG: List[UnderfloorPipe] = [
    UnderfloorPipe("PEX-AL-PEX 16x2.0", 12.0, 16.0, 2.0,
                    material="PEX-AL-PEX", lambda_w_mk=0.45,
                    max_length_m=100.0),
    UnderfloorPipe("PEX-AL-PEX 20x2.0", 16.0, 20.0, 2.0,
                    material="PEX-AL-PEX", lambda_w_mk=0.45,
                    max_length_m=120.0),
    UnderfloorPipe("PE-RT/AL/PE-RT 16x2.0", 12.0, 16.0, 2.0,
                    material="PE-RT", lambda_w_mk=0.45,
                    max_length_m=100.0),
    UnderfloorPipe("PE-Xa 17x2.0 (Rehau Rautherm)", 13.0, 17.0, 2.0,
                    material="PE-Xa", lambda_w_mk=0.41,
                    max_length_m=120.0),
    UnderfloorPipe("PE-Xa 20x2.0", 16.0, 20.0, 2.0,
                    material="PE-Xa", lambda_w_mk=0.41,
                    max_length_m=130.0),
]


# ============================================================================
# Поправочные коэффициенты
# ============================================================================

# Зависимость удельной теплоотдачи от шага укладки (для типового покрытия плитка).
# Базовый шаг = 150 мм, q_factor = 1.0.
PITCH_FACTOR: Dict[float, float] = {
    100: 1.22,
    150: 1.00,
    200: 0.84,
    250: 0.72,
    300: 0.62,
}

# Поправка по покрытию пола (тепловое сопротивление R_λ)
COVER_FACTOR = {
    "tile":     1.00,   # керамическая плитка
    "stone":    1.00,
    "laminate": 0.86,   # ламинат 8-10 мм
    "parquet":  0.78,   # массив 14 мм
    "carpet":   0.65,   # ковролин 8 мм
    "linoleum": 0.92,
}

COVER_LABELS = {
    "tile": "Керамическая плитка",
    "stone": "Камень / керамогранит",
    "laminate": "Ламинат",
    "parquet": "Паркет / массив",
    "carpet": "Ковролин",
    "linoleum": "Линолеум",
}

# Базовый удельный поток при Δθ_H = 15 K, шаг 150, плитка, трубка 16x2.0
# Уточнено по таблице EN 1264-2 (системы типа A, бетонная стяжка 60 мм)
BASE_Q_W_M2_AT_15K = 71.0


# Максимально допустимая температура поверхности пола, °C (EN 1264-2 / СП 60)
MAX_FLOOR_T_BY_ZONE = {
    "habitable": 29.0,   # жилые комнаты
    "edge":      35.0,   # краевые зоны и ванные (полоса 1 м у наружной стены)
    "bath":      33.0,   # обычная ванная
    "corridor":  27.0,
    "office":    28.0,
}


# ============================================================================
# Расчёт удельного теплового потока
# ============================================================================

def heat_flux_w_m2(
    dt_h: float,
    *,
    pitch_mm: int = 150,
    cover: str = "tile",
    pipe: Optional[UnderfloorPipe] = None,
) -> float:
    """Удельная теплоотдача греющего пола, Вт/м².

    Параметры
    ---------
    dt_h     : средний температурный напор Δθ_H = (t_s+t_r)/2 − t_room
    pitch_mm : шаг труб, мм
    cover    : тип покрытия (ключ из COVER_FACTOR)
    pipe     : трубка (влияет слабо через лямбду; для базового расчёта None)
    """
    if dt_h <= 0:
        return 0.0
    k_pitch = _interp(PITCH_FACTOR, float(pitch_mm))
    k_cover = COVER_FACTOR.get(cover, 1.0)
    k_pipe = 1.0
    if pipe is not None:
        # Большая внешняя поверхность трубы (20 мм vs 16 мм) даёт +5%
        if pipe.outer_diameter_mm >= 19.0:
            k_pipe = 1.05
    # Линейная аппроксимация по EN 1264-2 (для типового диапазона 5-30 K)
    return BASE_Q_W_M2_AT_15K * (dt_h / 15.0) * k_pitch * k_cover * k_pipe


def floor_surface_temperature_c(
    q_w_m2: float, t_room: float, alpha_floor_w_m2k: float = 10.8,
) -> float:
    """Температура поверхности пола из удельной теплоотдачи.

        T_пов = T_room + q / α

    α = 10.8 Вт/(м²·К) — суммарный коэффициент теплоотдачи
    верх + нижняя половина потерь, EN 1264.
    """
    if alpha_floor_w_m2k <= 0:
        return t_room
    return t_room + q_w_m2 / alpha_floor_w_m2k


def _interp(table: Dict[float, float], x: float) -> float:
    keys = sorted(table.keys())
    if x <= keys[0]:
        return table[keys[0]]
    if x >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        if keys[i] <= x <= keys[i + 1]:
            x0, x1 = keys[i], keys[i + 1]
            y0, y1 = table[x0], table[x1]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[keys[-1]]


# ============================================================================
# Контур тёплого пола
# ============================================================================

@dataclass
class UnderfloorLoop:
    """Один контур (петля) тёплого пола, обслуживающий часть помещения."""

    name: str
    room_id: str = ""
    area_m2: float = 0.0
    q_required_w: float = 0.0          # требуемая мощность контура

    # Параметры укладки
    pipe: Optional[UnderfloorPipe] = None
    pitch_mm: int = 150
    cover: str = "tile"
    zone: str = "habitable"            # для max T_floor

    # Температурный график
    t_supply_c: float = 45.0
    t_return_c: float = 35.0
    t_room_c: float = 20.0

    # Расчётные результаты
    q_actual_w_m2: float = 0.0
    q_actual_w: float = 0.0
    t_floor_surface_c: float = 0.0
    t_floor_limit_c: float = 0.0
    pipe_length_m: float = 0.0
    flow_kg_h: float = 0.0
    pressure_drop_kpa: float = 0.0
    warnings: List[str] = field(default_factory=list)


def design_loop(loop: UnderfloorLoop) -> UnderfloorLoop:
    """Расчёт контура: q факт., длина трубы, расход и Δp.

    Логика:
      1. Δθ_H = (t_s+t_r)/2 − t_room
      2. q = heat_flux_w_m2(Δθ_H, pitch, cover, pipe)
      3. Q_контура = q · площадь
      4. T_поверхности = t_room + q / α; сверяем с лимитом
      5. Длина трубы L = площадь / (pitch/1000)
      6. Расход G = Q · 3.6 / (c · Δt), где Δt = t_s − t_r
      7. Δp = pressure_drop_per_m · L
    """
    pipe = loop.pipe or PIPE_CATALOG[0]
    loop.pipe = pipe
    dt_h = (loop.t_supply_c + loop.t_return_c) / 2.0 - loop.t_room_c
    if dt_h <= 0:
        loop.warnings.append(
            f"Δθ_H ≤ 0 ({dt_h:.1f} K): подача недостаточно горячая")
        return loop

    q = heat_flux_w_m2(dt_h, pitch_mm=loop.pitch_mm,
                          cover=loop.cover, pipe=pipe)
    loop.q_actual_w_m2 = q
    loop.q_actual_w = q * loop.area_m2

    # Температура поверхности
    loop.t_floor_surface_c = floor_surface_temperature_c(q, loop.t_room_c)
    loop.t_floor_limit_c = MAX_FLOOR_T_BY_ZONE.get(loop.zone, 29.0)
    if loop.t_floor_surface_c > loop.t_floor_limit_c:
        loop.warnings.append(
            f"T поверхности {loop.t_floor_surface_c:.1f}°C превышает лимит "
            f"{loop.t_floor_limit_c:.1f}°C — увеличьте шаг, понизьте t_подачи "
            f"или измените покрытие")

    # Длина трубы. При прямом змеевике L ≈ A / шаг + 2·(длинная сторона + подвод).
    # Для оценки берём упрощённое: L = A / (pitch_mm/1000).
    pitch_m = loop.pitch_mm / 1000.0
    loop.pipe_length_m = loop.area_m2 / max(pitch_m, 0.05)
    if loop.pipe_length_m > pipe.max_length_m:
        # Разбить на несколько петель
        n_loops = math.ceil(loop.pipe_length_m / pipe.max_length_m)
        loop.warnings.append(
            f"Длина {loop.pipe_length_m:.0f} м > предела {pipe.max_length_m:.0f} м — "
            f"разделите на {n_loops} петель")

    # Расход и Δp
    dt = loop.t_supply_c - loop.t_return_c
    if dt > 0:
        # G [кг/ч] = Q [Вт] · 3.6 / (c [кДж/кг·К] · Δt [K])
        loop.flow_kg_h = loop.q_actual_w * 3.6 / (4.186 * dt)
    loop.pressure_drop_kpa = (
        pipe.pressure_drop_per_m_pa * loop.pipe_length_m / 1000.0)

    return loop


# ============================================================================
# Подбор для всего помещения
# ============================================================================

def design_for_space(
    space,
    *,
    pitch_mm: int = 150,
    cover: str = "tile",
    zone: str = "habitable",
    t_supply_c: float = 45.0,
    t_return_c: float = 35.0,
    pipe: Optional[UnderfloorPipe] = None,
    coverage_ratio: float = 0.85,
) -> UnderfloorLoop:
    """Создаёт и рассчитывает контур ТП для одного Space.

    coverage_ratio — доля площади, занятая тёплым полом (учитываем мебель,
    шкафы и пр.). 0.85 — типично для жилых, 0.95 — для офисов.
    """
    q_required = getattr(space, "heat_loss_w", 0.0)
    area = getattr(space, "area_m2", 0.0) * coverage_ratio
    loop = UnderfloorLoop(
        name=f"ТП-{getattr(space, 'number', '?')}",
        room_id=getattr(space, "space_id", ""),
        area_m2=area,
        q_required_w=q_required,
        pipe=pipe,
        pitch_mm=pitch_mm,
        cover=cover,
        zone=zone,
        t_supply_c=t_supply_c,
        t_return_c=t_return_c,
        t_room_c=getattr(space, "t_in_heat", 20.0),
    )
    return design_loop(loop)


def design_for_project_spaces(
    spaces, **kwargs,
) -> Dict[str, UnderfloorLoop]:
    """Расчёт ТП для всех помещений с указанной нагрузкой."""
    result: Dict[str, UnderfloorLoop] = {}
    for sp in spaces:
        if getattr(sp, "heat_loss_w", 0.0) <= 0:
            continue
        if getattr(sp, "area_m2", 0.0) <= 0:
            continue
        loop = design_for_space(sp, **kwargs)
        result[sp.space_id] = loop
    return result
