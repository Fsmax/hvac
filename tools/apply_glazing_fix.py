# -*- coding: utf-8 -*-
"""Собирает исправленный thermal_all из чистого остекления.

Берёт существующий thermal_all.csv, ВЫБРАСЫВАЕТ все строки навесных
стен (family содержит «Витраж»/curtain — фасад/перегородки/душевые/ядро,
все old-привязки), и ДОБАВЛЯЕТ чистые строки остекления из
glazing_clean.csv (geom-перепривязка, площадь поделена по фронту).

Глухие стены, спандрел (Базовая стена «Aluminium»), окна, двери, проёмы —
сохраняются без изменений.

Чистые строки помечаются function="curtain (orphan)" → загрузчик
доверяет им как фасаду (is_orphan_facade), минуя геометрические эвристики
bsc, которые иначе пометили бы поделённый по комнатам фасад внутренним.

Вывод: tools/out/fixed/thermal_all.csv (+ копия spaces.csv) — чтобы прогнать
reconcile_glazing.py на исправленных данных и сравнить флаги до/после.
"""
import csv
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
import reconcile_glazing as rec  # noqa: E402

THERMAL_HEADER = [
    "space_id", "space_number", "space_name", "space_level", "row_type",
    "is_exterior_wall", "element_id", "link_model", "category", "family",
    "type", "element_level", "boundary_length_m", "space_height_m",
    "approx_area_m2", "element_area", "thickness", "function",
    "thermal_value", "host_element_id", "boundary_space_count",
    "orientation_deg", "room_boundary_count",
]

UNCOND_PFX = ("OFC-", "BAL-", "TER-", "SHAFT")


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else _ROOT
    spaces_csv = os.path.join(folder, "spaces.csv")
    thermal_csv = os.path.join(folder, "thermal_all.csv")
    clean_csv = os.path.join(_HERE, "out", "glazing_clean.csv")

    spaces = rec.data_loader.load_spaces(spaces_csv)
    sp_by_id = {s.space_id: s for s in spaces}

    # 1) читаем старый thermal, выбрасываем все curtain-строки
    kept = []
    dropped = 0
    with open(thermal_csv, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            fam = (row.get("family", "") or "").lower()
            if "витраж" in fam or "curtain" in fam:
                dropped += 1
                continue
            kept.append(row)
    print("Старых строк сохранено:", len(kept), " выброшено витражных:", dropped)

    # 2) читаем чистое остекление → thermal-строки
    added = 0
    on_uncond = 0
    clean_rows = []
    with open(clean_csv, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            sid = row["space_id"].strip()
            sp = sp_by_id.get(sid)
            num = sp.number if sp else ""
            if (num or "").upper().startswith(UNCOND_PFX):
                on_uncond += 1
            area = row["area_m2"]
            clean_rows.append({
                "space_id": sid,
                "space_number": num,
                "space_name": sp.name if sp else "",
                "space_level": sp.level if sp else row.get("level", ""),
                "row_type": "external_wall",
                "is_exterior_wall": "yes",
                "element_id": row["element_id"],
                "link_model": row["source"],
                "category": "Стены",
                "family": "Витраж",
                "type": row["type"],
                "element_level": row.get("level", ""),
                "boundary_length_m": "",
                "space_height_m": "",
                "approx_area_m2": area,
                "element_area": area,
                "thickness": "",
                "function": "curtain (orphan)",
                "thermal_value": "",
                "host_element_id": "",
                "boundary_space_count": "1",
                "orientation_deg": row.get("orientation_deg", ""),
                "room_boundary_count": "0",
            })
            added += 1
    print("Чистых строк остекления добавлено:", added,
          " (из них на неотапл. помещениях:", on_uncond, ")")

    # 3) запись
    out_dir = os.path.join(_HERE, "out", "fixed")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    out_thermal = os.path.join(out_dir, "thermal_all.csv")
    with open(out_thermal, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=THERMAL_HEADER)
        w.writeheader()
        for row in kept:
            w.writerow({k: row.get(k, "") for k in THERMAL_HEADER})
        for row in clean_rows:
            w.writerow(row)
    shutil.copyfile(spaces_csv, os.path.join(out_dir, "spaces.csv"))
    print("Записано:", out_thermal)
    print("Прогон сверки: C:\\Python314\\python.exe tools\\reconcile_glazing.py",
          out_dir)


if __name__ == "__main__":
    main()
