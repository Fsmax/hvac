# -*- coding: utf-8 -*-
"""Каталог конструкций — сборка уникальных типов из выгрузки Revit."""

from __future__ import annotations
from typing import Dict, List, Tuple
from hvac.models import BoundaryElement, Construction


# Нормативное сопротивление теплопередаче R_норм для жилых и общественных
# зданий по СП 50.13330.2012 табл. 3. Формула:
#     R_норм = a · ГСОП + b
# где ГСОП — градусо-сутки отопительного периода (база 18 °C).
# Коэффициенты (a, b, R_min) для каждой категории:
#   a — наклон линейной зависимости от ГСОП, м²·К/Вт на градусо-сутки
#   b — свободный член, м²·К/Вт
#   R_min — минимальное значение для южных климатов
_R_NORM_COEFFS: Dict[str, Tuple[float, float, float]] = {
    # Категория: (a, b, R_min)
    "Стены":    (0.00035, 1.4, 1.4),    # для жилых; для общ. (0.0003, 1.2, 1.2)
    "Покрытие": (0.0005,  2.2, 2.2),
    "Пол":      (0.00045, 1.9, 1.9),    # перекрытия над неотапл. подвалами / по грунту
    "Окна":     (0.000075, 0.15, 0.30),
    "Витраж":   (0.000075, 0.15, 0.30),
    "Двери":    (0.0,     0.6, 0.6),    # СП 50 не нормирует напрямую → дефолт
}


def r_norm_for(category: str, gsop_18: float,
               building_type: str = "residential") -> float:
    """Нормативное R по СП 50 табл. 3.

    Параметры
    ---------
    category : "Стены" / "Покрытие" / "Пол" / "Окна" / "Витраж" / "Двери"
    gsop_18 : градусо-сутки отопительного периода (база 18 °C)
    building_type : "residential" (жилые) или "public" (общественные)

    Возвращает нормативное R, м²·К/Вт. Если категория неизвестна — 0.
    """
    coeffs = _R_NORM_COEFFS.get(category)
    if not coeffs:
        return 0.0
    a, b, r_min = coeffs
    # Общественные здания нормируются мягче (около -15% для стен)
    if building_type == "public" and category == "Стены":
        a, b, r_min = 0.0003, 1.2, 1.2
    if gsop_18 <= 0:
        return r_min
    return max(a * gsop_18 + b, r_min)


def u_norm_for(category: str, gsop_18: float,
               building_type: str = "residential") -> float:
    """Нормативное U = 1 / R_норм."""
    r = r_norm_for(category, gsop_18, building_type)
    return 1.0 / r if r > 0 else 0.0


# Дефолтные U-значения по СП 50.13330 для типичных условий.
# Пользователь редактирует в UI вкладки "Конструкции".
DEFAULT_U_BY_CATEGORY = {
    "Стены":    0.45,
    "Двери":    2.20,
    "Окна":     1.80,
    "Витраж":   2.20,
    "Покрытие": 0.25,
    "Пол":      0.35,
}

# Коэффициент пропускания солнечного тепла (для светопрозрачных).
# Современные стекла Low-E / selective: 0.25-0.40.
DEFAULT_SHGC = {
    "Стены":    0.00, "Двери":    0.00, "Окна":     0.45,
    "Витраж":   0.40, "Покрытие": 0.00, "Пол":      0.00,
}


def construction_key(category: str, family: str, type_name: str,
                     thickness_mm: float) -> str:
    """Уникальный ключ типа конструкции."""
    th = f"{int(thickness_mm)}" if thickness_mm else "0"
    parts = [category, family, type_name, th]
    return " / ".join(p for p in parts if p)


# Ключевые слова для детекции витражей (Curtain Walls в Revit).
# Если ЛЮБОЕ слово встречается в family/type_name → конструкция считается
# витражом (Витраж), даже если в CSV категория = "Стены"/"Walls".
# Это нужно потому что Dynamo-скрипт выгружает Curtain Walls с category=Walls,
# а они должны быть остеклёнными (с SHGC > 0).
_CURTAIN_WALL_KEYWORDS = (
    "витраж", "curtain", "glaz", "glass", "стекл",
    "facade", "фасад", "ограждение",
    # Названия типов из проекта Chorsu и подобных:
    "chr_balcony", "balcony", "балкон", "loggia", "лоджия",
)


def normalize_category(category: str, family: str, type_name: str = "") -> str:
    """Нормализует категорию (например, витраж → отдельная категория).

    Параметры
    ---------
    category : категория из CSV (Стены / Окна / Витраж / Двери / Покрытие / Пол)
    family : имя семейства в Revit
    type_name : имя типа в Revit (опционально для обратной совместимости)

    Возвращает нормализованную категорию. Если family или type_name содержат
    ключевые слова витража (см. _CURTAIN_WALL_KEYWORDS) — категория станет
    "Витраж" даже если в CSV была "Стены".
    """
    combined = ((family or "") + " " + (type_name or "")).lower()
    for kw in _CURTAIN_WALL_KEYWORDS:
        if kw in combined:
            return "Витраж"
    return category or ""


def build_construction_catalog(elements: List[BoundaryElement]) -> Dict[str, Construction]:
    """Собирает уникальные конструкции из элементов наружных ограждений."""
    catalog: Dict[str, Construction] = {}
    for el in elements:
        if not el.is_exterior:
            continue
        cat = normalize_category(el.category, el.family, el.type_name)
        key = construction_key(cat, el.family, el.type_name, el.thickness_mm)
        if key not in catalog:
            catalog[key] = Construction(
                key=key,
                category=cat,
                family=el.family,
                type_name=el.type_name,
                thickness_mm=el.thickness_mm,
                u_value=DEFAULT_U_BY_CATEGORY.get(cat, 0.5),
                shgc=DEFAULT_SHGC.get(cat, 0.0),
            )
        el.construction_key = key
    return catalog
