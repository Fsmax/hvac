# -*- coding: utf-8 -*-
"""Вертикальный sidebar навигации: группы с подписями + сворачивание.

Развёрнутый режим (~192 px): иконка + подпись, заголовки групп по маршруту
работы. Свёрнутый (56 px): только иконки с тултипами — прежнее поведение.
Иконки пока emoji; замена на SVG — отдельным этапом (см. ревизию UI).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from hvac.i18n import t as _t

WIDTH_EXPANDED = 192
WIDTH_COMPACT = 56


@dataclass
class SidebarItem:
    key: str
    icon: str            # emoji или текст-глиф (заменим на SVG)
    tooltip: str         # подпись пункта (имя поля сохранено для совместимости)
    group: str = ""      # заголовок группы ПЕРЕД этим пунктом ("" — без него)


class _ItemButton(QPushButton):
    """Кнопка пункта с бейджем-счётчиком в правом верхнем углу."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._badge = QLabel("", self)
        self._badge.setObjectName("SidebarBadge")
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._badge.hide()

    def set_badge(self, text: str, kind: str = "count") -> None:
        """kind: "count" — красный счётчик; "stale" — жёлтая точка."""
        self._badge.setText(text)
        self._badge.setProperty("kind", kind)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
        self._badge.setVisible(bool(text))
        if text:
            self._place_badge()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._place_badge()

    def _place_badge(self) -> None:
        if not self._badge.isVisible():
            return
        self._badge.adjustSize()
        self._badge.move(self.width() - self._badge.width() - 4, 3)


class Sidebar(QFrame):
    """Панель навигации с группами; умеет сворачиваться в узкую рейку."""

    selected = Signal(str)          # key
    collapsedChanged = Signal(bool)

    def __init__(self, items: List[SidebarItem], collapsed: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")

        self._items: List[SidebarItem] = list(items)
        self._collapsed = bool(collapsed)
        self._buttons: dict[str, _ItemButton] = {}
        self._group_labels: List[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Пункты — в скролле: на минимальной высоте окна (700 px) полный
        # список с заголовками групп не помещается.
        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, stretch=1)

        body = QWidget()
        body.setObjectName("SidebarBody")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for item in self._items:
            if item.group:
                glbl = QLabel(item.group.upper())
                glbl.setObjectName("SidebarGroupLabel")
                lay.addWidget(glbl)
                self._group_labels.append(glbl)
            btn = _ItemButton(body)
            btn.clicked.connect(self._make_handler(item.key))
            lay.addWidget(btn)
            self._group.addButton(btn)
            self._buttons[item.key] = btn

        lay.addStretch(1)

        # Кнопка сворачивания — внизу, вне скролла.
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("SidebarCollapse")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._on_toggle)
        outer.addWidget(self._toggle_btn)

        self._apply_mode()

    # ---------- Публичное API ----------
    def select(self, key: str) -> None:
        """Программно выделить пункт (без сигнала)."""
        btn = self._buttons.get(key)
        if btn:
            btn.setChecked(True)

    def set_badge(self, key: str, text: str) -> None:
        """Счётчик на пункте (например, число проблем); "" — скрыть."""
        btn = self._buttons.get(key)
        if btn:
            btn.set_badge(text, kind="count")

    def set_stale(self, key: str, stale: bool) -> None:
        """Жёлтая точка «результаты устарели» на пункте раздела."""
        btn = self._buttons.get(key)
        if btn:
            btn.set_badge("●" if stale else "", kind="stale")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_mode()
        self.collapsedChanged.emit(collapsed)

    def retranslate(self, items: List[SidebarItem]) -> None:
        """Обновляет подписи пунктов и групп по новому списку (смена языка).
        Кнопки не пересоздаются — только тексты."""
        self._items = list(items)
        groups = [it.group for it in self._items if it.group]
        for lbl, title in zip(self._group_labels, groups):
            lbl.setText(title.upper())
        self._apply_mode()

    # ---------- Внутреннее ----------
    def _make_handler(self, key: str) -> Callable[[], None]:
        def handler() -> None:
            self.selected.emit(key)
        return handler

    def _on_toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _apply_mode(self) -> None:
        compact = self._collapsed
        self.setFixedWidth(WIDTH_COMPACT if compact else WIDTH_EXPANDED)
        for item in self._items:
            btn = self._buttons.get(item.key)
            if btn is None:
                continue
            if compact:
                btn.setText(item.icon)
                btn.setToolTip(item.tooltip)
            else:
                btn.setText(f"{item.icon}  {item.tooltip}")
                btn.setToolTip("")
            btn.setProperty("compact", compact)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for lbl in self._group_labels:
            lbl.setVisible(not compact)
        if compact:
            self._toggle_btn.setText("⟩")
            self._toggle_btn.setToolTip(_t("sidebar.expand"))
        else:
            self._toggle_btn.setText("⟨  " + _t("sidebar.collapse"))
            self._toggle_btn.setToolTip("")
