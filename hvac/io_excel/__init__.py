# -*- coding: utf-8 -*-
"""Экспорт результатов расчёта в многолистовой Excel-файл.

Монолит разбит на группы листов (см. _core / _extensions / _detailed);
общие стили и помощники — в _common. Публичный API без изменений:
    from hvac.io_excel import export_to_excel
"""
from __future__ import annotations

from hvac.project import HVACProject
from hvac.io_excel._core import write_core_sheets
from hvac.io_excel._extensions import write_extension_sheets
from hvac.io_excel._detailed import write_detailed_sheets

__all__ = ["export_to_excel"]


def export_to_excel(project: HVACProject, path: str) -> None:
    """Сохраняет результаты расчёта в xlsx (листы — по подмодулям групп)."""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise RuntimeError("Не установлен openpyxl. Выполните: pip install openpyxl")

    wb = Workbook()
    write_core_sheets(wb, project)
    write_extension_sheets(wb, project)
    write_detailed_sheets(wb, project)
    wb.save(path)
