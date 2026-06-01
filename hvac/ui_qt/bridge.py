# -*- coding: utf-8 -*-
"""Мост между event bus HVACProject и Qt-сигналами.

HVACProject публикует события через `emit("data_loaded", ...)`. Этот класс
подписывается на все известные события и переизлучает их как Qt-сигналы,
чтобы любой QObject мог подключиться стандартным `.connect()`.

Использование:
    bridge = ProjectBridge(project)
    bridge.dataLoaded.connect(my_panel.refresh)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from hvac.project import HVACProject


class ProjectBridge(QObject):
    """Qt-обёртка над event bus проекта."""

    # Известные события HVACProject — добавлять сюда новые по мере появления
    projectLoaded = Signal()
    dataLoaded = Signal()
    calculationDone = Signal()
    ventilationDone = Signal(int)        # skipped
    zonesChanged = Signal()
    ahuLoadsCalculated = Signal()
    spacesChanged = Signal()
    constructionsChanged = Signal()
    smokeSystemsChanged = Signal()
    smokeLoadsCalculated = Signal()
    equipmentChanged = Signal()

    # Глобальные служебные сигналы UI (не от проекта)
    busyChanged = Signal(bool, str)      # (busy, status_text)
    statusMessage = Signal(str, int)     # (text, timeout_ms)
    dirtyChanged = Signal(bool)          # есть несохранённые изменения

    _EVENT_MAP = {
        "project_loaded": "projectLoaded",
        "data_loaded": "dataLoaded",
        "calculation_done": "calculationDone",
        "ventilation_done": "ventilationDone",
        "zones_changed": "zonesChanged",
        "ahu_loads_calculated": "ahuLoadsCalculated",
        "spaces_changed": "spacesChanged",
        "constructions_changed": "constructionsChanged",
        "smoke_systems_changed": "smokeSystemsChanged",
        "smoke_loads_calculated": "smokeLoadsCalculated",
        "equipment_changed": "equipmentChanged",
    }

    def __init__(self, project: HVACProject, parent: QObject | None = None):
        super().__init__(parent)
        self._project = project
        for event_name, signal_name in self._EVENT_MAP.items():
            project.subscribe(event_name, self._make_relay(signal_name))

    def _make_relay(self, signal_name: str):
        """Создаёт callback, переизлучающий kwargs в Qt-сигнал."""
        signal = getattr(self, signal_name)

        def _relay(**kwargs: Any) -> None:
            try:
                if kwargs:
                    # Передаём первое значение — большинство сигналов одно-аргументные
                    signal.emit(next(iter(kwargs.values())))
                else:
                    signal.emit()
            except Exception:
                import logging
                logging.exception("Bridge: ошибка при relay %s", signal_name)

        return _relay

    @property
    def project(self) -> HVACProject:
        return self._project
