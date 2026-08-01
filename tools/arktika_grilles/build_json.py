# -*- coding: utf-8 -*-
"""Сборка hvac/catalogs/data/grilles.json из каталога ARKTIKA/Арктос.

Использует геометрический парсер шумовых таблиц (build_grilles.extract_page)
для основной массы семейств + спец-парсеры переточных (velocity) и
напольных (только F0). Карта «страница -> семейство» — FAMILY_MAP.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
import fitz

sys.path.insert(0, os.path.dirname(__file__))
from build_grilles import extract_page, main_table, num, parse_size  # noqa: E402

PDF = next((a for a in sys.argv[1:] if a.lower().endswith(".pdf")),
           os.environ.get("ARKTIKA_PDF",
                          r"C:\Users\black\Downloads\Telegram Desktop"
                          r"\ARKTIKA_v8.02.pdf"))
# grilles.json в пакете: tools/arktika_grilles -> ../../hvac/catalogs/data
OUTDATA = (Path(__file__).resolve().parents[2]
           / "hvac" / "catalogs" / "data" / "grilles.json")
OUTDBG = Path(__file__).parent / "build_summary.txt"

# page(1-based) -> метаданные семейства. layout: noise|slot|transfer|floor
FAMILY_MAP = {
    387: dict(code="АМ/АД", variants=["АМН", "АМР", "АДН", "АДР"],
              name="Решётки регулируемые АМН/АМР/АДН/АДР",
              mount="wall", kind="universal", layout="noise"),
    391: dict(code="ПР", variants=["ПРН", "ПРР"],
              name="Решётки перфорированные ПРН/ПРР",
              mount="wall", kind="universal", layout="noise"),
    393: dict(code="РС", variants=["РСН", "РСР"],
              name="Решётки сотовые РСН/РСР",
              mount="wall", kind="universal", layout="noise"),
    395: dict(code="АЛ", variants=["АЛН", "АЛР"],
              name="Решётки АЛН/АЛР",
              mount="wall", kind="universal", layout="noise"),
    397: dict(code="АМ/АД-К", variants=["АМН-К", "АМР-К", "АДН-К", "АДР-К"],
              name="Решётки АМН-К/АМР-К/АДН-К/АДР-К (с присоед. камерой)",
              mount="plenum", kind="universal", layout="noise"),
    401: dict(code="ПР-К", variants=["ПРН-К", "ПРР-К"],
              name="Решётки перфорированные ПРН-К/ПРР-К",
              mount="plenum", kind="universal", layout="noise"),
    403: dict(code="РС-К", variants=["РСН-К", "РСР-К"],
              name="Решётки сотовые РСН-К/РСР-К",
              mount="plenum", kind="universal", layout="noise"),
    405: dict(code="АЛ-К", variants=["АЛН-К", "АЛР-К"],
              name="Решётки АЛН-К/АЛР-К",
              mount="plenum", kind="universal", layout="noise"),
    406: dict(code="АБ", variants=["АБН", "АБР"],
              name="Решётки АБН/АБР",
              mount="wall", kind="universal", layout="noise"),
    408: dict(code="КМУ", variants=["КМУ"],
              name="Решётки КМУ для круглых воздуховодов",
              mount="round_duct", kind="supply", layout="noise"),
    409: dict(code="КДУ/КДН", variants=["КДУ", "КДН"],
              name="Решётки КДУ/КДН для круглых воздуховодов",
              mount="round_duct", kind="universal", layout="noise"),
    412: dict(code="АРС/АЛС/АВС", variants=["АРС", "АЛС", "АВС"],
              name="Решётки щелевые АРС/АЛС/АВС (на 1 м длины)",
              mount="slot", kind="universal", layout="slot"),
    413: dict(code="АП", variants=["АП"],
              name="Решётки переточные АП",
              mount="transfer", kind="transfer", layout="transfer"),
    415: dict(code="РНБ/РНР", variants=["РНБ", "РНР"],
              name="Решётки напольные РНБ/РНР",
              mount="floor", kind="universal", layout="floor"),
}

TRANSFER_V = [0.2, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 2.5]
TRANSFER_DP = [0.1, 0.3, 0.7, 1.3, 2.0, 4.0, 8.0, 12.0]


def parse_regulator(page):
    """Таблица «% открытия регулятора расхода» -> K / ΔLwA, или None."""
    for tb in page.find_tables().tables:
        rows = tb.extract()
        flat = " ".join(str(c) for r in rows for c in r if c)
        if "регулятора" not in flat:
            continue
        open_pct, K, dLwA = [], [], []
        for r in rows:
            head = str(r[0] or "")
            vals = [num(c) for c in r[1:]]
            vals = [v for v in vals if v is not None]
            if "%" in head or "открыт" in head:
                open_pct = [int(v) for v in (num(c) for c in r[1:])
                            if v is not None]
            elif head.strip().startswith("К") or head.strip() == "K":
                K = vals
            elif "L" in head and "A" in head:
                dLwA = vals
        if K:
            return {"open_pct": open_pct, "K": K, "dLwA": dLwA}
    return None


def parse_transfer(page):
    """Переточные АП: размер, F0, Fж.с., L0 при 8 скоростях."""
    tb = main_table(page)
    sizes = []
    for r in tb.extract():
        sz = parse_size(r[0])
        f0 = num(r[1]) if len(r) > 1 else None
        if sz is None or f0 is None or sz[1] is None:
            continue
        fzs = num(r[2]) if len(r) > 2 else None
        # числовые L0 после F0 и Fж.с.
        l0s = [num(c) for c in r[3:3 + len(TRANSFER_V)]]
        pts = []
        for i, l0 in enumerate(l0s):
            if l0 is None:
                continue
            pts.append({"lwa": None, "v": TRANSFER_V[i], "l0": l0,
                        "dp": TRANSFER_DP[i], "throw": {}})
        if pts:
            sizes.append({"a": sz[0], "b": sz[1], "f0": f0,
                          "f_free": fzs, "points": pts})
    return sizes


def parse_floor(page):
    """Напольные РНБ/РНР: только размер и F0 (аэродинамика — номограммой)."""
    tb = main_table(page)
    sizes = []
    for r in tb.extract():
        sz = parse_size(r[0])
        f0 = num(r[1]) if len(r) > 1 else None
        if sz is None or f0 is None or sz[1] is None:
            continue
        sizes.append({"a": sz[0], "b": sz[1], "f0": f0, "points": []})
    return sizes


def main():
    doc = fitz.open(PDF)
    families = []
    summary = []
    for page1, meta in FAMILY_MAP.items():
        page = doc[page1 - 1]
        layout = meta["layout"]
        if layout in ("noise", "slot"):
            res = extract_page(page)
            sizes = res.get("sizes", []) if res else []
            if layout == "slot":
                for s in sizes:           # размер = число щелей
                    s["slots"] = s.pop("a")
                    s["b"] = None
                    s["length_m"] = 1.0
        elif layout == "transfer":
            sizes = parse_transfer(page)
        elif layout == "floor":
            sizes = parse_floor(page)
        else:
            sizes = []
        reg = parse_regulator(page) if layout in ("noise", "slot") else None
        fam = {k: meta[k] for k in
               ("code", "variants", "name", "mount", "kind", "layout")}
        fam["page"] = page1
        if reg:
            fam["regulator"] = reg
        fam["sizes"] = sizes
        families.append(fam)
        lwas = sorted({p["lwa"] for s in sizes for p in s["points"]
                       if p.get("lwa")}) if sizes else []
        summary.append(f"p{page1} {meta['code']:12s} layout={layout:8s} "
                       f"sizes={len(sizes):3d} lwa={lwas} "
                       f"reg={'yes' if reg else 'no'}")

    doc_out = {
        "source": "ARKTIKA / Арктос. Оборудование для систем вентиляции, "
                   "издание №8.02 (www.arktika.ru)",
        "note": "Данные для подбора решёток при α=0° (подача или удаление). "
                "Точки: lwa — уровень шума дБ(А); l0 — расход м³/ч; "
                "dp — ΔPполн, Па; throw — дальнобойность, м при Vx, м/с; "
                "v — скорость в живом сечении, м/с (переточные).",
        "families": families,
    }
    OUTDATA.parent.mkdir(parents=True, exist_ok=True)
    OUTDATA.write_text(json.dumps(doc_out, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    total = sum(len(f["sizes"]) for f in families)
    summary.append(f"\nИТОГО семейств={len(families)} размеров={total}")
    summary.append(f"JSON: {OUTDATA} ({OUTDATA.stat().st_size} байт)")
    OUTDBG.write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
