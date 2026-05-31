# -*- coding: utf-8 -*-
"""_EnergyTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


class _EnergyTab(QWidget):
    """8760-часовая симуляция: годовое потребление и почасовой график."""
    HEADER_KEYS = ("panel.eng.en.col.param", "panel.eng.en.col.value")

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._chart_canvas = None

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.en.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        # Параметры симуляции
        from PySide6.QtWidgets import QDoubleSpinBox
        toolbar = QHBoxLayout()
        self._lbl_tau = QLabel(_t("panel.eng.en.tau"))
        toolbar.addWidget(self._lbl_tau)
        self.tau_spin = QDoubleSpinBox()
        self.tau_spin.setRange(2.0, 48.0)
        self.tau_spin.setValue(12.0)
        self.tau_spin.setSuffix(" ч")
        self.tau_spin.setDecimals(1)
        toolbar.addWidget(self.tau_spin)
        toolbar.addSpacing(12)
        self._lbl_setback = QLabel(_t("panel.eng.en.setback"))
        toolbar.addWidget(self._lbl_setback)
        self.setback_spin = QDoubleSpinBox()
        self.setback_spin.setRange(-5.0, 0.0)
        self.setback_spin.setValue(0.0)
        self.setback_spin.setSuffix(" °C")
        self.setback_spin.setDecimals(1)
        toolbar.addWidget(self.setback_spin)
        toolbar.addStretch(1)

        self.chart_btn = QPushButton(_t("panel.eng.en.btn_chart"))
        self.chart_btn.setToolTip(_t("panel.eng.en.btn_chart_tt"))
        self.chart_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.chart_btn.clicked.connect(self._toggle_chart)
        toolbar.addWidget(self.chart_btn)

        self.run_btn = QPushButton(_t("panel.eng.en.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        # Стек: таблица результатов / график
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        self.stack.addWidget(self.table)
        self.chart_placeholder = QLabel(_t("panel.eng.en.matplotlib"))
        self.chart_placeholder.setAlignment(Qt.AlignCenter)
        self.chart_placeholder.setProperty("role", "muted")
        self.stack.addWidget(self.chart_placeholder)
        outer.addWidget(self.stack, stretch=1)

        # Сводка-баннер
        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.en.info"))
        self._lbl_tau.setText(_t("panel.eng.en.tau"))
        self._lbl_setback.setText(_t("panel.eng.en.setback"))
        if self.stack.currentWidget() is self.table:
            self.chart_btn.setText(_t("panel.eng.en.btn_chart"))
        else:
            self.chart_btn.setText(_t("panel.eng.en.btn_table"))
        self.chart_btn.setToolTip(_t("panel.eng.en.btn_chart_tt"))
        self.run_btn.setText(_t("panel.eng.en.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self.chart_placeholder.setText(_t("panel.eng.en.matplotlib"))
        self._refresh()

    def _run(self):
        try:
            self.project.simulate_annual_energy(
                keep_hourly=True,
                thermal_mass_tau_h=self.tau_spin.value(),
                heating_setpoint_offset=self.setback_spin.value(),
            )
        except Exception as e:
            QMessageBox.critical(
                self, _t("panel.eng.en.status_err"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.en.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _toggle_chart(self):
        if self.stack.currentWidget() is self.table:
            self._show_chart()
        else:
            self.stack.setCurrentWidget(self.table)
            self.chart_btn.setText(_t("panel.eng.en.btn_chart"))

    def _show_chart(self):
        result = getattr(self.project, "energy_simulation_result", None)
        if result is None or result.hourly_q_heat_w is None:
            self.stack.setCurrentWidget(self.chart_placeholder)
            self.chart_placeholder.setText(_t("panel.eng.en.run_first"))
            return
        try:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        except ImportError:
            self.stack.setCurrentWidget(self.chart_placeholder)
            self.chart_placeholder.setText(_t("panel.eng.en.install"))
            return

        fig = Figure(figsize=(10, 6))
        # Двухосный график: T_out и нагрузки
        ax1 = fig.add_subplot(211)
        # Прорежим до 1 точки на сутки для T (365)
        daily = [
            sum(result.hourly_t_out_c[d * 24:(d + 1) * 24]) / 24
            for d in range(365)
        ]
        ax1.plot(range(365), daily, color="#4477AA", linewidth=0.8)
        ax1.set_ylabel(_t("panel.eng.en.chart.t_ext"))
        ax1.set_title(_t("panel.eng.en.chart.t_year"))
        ax1.grid(True, alpha=0.3)

        ax2 = fig.add_subplot(212, sharex=ax1)
        daily_h = [
            sum(result.hourly_q_heat_w[d * 24:(d + 1) * 24]) / 24 / 1000
            for d in range(365)
        ]
        daily_c = [
            sum(result.hourly_q_cool_w[d * 24:(d + 1) * 24]) / 24 / 1000
            for d in range(365)
        ]
        ax2.fill_between(range(365), 0, daily_h,
                          color="#CC4444", alpha=0.65,
                          label=_t("panel.eng.en.chart.heat"))
        ax2.fill_between(range(365), 0, daily_c,
                          color="#4477AA", alpha=0.65,
                          label=_t("panel.eng.en.chart.cool"))
        ax2.set_xlabel(_t("panel.eng.en.chart.day"))
        ax2.set_ylabel(_t("panel.eng.en.chart.q_avg"))
        ax2.set_title(_t("panel.eng.en.chart.qd_year"))
        ax2.legend(loc="upper right")
        ax2.grid(True, alpha=0.3)
        fig.tight_layout()

        if self._chart_canvas is not None:
            self.stack.removeWidget(self._chart_canvas)
            self._chart_canvas.deleteLater()
        self._chart_canvas = FigureCanvasQTAgg(fig)
        self.stack.addWidget(self._chart_canvas)
        self.stack.setCurrentWidget(self._chart_canvas)
        self.chart_btn.setText(_t("panel.eng.en.btn_table"))

    def _refresh(self, *_):
        result = getattr(self.project, "energy_simulation_result", None)
        if result is None or result.n_spaces == 0:
            self.table.setRowCount(0)
            self.summary.setText(_t("panel.eng.en.empty"))
            return
        from hvac.energy_simulation import hour_to_iso_datetime
        rows = [
            [_t("panel.eng.en.row.spaces"), f"{result.n_spaces}"],
            [_t("panel.eng.en.row.area"), f"{result.total_area_m2:.0f}"],
            ["", ""],
            [_t("panel.eng.en.row.e_heat"),
              f"{result.e_heat_kwh:,.0f}".replace(",", " ")],
            [_t("panel.eng.en.row.e_cool"),
              f"{result.e_cool_kwh:,.0f}".replace(",", " ")],
            [_t("panel.eng.en.row.e_heat_m2"),
              f"{result.e_heat_kwh_m2:.1f}"],
            [_t("panel.eng.en.row.e_cool_m2"),
              f"{result.e_cool_kwh_m2:.1f}"],
            [_t("panel.eng.en.row.e_total_m2"),
              f"{result.e_total_kwh_m2:.1f}"],
            ["", ""],
            [_t("panel.eng.en.row.q_peak_heat"),
              f"{result.q_peak_heat_w / 1000:.1f}"],
            [_t("panel.eng.en.row.q_peak_cool"),
              f"{result.q_peak_cool_w / 1000:.1f}"],
            [_t("panel.eng.en.row.t_peak_heat"),
              hour_to_iso_datetime(result.hour_of_peak_heat)],
            [_t("panel.eng.en.row.t_peak_cool"),
              hour_to_iso_datetime(result.hour_of_peak_cool)],
            [_t("panel.eng.en.row.h_peak_heat"),
              f"{result.hours_at_peak_heat}"],
            [_t("panel.eng.en.row.h_peak_cool"),
              f"{result.hours_at_peak_cool}"],
            [_t("panel.eng.en.row.h_heat"),
              f"{result.heating_hours}"],
            [_t("panel.eng.en.row.h_cool"),
              f"{result.cooling_hours}"],
        ]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)

        self.summary.setText(_t("panel.eng.en.summary").format(
            total=result.e_total_kwh_m2,
            qh=result.q_peak_heat_w / 1000,
            qc=result.q_peak_cool_w / 1000,
            hh=result.heating_hours, ch=result.cooling_hours))


