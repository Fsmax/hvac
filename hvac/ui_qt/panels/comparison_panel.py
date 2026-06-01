# -*- coding: utf-8 -*-
"""ComparisonPanel — сравнение текущего проекта со вторым (.hvac.json).

Грузит второй проект в отдельный экземпляр HVACProject (не затрагивая
текущий) и показывает таблицу ключевых метрик: текущий / сравнение / Δ / Δ%.
Полезно при оптимизации ограждений, вариантов вентиляции и т.п.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from hvac.i18n import t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.theme import tokens
from hvac.ui_qt.widgets.card import Card


def comparison_metrics(project: HVACProject) -> Dict[str, float]:
    """Сводные метрики проекта для сравнения. Чистая функция (без Qt)."""
    spaces = project.spaces
    area = sum(s.area_m2 for s in spaces)
    ql = sum(s.heat_loss_w for s in spaces)
    qg = sum(s.heat_gain_w for s in spaces)
    return {
        "n_spaces": float(len(spaces)),
        "area": area,
        "ql_kw": ql / 1000.0,
        "qg_kw": qg / 1000.0,
        "q_density": (ql / area) if area else 0.0,
        "supply": sum(s.supply_m3h for s in spaces),
        "exhaust": sum(s.exhaust_m3h for s in spaces),
    }


# (ключ метрики, i18n-ключ строки, число знаков после запятой)
_METRIC_ROWS = [
    ("n_spaces",  "panel.comparison.row.n_spaces",  0),
    ("area",      "panel.comparison.row.area",      1),
    ("ql_kw",     "panel.comparison.row.ql",        2),
    ("qg_kw",     "panel.comparison.row.qg",        2),
    ("q_density", "panel.comparison.row.density",   1),
    ("supply",    "panel.comparison.row.supply",    0),
    ("exhaust",   "panel.comparison.row.exhaust",   0),
]

_COL_KEYS = [
    "panel.comparison.col.metric", "panel.comparison.col.current",
    "panel.comparison.col.other",  "panel.comparison.col.delta",
    "panel.comparison.col.delta_pct",
]


def _fmt(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}".replace(",", " ")


class ComparisonPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._other: Optional[HVACProject] = None
        self._other_name: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.comparison.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.load_btn = QPushButton(_t("panel.comparison.btn_load"))
        self.load_btn.setProperty("role", "primary")
        self.load_btn.setCursor(Qt.PointingHandCursor)
        self.load_btn.clicked.connect(self._load_other)
        head.addWidget(self.load_btn)
        outer.addLayout(head)

        self.info_card = Card(_t("panel.comparison.title"),
                              _t("panel.comparison.hint"))
        self.info_lbl = QLabel(_t("panel.comparison.not_loaded"))
        self.info_lbl.setProperty("role", "muted")
        self.info_card.body().addWidget(self.info_lbl)
        outer.addWidget(self.info_card)

        self.table = QTableWidget(len(_METRIC_ROWS), len(_COL_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _COL_KEYS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        for c in range(1, len(_COL_KEYS)):
            self.table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.calculationDone, bridge.ventilationDone):
            sig.connect(self._refresh)
        self._refresh()

    # ---- логика ----
    def _load_other(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("panel.comparison.dlg_title"), "",
            _t("panel.comparison.dlg_filter"))
        if not path:
            return
        from hvac.io_json import load_project
        other = HVACProject()
        try:
            load_project(other, path)
        except Exception as e:
            QMessageBox.critical(self, _t("dialog.error.title"), str(e))
            return
        self._other = other
        from pathlib import Path
        self._other_name = Path(path).name
        self._refresh()

    def _refresh(self, *args: Any) -> None:
        cur = comparison_metrics(self.project)
        other = comparison_metrics(self._other) if self._other else None

        if self._other is None:
            self.info_lbl.setText(_t("panel.comparison.not_loaded"))
        else:
            self.info_lbl.setText(_t("panel.comparison.loaded").format(
                name=self._other_name,
                cur=self.project.params.project_name or "—",
                other=self._other.params.project_name or "—"))

        warn = QColor(tokens()["warning"])
        for row, (key, label_key, dec) in enumerate(_METRIC_ROWS):
            cv = cur[key]
            self._set(row, 0, _t(label_key), align_left=True)
            self._set(row, 1, _fmt(cv, dec))
            if other is None:
                for c in (2, 3, 4):
                    self._set(row, c, "—")
                continue
            ov = other[key]
            delta = ov - cv
            self._set(row, 2, _fmt(ov, dec))
            sign = "+" if delta >= 0 else "−"
            self._set(row, 3, f"{sign}{_fmt(abs(delta), dec)}",
                      brush=warn if abs(delta) > 1e-9 else None)
            if abs(cv) > 1e-9:
                pct = delta / cv * 100.0
                psign = "+" if pct >= 0 else "−"
                self._set(row, 4, f"{psign}{_fmt(abs(pct), 1)}%",
                          brush=warn if abs(pct) > 0.05 else None)
            else:
                self._set(row, 4, "—")

    def _set(self, row: int, col: int, text: str,
             align_left: bool = False, brush: Optional[QBrush] = None) -> None:
        item = QTableWidgetItem(text)
        if align_left:
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if brush is not None:
            item.setForeground(brush)
        self.table.setItem(row, col, item)

    # ---- локализация ----
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.comparison.title"))
        self.load_btn.setText(_t("panel.comparison.btn_load"))
        self.info_card.set_title(_t("panel.comparison.title"))
        self.info_card.set_subtitle(_t("panel.comparison.hint"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _COL_KEYS])
        self._refresh()
