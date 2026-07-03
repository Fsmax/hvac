# -*- coding: utf-8 -*-
"""Трекер актуальности расчётных слоёв (ответ на находку F06 ревизии UI).

Слои и зависимости: данные → нагрузки → вентиляция → приточные установки.
Правка данных помечает зависимые слои устаревшими; пересчёт слоя снимает
пометку с него и помечает нижележащие (вентиляция зависит от нагрузок через
воздушное отопление, AHU — от вентиляции).

Слой помечается только если у него вообще есть результаты: пользователю,
который ещё не считал вентиляцию, нечему устаревать.

Состояние живёт в памяти сессии: при загрузке проекта считаем результаты
согласованными (в файле нет отметок времени расчёта), лента появится после
первой правки.
"""
from __future__ import annotations

from typing import Set

from PySide6.QtCore import QObject, Signal

from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge

# Порядок важен: так слои перечисляются в ленте.
LAYERS = ("loads", "ventilation", "ahu")


class StalenessTracker(QObject):
    """Следит за событиями ProjectBridge и знает, какие слои устарели."""

    changed = Signal()

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.project = project
        self._stale: Set[str] = set()
        self._dismissed = False

        bridge.dataEdited.connect(self._on_data_edited)
        bridge.spacesChanged.connect(self._on_data_edited)
        bridge.constructionsChanged.connect(self._on_data_edited)
        bridge.zonesChanged.connect(self._on_zones_changed)
        bridge.calculationDone.connect(self._on_calc_done)
        bridge.ventilationDone.connect(self._on_vent_done)
        bridge.ahuLoadsCalculated.connect(self._on_ahu_done)
        bridge.projectLoaded.connect(self._reset)
        bridge.dataLoaded.connect(self._reset)

    # ---------- Чтение ----------
    def stale_layers(self) -> list[str]:
        """Устаревшие слои в порядке LAYERS."""
        return [k for k in LAYERS if k in self._stale]

    def is_dismissed(self) -> bool:
        return self._dismissed

    def dismiss(self) -> None:
        """Скрыть ленту до следующего изменения (пометки остаются)."""
        self._dismissed = True
        self.changed.emit()

    # ---------- Наличие результатов у слоя ----------
    def _has_loads(self) -> bool:
        return any(s.heat_loss_w for s in self.project.spaces)

    def _has_vent(self) -> bool:
        return any(s.supply_m3h or s.exhaust_m3h
                   for s in self.project.spaces)

    def _has_ahu(self) -> bool:
        return bool(getattr(self.project, "ahu_loads", None))

    # ---------- Переходы ----------
    def _mark(self, *layers: str) -> None:
        added = set(layers) - self._stale
        if not added:
            return
        self._stale |= added
        self._dismissed = False
        self.changed.emit()

    def _clear(self, *layers: str) -> None:
        if not self._stale & set(layers):
            return
        self._stale -= set(layers)
        self.changed.emit()

    def _on_data_edited(self, *_a) -> None:
        marks = []
        if self._has_loads():
            marks.append("loads")
        if self._has_vent():
            marks.append("ventilation")
        if self._has_ahu():
            marks.append("ahu")
        if marks:
            self._mark(*marks)

    def _on_zones_changed(self, *_a) -> None:
        # Перепривязка систем меняет группировку приточек, не нагрузки.
        if self._has_ahu():
            self._mark("ahu")

    def _on_calc_done(self, *_a) -> None:
        self._clear("loads")
        # Вентиляция зависит от нагрузок (воздушное отопление/охлаждение),
        # AHU — от вентиляции. В цепочке «Всё сразу» их события придут
        # следом и снимут пометки.
        marks = []
        if self._has_vent():
            marks.append("ventilation")
        if self._has_ahu():
            marks.append("ahu")
        if marks:
            self._mark(*marks)

    def _on_vent_done(self, *_a) -> None:
        self._clear("ventilation")
        if self._has_ahu():
            self._mark("ahu")

    def _on_ahu_done(self, *_a) -> None:
        self._clear("ahu")

    def _reset(self, *_a) -> None:
        self._stale.clear()
        self._dismissed = False
        self.changed.emit()
