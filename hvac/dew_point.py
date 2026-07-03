# -*- coding: utf-8 -*-
"""Проверка ограждающих конструкций на риск конденсации
(КМК 2.01.04-18 / СП 50.13330.2012 п. 5.7, Приложение Е).

Норматив переключается через project.params.thermal_norm
("KMK_UZ" — основная, "SP_RU").

Для каждой внешней ограждающей конструкции рассчитывает:

  • τ_int — температура внутренней поверхности при расчётных условиях
  • t_d   — точка росы воздуха помещения (по формуле Магнуса)
  • Δt    — перепад t_in − τ_int (нормативный)

И флагует:
  • condensation_risk = True если τ_int < t_d (выпадение конденсата)
  • normative_fail    = True если Δt > Δt_н (КМК Табл.4 / СП 50 Табл.5)

Нормируемые перепады Δt_н (жилые / общественные):
  • КМК 2.01.04-18 Табл.4: стены 4.0/5.0; покрытия 3.5/4.5; полы 2.0/2.5
  • СП 50.13330 Табл.5:    стены 4.0/4.5; покрытия 3.0/4.0; полы 2.0/2.5

Формулы:

  R_si (сопротивление внутр. теплопереходу), α_в по КМК Табл.5/СП Табл.4:
    – стены, полы, гладкие потолки   R_si = 1/8.7  ≈ 0.115 м²·К/Вт
    – рёбристые потолки              R_si = 1/7.6  ≈ 0.132
    – окна                           R_si = 1/8.0  ≈ 0.125

  Температура внутренней поверхности:
    τ_int = t_in − (t_in − t_out) · R_si · U

  Формула Магнуса для точки росы (с погрешностью <0.1 K в диапазоне −40…+50°C):
    γ = ln(φ/100) + (a·t)/(b+t),   a = 17.625,  b = 243.04
    t_d = b·γ / (a − γ)
    (коэффициенты Альдучова–Эскриджа, согласованы с saturation_pressure_pa)
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space, BoundaryElement


# ============================================================================
# Константы СП 50.13330
# ============================================================================

# Сопротивление теплопереходу внутренней поверхности R_si = 1/α_в, м²·К/Вт.
# Коэф. α_в по КМК 2.01.04-18 Табл.5 = СП 50.13330 Табл.4 (совпадают):
# стены/полы/гладкие потолки 8.7; рёбристые потолки 7.6; окна 8.0; фонари 9.9.
R_SI_WALL = 1.0 / 8.7        # 0.1149
R_SI_CEILING = 1.0 / 8.7     # 0.1149  (гладкий потолок/покрытие; рёбристый — 1/7.6)
R_SI_FLOOR = 1.0 / 8.7       # 0.1149
R_SI_DEFAULT = R_SI_WALL

# Нормируемый температурный перепад Δt_н, °C — по активной норме
# (project.params.thermal_norm). КМК 2.01.04-18 Табл.4 (Узбекистан,
# основная) и СП 50.13330 Табл.5 (РФ). Различаются «residential» (жилые,
# лечебные, детские, учебные — строка 1 Табл.4) и «public» (общественные,
# адм.-быт., производственные — строка 2).
DT_NORM_BY_NORM = {
    "KMK_UZ": {
        "residential": {"wall": 4.0, "ceiling": 3.5, "attic": 3.5,
                        "floor": 2.0, "shower": 2.5},
        "public":      {"wall": 5.0, "ceiling": 4.5, "attic": 4.5,
                        "floor": 2.5, "shower": 2.5},
    },
    "SP_RU": {
        "residential": {"wall": 4.0, "ceiling": 3.0, "attic": 3.0,
                        "floor": 2.0, "shower": 2.5},
        "public":      {"wall": 4.5, "ceiling": 4.0, "attic": 4.0,
                        "floor": 2.5, "shower": 2.5},
    },
}

# Дефолтный набор (КМК, жилые) — для обратной совместимости API/тестов.
DT_NORM = DT_NORM_BY_NORM["KMK_UZ"]["residential"]

# Типы помещений «жилой» категории Δt_н (КМК Табл.4 строка 1). Остальные —
# общественная категория (строка 2, более мягкие перепады).
_RESIDENTIAL_ROOM_TYPES = {"Жилая комната", "Гостиничный номер"}

# Стандартные значения внутренней относительной влажности для разных
# типов помещений, % (используется если у Space нет своего rh_design)
ROOM_TYPE_RH_DESIGN = {
    "Офис":              50,
    "Жилая комната":     55,
    "Гостиничный номер": 55,
    "Конференц-зал":     50,
    "Магазин / торговля": 50,
    "Ресторан / зал":  60,
    "Кухня":           60,
    "Горячий цех":     65,
    "Санузел":           70,   # повышенная — душ, пар
    "Душевая":           75,   # активное парообразование
    "Бассейн":           65,   # зеркало воды — высокая влажность
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


def is_public_room(room_type: str) -> bool:
    """True — помещение относится к общественной категории Δt_н (КМК Табл.4
    строка 2), False — к жилой/лечебной/учебной (строка 1)."""
    return (room_type or "") not in _RESIDENTIAL_ROOM_TYPES


def resolve_dt_norm(thermal_norm: str = "KMK_UZ",
                    is_public: bool = False) -> Dict[str, float]:
    """Набор Δt_н для активной нормы и категории здания (см. DT_NORM_BY_NORM)."""
    by_norm = DT_NORM_BY_NORM.get(thermal_norm, DT_NORM_BY_NORM["KMK_UZ"])
    return by_norm["public" if is_public else "residential"]


def dt_normative_for_category(category: str,
                              dt_norm: Optional[Dict[str, float]] = None) -> float:
    """Δt_н по КМК Табл.4 / СП 50 Табл.5 в зависимости от категории.

    dt_norm — набор по активной норме (resolve_dt_norm); по умолчанию
    КМК/жилые (DT_NORM).
    """
    if dt_norm is None:
        dt_norm = DT_NORM
    cat = (category or "").lower()
    if "потол" in cat or "перекр" in cat or "покры" in cat or "крыш" in cat:
        return dt_norm["ceiling"]
    if "пол" in cat:
        return dt_norm["floor"]
    return dt_norm["wall"]


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
                  t_out: float, rh_in: Optional[float] = None,
                  dt_norm: Optional[Dict[str, float]] = None) -> CondensationCheck:
    """Проверяет один элемент ограждения на риск конденсации.

    Если rh_in не задан — определяется автоматически по типу помещения.
    dt_norm — набор Δt_н по активной норме/категории здания (resolve_dt_norm);
    по умолчанию КМК/жилые.
    """
    if rh_in is None:
        rh_in = _resolve_rh(space)
    if dt_norm is None:
        dt_norm = DT_NORM

    r_si = r_si_for_category(element.category)
    dt_n = dt_normative_for_category(element.category, dt_norm)
    # Душевые/санузлы используют более строгий перепад
    if space.room_type == "Санузел":
        dt_n = dt_norm["shower"]

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
    thermal_norm = getattr(project.params, "thermal_norm", "KMK_UZ")

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
        dt_norm = resolve_dt_norm(thermal_norm, is_public_room(space.room_type))
        results.append(check_element(element, space, t_out, rh, dt_norm))

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
