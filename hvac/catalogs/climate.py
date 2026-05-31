# -*- coding: utf-8 -*-
"""
Климатическая база данных СП 131.13330 (РФ/СНГ).

Данные вынесены во внешний редактируемый файл
``hvac/catalogs/data/climate.json`` и загружаются при импорте модуля.

Каждая запись:
    name : { country, t_heat_092, t_heat_098, t_cool_095, daily_amp,
             solar_vert, gsop_18 }
где:
    t_heat_092 — расчётная зимняя температура (обеспеч. 0,92), °C
    t_heat_098 — расчётная зимняя (обеспеч. 0,98) — для категории А, °C
    t_cool_095 — расчётная летняя (обеспеч. 0,95), °C
    daily_amp  — суточная амплитуда летом, K
    solar_vert — пиковая солнечная радиация на вертикальную поверхность, Вт/м²
    gsop_18    — градусо-сутки отопительного периода (база +18°C)

Опциональные поля периода со среднесуточной t ≤ 10 °C (КМК 2.01.01-94),
нужны для ТОЧНОГО расчёта Dd по КМК 2.01.04-18 форм.(1) и нормативов ШНҚ:
    z_ht_10    — продолжительность периода ≤10°C, сут
    t_ht_10    — средняя температура периода ≤10°C, °C
Если их нет — Dd считается приближённо из gsop_18 (см. hvac/energy.py).
"""

import json
from importlib.resources import files
from typing import Dict, TypedDict

try:                                  # Python 3.11+
    from typing import NotRequired
except ImportError:                   # pragma: no cover
    from typing_extensions import NotRequired


class ClimateEntry(TypedDict):
    """Схема одной климатической записи (поля описаны выше)."""
    country: str
    t_heat_092: float
    t_heat_098: float
    t_cool_095: float
    daily_amp: float
    solar_vert: float
    gsop_18: float
    z_ht_10: NotRequired[float]   # длительность периода ≤10°C, сут (КМК 2.01.01-94)
    t_ht_10: NotRequired[float]   # ср. температура периода ≤10°C, °C


def _load_climate_db() -> Dict[str, ClimateEntry]:
    """Читает базу климата из hvac/catalogs/data/climate.json.

    Через importlib.resources — работает и при запуске из исходников,
    и в собранном PyInstaller-приложении (файл объявлен в datas).
    """
    raw = (files("hvac.catalogs") / "data" / "climate.json").read_text("utf-8")
    return json.loads(raw)


CLIMATE_DB: Dict[str, ClimateEntry] = _load_climate_db()
