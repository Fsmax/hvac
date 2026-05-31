# -*- coding: utf-8 -*-
"""Вертикальный sidebar навигации (как в VS Code / Linear).

Использует emoji-иконки вместо файлов-SVG, чтобы не тянуть assets на этом
этапе. Заменим на нормальные SVG-иконки позже (Lucide / Phosphor).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget,
)


@dataclass
class SidebarItem:
    key: str
    icon: str            # emoji или текст-глиф пока (заменим на SVG)
    tooltip: str


class Sidebar(QFrame):
    """Узкая вертикальная панель навигации с иконками."""

    selected = Signal(str)   # key

    def __init__(self, items: List[SidebarItem], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(56)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        for item in items:
            btn = QToolButton(self)
            btn.setText(item.icon)
            btn.setToolTip(item.tooltip)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._make_handler(item.key))
            layout.addWidget(btn)
            self._group.addButton(btn)
            self._buttons[item.key] = btn

        spacer = QWidget(self)
        spacer.setObjectName("SidebarSpacer")
        layout.addWidget(spacer, stretch=1)

    def _make_handler(self, key: str) -> Callable[[], None]:
        def handler() -> None:
            self.selected.emit(key)
        return handler

    def select(self, key: str) -> None:
        """Программно выделить пункт (без сигнала)."""
        btn = self._buttons.get(key)
        if btn:
            btn.setChecked(True)

    def retranslate(self, items: List[SidebarItem]) -> None:
        """Обновляет tooltip пунктов по новому списку (для смены языка).
        Кнопки сами не пересоздаются — только подсказки."""
        for item in items:
            btn = self._buttons.get(item.key)
            if btn:
                btn.setToolTip(item.tooltip)
