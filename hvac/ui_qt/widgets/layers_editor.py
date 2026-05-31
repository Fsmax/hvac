# -*- coding: utf-8 -*-
"""Диалог редактирования слоёв многослойной конструкции."""

from __future__ import annotations
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Construction, Layer, _rsi_rse_for
from hvac.catalogs.materials import MATERIALS, AIR_GAPS


def _set_item_text(table: QTableWidget, row: int, col: int, text: str) -> None:
    """Безопасно ставит текст ячейки (item() может вернуть None)."""
    it = table.item(row, col)
    if it is not None:
        it.setText(text)


class LayersEditor(QDialog):
    """Редактор слоёв одной конструкции.

    Колонки: [Материал | Толщ., мм | λ, Вт/(м·К) | R слоя, м²К/Вт].
    R слоя вычисляется автоматически (read-only) либо задаётся прямо
    для воздушных прослоек.
    Кнопки внизу: Добавить, Удалить, Вверх, Вниз.
    Сводка справа: Rsi/Rse, Σ R, U.
    """

    HEADER_KEYS = (
        "dlg.layers.col.material",
        "dlg.layers.col.th",
        "dlg.layers.col.lambda",
        "dlg.layers.col.r",
    )

    def __init__(self, construction: Construction, parent: QWidget | None = None):
        super().__init__(parent)
        self.construction = construction
        self.setWindowTitle(_t("dlg.layers.title").format(key=construction.key))
        self.resize(820, 480)

        root = QHBoxLayout(self)

        # ===== Левая часть: таблица слоёв + кнопки =====
        left = QVBoxLayout()
        cat_lbl = QLabel(_t("dlg.layers.category").format(
            category=construction.category))
        cat_lbl.setProperty("role", "muted")
        left.addWidget(cat_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents)
        left.addWidget(self.table, stretch=1)

        btns = QHBoxLayout()
        b_add = QPushButton(_t("dlg.layers.btn_add"))
        b_del = QPushButton(_t("dlg.layers.btn_delete"))
        b_up = QPushButton("↑")
        b_dn = QPushButton("↓")
        b_air = QPushButton(_t("dlg.layers.btn_air"))
        for b in (b_add, b_air, b_del, b_up, b_dn):
            btns.addWidget(b)
        btns.addStretch(1)
        left.addLayout(btns)
        root.addLayout(left, stretch=3)

        # ===== Правая часть: сводка =====
        right = QVBoxLayout()
        right.addWidget(QLabel(_t("dlg.layers.summary_title")))
        self.summary_lbl = QLabel()
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setTextFormat(Qt.RichText)
        right.addWidget(self.summary_lbl)
        right.addStretch(1)
        root.addLayout(right, stretch=2)

        # ===== OK / Отмена =====
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        right.addWidget(box)

        # Подключения
        b_add.clicked.connect(self._add_material_layer)
        b_air.clicked.connect(self._add_air_gap)
        b_del.clicked.connect(self._delete_selected)
        b_up.clicked.connect(lambda: self._move_selected(-1))
        b_dn.clicked.connect(lambda: self._move_selected(+1))
        self.table.itemChanged.connect(lambda *_: self._refresh_summary())

        # Заполнение
        for layer in construction.layers:
            self._append_row(layer)
        self._refresh_summary()

    # ---------- helpers ----------
    def _append_row(self, layer: Layer) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        combo = QComboBox()
        combo.setEditable(True)
        all_names = list(MATERIALS.keys()) + list(AIR_GAPS.keys())
        combo.addItems(all_names)
        combo.setCurrentText(layer.material or "")
        combo.currentTextChanged.connect(
            lambda txt, r=row: self._on_material_changed(r, txt))
        self.table.setCellWidget(row, 0, combo)

        for col, value in ((1, layer.thickness_mm), (2, layer.lambda_w_mk)):
            item = QTableWidgetItem(f"{value:g}" if value else "")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item)

        r_item = QTableWidgetItem(self._fmt_r(layer))
        r_item.setFlags(r_item.flags() & ~Qt.ItemIsEditable)
        r_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if layer.r_m2k_w > 0 and not (layer.lambda_w_mk and layer.thickness_mm):
            # воздушная прослойка — хранит прямой R
            _set_item_text(self.table, row, 1, "")
            _set_item_text(self.table, row, 2, "")
            r_item.setText(f"{layer.r_m2k_w:.3f}")
            r_item.setData(Qt.UserRole, "air")
            r_item.setFlags(r_item.flags() | Qt.ItemIsEditable)
        self.table.setItem(row, 3, r_item)

    def _fmt_r(self, layer: Layer) -> str:
        if layer.r_m2k_w > 0 and not layer.lambda_w_mk:
            return f"{layer.r_m2k_w:.3f}"
        if layer.lambda_w_mk > 0 and layer.thickness_mm > 0:
            return f"{(layer.thickness_mm / 1000.0) / layer.lambda_w_mk:.3f}"
        return ""

    def _on_material_changed(self, row: int, text: str) -> None:
        mat = MATERIALS.get(text)
        if mat is not None:
            # Автозаполнить λ
            item = self.table.item(row, 2)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 2, item)
            item.setText(f"{mat.lambda_w_mk:g}")
        elif text in AIR_GAPS:
            r = AIR_GAPS[text]
            _set_item_text(self.table, row, 1, "")
            _set_item_text(self.table, row, 2, "")
            r_item = self.table.item(row, 3)
            if r_item is not None:
                r_item.setText(f"{r:.3f}")
                r_item.setData(Qt.UserRole, "air")
        self._refresh_summary()

    def _add_material_layer(self) -> None:
        self._append_row(Layer(material="", thickness_mm=100.0, lambda_w_mk=0.0))

    def _add_air_gap(self) -> None:
        self._append_row(Layer(material="Воздушная прослойка 50 мм",
                               r_m2k_w=AIR_GAPS["Воздушная прослойка 50 мм"]))

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._refresh_summary()

    def _move_selected(self, delta: int) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        new = row + delta
        if not (0 <= new < self.table.rowCount()):
            return
        # Заберём существующие слои в Layer-объекты, переставим, перерисуем
        layers = self._collect_layers()
        layers[row], layers[new] = layers[new], layers[row]
        self.table.setRowCount(0)
        for l in layers:
            self._append_row(l)
        self.table.setCurrentCell(new, 0)
        self._refresh_summary()

    def _collect_layers(self) -> List[Layer]:
        out: List[Layer] = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            material = combo.currentText().strip() if combo else ""
            thickness = _to_float(self.table.item(row, 1))
            lam = _to_float(self.table.item(row, 2))
            r_item = self.table.item(row, 3)
            r_air = 0.0
            if r_item and r_item.data(Qt.UserRole) == "air":
                r_air = _to_float(r_item)
            mat = MATERIALS.get(material)
            density = mat.density_kg_m3 if mat else 0.0
            out.append(Layer(material=material, thickness_mm=thickness,
                             lambda_w_mk=lam, density_kg_m3=density,
                             r_m2k_w=r_air))
        return out

    def _refresh_summary(self) -> None:
        rsi, rse = _rsi_rse_for(self.construction.category)
        r = rsi + rse
        for layer in self._collect_layers():
            if layer.r_m2k_w > 0:
                r += layer.r_m2k_w
            elif layer.lambda_w_mk > 0 and layer.thickness_mm > 0:
                r += (layer.thickness_mm / 1000.0) / layer.lambda_w_mk
        u = 1.0 / r if r > 0 else 0.0
        self.summary_lbl.setText(_t("dlg.layers.summary").format(
            rsi=rsi, rse=rse, r=r, u=u))

    # ---------- результат ----------
    def get_layers(self) -> List[Layer]:
        return self._collect_layers()


def _to_float(item) -> float:
    if item is None:
        return 0.0
    try:
        return float((item.text() or "0").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
