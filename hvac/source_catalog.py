# -*- coding: utf-8 -*-
"""Каталог котлов и чиллеров и подбор количества агрегатов.

Источник (HeatingSystem / CoolingSystem) подбирается по требуемой
мощности (Σ нагрузок × запас — считает hvac/equipment_sizing.py):
для каждой модели каталога вычисляется количество одинаковых агрегатов
N = ceil(required / q_kw) и фактический запас каскада. Варианты
сортируются: меньше агрегатов, затем меньше перебор мощности.

Это каталожный ПРЕДПОДБОР: данные встроенного каталога — типовые ряды
серий; финальный типоразмер уточняется по программе подбора
производителя. Резервный агрегат (N+1) добавляет UI по флагу.

Данные каталога — hvac/catalogs/data/boilers.json и chillers.json;
пользовательские дополнения — JSON-файлы типов "boilers" / "chillers"
в ~/.hvac_calc/catalogs/ (формат — hvac/catalogs/user_catalogs.py).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from importlib.resources import files
from pathlib import Path
from typing import List, Optional, Union

from hvac.catalogs.user_catalogs import iter_user_catalogs


@dataclass
class BoilerModel:
    """Запись каталога котлов (водогрейные)."""
    name: str
    manufacturer: str = ""
    family: str = ""               # «Жаротрубный водогрейный, газ», …
    q_kw: float = 0.0              # номинальная теплопроизводительность
    efficiency: float = 0.92       # КПД по низшей теплоте (конденсац. >1)
    fuel: str = "gas"              # gas / diesel / gas_diesel / electric
    t_max_c: float = 110.0         # макс. температура подачи
    pressure_bar: float = 6.0      # макс. рабочее давление
    weight_kg: float = 0.0
    note: str = ""


@dataclass
class ChillerModel:
    """Запись каталога чиллеров."""
    name: str
    manufacturer: str = ""
    family: str = ""               # «Возд. охл., винтовой, R134a», …
    q_kw: float = 0.0              # номинальная холодопроизводительность
    eer: float = 3.0               # EER при номинальных условиях
    cooling: str = "air"           # air / water — охлаждение конденсатора
    compressor: str = ""           # scroll / screw / centrifugal
    refrigerant: str = ""
    weight_kg: float = 0.0
    note: str = ""

    @property
    def power_el_kw(self) -> float:
        """Оценка электрической мощности по EER."""
        return self.q_kw / self.eer if self.eer > 0 else 0.0


SourceModel = Union[BoilerModel, ChillerModel]

_BOILER_FIELDS = {f.name for f in fields(BoilerModel)}
_CHILLER_FIELDS = {f.name for f in fields(ChillerModel)}


def _from_dict(cls, allowed: set, d: dict):
    """Модель из словаря JSON; неизвестные ключи игнорируются."""
    return cls(**{k: v for k, v in d.items() if k in allowed})


def _load_builtin(fname: str, cls, allowed: set) -> list:
    raw = (files("hvac.catalogs") / "data" / fname).read_text("utf-8")
    return [_from_dict(cls, allowed, m)
            for m in json.loads(raw).get("models", [])]


def load_boiler_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[BoilerModel]:
    """Встроенный каталог котлов + пользовательские каталоги типа "boilers"."""
    models = _load_builtin("boilers.json", BoilerModel, _BOILER_FIELDS)
    for data in iter_user_catalogs("boilers", user_dir):
        models.extend(_from_dict(BoilerModel, _BOILER_FIELDS, m)
                      for m in data.get("models", []))
    return models


def load_chiller_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[ChillerModel]:
    """Встроенный каталог чиллеров + пользовательские типа "chillers"."""
    models = _load_builtin("chillers.json", ChillerModel, _CHILLER_FIELDS)
    for data in iter_user_catalogs("chillers", user_dir):
        models.extend(_from_dict(ChillerModel, _CHILLER_FIELDS, m)
                      for m in data.get("models", []))
    return models


BOILER_CATALOG: List[BoilerModel] = load_boiler_catalog()
CHILLER_CATALOG: List[ChillerModel] = load_chiller_catalog()


def catalog_for_domain(domain: str) -> List[SourceModel]:
    """Каталог по домену источника: heating → котлы, cooling → чиллеры."""
    return BOILER_CATALOG if domain == "heating" else CHILLER_CATALOG


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class SourcePick:
    """Вариант каскада: N одинаковых агрегатов одной модели."""
    model: SourceModel
    units: int = 0                 # рабочих агрегатов (без резерва)
    total_kw: float = 0.0          # units × q_kw
    margin_pct: float = 0.0        # запас каскада над требуемой мощностью


def cascade_for(required_kw: float, q_kw: float,
                max_units: int = 8) -> int:
    """Количество агрегатов мощностью q_kw под требуемую нагрузку.

    0 — модель не подходит (нет мощности или нужно больше max_units).
    """
    if required_kw <= 0 or q_kw <= 0:
        return 0
    n = int(math.ceil(required_kw / q_kw - 1e-9))
    return n if 0 < n <= max_units else 0


def select_source_units(
    required_kw: float,
    catalog: List[SourceModel],
    *,
    max_units: int = 8,
    n_best: int = 5,
) -> List[SourcePick]:
    """Варианты каскадов под требуемую мощность (кВт).

    Возвращает до n_best вариантов (0 — все подходящие), сортировка:
    меньше агрегатов, затем меньше перебор мощности, затем меньшая
    единичная мощность. Пусто — нагрузка нулевая или каталог не покрыл.
    """
    if required_kw <= 0:
        return []
    picks: List[SourcePick] = []
    for m in catalog:
        n = cascade_for(required_kw, m.q_kw, max_units)
        if not n:
            continue
        total = n * m.q_kw
        picks.append(SourcePick(
            model=m, units=n, total_kw=total,
            margin_pct=(total - required_kw) / required_kw * 100.0))
    picks.sort(key=lambda p: (p.units, p.margin_pct, p.model.q_kw))
    return picks[:n_best] if n_best > 0 else picks
