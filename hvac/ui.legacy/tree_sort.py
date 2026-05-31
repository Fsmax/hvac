# -*- coding: utf-8 -*-
"""Сортировка ttk.Treeview по клику на заголовок столбца.

Поведение:
* 1-й клик по столбцу — сортировка по возрастанию (▲ в заголовке)
* 2-й клик по тому же столбцу — по убыванию (▼)
* 3-й клик — сброс к исходному порядку
* Клик по другому столбцу — переключение на него (асc)

Особенности:
* Числа сортируются как числа (1 < 2 < 10, а не 1 < 10 < 2).
* Строки с цифрами — natural sort: «B02-003» идёт перед «B02-034».
* Пустые ячейки (``""``, ``"—"``, ``"?"``) уходят в конец независимо от
  направления — это удобнее, чем когда они «прыгают» между верхом и низом.
"""

from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Iterable, Optional, Tuple

_ARROW_UP = " ▲"
_ARROW_DOWN = " ▼"
_NUM_CHUNK_RE = re.compile(r"(\d+)")
_EMPTY_TOKENS = {"", "—", "-", "?", "None", "none"}


def _sort_key(value) -> Tuple:
    """Ключ сортировки: (приоритет_пустоты, тип_значения, само_значение).

    Возвращает кортеж так, чтобы сортировка вела себя одинаково для смеси
    чисел и строк, а пустые ячейки всегда оказывались в конце.
    """
    if value is None:
        return (1, 0, "")
    # Чистое число?
    if isinstance(value, (int, float)):
        return (0, 0, float(value))
    s = str(value).strip()
    if s in _EMPTY_TOKENS:
        return (1, 0, "")
    # Строка, которая на самом деле число (например, "12.5")
    try:
        return (0, 0, float(s.replace(",", ".")))
    except ValueError:
        pass
    # Natural sort: бьём строку на куски цифр/нецифр
    chunks = _NUM_CHUNK_RE.split(s.lower())
    key = []
    for ch in chunks:
        if ch.isdigit():
            key.append((0, int(ch), ""))
        elif ch:
            key.append((1, 0, ch))
    return (0, 1, tuple(key))


def attach_sort(tree: ttk.Treeview,
                columns: Iterable[str]) -> Callable[[], None]:
    """Делает заголовки столбцов сортирующими по клику.

    Параметры
    ---------
    tree : ttk.Treeview
        Виджет, к которому подключаем сортировку.
    columns : Iterable[str]
        Идентификаторы столбцов (как переданы в ``columns=`` при создании
        Treeview). Используются и как column-id, и как текст заголовка.

    Возвращает
    ----------
    snapshot : callable
        Функцию без аргументов. Вызывайте её после каждой перезагрузки
        данных в дерево (``refresh``), чтобы запомнить новый «исходный
        порядок» — именно он будет восстанавливаться на третьем клике.
    """
    columns = tuple(columns)
    state = {"col": None, "dir": None}
    orig_headings = {c: tree.heading(c, "text") for c in columns}
    original_order: list = []

    def _restore_headings() -> None:
        for c in columns:
            tree.heading(c, text=orig_headings[c])

    def _reset_to_original() -> None:
        for idx, iid in enumerate(original_order):
            if tree.exists(iid):
                tree.move(iid, "", idx)

    def _sort_by(col: str) -> None:
        prev_col = state["col"]
        prev_dir = state["dir"]

        # Определяем следующее направление
        if prev_col == col:
            next_dir: Optional[str] = {
                "asc": "desc", "desc": None,
            }.get(prev_dir, "asc")
        else:
            next_dir = "asc"

        _restore_headings()
        state["col"] = col if next_dir else None
        state["dir"] = next_dir

        if next_dir is None:
            _reset_to_original()
            return

        tree.heading(
            col,
            text=orig_headings[col]
            + (_ARROW_UP if next_dir == "asc" else _ARROW_DOWN),
        )
        rows = [(tree.set(iid, col), iid) for iid in tree.get_children("")]
        rows.sort(key=lambda r: _sort_key(r[0]), reverse=(next_dir == "desc"))
        for idx, (_, iid) in enumerate(rows):
            tree.move(iid, "", idx)

    for c in columns:
        tree.heading(c, command=lambda col=c: _sort_by(col))

    def snapshot() -> None:
        """Запомнить текущий порядок строк как исходный + сбросить стрелки."""
        nonlocal original_order
        original_order = list(tree.get_children(""))
        state["col"] = None
        state["dir"] = None
        _restore_headings()

    return snapshot


def make_scrollable_tree(
    parent,
    columns: Iterable[str],
    widths: Optional[Dict[str, int]] = None,
    right_align: Optional[Iterable[str]] = None,
    height: int = 20,
    select_mode: str = "browse",
) -> Tuple[ttk.Treeview, Callable[[], None], ttk.Frame]:
    """Создаёт Treeview с вертикальным и горизонтальным ползунками
    и подключённой сортировкой по клику на заголовок.

    Параметры
    ---------
    parent       : родительский виджет
    columns      : идентификаторы столбцов
    widths       : словарь {имя_столбца: ширина_px}; по умолчанию 100
    right_align  : имена столбцов с правым выравниванием (числовые колонки)
    height       : высота в строках
    select_mode  : "browse" / "extended" / "none"

    Возвращает (tree, sort_snapshot, frame).
    frame — внешний контейнер, который нужно упаковать через .pack/.grid.
    sort_snapshot — вызовите после каждой перезагрузки данных в дерево.
    """
    columns = tuple(columns)
    widths = widths or {}
    right_align_set = set(right_align or ())

    frame = ttk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    tree = ttk.Treeview(frame, columns=columns, show="headings",
                         height=height, selectmode=select_mode)
    for c in columns:
        tree.heading(c, text=c)
        anchor = "e" if c in right_align_set else "w"
        tree.column(c, anchor=anchor, width=widths.get(c, 100),
                    stretch=False)

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    # Shift + колесо мыши → горизонтальная прокрутка
    def _on_shift_wheel(event):
        tree.xview_scroll(int(-event.delta / 120), "units")
        return "break"
    tree.bind("<Shift-MouseWheel>", _on_shift_wheel)

    sort_snapshot = attach_sort(tree, columns)
    return tree, sort_snapshot, frame


def make_search_bar(parent, on_change: Callable[[str], None],
                    placeholder: str = "поиск по подстроке"
                    ) -> Tuple[ttk.Frame, tk.StringVar]:
    """Создаёт компактную панель поиска с лупой и Entry.

    on_change(query) вызывается при каждом изменении текста.
    Esc в поле — очистка.
    Возвращает (frame, var). frame нужно упаковать самостоятельно.
    """
    fr = ttk.Frame(parent)
    var = tk.StringVar()
    ttk.Label(fr, text="🔍 Поиск:",
              font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)
    ent = ttk.Entry(fr, textvariable=var, width=30)
    ent.pack(side="left", padx=4)
    ent.bind("<Escape>", lambda e: var.set(""))
    var.trace_add("write", lambda *_: on_change(var.get()))
    ttk.Label(fr, text=placeholder,
              foreground="#888").pack(side="left", padx=2)
    return fr, var
