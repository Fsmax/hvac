# -*- coding: utf-8 -*-
"""Каталог конструкций — сборка уникальных типов из выгрузки Revit."""

from __future__ import annotations
from typing import Dict, List, Tuple
from hvac.models import BoundaryElement, Construction


# Нормативное (требуемое) сопротивление теплопередаче R₀^тр переключается по
# активной норме project.params.thermal_norm (как Δt_н в dew_point.py):
#   • "KMK_UZ" — КМК 2.01.04-18 Табл.2а/2б/2в (Узбекистан, ОСНОВНАЯ норма):
#       ступенчатые значения по полосам Dd (≤2000/2000–3000/>3000), 3 уровня
#       теплозащиты. См. hvac/catalogs/kmk_thermal.py + data/kmk_thermal.json.
#   • "SP_RU"  — СП 50.13330.2012 Табл.3 (РФ): линейно R = a·ГСОП + b.
#
# СП 50 Табл.3 — коэффициенты (a, b, R_min) на категорию:
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


def _r_norm_sp(category: str, gsop_18: float,
               building_type: str = "residential") -> float:
    """R₀^тр по СП 50.13330 Табл.3 (линейно R = a·ГСОП + b)."""
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


def r_norm_for(category: str, gsop_18: float,
               building_type: str = "residential",
               thermal_norm: str = "KMK_UZ", level: int = 1,
               n_floors: int = 4, n: float = 1.0,
               dd: float = None) -> float:
    """Требуемое сопротивление теплопередаче R₀^тр по активной норме.

    Параметры
    ---------
    category : "Стены" / "Покрытие" / "Пол" / "Окна" / "Витраж" / "Двери"
    gsop_18 : ГСОП, градусо-сутки отопит. периода (t_в=+20°C, ≤8°C, СП 50.13330).
              Для КМК используется как селектор полосы Dd, если явный `dd` не задан.
    building_type : "residential"/"public"/"industrial" либо детальный тип
              (напр. "жилое 4-5 этажей") — см. kmk_thermal.kmk_category_for.
    thermal_norm : "KMK_UZ" (КМК 2.01.04-18, основная) или "SP_RU" (СП 50).
    level : уровень теплозащиты КМК — 1 (Табл.2а, минимум), 2 (2б), 3 (2в).
    n_floors : этажность (для выбора res_low ≤3 / res_high >3 в КМК).
    n : коэф. КМК Табл.3 для покрытий/полов (1.0 — прямой контакт с наружным
        воздухом). Только для thermal_norm="KMK_UZ".
    dd : явные градус-сутки Dd (период ≤12 °C ШНҚ 2.01.01-22, КМК форм.1).
         Если None — берётся gsop_18 (приближение, период ≤8 °C).

    Возвращает R₀^тр, м²·К/Вт. Если категория неизвестна — 0.
    """
    if thermal_norm == "SP_RU":
        return _r_norm_sp(category, gsop_18, building_type)
    # КМК 2.01.04-18 (по умолчанию)
    from hvac.catalogs.kmk_thermal import r_norm_kmk, kmk_category_for
    kmk_cat = kmk_category_for(building_type, n_floors)
    return r_norm_kmk(category, gsop_18 if dd is None else dd,
                      kmk_category=kmk_cat, level=level, n=n)


def u_norm_for(category: str, gsop_18: float,
               building_type: str = "residential",
               thermal_norm: str = "KMK_UZ", level: int = 1,
               n_floors: int = 4, n: float = 1.0,
               dd: float = None) -> float:
    """Нормативное U = 1 / R₀^тр (по активной норме, см. r_norm_for)."""
    r = r_norm_for(category, gsop_18, building_type, thermal_norm,
                   level, n_floors, n, dd)
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
    "facade", "фасад", "ограждение", "storefront", "витрин",
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
