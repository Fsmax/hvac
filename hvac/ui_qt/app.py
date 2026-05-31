# -*- coding: utf-8 -*-
"""Точка входа Qt-приложения."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from hvac.project import HVACProject
from hvac.ui_qt import settings as user_settings
from hvac.ui_qt.main_window import MainWindow
from hvac.ui_qt.theme import apply_theme, Theme


def _load_app_icon() -> QIcon:
    """Загружает иконку приложения, проверяя несколько путей.

    Работает и в dev-режиме (resources/ рядом с пакетом), и в
    PyInstaller-сборке (data-файлы лежат рядом с .exe).
    """
    candidates = []
    # 1. Рядом с hvac/ui_qt/app.py → ../../resources
    pkg_root = Path(__file__).resolve().parent.parent.parent
    candidates.append(pkg_root / "resources" / "app.ico")
    candidates.append(pkg_root / "resources" / "app.png")
    # 2. Рядом с .exe (PyInstaller onedir)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "resources" / "app.ico")
        candidates.append(exe_dir / "app.ico")
    for path in candidates:
        if path.exists():
            return QIcon(str(path))
    return QIcon()


def _pick_default_font() -> QFont:
    """Подбирает лучший доступный шрифт интерфейса.

    Приоритет: Segoe UI Variable (Win11) → Inter → Segoe UI → системный.
    """
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Display", "Inter", "Segoe UI"):
        if name in families:
            f = QFont(name, 10)
            f.setHintingPreference(QFont.PreferFullHinting)
            return f
    return QFont()


def run_gui() -> int:
    """Запускает GUI. Возвращает код выхода."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("HVAC Calculator")
    app.setApplicationDisplayName("HVAC Calculator")
    app.setOrganizationName("HVAC")
    app.setApplicationVersion("4.0")
    app.setFont(_pick_default_font())
    app.setWindowIcon(_load_app_icon())

    saved_theme = user_settings.load().get("theme", "dark")
    apply_theme(app, Theme.LIGHT if saved_theme == "light" else Theme.DARK)

    project = HVACProject()
    window = MainWindow(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
