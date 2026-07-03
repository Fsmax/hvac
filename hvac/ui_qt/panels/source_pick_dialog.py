# -*- coding: utf-8 -*-
"""SourcePickDialog — подбор котла / чиллера из каталога.

Показывает ВЕСЬ каталог (hvac/source_catalog.py) таблицей: для каждой
модели считается количество одинаковых агрегатов N = ceil(required / q)
и фактический запас каскада под требуемую мощность (редактируется в
диалоге, пересчёт живой). Модели, не покрывающие нагрузку разумным
каскадом (> max_units), показаны серым и не выбираются.

Результат `values()` — kwargs для `update_zone_system`: единичная
мощность (design_capacity_kw), количество (unit_count, + резервный по
флагу N+1), модель (selected_model) и КПД/COP из каталога.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QHBoxLayout, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.source_catalog import SourceModel, cascade_for, catalog_for_domain

# Колонки таблицы.
(C_MODEL, C_MANUF, C_FAMILY, C_Q, C_EFF, C_UNITS, C_TOTAL,
 C_MARGIN, C_NOTE) = range(9)
C_COUNT = 9

MAX_UNITS = 8


class _NumTableItem(QTableWidgetItem):
    """Сортировка по числу из Qt.UserRole+1, иначе по тексту."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        a = self.data(Qt.UserRole + 1)
        b = other.data(Qt.UserRole + 1)
        if a is not None and b is not None:
            return float(a) < float(b)
        return self.text() < other.text()


def _item(text: str, num: Optional[float] = None,
          align_right: bool = True) -> _NumTableItem:
    it = _NumTableItem(text)
    if num is not None:
        it.setData(Qt.UserRole + 1, float(num))
    if align_right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


class SourcePickDialog(QDialog):
    """Каталожный подбор источника: domain = 'heating' | 'cooling'."""

    def __init__(self, parent: Optional[QWidget], *, domain: str,
                 required_kw: float = 0.0, context: str = ""):
        super().__init__(parent)
        self.domain = domain
        self._models: List[SourceModel] = list(catalog_for_domain(domain))

        title_key = ("panel.srcpick.title.heating" if domain == "heating"
                     else "panel.srcpick.title.cooling")
        self.setWindowTitle(_t(title_key))
        self.setMinimumSize(860, 520)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        if context:
            ctx = QLabel(context)
            ctx.setProperty("role", "muted")
            ctx.setWordWrap(True)
            outer.addWidget(ctx)

        ctl = QHBoxLayout()
        ctl.addWidget(QLabel(_t("panel.srcpick.f.required")))
        self.required = QDoubleSpinBox()
        self.required.setRange(0.0, 1_000_000.0)
        self.required.setDecimals(0)
        self.required.setSingleStep(50.0)
        self.required.setValue(max(0.0, required_kw))
        self.required.valueChanged.connect(lambda *_: self._recompute())
        ctl.addWidget(self.required)
        self.reserve = QCheckBox(_t("panel.srcpick.f.reserve"))
        ctl.addWidget(self.reserve)
        ctl.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("panel.srcpick.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(lambda *_: self._apply_filter())
        ctl.addWidget(self.search)
        outer.addLayout(ctl)

        eff_key = ("panel.srcpick.col.eff" if domain == "heating"
                   else "panel.srcpick.col.eer")
        col_keys = ["panel.srcpick.col.model", "panel.srcpick.col.manufacturer",
                    "panel.srcpick.col.family", "panel.srcpick.col.q",
                    eff_key, "panel.srcpick.col.units",
                    "panel.srcpick.col.total", "panel.srcpick.col.margin",
                    "panel.srcpick.col.note"]
        self.table = QTableWidget(0, C_COUNT)
        self.table.setHorizontalHeaderLabels([_t(k) for k in col_keys])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        for c, w in enumerate([170, 120, 210, 90, 60, 60, 80, 80, 140]):
            self.table.setColumnWidth(c, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_ok)
        self.table.itemDoubleClicked.connect(self._double_clicked)
        outer.addWidget(self.table, stretch=1)

        hint = QLabel(_t("panel.srcpick.hint"))
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText(_t("btn.ok"))
        self.bb.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        outer.addWidget(self.bb)

        self._recompute()

    # ------------------------------------------------------------- расчёт
    def _recompute(self) -> None:
        """Перезаполняет таблицу под текущую требуемую мощность."""
        req = self.required.value()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._models))
        for r, m in enumerate(self._models):
            n = cascade_for(req, m.q_kw, MAX_UNITS)
            total = n * m.q_kw
            margin = (total - req) / req * 100.0 if req > 0 and n else 0.0
            eff = (getattr(m, "efficiency", 0.0) if self.domain == "heating"
                   else getattr(m, "eer", 0.0))
            fits = n > 0
            cells = [
                _item(m.name, align_right=False),
                _item(m.manufacturer, align_right=False),
                _item(m.family, align_right=False),
                _item(f"{m.q_kw:g}", m.q_kw),
                _item(f"{eff:g}", eff),
                _item(str(n) if fits else "—",
                      n if fits else math.inf),
                _item(f"{total:g}" if fits else "—",
                      total if fits else math.inf),
                # сортировка по запасу: при равном запасе — меньше агрегатов
                _item(f"+{margin:.1f}" if fits else "—",
                      margin + n / 1000.0 if fits else math.inf),
                _item(m.note or "", align_right=False),
            ]
            cells[C_MODEL].setData(Qt.UserRole, r)      # индекс модели
            for c, it in enumerate(cells):
                if not fits:
                    it.setForeground(Qt.gray)
                self.table.setItem(r, c, it)
        # setSortingEnabled(True) пересортирует по текущему индикатору;
        # первый раз задаём сортировку «лучший запас сверху».
        self.table.setSortingEnabled(True)
        if not getattr(self, "_sorted", False):
            self.table.sortByColumn(C_MARGIN, Qt.AscendingOrder)
            self._sorted = True
        self._apply_filter()
        self._update_ok()

    def _apply_filter(self) -> None:
        text = self.search.text().lower().strip()
        for r in range(self.table.rowCount()):
            visible = True
            if text:
                hay = " ".join(
                    (self.table.item(r, c).text() if self.table.item(r, c)
                     else "")
                    for c in (C_MODEL, C_MANUF, C_FAMILY, C_NOTE)).lower()
                visible = text in hay
            self.table.setRowHidden(r, not visible)

    # ---------------------------------------------------------- выбор
    def _current_pick(self) -> Tuple[Optional[SourceModel], int]:
        """(модель, N рабочих) по выделенной строке; (None, 0) — нет."""
        row = self.table.currentRow()
        if row < 0:
            return (None, 0)
        it = self.table.item(row, C_MODEL)
        if it is None or it.data(Qt.UserRole) is None:
            return (None, 0)
        m = self._models[int(it.data(Qt.UserRole))]
        n = cascade_for(self.required.value(), m.q_kw, MAX_UNITS)
        return (m, n)

    def _update_ok(self) -> None:
        m, n = self._current_pick()
        self.bb.button(QDialogButtonBox.Ok).setEnabled(n > 0)

    def _double_clicked(self, _item) -> None:
        m, n = self._current_pick()
        if n > 0:
            self.accept()

    def values(self) -> dict:
        """kwargs для update_zone_system; {} — ничего не выбрано."""
        m, n = self._current_pick()
        if m is None or n <= 0:
            return {}
        units = n + (1 if self.reserve.isChecked() else 0)
        out = {
            "design_capacity_kw": float(m.q_kw),
            "unit_count": int(units),
            "selected_model": (m.manufacturer + " " + m.name).strip(),
        }
        if self.domain == "heating":
            out["efficiency"] = float(getattr(m, "efficiency", 0.92))
        else:
            out["cop"] = float(getattr(m, "eer", 3.0))
        return out
