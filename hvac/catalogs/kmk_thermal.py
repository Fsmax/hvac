# -*- coding: utf-8 -*-
"""Нормируемое сопротивление теплопередаче R₀^тр по КМК 2.01.04-18 Табл.2а/2б/2в.

КМК задаёт R₀^тр СТУПЕНЧАТО (не линейно, в отличие от СП 50 Табл.3): по
полосам градус-суток Dd (≤2000 / 2000–3000 / >3000), для 4 категорий зданий,
5 типов конструкций (стены / покрытие / пол / окна / фонари) и 3 уровней
теплозащиты (2а — обязательный минимум, 2б, 2в).

Данные — в `data/kmk_thermal.json`. ⚠ Числа извлечены OCR + визуальной сверкой
со сканом нормы; перед проектным применением требуется сверка с эталоном
(см. `_warning`/`_verify` в JSON).

Использование:
    from hvac.catalogs.kmk_thermal import r_norm_kmk, kmk_category_for
    cat = kmk_category_for("жилое 4-5 этажей", n_floors=5)   # -> "res_high"
    R = r_norm_kmk("Стены", dd=2100, kmk_category=cat, level=1)  # (м²·°С)/Вт
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Dict, List


def _load() -> dict:
    raw = (files("hvac.catalogs") / "data" / "kmk_thermal.json").read_text("utf-8")
    return json.loads(raw)


KMK_THERMAL = _load()
_BOUNDS: List[float] = KMK_THERMAL["dd_band_bounds"]      # [2000, 3000]
_ELEMENTS: List[str] = KMK_THERMAL["_elements"]            # порядок колонок
_LEVELS: Dict[str, dict] = KMK_THERMAL["levels"]


# Категория конструкции инструмента → индекс колонки в строке полосы Dd.
# "Двери" в КМК Табл.2 не нормируются напрямую → None (вернём 0).
_ELEMENT_COLUMN = {
    "Стены":    0,   # wall
    "Покрытие": 1,   # roof (×n)
    "Пол":      2,   # floor (×n)
    "Окна":     3,   # window
    "Витраж":   3,   # window (дераза ва балкон эшиклар — ближайшее)
    "Фонари":   4,   # lantern
    "Двери":    None,
}

# Колонки, значение которых по таблице умножается на коэффициент n (Табл.3).
_N_SCALED_COLUMNS = {1, 2}   # roof, floor


def dd_band_index(dd: float) -> int:
    """Индекс полосы градус-суток: 0 (≤2000), 1 (2000–3000), 2 (>3000)."""
    if dd <= _BOUNDS[0]:
        return 0
    if dd <= _BOUNDS[1]:
        return 1
    return 2


def kmk_category_for(building_type: str, n_floors: int = 4) -> str:
    """Категория КМК Табл.2 по типу/этажности здания.

    res_low  — жилые ≤3 эт., лечебно-профилактич., детские, учебные, интернаты
    res_high — жилые >3 эт. и лечебно-профилактич.
    public   — общественные (кроме указанных), административные, бытовые
    industrial — производственные

    Принимает как обобщённые ("residential"/"public"/"industrial"), так и
    детальные ("жилое 4-5 этажей", "офис", ...) обозначения building_type.
    """
    bt = (building_type or "").lower()
    n = max(1, int(n_floors or 1))
    if "жил" in bt or "residential" in bt or "интернат" in bt:
        return "res_low" if n <= 3 else "res_high"
    if ("произв" in bt or "industrial" in bt or "цех" in bt
            or "склад" in bt or "промыш" in bt):
        return "industrial"
    return "public"


def r_norm_kmk(category: str, dd: float, kmk_category: str = "public",
               level: int = 1, n: float = 1.0) -> float:
    """R₀^тр [(м²·°С)/Вт] по КМК Табл.2а/2б/2в.

    Параметры
    ---------
    category : категория конструкции инструмента ("Стены"/"Покрытие"/"Пол"/
               "Окна"/"Витраж"/"Фонари"/"Двери")
    dd       : градус-сутки отопительного периода (порог сезона 10 °C, форм.1)
    kmk_category : категория здания КМК (см. kmk_category_for): res_low /
               res_high / public / industrial
    level    : уровень теплозащиты 1 (2а), 2 (2б), 3 (2в)
    n        : коэф. КМК Табл.3 для покрытий/полов (1.0 — прямой контакт с
               наружным воздухом; <1 — над неотапливаемыми объёмами).
               Применяется только к колонкам roof/floor.

    Возвращает R₀^тр, (м²·°С)/Вт. Для неизвестной категории/двери — 0.0.
    """
    col = _ELEMENT_COLUMN.get(category)
    if col is None:
        return 0.0
    lvl = _LEVELS.get(str(level)) or _LEVELS["1"]
    rows = lvl["categories"].get(kmk_category)
    if not rows:
        return 0.0
    value = float(rows[dd_band_index(dd)][col])
    if col in _N_SCALED_COLUMNS:
        value *= n
    return value


def list_kmk_levels() -> List[Dict[str, str]]:
    """Список уровней теплозащиты для UI: [{level, title, table}]."""
    return [
        {"level": code, "title": data.get("title", code),
         "table": data.get("table", "")}
        for code, data in sorted(_LEVELS.items())
    ]
