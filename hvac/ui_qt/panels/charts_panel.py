# -*- coding: utf-8 -*-
"""ChartsPanel — графики на matplotlib через QtAgg-backend.

Использует существующий реестр графиков `hvac.reports.list_charts()` /
`draw_chart()`. Тема matplotlib переключается синхронно с темой
приложения (dark/light).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import (   # noqa: E402
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavToolbar,
)
from matplotlib.figure import Figure   # noqa: E402

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.reports import draw_chart, list_charts
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.theme import current_theme, tokens, Theme


class ChartsPanel(QWidget):
    """Панель графиков."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._current_chart: Optional[str] = None

        self._build_ui()
        self._wire()
        self._apply_mpl_theme()
        # Первый график при появлении данных
        if self.project.spaces and list_charts():
            self._current_chart = list_charts()[0]
            self.combo.setCurrentText(self._current_chart)
            self._redraw()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # Тулбар: выбор графика + кнопка обновления
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.title_lbl = QLabel(_t("panel.charts.title"))
        self.title_lbl.setProperty("role", "h1")
        bar.addWidget(self.title_lbl)
        bar.addSpacing(20)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(360)
        for name in list_charts():
            self.combo.addItem(name)
        bar.addWidget(self.combo, stretch=1)

        self.refresh_btn = QPushButton(_t("btn.refresh"))
        self.refresh_btn.setProperty("role", "ghost")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        bar.addWidget(self.refresh_btn)

        bar.addStretch(0)
        outer.addLayout(bar)

        # Канвас + навтулбар matplotlib
        self.figure = Figure(figsize=(8, 5), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(self.canvas.sizePolicy())  # noqa
        outer.addWidget(self.canvas, stretch=1)

        self.nav = NavToolbar(self.canvas, self)
        # Скрываем дефолтные кнопки save/configure которые ломают тему
        for action in self.nav.actions():
            if action.text() in ("Customize", "Save"):
                action.setVisible(False)
        outer.addWidget(self.nav)

        self.empty_lbl = QLabel(_t("common.empty_no_data"))
        self.empty_lbl.setProperty("role", "muted")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.empty_lbl)

    def _wire(self) -> None:
        self.combo.currentTextChanged.connect(self._on_combo)
        self.refresh_btn.clicked.connect(self._redraw)

        self.bridge.dataLoaded.connect(self._redraw)
        self.bridge.projectLoaded.connect(self._redraw)
        self.bridge.calculationDone.connect(self._redraw)
        self.bridge.ventilationDone.connect(self._redraw)

    # ---------- Темизация matplotlib ----------
    def _apply_mpl_theme(self) -> None:
        t = tokens()
        is_dark = current_theme() == Theme.DARK
        rc = {
            "figure.facecolor": t["bg"],
            "axes.facecolor": t["surface"],
            "axes.edgecolor": t["border"],
            "axes.labelcolor": t["text"],
            "axes.titlecolor": t["text"],
            "xtick.color": t["text_muted"],
            "ytick.color": t["text_muted"],
            "grid.color": t["border"],
            "grid.alpha": 0.5,
            "text.color": t["text"],
            "savefig.facecolor": t["bg"],
            "legend.facecolor": t["elevated"] if is_dark else t["surface"],
            "legend.edgecolor": t["border"],
            "legend.labelcolor": t["text"],
        }
        matplotlib.rcParams.update(rc)
        self.figure.patch.set_facecolor(t["bg"])

    # ---------- Перерисовка ----------
    def _on_combo(self, name: str) -> None:
        self._current_chart = name
        self._redraw()

    def _redraw(self, *args: object) -> None:
        self._apply_mpl_theme()
        self.figure.clear()

        if not self.project.spaces:
            self.canvas.setVisible(False)
            self.nav.setVisible(False)
            self.empty_lbl.setText(_t("common.empty_no_data"))
            self.empty_lbl.setVisible(True)
            self.canvas.draw_idle()
            return

        # Большинство графиков требуют выполненного расчёта
        has_results = any(s.heat_loss_w or s.heat_gain_w
                          for s in self.project.spaces)
        if not has_results:
            self.canvas.setVisible(False)
            self.nav.setVisible(False)
            self.empty_lbl.setText(_t("common.empty_no_results"))
            self.empty_lbl.setVisible(True)
            self.canvas.draw_idle()
            return

        self.canvas.setVisible(True)
        self.nav.setVisible(True)
        self.empty_lbl.setVisible(False)

        name = self._current_chart or self.combo.currentText()
        try:
            draw_chart(name, self.project, self.figure)
        except Exception as e:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, _t("panel.charts.err.draw").format(err=e),
                    ha="center", va="center", color=tokens()["danger"])
            ax.set_axis_off()
        self.canvas.draw_idle()

    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.charts.title"))
        self.refresh_btn.setText(_t("btn.refresh"))
        self._redraw()
