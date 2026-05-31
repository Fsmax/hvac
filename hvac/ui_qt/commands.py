# -*- coding: utf-8 -*-
"""Реестр команд приложения для командной палитры и горячих клавиш.

Команды собираются в одном месте — палитре, меню и shortcut'ам не нужно
дублировать определения. Каждая команда — dataclass с id, title, callable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class Command:
    id: str
    title: str            # отображается в палитре
    category: str         # «Навигация», «Действия», «Вид», ...
    handler: Callable[[], object]
    shortcut: Optional[str] = None
    hint: str = ""        # подсказка в палитре справа от названия


class CommandRegistry:
    """Глобальный список команд."""

    def __init__(self) -> None:
        self._items: List[Command] = []

    def add(self, cmd: Command) -> None:
        self._items.append(cmd)

    def all(self) -> List[Command]:
        return list(self._items)

    def find(self, cmd_id: str) -> Optional[Command]:
        for c in self._items:
            if c.id == cmd_id:
                return c
        return None
