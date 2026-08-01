#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Восстановление привязок помещений к системам в текущий проект из предшественника.

Источник:  ALL-BLOCKS_fixed.hvac.json            (есть полные привязки, тот же space_id)
Цель:      ALL-BLOCKS_fixed_2026-06-22.hvac.json (привязки обнулены)

Переносит ТОЛЬКО 3 поля: system_ventilation / system_heating / system_cooling
(сопоставление по space_id — наборы id идентичны 4272/4272). Нагрузки, типы,
вентиляция, геометрия текущего файла НЕ трогаются.

После переноса удаляет ПУСТЫЕ системы (0 помещений) из словарей систем
(ventilation_systems + парный ahu_loads, heating_systems, cooling_systems).

Запуск:  python restore_systems.py [--dry]
"""
import json, os, sys, shutil
from collections import Counter

# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")
SRC = os.path.join(HERE, "ALL-BLOCKS_fixed.hvac.json")
SYS_FIELDS = ("system_ventilation", "system_heating", "system_cooling")
DRY = "--dry" in sys.argv


def main():
    dst = json.load(open(DST, encoding="utf-8"))
    src = json.load(open(SRC, encoding="utf-8"))

    src_by_id = {s["space_id"]: s for s in src["spaces"]}
    dst_ids = {s["space_id"] for s in dst["spaces"]}
    missing = [sid for sid in dst_ids if sid not in src_by_id]
    print("dst spaces=%d | src spaces=%d | dst ids missing in src=%d"
          % (len(dst["spaces"]), len(src["spaces"]), len(missing)))

    # --- 1) перенос 3 полей по space_id ---
    rooms_changed = 0
    field_writes = 0
    no_src = 0
    for s in dst["spaces"]:
        ss = src_by_id.get(s["space_id"])
        if ss is None:
            no_src += 1
            continue
        ch = False
        for f in SYS_FIELDS:
            if s.get(f) != ss.get(f, ""):
                if not DRY:
                    s[f] = ss.get(f, "")
                field_writes += 1
                ch = True
        if ch:
            rooms_changed += 1
    print("rooms changed=%d | field writes=%d | dst rooms without src=%d"
          % (rooms_changed, field_writes, no_src))

    # assignment coverage after (use src values in dry mode for accurate preview)
    def cur_val(s, f):
        if DRY:
            ss = src_by_id.get(s["space_id"])
            return ss.get(f, "") if ss else s.get(f, "")
        return s.get(f, "")
    for f in SYS_FIELDS:
        n = sum(1 for s in dst["spaces"] if cur_val(s, f))
        print("  coverage %s: %d/%d" % (f, n, len(dst["spaces"])))

    # --- 2) удалить пустые системы (0 помещений) ---
    print("\n-- empty systems (defined but 0 rooms) --")
    used = {f: Counter(cur_val(s, f) for s in dst["spaces"] if cur_val(s, f)) for f in SYS_FIELDS}
    plans = [
        ("ventilation_systems", "system_ventilation", "ahu_loads"),
        ("heating_systems", "system_heating", None),
        ("cooling_systems", "system_cooling", None),
    ]
    total_removed = 0
    for cat, fld, paired in plans:
        d = dst.get(cat, {}) or {}
        u = used[fld]
        empty = [name for name in d if u.get(name, 0) == 0]
        orphan = [name for name in u if name not in d]
        print("  %-20s defined=%d used=%d EMPTY=%d %s%s"
              % (cat, len(d), len([x for x in d if u.get(x, 0) > 0]), len(empty),
                 empty if empty else "",
                 ("  ORPHANS=%s" % orphan) if orphan else ""))
        if not DRY:
            for name in empty:
                d.pop(name, None)
                if paired and paired in dst and isinstance(dst[paired], dict):
                    dst[paired].pop(name, None)
            total_removed += len(empty)
    print("total empty systems removed: %d" % (0 if DRY else total_removed))

    if DRY:
        print("\n(dry run — файл не тронут)")
        return

    bak = DST + ".bak_before_sysrestore"
    if not os.path.exists(bak):
        shutil.copy2(DST, bak)
        print("\nBackup -> %s" % bak)
    else:
        print("\nBackup уже существует: %s" % bak)

    text = json.dumps(dst, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    with open(DST, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Written -> %s" % DST)


if __name__ == "__main__":
    main()
