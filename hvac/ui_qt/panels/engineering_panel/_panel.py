# -*- coding: utf-8 -*-
"""EngineeringPanel — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget
from hvac.project import HVACProject
from hvac.i18n import on_language_change, t as _t
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card
from hvac.ui_qt.panels.engineering_panel._psychro import _PsychroTab
from hvac.ui_qt.panels.engineering_panel._ducts import _DuctTab
from hvac.ui_qt.panels.engineering_panel._hydraulics import _HydraulicsTab
from hvac.ui_qt.panels.engineering_panel._radiators import _RadiatorsTab
from hvac.ui_qt.panels.engineering_panel._acoustics import _AcousticsTab
from hvac.ui_qt.panels.engineering_panel._underfloor import _UnderfloorTab
from hvac.ui_qt.panels.engineering_panel._fancoils import _FancoilsTab
from hvac.ui_qt.panels.engineering_panel._vrf import _VRFTab
from hvac.ui_qt.panels.engineering_panel._energy import _EnergyTab
from hvac.ui_qt.panels.engineering_panel._comfort import _ComfortTab
from hvac.ui_qt.panels.engineering_panel._curtain import _CurtainTab
from hvac.ui_qt.panels.engineering_panel._itp import _ITPTab


class EngineeringPanel(QWidget):
    """Подробная инженерия v4.1+v4.4 — 12 вкладок."""

    TAB_KEYS = (
        "panel.eng.tab.psychro",
        "panel.eng.tab.duct",
        "panel.eng.tab.hydro",
        "panel.eng.tab.radiators",
        "panel.eng.tab.acoustics",
        "panel.eng.tab.underfloor",
        "panel.eng.tab.fancoils",
        "panel.eng.tab.vrf",
        "panel.eng.tab.energy",
        "panel.eng.tab.comfort",
        "panel.eng.tab.curtain",
        "panel.eng.tab.itp",
    )

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        head = QHBoxLayout()
        self._h = QLabel(_t("panel.eng.title"))
        self._h.setProperty("role", "h1")
        head.addWidget(self._h)
        head.addStretch(1)
        outer.addLayout(head)

        self._card = Card(
            _t("panel.eng.card.title"), _t("panel.eng.card.sub"))
        self._card._i18n_title_key = "panel.eng.card.title"
        self._card._i18n_sub_key = "panel.eng.card.sub"
        self.tabs = QTabWidget()
        self._tabs_widgets = [
            _PsychroTab(project, bridge),
            _DuctTab(project, bridge),
            _HydraulicsTab(project, bridge),
            _RadiatorsTab(project, bridge),
            _AcousticsTab(project, bridge),
            _UnderfloorTab(project, bridge),
            _FancoilsTab(project, bridge),
            _VRFTab(project, bridge),
            _EnergyTab(project, bridge),
            _ComfortTab(project, bridge),
            _CurtainTab(project, bridge),
            _ITPTab(project, bridge),
        ]
        for w, key in zip(self._tabs_widgets, self.TAB_KEYS):
            self.tabs.addTab(w, _t(key))
        self._card.body().addWidget(self.tabs)
        outer.addWidget(self._card, stretch=1)

        on_language_change(lambda _lang: self.retranslate_ui())

    def retranslate_ui(self) -> None:
        self._h.setText(_t("panel.eng.title"))
        if hasattr(self._card, "set_title"):
            self._card.set_title(_t("panel.eng.card.title"))
            self._card.set_subtitle(_t("panel.eng.card.sub"))
        for i, key in enumerate(self.TAB_KEYS):
            self.tabs.setTabText(i, _t(key))
        for w in self._tabs_widgets:
            if hasattr(w, "retranslate_ui"):
                w.retranslate_ui()

