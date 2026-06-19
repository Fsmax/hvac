# -*- coding: utf-8 -*-
"""_GrillesTab — подбор воздухораспределительных решёток (каталог ARKTIKA).

Общий фильтр (монтаж / серия / предел шума LwA) применяется и к
калькулятору (подбор под введённый расход), и к подбору по всем
помещениям проекта (из Space.supply_m3h / exhaust_m3h).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


# Порядок типов монтажа в фильтре -> ключ i18n
_MOUNTS = [
    (None, "panel.eng.grille.mount.all"),
    ("wall", "panel.eng.grille.mount.wall"),
    ("plenum", "panel.eng.grille.mount.plenum"),
    ("round_duct", "panel.eng.grille.mount.round_duct"),
    ("slot", "panel.eng.grille.mount.slot"),
    ("transfer", "panel.eng.grille.mount.transfer"),
    ("floor", "panel.eng.grille.mount.floor"),
]
_LWA_CHOICES = [25, 30, 35, 40, 45]
# Предельная скорость в живом сечении, м/с (None — без ограничения)
_V_CHOICES = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


class _GrillesTab(QWidget):
    CALC_KEYS = (
        "panel.eng.grille.col.variant", "panel.eng.grille.col.size",
        "panel.eng.grille.col.qty", "panel.eng.grille.col.v",
        "panel.eng.grille.col.lwa", "panel.eng.grille.col.dp",
        "panel.eng.grille.col.throw", "panel.eng.grille.col.note",
    )
    PROJ_KEYS = (
        "panel.eng.grille.col.no", "panel.eng.grille.col.room",
        "panel.eng.grille.col.qs", "panel.eng.grille.col.gs",
        "panel.eng.grille.col.qe", "panel.eng.grille.col.ge",
    )

    def __init__(self, project, bridge, parent=None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._info = QLabel(_t("panel.eng.grille.info"))
        self._info.setProperty("role", "muted")
        self._info.setWordWrap(True)
        outer.addWidget(self._info)

        # --- общий фильтр: монтаж / серия / шум ---
        flt = QHBoxLayout()
        self._lbl_mount = QLabel(_t("panel.eng.grille.mount"))
        flt.addWidget(self._lbl_mount)
        self.mount_combo = QComboBox()
        self._fill_mount_combo()
        self.mount_combo.currentIndexChanged.connect(self._reload_families)
        flt.addWidget(self.mount_combo)

        self._lbl_fam = QLabel(_t("panel.eng.grille.family"))
        flt.addWidget(self._lbl_fam)
        self.family_combo = QComboBox()
        self._fill_family_combo()
        flt.addWidget(self.family_combo)

        self._lbl_lwa = QLabel(_t("panel.eng.grille.lwa"))
        flt.addWidget(self._lbl_lwa)
        self.lwa_combo = QComboBox()
        for v in _LWA_CHOICES:
            self.lwa_combo.addItem(f"{v}", userData=v)
        self.lwa_combo.setCurrentIndex(_LWA_CHOICES.index(35))
        flt.addWidget(self.lwa_combo)
        self._lbl_lwa_u = QLabel(_t("panel.eng.grille.lwa.unit"))
        self._lbl_lwa_u.setProperty("role", "muted")
        flt.addWidget(self._lbl_lwa_u)

        self._lbl_vel = QLabel(_t("panel.eng.grille.vel"))
        flt.addWidget(self._lbl_vel)
        self.vel_combo = QComboBox()
        self._fill_vel_combo()
        flt.addWidget(self.vel_combo)
        self._lbl_vel_u = QLabel(_t("panel.eng.grille.vel.unit"))
        self._lbl_vel_u.setProperty("role", "muted")
        flt.addWidget(self._lbl_vel_u)

        self._lbl_size = QLabel(_t("panel.eng.grille.size"))
        flt.addWidget(self._lbl_size)
        self.amax_spin = QSpinBox()
        self._setup_size_spin(self.amax_spin, "A≤ ")
        flt.addWidget(self.amax_spin)
        self.bmax_spin = QSpinBox()
        self._setup_size_spin(self.bmax_spin, "B≤ ")
        flt.addWidget(self.bmax_spin)
        flt.addStretch(1)
        outer.addLayout(flt)

        # --- калькулятор ---
        self._calc_title = QLabel(_t("panel.eng.grille.calc.title"))
        self._calc_title.setProperty("role", "h2")
        outer.addWidget(self._calc_title)
        calc = QHBoxLayout()
        self._lbl_flow = QLabel(_t("panel.eng.grille.calc.flow"))
        calc.addWidget(self._lbl_flow)
        self.flow_spin = QDoubleSpinBox()
        self.flow_spin.setRange(5.0, 100000.0)
        self.flow_spin.setDecimals(0)
        self.flow_spin.setSingleStep(50.0)
        self.flow_spin.setValue(300.0)
        calc.addWidget(self.flow_spin)
        self.calc_btn = QPushButton(_t("panel.eng.grille.calc.btn"))
        self.calc_btn.setProperty("role", "primary")
        self.calc_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.calc_btn.clicked.connect(self._run_calc)
        calc.addWidget(self.calc_btn)
        calc.addStretch(1)
        outer.addLayout(calc)

        self.calc_table = QTableWidget(0, 0)
        _setup_table(self.calc_table, [_t(k) for k in self.CALC_KEYS])
        self.calc_table.setMaximumHeight(190)
        outer.addWidget(self.calc_table)

        # --- по помещениям проекта ---
        proj = QHBoxLayout()
        self._proj_title = QLabel(_t("panel.eng.grille.proj.title"))
        self._proj_title.setProperty("role", "h2")
        proj.addWidget(self._proj_title)
        proj.addStretch(1)
        self.proj_btn = QPushButton(_t("panel.eng.grille.proj.btn"))
        self.proj_btn.setProperty("role", "primary")
        self.proj_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.proj_btn.clicked.connect(self._run_project)
        proj.addWidget(self.proj_btn)
        outer.addLayout(proj)

        self.proj_table = QTableWidget(0, 0)
        _setup_table(self.proj_table, [_t(k) for k in self.PROJ_KEYS])
        outer.addWidget(self.proj_table, stretch=1)

        for sig in (bridge.calculationDone,):
            sig.connect(self._refresh_project)
        self._refresh_project()

    # ---------- наполнение комбобоксов ----------
    def _fill_mount_combo(self):
        from hvac.grille_catalog import grille_mounts
        present = set(grille_mounts())
        self.mount_combo.blockSignals(True)
        self.mount_combo.clear()
        for key, i18n in _MOUNTS:
            if key is None or key in present:
                self.mount_combo.addItem(_t(i18n), userData=key)
        self.mount_combo.blockSignals(False)

    def _fill_family_combo(self):
        from hvac.grille_catalog import grille_families
        mount = self.mount_combo.currentData()
        from hvac.grille_catalog import GRILLE_CATALOG
        if mount:
            codes = []
            for m in GRILLE_CATALOG:
                if m.mount == mount and m.family_code not in codes:
                    codes.append(m.family_code)
            fams = [(c, n) for c, n in grille_families() if c in codes]
        else:
            fams = grille_families()
        self.family_combo.blockSignals(True)
        self.family_combo.clear()
        self.family_combo.addItem(_t("panel.eng.grille.family.all"),
                                  userData=None)
        for code, _name in fams:
            self.family_combo.addItem(code, userData=code)
        self.family_combo.blockSignals(False)

    def _fill_vel_combo(self):
        self.vel_combo.blockSignals(True)
        self.vel_combo.clear()
        self.vel_combo.addItem(_t("panel.eng.grille.vel.any"), userData=None)
        for v in _V_CHOICES:
            self.vel_combo.addItem(f"{v:g}", userData=v)
        self.vel_combo.blockSignals(False)

    def _setup_size_spin(self, spin, prefix: str):
        """Спинбокс предела габарита, мм: 0 -> без ограничения («—»)."""
        spin.setRange(0, 2000)
        spin.setSingleStep(50)
        spin.setPrefix(prefix)
        spin.setSuffix(_t("panel.eng.grille.size.unit"))
        spin.setSpecialValueText(prefix + _t("panel.eng.grille.dash"))
        spin.setValue(0)

    def _reload_families(self):
        self._fill_family_combo()

    # ---------- параметры подбора из фильтра ----------
    def _filter_kwargs(self) -> dict:
        fam = self.family_combo.currentData()
        return {
            "max_lwa": float(self.lwa_combo.currentData()),
            "mount": self.mount_combo.currentData(),
            "families": [fam] if fam else None,
            "max_velocity": self.vel_combo.currentData(),
            "max_a_mm": self.amax_spin.value() or None,
            "max_b_mm": self.bmax_spin.value() or None,
        }

    # ---------- калькулятор ----------
    def _run_calc(self):
        from hvac.grille_catalog import select_grilles
        flow = float(self.flow_spin.value())
        try:
            picks = select_grilles(flow, n_best=6, **self._filter_kwargs())
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        if not picks:
            self.calc_table.setRowCount(0)
            self.bridge.statusMessage.emit(_t("panel.eng.grille.calc.empty"),
                                           5000)
            return
        dash = _t("panel.eng.grille.dash")
        rows = []
        for p in picks:
            m = p.model
            rows.append([
                "/".join(m.variants),
                m.size_label(),
                p.n_units,
                round(p.velocity, 1),
                round(p.lwa) if p.lwa is not None else dash,
                round(p.dp, 1) if p.dp is not None else dash,
                round(p.throw_05, 1) if p.throw_05 is not None else dash,
                "; ".join(p.warnings),
            ])
        self.calc_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.calc_table, i, row)

    # ---------- подбор по помещениям ----------
    def _run_project(self):
        try:
            picks = self.project.select_grilles_for_all_spaces(
                **self._filter_kwargs())
        except Exception as e:
            QMessageBox.critical(self, _t("panel.eng.common.error"), str(e))
            return
        if not picks:
            QMessageBox.information(
                self, _t("panel.eng.grille.proj.title"),
                _t("panel.eng.grille.proj.none"))
            return
        self.bridge.statusMessage.emit(
            _t("panel.eng.grille.proj.status").format(n=len(picks)), 4000)
        self.bridge.dirtyChanged.emit(True)
        self._refresh_project()

    @staticmethod
    def _pick_str(pick, dash: str) -> str:
        if pick is None:
            return dash
        m = pick.model
        s = f"{'/'.join(m.variants)} {m.size_label()}".strip()
        if pick.n_units > 1:
            s += f" ×{pick.n_units}"
        return s

    def _refresh_project(self, *_):
        data = getattr(self.project, "grille_picks", {}) or {}
        dash = _t("panel.eng.grille.dash")
        rows = []
        for sp in self.project.spaces:
            rp = data.get(sp.space_id)
            if rp is None:
                continue
            rows.append([
                sp.number, sp.name,
                round(getattr(sp, "supply_m3h", 0.0) or 0.0, 0),
                self._pick_str(rp.supply, dash),
                round(getattr(sp, "exhaust_m3h", 0.0) or 0.0, 0),
                self._pick_str(rp.exhaust, dash),
            ])
        self.proj_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            _set_row(self.proj_table, i, row)

    # ---------- i18n ----------
    def retranslate_ui(self) -> None:
        self._info.setText(_t("panel.eng.grille.info"))
        self._lbl_mount.setText(_t("panel.eng.grille.mount"))
        self._lbl_fam.setText(_t("panel.eng.grille.family"))
        self._lbl_lwa.setText(_t("panel.eng.grille.lwa"))
        self._lbl_lwa_u.setText(_t("panel.eng.grille.lwa.unit"))
        self._lbl_vel.setText(_t("panel.eng.grille.vel"))
        self._lbl_vel_u.setText(_t("panel.eng.grille.vel.unit"))
        self._lbl_size.setText(_t("panel.eng.grille.size"))
        for spin, pfx in ((self.amax_spin, "A≤ "), (self.bmax_spin, "B≤ ")):
            spin.setSuffix(_t("panel.eng.grille.size.unit"))
            spin.setSpecialValueText(pfx + _t("panel.eng.grille.dash"))
        self._calc_title.setText(_t("panel.eng.grille.calc.title"))
        self._lbl_flow.setText(_t("panel.eng.grille.calc.flow"))
        self.calc_btn.setText(_t("panel.eng.grille.calc.btn"))
        self._proj_title.setText(_t("panel.eng.grille.proj.title"))
        self.proj_btn.setText(_t("panel.eng.grille.proj.btn"))
        prev_mount = self.mount_combo.currentData()
        prev_fam = self.family_combo.currentData()
        self._fill_mount_combo()
        idx = self.mount_combo.findData(prev_mount)
        if idx >= 0:
            self.mount_combo.setCurrentIndex(idx)
        self._fill_family_combo()
        idx = self.family_combo.findData(prev_fam)
        if idx >= 0:
            self.family_combo.setCurrentIndex(idx)
        prev_vel = self.vel_combo.currentData()
        self._fill_vel_combo()
        idx = self.vel_combo.findData(prev_vel)
        if idx >= 0:
            self.vel_combo.setCurrentIndex(idx)
        self.calc_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.CALC_KEYS])
        self.proj_table.setHorizontalHeaderLabels(
            [_t(k) for k in self.PROJ_KEYS])
        self._refresh_project()
