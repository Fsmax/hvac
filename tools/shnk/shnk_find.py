# -*- coding: utf-8 -*-
"""Поиск по PDF нормативов ШНҚ, лежащим рядом с этим файлом.

    python tools/shnk/shnk_find.py "тамбур"            # искать во всех ШНҚ
    python tools/shnk/shnk_find.py "кратность|ҳаво алмашинуви" -d 2.04.05
    python tools/shnk/shnk_find.py --page 82 -d 2.08.02   # страница целиком

Несколько слов разделяются `|` (ИЛИ). Тексты узбекские, поэтому ищи и по
узбекскому термину: расход воздуха — «ҳаво сарфи», кратность —
«ҳаво алмашинуви», температура — «ҳарорат», приложение — «ИЛОВА»,
таблица — «жадвал».
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def docs(filter_: str | None) -> list[Path]:
    found = sorted(HERE.glob("*.pdf"))
    if filter_:
        found = [p for p in found if filter_.lower() in p.name.lower()]
    if not found:
        sys.exit(f"нет PDF по фильтру «{filter_}» в {HERE}")
    return found


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Поиск по ШНҚ (PDF)")
    ap.add_argument("query", nargs="?", help="слова через | (ИЛИ)")
    ap.add_argument("-d", "--doc", help="часть имени документа, напр. 2.08.02")
    ap.add_argument("-p", "--page", type=int, help="напечатать страницу целиком")
    ap.add_argument("-c", "--context", type=int, default=170, help="длина строки")
    ap.add_argument("-n", "--limit", type=int, default=60, help="сколько строк вывести")
    args = ap.parse_args()

    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("нет PyMuPDF: python -m pip install pymupdf")

    if args.page:
        for path in docs(args.doc):
            doc = fitz.open(path)
            if args.page > doc.page_count:
                print(f"{path.name}: всего {doc.page_count} стр.")
                continue
            print(f"\n{'=' * 70}\n{path.name}  стр. {args.page}\n{'=' * 70}")
            print(doc[args.page - 1].get_text())
        return

    if not args.query:
        sys.exit("нужен запрос или --page")

    words = [w.strip().lower() for w in args.query.split("|") if w.strip()]
    shown = 0
    for path in docs(args.doc):
        doc = fitz.open(path)
        hits: list[tuple[int, str]] = []
        for pno in range(doc.page_count):
            text = doc[pno].get_text()
            low = text.lower()
            if not any(w in low for w in words):
                continue
            for line in text.splitlines():
                ll = line.lower()
                if any(w in ll for w in words) and line.strip():
                    hits.append((pno + 1, re.sub(r"\s+", " ", line.strip())))
        if hits:
            print(f"\n### {path.name} — совпадений: {len(hits)}")
            for pno, line in hits:
                if shown >= args.limit:
                    print(f"  … лимит {args.limit}, уточни запрос или подними -n")
                    return
                print(f"  стр.{pno:>3}  {line[: args.context]}")
                shown += 1
    if not shown:
        print(f"по «{args.query}» ничего не найдено")


if __name__ == "__main__":
    main()
