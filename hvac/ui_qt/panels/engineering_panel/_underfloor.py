# -*- coding: utf-8 -*-
"""_UnderfloorTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _UnderfloorTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.uf.col.no", "panel.eng.uf.col.space",
        "panel.eng.uf.col.area", "panel.eng.uf.col.pitch",
        "panel.eng.uf.col.cover", "panel.eng.uf.col.tsurf",
        "panel.eng.uf.col.tlim", "panel.eng.uf.col.q_m2",
        "panel.eng.uf.col.qfact", "panel.eng.uf.col.pipe",
        "panel.eng.uf.col.notes",
    )
    COVERS = (
        ("panel.eng.uf.cover.tile", "tile"),
        ("panel.eng.uf.cover.laminate", "laminate"),
        ("panel.eng.uf.cover.parquet", "parquet"),
        ("panel.eng.uf.cover.carpet", "carpet"),
        ("panel.eng.uf.cover.linoleum", "linoleum"),
    )
    ZONES = (
        ("panel.eng.uf.zone.habitable", "habitable"),
        ("panel.eng.uf.zone.bath", "bath"),
        ("panel.eng.uf.zone.edge", "edge"),
        ("panel.eng.uf.zone.corridor", "corridor"),
        ("panel.eng.uf.zone.office", "office"),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        from PySide6.QtWidgets import QSpinBox
        toolbar = QHBoxLayout()
        self._lbl_pitch = QLabel(_t("panel.eng.uf.pitch"))
        toolbar.addWidget(self._lbl_pitch)
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(50, 400)
        self.pitch_spin.setValue(150)
        self.pitch_spin.setSuffix(" мм")
        toolbar.addWidget(self.pitch_spin)
        toolbar.addSpacing(12)
        self._lbl_cover = QLabel(_t("panel.eng.uf.cover"))
        toolbar.addWidget(self._lbl_cover)
        self.cover_combo = QComboBox()
        for key, code in self.COVERS:
            self.cover_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.cover_combo)
        toolbar.addSpacing(12)
        self._lbl_zone = QLabel(_t("panel.eng.uf.zone"))
        toolbar.addWidget(self._lbl_zone)
        self.zone_combo = QComboBox()
        for key, code in self.ZONES:
            self.zone_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.zone_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.uf.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")
        outer.addWidget(self.summary)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh)
        self._refresh()

    def _refill_combo(self, combo, items):
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for key, code in items:
            combo.addItem(_t(key), userData=code)
        for i in range(combo.count()):
            if combo.itemData(i) == prev:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)

    def retranslate_ui(self) -> None:
        self._lbl_pitch.setText(_t("panel.eng.uf.pitch"))
        self._lbl_cover.setText(_t("panel.eng.uf.cover"))
        self._lbl_zone.setText(_t("panel.eng.uf.zone"))
        self._refill_combo(self.cover_combo, self.COVERS)
        self._refill_combo(self.zone_combo, self.ZONES)
        self.run_btn.setText(_t("panel.eng.uf.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.design_underfloor_loops(
                pitch_mm=self.pitch_spin.value(),
                cover=self.cover_combo.currentData(),
                zone=self.zone_combo.currentData(),
            )
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.uf.status"), 3000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "underfloor_loops", {}) or {}
        rows = []
        total_pipe = 0.0
        for sp in self.project.spaces:
            loop = data.get(sp.space_id)
            if loop is None:
                continue
            total_pipe += loop.pipe_length_m
            warns = "; ".join(loop.warnings) or "—"
            rows.append([
                sp.number, sp.name,
                round(loop.area_m2, 1),
                _t("panel.eng.uf.pitch_mm").format(n=loop.pitch_mm),
                loop.cover,
                round(loop.t_floor_surface_c, 1),
                round(loop.t_floor_limit_c, 1),
                round(loop.q_actual_w_m2, 1),
                round(loop.q_actual_w, 0),
                round(loop.pipe_length_m, 0),
                warns,
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)
        if data:
            self.summary.setText(_t("panel.eng.uf.summary").format(
                n=len(data), pipe=total_pipe))
        else:
            self.summary.setText(_t("panel.eng.common.no_data"))


