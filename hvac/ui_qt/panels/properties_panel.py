# -*- coding: utf-8 -*-
"""PropertiesPanel — детали выделенного объекта (помещение / конструкция).

Показывается справа в SpacesPanel и других панелях, где есть выбор объекта.
Содержит редактируемые поля + breakdown расчёта.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from hvac.catalogs.room_types import (
    apply_room_type_defaults, get_all_room_types,
)
from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge


class PropertiesPanel(QWidget):
    """Reactive details-view выделенного помещения."""

    valueChanged = Signal()

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._space: Optional[Space] = None
        self._loading = False

        self._build_ui()
        self.bridge.calculationDone.connect(self._refresh_breakdown)
        self.show_space(None)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Скролл — у помещения много полей
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(20, 20, 20, 20)
        col.setSpacing(16)

        # Заголовок
        self.title_lbl = QLabel(_t("panel.props.empty"))
        self.title_lbl.setProperty("role", "h2")
        self.title_lbl.setWordWrap(True)
        col.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setProperty("role", "muted")
        self.subtitle_lbl.setWordWrap(True)
        col.addWidget(self.subtitle_lbl)

        self.empty_hint = QLabel(_t("panel.props.hint"))
        self.empty_hint.setProperty("role", "hint")
        self.empty_hint.setWordWrap(True)
        col.addWidget(self.empty_hint)

        # Редактируемые поля
        self.form = QFormLayout()
        self.form.setSpacing(8)
        self.form.setLabelAlignment(Qt.AlignLeft)

        self.type_combo = QComboBox()
        self.type_combo.addItems(get_all_room_types())
        self.type_combo.setEditable(True)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._lbl_type = QLabel(_t("panel.props.field.type"))
        self.form.addRow(self._lbl_type, self.type_combo)

        self.t_heat_spin = QDoubleSpinBox()
        self.t_heat_spin.setRange(-10.0, 40.0)
        self.t_heat_spin.setSuffix(" °C")
        self.t_heat_spin.setDecimals(1)
        self.t_heat_spin.valueChanged.connect(self._on_t_heat)
        self._lbl_t_heat = QLabel(_t("panel.props.field.t_heat"))
        self.form.addRow(self._lbl_t_heat, self.t_heat_spin)

        self.t_cool_spin = QDoubleSpinBox()
        self.t_cool_spin.setRange(15.0, 40.0)
        self.t_cool_spin.setSuffix(" °C")
        self.t_cool_spin.setDecimals(1)
        self.t_cool_spin.valueChanged.connect(self._on_t_cool)
        self._lbl_t_cool = QLabel(_t("panel.props.field.t_cool"))
        self.form.addRow(self._lbl_t_cool, self.t_cool_spin)

        self.occup_spin = QDoubleSpinBox()
        self.occup_spin.setRange(0.0, 1000.0)
        self.occup_spin.setDecimals(1)
        self.occup_spin.setSuffix(_t("panel.props.suffix.people"))
        self.occup_spin.valueChanged.connect(self._on_occup)
        self._lbl_occup = QLabel(_t("panel.props.field.occup"))
        self.form.addRow(self._lbl_occup, self.occup_spin)

        self.light_spin = QDoubleSpinBox()
        self.light_spin.setRange(0.0, 200.0)
        self.light_spin.setSuffix(" Вт/м²")
        self.light_spin.setDecimals(1)
        self.light_spin.valueChanged.connect(self._on_light)
        self._lbl_light = QLabel(_t("panel.props.field.light"))
        self.form.addRow(self._lbl_light, self.light_spin)

        self.equip_spin = QDoubleSpinBox()
        self.equip_spin.setRange(0.0, 500.0)
        self.equip_spin.setSuffix(" Вт/м²")
        self.equip_spin.setDecimals(1)
        self.equip_spin.valueChanged.connect(self._on_equip)
        self._lbl_equip = QLabel(_t("panel.props.field.equip"))
        self.form.addRow(self._lbl_equip, self.equip_spin)

        self.inf_spin = QDoubleSpinBox()
        self.inf_spin.setRange(0.0, 10.0)
        self.inf_spin.setSuffix(" 1/ч")
        self.inf_spin.setDecimals(2)
        self.inf_spin.valueChanged.connect(self._on_inf)
        self._lbl_inf = QLabel(_t("panel.props.field.inf"))
        self.form.addRow(self._lbl_inf, self.inf_spin)

        # Чекбоксы — геометрические признаки
        flags_row = QHBoxLayout()
        flags_row.setSpacing(12)
        self.corner_cb = QCheckBox(_t("panel.props.flag.corner"))
        self.corner_cb.toggled.connect(self._on_corner)
        self.roof_cb = QCheckBox(_t("panel.props.flag.roof"))
        self.roof_cb.toggled.connect(self._on_roof)
        self.floor_cb = QCheckBox(_t("panel.props.flag.floor"))
        self.floor_cb.toggled.connect(self._on_floor)
        self.unheated_cb = QCheckBox(_t("panel.props.flag.unheated"))
        self.unheated_cb.toggled.connect(self._on_unheated)
        # Воздушное отопление/охлаждение: помещение обслуживается приточным
        # воздухом (расход приточки подбирается по нагрузке — см. air_heating).
        self.air_heat_cb = QCheckBox(_t("panel.props.flag.air_heat"))
        self.air_heat_cb.toggled.connect(self._on_air_heat)
        self.air_cool_cb = QCheckBox(_t("panel.props.flag.air_cool"))
        self.air_cool_cb.toggled.connect(self._on_air_cool)
        flags_row.addWidget(self.corner_cb)
        flags_row.addWidget(self.roof_cb)
        flags_row.addWidget(self.floor_cb)
        flags_row.addWidget(self.unheated_cb)
        flags_row.addWidget(self.air_heat_cb)
        flags_row.addWidget(self.air_cool_cb)
        flags_row.addStretch(1)

        self._lbl_flags = QLabel(_t("panel.props.field.flags"))
        self.form.addRow(self._lbl_flags, _row_widget(flags_row))

        col.addLayout(self.form)

        # Breakdown результатов расчёта
        col.addSpacing(8)
        self._results_title = QLabel(_t("panel.props.results.title"))
        self._results_title.setProperty("role", "h2")
        col.addWidget(self._results_title)

        self.breakdown_lbl = QLabel(_t("panel.props.results.not_yet"))
        self.breakdown_lbl.setProperty("role", "muted")
        self.breakdown_lbl.setWordWrap(True)
        self.breakdown_lbl.setTextFormat(Qt.RichText)
        col.addWidget(self.breakdown_lbl)

        col.addStretch(1)

    # ---------- API ----------
    def show_space(self, sp: Optional[Space]) -> None:
        self._space = sp
        self._loading = True
        try:
            if sp is None:
                self.title_lbl.setText(_t("panel.props.empty"))
                self.subtitle_lbl.setText(_t("panel.props.nothing"))
                self.empty_hint.setVisible(True)
                self._set_form_enabled(False)
                self.breakdown_lbl.setText("")
                return

            self.title_lbl.setText(f"{sp.number} · {sp.name}")
            user_mark = _t("panel.props.user_mark") if sp.user_modified else ""
            self.subtitle_lbl.setText(_t("panel.props.subtitle").format(
                level=sp.level, area=sp.area_m2,
                volume=sp.volume_m3, mod=user_mark))
            self.empty_hint.setVisible(False)
            self._set_form_enabled(True)

            self.type_combo.setCurrentText(sp.room_type or "")
            self.t_heat_spin.setValue(float(sp.t_in_heat))
            self.t_cool_spin.setValue(float(sp.t_in_cool))
            self.occup_spin.setValue(float(sp.occupancy_people))
            self.light_spin.setValue(float(sp.lighting_w_m2))
            self.equip_spin.setValue(float(sp.equipment_w_m2))
            self.inf_spin.setValue(float(sp.ach_inf))
            self.corner_cb.setChecked(bool(sp.is_corner))
            self.roof_cb.setChecked(bool(sp.has_roof))
            self.floor_cb.setChecked(bool(sp.has_floor_to_ground))
            self.unheated_cb.setChecked(sp.floor_over_unheated_n > 0)
            self.air_heat_cb.setChecked(bool(sp.air_heating))
            self.air_cool_cb.setChecked(bool(sp.air_cooling))
            self._refresh_breakdown()
        finally:
            self._loading = False

    # ---------- Обработчики ----------
    def _set_form_enabled(self, enabled: bool) -> None:
        for w in (self.type_combo, self.t_heat_spin, self.t_cool_spin,
                  self.occup_spin, self.light_spin, self.equip_spin,
                  self.inf_spin, self.corner_cb, self.roof_cb, self.floor_cb,
                  self.unheated_cb, self.air_heat_cb, self.air_cool_cb):
            w.setEnabled(enabled)

    def _mark_dirty(self) -> None:
        if self._space and not self._loading:
            self._space.user_modified = True
            self.bridge.dirtyChanged.emit(True)
            self.valueChanged.emit()

    def _on_type_changed(self, value: str) -> None:
        if self._loading or not self._space:
            return
        self._space.room_type = value
        apply_room_type_defaults(self._space)
        # После применения дефолтов — перечитаем форму
        was_loading = self._loading
        self._loading = True
        try:
            self.t_heat_spin.setValue(float(self._space.t_in_heat))
            self.t_cool_spin.setValue(float(self._space.t_in_cool))
            self.occup_spin.setValue(float(self._space.occupancy_people))
            self.light_spin.setValue(float(self._space.lighting_w_m2))
            self.equip_spin.setValue(float(self._space.equipment_w_m2))
            self.inf_spin.setValue(float(self._space.ach_inf))
        finally:
            self._loading = was_loading
        self._mark_dirty()

    def _on_t_heat(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.t_in_heat = float(v)
            self._mark_dirty()

    def _on_t_cool(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.t_in_cool = float(v)
            self._mark_dirty()

    def _on_occup(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.occupancy_people = float(v)
            self._mark_dirty()

    def _on_light(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.lighting_w_m2 = float(v)
            self._mark_dirty()

    def _on_equip(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.equipment_w_m2 = float(v)
            self._mark_dirty()

    def _on_inf(self, v: float) -> None:
        if self._space and not self._loading:
            self._space.ach_inf = float(v)
            self._mark_dirty()

    def _on_corner(self, v: bool) -> None:
        if self._space and not self._loading:
            self._space.is_corner = bool(v)
            self._mark_dirty()

    def _on_roof(self, v: bool) -> None:
        if self._space and not self._loading:
            self._space.has_roof = bool(v)
            self._mark_dirty()

    def _on_floor(self, v: bool) -> None:
        if self._space and not self._loading:
            self._space.has_floor_to_ground = bool(v)
            self._mark_dirty()

    def _on_unheated(self, v: bool) -> None:
        if self._space and not self._loading:
            # КМК Табл.3: над неотап. подвалом n=0.6 (типовое). Значения
            # 0.4 (техподполье) / 0.8 (холодный подвал) задаются через JSON.
            self._space.floor_over_unheated_n = 0.6 if v else 0.0
            self._mark_dirty()

    def _on_air_heat(self, v: bool) -> None:
        if self._space and not self._loading:
            self._space.air_heating = bool(v)
            self._mark_dirty()

    def _on_air_cool(self, v: bool) -> None:
        if self._space and not self._loading:
            self._space.air_cooling = bool(v)
            self._mark_dirty()

    # ---------- Breakdown ----------
    def _refresh_breakdown(self, *args: object) -> None:
        sp = self._space
        if not sp:
            return
        if not sp.heat_loss_breakdown and not sp.heat_gain_breakdown:
            self.breakdown_lbl.setText(_t("panel.props.results.not_yet"))
            return

        def fmt_block(title: str, breakdown: dict, total_w: float) -> str:
            if not breakdown:
                return ""
            lines = [_t("panel.props.block_header").format(
                title=title, kw=total_w / 1000)]
            items = sorted(
                ((k, v) for k, v in breakdown.items() if k != "ИТОГО" and v),
                key=lambda kv: -abs(kv[1]),
            )
            for k, v in items:
                lines.append(_t("panel.props.block_row").format(key=k, w=v))
            return "<br>".join(lines)

        parts = [
            fmt_block(_t("panel.props.heat_loss_label"),
                       sp.heat_loss_breakdown, sp.heat_loss_w),
            fmt_block(_t("panel.props.heat_gain_label"),
                       sp.heat_gain_breakdown, sp.heat_gain_w),
        ]
        self.breakdown_lbl.setText("<br><br>".join(p for p in parts if p))

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        # Метки полей
        self._lbl_type.setText(_t("panel.props.field.type"))
        self._lbl_t_heat.setText(_t("panel.props.field.t_heat"))
        self._lbl_t_cool.setText(_t("panel.props.field.t_cool"))
        self._lbl_occup.setText(_t("panel.props.field.occup"))
        self._lbl_light.setText(_t("panel.props.field.light"))
        self._lbl_equip.setText(_t("panel.props.field.equip"))
        self._lbl_inf.setText(_t("panel.props.field.inf"))
        self._lbl_flags.setText(_t("panel.props.field.flags"))
        self.occup_spin.setSuffix(_t("panel.props.suffix.people"))
        self.corner_cb.setText(_t("panel.props.flag.corner"))
        self.roof_cb.setText(_t("panel.props.flag.roof"))
        self.floor_cb.setText(_t("panel.props.flag.floor"))
        self.unheated_cb.setText(_t("panel.props.flag.unheated"))
        self.air_heat_cb.setText(_t("panel.props.flag.air_heat"))
        self.air_cool_cb.setText(_t("panel.props.flag.air_cool"))
        self.empty_hint.setText(_t("panel.props.hint"))
        self._results_title.setText(_t("panel.props.results.title"))
        # Если есть выбранное помещение — пересоберём subtitle и breakdown
        if self._space is not None:
            self.show_space(self._space)


def _row_widget(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return w
