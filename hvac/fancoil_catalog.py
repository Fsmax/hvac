# -*- coding: utf-8 -*-
"""Каталог фанкойлов и подбор под нагрузку.

Источники: каталоги Carrier 42N/42GW, Daikin FWC/FWQ, Mitsubishi PCFY,
Lessar, Systemair Topvex FC. Производительности приведены к стандартным
условиям EN 1397:

    Холод:  T_air_in = 27°C DB / 19°C WB, T_water = 7/12 °C
    Тепло:  T_air_in = 20°C, T_water = 70/60 °C (или 60/40 для 4-тр.)

Базовый расчёт пересчёта на фактические условия — линейный по разнице
температур (EN 1397 § 6):

    Q_actual = Q_nominal · (ΔT_actual / ΔT_nominal)

Это упрощение работает в пределах ±20% от номинала; для точного подбора
использовать программы производителей.

Данные каталога вынесены в hvac/catalogs/data/fancoils.json;
пользовательские дополнения — JSON-файлы в ~/.hvac_calc/catalogs/
(формат описан в hvac/catalogs/user_catalogs.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from importlib.resources import files
from pathlib import Path
from typing import Dict, List, Optional, Union

from hvac.catalogs.user_catalogs import iter_user_catalogs


@dataclass
class FancoilModel:
    """Запись каталога фанкойла."""
    name: str
    family: str = ""                   # «Кассетный», «Канальный», «Настенный»
    pipes: int = 4                     # 2 или 4 трубы

    # Производительность по EN 1397 (на средней скорости вентилятора)
    q_cool_nom_w: float = 0.0          # полная холодопроизводительность
    q_cool_sens_nom_w: float = 0.0     # явная часть холода
    q_heat_nom_w: float = 0.0          # теплопроизводительность

    # Расходы воздуха и воды
    air_flow_m3_h: float = 0.0         # на средней скорости
    air_flow_min_m3_h: float = 0.0
    air_flow_max_m3_h: float = 0.0
    water_flow_cool_l_h: float = 0.0   # при ΔT=5K по воде
    water_flow_heat_l_h: float = 0.0   # при ΔT=10K по воде

    # Электрика и шум
    fan_power_w: float = 0.0
    noise_db_a: float = 0.0            # ср. скорость, 3 м от агрегата

    # Габариты, мм
    width_mm: int = 0
    depth_mm: int = 0
    height_mm: int = 0

    # Расчётные условия (для пересчёта)
    cool_dt_nominal: float = 20.0      # T_air − T_water_avg = 27 − 9.5 ≈ 17.5
    heat_dt_nominal: float = 45.0      # 20 − 65 = -45 (модуль)

    note: str = ""


def correct_cool(q_nom: float, dt_actual: float,
                  dt_nominal: float = 20.0) -> float:
    """Линейная коррекция холодопроизводительности по ΔT."""
    if dt_nominal <= 0 or dt_actual <= 0:
        return 0.0
    return q_nom * (dt_actual / dt_nominal)


def correct_heat(q_nom: float, dt_actual: float,
                  dt_nominal: float = 45.0) -> float:
    """Линейная коррекция теплопроизводительности."""
    if dt_nominal <= 0 or dt_actual <= 0:
        return 0.0
    return q_nom * (dt_actual / dt_nominal)


# ============================================================================
# Каталог — типовые модели Carrier 42N / Daikin FWC / Mitsubishi PCFY
# ============================================================================
# Данные вынесены в hvac/catalogs/data/fancoils.json; пользовательские
# дополнения — JSON в ~/.hvac_calc/catalogs/ (см. catalogs/user_catalogs.py).

_FIELD_NAMES = {f.name for f in fields(FancoilModel)}


def _model_from_dict(d: dict) -> FancoilModel:
    """FancoilModel из словаря JSON; неизвестные ключи игнорируются."""
    return FancoilModel(**{k: v for k, v in d.items() if k in _FIELD_NAMES})


def _load_builtin() -> List[FancoilModel]:
    """Читает встроенный каталог из hvac/catalogs/data/fancoils.json.

    Через importlib.resources — работает и из исходников, и в сборке
    PyInstaller (файл объявлен в datas hvac_calc.spec).
    """
    raw = (files("hvac.catalogs") / "data" / "fancoils.json").read_text("utf-8")
    return [_model_from_dict(m) for m in json.loads(raw).get("models", [])]


def load_fancoil_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[FancoilModel]:
    """Встроенный каталог + пользовательские каталоги типа "fancoils"."""
    models = _load_builtin()
    for data in iter_user_catalogs("fancoils", user_dir):
        models.extend(_model_from_dict(m) for m in data.get("models", []))
    return models


FANCOIL_CATALOG: List[FancoilModel] = load_fancoil_catalog()


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class FancoilPick:
    model: FancoilModel
    actual_cool_w: float = 0.0
    actual_heat_w: float = 0.0
    cool_margin_pct: float = 0.0
    heat_margin_pct: float = 0.0
    note: str = ""


def select_fancoil(
    required_cool_w: float,
    required_heat_w: float = 0.0,
    *,
    t_air_db: float = 27.0,
    t_water_cool_supply: float = 7.0,
    t_water_cool_return: float = 12.0,
    t_water_heat_supply: float = 60.0,
    t_water_heat_return: float = 40.0,
    t_air_heat: float = 20.0,
    family_filter: Optional[List[str]] = None,
    pipes_filter: Optional[int] = None,
    catalog: Optional[List[FancoilModel]] = None,
    min_margin: float = 0.0,
    max_margin: float = 0.50,
) -> Optional[FancoilPick]:
    """Подбор фанкойла под холодильную (и опц. тепловую) нагрузку.

    Линейный пересчёт от номинала. В фильтре приоритет по семейству.

    Возвращает FancoilPick или None если ничего не подошло.
    """
    cat = catalog if catalog is not None else FANCOIL_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]
    if pipes_filter is not None:
        cat = [m for m in cat if m.pipes == pipes_filter]
    if not cat:
        return None

    # Расчётные ΔT
    t_water_cool_avg = 0.5 * (t_water_cool_supply + t_water_cool_return)
    dt_cool_actual = t_air_db - t_water_cool_avg
    t_water_heat_avg = 0.5 * (t_water_heat_supply + t_water_heat_return)
    dt_heat_actual = t_water_heat_avg - t_air_heat

    picks: List[FancoilPick] = []
    for m in cat:
        q_cool = correct_cool(m.q_cool_nom_w, dt_cool_actual,
                                 m.cool_dt_nominal)
        q_heat = correct_heat(m.q_heat_nom_w, dt_heat_actual,
                                 m.heat_dt_nominal) if required_heat_w > 0 else 0
        if q_cool < required_cool_w * (1.0 + min_margin):
            continue
        if required_heat_w > 0 and q_heat < required_heat_w * (1.0 + min_margin):
            continue
        cool_margin = (q_cool - required_cool_w) / required_cool_w
        heat_margin = ((q_heat - required_heat_w) / required_heat_w
                        if required_heat_w > 0 else 0.0)
        if cool_margin > max_margin:
            continue
        picks.append(FancoilPick(
            model=m, actual_cool_w=q_cool, actual_heat_w=q_heat,
            cool_margin_pct=cool_margin * 100.0,
            heat_margin_pct=heat_margin * 100.0,
        ))

    if not picks:
        return None
    # Минимальный запас — лучший вариант
    picks.sort(key=lambda p: p.cool_margin_pct)
    return picks[0]


def select_fancoils_for_spaces(
    spaces,
    *,
    family_filter: Optional[List[str]] = None,
    pipes_filter: Optional[int] = None,
    **kwargs,
) -> Dict[str, FancoilPick]:
    """Подбор фанкойлов на все помещения с heat_gain_w > 0."""
    result: Dict[str, FancoilPick] = {}
    for sp in spaces:
        q_cool = getattr(sp, "heat_gain_w", 0.0)
        if q_cool <= 0:
            continue
        q_heat = getattr(sp, "heat_loss_w", 0.0) or 0.0
        pick = select_fancoil(
            required_cool_w=q_cool,
            required_heat_w=q_heat,
            t_air_db=getattr(sp, "t_in_cool", 24.0) + 3.0,
            t_air_heat=getattr(sp, "t_in_heat", 20.0),
            family_filter=family_filter,
            pipes_filter=pipes_filter,
            **kwargs,
        )
        if pick is not None:
            result[sp.space_id] = pick
    return result
