# -*- coding: utf-8 -*-
"""_DuctTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


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


