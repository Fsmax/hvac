# -*- coding: utf-8 -*-
"""Подбор пластинчатого теплообменника для ИТП.

Классический расчёт по среднелогарифмическому температурному напору
(LMTD, противоток):

    Δt_б = t1' − t2''      (вход грею­щей − выход нагреваемой)
    Δt_м = t1'' − t2'      (выход греющей − вход нагреваемой)
    LMTD = (Δt_б − Δt_м) / ln(Δt_б / Δt_м)
    F    = Q·(1 + запас) / (k · LMTD)

Коэффициент теплопередачи k для разборных пластинчатых ТО вода-вода
в рабочем диапазоне 3000…5500 Вт/(м²·К) — уточняется по подбору
изготовителя (Альфа-Лаваль, Ридан, Funke); запас поверхности 10…20%
на загрязнение (РД 34.20.501, практика проектирования ИТП).

Расходы сторон: G [м³/ч] = 0,86·Q [кВт] / Δt (при ρ≈1000 кг/м³,
c=4,187 кДж/(кг·К)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

# Типовые температурные графики ИТП: (t1', t1'', t2', t2'')
HX_PRESETS: dict[str, Tuple[float, float, float, float]] = {
    "heating_95_70": (95.0, 70.0, 60.0, 80.0),   # отопление 95/70 → 80/60
    "heating_80_60": (80.0, 60.0, 50.0, 70.0),   # отопление 80/60 → 70/50
    "dhw": (70.0, 30.0, 5.0, 60.0),              # ГВС 70/30 → 5/60
}


@dataclass
class PlateHXInput:
    """Исходные данные подбора пластинчатого ТО."""
    q_kw: float = 100.0          # тепловая нагрузка
    t_hot_in: float = 95.0       # греющая, вход
    t_hot_out: float = 70.0      # греющая, выход
    t_cold_in: float = 60.0      # нагреваемая, вход
    t_cold_out: float = 80.0     # нагреваемая, выход
    k_w_m2k: float = 4500.0      # коэффициент теплопередачи
    margin: float = 0.10         # запас поверхности на загрязнение


@dataclass
class PlateHXResult:
    """Результат подбора."""
    lmtd_k: float = 0.0
    area_m2: float = 0.0         # требуемая поверхность с запасом
    g_hot_m3h: float = 0.0       # расход греющей стороны
    g_cold_m3h: float = 0.0      # расход нагреваемой стороны
    warnings: List[str] = field(default_factory=list)


def calc_plate_hx(inp: PlateHXInput) -> PlateHXResult:
    """Подбор поверхности пластинчатого ТО по LMTD (противоток)."""
    if inp.q_kw <= 0:
        raise ValueError("Нагрузка должна быть положительной")
    if inp.t_hot_in <= inp.t_hot_out:
        raise ValueError("Греющая сторона: t входа должна быть выше t выхода")
    if inp.t_cold_out <= inp.t_cold_in:
        raise ValueError("Нагреваемая сторона: t выхода должна быть выше t входа")
    if inp.k_w_m2k <= 0:
        raise ValueError("k должен быть положительным")

    res = PlateHXResult()

    # Температурный крест: в противотоке выход нагреваемой может
    # превышать выход греющей, но не вход греющей.
    dt_big = inp.t_hot_in - inp.t_cold_out
    dt_small = inp.t_hot_out - inp.t_cold_in
    if dt_big <= 0 or dt_small <= 0:
        raise ValueError(
            "Температурный крест: график недостижим в одном ТО "
            f"(Δt концов {dt_big:.1f} / {dt_small:.1f} K)")

    if abs(dt_big - dt_small) < 1e-6:
        res.lmtd_k = dt_big
    else:
        res.lmtd_k = (dt_big - dt_small) / math.log(dt_big / dt_small)

    res.area_m2 = inp.q_kw * 1000.0 * (1.0 + inp.margin) / (
        inp.k_w_m2k * res.lmtd_k)

    res.g_hot_m3h = 0.86 * inp.q_kw / (inp.t_hot_in - inp.t_hot_out)
    res.g_cold_m3h = 0.86 * inp.q_kw / (inp.t_cold_out - inp.t_cold_in)

    if res.lmtd_k < 5.0:
        res.warnings.append(
            f"LMTD {res.lmtd_k:.1f} K мал — поверхность будет большой, "
            "проверьте температурный график")
    if not 2500.0 <= inp.k_w_m2k <= 6500.0:
        res.warnings.append(
            f"k = {inp.k_w_m2k:.0f} Вт/(м²·К) вне типового диапазона "
            "пластинчатых ТО вода-вода (3000…5500)")
    return res
