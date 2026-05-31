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
"""

import json
from importlib.resources import files
from typing import Dict, TypedDict


class ClimateEntry(TypedDict):
    """Схема одной климатической записи (поля описаны выше)."""
    country: str
    t_heat_092: float
    t_heat_098: float
    t_cool_095: float
    daily_amp: float
    solar_vert: float
    gsop_18: float


def _load_climate_db() -> Dict[str, ClimateEntry]:
    """Читает базу климата из hvac/catalogs/data/climate.json.

    Через importlib.resources — работает и при запуске из исходников,
    и в собранном PyInstaller-приложении (файл объявлен в datas).
    """
    raw = (files("hvac.catalogs") / "data" / "climate.json").read_text("utf-8")
    return json.loads(raw)


CLIMATE_DB: Dict[str, ClimateEntry] = _load_climate_db()
