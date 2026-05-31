# -*- coding: utf-8 -*-
"""_AcousticsTab — вынесено из engineering_panel (монолит)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget
from hvac.i18n import t as _t
from hvac.ui_qt.panels.engineering_panel._common import _setup_table, _set_row


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

