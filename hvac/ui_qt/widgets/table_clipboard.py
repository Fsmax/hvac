# -*- coding: utf-8 -*-
"""Утилиты копирования/вставки для табличных представлений (Excel-совместимо).

- selection_to_tsv(view)         — выделение → TSV-строка;
- copy_selection_to_clipboard()  — выделение → буфер обмена;
- clipboard_grid()               — буфер → list[list[str]] (разбор TSV);
- install_copy(view)             — вешает Ctrl+C на копирование выделения.

Копирование работает с любым QTableView (читает Qt.DisplayRole, то есть то,
что видит пользователь). Вставка — задача конкретной панели: она знает,
какие колонки редактируемы и как привести строку к значению.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication


def selection_to_tsv(view) -> str:
    """Сериализует выделенные ячейки в прямоугольный TSV-блок.

    Пропуски в выделении заполняются пустыми ячейками, чтобы блок остался
    прямоугольным и корректно вставлялся в Excel.
    """
    sel = view.selectionModel()
    if sel is None:
        return ""
    indexes = sel.selectedIndexes()
    if not indexes:
        return ""
    model = view.model()
    rows = sorted({i.row() for i in indexes})
    cols = sorted({i.column() for i in indexes})
    cells = {}
    for i in indexes:
        val = model.data(i, Qt.DisplayRole)
        cells[(i.row(), i.column())] = "" if val is None else str(val)
    lines = ["\t".join(cells.get((r, c), "") for c in cols) for r in rows]
    return "\n".join(lines)


def copy_selection_to_clipboard(view) -> bool:
    """Копирует выделение в системный буфер. Возвращает True, если что-то
    скопировано."""
    tsv = selection_to_tsv(view)
    if not tsv:
        return False
    QApplication.clipboard().setText(tsv)
    return True


def clipboard_grid() -> List[List[str]]:
    """Разбирает текст буфера обмена в матрицу строк (строки × колонки)."""
    text = QApplication.clipboard().text()
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    if not text:
        return []
    return [row.split("\t") for row in text.split("\n")]


def install_copy(view) -> QShortcut:
    """Вешает Ctrl+C на копирование выделения в TSV. Возвращает QShortcut
    (живёт вместе с view)."""
    sc = QShortcut(QKeySequence.Copy, view)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: copy_selection_to_clipboard(view))
    return sc
