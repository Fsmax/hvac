# -*- coding: utf-8 -*-
"""Нормативный удельный расход тепла q_ov по ШНҚ 2.01.18-24 (Узбекистан).

Таблицы 1–3 ШНҚ задают q_ov [Вт/м²] — нормативный удельный расход тепла
на отопление и вентиляцию — в зависимости от типа здания, этажности и
градус-суток отопительного периода Dd (полосы ≤2000 / 2000–3000 / >3000).

Данные вынесены в `data/shnq_energy.json`. Здесь — загрузка и выбор
значения с интерполяцией по этажности.

Использование:
    from hvac.catalogs.shnq_energy import normative_q_ov_shnq, building_type_to_shnq
    cat = building_type_to_shnq("гостиница")          # -> "hotel"
    q = normative_q_ov_shnq(cat, n_floors=3, dd=2100)  # Вт/м²
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Dict, List, Optional


def _load() -> dict:
    raw = (files("hvac.catalogs") / "data" / "shnq_energy.json").read_text("utf-8")
    return json.loads(raw)


SHNQ_ENERGY = _load()
_BOUNDS = SHNQ_ENERGY["dd_band_bounds"]           # [2000, 3000]
_CATEGORIES: Dict[str, dict] = SHNQ_ENERGY["categories"]


# Сопоставление building_type инструмента (detect_building_type) → категория ШНҚ.
_BUILDING_TYPE_MAP = {
    "гостиница":           "hotel",
    "офис":                "office",
    "магазин":             "shop",
    "школа":               "school",
    "жилое 1-3 этажа":     "residential",
    "жилое 4-5 этажей":    "residential",
    "жилое 6-9 этажей":    "residential",
    "жилое 10-12":         "residential",
    "жилое 12+":           "residential",
    "общественное":        "office",   # обобщённый общественный — берём офис
}


def building_type_to_shnq(building_type: str) -> str:
    """Категория ШНҚ по building_type инструмента (по умолчанию 'office')."""
    return _BUILDING_TYPE_MAP.get(building_type, "office")


def dd_band_index(dd: float) -> int:
    """Индекс полосы градус-суток: 0 (≤2000), 1 (2000–3000), 2 (>3000)."""
    if dd <= _BOUNDS[0]:
        return 0
    if dd <= _BOUNDS[1]:
        return 1
    return 2


def normative_q_ov_shnq(category: str, n_floors: int,
                        dd: float) -> Optional[float]:
    """Нормативный q_ov [Вт/м²] по ШНҚ Табл.1–3.

    Выбирает строку по этажности (ближайшая зашитая этажность ≤ n_floors,
    либо минимальная, если n_floors меньше всех) и полосу по Dd.
    Возвращает None, если категория неизвестна.
    """
    cat = _CATEGORIES.get(category)
    if not cat:
        return None
    by_floors: Dict[str, list] = cat["by_floors"]
    floors_avail = sorted(int(k) for k in by_floors)
    n = max(1, int(n_floors or 1))
    # ближайшая зашитая этажность ≤ n; если n меньше минимума — минимальная
    chosen = floors_avail[0]
    for f in floors_avail:
        if f <= n:
            chosen = f
        else:
            break
    row = by_floors[str(chosen)]
    return float(row[dd_band_index(dd)])


def shnq_category_title(code: str) -> str:
    """Человекочитаемое имя категории ШНҚ (для отчётов). Код, если неизвестна."""
    cat = _CATEGORIES.get(code)
    return cat.get("title", code) if cat else code


def list_shnq_categories() -> List[Dict[str, str]]:
    """Список категорий ШНҚ для UI: [{code, title, table}]."""
    return [
        {"code": code, "title": data.get("title", code),
         "table": data.get("table", "")}
        for code, data in _CATEGORIES.items()
    ]
