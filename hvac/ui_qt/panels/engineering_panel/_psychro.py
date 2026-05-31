# -*- coding: utf-8 -*-
"""_PsychroTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _PsychroTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.psy.col.point", "panel.eng.psy.col.t",
        "panel.eng.psy.col.w", "panel.eng.psy.col.rh",
        "panel.eng.psy.col.h", "panel.eng.psy.col.td",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._chart_canvas = None

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        toolbar = QHBoxLayout()
        self._lbl_ahu = QLabel(_t("panel.eng.psy.ahu"))
        toolbar.addWidget(self._lbl_ahu)
        self.ahu_combo = QComboBox()
        self.ahu_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self.ahu_combo)
        toolbar.addSpacing(12)
        self._lbl_mode = QLabel(_t("panel.eng.psy.mode"))
        toolbar.addWidget(self._lbl_mode)
        self.mode_combo = QComboBox()
        for key, code in [("panel.eng.psy.mode.winter", "winter"),
                          ("panel.eng.psy.mode.summer", "summer"),
                          ("panel.eng.psy.mode.trans", "transitional")]:
            self.mode_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.mode_combo)
        self.mode_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addSpacing(12)
        self.chart_btn = QPushButton(_t("panel.eng.psy.btn_chart"))
        self.chart_btn.setToolTip(_t("panel.eng.psy.btn_chart_tt"))
        self.chart_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.chart_btn.clicked.connect(self._toggle_chart)
        toolbar.addWidget(self.chart_btn)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.psy.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        # Контент: либо таблица, либо диаграмма
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        self.stack.addWidget(self.table)
        self.chart_placeholder = QLabel(_t("panel.eng.psy.matplotlib"))
        self.chart_placeholder.setAlignment(Qt.AlignCenter)
        self.chart_placeholder.setProperty("role", "muted")
        self.stack.addWidget(self.chart_placeholder)
        outer.addWidget(self.stack, stretch=1)

        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        for sig in (bridge.calculationDone, bridge.ventilationDone,
                    bridge.zonesChanged):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_ahu.setText(_t("panel.eng.psy.ahu"))
        self._lbl_mode.setText(_t("panel.eng.psy.mode"))
        prev_mode = self.mode_combo.currentData()
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for key, code in [("panel.eng.psy.mode.winter", "winter"),
                          ("panel.eng.psy.mode.summer", "summer"),
                          ("panel.eng.psy.mode.trans", "transitional")]:
            self.mode_combo.addItem(_t(key), userData=code)
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == prev_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        self.mode_combo.blockSignals(False)
        if self.stack.currentWidget() is self.table:
            self.chart_btn.setText(_t("panel.eng.psy.btn_chart"))
        else:
            self.chart_btn.setText(_t("panel.eng.psy.btn_table"))
        self.chart_btn.setToolTip(_t("panel.eng.psy.btn_chart_tt"))
        self.run_btn.setText(_t("panel.eng.psy.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self.chart_placeholder.setText(_t("panel.eng.psy.matplotlib"))
        self._refresh()

    def _run(self):
        try:
            self.project.calculate_ahu_loads()
            self.project.compute_ahu_processes()
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.psy.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _toggle_chart(self):
        """Переключение между таблицей и i-d диаграммой."""
        if self.stack.currentWidget() is self.table:
            self._show_chart()
        else:
            self.stack.setCurrentWidget(self.table)
            self.chart_btn.setText(_t("panel.eng.psy.btn_chart"))

    def _show_chart(self):
        proc_data = getattr(self.project, "ahu_processes", {}) or {}
        ahu = self.ahu_combo.currentText()
        if not ahu or ahu not in proc_data:
            self.stack.setCurrentWidget(self.chart_placeholder)
            self.chart_placeholder.setText(_t("panel.eng.psy.run_first"))
            return
        try:
            from hvac.psychro_chart import render_processes_for_ahu
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        except ImportError:
            self.stack.setCurrentWidget(self.chart_placeholder)
            self.chart_placeholder.setText(_t("panel.eng.psy.install"))
            return

        fig = render_processes_for_ahu(
            proc_data, ahu, modes=("winter", "summer", "transitional"))
        # Удаляем старый canvas, если есть
        if self._chart_canvas is not None:
            self.stack.removeWidget(self._chart_canvas)
            self._chart_canvas.deleteLater()
        self._chart_canvas = FigureCanvasQTAgg(fig)
        self.stack.addWidget(self._chart_canvas)
        self.stack.setCurrentWidget(self._chart_canvas)
        self.chart_btn.setText(_t("panel.eng.psy.btn_table"))

    def _refresh(self, *_):
        proc_data = getattr(self.project, "ahu_processes", {}) or {}
        # Обновляем список AHU
        prev_ahu = self.ahu_combo.currentText()
        self.ahu_combo.blockSignals(True)
        self.ahu_combo.clear()
        for name in proc_data.keys():
            self.ahu_combo.addItem(name)
        if prev_ahu:
            i = self.ahu_combo.findText(prev_ahu)
            if i >= 0:
                self.ahu_combo.setCurrentIndex(i)
        self.ahu_combo.blockSignals(False)

        ahu = self.ahu_combo.currentText()
        mode = self.mode_combo.currentData() or "winter"
        rows = []
        summary_lines = []
        for name, by_mode in proc_data.items():
            if ahu and name != ahu:
                continue
            proc = by_mode.get(mode)
            if proc is None:
                continue
            for point, st in proc.points.items():
                rows.append([
                    point,
                    round(st.t_c, 1), round(st.w_g_kg, 2),
                    round(st.rh * 100, 1), round(st.h_kj_kg, 2),
                    round(st.t_dp_c, 1),
                ])
            summary_lines.append(_t("panel.eng.psy.summary").format(
                name=name, mode=mode,
                qh=proc.q_heater_kw, qc=proc.q_cooler_total_kw,
                qs=proc.q_cooler_sensible_kw, ql=proc.q_cooler_latent_kw,
                cond=proc.condensate_kg_h))
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)
        self.summary.setText("\n".join(summary_lines)
                              or _t("panel.eng.common.no_data"))


