# -*- coding: utf-8 -*-
"""Экспорт результатов расчёта в CSV для обратной записи в параметры
Revit Spaces/Rooms через Dynamo-скрипт revit_dynamo_apply_results.py.

Полный инженерный набор: нагрузки (отопление/охлаждение, явная/скрытая),
вентиляция (приток/вытяжка/кратность), расчётные температуры и имена
обслуживающих систем и контуров.

REVIT_FIELDS — единый контракт колонок: имя колонки CSV, рекомендованное
имя параметра Revit, тип значения и функция-извлекатель из Space.
Dynamo-скрипт apply использует тот же перечень имён параметров, поэтому в
проекте Revit достаточно создать Project Parameters категории Spaces/Rooms
с указанными именами:
  • числовые поля (kind != "text") → параметр типа «Число» (Number);
  • текстовые поля (имена систем/контуров) → параметр типа «Текст» (Text).
"""

from __future__ import annotations

import csv
from typing import Callable, List, Tuple

from hvac.models import Space
from hvac.project import HVACProject

# (csv_column, revit_param, kind, accessor)
#   kind: "power" | "flow" | "temp" | "ach" | "text"
REVIT_FIELDS: List[Tuple[str, str, str, Callable[[Space], object]]] = [
    ("heating_load_w",     "Heating Load",       "power", lambda s: round(s.heat_loss_w, 1)),
    ("cooling_load_w",     "Cooling Load",       "power", lambda s: round(s.heat_gain_w, 1)),
    ("cooling_sensible_w", "Cooling Sensible Load", "power", lambda s: round(s.heat_gain_sensible_w, 1)),
    ("cooling_latent_w",   "Cooling Latent Load",   "power", lambda s: round(s.heat_gain_latent_w, 1)),
    ("supply_m3h",         "Supply Airflow",     "flow",  lambda s: round(s.supply_m3h, 1)),
    ("exhaust_m3h",        "Exhaust Airflow",    "flow",  lambda s: round(s.exhaust_m3h, 1)),
    ("ach",                "Air Changes",        "ach",   lambda s: round(s.ach_calculated, 2)),
    ("t_in_heat",          "Heating Setpoint",   "temp",  lambda s: round(s.t_in_heat, 1)),
    ("t_in_cool",          "Cooling Setpoint",   "temp",  lambda s: round(s.t_in_cool, 1)),
    ("system_heating",     "Heating System",     "text",  lambda s: s.system_heating),
    ("system_cooling",     "Cooling System",     "text",  lambda s: s.system_cooling),
    ("system_ventilation", "Ventilation System", "text",  lambda s: s.system_ventilation),
    ("circuit_heating",    "Heating Circuit",    "text",  lambda s: s.circuit_heating),
    ("circuit_cooling",    "Cooling Circuit",    "text",  lambda s: s.circuit_cooling),
    ("duct_zone",          "Duct Zone",          "text",  lambda s: s.duct_zone),
]

# Колонки-идентификаторы помещения (не пишутся в параметры, нужны для привязки)
ID_COLUMNS = ["space_id", "space_number", "space_name"]


def csv_header() -> List[str]:
    """Заголовок CSV: идентификаторы + поля результатов."""
    return ID_COLUMNS + [col for col, _param, _kind, _acc in REVIT_FIELDS]


def export_results_for_revit(project: HVACProject, path: str) -> None:
    """Сохраняет полный набор результатов расчёта в CSV для импорта в Revit."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(csv_header())
        for sp in project.spaces:
            row: list[object] = [sp.space_id, sp.number, sp.name]
            for _col, _param, _kind, accessor in REVIT_FIELDS:
                row.append(accessor(sp))
            w.writerow(row)
