# -*- coding: utf-8 -*-
"""ExtensionsPanel — расширения v3.7: ГВС, энергопаспорт, точка росы,
   подбор воздуховодов и труб."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card


class ExtensionsPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

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

        self.title_lbl = QLabel(_t("panel.ext.title"))
        self.title_lbl.setProperty("role", "h1")
        col.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel(_t("panel.ext.subtitle"))
        self.subtitle_lbl.setProperty("role", "muted")
        col.addWidget(self.subtitle_lbl)
        col.addSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        col.addLayout(grid)

        # Каждый item: (key, title-i18n, desc-i18n, runner, summary_fn)
        self.cards = {}
        items = [
            ("dhw",    "panel.ext.dhw.title",    "panel.ext.dhw.desc",
             lambda: self.project.calculate_dhw(strategy="by_type"),
             self._dhw_summary),
            ("energy", "panel.ext.energy.title", "panel.ext.energy.desc",
             lambda: self.project.calculate_energy_passport(),
             self._energy_summary),
            ("dew",    "panel.ext.dew.title",    "panel.ext.dew.desc",
             lambda: self.project.check_condensation_risk(),
             self._dew_summary),
            ("ducts",  "panel.ext.ducts.title",  "panel.ext.ducts.desc",
             lambda: self.project.size_ducts(shape="round"),
             self._ducts_summary),
            ("pipes",  "panel.ext.pipes.title",  "panel.ext.pipes.desc",
             lambda: self.project.size_pipes(pipe_material="steel"),
             self._pipes_summary),
        ]
        for i, (key, title_key, desc_key, runner, summary_fn) in enumerate(items):
            card = self._make_action_card(key, title_key, desc_key,
                                            runner, summary_fn)
            self.cards[key] = card
            grid.addWidget(card, i // 2, i % 2)

        col.addStretch(1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone):
            sig.connect(self._refresh_all_summaries)
        self._refresh_all_summaries()

    def _make_action_card(self, key: str, title_key: str, desc_key: str,
                           runner: Callable[[], None],
                           summary_fn: Callable[[], str]) -> Card:
        card = Card(_t(title_key), _t(desc_key))
        # Хранение ключей i18n на самой карточке — нужно для retranslate_ui
        card._i18n_title_key = title_key
        card._i18n_desc_key = desc_key

        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setMaximumHeight(80)
        summary.setPlaceholderText(_t("panel.ext.summary.empty"))
        card.body().addWidget(summary)
        card._summary = summary
        card._summary_fn = summary_fn

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton(_t("panel.ext.btn_run"))
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        card._btn = btn

        def go() -> None:
            try:
                runner()
                self._refresh_all_summaries()
                self.bridge.statusMessage.emit(
                    _t("panel.ext.status.ok").format(title=_t(title_key)),
                    4000)
            except Exception as e:
                self.bridge.statusMessage.emit(
                    _t("panel.ext.status.err").format(
                        title=_t(title_key), err=e), 6000)
        btn.clicked.connect(go)
        row.addWidget(btn)
        card.body().addLayout(row)
        return card

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.ext.title"))
        self.subtitle_lbl.setText(_t("panel.ext.subtitle"))
        for card in self.cards.values():
            card.set_title(_t(card._i18n_title_key))
            card.set_subtitle(_t(card._i18n_desc_key))
            card._summary.setPlaceholderText(_t("panel.ext.summary.empty"))
            card._btn.setText(_t("panel.ext.btn_run"))
        self._refresh_all_summaries()

    def _refresh_all_summaries(self, *args: Any) -> None:
        for card in self.cards.values():
            try:
                text = card._summary_fn()
            except Exception:
                text = ""
            card._summary.setPlainText(text or "")

    # ---- Сводки ----
    def _dhw_summary(self) -> str:
        systems = getattr(self.project, "dhw_systems", {}) or {}
        if not systems:
            return ""
        total_v = sum(getattr(s, "demand", None) and s.demand.v_day_m3 or 0
                      for s in systems.values())
        total_q = sum(getattr(s, "demand", None) and s.demand.q_peak_kw or 0
                      for s in systems.values())
        return _t("panel.ext.sum.dhw").format(
            n=len(systems), v=total_v, q=total_q)

    def _energy_summary(self) -> str:
        ep = getattr(self.project, "energy_passport", None)
        if not ep:
            return ""
        if ep.shnq_compliant is None:
            shnq = _t("panel.ext.sum.energy.shnq_na")
        else:
            key = ("panel.ext.sum.energy.shnq_ok" if ep.shnq_compliant
                   else "panel.ext.sum.energy.shnq_fail")
            shnq = _t(key).format(qd=ep.q_design_specific_w_m2,
                                  qov=f"{ep.q_ov_normative_w_m2:.0f}")
        return _t("panel.ext.sum.energy").format(
            cls=ep.energy_class or "?",
            q=ep.qh_specific_kwh_m2,
            dev=ep.deviation_percent,
            shnq=shnq)

    def _dew_summary(self) -> str:
        results = getattr(self.project, "condensation_results", []) or []
        if not results:
            return ""
        risky = [r for r in results if getattr(r, "is_risky", False)]
        return _t("panel.ext.sum.dew").format(
            n=len(results), risky=len(risky))

    def _ducts_summary(self) -> str:
        nets = getattr(self.project, "duct_networks", {}) or {}
        if not nets:
            return ""
        total_sections = sum(len(n.sections) for n in nets.values()
                             if hasattr(n, "sections"))
        return _t("panel.ext.sum.ducts").format(
            n=len(nets), s=total_sections)

    def _pipes_summary(self) -> str:
        nets = getattr(self.project, "pipe_networks", {}) or {}
        if not nets:
            return ""
        total_sections = sum(len(n.sections) for n in nets.values()
                             if hasattr(n, "sections"))
        return _t("panel.ext.sum.pipes").format(
            n=len(nets), s=total_sections)
