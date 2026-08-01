# -*- coding: utf-8 -*-
"""Переклассификация типов помещений и пересчёт вентиляции по нормам.

Запускает авто-определение типа (auto_detect_room_type) для помещений проекта,
применяет тепловые дефолты нового типа и пересчитывает вентиляцию по справочнику
норм (ШНҚ 2.08.02-23 / СП). По умолчанию трогает только помещения с типом
«Прочее»; помещения с ручной правкой (user_modified / vent_user_modified) не
изменяются.

Использование (из корня репозитория D:\\HVAC):
    python tools/reclassify_room_types.py ALL-BLOCKS.hvac.json
    python tools/reclassify_room_types.py ALL-BLOCKS.hvac.json --dry   # без записи
    python tools/reclassify_room_types.py ALL-BLOCKS.hvac.json --all   # все типы, не только Прочее

Перед записью создаётся резервная копия <path>.bak-YYYYMMDDHHMMSS.
"""
from __future__ import annotations

import collections
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hvac.project import HVACProject                                    # noqa: E402
from hvac.io_json import load_project, save_project                     # noqa: E402
from hvac.catalogs.room_types import (                                  # noqa: E402
    auto_detect_room_type, apply_room_type_defaults,
)


def reclassify(path: str, only_prochee: bool = True, dry: bool = False,
               thermal: bool = False, force: bool = False) -> None:
    proj = HVACProject()
    load_project(proj, path)

    before = collections.Counter(sp.room_type for sp in proj.spaces)
    sup0 = sum(sp.supply_m3h for sp in proj.spaces)
    exh0 = sum(sp.exhaust_m3h for sp in proj.spaces)

    changed = 0
    for sp in proj.spaces:
        # --force: переклассифицировать даже помещения с ручной правкой
        # (user_modified). Ручной расход (vent_user_modified) вентиляция всё
        # равно не перетрёт — это контролирует calculate_ventilation.
        if sp.user_modified and not force:
            continue
        if only_prochee and sp.room_type != "Прочее":
            continue
        nt = auto_detect_room_type(sp.name)
        if nt != sp.room_type:
            sp.room_type = nt
            apply_room_type_defaults(sp)
            changed += 1

    # По умолчанию — только вентиляция (задача «по вентиляции»). Полный пересчёт
    # теплопотерь у переклассифицированных делается опционально (--thermal):
    # recalculate() не идемпотентен (исправляет латентный рассинхрон площадей в
    # self-contained JSON) и сдвинул бы теплопотери у нескольких НЕзатронутых
    # помещений — поэтому по умолчанию тепло не трогаем, пересчёт в приложении.
    if thermal:
        proj.recalculate()
    proj.calculate_ventilation()

    after = collections.Counter(sp.room_type for sp in proj.spaces)
    sup1 = sum(sp.supply_m3h for sp in proj.spaces)
    exh1 = sum(sp.exhaust_m3h for sp in proj.spaces)

    print(f"Помещений: {len(proj.spaces)} | переклассифицировано: {changed}")
    print(f"Приток  Σ: {sup0:>13,.0f} → {sup1:>13,.0f} м³/ч")
    print(f"Вытяжка Σ: {exh0:>13,.0f} → {exh1:>13,.0f} м³/ч")
    print("Изменение распределения типов:")
    for t in sorted(set(before) | set(after)):
        d = after[t] - before[t]
        if d:
            print(f"  {after[t]:5d}  {t:28s} ({d:+d})")

    if dry:
        print("\n[dry-run] файл НЕ изменён.")
        return

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = f"{path}.bak-{stamp}"
    shutil.copy2(path, bak)
    save_project(proj, path, force_self_contained=True)
    print(f"\nСохранено: {path}\nБэкап:     {bak}")


if __name__ == "__main__":
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not pos:
        print(__doc__)
        sys.exit(1)
    reclassify(pos[0], only_prochee="--all" not in flags, dry="--dry" in flags,
               thermal="--thermal" in flags, force="--force" in flags)
