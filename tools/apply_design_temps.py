# -*- coding: utf-8 -*-
"""Проталкивает расчётные температуры из справочника типов в помещения проекта
и пересчитывает тепло + вентиляцию.

Источник температур — design criteria заказчика (гостиничный комплекс):
Summer → t_in_cool, Winter → t_in_heat. Значения уже внесены в
hvac/catalogs/data/room_types.json для типов из CHANGED ниже.

Обновляются только t_in_heat / t_in_cool у помещений изменённых типов и без
ручной правки (user_modified). Занятость/освещение/оборудование НЕ трогаются.

Использование (из корня D:\\HVAC):
    python tools/apply_design_temps.py ALL-BLOCKS.hvac.json [--dry]
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hvac.project import HVACProject                          # noqa: E402
from hvac.io_json import load_project, save_project           # noqa: E402
from hvac.catalogs.room_types import ROOM_TYPE_PRESETS        # noqa: E402

# Типы, чьи температуры заданы по таблице заказчика (см. docstring).
CHANGED = {
    "Гостиничный номер", "Вестибюль", "Коридор", "Конференц-зал",
    "Магазин / торговля", "Офис", "Гардероб", "Раздевалка",
    "Ресторан / кухня", "Горячий цех", "Холодный цех",
    "Мусорокамера", "Прачечная",
}


def apply_temps(path: str, dry: bool = False) -> None:
    proj = HVACProject()
    load_project(proj, path)

    hl0 = sum(s.heat_loss_w for s in proj.spaces)
    hg0 = sum(s.heat_gain_w for s in proj.spaces)

    n = 0
    for sp in proj.spaces:
        if sp.user_modified or sp.room_type not in CHANGED:
            continue
        pre = ROOM_TYPE_PRESETS.get(sp.room_type)
        if pre and (sp.t_in_heat != pre["t_in_heat"]
                    or sp.t_in_cool != pre["t_in_cool"]):
            sp.t_in_heat = pre["t_in_heat"]
            sp.t_in_cool = pre["t_in_cool"]
            n += 1

    proj.recalculate()            # теплопотери/поступления по новым t
    proj.calculate_ventilation()  # вентиляция (t влияет на влагоудаление бассейна)

    hl1 = sum(s.heat_loss_w for s in proj.spaces)
    hg1 = sum(s.heat_gain_w for s in proj.spaces)

    print(f"Обновлено температур: {n}")
    print(f"Теплопотери  Σ: {hl0/1000:>11,.1f} → {hl1/1000:>11,.1f} кВт")
    print(f"Теплопоступл Σ: {hg0/1000:>11,.1f} → {hg1/1000:>11,.1f} кВт")

    if dry:
        print("\n[dry-run] файл НЕ изменён.")
        return

    bak = f"{path}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(path, bak)
    save_project(proj, path, force_self_contained=True)
    print(f"\nСохранено: {path}\nБэкап:     {bak}")


if __name__ == "__main__":
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not pos:
        print(__doc__)
        sys.exit(1)
    apply_temps(pos[0], dry="--dry" in sys.argv[1:])
