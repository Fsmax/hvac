# -*- coding: utf-8 -*-
"""Проверка ограждающих конструкций на риск конденсации
(СП 50.13330.2012 п. 5.7, Приложение Е).

Для каждой внешней ограждающей конструкции рассчитывает:

  • τ_int — температура внутренней поверхности при расчётных условиях
  • t_d   — точка росы воздуха помещения (по формуле Магнуса)
  • Δt    — перепад t_in − τ_int (нормативный по СП 50)

И флагует:
  • condensation_risk = True если τ_int < t_d (выпадение конденсата)
  • normative_fail    = True если Δt > Δt_н по СП 50 Таблица 5

Нормативные перепады Δt_н по СП 50 Табл. 5 (для жилых/общественных):
  • Стены наружные:           4.0 K
  • Покрытия (потолки):       3.0 K
  • Чердачные перекрытия:     3.0 K
  • Полы над неотап.:         2.0 K
  • Окна, балконные двери:    нормативные R_окн, проверка не Δt

Формулы:

  R_si (сопротивление внутр. теплопереходу) по СП 50:
    – стены, окна          R_si = 1/α_в = 1/8.7  ≈ 0.115 м²·К/Вт
    – потолки              R_si = 1/8.0  ≈ 0.125
    – полы                 R_si = 1/8.7  ≈ 0.115

  Температура внутренней поверхности:
    τ_int = t_in − (t_in − t_out) · R_si · U

  Формула Магнуса для точки росы (с погрешностью <0.1 K в диапазоне −40…+50°C):
    γ = ln(φ/100) + (a·t)/(b+t),   a = 17.27,  b = 237.7
    t_d = b·γ / (a − γ)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space, BoundaryElement, Construction


# ============================================================================
# Константы СП 50.13330
# ============================================================================

# Сопротивление теплопереходу внутренней поверхности, м²·К/Вт (СП 50 Табл. 4)
R_SI_WALL = 1.0 / 8.7        # 0.1149
R_SI_CEILING = 1.0 / 8.0     # 0.1250
R_SI_FLOOR = 1.0 / 8.7       # 0.1149  (для полов над неотапливаемыми)
R_SI_DEFAULT = R_SI_WALL

# Нормативные перепады температур Δt_н по СП 50 Табл. 5
# (для жилых, гостиниц, школ, больниц, общежитий, общественных зданий)
DT_NORM = {
    "wall":       4.0,    # наружные стены
    "ceiling":    3.0,    # покрытия и чердачные перекрытия
    "attic":      3.0,    # перекрытия чердачные
    "floor":      2.0,    # перекрытия над проездами/подвалами/подпольями
    "shower":     2.5,    # для помещений душевых, бассейнов (СП 50)
}

# Стандартные значения внутренней относительной влажности для разных
# типов помещений, % (используется если у Space нет своего rh_design)
ROOM_TYPE_RH_DESIGN = {
    "Офис":              50,
    "Жилая комната":     55,
    "Гостиничный номер": 55,
    "Конференц-зал":     50,
    "Магазин / торговля": 50,
    "Ресторан / кухня":  60,
    "Санузел":           70,   # повышенная — душ, пар
    "Серверная":         45,   # пониженная — техника
    "Технич. помещение": 50,
    "Коридор":           45,
    "Вестибюль":         45,
    "Лестница":          40,
    "Лифт / шахта":      40,
    "Гараж / автостоянка": 40,
    "Склад":             50,
    "Прочее":            50,
}


# ============================================================================
# Базовые формулы
# ============================================================================

def saturation_pressure_pa(t_c: float) -> float:
    """Давление насыщенного водяного пара (Па) по формуле Магнуса.

    Хорошо работает в диапазоне −40…+50°C, погрешность <0.3 %.
    """
    return 610.94 * math.exp((17.625 * t_c) / (243.04 + t_c))


def dew_point_c(t_air_c: float, rh_percent: float) -> float:
    """Точка росы по сухой t воздуха и относительной влажности (формула Магнуса).

    Параметры
    ---------
    t_air_c : температура воздуха, °C
    rh_percent : относительная влажность, % (0..100)

    Возвращает
    ----------
    Температуру точки росы, °C. При rh=100 равна t_air_c.
    Для rh ≤ 0 возвращает −273.15 (вырожденный случай).
    """
    if rh_percent <= 0:
        return -273.15
    rh = min(max(rh_percent, 0.01), 100.0) / 100.0
    a, b = 17.625, 243.04
    gamma = math.log(rh) + (a * t_air_c) / (b + t_air_c)
    return (b * gamma) / (a - gamma)


def surface_temperature(u_value: float, t_in: float, t_out: float,
                        r_si: float = R_SI_WALL) -> float:
    """Температура внутренней поверхности ограждения.

    τ_int = t_in − (t_in − t_out) · R_si · U

    Параметры
    ---------
    u_value : коэффициент теплопередачи U, Вт/(м²·К)
    t_in    : температура внутреннего воздуха, °C
    t_out   : расчётная зимняя наружная, °C
    r_si    : сопротивление теплопереходу внутренней поверхности, м²·К/Вт

    Возвращает
    ----------
    τ_int, °C. Для U=0 или вырожденных случаев возвращает t_in.
    """
    if u_value <= 0:
        return t_in
    return t_in - (t_in - t_out) * r_si * u_value


def r_si_for_category(category: str) -> float:
    """R_si в зависимости от категории ограждения."""
    cat = (category or "").lower()
    if "потол" in cat or "перекр" in cat or "покры" in cat or "крыш" in cat:
        return R_SI_CEILING
    if "пол" in cat or "fl" in cat:
        return R_SI_FLOOR
    return R_SI_WALL


def dt_normative_for_category(category: str) -> float:
    """Δt_н по СП 50 Табл. 5 в зависимости от категории."""
    cat = (category or "").lower()
    if "потол" in cat or "перекр" in cat or "покры" in cat or "крыш" in cat:
        return DT_NORM["ceiling"]
    if "пол" in cat:
        return DT_NORM["floor"]
    return DT_NORM["wall"]


# ============================================================================
# Структуры результатов
# ============================================================================

@dataclass
class CondensationCheck:
    """Результат проверки одного элемента ограждения на конденсат."""
    space_id: str
    space_number: str
    space_name: str
    element_id: str
    category: str
    construction_key: str
    u_value: float                # Вт/(м²·К)
    t_in: float                   # °C — внутренний воздух
    t_out: float                  # °C — расчётная наружная
    rh_in: float                  # % — расчётная вл. внутри
    t_surface: float              # °C — τ_int
    t_dew: float                  # °C — точка росы
    dt_actual: float              # K — t_in − τ_int
    dt_normative: float           # K — норматив СП 50 Табл. 5

    # Флаги
    condensation_risk: bool = False     # τ_int < t_d
    normative_fail: bool = False        # Δt > Δt_н

    @property
    def severity(self) -> str:
        """Серьёзность результата: 'ok' / 'normative' / 'condensation'."""
        if self.condensation_risk:
            return "condensation"
        if self.normative_fail:
            return "normative"
        return "ok"

    @property
    def margin_to_dew(self) -> float:
        """Запас до точки росы, K. Отрицательное = конденсат."""
        return self.t_surface - self.t_dew


# ============================================================================
# Анализ
# ============================================================================

def _resolve_rh(space: "Space") -> float:
    """Возвращает расчётную относительную влажность для помещения, %.

    Иерархия: 1) явное поле space.rh_design (если есть), 2) пресет по
    room_type, 3) дефолт 50%.
    """
    rh = getattr(space, "rh_design", None)
    if rh is not None and rh > 0:
        return float(rh)
    return ROOM_TYPE_RH_DESIGN.get(space.room_type, 50.0)


def check_element(element: "BoundaryElement", space: "Space",
                  t_out: float, rh_in: Optional[float] = None) -> CondensationCheck:
    """Проверяет один элемент ограждения на риск конденсации.

    Если rh_in не задан — определяется автоматически по типу помещения.
    """
    if rh_in is None:
        rh_in = _resolve_rh(space)

    r_si = r_si_for_category(element.category)
    dt_n = dt_normative_for_category(element.category)
    # Душевые/санузлы используют более строгий перепад
    if space.room_type == "Санузел":
        dt_n = DT_NORM["shower"]

    t_surface = surface_temperature(element.u_value, space.t_in_heat,
                                    t_out, r_si)
    t_dew = dew_point_c(space.t_in_heat, rh_in)
    dt_actual = space.t_in_heat - t_surface

    return CondensationCheck(
        space_id=space.space_id,
        space_number=space.number,
        space_name=space.name,
        element_id=element.element_id,
        category=element.category,
        construction_key=element.construction_key,
        u_value=element.u_value,
        t_in=space.t_in_heat,
        t_out=t_out,
        rh_in=rh_in,
        t_surface=t_surface,
        t_dew=t_dew,
        dt_actual=dt_actual,
        dt_normative=dt_n,
        condensation_risk=(t_surface < t_dew),
        normative_fail=(dt_actual > dt_n + 0.05),  # +0.05 — допуск окр.
    )


def analyze_project(project: "HVACProject",
                    rh_override: Optional[float] = None,
                    include_internal: bool = False) -> List[CondensationCheck]:
    """Проверка всех внешних элементов всех помещений.

    Параметры
    ---------
    rh_override : если задано — используется для всех помещений (например 55%)
    include_internal : включать ли внутренние ограждения (по умолчанию нет)

    Возвращает
    ----------
    Список CondensationCheck. Каждый элемент проверяется отдельно с учётом
    своего U и своего t_in.
    """
    results: List[CondensationCheck] = []
    t_out = project.params.t_out_heating

    for element in project.elements:
        if not include_internal and not element.is_exterior:
            continue
        if element.u_value <= 0:
            continue  # U не задан — нечего проверять

        space = project.get_space(element.space_id)
        if not space:
            continue

        # Полы по грунту проверяются по своей температуре грунта,
        # обычно не на конденсат, пропускаем
        if not element.is_exterior:
            continue

        rh = rh_override if rh_override else _resolve_rh(space)
        results.append(check_element(element, space, t_out, rh))

    return results


def summarize_by_construction(checks: List[CondensationCheck]) -> Dict[str, Dict]:
    """Сводка по конструкциям: для каждого ключа — худший случай."""
    by_key: Dict[str, Dict] = {}
    for c in checks:
        key = c.construction_key or "—"
        info = by_key.setdefault(key, {
            "construction_key": key,
            "u_value": c.u_value,
            "n_elements": 0,
            "n_condensation": 0,
            "n_normative_fail": 0,
            "worst_margin": float("inf"),
            "worst_space": "",
        })
        info["n_elements"] += 1
        if c.condensation_risk:
            info["n_condensation"] += 1
        if c.normative_fail:
            info["n_normative_fail"] += 1
        if c.margin_to_dew < info["worst_margin"]:
            info["worst_margin"] = c.margin_to_dew
            info["worst_space"] = f"{c.space_number} {c.space_name}"
    return by_key


def summarize_by_space(checks: List[CondensationCheck]) -> Dict[str, Dict]:
    """Сводка по помещениям: сколько проблемных элементов в каждом."""
    by_space: Dict[str, Dict] = {}
    for c in checks:
        info = by_space.setdefault(c.space_id, {
            "space_id": c.space_id,
            "space_label": f"{c.space_number} {c.space_name}",
            "n_total": 0,
            "n_condensation": 0,
            "n_normative_fail": 0,
            "worst_margin": float("inf"),
        })
        info["n_total"] += 1
        if c.condensation_risk:
            info["n_condensation"] += 1
        if c.normative_fail:
            info["n_normative_fail"] += 1
        info["worst_margin"] = min(info["worst_margin"], c.margin_to_dew)
    return by_space


def total_problems(checks: List[CondensationCheck]) -> Dict[str, int]:
    """Сколько всего проблемных элементов в проекте."""
    return {
        "total": len(checks),
        "condensation": sum(1 for c in checks if c.condensation_risk),
        "normative_fail": sum(1 for c in checks if c.normative_fail),
        "ok": sum(1 for c in checks
                  if not c.condensation_risk and not c.normative_fail),
    }
