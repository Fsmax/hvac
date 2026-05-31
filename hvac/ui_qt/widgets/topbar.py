# -*- coding: utf-8 -*-
"""Топбар: бренд + контекстная информация + быстрые действия."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from hvac.i18n import t as _t


class TopBar(QFrame):
    """Горизонтальная панель сверху."""

    recalcRequested = Signal()
    saveRequested = Signal()
    exportRequested = Signal()
    themeToggleRequested = Signal()
    languageToggleRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TopBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Бренд
        brand = QLabel("HVAC")
        brand.setProperty("role", "brand")
        accent = QLabel("Calculator")
        accent.setProperty("role", "brand")
        accent_in = QLabel("4.0")
        accent_in.setProperty("role", "brandAccent")
        layout.addWidget(brand)
        layout.addWidget(accent)
        layout.addWidget(accent_in)
        layout.addSpacing(20)

        # Контекстные «пилюли»
        self.project_pill = QLabel(_t("topbar.no_project"))
        self.project_pill.setProperty("role", "pill")
        self.city_pill = QLabel("—")
        self.city_pill.setProperty("role", "pill")
        self.method_pill = QLabel("СП 50.13330")
        self.method_pill.setProperty("role", "pill")
        for pill in (self.project_pill, self.city_pill, self.method_pill):
            layout.addWidget(pill)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(spacer)

        # Быстрые действия справа
        self.recalc_btn = QPushButton("▶  " + _t("topbar.recalc"))
        self.recalc_btn.setProperty("role", "primary")
        self.recalc_btn.setCursor(Qt.PointingHandCursor)
        self.recalc_btn.clicked.connect(self.recalcRequested)

        self.save_btn = QPushButton(_t("topbar.save"))
        self.save_btn.setProperty("role", "ghost")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.saveRequested)

        self.export_btn = QPushButton(_t("topbar.export") + "…")
        self.export_btn.setProperty("role", "ghost")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self.exportRequested)

        # Кнопка-иконка переключения языка
        self.lang_btn = QPushButton("RU")
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.setFixedWidth(44)
        self.lang_btn.setToolTip(_t("topbar.lang_tooltip"))
        self.lang_btn.clicked.connect(self.languageToggleRequested)

        # Кнопка-иконка переключения темы
        self.theme_btn = QPushButton("☾")
        self.theme_btn.setProperty("role", "ghost")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFixedWidth(36)
        self.theme_btn.setToolTip(_t("topbar.theme_tooltip"))
        self.theme_btn.clicked.connect(self.themeToggleRequested)

        layout.addWidget(self.save_btn)
        layout.addWidget(self.export_btn)
        layout.addWidget(self.lang_btn)
        layout.addWidget(self.theme_btn)
        layout.addWidget(self.recalc_btn)

    def set_theme_icon(self, is_dark: bool) -> None:
        """Меняет глиф в зависимости от текущей темы."""
        # В dark-теме показываем солнце (клик → светлая).
        # В light-теме — луну (клик → тёмная).
        self.theme_btn.setText("☀" if is_dark else "☾")

    def set_language_label(self, lang_code: str) -> None:
        """Обновляет надпись на кнопке-переключателе языка."""
        label = {"ru": "RU", "uz": "UZ"}.get(lang_code, lang_code.upper())
        self.lang_btn.setText(label)
        self.lang_btn.setToolTip(
            _t("topbar.lang_tooltip_current").format(label=label))
        self._last_project_name = getattr(self, "_last_project_name", "")

    def retranslate(self) -> None:
        """Обновляет все подписи в TopBar на текущий язык."""
        self.recalc_btn.setText("▶  " + _t("topbar.recalc"))
        self.save_btn.setText(_t("topbar.save"))
        self.export_btn.setText(_t("topbar.export") + "…")
        self.lang_btn.setToolTip(_t("topbar.lang_tooltip"))
        self.theme_btn.setToolTip(_t("topbar.theme_tooltip"))
        # Обновляем «пилюлю» проекта — если имя не задано, показываем
        # локализованный плейсхолдер.
        if not getattr(self, "_project_name", ""):
            self.project_pill.setText(_t("topbar.no_project"))

    def set_project_name(self, name: str) -> None:
        self._project_name = name
        self.project_pill.setText(name or _t("topbar.no_project"))
        self.project_pill.setProperty(
            "role", "pillAccent" if name else "pill")
        self._refresh_style(self.project_pill)

    def set_city(self, city: str) -> None:
        self.city_pill.setText(city or "—")
        self.city_pill.setProperty(
            "role", "pillAccent" if city else "pill")
        self._refresh_style(self.city_pill)

    def set_methodology(self, name: str) -> None:
        self.method_pill.setText(name or "—")

    @staticmethod
    def _refresh_style(w: QWidget) -> None:
        """QSS не пересчитывается автоматически при смене dynamic property."""
        w.style().unpolish(w)
        w.style().polish(w)
