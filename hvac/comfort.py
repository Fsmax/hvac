# -*- coding: utf-8 -*-
"""Тепловой комфорт PMV/PPD по ISO 7730 (метод Фангера).

PMV (Predicted Mean Vote) — прогнозируемая средняя оценка теплоощущения
по семибалльной шкале от −3 (холодно) до +3 (жарко). PPD (Predicted
Percentage of Dissatisfied) — прогнозируемый процент недовольных
микроклиматом, однозначная функция PMV (минимум 5% при PMV = 0).

Реализовано уравнение Фангера по ISO 7730:2005 (раздел 4; алгоритм —
эталонный код Приложения D). Российское нормирование микроклимата —
ГОСТ 30494-2011; его «оптимальные» параметры примерно соответствуют
категории B по ISO 7730.

Категории среды (ISO 7730 Приложение A, табл. A.1):

    A: |PMV| < 0.2  (PPD < 6%)
    B: |PMV| < 0.5  (PPD < 10%)
    C: |PMV| < 0.7  (PPD < 15%)

Типичные входные значения:

    met (метаболизм):  сидя спокойно 1.0; офисная работа 1.2;
                       стоя / лёгкая работа 1.6   (1 met = 58.15 Вт/м²)
    clo (одежда):      лето 0.5; зима в помещении 1.0
                       (1 clo = 0.155 м²·К/Вт)
    v_air (подвижность воздуха): 0.1 м/с — спокойный воздух в комнате
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject

MET_TO_W_M2 = 58.15      # 1 met, Вт/м² поверхности тела
CLO_TO_M2K_W = 0.155     # 1 clo, м²·К/Вт


def water_vapour_pressure_pa(t_air_c: float, rh_pct: float) -> float:
    """Парциальное давление водяного пара, Па (формула из ISO 7730 Прил. D)."""
    return rh_pct * 10.0 * math.exp(16.6536 - 4030.183 / (t_air_c + 235.0))


def calc_pmv(t_air_c: float,
             t_radiant_c: Optional[float] = None,
             v_air_ms: float = 0.1,
             rh_pct: float = 50.0,
             met: float = 1.2,
             clo: float = 1.0,
             work_met: float = 0.0) -> float:
    """PMV по уравнению Фангера (ISO 7730:2005, Приложение D).

    Параметры
    ---------
    t_air_c     : температура воздуха, °C
    t_radiant_c : средняя радиационная температура, °C (None → = t_air_c)
    v_air_ms    : относительная скорость воздуха, м/с
    rh_pct      : относительная влажность, %
    met / clo   : метаболизм (met) и теплоизоляция одежды (clo)
    work_met    : внешняя механическая работа, met (обычно 0)
    """
    ta = t_air_c
    tr = t_radiant_c if t_radiant_c is not None else t_air_c
    pa = water_vapour_pressure_pa(ta, rh_pct)
    icl = CLO_TO_M2K_W * clo
    m = met * MET_TO_W_M2
    w = work_met * MET_TO_W_M2
    mw = m - w

    fcl = 1.05 + 0.645 * icl if icl > 0.078 else 1.0 + 1.29 * icl
    hcf = 12.1 * math.sqrt(max(v_air_ms, 0.0))   # вынужденная конвекция
    taa = ta + 273.0
    tra = tr + 273.0

    # Итерация температуры поверхности одежды (метод половинного шага
    # из эталонного кода ISO 7730 Прил. D)
    tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4
    xn = tcla / 100.0
    xf = tcla / 50.0
    hc = hcf
    for _ in range(150):
        if abs(xn - xf) <= 0.00015:
            break
        xf = (xf + xn) / 2.0
        hcn = 2.38 * abs(100.0 * xf - taa) ** 0.25  # естественная конвекция
        hc = max(hcf, hcn)
        xn = (p5 + p4 * hc - p2 * xf ** 4) / (100.0 + p3 * hc)
    tcl = 100.0 * xn - 273.0

    # Составляющие теплового баланса, Вт/м²
    hl1 = 3.05e-3 * (5733.0 - 6.99 * mw - pa)            # диффузия через кожу
    hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0     # испарение пота
    hl3 = 1.7e-5 * m * (5867.0 - pa)                     # дыхание, скрытая
    hl4 = 0.0014 * m * (34.0 - ta)                       # дыхание, явная
    hl5 = 3.96 * fcl * (xn ** 4 - (tra / 100.0) ** 4)    # излучение
    hl6 = fcl * hc * (tcl - ta)                          # конвекция

    ts = 0.303 * math.exp(-0.036 * m) + 0.028
    return ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)


def calc_ppd(pmv: float) -> float:
    """PPD (% недовольных) из PMV. Минимум 5% при PMV = 0."""
    return 100.0 - 95.0 * math.exp(-0.03353 * pmv ** 4 - 0.2179 * pmv ** 2)


def comfort_category(pmv: float) -> str:
    """Категория среды по ISO 7730 табл. A.1: "A"/"B"/"C", "—" — вне."""
    a = abs(pmv)
    if a < 0.2:
        return "A"
    if a < 0.5:
        return "B"
    if a < 0.7:
        return "C"
    return "—"


@dataclass
class ComfortResult:
    """Оценка комфорта одного помещения для одного сезона."""
    space_id: str
    season: str                  # "heating" | "cooling"
    t_air_c: float
    rh_pct: float
    v_air_ms: float
    met: float
    clo: float
    pmv: float = 0.0
    ppd: float = 0.0
    category: str = "—"          # A / B / C / — (ISO 7730 табл. A.1)


def assess_space(space, season: str = "heating", *,
                 met: float = 1.2,
                 clo: Optional[float] = None,
                 v_air_ms: float = 0.1,
                 rh_override: Optional[float] = None) -> ComfortResult:
    """Оценка комфорта помещения при расчётных параметрах сезона.

    Температура воздуха — уставка помещения (t_in_heat / t_in_cool),
    радиационная температура принята равной температуре воздуха.
    clo по умолчанию: 1.0 зимой, 0.5 летом.
    """
    from hvac.dew_point import _resolve_rh
    heating = season == "heating"
    ta = space.t_in_heat if heating else space.t_in_cool
    rh = rh_override if rh_override is not None else _resolve_rh(space)
    clo_val = clo if clo is not None else (1.0 if heating else 0.5)
    pmv = calc_pmv(ta, v_air_ms=v_air_ms, rh_pct=rh, met=met, clo=clo_val)
    return ComfortResult(
        space_id=space.space_id, season=season,
        t_air_c=ta, rh_pct=rh, v_air_ms=v_air_ms, met=met, clo=clo_val,
        pmv=round(pmv, 2), ppd=round(calc_ppd(pmv), 1),
        category=comfort_category(pmv),
    )


def assess_project(project: "HVACProject", season: str = "heating", *,
                   met: float = 1.2,
                   clo: Optional[float] = None,
                   v_air_ms: float = 0.1,
                   rh_override: Optional[float] = None,
                   ) -> Dict[str, ComfortResult]:
    """Оценка PMV/PPD для всех помещений проекта с площадью > 0.

    Возвращает {space_id: ComfortResult}.
    """
    out: Dict[str, ComfortResult] = {}
    for sp in project.spaces:
        if sp.area_m2 <= 0:
            continue
        out[sp.space_id] = assess_space(
            sp, season, met=met, clo=clo,
            v_air_ms=v_air_ms, rh_override=rh_override,
        )
    return out
