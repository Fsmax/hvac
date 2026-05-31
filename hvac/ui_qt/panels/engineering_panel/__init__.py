# -*- coding: utf-8 -*-
"""Панель «Инженерия» (v4.1) — пакет.

Монолит разбит на модули по вкладкам (_psychro, _ducts, ...); главный
класс — в _panel. Публичный API без изменений:
    from hvac.ui_qt.panels.engineering_panel import EngineeringPanel
"""
from hvac.ui_qt.panels.engineering_panel._panel import EngineeringPanel

__all__ = ["EngineeringPanel"]
