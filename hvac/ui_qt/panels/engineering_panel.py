# -*- coding: utf-8 -*-
"""EngineeringPanel — подробная инженерия v4.1.

5 вкладок:
    1. Психрометрика AHU         — точки процесса по режимам
    2. Аэродинамика воздуховодов — детальный расчёт ΔP сети
    3. Гидравлика отопления      — насос, бак, подпитка
    4. Радиаторы по помещениям   — подобранные приборы
    5. Акустика и шумоглушители  — Lpa и подбор глушителей

Каждая вкладка имеет кнопку «Рассчитать» и таблицу результатов.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from hvac.i18n import on_language_change, t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card


# ---------------------------------------------------------------------------
# Утилиты заполнения таблиц
# ---------------------------------------------------------------------------

def _setup_table(table: QTableWidget, headers: list[str]) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setStretchLastSection(True)


def _set_row(table: QTableWidget, row: int, values: list[Any]) -> None:
    for c, v in enumerate(values):
        if isinstance(v, float):
            text = f"{v:,.2f}".replace(",", " ") if v != int(v) else f"{int(v)}"
        else:
            text = str(v)
        item = QTableWidgetItem(text)
        if isinstance(v, (int, float)):
            item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
        table.setItem(row, c, item)


# ---------------------------------------------------------------------------
# Вкладки
# ---------------------------------------------------------------------------

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


class _DuctTab(QWidget):
    SUMMARY_KEYS = (
        "panel.eng.duct.col.sys", "panel.eng.duct.col.terms",
        "panel.eng.duct.col.q", "panel.eng.duct.col.dp",
        "panel.eng.duct.col.v", "panel.eng.duct.col.crit",
    )
    EDGES_KEYS = (
        "panel.eng.duct.col.id", "panel.eng.duct.col.parent",
        "panel.eng.duct.col.terminal", "panel.eng.duct.col.name",
        "panel.eng.duct.col.flow", "panel.eng.duct.col.len",
        "panel.eng.duct.col.size", "panel.eng.duct.col.vel",
        "panel.eng.duct.col.dpf", "panel.eng.duct.col.dpl",
        "panel.eng.duct.col.dpt",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        self._info = QLabel(_t("panel.eng.duct.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        toolbar = QHBoxLayout()
        self._lbl_net = QLabel(_t("panel.eng.duct.net"))
        toolbar.addWidget(self._lbl_net)
        self.net_combo = QComboBox()
        self.net_combo.currentIndexChanged.connect(self._on_net_changed)
        toolbar.addWidget(self.net_combo, stretch=1)
        self.build_btn = QPushButton(_t("panel.eng.duct.btn_build"))
        self.build_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.build_btn.clicked.connect(self._build)
        toolbar.addWidget(self.build_btn)
        self.recompute_btn = QPushButton(_t("panel.eng.duct.btn_recompute"))
        self.recompute_btn.setProperty("role", "primary")
        self.recompute_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.recompute_btn.clicked.connect(self._recompute_current)
        toolbar.addWidget(self.recompute_btn)
        outer.addLayout(toolbar)

        # Кнопки управления участками
        edit_bar = QHBoxLayout()
        self.add_edge_btn = QPushButton(_t("panel.eng.duct.btn_add"))
        self.add_edge_btn.clicked.connect(self._add_edge)
        edit_bar.addWidget(self.add_edge_btn)
        self.edit_edge_btn = QPushButton(_t("panel.eng.duct.btn_edit"))
        self.edit_edge_btn.clicked.connect(self._edit_selected_edge)
        edit_bar.addWidget(self.edit_edge_btn)
        self.del_edge_btn = QPushButton(_t("panel.eng.duct.btn_delete"))
        self.del_edge_btn.clicked.connect(self._delete_selected_edge)
        edit_bar.addWidget(self.del_edge_btn)
        edit_bar.addStretch(1)
        self.fan_label = QLabel("")
        self.fan_label.setProperty("role", "muted")
        edit_bar.addWidget(self.fan_label)
        outer.addLayout(edit_bar)

        # Таблица сводки сетей
        self.summary_table = QTableWidget(0, 0)
        _setup_table(self.summary_table, [_t(k) for k in self.SUMMARY_KEYS])
        self.summary_table.setMaximumHeight(160)
        outer.addWidget(self.summary_table)

        # Таблица участков активной сети
        self.edges_table = QTableWidget(0, 0)
        _setup_table(self.edges_table, [_t(k) for k in self.EDGES_KEYS])
        self.edges_table.doubleClicked.connect(
            lambda *_: self._edit_selected_edge())
        outer.addWidget(self.edges_table, stretch=1)

        # Совместимость со старым именем (в коде использовалось self.table)
        self.table = self.summary_table

    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.duct.info"))
        self._lbl_net.setText(_t("panel.eng.duct.net"))
        self.build_btn.setText(_t("panel.eng.duct.btn_build"))
        self.recompute_btn.setText(_t("panel.eng.duct.btn_recompute"))
        self.add_edge_btn.setText(_t("panel.eng.duct.btn_add"))
        self.edit_edge_btn.setText(_t("panel.eng.duct.btn_edit"))
        self.del_edge_btn.setText(_t("panel.eng.duct.btn_delete"))
        self.summary_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.SUMMARY_KEYS])
        self.edges_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.EDGES_KEYS])
        self._refresh()

    def _build(self):
        from hvac.duct_network import (
            DuctEdge, DuctFitting, DuctNetworkDetailed,
        )
        # Конвертация существующих DuctNetwork в детальные.
        # Если у сети нет sections — пропускаем.
        result = {}
        for name, net in self.project.duct_networks.items():
            if not net.sections:
                continue
            detailed = DuctNetworkDetailed(
                system_name=name, role=net.role)
            # Простейшая конвертация: магистраль + ветви
            trunk_id = "trunk"
            sections = list(net.sections)
            trunk_sec = next((s for s in sections
                              if s.section_type == "trunk"), sections[0])
            detailed.add_edge(DuctEdge(
                edge_id=trunk_id, parent_id="",
                flow_m3_h=trunk_sec.flow_m3h,
                length_m=trunk_sec.length_m,
                shape=trunk_sec.shape,
                diameter_mm=trunk_sec.diameter_mm,
                width_mm=trunk_sec.width_mm,
                height_mm=trunk_sec.height_mm,
                fittings=[DuctFitting(kind="weather_louver"),
                          DuctFitting(kind="tee_straight",
                                       quantity=max(len(sections)-2, 0))],
            ))
            i = 0
            for s in sections:
                if s is trunk_sec:
                    continue
                i += 1
                detailed.add_edge(DuctEdge(
                    edge_id=f"branch_{i}", parent_id=trunk_id,
                    flow_m3_h=s.flow_m3h,
                    length_m=s.length_m,
                    shape=s.shape,
                    diameter_mm=s.diameter_mm,
                    width_mm=s.width_mm,
                    height_mm=s.height_mm,
                    fittings=[DuctFitting(kind="tee_branch"),
                              DuctFitting(kind="elbow_90_round_r15d"),
                              DuctFitting(kind="grille_supply")],
                    terminal_name=s.note or _t(
                        "panel.eng.duct.terminal_dflt").format(i=i),
                    is_terminal=True,
                ))
            detailed.compute()
            result[name] = detailed
        self.project.duct_networks_detailed = result
        self.bridge.statusMessage.emit(
            _t("panel.eng.duct.status_built").format(n=len(result)), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _current_network_name(self) -> str:
        return self.net_combo.currentText()

    def _current_network(self):
        name = self._current_network_name()
        nets = getattr(self.project, "duct_networks_detailed", {}) or {}
        return nets.get(name)

    def _on_net_changed(self):
        self._refresh_edges_table()

    def _recompute_current(self):
        net = self._current_network()
        if net is None:
            QMessageBox.information(
                self, _t("panel.eng.duct.no_net"),
                _t("panel.eng.duct.no_net_msg"))
            return
        try:
            net.compute()
        except Exception as e:
            QMessageBox.critical(
                self, _t("panel.eng.duct.calc_err"), str(e))
            return
        self.bridge.statusMessage.emit(
            _t("panel.eng.duct.recomp_status").format(name=net.system_name),
            3000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _selected_edge_id(self) -> str | None:
        row = self.edges_table.currentRow()
        if row < 0:
            return None
        item = self.edges_table.item(row, 0)
        return item.text() if item else None

    def _add_edge(self):
        from hvac.duct_network import DuctNetworkDetailed
        from hvac.ui_qt.widgets.duct_edge_dialog import DuctEdgeDialog
        net = self._current_network()
        if net is None:
            # Создать новую сеть из имени системы вентиляции
            sys_name, ok = self._ask_system_name()
            if not ok:
                return
            net = DuctNetworkDetailed(system_name=sys_name)
            self.project.duct_networks_detailed[sys_name] = net
        dlg = DuctEdgeDialog(self, edge=None,
                              known_edge_ids=list(net.edges.keys()),
                              is_new=True)
        if dlg.exec() != dlg.Accepted:
            return
        try:
            net.add_edge(dlg.edge)
        except ValueError as e:
            QMessageBox.warning(self, _t("panel.eng.common.error"), str(e))
            return
        net.compute()
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _ask_system_name(self) -> tuple[str, bool]:
        """Спрашивает имя для новой сети (из систем вентиляции проекта)."""
        from PySide6.QtWidgets import QInputDialog
        names = list(self.project.ventilation_systems.keys())
        if names:
            name, ok = QInputDialog.getItem(
                self, _t("panel.eng.duct.new_net_title"),
                _t("panel.eng.duct.new_net_combo"), names, 0, False)
        else:
            name, ok = QInputDialog.getText(
                self, _t("panel.eng.duct.new_net_title"),
                _t("panel.eng.duct.new_net_text"))
        return (name or "").strip(), ok

    def _edit_selected_edge(self):
        from hvac.ui_qt.widgets.duct_edge_dialog import DuctEdgeDialog
        net = self._current_network()
        if net is None:
            return
        eid = self._selected_edge_id()
        if not eid:
            return
        edge = net.edges.get(eid)
        if edge is None:
            return
        dlg = DuctEdgeDialog(
            self, edge=edge,
            known_edge_ids=[k for k in net.edges.keys() if k != eid],
            is_new=False,
        )
        if dlg.exec() != dlg.Accepted:
            return
        # Копируем поля обратно
        for fld in ("parent_id", "flow_m3_h", "length_m", "shape",
                    "diameter_mm", "width_mm", "height_mm",
                    "terminal_name", "is_terminal", "note", "fittings"):
            setattr(edge, fld, getattr(dlg.edge, fld))
        net.compute()
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _delete_selected_edge(self):
        net = self._current_network()
        if net is None:
            return
        eid = self._selected_edge_id()
        if not eid:
            return
        # Запрет удаления, если у участка есть дети
        children = [e.edge_id for e in net.edges.values()
                    if e.parent_id == eid]
        if children:
            QMessageBox.warning(
                self, _t("panel.eng.duct.del_block_title"),
                _t("panel.eng.duct.del_block_msg").format(
                    eid=eid, children=", ".join(children)))
            return
        ans = QMessageBox.question(
            self, _t("panel.eng.duct.del_title"),
            _t("panel.eng.duct.del_msg").format(eid=eid),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        del net.edges[eid]
        net.compute()
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        nets = getattr(self.project, "duct_networks_detailed", {}) or {}
        # Сводка сетей
        rows = []
        for name, n in nets.items():
            critical = next((b for b in n.branches
                             if b.terminal_edge_id == n.critical_branch_id),
                            None)
            crit_name = (critical.terminal_name if critical
                         else n.critical_branch_id)
            v_max = max((e.velocity_m_s for e in n.edges.values()),
                         default=0.0)
            rows.append([
                name, len(n.branches),
                round(n.fan_flow_m3_h, 0),
                round(n.fan_pressure_required_pa, 0),
                round(v_max, 2),
                crit_name,
            ])
        self.summary_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.summary_table, i, row)

        # Combobox сетей
        prev = self._current_network_name()
        self.net_combo.blockSignals(True)
        self.net_combo.clear()
        for name in nets.keys():
            self.net_combo.addItem(name)
        if prev:
            i = self.net_combo.findText(prev)
            if i >= 0:
                self.net_combo.setCurrentIndex(i)
        self.net_combo.blockSignals(False)

        self._refresh_edges_table()

    def _refresh_edges_table(self):
        net = self._current_network()
        if net is None:
            self.edges_table.setRowCount(0)
            self.fan_label.setText("")
            return
        root_lbl = _t("panel.eng.duct.parent_root")
        yes_lbl = _t("panel.eng.duct.terminal_yes")
        no_lbl = _t("panel.eng.duct.terminal_no")
        rows = []
        for e in net.edges.values():
            size = (f"Ø{e.diameter_mm:.0f}" if e.shape == "round"
                    else f"{e.width_mm:.0f}×{e.height_mm:.0f}")
            rows.append([
                e.edge_id,
                e.parent_id or root_lbl,
                yes_lbl if e.is_terminal else no_lbl,
                e.terminal_name or "—",
                round(e.flow_m3_h, 0),
                round(e.length_m, 1),
                size,
                round(e.velocity_m_s, 2),
                round(e.dp_friction_pa, 1),
                round(e.dp_local_pa, 1),
                round(e.dp_total_pa, 1),
            ])
        self.edges_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.edges_table, i, row)
        # Подсветка диктующей ветви
        crit_path = []
        if net.critical_branch_id:
            critical = next((b for b in net.branches
                             if b.terminal_edge_id == net.critical_branch_id),
                            None)
            if critical:
                crit_path = critical.edges
        for r in range(self.edges_table.rowCount()):
            eid_item = self.edges_table.item(r, 0)
            if eid_item and eid_item.text() in crit_path:
                for c in range(self.edges_table.columnCount()):
                    item = self.edges_table.item(r, c)
                    if item is not None:
                        item.setBackground(Qt.yellow)

        q = f"{net.fan_flow_m3_h:,.0f}".replace(",", " ")
        dp = f"{net.fan_pressure_required_pa:,.0f}".replace(",", " ")
        self.fan_label.setText(
            _t("panel.eng.duct.fan_label").format(q=q, dp=dp))


class _HydraulicsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.hyd.col.loop", "panel.eng.hyd.col.q",
        "panel.eng.hyd.col.h", "panel.eng.hyd.col.pump",
        "panel.eng.hyd.col.p", "panel.eng.hyd.col.vtank",
        "panel.eng.hyd.col.tank", "panel.eng.hyd.col.pmax",
        "panel.eng.hyd.col.makeup",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        toolbar = QHBoxLayout()
        self._lbl_h = QLabel(_t("panel.eng.hyd.h_static"))
        toolbar.addWidget(self._lbl_h)
        from PySide6.QtWidgets import QDoubleSpinBox
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.0, 200.0)
        self.height_spin.setSuffix(" м")
        self.height_spin.setValue(10.0)
        toolbar.addWidget(self.height_spin)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.hyd.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.dataLoaded, bridge.calculationDone):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_h.setText(_t("panel.eng.hyd.h_static"))
        self.run_btn.setText(_t("panel.eng.hyd.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.design_heating_hydraulics(
                static_height_m=self.height_spin.value())
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.hyd.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "heating_hydraulics_results",
                       {}) or {}
        rows = []
        for name, r in data.items():
            rows.append([
                name,
                round(r.pump.flow_m3_h, 2),
                round(r.pump.head_m, 2),
                r.pump.selected_model or "—",
                round(r.pump.selected_power_w, 0),
                round(r.expansion_tank.required_tank_volume_l, 1),
                r.expansion_tank.selected_model or "—",
                round(r.expansion_tank.p_max_bar, 2),
                round(r.makeup.daily_makeup_l, 1),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


class _RadiatorsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.rad.col.no", "panel.eng.rad.col.space",
        "panel.eng.rad.col.q", "panel.eng.rad.col.model",
        "panel.eng.rad.col.height", "panel.eng.rad.col.size",
        "panel.eng.rad.col.qfact", "panel.eng.rad.col.margin",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        toolbar = QHBoxLayout()
        self._lbl_fam = QLabel(_t("panel.eng.rad.family"))
        toolbar.addWidget(self._lbl_fam)
        self.family_combo = QComboBox()
        self.family_combo.addItem(_t("panel.eng.rad.family.all"), userData=None)
        for fam in [
            "Стальной панельный 11", "Стальной панельный 22",
            "Стальной панельный 33", "Алюминий",
            "Биметалл", "Биметалл (моноблок)", "Чугун",
        ]:
            self.family_combo.addItem(fam, userData=fam)
        toolbar.addWidget(self.family_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.rad.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_fam.setText(_t("panel.eng.rad.family"))
        prev_data = self.family_combo.currentData()
        self.family_combo.blockSignals(True)
        self.family_combo.clear()
        self.family_combo.addItem(_t("panel.eng.rad.family.all"), userData=None)
        for fam in [
            "Стальной панельный 11", "Стальной панельный 22",
            "Стальной панельный 33", "Алюминий",
            "Биметалл", "Биметалл (моноблок)", "Чугун",
        ]:
            self.family_combo.addItem(fam, userData=fam)
        for i in range(self.family_combo.count()):
            if self.family_combo.itemData(i) == prev_data:
                self.family_combo.setCurrentIndex(i)
                break
        self.family_combo.blockSignals(False)
        self.run_btn.setText(_t("panel.eng.rad.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        fam = self.family_combo.currentData()
        filter_list = [fam] if fam else None
        try:
            self.project.select_radiators_for_all_spaces(
                family_filter=filter_list)
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.rad.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "radiator_picks", {}) or {}
        rows = []
        for sp in self.project.spaces:
            pick = data.get(sp.space_id)
            if pick is None:
                continue
            length_or_sect = (
                _t("panel.eng.rad.sect").format(n=pick.sections)
                if pick.model.is_sectional
                else _t("panel.eng.rad.mm").format(n=pick.model.length_mm))
            rows.append([
                sp.number, sp.name,
                round(sp.heat_loss_w, 0),
                pick.model.name,
                pick.model.height_mm,
                length_or_sect,
                round(pick.actual_power_w, 0),
                round(pick.margin_pct, 1),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


class _AcousticsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.ac.col.ahu", "panel.eng.ac.col.norm",
        "panel.eng.ac.col.lp", "panel.eng.ac.col.margin",
        "panel.eng.ac.col.silencer", "panel.eng.ac.col.length",
        "panel.eng.ac.col.dp",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.ac.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.ac.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.ac.info"))
        self.run_btn.setText(_t("panel.eng.ac.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        try:
            self.project.analyze_acoustics_for_ahus()
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.ac.status"), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "acoustics_results", {}) or {}
        rows = []
        for name, a in data.items():
            sil = a.silencer_selected
            rows.append([
                name,
                round(a.lpa_required_dba, 1),
                round(a.lpa_at_terminal, 1),
                round(a.margin_dba, 1),
                sil.name if sil else "—",
                sil.length_mm if sil else "—",
                round(sil.pressure_drop_pa, 0) if sil else "—",
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


# ---------------------------------------------------------------------------
# Главная панель
# ---------------------------------------------------------------------------

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


class _FancoilsTab(QWidget):
    HEADER_KEYS = (
        "panel.eng.fc.col.no", "panel.eng.fc.col.space",
        "panel.eng.fc.col.qc", "panel.eng.fc.col.qh",
        "panel.eng.fc.col.model", "panel.eng.fc.col.family",
        "panel.eng.fc.col.pipes", "panel.eng.fc.col.qc_fact",
        "panel.eng.fc.col.margin", "panel.eng.fc.col.air",
        "panel.eng.fc.col.noise",
    )
    PIPES = (
        ("panel.eng.fc.pipes.any", None),
        ("panel.eng.fc.pipes.2", 2),
        ("panel.eng.fc.pipes.4", 4),
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        toolbar = QHBoxLayout()
        self._lbl_fam = QLabel(_t("panel.eng.fc.family"))
        toolbar.addWidget(self._lbl_fam)
        self.family_combo = QComboBox()
        self.family_combo.addItem(_t("panel.eng.fc.family.all"), userData=None)
        for fam in ("Кассетный 600×600", "Кассетный 600×600 (Roundflow)",
                     "Канальный низконапорный",
                     "Канальный среднего напора", "Настенный",
                     "Напольно-потолочный"):
            self.family_combo.addItem(fam, userData=fam)
        toolbar.addWidget(self.family_combo)
        toolbar.addSpacing(12)
        self._lbl_pipes = QLabel(_t("panel.eng.fc.pipes"))
        toolbar.addWidget(self._lbl_pipes)
        self.pipes_combo = QComboBox()
        for key, code in self.PIPES:
            self.pipes_combo.addItem(_t(key), userData=code)
        toolbar.addWidget(self.pipes_combo)
        toolbar.addStretch(1)
        self.run_btn = QPushButton(_t("panel.eng.fc.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        _setup_table(self.table, [_t(k) for k in self.HEADER_KEYS])
        outer.addWidget(self.table, stretch=1)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh)
        self._refresh()

    def retranslate_ui(self) -> None:
        self._lbl_fam.setText(_t("panel.eng.fc.family"))
        self._lbl_pipes.setText(_t("panel.eng.fc.pipes"))
        prev_fam = self.family_combo.currentData()
        self.family_combo.blockSignals(True)
        self.family_combo.clear()
        self.family_combo.addItem(_t("panel.eng.fc.family.all"), userData=None)
        for fam in ("Кассетный 600×600", "Кассетный 600×600 (Roundflow)",
                     "Канальный низконапорный",
                     "Канальный среднего напора", "Настенный",
                     "Напольно-потолочный"):
            self.family_combo.addItem(fam, userData=fam)
        for i in range(self.family_combo.count()):
            if self.family_combo.itemData(i) == prev_fam:
                self.family_combo.setCurrentIndex(i)
                break
        self.family_combo.blockSignals(False)

        prev_pipes = self.pipes_combo.currentData()
        self.pipes_combo.blockSignals(True)
        self.pipes_combo.clear()
        for key, code in self.PIPES:
            self.pipes_combo.addItem(_t(key), userData=code)
        for i in range(self.pipes_combo.count()):
            if self.pipes_combo.itemData(i) == prev_pipes:
                self.pipes_combo.setCurrentIndex(i)
                break
        self.pipes_combo.blockSignals(False)

        self.run_btn.setText(_t("panel.eng.fc.btn_run"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in self.HEADER_KEYS])
        self._refresh()

    def _run(self):
        fam = self.family_combo.currentData()
        family_filter = [fam] if fam else None
        pipes = self.pipes_combo.currentData()
        try:
            self.project.select_fancoils_for_project(
                family_filter=family_filter, pipes_filter=pipes,
            )
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.eng.fc.status"), 3000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh()

    def _refresh(self, *_):
        data = getattr(self.project, "fancoil_picks", {}) or {}
        rows = []
        for sp in self.project.spaces:
            pick = data.get(sp.space_id)
            if pick is None:
                continue
            rows.append([
                sp.number, sp.name,
                round(sp.heat_gain_w, 0),
                round(sp.heat_loss_w, 0),
                pick.model.name, pick.model.family,
                pick.model.pipes,
                round(pick.actual_cool_w, 0),
                round(pick.cool_margin_pct, 1),
                round(pick.model.air_flow_m3_h, 0),
                round(pick.model.noise_db_a, 0),
            ])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.table, i, row)


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
        hours = list(range(len(result.hourly_t_out_c)))
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


class EngineeringPanel(QWidget):
    """Подробная инженерия v4.1+v4.2 — 9 вкладок."""

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
