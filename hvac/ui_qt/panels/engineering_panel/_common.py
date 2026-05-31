# -*- coding: utf-8 -*-
"""Общие помощники таблиц для вкладок панели «Инженерия»."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QTableWidget, QTableWidgetItem,
)


def _setup_table(table: QTableWidget, headers: list[str]) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setStretchLastSection(True)


def _set_row(table: QTableWidget, row: int, values: list[Any]) -> None:
    for c, v in enumerate(values):
        if isinstance(v, float):
            text = f"{v:,.2f}".replace(",", " ") if v != int(v) else f"{int(v)}"
        else:
            text = str(v)
        item = QTableWidgetItem(text)
        if isinstance(v, (int, float)):
            item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
        table.setItem(row, c, item)
