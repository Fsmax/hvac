# -*- coding: utf-8 -*-
"""Экстрактор таблиц подбора решёток ARKTIKA/Арктос -> grilles.json.

Алгоритм (геометрический, не зависит от жёстких индексов колонок):
  1. find_tables -> главная таблица (первый столбец «Размер»).
  2. Шумовые полосы — слова «LwA…» в верхней строке шапки; уровень =
     цифры в токене, x-центр запоминаем.
  3. Группы рабочих точек — по словам «L0» в подшапке (x-позиции).
     Группа g: [x(L0_g), x(L0_{g+1})).
  4. Каждый столбец данных относим к группе по x-центру; роль столбца:
     L0 / ΔP (есть «ΔP»/«Па») / дальнобойность (иначе). Скорость Vx
     дальнобойности — из строки значений 0,2/0,5/0,75 по x.
  5. Уровень шума группы = ближайший по x центр подписи «LwA…».
  Результат: для каждого размера набор точек {lwa, l0, dp, throw{vx}}.
"""
from __future__ import annotations
import json
import re
import os
import sys
from pathlib import Path
import fitz

# Путь к PDF каталога ARKTIKA: аргумент командной строки *.pdf или
# переменная окружения ARKTIKA_PDF (иначе — путь по умолчанию).
PDF = next((a for a in sys.argv[1:] if a.lower().endswith(".pdf")),
           os.environ.get("ARKTIKA_PDF",
                          r"C:\Users\black\Downloads\Telegram Desktop"
                          r"\ARKTIKA_v8.02.pdf"))
OUT = Path(__file__).parent          # отладочные дампы (--audit/validate)


def num(s):
    """'0,018'->0.018; '–'/''/None->None; '2,7 1100'->первое число."""
    if s is None:
        return None
    s = str(s).strip().replace("\xa0", " ")
    s = s.replace(",", ".")
    m = re.findall(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    return float(m[0])


def two_nums(s):
    """Из ячейки достаём до двух чисел (на случай слипшихся '2,7 1100')."""
    if s is None:
        return []
    return [float(x.replace(",", ".")) for x in
            re.findall(r"-?\d+(?:,\d+)?", str(s))]


def parse_size(s):
    """'200  100' -> (200,100); 'Ø160' -> (160,None)."""
    if s is None:
        return None
    nums = re.findall(r"\d+", str(s))
    if not nums:
        return None
    a = int(nums[0])
    b = int(nums[1]) if len(nums) > 1 else None
    return a, b


def main_table(page):
    """Возвращает таблицу с первым столбцом «Размер» (или наибольшую)."""
    tabs = page.find_tables()
    best, best_score = None, -1
    for tb in tabs.tables:
        rows = tb.extract()
        if not rows:
            continue
        head = " ".join(str(c) for c in rows[0] if c)
        score = tb.row_count * tb.col_count
        if "Размер" in head or "азмер" in head:
            score += 100000
        if score > best_score:
            best, best_score = tb, score
    return best


def col_bounds(tb):
    xs = set()
    for cc in tb.cells:
        if cc:
            xs.add(round(cc[0], 1))
            xs.add(round(cc[2], 1))
    return sorted(xs)


def extract_page(page, debug=False):
    tb = main_table(page)
    if tb is None:
        return None
    rows = tb.extract()
    xs = col_bounds(tb)
    # центры столбцов
    centers = [(xs[i] + xs[i + 1]) / 2 for i in range(len(xs) - 1)]
    ncol = tb.col_count

    bbox = tb.bbox
    band_h = (bbox[3] - bbox[1]) / max(tb.row_count, 1)
    words = page.get_text("words")
    head_words = [w for w in words
                  if bbox[1] - 2 <= w[1] <= bbox[1] + band_h * 3.6 and w[4].strip()]

    # 1) шумовые подписи LwA
    noise_labels = []  # (xc, level)
    for w in head_words:
        t = w[4]
        if "wA" in t or "wА" in t or t.startswith("LwA") or t.startswith("L"):
            m = re.search(r"(\d{2})", t)
            if "wA" in t and m:
                noise_labels.append(((w[0] + w[2]) / 2, int(m.group(1))))
    # 2) позиции L0 и ΔP в подшапке
    l0_x = sorted((w[0] + w[2]) / 2 for w in head_words
                  if w[4].replace(" ", "").startswith("L0")
                  or w[4].replace(" ", "") in ("L0,", "L0"))
    dp_x = [(w[0] + w[2]) / 2 for w in head_words
            if "ΔP" in w[4] or "ΔР" in w[4]]
    # 3) значения Vx (0,2 / 0,5 / 0,75) в нижней строке шапки
    vx_words = [((w[0] + w[2]) / 2, w[4]) for w in head_words
                if re.fullmatch(r"0,(2|5|75)", w[4].strip())]

    if debug:
        dbg = [f"ncol={ncol} rows={tb.row_count}",
               f"noise_labels={noise_labels}",
               f"l0_x={[round(x,1) for x in l0_x]}",
               f"dp_x={[round(x,1) for x in dp_x]}",
               f"vx={[(round(x,1),v) for x,v in vx_words]}",
               f"centers={[round(c,1) for c in centers]}"]
        (OUT / "dbg_struct.txt").write_text("\n".join(dbg), encoding="utf-8")

    if not l0_x:
        return {"layout": "non-noise", "rows": rows[:3]}

    # группы рабочих точек по L0
    groups = []  # dict: x_start, x_end, lwa, col_l0, col_dp, throws[(col,vx)]
    for gi, x0 in enumerate(l0_x):
        x1 = l0_x[gi + 1] if gi + 1 < len(l0_x) else 1e9
        lwa = min(noise_labels, key=lambda nl: abs(nl[0] - x0))[1] \
            if noise_labels else None
        groups.append({"x0": x0, "x1": x1, "lwa": lwa,
                       "col_l0": None, "col_dp": None, "throws": []})

    def which_group(xc):
        for g in groups:
            if g["x0"] - 6 <= xc < g["x1"] - 6:
                return g
        return None

    # назначаем роли столбцам (индекс >=2, т.е. после Размер и F0)
    for ci in range(2, ncol):
        xc = centers[ci]
        g = which_group(xc)
        if g is None:
            continue
        # L0?
        if any(abs(xc - lx) < 12 for lx in l0_x) and g["col_l0"] is None:
            g["col_l0"] = ci
            continue
        # ΔP?
        if any(abs(xc - dx) < 14 for dx in dp_x):
            g["col_dp"] = ci
            continue
        # иначе — дальнобойность; vx по ближайшему
        vx = None
        if vx_words:
            vx = min(vx_words, key=lambda vw: abs(vw[0] - xc))
            vx = vx[1] if abs(vx[0] - xc) < 14 else None
        g["throws"].append((ci, vx))

    # данные
    sizes = []
    for r in rows:
        sz = parse_size(r[0])
        f0 = num(r[1]) if len(r) > 1 else None
        if sz is None or f0 is None:
            continue
        a, b = sz
        pts = []
        for g in groups:
            if g["col_l0"] is None:
                continue
            l0 = num(r[g["col_l0"]]) if g["col_l0"] < len(r) else None
            if l0 is None:
                continue
            dp = num(r[g["col_dp"]]) if (g["col_dp"] is not None
                                         and g["col_dp"] < len(r)) else None
            thr = {}
            for ci, vx in g["throws"]:
                if ci < len(r):
                    tv = num(r[ci])
                    if tv is not None and vx:
                        thr[vx.replace(",", ".")] = tv
            pts.append({"lwa": g["lwa"], "l0": l0, "dp": dp, "throw": thr})
        if pts:
            sizes.append({"a": a, "b": b, "f0": f0, "points": pts})
    return {"layout": "noise", "sizes": sizes}


def page_title(page):
    txt = page.get_text().splitlines()
    for ln in txt:
        s = ln.strip()
        if "подбор" in s.lower() or "Данные для" in s:
            return s
    # иначе первые осмысленные строки
    for ln in txt:
        s = ln.strip()
        if len(s) > 8 and not s.isdigit() and "www." not in s \
                and "Оборудование" not in s and "Воздухораспред" not in s:
            return s
    return ""


if __name__ == "__main__":
    import sys
    doc = fitz.open(PDF)
    if "--audit" in sys.argv:
        report = []
        for p1 in range(386, 416):          # 1-based
            page = doc[p1 - 1]
            title = page_title(page)
            try:
                res = extract_page(page)
            except Exception as e:
                report.append(f"p{p1}: ERROR {e!r} | {title[:70]}")
                continue
            if res is None:
                report.append(f"p{p1}: no-table | {title[:70]}")
                continue
            if res["layout"] == "noise":
                szs = res["sizes"]
                samp = ""
                if szs:
                    s0 = szs[0]
                    lwas = [p["lwa"] for p in s0["points"]]
                    samp = (f" first={s0['a']}x{s0['b']} f0={s0['f0']} "
                            f"lwa={lwas} l0={[p['l0'] for p in s0['points']]}")
                report.append(f"p{p1}: NOISE sizes={len(szs)}{samp} | {title[:60]}")
            else:
                report.append(f"p{p1}: {res['layout']} | {title[:60]}")
        (OUT / "report_all.txt").write_text("\n".join(report), encoding="utf-8")
        print("audit written")
    else:
        res = extract_page(doc[386], debug=True)
        (OUT / "validate_387.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"page387: layout={res['layout']} sizes={len(res.get('sizes', []))}")
        if res.get("sizes"):
            (OUT / "validate_387_first.txt").write_text(
                json.dumps(res["sizes"][0], ensure_ascii=False, indent=1),
                encoding="utf-8")
