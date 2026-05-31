# -*- coding: utf-8 -*-
"""_VRFTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _VRFTab(QWidget):
    SUMMARY_KEYS = (
        "panel.eng.vrf.col.sys", "panel.eng.vrf.col.outdoor",
        "panel.eng.vrf.col.indoor", "panel.eng.vrf.col.index",
        "panel.eng.vrf.col.kconn", "panel.eng.vrf.col.qc",
        "panel.eng.vrf.col.qh", "panel.eng.vrf.col.corr",
        "panel.eng.vrf.col.check",
    )
    INDOORS_KEYS = (
        "panel.eng.vrf.col.sys2", "panel.eng.vrf.col.space",
        "panel.eng.vrf.col.indoor_model", "panel.eng.vrf.col.idx",
        "panel.eng.vrf.col.qc_w", "panel.eng.vrf.col.dliq",
        "panel.eng.vrf.col.dgas",
    )
    GROUPS = (
        ("panel.eng.vrf.group.level", "level"),
        ("panel.eng.vrf.group.all", "all"),
    )
    INDOORS_FAM = (
        ("panel.eng.vrf.indoor.cassette", "Кассетный"),
        ("panel.eng.vrf.indoor.duct", "Канальный"),
        ("panel.eng.vrf.indoor.wall", "Настенный"),
        ("panel.eng.vrf.indoor.any", None),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.vrf.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        from PySide6.QtWidgets import QDoubleSpinBox
        toolbar = QHBoxLayout()
        self._lbl_group = QLabel(_t("panel.eng.vrf.group"))
        toolbar.addWidget(self._lbl_group)
        self.group_combo = QComboBox()
        for key, code in self.GROUPS:
            self.group_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.group_combo)
        toolbar.addSpacing(12)
        self._lbl_indoor = QLabel(_t("panel.eng.vrf.indoor"))
        toolbar.addWidget(self._lbl_indoor)
        self.indoor_combo = QComboBox()
        for key, code in self.INDOORS_FAM:
            self.indoor_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.indoor_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.vrf.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        # Параметры трасс
        params_row = QHBoxLayout()
        self._lbl_main = QLabel(_t("panel.eng.vrf.main_pipe"))
        params_row.addWidget(self._lbl_main)
        self.main_pipe_spin = QDoubleSpinBox()
        self.main_pipe_spin.setRange(5, 500)
        self.main_pipe_spin.setValue(30)
        self.main_pipe_spin.setSuffix(" м")
        params_row.addWidget(self.main_pipe_spin)
        params_row.addSpacing(12)
        self._lbl_max = QLabel(_t("panel.eng.vrf.max_pipe"))
        params_row.addWidget(self._lbl_max)
        self.max_pipe_spin = QDoubleSpinBox()
        self.max_pipe_spin.setRange(5, 300)
        self.max_pipe_spin.setValue(60)
        self.max_pipe_spin.setSuffix(" м")
        params_row.addWidget(self.max_pipe_spin)
        params_row.addSpacing(12)
        self._lbl_dh = QLabel(_t("panel.eng.vrf.dh_max"))
        params_row.addWidget(self._lbl_dh)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0, 150)
        self.height_spin.setValue(15)
        self.height_spin.setSuffix(" м")
        params_row.addWidget(self.height_spin)
        params_row.addStretch(1)
        outer.addLayout(params_row)

        # Таблица сводки систем
        self.summary_table = QTableWidget(0, 0)
        _setup_table(self.summary_table, [_t(k) for k in self.SUMMARY_KEYS])
        outer.addWidget(self.summary_table)

        # Таблица внутренних блоков
        self.indoors_table = QTableWidget(0, 0)
        _setup_table(self.indoors_table, [_t(k) for k in self.INDOORS_KEYS])
        outer.addWidget(self.indoors_table, stretch=1)

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
        self._info.setText(_t("panel.eng.vrf.info"))
        self._lbl_group.setText(_t("panel.eng.vrf.group"))
        self._lbl_indoor.setText(_t("panel.eng.vrf.indoor"))
        self._lbl_main.setText(_t("panel.eng.vrf.main_pipe"))
        self._lbl_max.setText(_t("panel.eng.vrf.max_pipe"))
        self._lbl_dh.setText(_t("panel.eng.vrf.dh_max"))
        self._refill_combo(self.group_combo, self.GROUPS)
        self._refill_combo(self.indoor_combo, self.INDOORS_FAM)
        self.run_btn.setText(_t("panel.eng.vrf.btn_run"))
        self.summary_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.SUMMARY_KEYS])
        self.indoors_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.INDOORS_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.build_vrf_systems(
                indoor_family=self.indoor_combo.currentData(),
                group_by=self.group_combo.currentData(),
                main_pipe_length_m=self.main_pipe_spin.value(),
                max_pipe_length_m=self.max_pipe_spin.value(),
                max_height_m=self.height_spin.value(),
            )
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.vrf.status"), 3000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        from hvac.vrf import check_constraints, pipe_diameters_by_index
        data = getattr(self.project, "vrf_systems", {}) or {}

        # Сводка
        rows = []
        for name, sys in data.items():
            check = check_constraints(sys)
            status = (_t("panel.eng.vrf.ok") if check.ok
                      else _t("panel.eng.vrf.warn").format(n=len(check.issues)))
            out_name = sys.outdoor.name if sys.outdoor else "—"
            q_cool = sys.outdoor.q_cool_w / 1000.0 if sys.outdoor else 0.0
            q_heat = sys.outdoor.q_heat_w / 1000.0 if sys.outdoor else 0.0
            rows.append([
                name, out_name,
                len(sys.indoors),
                sys.total_indoor_capacity_index,
                round(sys.combination_ratio, 2),
                round(q_cool, 1), round(q_heat, 1),
                round(sys.capacity_correction_factor, 3),
                status,
            ])
        self.summary_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.summary_table, i, row)

        # Внутренние
        rows = []
        for name, sys in data.items():
            for a in sys.indoors:
                liq, gas = pipe_diameters_by_index(a.indoor.capacity_index)
                rows.append([
                    name, a.space_id or "—",
                    a.indoor.name,
                    a.indoor.capacity_index,
                    round(a.indoor.q_cool_w, 0),
                    f"{liq:.2f}", f"{gas:.2f}",
                ])
        self.indoors_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.indoors_table, i, row)


