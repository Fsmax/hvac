# -*- coding: utf-8 -*-
"""Подсказки типовых размеров оборудования по нагрузке/расходу.

Чистые функции без зависимости от HVACProject — выбирают ближайший
больший стандартный размер из ряда.
"""

from __future__ import annotations

import math
from typing import List, Tuple


# Стандартные ряды единичной мощности (кВт) — для подбора КОЛИЧЕСТВА
# агрегатов источника. Те же ряды, что в suggest_boiler_size/chiller_size.
BOILER_KW_LADDER = [25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000]
CHILLER_KW_LADDER = [30, 50, 100, 150, 200, 300, 500, 750, 1000, 1500]


def pick_units(required_kw: float, ladder: List[int]) -> Tuple[float, int]:
    """Подбирает (единичная_мощность_кВт, количество) под требуемую мощность.

    Один агрегат ближайшего большего типоразмера, пока хватает ряда; если
    нагрузка превышает крупнейший типоразмер — каскад из N одинаковых
    крупнейших агрегатов (округление вверх).
    """
    if required_kw <= 0 or not ladder:
        return (0.0, 0)
    for size in ladder:
        if required_kw <= size:
            return (float(size), 1)
    largest = float(ladder[-1])
    return (largest, max(1, math.ceil(required_kw / largest)))


def suggest_ahu_size(airflow_m3h: float) -> str:
    """Подсказывает ближайший типовой размер AHU/вентилятора по расходу.
    Возвращает строку вроде '25 000' или '50 000+'."""
    if airflow_m3h <= 0:
        return "—"
    # Типовые размеры приточных установок (Systemair / VTS / Daikin / VEZA), м³/ч.
    standard_sizes = [500, 1000, 1500, 2000, 3000, 5000, 7500, 10000,
                      12500, 15000, 20000, 25000, 30000, 40000, 50000]
    for s in standard_sizes:
        if airflow_m3h <= s:
            return f"{s:,}".replace(",", " ")
    return f"{int(round(airflow_m3h / 10000) * 10000):,}+".replace(",", " ")


def suggest_boiler_size(q_w: float) -> str:
    """Типовая мощность котла по нагрузке."""
    if q_w <= 0:
        return "—"
    standard_kw = [25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000]
    q_kw = q_w / 1000
    for s in standard_kw:
        if q_kw <= s:
            return f"{s} кВт"
    return f"{int(round(q_kw / 500) * 500)}+ кВт"


def suggest_chiller_size(q_w: float) -> str:
    """Типовая мощность чиллера по нагрузке."""
    if q_w <= 0:
        return "—"
    standard_kw = [30, 50, 100, 150, 200, 300, 500, 750, 1000, 1500]
    q_kw = q_w / 1000
    for s in standard_kw:
        if q_kw <= s:
            return f"{s} кВт"
    return f"{int(round(q_kw / 500) * 500)}+ кВт"
