# -*- coding: utf-8 -*-
"""Welcome-экран: показывается на пустом проекте.

Большая «карточка» по центру с действиями: открыть проект / загрузить CSV /
создать пустой. Заменяет диалог-приветствие первого запуска.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from hvac.i18n import t as _t


class WelcomePanel(QWidget):
    """Экран на пустом проекте."""

    openProject = Signal()
    loadCsv = Signal()
    newEmpty = Signal()
    fromTemplate = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)

        card = QFrame()
        card.setProperty("role", "card")
        card.setMaximumWidth(640)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(40, 36, 40, 36)
        inner.setSpacing(8)

        title = QLabel(_t("welcome.title"))
        title.setProperty("role", "h1")
        subtitle = QLabel(_t("welcome.subtitle"))
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)

        inner.addWidget(title)
        inner.addWidget(subtitle)
        inner.addSpacing(20)

        # Действия
        actions = QVBoxLayout()
        actions.setSpacing(10)

        actions.addLayout(self._action_row(
            _t("welcome.action_open"),
            _t("welcome.action_open_desc"),
            self.openProject,
        ))
        actions.addLayout(self._action_row(
            _t("welcome.action_csv"),
            _t("welcome.action_csv_desc"),
            self.loadCsv,
            primary=True,
        ))
        actions.addLayout(self._action_row(
            _t("welcome.action_new"),
            _t("welcome.action_new_desc"),
            self.newEmpty,
        ))
        actions.addLayout(self._action_row(
            _t("welcome.action_template"),
            _t("welcome.action_template_desc"),
            self.fromTemplate,
        ))

        inner.addLayout(actions)
        inner.addSpacing(16)

        hint = QLabel(_t("welcome.hint"))
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        inner.addWidget(hint)

        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(card)
        wrap.addStretch(1)
        outer.addLayout(wrap)
        outer.addStretch(2)

    def _action_row(self, title: str, desc: str, signal: Signal,
                    primary: bool = False) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        btn = QPushButton(title)
        if primary:
            btn.setProperty("role", "primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(260)
        btn.setMinimumHeight(40)
        btn.clicked.connect(signal)
        row.addWidget(btn)

        desc_l = QLabel(desc)
        desc_l.setProperty("role", "muted")
        desc_l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(desc_l, stretch=1)
        return row
