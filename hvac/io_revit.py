# -*- coding: utf-8 -*-
"""Экспорт результатов в CSV для обратной записи в Revit Spaces
через Dynamo-скрипт revit_dynamo_apply_results.py."""

from __future__ import annotations
import csv
from hvac.project import HVACProject


def export_results_for_revit(project: HVACProject, path: str) -> None:
    """Сохраняет результаты расчёта в CSV для импорта в Revit."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["space_id", "space_number", "space_name",
                    "heating_load_w", "cooling_load_w"])
        for sp in project.spaces:
            w.writerow([sp.space_id, sp.number, sp.name,
                        round(sp.heat_loss_w, 1),
                        round(sp.heat_gain_w, 1)])
