# -*- coding: utf-8 -*-
"""Миграция: обновить геометрию ограждений в существующем проекте на
исправленную (чистый витраж + геом внутр.стены + площади), СОХРАНИВ все
системы/зоны/настройки/климат/конструкции. Пишет КОПИЮ, оригинал не трогает.

Как: грузит проект (self-contained, со всеми системами) → пересчитывает со
СТАРОЙ геометрией (база для diff) → заменяет P.elements на свежие из
thermal_all.csv (тот же data_loader, что и импорт) → пересчитывает →
сохраняет копию. Помещения (с системами) НЕ трогаются — меняются только
ограждения. Отчёт изменений по помещениям/блокам.

Запуск: C:\\Python314\\python.exe D:\\HVAC\\tools\\migrate_geometry.py
"""
import collections
import csv
import os
import sys

sys.path.insert(0, r"D:\HVAC")
sys.path.insert(0, r"D:\HVAC\tools")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json, data_loader  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

SRC = r"D:\HVAC\ALL-BLOCKS.hvac.json"
DST = r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json"
THERMAL = r"D:\HVAC\thermal_all.csv"


def snapshot(P):
    d = {}
    for s in P.spaces:
        ext = [e for e in P.elements_for(s.space_id) if e.is_exterior]
        glaz = sum(e.net_area_m2 or 0 for e in ext
                   if "витраж" in (e.family or "").lower())
        wall = sum(e.net_area_m2 or 0 for e in ext
                   if "витраж" not in (e.family or "").lower())
        d[s.space_id] = (s.heat_loss_w, s.heat_gain_w, glaz, wall)
    return d


def systems_fingerprint(P):
    return (sum(1 for s in P.spaces if s.system_heating),
            sum(1 for s in P.spaces if s.system_cooling),
            sum(1 for s in P.spaces if s.system_ventilation),
            len(P.ventilation_systems), len(P.heating_systems),
            len(P.cooling_systems))


def main():
    print("Загружаю проект:", SRC)
    P = HVACProject()
    io_json.load_project(P, SRC)
    sysf_before = systems_fingerprint(P)

    # База: пересчёт со СТАРОЙ (ручной) геометрией
    P.recalculate()
    before = snapshot(P)
    loss_b = sum(s.heat_loss_w for s in P.spaces) / 1000.0
    gain_b = sum(s.heat_gain_w for s in P.spaces) / 1000.0

    # Замена геометрии ограждений на исправленную (помещения не трогаем!)
    new_elems = data_loader.load_thermal(THERMAL, P.spaces)
    P.elements = P._dedup_openings(new_elems)
    P._invalidate_elements_index()
    P.recalculate()
    after = snapshot(P)
    loss_a = sum(s.heat_loss_w for s in P.spaces) / 1000.0
    gain_a = sum(s.heat_gain_w for s in P.spaces) / 1000.0
    sysf_after = systems_fingerprint(P)

    # Сохранение КОПИИ (оригинал не трогаем)
    io_json.save_project(P, DST, force_self_contained=True)

    # Отчёт по помещениям
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    rep = os.path.join(out_dir, "migration_diff_by_space.csv")
    sp_by_id = {s.space_id: s for s in P.spaces}
    blk = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    with open(rep, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["space_id", "number", "name", "block",
                    "loss_before_W", "loss_after_W", "gain_before_W",
                    "gain_after_W", "glaz_before_m2", "glaz_after_m2",
                    "wall_before_m2", "wall_after_m2"])
        for sid, (lb, gb, glb, wlb) in before.items():
            la, ga, gla, wla = after.get(sid, (0, 0, 0, 0))
            s = sp_by_id.get(sid)
            b = rec.block_of_space(s.level if s else "", s.number if s else "")
            blk[b][0] += lb / 1000.0
            blk[b][1] += la / 1000.0
            blk[b][2] += gb / 1000.0
            blk[b][3] += ga / 1000.0
            w.writerow([sid, s.number if s else "", s.name if s else "", b,
                        round(lb), round(la), round(gb), round(ga),
                        round(glb, 1), round(gla, 1),
                        round(wlb, 1), round(wla, 1)])

    print("\n=== СИСТЕМЫ (должны совпасть до/после) ===")
    print("  до:    отоп/охл/вент назнач =", sysf_before[:3],
          " систем =", sysf_before[3:])
    print("  после: отоп/охл/вент назнач =", sysf_after[:3],
          " систем =", sysf_after[3:])
    print("  СИСТЕМЫ СОХРАНЕНЫ" if sysf_before == sysf_after
          else "  !!! РАСХОЖДЕНИЕ В СИСТЕМАХ !!!")

    print("\n=== ЗДАНИЕ (кВт) ===")
    print("  теплопотери:    %.0f -> %.0f (%.0f%%)"
          % (loss_b, loss_a, 100 * (loss_a - loss_b) / loss_b if loss_b else 0))
    print("  теплопоступл.:  %.0f -> %.0f (%.0f%%)"
          % (gain_b, gain_a, 100 * (gain_a - gain_b) / gain_b if gain_b else 0))

    print("\n=== ПО БЛОКАМ (Qпот / Qпоступ, кВт) до -> после ===")
    for b in sorted(blk):
        v = blk[b]
        print("  %-5s  потери %7.0f -> %-7.0f  поступл %7.0f -> %-7.0f"
              % (b, v[0], v[1], v[2], v[3]))

    # HTL-039
    h = "750384"
    if h in before:
        lb, gb, glb, wlb = before[h]
        la, ga, gla, wla = after[h]
        print("\n=== HTL-039 ALL DAY DINING ===")
        print("  витраж м²:   %.1f -> %.1f" % (glb, gla))
        print("  глух.ст м²:  %.1f -> %.1f" % (wlb, wla))
        print("  Qпот Вт:     %.0f -> %.0f" % (lb, la))
        print("  Qпоступ Вт:  %.0f -> %.0f" % (gb, ga))

    print("\nСохранено (КОПИЯ, оригинал не тронут):", DST)
    print("Отчёт по помещениям:", rep)


if __name__ == "__main__":
    main()
