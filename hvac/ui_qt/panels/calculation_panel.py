# -*- coding: utf-8 -*-
"""CalculationPanel — запуск расчётов с прогрессом и сводкой.

Расчёты выполняются в QThread, чтобы UI не блокировался. По завершении
ProjectBridge получит событие calculation_done и все панели обновятся
автоматически.
"""
from __future__ import annotations

import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card


# ===========================================================================
# Worker thread
# ===========================================================================


class CalcWorker(QObject):
    """Выполняет произвольную callable в отдельном потоке.

    Поскольку HVACProject — обычная python-структура без Qt-зависимостей,
    его можно безопасно использовать из не-main потока. Сигналы Qt при
    эмите из worker-потока автоматически очередятся в main-loop.
    """

    finished = Signal()
    failed = Signal(str, str)   # (message, traceback)

    def __init__(self, fn: Callable[[], None]):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self._fn()
            self.finished.emit()
        except Exception as e:
            self.failed.emit(str(e), traceback.format_exc())


# ===========================================================================
# Карточка действия
# ===========================================================================


class ActionCard(Card):
    """Карточка одного типа расчёта: заголовок + описание + кнопка."""

    run = Signal()

    def __init__(self, title: str, subtitle: str, button_text: str,
                 primary: bool = False, parent: QWidget | None = None):
        super().__init__(title, subtitle, parent)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.status = QLabel("—")
        self.status.setProperty("role", "muted")
        row.addWidget(self.status, stretch=1)

        self.btn = QPushButton(button_text)
        if primary:
            self.btn.setProperty("role", "primary")
        self.btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn.clicked.connect(self.run)
        row.addWidget(self.btn)

        self.body().addLayout(row)

    def set_status(self, text: str, role: str = "muted") -> None:
        self.status.setText(text)
        self.status.setProperty("role", role)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def set_busy(self, busy: bool) -> None:
        self.btn.setEnabled(not busy)


# ===========================================================================
# Сводка результатов
# ===========================================================================


class SummaryGrid(QWidget):
    """Карточки-числа: Σ зима, Σ лето, S, плотность."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cards: dict[str, tuple[QLabel, QLabel]] = {}

        grid = QGridLayout(self)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        items = [
            ("loss",     _t("panel.calc.summary.loss"),    "кВт"),
            ("gain",     _t("panel.calc.summary.gain"),    "кВт"),
            ("area",     _t("panel.calc.summary.area"),    "м²"),
            ("density",  _t("panel.calc.summary.density"), "Вт/м²"),
            ("supply",   _t("panel.calc.summary.supply"),  "м³/ч"),
            ("exhaust",  _t("panel.calc.summary.exhaust"), "м³/ч"),
        ]
        for i, (key, title, unit) in enumerate(items):
            grid.addWidget(self._make_card(key, title, unit),
                           i // 3, i % 3)

    def _make_card(self, key: str, title: str, unit: str) -> Card:
        card = Card("", "")
        card.body().setSpacing(2)

        value_lbl = QLabel("—")
        value_lbl.setStyleSheet("font-size: 26px; font-weight: 700;")
        unit_lbl = QLabel(f"{title} · <span style='opacity:0.6'>{unit}</span>")
        unit_lbl.setTextFormat(Qt.RichText)
        unit_lbl.setProperty("role", "muted")
        card.body().addWidget(value_lbl)
        card.body().addWidget(unit_lbl)
        self._cards[key] = (value_lbl, unit_lbl)
        return card

    def update(self, project: HVACProject) -> None:
        spaces = project.spaces
        n = len(spaces)
        if n == 0:
            for v, _ in self._cards.values():
                v.setText("—")
            return

        loss_kw = sum(s.heat_loss_w for s in spaces) / 1000.0
        gain_kw = sum(s.heat_gain_w for s in spaces) / 1000.0
        area = sum(s.area_m2 for s in spaces)
        density = (loss_kw * 1000.0 / area) if area > 0 else 0.0
        supply = sum(s.supply_m3h for s in spaces)
        exhaust = sum(s.exhaust_m3h for s in spaces)

        self._cards["loss"][0].setText(f"{loss_kw:.1f}")
        self._cards["gain"][0].setText(f"{gain_kw:.1f}")
        self._cards["area"][0].setText(f"{area:,.0f}".replace(",", " "))
        self._cards["density"][0].setText(f"{density:.1f}")
        self._cards["supply"][0].setText(
            f"{supply:,.0f}".replace(",", " ") if supply else "—")
        self._cards["exhaust"][0].setText(
            f"{exhaust:,.0f}".replace(",", " ") if exhaust else "—")


# ===========================================================================
# Основная панель
# ===========================================================================


class CalculationPanel(QWidget):
    """Корневая панель расчётов."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._thread: Optional[QThread] = None
        self._worker: Optional[CalcWorker] = None

        self._build_ui()
        self._wire()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(28, 24, 28, 28)
        col.setSpacing(16)

        # Заголовок
        h = QLabel(_t("panel.calc.title"))
        h.setProperty("role", "h1")
        col.addWidget(h)
        sub = QLabel(_t("panel.calc.subtitle"))
        sub.setProperty("role", "muted")
        col.addWidget(sub)

        # Прогресс-бар на всю ширину (виден только во время работы)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)        # indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        col.addWidget(self.progress)

        # Сетка карточек-действий
        actions = QGridLayout()
        actions.setHorizontalSpacing(16)
        actions.setVerticalSpacing(16)
        col.addLayout(actions)

        self.card_heat = ActionCard(
            _t("panel.calc.heat.title"),
            _t("panel.calc.heat.desc"),
            _t("panel.calc.heat.btn"), primary=True,
        )
        self.card_heat.run.connect(self._run_heat)
        actions.addWidget(self.card_heat, 0, 0)

        self.card_vent = ActionCard(
            _t("panel.calc.vent.title"),
            _t("panel.calc.vent.desc"),
            _t("panel.calc.vent.btn"),
        )
        self.card_vent.run.connect(self._run_vent)
        actions.addWidget(self.card_vent, 0, 1)

        self.card_ahu = ActionCard(
            _t("panel.calc.ahu.title"),
            _t("panel.calc.ahu.desc"),
            _t("panel.calc.ahu.btn"),
        )
        self.card_ahu.run.connect(self._run_ahu)
        actions.addWidget(self.card_ahu, 1, 0)

        self.card_all = ActionCard(
            _t("panel.calc.all.title"),
            _t("panel.calc.all.desc"),
            _t("panel.calc.all.btn"),
        )
        self.card_all.run.connect(self._run_all)
        actions.addWidget(self.card_all, 1, 1)

        # Сводка
        col.addSpacing(8)
        h2 = QLabel(_t("panel.calc.summary"))
        h2.setProperty("role", "h2")
        col.addWidget(h2)

        self.summary = SummaryGrid()
        col.addWidget(self.summary)

        # Валидация (placeholder — детальную выведем в task #13)
        col.addSpacing(8)
        self.validation_lbl = QLabel("")
        self.validation_lbl.setProperty("role", "hint")
        self.validation_lbl.setWordWrap(True)
        col.addWidget(self.validation_lbl)

        col.addStretch(1)

    def _wire(self) -> None:
        self.bridge.dataLoaded.connect(self._refresh)
        self.bridge.projectLoaded.connect(self._refresh)
        self.bridge.calculationDone.connect(self._refresh)
        self.bridge.ventilationDone.connect(self._refresh)
        self.bridge.ahuLoadsCalculated.connect(self._refresh)
        self._refresh()

    # ---------- Реакции ----------
    def _refresh(self, *args: object) -> None:
        n = len(self.project.spaces)
        has_heat = n > 0 and any(s.heat_loss_w for s in self.project.spaces)
        has_vent = n > 0 and any(s.supply_m3h for s in self.project.spaces)
        has_ahu = bool(self.project.ahu_loads)

        done_text = _t("panel.calc.status.done")
        nope_text = _t("panel.calc.status.not_done")
        self.card_heat.set_status(done_text if has_heat else nope_text,
                                    "success" if has_heat else "muted")
        self.card_vent.set_status(done_text if has_vent else nope_text,
                                    "success" if has_vent else "muted")
        self.card_ahu.set_status(done_text if has_ahu else nope_text,
                                   "success" if has_ahu else "muted")

        all_btn_enabled = n > 0
        for card in (self.card_heat, self.card_vent,
                     self.card_ahu, self.card_all):
            card.btn.setEnabled(all_btn_enabled and self._thread is None)

        self.summary.update(self.project)

        # Валидация — короткая сводка
        problems = []
        try:
            problems = self.project.validate() or []
        except Exception:
            pass
        if not n:
            self.validation_lbl.setText(_t("panel.calc.validate.no_data"))
        elif problems:
            self.validation_lbl.setText(
                _t("panel.calc.validate.problems").format(
                    n=len(problems), first=problems[0]))
            self.validation_lbl.setProperty("role", "warning")
        else:
            self.validation_lbl.setText(_t("panel.calc.validate.ok"))
            self.validation_lbl.setProperty("role", "success")
        self.validation_lbl.style().unpolish(self.validation_lbl)
        self.validation_lbl.style().polish(self.validation_lbl)

    # ---------- Запуск расчётов ----------
    def _run_heat(self) -> None:
        self._start(_t("panel.calc.run.heat"), self.project.recalculate)

    def _run_vent(self) -> None:
        self._start(_t("panel.calc.run.vent"),
                     self.project.calculate_ventilation)

    def _run_ahu(self) -> None:
        self._start(_t("panel.calc.run.ahu"),
                     self.project.calculate_ahu_loads)

    def _run_all(self) -> None:
        def chain() -> None:
            self.project.recalculate()
            self.project.calculate_ventilation()
            self.project.calculate_ahu_loads()
        self._start(_t("panel.calc.run.all"), chain)

    def _start(self, status: str, fn: Callable[[], None]) -> None:
        if self._thread is not None:
            return  # уже идёт другой расчёт
        if not self.project.spaces:
            return

        self.progress.setVisible(True)
        for card in (self.card_heat, self.card_vent,
                     self.card_ahu, self.card_all):
            card.set_busy(True)
        self.bridge.statusMessage.emit(status, 0)

        self._thread = QThread(self)
        self._worker = CalcWorker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_finished(self) -> None:
        self._cleanup()
        self.bridge.statusMessage.emit(_t("panel.calc.run.done"), 4000)

    def _on_failed(self, msg: str, tb: str) -> None:
        self._cleanup()
        self.bridge.statusMessage.emit(_t("panel.calc.run.err"), 4000)
        m = QMessageBox(self)
        m.setIcon(QMessageBox.Critical)
        m.setWindowTitle(_t("panel.calc.run.err"))
        m.setText(msg)
        m.setDetailedText(tb)
        m.exec()

    def _cleanup(self) -> None:
        self.progress.setVisible(False)
        for card in (self.card_heat, self.card_vent,
                     self.card_ahu, self.card_all):
            card.set_busy(False)
        if self._thread is not None:
            self._thread.wait(2000)
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._refresh()
