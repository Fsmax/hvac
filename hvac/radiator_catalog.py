# -*- coding: utf-8 -*-
"""Каталог отопительных приборов и подбор под расчётную нагрузку.

Тепловые характеристики приводятся к стандартным условиям EN 442:
температурный напор ΔTн = 50 K (Tпод/Tобр/Tпом = 75/65/20).

Пересчёт мощности на фактический температурный график:

    Q_факт = Q_номин · (ΔT_факт / ΔT_номин)^n

где n — экспонента теплоотдачи прибора (по EN 442):

    Чугунные секционные:     n ≈ 1.30
    Стальные панельные:      n ≈ 1.30
    Алюминиевые секционные:  n ≈ 1.34
    Биметаллические:         n ≈ 1.30
    Конвекторы:              n ≈ 1.35..1.40
    Тёплый пол:              n ≈ 1.10 (греющая поверхность)

ΔT — средний логарифмический температурный напор:

    ΔT = ((T_пд − T_пм) − (T_об − T_пм)) / ln((T_пд − T_пм)/(T_об − T_пм))

или арифметическое приближение (СП 60 п. 6.3):

    ΔT ≈ (T_пд + T_об)/2 − T_пм

Источники
---------
EN 442-2 (Radiators and convectors — Test methods and rating)
СП 60.13330.2020 п. 6.3, СП 60 Приложение В (методика подбора)
Каталоги Kermi (Therm-X2), Purmo (Compact), Rifar (Monolit, Base),
Global (Vox), Konner.

Данные каталога вынесены в hvac/catalogs/data/radiators.json;
пользовательские дополнения — JSON-файлы в ~/.hvac_calc/catalogs/
(формат описан в hvac/catalogs/user_catalogs.py).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from importlib.resources import files
from pathlib import Path
from typing import Dict, List, Optional, Union

from hvac.catalogs.user_catalogs import iter_user_catalogs


# ============================================================================
# Расчёт мощности при произвольном температурном графике
# ============================================================================

def log_mean_temp_diff(t_supply: float, t_return: float,
                       t_room: float) -> float:
    """Логарифмический средний температурный напор, K.

    ΔT = ((Tпд − Tпм) − (Tоб − Tпм)) / ln((Tпд − Tпм)/(Tоб − Tпм))

    При близких ΔT1 ≈ ΔT2 возвращает арифметическое.
    """
    a = t_supply - t_room
    b = t_return - t_room
    if a <= 0 or b <= 0:
        return 0.0
    if abs(a - b) < 0.1:
        return 0.5 * (a + b)
    return (a - b) / math.log(a / b)


def arithmetic_temp_diff(t_supply: float, t_return: float,
                         t_room: float) -> float:
    """Арифметический ΔT (СП 60 п. 6.3). Простое приближение."""
    return 0.5 * (t_supply + t_return) - t_room


def correct_power(q_nominal_w: float,
                   dt_actual: float,
                   dt_nominal: float = 50.0,
                   n: float = 1.30) -> float:
    """Q при фактическом ΔT из номинала по формуле EN 442.

        Q = Q_ном · (ΔT_факт / ΔT_ном)^n

    Если ΔT_факт ≤ 0 — прибор не отдаёт тепла.
    """
    if dt_actual <= 0 or dt_nominal <= 0:
        return 0.0
    return q_nominal_w * (dt_actual / dt_nominal) ** n


# ============================================================================
# Каталог
# ============================================================================

@dataclass
class RadiatorModel:
    """Один типоразмер прибора отопления.

    Q_nominal_w задано для условий EN 442 (75/65/20, ΔT_n = 50 K).
    Если у прибора задано section_count_per_step > 0 — это секционная
    модель: фактическое Q = section_count · q_per_section_w.
    """
    name: str                              # «Kermi FK0 22 500x1000»
    family: str = ""                       # «Стальной панельный», «Алюминий»
    height_mm: int = 0
    length_mm: int = 0                     # для секционных: длина одной секции
    depth_mm: int = 0
    q_nominal_w: float = 0.0               # при ΔT=50 K
    n_exponent: float = 1.30
    is_sectional: bool = False             # секционный (можно набирать секции)
    sections: int = 1                      # для записи о собранном радиаторе
    max_sections: int = 1                  # ограничение по производителю
    water_volume_l: float = 0.0
    weight_kg: float = 0.0
    note: str = ""

    def actual_power_w(self, t_supply: float, t_return: float,
                        t_room: float = 20.0,
                        use_log_mean: bool = True) -> float:
        """Фактическая мощность при заданном графике."""
        dt = (log_mean_temp_diff(t_supply, t_return, t_room)
              if use_log_mean else
              arithmetic_temp_diff(t_supply, t_return, t_room))
        return correct_power(self.q_nominal_w, dt,
                               dt_nominal=50.0, n=self.n_exponent)


# ============================================================================
# Генератор семейства панельных радиаторов (Kermi FK0 / Purmo Compact / …)
# ============================================================================
#
# Тепловой поток стального панельного радиатора с боковым подключением
# хорошо аппроксимируется линейной зависимостью от длины при фиксированной
# высоте и типе:
#
#     Q(L) = q_per_m · L_m
#
# Удельные мощности q_per_m (Вт на 1 м длины при ΔT=50K) по справочникам
# производителей лежат в hvac/catalogs/data/radiators.json
# (panel_families) — см. описание формата в hvac/catalogs/user_catalogs.py.

def _generate_panel_family(brand: str,
                             q_table: Dict[int, Dict[int, float]],
                             v_table: Dict[int, Dict[int, float]],
                             depth_mm: Dict[int, int],
                             lengths_mm: List[int],
                             family_prefix: str = "Стальной панельный",
                             n_exponent: float = 1.30,
                             ) -> List[RadiatorModel]:
    """Генерирует список RadiatorModel для семейства панельных радиаторов."""
    models: List[RadiatorModel] = []
    for h, by_type in q_table.items():
        for t, q_per_m in by_type.items():
            v_per_m = v_table.get(h, {}).get(t, 0.5 * t / 10)
            for L in lengths_mm:
                Lm = L / 1000.0
                q = q_per_m * Lm
                v = v_per_m * Lm
                w = 0.55 * q_per_m * Lm / 50.0   # вес ≈ 1 кг на 50 Вт
                models.append(RadiatorModel(
                    name=f"{brand} {t} {h}x{L}",
                    family=f"{family_prefix} {t}",
                    height_mm=h, length_mm=L, depth_mm=depth_mm[t],
                    q_nominal_w=q, n_exponent=n_exponent,
                    water_volume_l=v, weight_kg=w,
                ))
    return models


_FIELD_NAMES = {f.name for f in fields(RadiatorModel)}


def _model_from_dict(d: dict) -> RadiatorModel:
    """RadiatorModel из словаря JSON; неизвестные ключи игнорируются."""
    return RadiatorModel(**{k: v for k, v in d.items() if k in _FIELD_NAMES})


def _models_from_catalog_dict(data: dict) -> List[RadiatorModel]:
    """Модели из словаря каталога: panel_families (генератор) + models."""
    models: List[RadiatorModel] = []
    for fam in data.get("panel_families", []):
        models.extend(_generate_panel_family(
            fam["brand"],
            {int(h): {int(t): float(q) for t, q in by_t.items()}
             for h, by_t in fam["q_per_m"].items()},
            {int(h): {int(t): float(v) for t, v in by_t.items()}
             for h, by_t in fam.get("v_per_m", {}).items()},
            {int(t): int(d) for t, d in fam["depth_mm"].items()},
            [int(x) for x in fam["lengths_mm"]],
            family_prefix=fam.get("family_prefix", "Стальной панельный"),
            n_exponent=float(fam.get("n_exponent", 1.30)),
        ))
    models.extend(_model_from_dict(m) for m in data.get("models", []))
    return models


# ============================================================================
# Каталог типовых моделей
# ============================================================================
# Данные вынесены в hvac/catalogs/data/radiators.json: панельные семейства
# (Kermi FK0, Purmo Compact) генерируются из таблиц q_per_m (5 высот ×
# 3 типа × 15 длин = 225 моделей на бренд), секционные (алюминий / биметалл /
# чугун), конвекторы и тёплый пол заданы явными записями. Пользовательские
# дополнения — JSON в ~/.hvac_calc/catalogs/ (см. catalogs/user_catalogs.py).

def _load_builtin() -> List[RadiatorModel]:
    """Читает встроенный каталог из hvac/catalogs/data/radiators.json.

    Через importlib.resources — работает и из исходников, и в сборке
    PyInstaller (файл объявлен в datas hvac_calc.spec).
    """
    raw = (files("hvac.catalogs") / "data" / "radiators.json").read_text("utf-8")
    return _models_from_catalog_dict(json.loads(raw))


def load_radiator_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[RadiatorModel]:
    """Встроенный каталог + пользовательские каталоги типа "radiators"."""
    models = _load_builtin()
    for data in iter_user_catalogs("radiators", user_dir):
        models.extend(_models_from_catalog_dict(data))
    return models


RADIATOR_CATALOG: List[RadiatorModel] = load_radiator_catalog()


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class RadiatorPick:
    """Результат подбора прибора отопления."""
    model: RadiatorModel
    sections: int                          # для секционных — сколько секций
    actual_power_w: float                  # фактическая Q при графике
    margin_pct: float                      # запас (Q_факт − Q_нужно)/Q_нужно
    note: str = ""


def select_radiator(
    required_power_w: float,
    t_supply: float = 80.0,
    t_return: float = 60.0,
    t_room: float = 20.0,
    *,
    family_filter: Optional[List[str]] = None,
    catalog: Optional[List[RadiatorModel]] = None,
    use_log_mean: bool = True,
    prefer_sectional: bool = False,
    min_margin: float = 0.0,
    max_margin: float = 0.50,
) -> Optional[RadiatorPick]:
    """Подбор одного отопительного прибора под требуемую нагрузку.

    Логика:
        - Для не-секционных: ищет модель в каталоге, чьё actual_power_w
          ближе всех к required_power_w сверху (с минимальным запасом).
        - Для секционных: считает число секций как ceil(Q/q_секции) и
          проверяет, не превышено ли max_sections.

    Параметры
    ---------
    family_filter      : список названий семейств (None — все)
    catalog            : альтернативный список моделей (по умолчанию глобальный)
    prefer_sectional   : True — приоритет секционных (более гибкий подбор)
    min_margin         : минимальный запас, доля (0.05 = +5%)
    max_margin         : максимально допустимый запас (1.00 = +100% — отказ)
    """
    cat = catalog if catalog is not None else RADIATOR_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]
    if not cat:
        return None

    candidates: List[RadiatorPick] = []
    for m in cat:
        q_unit = m.actual_power_w(t_supply, t_return, t_room,
                                    use_log_mean=use_log_mean)
        if q_unit <= 0:
            continue
        if m.is_sectional:
            need = math.ceil(required_power_w / q_unit * (1.0 + min_margin))
            if need > m.max_sections:
                continue
            need = max(need, 2)            # минимум 2 секции
            q_total = q_unit * need
        else:
            need = 1
            q_total = q_unit
            if q_total < required_power_w * (1.0 + min_margin):
                continue
        margin = (q_total - required_power_w) / required_power_w
        if margin > max_margin:
            continue
        candidates.append(RadiatorPick(
            model=m, sections=need,
            actual_power_w=q_total,
            margin_pct=margin * 100.0,
        ))

    if not candidates:
        return None

    # Предпочтения:
    # 1) prefer_sectional — секционные первыми
    # 2) Минимальный запас
    def _key(p: RadiatorPick):
        sec_priority = 0 if (prefer_sectional and p.model.is_sectional) else 1
        return (sec_priority, p.margin_pct)

    candidates.sort(key=_key)
    return candidates[0]


def select_radiators_for_spaces(
    spaces,
    t_supply: float = 80.0,
    t_return: float = 60.0,
    *,
    family_filter: Optional[List[str]] = None,
    prefer_sectional: bool = False,
) -> dict:
    """Подбор приборов для каждого помещения проекта.

    spaces : итерируемое из Space (используется space.heat_loss_w, t_in_heat).

    Возвращает {space_id: RadiatorPick | None}.
    """
    result: Dict[str, Optional[RadiatorPick]] = {}
    for sp in spaces:
        q = getattr(sp, "heat_loss_w", 0.0)
        if q <= 0:
            result[getattr(sp, "space_id", "")] = None
            continue
        t_room = getattr(sp, "t_in_heat", 20.0)
        pick = select_radiator(
            q, t_supply=t_supply, t_return=t_return, t_room=t_room,
            family_filter=family_filter, prefer_sectional=prefer_sectional,
        )
        result[getattr(sp, "space_id", "")] = pick
    return result
