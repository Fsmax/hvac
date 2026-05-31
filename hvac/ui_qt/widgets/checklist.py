# -*- coding: utf-8 -*-
"""Dockable чек-лист «Готовность проекта» — справа от рабочей области.

Шесть состояний: загружены CSV, выбран город, U утверждены, зоны назначены,
расчёт выполнен, вентиляция посчитана. Клик переключает в соответствующую
панель.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from hvac.i18n import on_language_change, t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


@dataclass
class _Step:
    key: str
    title_key: str
    panel_key: str
    check: Callable[[HVACProject], bool]
    hint: Callable[[HVACProject], str]


STEPS: List[_Step] = [
    _Step(
        "csv", "checklist.step_csv", "data",
        lambda p: len(p.spaces) > 0,
        lambda p: (
            _t("checklist.csv_hint").format(n=len(p.spaces))
            if p.spaces else _t("checklist.csv_hint_empty")
        ),
    ),
    _Step(
        "city", "checklist.step_city", "data",
        lambda p: bool(p.params.city),
        lambda p: p.params.city or _t("checklist.city_hint_empty"),
    ),
    _Step(
        "u_values", "checklist.step_u", "constructions",
        lambda p: bool(p.constructions) and all(
            c.u_value > 0 for c in p.constructions.values()),
        lambda p: (
            _t("checklist.u_hint").format(n=len(p.constructions))
            if p.constructions
            else _t("checklist.u_hint_empty")
        ),
    ),
    _Step(
        "zones", "checklist.step_zones", "zones",
        lambda p: any(s.system_heating for s in p.spaces),
        lambda p: (
            _t("checklist.zones_hint").format(
                n=len({s.system_heating for s in p.spaces if s.system_heating}))
            if any(s.system_heating for s in p.spaces)
            else _t("checklist.zones_hint_empty")
        ),
    ),
    _Step(
        "calc", "checklist.step_calc", "calculation",
        lambda p: any(s.heat_loss_w for s in p.spaces),
        lambda p: (
            _t("checklist.calc_hint").format(
                kw=sum(s.heat_loss_w for s in p.spaces) / 1000)
            if any(s.heat_loss_w for s in p.spaces)
            else _t("checklist.calc_hint_empty")
        ),
    ),
    _Step(
        "vent", "checklist.step_vent", "ventilation",
        lambda p: any(s.supply_m3h for s in p.spaces),
        lambda p: (
            _t("checklist.vent_hint").format(
                m3h=f"{sum(s.supply_m3h for s in p.spaces):,.0f}".replace(",", " "))
            if any(s.supply_m3h for s in p.spaces)
            else _t("checklist.vent_hint_empty")
        ),
    ),
]


class ChecklistPanel(QWidget):
    """Узкая правая панель с чек-листом готовности."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 navigate: Callable[[str], None],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self.navigate = navigate
        self._rows: dict[str, _StepRow] = {}

        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        self._header = QLabel(_t("checklist.title"))
        self._header.setProperty("role", "h2")
        outer.addWidget(self._header)

        for step in STEPS:
            row = _StepRow(step, navigate)
            outer.addWidget(row)
            self._rows[step.key] = row

        outer.addStretch(1)

        # Подписки
        for sig in (
            bridge.dataLoaded, bridge.projectLoaded, bridge.zonesChanged,
            bridge.calculationDone, bridge.ventilationDone,
            bridge.constructionsChanged, bridge.spacesChanged,
        ):
            sig.connect(self._refresh)
        on_language_change(lambda _lang: self.retranslate_ui())
        self._refresh()

    def _refresh(self, *args: Any) -> None:
        for step in STEPS:
            ok = bool(step.check(self.project))
            hint = step.hint(self.project)
            self._rows[step.key].set_state(ok, hint)

    def retranslate_ui(self) -> None:
        self._header.setText(_t("checklist.title"))
        for row in self._rows.values():
            row.retranslate_ui()
        self._refresh()


class _StepRow(QFrame):
    """Одна строка чек-листа: индикатор + название + подсказка."""

    def __init__(self, step: _Step, navigate: Callable[[str], None]):
        super().__init__()
        self._step = step
        self._navigate = navigate
        self.setProperty("role", "card")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.icon = QLabel("○")
        self.icon.setStyleSheet("font-size: 16px;")
        self.title = QLabel(_t(step.title_key))
        self.title.setStyleSheet("font-weight: 500;")
        top.addWidget(self.icon)
        top.addWidget(self.title, stretch=1)
        lay.addLayout(top)

        self.hint = QLabel("")
        self.hint.setProperty("role", "muted")
        self.hint.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.hint)

    def set_state(self, ok: bool, hint: str) -> None:
        from hvac.ui_qt.theme import tokens
        t = tokens()
        if ok:
            self.icon.setText("✓")
            self.icon.setStyleSheet(
                f"font-size: 16px; color: {t['success']};")
        else:
            self.icon.setText("○")
            self.icon.setStyleSheet(
                f"font-size: 16px; color: {t['text_dim']};")
        self.hint.setText(hint)

    def retranslate_ui(self) -> None:
        self.title.setText(_t(self._step.title_key))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._navigate(self._step.panel_key)
        super().mousePressEvent(event)
