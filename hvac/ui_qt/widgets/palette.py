# -*- coding: utf-8 -*-
"""Командная палитра в стиле VS Code: Ctrl+K → поиск по командам."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.ui_qt.commands import Command, CommandRegistry


class CommandPalette(QDialog):
    """Модальный popup со списком команд."""

    def __init__(self, registry: CommandRegistry, parent: QWidget | None = None):
        super().__init__(parent)
        self.registry = registry
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setModal(True)
        self.setFixedWidth(640)
        self.setMaximumHeight(480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Контейнер с border-radius (через QFrame и QSS)
        frame = QFrame()
        frame.setProperty("role", "card")
        outer.addWidget(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("palette.search_ph"))
        self.search.setMinimumHeight(40)
        self.search.setStyleSheet(
            "QLineEdit { border: none; border-bottom: 1px solid rgba(255,255,255,0.08);"
            " padding: 10px 16px; font-size: 14px; background: transparent; }"
        )
        col.addWidget(self.search)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSpacing(0)
        col.addWidget(self.list)

        self.search.textChanged.connect(self._refilter)
        self.list.itemActivated.connect(self._run_item)
        self.search.returnPressed.connect(self._run_current)

        self._refilter("")

    # ---------- API ----------
    def show_at(self, parent: QWidget) -> None:
        # Центрируем по верхней трети родителя
        if parent:
            geo = parent.geometry()
            cx = geo.center().x()
            top = geo.top() + 100
            self.move(cx - self.width() // 2, top)
        self.search.setFocus()
        self.search.selectAll()
        self.show()

    # ---------- Внутреннее ----------
    def _refilter(self, text: str) -> None:
        text = text.strip().lower()
        self.list.clear()
        matches = self._fuzzy(self.registry.all(), text)
        for cmd in matches[:40]:
            item = QListWidgetItem(self.list)
            w = _CommandRow(cmd)
            item.setSizeHint(w.sizeHint())
            self.list.setItemWidget(item, w)
            item.setData(Qt.UserRole, cmd.id)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _fuzzy(self, cmds: List[Command], query: str) -> List[Command]:
        if not query:
            # Сортируем по категории, потом по title
            return sorted(cmds, key=lambda c: (c.category, c.title))
        # Простой ранжированный фильтр: все слова запроса должны встречаться
        terms = query.split()
        scored: List[tuple[int, Command]] = []
        for c in cmds:
            haystack = f"{c.title} {c.category} {c.hint}".lower()
            if not all(t in haystack for t in terms):
                continue
            # Приоритет: начало title > слово в title > подстрока
            score = 0
            if c.title.lower().startswith(query):
                score += 100
            for t in terms:
                if t in c.title.lower():
                    score += 10
            scored.append((-score, c))
        scored.sort(key=lambda x: (x[0], x[1].title))
        return [c for _, c in scored]

    def _run_item(self, item: QListWidgetItem) -> None:
        cmd_id = item.data(Qt.UserRole)
        cmd = self.registry.find(cmd_id)
        if cmd:
            self.hide()
            cmd.handler()

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item:
            self._run_item(item)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Стрелки в поле поиска двигают выделение списка
        if event.key() == Qt.Key_Down:
            self.list.setCurrentRow(
                min(self.list.currentRow() + 1, self.list.count() - 1))
            return
        if event.key() == Qt.Key_Up:
            self.list.setCurrentRow(max(self.list.currentRow() - 1, 0))
            return
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


class _CommandRow(QWidget):
    """Одна строка палитры: категория | title | shortcut."""

    def __init__(self, cmd: Command):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        title = QLabel(cmd.title)
        title.setStyleSheet("font-size: 13px;")
        layout.addWidget(title, stretch=1)

        if cmd.hint:
            hint = QLabel(cmd.hint)
            hint.setProperty("role", "muted")
            layout.addWidget(hint)

        cat = QLabel(cmd.category)
        cat.setProperty("role", "muted")
        cat.setStyleSheet("font-size: 11px;")
        layout.addWidget(cat)

        if cmd.shortcut:
            kbd = QLabel(cmd.shortcut)
            kbd.setStyleSheet(
                "background: rgba(255,255,255,0.06); padding: 2px 8px; "
                "border-radius: 4px; font-size: 11px;"
            )
            layout.addWidget(kbd)

    def sizeHint(self) -> QSize:
        return QSize(0, 34)
