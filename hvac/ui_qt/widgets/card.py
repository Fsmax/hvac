# -*- coding: utf-8 -*-
"""Карточка-контейнер с заголовком — базовый строительный блок панелей."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget


class Card(QFrame):
    """QFrame с тенью + закруглением + заголовком/описанием.

    Использование:
        card = Card("Источники данных", "Откуда загружать геометрию")
        card.body().addWidget(...)
    """

    def __init__(self, title: str = "", subtitle: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "card")
        # Карточка занимает по высоте только нужное (не растягивается под соседа в сетке)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 18, 20, 20)
        self._outer.setSpacing(4)

        # Заголовок и подзаголовок создаём всегда (даже пустыми), чтобы
        # можно было обновить их позже через set_title/set_subtitle
        # после смены языка интерфейса.
        self._title_label = QLabel(title)
        self._title_label.setProperty("role", "h2")
        self._title_label.setVisible(bool(title))
        self._outer.addWidget(self._title_label)

        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setProperty("role", "muted")
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setVisible(bool(subtitle))
        self._outer.addWidget(self._subtitle_label)

        if title or subtitle:
            self._outer.addSpacing(12)

        # Внутренний body — куда наследники добавляют свои виджеты
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(10)
        self._outer.addLayout(self._body)

    def body(self) -> QVBoxLayout:
        return self._body

    def set_title(self, text: str) -> None:
        self._title_label.setText(text)
        self._title_label.setVisible(bool(text))

    def set_subtitle(self, text: str) -> None:
        self._subtitle_label.setText(text)
        self._subtitle_label.setVisible(bool(text))
