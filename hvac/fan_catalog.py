# -*- coding: utf-8 -*-
"""Каталог вентиляторов и подбор по рабочей точке сети.

Характеристика вентилятора аппроксимируется параболой через две
каталожные точки — максимальный расход при свободном выходе (q_max)
и максимальное давление при нулевом расходе (p_max):

    p(q) = p_max · (1 − (q / q_max)²)

Подбор: для требуемой точки (Q, Δp) из аэродинамического расчёта
(hvac/duct_network.py: fan_flow_m3_h / fan_pressure_required_pa)
выбираются модели, дающие в этой точке давление не ниже требуемого,
с предпочтением минимальной электрической мощности. Это каталожный
предподбор; финальный — по программе изготовителя с реальной кривой.

Данные каталога — hvac/catalogs/data/fans.json; пользовательские
дополнения — JSON-файлы типа "fans" в ~/.hvac_calc/catalogs/
(формат описан в hvac/catalogs/user_catalogs.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from importlib.resources import files
from pathlib import Path
from typing import List, Optional, Union

from hvac.catalogs.user_catalogs import iter_user_catalogs

# Рабочая точка правее этой доли q_max — на «хвосте» кривой: шумно и
# неустойчиво, выдаём предупреждение.
FLOW_RATIO_WARN = 0.85


@dataclass
class FanModel:
    """Запись каталога вентилятора."""
    name: str
    family: str = ""               # «Канальный круглый», «Радиальный», …
    flow_max_m3_h: float = 0.0     # расход при свободном выходе
    pressure_max_pa: float = 0.0   # давление при нулевом расходе
    power_w: float = 0.0
    rpm: int = 0
    noise_db_a: float = 0.0
    diameter_mm: int = 0           # круглое присоединение
    width_mm: int = 0              # прямоугольное присоединение
    height_mm: int = 0
    note: str = ""

    def pressure_at_flow(self, flow_m3_h: float) -> float:
        """Давление на параболической кривой при данном расходе, Па."""
        if self.flow_max_m3_h <= 0 or flow_m3_h >= self.flow_max_m3_h:
            return 0.0
        ratio = flow_m3_h / self.flow_max_m3_h
        return self.pressure_max_pa * (1.0 - ratio * ratio)


_FIELD_NAMES = {f.name for f in fields(FanModel)}


def _model_from_dict(d: dict) -> FanModel:
    """FanModel из словаря JSON; неизвестные ключи игнорируются."""
    return FanModel(**{k: v for k, v in d.items() if k in _FIELD_NAMES})


def _load_builtin() -> List[FanModel]:
    """Читает встроенный каталог из hvac/catalogs/data/fans.json."""
    raw = (files("hvac.catalogs") / "data" / "fans.json").read_text("utf-8")
    return [_model_from_dict(m) for m in json.loads(raw).get("models", [])]


def load_fan_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[FanModel]:
    """Встроенный каталог + пользовательские каталоги типа "fans"."""
    models = _load_builtin()
    for data in iter_user_catalogs("fans", user_dir):
        models.extend(_model_from_dict(m) for m in data.get("models", []))
    return models


FAN_CATALOG: List[FanModel] = load_fan_catalog()


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class FanPick:
    """Вариант вентилятора для рабочей точки."""
    model: FanModel
    flow_m3_h: float = 0.0
    pressure_required_pa: float = 0.0
    pressure_available_pa: float = 0.0
    pressure_margin_pct: float = 0.0   # запас давления в рабочей точке
    flow_ratio_pct: float = 0.0        # положение точки на кривой, % q_max
    warnings: List[str] = field(default_factory=list)


def select_fans(
    flow_m3_h: float,
    pressure_pa: float,
    *,
    family_filter: Optional[List[str]] = None,
    catalog: Optional[List[FanModel]] = None,
    n_best: int = 3,
) -> List[FanPick]:
    """Варианты вентиляторов под рабочую точку (Q, Δp).

    Возвращает до n_best подходящих моделей, отсортированных по
    электрической мощности (экономичные первыми). Пусто — ничего
    не подошло.
    """
    if flow_m3_h <= 0:
        raise ValueError("Расход должен быть положительным")
    if pressure_pa < 0:
        raise ValueError("Давление не может быть отрицательным")

    cat = catalog if catalog is not None else FAN_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]

    picks: List[FanPick] = []
    for m in cat:
        if m.flow_max_m3_h <= flow_m3_h:
            continue
        p_avail = m.pressure_at_flow(flow_m3_h)
        if p_avail < pressure_pa:
            continue
        ratio = flow_m3_h / m.flow_max_m3_h
        pick = FanPick(
            model=m,
            flow_m3_h=flow_m3_h,
            pressure_required_pa=pressure_pa,
            pressure_available_pa=p_avail,
            pressure_margin_pct=((p_avail - pressure_pa)
                                 / max(pressure_pa, 1.0) * 100.0),
            flow_ratio_pct=ratio * 100.0,
        )
        if ratio > FLOW_RATIO_WARN:
            pick.warnings.append(
                f"Рабочая точка на {ratio * 100:.0f}% q_max — правый край "
                "кривой, возможен шум и неустойчивость")
        picks.append(pick)

    picks.sort(key=lambda p: (p.model.power_w, p.pressure_margin_pct))
    return picks[:max(n_best, 1)]


def select_fan(
    flow_m3_h: float,
    pressure_pa: float,
    **kwargs,
) -> Optional[FanPick]:
    """Лучший (наименее мощный) вентилятор для рабочей точки или None."""
    picks = select_fans(flow_m3_h, pressure_pa, n_best=1, **kwargs)
    return picks[0] if picks else None
