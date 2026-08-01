#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тиражирование вентиляции типового этажа L11 HTL на L12..L25 HTL.

Переносит ТОЛЬКО 4 поля вентиляции (supply_m3h, exhaust_m3h, hood_m3h,
vent_user_modified). Нагрузки/температуры/системы/геометрия НЕ трогаются.

Сопоставление помещений (гибрид):
  1) по «хвосту» номера: HTL-12XX.y .. HTL-25XX.y  ->  HTL-11XX.y   (точно, квартиро-зависимо)
  2) иначе (битые номера HTL-2207.* и пр.) — по (имя, площадь округл. 0.1) к L11.
     Представитель группы (имя,площадь): значение из vmod=1 помещений (намеренно
     заданное пользователем), при их отсутствии — мода по всей группе.

Запуск:  python tile_l11_vent.py [--dry]
Файл:    ALL-BLOCKS_fixed_2026-06-22.hvac.json (перезапись, перед этим .bak)
"""
import json, re, sys, shutil, os
from collections import defaultdict, Counter

# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")
VENT_FIELDS = ("supply_m3h", "exhaust_m3h", "hood_m3h", "vent_user_modified")
DRY = "--dry" in sys.argv


def floornum(level):
    m = re.match(r"L(\d+) HTL", level or "")
    return int(m.group(1)) if m else None


def suffix(num, fn):
    pref = "HTL-%d" % fn
    return num[len(pref):] if num.startswith(pref) else None


def na_key(s):
    return (s["name"], round(s["area_m2"], 1))


def representative(rooms):
    """(supply, exhaust, hood, vmod) для группы (имя,площадь) — приоритет vmod=1."""
    pref = [r for r in rooms if r["vent_user_modified"]] or rooms
    c = Counter((r["supply_m3h"], r["exhaust_m3h"], r["hood_m3h"]) for r in pref)
    sup, exh, hood = c.most_common(1)[0][0]
    vmod = any(
        r["vent_user_modified"]
        for r in pref
        if (r["supply_m3h"], r["exhaust_m3h"], r["hood_m3h"]) == (sup, exh, hood)
    )
    return {"supply_m3h": sup, "exhaust_m3h": exh, "hood_m3h": hood,
            "vent_user_modified": vmod}


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        d = json.load(f)
    sp = d["spaces"]

    L11 = [s for s in sp if floornum(s["level"]) == 11]
    by_suf = {suffix(s["number"], 11): s for s in L11}
    by_na = defaultdict(list)
    for s in L11:
        by_na[na_key(s)].append(s)
    na_rep = {k: representative(v) for k, v in by_na.items()}

    stats = []
    rooms_changed = 0
    fields_changed = 0
    unmatched_rows = []

    for fn in range(12, 26):
        tgt = [s for s in sp if floornum(s["level"]) == fn]
        n_num = n_na = n_un = n_roomchg = 0
        for s in tgt:
            k = suffix(s["number"], fn)
            if k is not None and k in by_suf:
                src = by_suf[k]
                newvals = {fld: src[fld] for fld in VENT_FIELDS}
                n_num += 1
            else:
                rep = na_rep.get(na_key(s))
                if rep is None:
                    n_un += 1
                    unmatched_rows.append((s["level"], s["number"], s["name"], round(s["area_m2"], 1)))
                    continue
                newvals = rep
                n_na += 1
            changed_here = False
            for fld in VENT_FIELDS:
                if s.get(fld) != newvals[fld]:
                    if not DRY:
                        s[fld] = newvals[fld]
                    fields_changed += 1
                    changed_here = True
            if changed_here:
                n_roomchg += 1
                rooms_changed += 1
        stats.append((fn, len(tgt), n_num, n_na, n_un, n_roomchg))

    print("=== DRY-RUN ===" if DRY else "=== APPLY ===")
    print("Floor | total | by_num | by_na | UNMATCH | rooms_changed")
    for fn, tot, a, b, c, ch in stats:
        print("  L%-2d  | %4d  | %4d   | %4d  | %5d   | %d" % (fn, tot, a, b, c, ch))
    print("TOTAL rooms changed: %d | field-writes: %d | unmatched: %d"
          % (rooms_changed, fields_changed, len(unmatched_rows)))
    for r in unmatched_rows:
        print("   UNMATCHED:", r)

    if DRY:
        print("\n(dry run — файл не тронут)")
        return

    # backup (не перезаписываем существующий .bak)
    bak = SRC + ".bak_before_L11tile"
    if not os.path.exists(bak):
        shutil.copy2(SRC, bak)
        print("\nBackup -> %s" % bak)
    else:
        print("\nBackup уже существует, не перезаписываю: %s" % bak)

    text = json.dumps(d, ensure_ascii=False, indent=2)
    text = text.replace("\n", "\r\n")  # CRLF как в оригинале (raw \n в строках не бывает — json их экранирует)
    with open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Written -> %s" % SRC)


if __name__ == "__main__":
    main()
