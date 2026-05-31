# -*- coding: utf-8 -*-
"""Командный режим (без GUI). Для пакетной обработки и тестов."""

from __future__ import annotations
import sys

from hvac.project import HVACProject
from hvac.io_excel import export_to_excel


def run_cli(spaces_csv: str, thermal_csv: str, output_xlsx: str,
            t_out_heating: float = -16.0, t_out_cooling: float = 36.0,
            project_name: str = "Проект", city: str = "") -> HVACProject:
    """Загружает CSV, считает, сохраняет в xlsx. Возвращает проект."""
    project = HVACProject()
    project.params.project_name = project_name
    if city and project.params.apply_city(city):
        print(f"Применён климат города: {city}")
    else:
        project.params.t_out_heating = t_out_heating
        project.params.t_out_cooling = t_out_cooling
    project.load(spaces_csv, thermal_csv)
    project.recalculate()
    export_to_excel(project, output_xlsx)
    total_loss = sum(s.heat_loss_w for s in project.spaces)
    total_gain = sum(s.heat_gain_w for s in project.spaces)
    total_area = sum(s.area_m2 for s in project.spaces)
    print(f"Помещений: {len(project.spaces)}, площадь: {total_area:.1f} м²")
    print(f"Σ Теплопотери:     {total_loss/1000:8.2f} кВт"
          f"   ({total_loss/total_area if total_area else 0:.1f} Вт/м²)")
    print(f"Σ Теплопоступл.:   {total_gain/1000:8.2f} кВт"
          f"   ({total_gain/total_area if total_area else 0:.1f} Вт/м²)")
    print(f"Файл результатов: {output_xlsx}")
    return project


def main():
    if len(sys.argv) < 4:
        print("Использование: python -m hvac.cli spaces.csv thermal.csv result.xlsx "
              "[t_зим] [t_лет] [город]")
        sys.exit(1)
    run_cli(sys.argv[1], sys.argv[2], sys.argv[3],
            t_out_heating=float(sys.argv[4]) if len(sys.argv) > 4 else -16.0,
            t_out_cooling=float(sys.argv[5]) if len(sys.argv) > 5 else 36.0,
            city=sys.argv[6] if len(sys.argv) > 6 else "")


if __name__ == "__main__":
    main()
