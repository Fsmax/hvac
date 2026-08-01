# -*- coding: utf-8 -*-
"""Сверка остекления/ограждений: живой Revit (эталон) ↔ что грузит программа.

Делает два уровня контроля, чтобы тысячи помещений можно было проверять
списком, а не глазами:

1) ПО БЛОКАМ (HTL/OFF/RES/BMG/...): сколько фасадного остекления есть в
   живой модели (через мост, инвентаризация по всем связям) против того,
   сколько реально попадает в расчёт (data_loader поверх thermal_all.csv).
   Большая «дельта» = стекло теряется на выгрузке/привязке.

2) ПО ПОМЕЩЕНИЯМ: для каждого Space — площадь Revit, наружная глухая
   площадь, фасадное остекление в расчёте, разбивка источника (ARC/FCD),
   и ФЛАГИ аномалий:
     NO_ENVELOPE   — у помещения нет ни одной наружной грани (внутреннее
                     ИЛИ фасад потерян при привязке);
     LEAK          — внутренний витраж (перегородка/душевая/ядро) посчитан
                     как наружный фасад;
     DROPPED       — фасадный витраж demoted во внутренний (возможна
                     потеря остекления у фасадной комнаты);
     DOUBLE_SRC    — остекление пришло И из ARC, И из FCD (двойной учёт);
     AREA_OVEREST  — approx-площадь (длина×высота) завышает реальную >1.5×;
     BIG_GLAZ      — остекление > 2× площади пола (подозрительно).

Вывод: tools/out/glazing_by_block.csv, glazing_by_space.csv + сводка в консоль.

Запуск (Revit открыт, мост 8080):
  C:\\Python314\\python.exe D:\\HVAC\\tools\\reconcile_glazing.py
По умолчанию читает D:\\HVAC\\spaces.csv + thermal_all.csv. Другая папка:
  ... reconcile_glazing.py D:\\HVAC\\new
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from hvac import data_loader  # noqa: E402
import bridge_glazing_inventory as inv  # noqa: E402
from hvac import revit_link as rl  # noqa: E402


# ---------- классификация остекления по имени типа/семейства ----------

INTERIOR_KW = (
    "interior", "partition", "перегород", "внутрен",
    "separator", "разделит", "empty", "not defined", "_not", "tbv",
    "shower", "душ", "кабин", "cabin", "core",
    "balustrade", "balustr", "ограждени", "перил",
)
FACADE_KW = (
    "storefront", "витрин", "facade", "фасад",
    "balcony", "балкон", "loggia", "лоджия",
    "glazing", "glz", "mullion", "glass", "стекл", "витраж", "glaz",
)
SPANDREL_KW = ("alumin", "spandrel", "спандрел", "facade slab")


def classify(family: str, type_name: str, kind: str = "") -> str:
    """facade | interior | spandrel | opaque (по имени)."""
    full = (str(family) + " " + str(type_name)).lower()
    is_curtain = ("витраж" in full or "curtain" in full or kind == "Curtain")
    # внутренний витраж проверяем РАНЬШЕ — перегородка/душевая/ядро не фасад
    if is_curtain and any(k in full for k in INTERIOR_KW):
        return "interior"
    if is_curtain or any(k in full for k in FACADE_KW):
        # спандрел из ключевых слов фасада не должен перебивать стекло,
        # но чистый алюм-спандрел (не curtain) — отдельно
        if not is_curtain and any(k in full for k in SPANDREL_KW):
            return "spandrel"
        return "facade"
    if any(k in full for k in SPANDREL_KW):
        return "spandrel"
    return "opaque"


def block_of_link(link: str) -> str:
    for b in ("HTL", "OFF", "RES", "BMG", "GRD", "LND", "STR", "Z01"):
        if "-%s-" % b in link or link.endswith(b):
            return b
    return "?"


def source_of_link(link: str) -> str:
    if "-ARC-" in link:
        return "ARC"
    if "-FCD-" in link:
        return "FCD"
    if not link:
        return "MAIN"
    return "OTH"


def block_of_space(level: str, number: str = "") -> str:
    """Блок по имени уровня (надёжно: 'L02 HTL (FFL)', 'GFL OFF (FFL)',
    'B1 (FFL)'), с откатом на префикс номера."""
    lv = (level or "").upper()
    for b in ("HTL", "OFF", "RES"):
        if b in lv:
            return b
    if lv.startswith("B") and "(FFL)" in lv:   # B1/B2 (FFL) — подвал/подиум
        return "BMG"
    nu = (number or "").upper()
    for b in ("HTL", "OFF", "RES"):
        if nu.startswith(b):
            return b
    if nu.startswith(("B01", "B0", "B1", "B2", "BMG", "GFL-G", "OFC-")):
        return "BMG"
    return "?"


def area_of(el) -> float:
    """Площадь элемента: element_area если есть, иначе approx."""
    a = el.element_area_m2 or 0.0
    if a > 0:
        return a
    return el.approx_area_m2 or 0.0


# ---------- живая инвентаризация по блокам ----------

def live_inventory_by_block():
    """{block: {'facade': m2, 'spandrel': m2, 'interior': m2}} из живого Revit."""
    print("Тяну инвентаризацию остекления из живой модели (мост 8080)...")
    res = rl.send_code(inv.CS, transaction_mode="none", timeout=180)
    text = res if isinstance(res, str) else str(res)
    out = {}
    links_seen = {}
    for ln in text.splitlines():
        if ln.startswith("#LINK"):
            p = ln.split("||")
            if len(p) >= 4:
                links_seen[p[1]] = (p[2], p[3])
            continue
        if not ln.startswith("G||"):
            continue
        p = ln.split("||")
        # G || link || kind || fam || type || count || area
        if len(p) < 7:
            continue
        link, kind, fam, typ = p[1], p[2], p[3], p[4]
        try:
            area = float(p[6])
        except Exception:
            area = 0.0
        block = block_of_link(link)
        src = source_of_link(link)
        cat = classify(fam, typ, kind)
        d = out.setdefault(block, {"facade": 0.0, "spandrel": 0.0,
                                   "interior": 0.0, "opaque": 0.0,
                                   "facade_ARC": 0.0, "facade_FCD": 0.0})
        d[cat] = d.get(cat, 0.0) + area
        if cat == "facade":
            d["facade_%s" % src] = d.get("facade_%s" % src, 0.0) + area
    return out, links_seen


# ---------- сверка по помещениям ----------

def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else _ROOT
    spaces_csv = os.path.join(folder, "spaces.csv")
    thermal_csv = os.path.join(folder, "thermal_all.csv")
    print("Папка данных:", folder)

    spaces = data_loader.load_spaces(spaces_csv)
    elems = data_loader.load_thermal(thermal_csv, spaces)
    sp_by_id = {s.space_id: s for s in spaces}
    print("Помещений:", len(spaces), " элементов ограждений:", len(elems))

    # группируем элементы по space_id
    by_space = {}
    for el in elems:
        by_space.setdefault(el.space_id, []).append(el)

    rows = []
    flag_counts = {}
    for s in spaces:
        els = by_space.get(s.space_id, [])
        opaque_ext = glaz_fac = glaz_arc = glaz_fcd = 0.0
        leak = dropped = overest = 0.0
        n_ext = 0
        for el in els:
            link = ""
            # link_model нет в BoundaryElement — источник берём из family/type
            cat = classify(el.family, el.type_name)
            a = area_of(el)
            ap = el.approx_area_m2 or 0.0
            em = el.element_area_m2 or 0.0
            if el.is_exterior:
                n_ext += 1
                if ap > 0 and em > 0 and ap > 1.5 * em:
                    overest += (ap - em)
                if cat in ("facade",):
                    glaz_fac += a
                elif cat == "interior":
                    leak += a
                else:
                    opaque_ext += a
            else:
                if cat == "facade":
                    dropped += a
        # источник остекления (ARC/FCD) по имени типа недоступен — оценим
        # по типам: M_Exterior Glazing/GLZ-* = ARC, CHR_Balcony/Storefront = FCD
        for el in els:
            if not el.is_exterior:
                continue
            t = (el.type_name or "").lower()
            if classify(el.family, el.type_name) != "facade":
                continue
            a = area_of(el)
            if "balcony" in t or "storefront" in t or "балкон" in t:
                glaz_fcd += a
            elif "glazing" in t or t.startswith("glz") or "glz-" in t \
                    or "exterior glazing" in t:
                glaz_arc += a

        area_rev = s.area_m2 or 0.0
        envelope = opaque_ext + glaz_fac
        wwr = (glaz_fac / envelope) if envelope > 0 else 0.0

        flags = []
        if area_rev > 5 and envelope <= 0.01:
            flags.append("NO_ENVELOPE")
        if leak > 2:
            flags.append("LEAK")
        if dropped > 2:
            flags.append("DROPPED")
        if glaz_arc > 1 and glaz_fcd > 1:
            flags.append("DOUBLE_SRC")
        if overest > 5:
            flags.append("AREA_OVEREST")
        if area_rev > 1 and glaz_fac > 2 * area_rev:
            flags.append("BIG_GLAZ")
        for f in flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

        rows.append({
            "space_id": s.space_id, "number": s.number, "name": s.name,
            "level": s.level, "block": block_of_space(s.level, s.number),
            "area_revit_m2": round(area_rev, 2),
            "n_ext": n_ext,
            "opaque_ext_m2": round(opaque_ext, 2),
            "glaz_facade_m2": round(glaz_fac, 2),
            "glaz_arc_m2": round(glaz_arc, 2),
            "glaz_fcd_m2": round(glaz_fcd, 2),
            "leak_interior_m2": round(leak, 2),
            "dropped_facade_m2": round(dropped, 2),
            "area_overest_m2": round(overest, 2),
            "wwr": round(wwr, 2),
            "flags": ";".join(flags),
        })

    # ---- запись по помещениям ----
    out_dir = os.path.join(_HERE, "out")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    import csv
    cols = ["space_id", "number", "name", "level", "block", "area_revit_m2",
            "n_ext", "opaque_ext_m2", "glaz_facade_m2", "glaz_arc_m2",
            "glaz_fcd_m2", "leak_interior_m2", "dropped_facade_m2",
            "area_overest_m2", "wwr", "flags"]
    sp_path = os.path.join(out_dir, "glazing_by_space.csv")
    with open(sp_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        # сначала помеченные, по убыванию суммарной аномальной площади
        def sev(r):
            return (len(r["flags"]) > 0,
                    r["leak_interior_m2"] + r["dropped_facade_m2"]
                    + r["area_overest_m2"])
        for r in sorted(rows, key=sev, reverse=True):
            w.writerow(r)

    # ---- по блокам: calc ----
    calc = {}
    for r in rows:
        b = r["block"]
        d = calc.setdefault(b, {"facade": 0.0, "opaque": 0.0,
                                "n": 0, "flagged": 0})
        d["facade"] += r["glaz_facade_m2"]
        d["opaque"] += r["opaque_ext_m2"]
        d["n"] += 1
        if r["flags"]:
            d["flagged"] += 1

    # ---- по блокам: live ----
    live, links_seen = live_inventory_by_block()

    blk_path = os.path.join(out_dir, "glazing_by_block.csv")
    blocks = sorted(set(list(calc.keys()) + list(live.keys())))
    with open(blk_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["block", "live_facade_m2", "live_facade_ARC",
                    "live_facade_FCD", "live_spandrel_m2",
                    "calc_facade_m2", "calc_opaque_ext_m2",
                    "delta_facade_m2", "coverage_%", "n_spaces", "n_flagged"])
        for b in blocks:
            lv = live.get(b, {})
            cc = calc.get(b, {})
            lf = round(lv.get("facade", 0.0), 1)
            la = round(lv.get("facade_ARC", 0.0), 1)
            lfc = round(lv.get("facade_FCD", 0.0), 1)
            ls = round(lv.get("spandrel", 0.0), 1)
            cf = round(cc.get("facade", 0.0), 1)
            co = round(cc.get("opaque", 0.0), 1)
            delta = round(lf - cf, 1)
            cov = round(100.0 * cf / lf, 0) if lf > 0 else 0
            w.writerow([b, lf, la, lfc, ls, cf, co, delta, cov,
                        cc.get("n", 0), cc.get("flagged", 0)])

    # ---- сводка в консоль ----
    print("\n========================= SVERKA PO BLOKAM =========================")
    print("%-5s %10s %9s %9s %10s %9s %7s" % (
        "block", "live_fac", "(ARC)", "(FCD)", "calc_fac", "delta", "cov%"))
    for b in blocks:
        lv = live.get(b, {})
        cc = calc.get(b, {})
        lf = lv.get("facade", 0.0)
        la = lv.get("facade_ARC", 0.0)
        lfc = lv.get("facade_FCD", 0.0)
        cf = cc.get("facade", 0.0)
        cov = (100.0 * cf / lf) if lf > 0 else 0
        print("%-5s %10.0f %9.0f %9.0f %10.0f %9.0f %6.0f%%" % (
            b, lf, la, lfc, cf, lf - cf, cov))

    print("\n================ ФЛАГИ (помещений) ================")
    for k in sorted(flag_counts, key=lambda x: -flag_counts[x]):
        print("  %-14s %5d" % (k, flag_counts[k]))
    print("  Всего помеченных:",
          sum(1 for r in rows if r["flags"]), "из", len(rows))

    print("\nТоп-15 помещений с аномалиями:")
    flagged = [r for r in rows if r["flags"]]
    flagged.sort(key=lambda r: -(r["leak_interior_m2"] + r["dropped_facade_m2"]
                                 + r["area_overest_m2"]))
    for r in flagged[:15]:
        print("  %-9s %-22s %-16s leak=%5.1f drop=%5.1f over=%5.1f | %s" % (
            r["number"], (r["name"] or "")[:22], r["level"][:16],
            r["leak_interior_m2"], r["dropped_facade_m2"],
            r["area_overest_m2"], r["flags"]))

    print("\nФайлы:")
    print("  ", sp_path)
    print("  ", blk_path)


if __name__ == "__main__":
    main()
