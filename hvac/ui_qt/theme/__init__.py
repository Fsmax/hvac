# -*- coding: utf-8 -*-
"""Управление темами оформления.

Темы хранятся как .qss-файлы в этой же папке. apply_theme() читает файл и
применяет ко всему приложению. Цветовые переменные определяются в начале
QSS как @-комментарии для документации (Qt сам их не подставляет, но
дизайнеру удобно).
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class Theme(str, Enum):
    DARK = "dark"
    LIGHT = "light"


_THEME_DIR = Path(__file__).parent


# Цветовые токены — единый источник правды для QSS и для Python-кода
# (графики matplotlib, custom-painted виджеты).
TOKENS = {
    Theme.DARK: {
        "bg":          "#0F1419",   # фон окна
        "surface":     "#161B22",   # карточки, панели
        "elevated":    "#1F252D",   # hover, выделение карточек
        "border":      "#2A323D",   # тонкие разделители
        "border_str":  "#3A4452",   # сильные разделители (focus)
        "text":        "#E5E9F0",   # основной текст
        "text_muted":  "#8B95A5",   # вторичный
        "text_dim":    "#5B6573",   # подписи, hint
        "accent":      "#3B9EFF",   # синий акцент (кнопки, ссылки, focus)
        "accent_hov":  "#5BAEFF",
        "accent_dim":  "#1F4A7A",   # фон выделенной строки
        "success":     "#4ADE80",
        "warning":     "#FBBF24",
        "warning_bg":  "#3A2E12",   # фон ленты «результаты устарели»
        "danger":      "#F87171",
        "sidebar_bg":  "#0B0F14",
    },
    Theme.LIGHT: {
        "bg":          "#FFFFFF",
        "surface":     "#F7F8FA",
        "elevated":    "#EEF1F6",
        "border":      "#E1E5EB",
        "border_str":  "#C3CAD6",
        "text":        "#1A1F2C",
        "text_muted":  "#5B6573",
        "text_dim":    "#8B95A5",
        "accent":      "#1F6FEB",
        "accent_hov":  "#0F5FD8",
        "accent_dim":  "#DDE9FB",
        "success":     "#16A34A",
        "warning":     "#D97706",
        "warning_bg":  "#FCEFDC",   # фон ленты «результаты устарели»
        "danger":      "#DC2626",
        "sidebar_bg":  "#F0F2F6",
    },
}


_current_theme: Theme = Theme.DARK


def current_theme() -> Theme:
    return _current_theme


def tokens(theme: Theme | None = None) -> dict[str, str]:
    """Цветовые токены текущей или указанной темы."""
    return TOKENS[theme or _current_theme]


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Применяет тему ко всему приложению."""
    global _current_theme
    _current_theme = theme

    qss_path = _THEME_DIR / f"{theme.value}.qss"
    template = qss_path.read_text(encoding="utf-8")
    # Подставляем токены: {{accent}} → #3B9EFF
    qss = template
    for key, value in TOKENS[theme].items():
        qss = qss.replace("{{" + key + "}}", value)
    app.setStyleSheet(qss)

    # Палитра тоже нужна — для виджетов, которые не подхватывают QSS
    # (стандартные диалоги, tooltip и пр.)
    pal = QPalette()
    t = TOKENS[theme]
    pal.setColor(QPalette.Window, QColor(t["bg"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.Base, QColor(t["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["elevated"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["surface"]))
    pal.setColor(QPalette.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor(t["elevated"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(t["text_dim"]))
    app.setPalette(pal)
