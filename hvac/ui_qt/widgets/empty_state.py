# -*- coding: utf-8 -*-
"""Единая заглушка пустого состояния для списков/деревьев.

Накладывается поверх viewport'а: короткий заголовок, одна строка подсказки
и (опционально) кнопка первого действия. Владелец зовёт sync(is_empty)
после каждого обновления данных — виджет сам следит только за геометрией.

Использование:
    self.tree_empty = EmptyStateHint(
        self.tree, _t("...title"), _t("...hint"),
        action_text=_t("btn.add"), on_action=self._add_item)
    ...
    self.tree_empty.sync(self.tree.topLevelItemCount() == 0)
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class EmptyStateHint(QWidget):
    """Оверлей «здесь пока пусто» поверх viewport'а."""

    def __init__(self, view: QAbstractScrollArea, title: str, hint: str = "",
                 action_text: str = "",
                 on_action: Optional[Callable[[], None]] = None):
        super().__init__(view.viewport())
        self._view = view

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(6)
        lay.addStretch(1)

        self.title_lbl = QLabel(title)
        self.title_lbl.setProperty("role", "h2")
        self.title_lbl.setAlignment(Qt.AlignHCenter)
        self.title_lbl.setWordWrap(True)
        lay.addWidget(self.title_lbl)

        self.hint_lbl = QLabel(hint)
        self.hint_lbl.setProperty("role", "muted")
        self.hint_lbl.setAlignment(Qt.AlignHCenter)
        self.hint_lbl.setWordWrap(True)
        self.hint_lbl.setVisible(bool(hint))
        lay.addWidget(self.hint_lbl)

        self.action_btn = QPushButton(action_text)
        self.action_btn.setProperty("role", "primary")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setVisible(bool(action_text))
        if on_action is not None:
            self.action_btn.clicked.connect(on_action)
        row = QVBoxLayout()  # кнопка по центру, не на всю ширину
        row.setContentsMargins(0, 8, 0, 0)
        row.addWidget(self.action_btn, alignment=Qt.AlignHCenter)
        lay.addLayout(row)

        lay.addStretch(2)

        view.viewport().installEventFilter(self)
        self._fit()
        self.hide()

    # ---------- Публичное API ----------
    def sync(self, is_empty: bool) -> None:
        """Показать/скрыть по факту пустоты данных владельца."""
        self.setVisible(bool(is_empty))
        if is_empty:
            self._fit()
            self.raise_()

    def set_texts(self, title: str, hint: str = "",
                  action_text: str = "") -> None:
        """Для retranslate_ui владельца."""
        self.title_lbl.setText(title)
        self.hint_lbl.setText(hint)
        self.hint_lbl.setVisible(bool(hint))
        if action_text:
            self.action_btn.setText(action_text)

    # ---------- Геометрия ----------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Resize and obj is self._view.viewport():
            self._fit()
        return False

    def _fit(self) -> None:
        self.setGeometry(self._view.viewport().rect())
