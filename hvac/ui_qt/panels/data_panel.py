# -*- coding: utf-8 -*-
"""DataPanel — параметры проекта, загрузка/сохранение, выбор климата.

Замена связки: Tk-вкладок «Данные» + «Параметры» + меню «Файл».
Сделана как одна прокручиваемая страница из карточек.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Callable, List

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from hvac.catalogs.climate import CLIMATE_DB
from hvac.engine import list_engines
from hvac.i18n import t as _t
from hvac.io_json import load_project, save_project
from hvac.ui_qt import settings as user_settings
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card
from hvac.ui_qt.widgets.city_combo import CityCombo


class _RevitImportWorker(QObject):
    """Выгрузка геометрии из Revit в фоне (модель может быть большой)."""
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, folder: str):
        super().__init__()
        self._folder = folder

    def run(self) -> None:
        try:
            from hvac.revit_link import import_from_revit
            self.finished.emit(import_from_revit(self._folder))
        except Exception as e:
            self.failed.emit(str(e))


class _RevitTaskWorker(QObject):
    """Произвольная операция живого моста Revit в фоновом потоке."""
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.failed.emit(str(e))


class DataPanel(QWidget):
    """Корневая панель «Данные проекта»."""

    # Сигнал наружу: при успешной загрузке/создании что-то поменялось.
    # Главное окно слушает через bridge, но иногда нужно «локально» обновить.
    csvLoaded = Signal()

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._spaces_path: str = ""
        self._thermal_path: str = ""
        # Список «переводчиков» — функций, которые перерисовывают подпись
        # конкретного виджета по текущему языку. Заполняется в _build_ui
        # и вызывается из retranslate_ui() при смене языка.
        self._translators: List[Callable[[], None]] = []

        self._build_ui()
        self._wire_bridge()
        self._refresh_from_project()

    # ---------- Translators ----------
    def _tr(self, fn: Callable[[], None]) -> None:
        """Регистрирует и сразу выполняет переводчик."""
        fn()
        self._translators.append(fn)

    def _tr_label(self, label: QLabel, key: str) -> None:
        self._tr(lambda: label.setText(_t(key)))

    def _tr_button(self, btn: QPushButton, key: str) -> None:
        self._tr(lambda: btn.setText(_t(key)))

    def _tr_check(self, cb: QCheckBox, key: str) -> None:
        self._tr(lambda: cb.setText(_t(key)))

    def _tr_card(self, card: Card, title_key: str, sub_key: str) -> None:
        def apply():
            card.set_title(_t(title_key))
            card.set_subtitle(_t(sub_key))
        self._tr(apply)

    def _tr_placeholder(self, edit: QLineEdit, key: str) -> None:
        self._tr(lambda: edit.setPlaceholderText(_t(key)))

    def retranslate_ui(self) -> None:
        """Вызывается из main_window после set_language."""
        for fn in self._translators:
            try:
                fn()
            except Exception:
                traceback.print_exc()
        # Сводка зависит от data — пересчитываем
        self._refresh_summary()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        col = QVBoxLayout(content)
        col.setContentsMargins(32, 28, 32, 32)
        col.setSpacing(20)

        # Заголовок страницы
        self.h_title = QLabel()
        self.h_title.setProperty("role", "h1")
        col.addWidget(self.h_title)
        self._tr_label(self.h_title, "panel.data.title")

        self.h_sub = QLabel()
        self.h_sub.setProperty("role", "muted")
        col.addWidget(self.h_sub)
        self._tr_label(self.h_sub, "panel.data.subtitle")
        col.addSpacing(8)

        # Двух-колоночная сетка карточек
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        col.addLayout(grid)

        grid.addWidget(self._build_project_card(),  0, 0, Qt.AlignTop)
        grid.addWidget(self._build_climate_card(),  0, 1, Qt.AlignTop)
        grid.addWidget(self._build_sources_card(),  1, 0, 1, 2)
        grid.addWidget(self._build_actions_card(),  2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        col.addStretch(1)

    def _build_project_card(self) -> Card:
        card = Card("", "")
        self._tr_card(card, "panel.data.project.title", "panel.data.project.desc")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self._tr_placeholder(self.name_edit, "panel.data.field.name.ph")
        self.name_edit.editingFinished.connect(self._apply_name)
        self._lbl_name = QLabel()
        self._tr_label(self._lbl_name, "panel.data.field.name")
        form.addRow(self._lbl_name, self.name_edit)

        self.method_combo = QComboBox()
        for eng in list_engines():
            self.method_combo.addItem(eng)
        self.method_combo.currentTextChanged.connect(self._apply_methodology)
        self._lbl_method = QLabel()
        self._tr_label(self._lbl_method, "panel.data.field.method")
        form.addRow(self._lbl_method, self.method_combo)

        card.body().addLayout(form)
        return card

    def _build_climate_card(self) -> Card:
        card = Card("", "")
        self._tr_card(card, "panel.data.climate.title", "panel.data.climate.desc")

        form = QFormLayout()
        form.setSpacing(10)

        row = QHBoxLayout()
        self.city_combo = CityCombo()
        self.city_combo.currentIndexChanged.connect(self._apply_city)
        row.addWidget(self.city_combo, stretch=1)
        self._lbl_city = QLabel()
        self._tr_label(self._lbl_city, "panel.data.field.city")
        form.addRow(self._lbl_city, row)

        # Read-only вывод подобранных параметров
        self.lbl_t_heat = QLabel("—")
        self.lbl_t_cool = QLabel("—")
        self.lbl_gsop = QLabel("—")
        self.lbl_solar = QLabel("—")
        for lbl in (self.lbl_t_heat, self.lbl_t_cool, self.lbl_gsop, self.lbl_solar):
            lbl.setProperty("role", "pillAccent")
            lbl.setAlignment(Qt.AlignCenter)

        params = QGridLayout()
        params.setHorizontalSpacing(10)
        params.setVerticalSpacing(6)

        # Подписи капшнов хранятся для retranslate
        self._climate_captions: list[tuple[QLabel, str]] = []

        def add(row, col, key, value_lbl):
            cap = QLabel()
            cap.setProperty("role", "hint")
            self._tr_label(cap, key)
            params.addWidget(cap, row, col)
            params.addWidget(value_lbl, row + 1, col)

        add(0, 0, "panel.data.climate.t_heat_cap", self.lbl_t_heat)
        add(0, 1, "panel.data.climate.t_cool_cap", self.lbl_t_cool)
        add(2, 0, "panel.data.climate.gsop_cap",  self.lbl_gsop)
        add(2, 1, "panel.data.climate.solar_cap", self.lbl_solar)
        card.body().addLayout(form)
        card.body().addSpacing(8)
        card.body().addLayout(params)

        # Возможность ручной правки t_зима / t_лето поверх подобранного города
        override = QHBoxLayout()
        self.t_heat_spin = QDoubleSpinBox()
        self.t_heat_spin.setRange(-60.0, 30.0)
        self.t_heat_spin.setSuffix(" °C")
        self.t_heat_spin.setDecimals(1)
        self.t_heat_spin.valueChanged.connect(self._apply_t_heat)

        self.t_cool_spin = QDoubleSpinBox()
        self.t_cool_spin.setRange(0.0, 55.0)
        self.t_cool_spin.setSuffix(" °C")
        self.t_cool_spin.setDecimals(1)
        self.t_cool_spin.valueChanged.connect(self._apply_t_cool)

        cap = QLabel()
        cap.setProperty("role", "hint")
        self._tr_label(cap, "panel.data.climate.override")
        card.body().addSpacing(8)
        card.body().addWidget(cap)
        self._lbl_t_heat_short = QLabel()
        self._lbl_t_cool_short = QLabel()
        self._tr_label(self._lbl_t_heat_short, "panel.data.climate.t_heat_short")
        self._tr_label(self._lbl_t_cool_short, "panel.data.climate.t_cool_short")
        override.addWidget(self._lbl_t_heat_short)
        override.addWidget(self.t_heat_spin)
        override.addSpacing(12)
        override.addWidget(self._lbl_t_cool_short)
        override.addWidget(self.t_cool_spin)
        override.addStretch(1)
        card.body().addLayout(override)

        # Глобальный поворот True North — крутит ВСЕ ориентации фасадов
        # сразу (для солнечного расчёта). Заменяет ручную правку «стороны»
        # по каждому ограждению.
        self.true_north_spin = QDoubleSpinBox()
        self.true_north_spin.setRange(-180.0, 180.0)
        self.true_north_spin.setSingleStep(5.0)
        self.true_north_spin.setDecimals(0)
        self.true_north_spin.setSuffix(" °")
        self.true_north_spin.valueChanged.connect(self._apply_true_north)

        tn_row = QHBoxLayout()
        self._lbl_true_north = QLabel()
        self._tr_label(self._lbl_true_north, "panel.data.climate.true_north")
        tn_row.addWidget(self._lbl_true_north)
        tn_row.addWidget(self.true_north_spin)
        tn_row.addStretch(1)
        self._lbl_true_north_hint = QLabel()
        self._lbl_true_north_hint.setProperty("role", "hint")
        self._lbl_true_north_hint.setWordWrap(True)
        self._tr_label(self._lbl_true_north_hint, "panel.data.climate.true_north_hint")
        card.body().addSpacing(8)
        card.body().addLayout(tn_row)
        card.body().addWidget(self._lbl_true_north_hint)

        # Затенение от солнца (жалюзи / маркизы / козырьки) — глобальный
        # множитель к теплопоступлениям через остекление. Меньше — меньше
        # летняя нагрузка.
        self._shading_specs = (
            ("panel.data.climate.shade_none",  1.0),
            ("panel.data.climate.shade_inner", 0.7),
            ("panel.data.climate.shade_outer", 0.5),
            ("panel.data.climate.shade_deep",  0.3),
        )
        self.shading_combo = QComboBox()
        for label_key, factor in self._shading_specs:
            self.shading_combo.addItem(_t(label_key), factor)
        self.shading_combo.currentIndexChanged.connect(self._apply_shading)

        # Перевод пунктов при смене языка (порядок фиксирован, фактор в data).
        def _retranslate_shading() -> None:
            for i, (lk, _f) in enumerate(self._shading_specs):
                self.shading_combo.setItemText(i, _t(lk))

        self._tr(_retranslate_shading)

        sh_row = QHBoxLayout()
        self._lbl_shading = QLabel()
        self._tr_label(self._lbl_shading, "panel.data.climate.shading")
        sh_row.addWidget(self._lbl_shading)
        sh_row.addWidget(self.shading_combo, stretch=1)
        card.body().addSpacing(8)
        card.body().addLayout(sh_row)

        # Климатическая зона (ШНҚ 2.08.02-23 табл.18) — рекомендуемые
        # расчётные параметры микроклимата тёплого периода. Кнопка
        # «Применить» проставляет tв(лето) во все помещения (опционально).
        from hvac.catalogs.climate_zones import list_climate_zones
        self.zone_combo = QComboBox()
        for z in list_climate_zones():
            self.zone_combo.addItem(z, z)
        self.zone_combo.currentIndexChanged.connect(self._apply_climate_zone)

        zone_row = QHBoxLayout()
        self._lbl_zone = QLabel()
        self._tr_label(self._lbl_zone, "panel.data.climate.zone")
        zone_row.addWidget(self._lbl_zone)
        zone_row.addWidget(self.zone_combo)
        self.zone_apply_btn = QPushButton()
        self._tr_button(self.zone_apply_btn, "panel.data.climate.zone_apply")
        self.zone_apply_btn.clicked.connect(self._apply_zone_to_rooms)
        zone_row.addWidget(self.zone_apply_btn)
        zone_row.addStretch(1)
        card.body().addSpacing(8)
        card.body().addLayout(zone_row)

        self._lbl_zone_info = QLabel()
        self._lbl_zone_info.setProperty("role", "hint")
        self._lbl_zone_info.setWordWrap(True)
        card.body().addWidget(self._lbl_zone_info)
        self._refresh_zone_info()
        return card

    def _build_sources_card(self) -> Card:
        card = Card("", "")
        self._tr_card(card, "panel.data.sources.title", "panel.data.sources.desc")

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # spaces.csv
        grid.addWidget(QLabel("spaces.csv"), 0, 0)
        self.spaces_path_lbl = QLabel()
        self.spaces_path_lbl.setProperty("role", "muted")
        self.spaces_path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self.spaces_path_lbl, 0, 1)
        b1 = QPushButton()
        self._tr_button(b1, "btn.pick")
        b1.setCursor(QCursor(Qt.PointingHandCursor))
        b1.clicked.connect(self._pick_spaces)
        grid.addWidget(b1, 0, 2)

        # thermal.csv
        grid.addWidget(QLabel("thermal.csv"), 1, 0)
        self.thermal_path_lbl = QLabel()
        self.thermal_path_lbl.setProperty("role", "muted")
        self.thermal_path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self.thermal_path_lbl, 1, 1)
        b2 = QPushButton()
        self._tr_button(b2, "btn.pick")
        b2.setCursor(QCursor(Qt.PointingHandCursor))
        b2.clicked.connect(self._pick_thermal)
        grid.addWidget(b2, 1, 2)

        card.body().addLayout(grid)

        card.body().addSpacing(6)
        self.keep_overrides = QCheckBox()
        self._tr_check(self.keep_overrides, "panel.data.keep_overrides")
        self.keep_overrides.setChecked(True)
        card.body().addWidget(self.keep_overrides)

        # Загрузка
        actions = QHBoxLayout()
        actions.addStretch(1)

        self.revit_btn = QPushButton()
        self._tr_button(self.revit_btn, "panel.data.btn_revit_import")
        self.revit_btn.setToolTip(_t("panel.data.revit.tooltip"))
        self.revit_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.revit_btn.clicked.connect(self._import_from_revit)
        actions.addWidget(self.revit_btn)

        # Инструменты живого моста: дифф модели + раскраска результатов
        self.revit_tools_btn = QPushButton()
        self._tr_button(self.revit_tools_btn, "panel.data.btn_revit_tools")
        self.revit_tools_btn.setCursor(QCursor(Qt.PointingHandCursor))
        menu = QMenu(self.revit_tools_btn)
        self._act_diff = menu.addAction("")
        self._act_diff.triggered.connect(self._revit_diff)
        menu.addSeparator()
        self._act_color_heat = menu.addAction("")
        self._act_color_heat.triggered.connect(
            lambda: self._revit_color("heating_w_m2"))
        self._act_color_cool = menu.addAction("")
        self._act_color_cool.triggered.connect(
            lambda: self._revit_color("cooling_w_m2"))
        self._act_color_ach = menu.addAction("")
        self._act_color_ach.triggered.connect(
            lambda: self._revit_color("ach"))
        self._act_color_clear = menu.addAction("")
        self._act_color_clear.triggered.connect(self._revit_color_clear)
        self.revit_tools_btn.setMenu(menu)

        def _tr_menu():
            self._act_diff.setText(_t("panel.data.revit.act_diff"))
            self._act_color_heat.setText(_t("panel.data.revit.act_color_heat"))
            self._act_color_cool.setText(_t("panel.data.revit.act_color_cool"))
            self._act_color_ach.setText(_t("panel.data.revit.act_color_ach"))
            self._act_color_clear.setText(
                _t("panel.data.revit.act_color_clear"))
        self._tr(_tr_menu)
        actions.addWidget(self.revit_tools_btn)

        self.load_btn = QPushButton()
        self._tr_button(self.load_btn, "panel.data.btn_load_csv")
        self.load_btn.setProperty("role", "primary")
        self.load_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.load_btn.clicked.connect(self._load_csv)
        actions.addWidget(self.load_btn)

        card.body().addLayout(actions)

        # Сводка после загрузки
        self.summary_lbl = QLabel("")
        self.summary_lbl.setProperty("role", "success")
        self.summary_lbl.setVisible(False)
        card.body().addWidget(self.summary_lbl)

        return card

    def _build_actions_card(self) -> Card:
        card = Card("", "")
        self._tr_card(card, "panel.data.actions.title", "panel.data.actions.desc")

        row = QHBoxLayout()
        row.setSpacing(10)

        b_new = QPushButton()
        self._tr_button(b_new, "panel.data.btn_new")
        b_new.setCursor(QCursor(Qt.PointingHandCursor))
        b_new.clicked.connect(self._new_empty)
        row.addWidget(b_new)

        b_open = QPushButton()
        self._tr_button(b_open, "panel.data.btn_open")
        b_open.setCursor(QCursor(Qt.PointingHandCursor))
        b_open.clicked.connect(self._open_project)
        row.addWidget(b_open)

        row.addStretch(1)

        b_save = QPushButton()
        self._tr_button(b_save, "panel.data.btn_save")
        b_save.setCursor(QCursor(Qt.PointingHandCursor))
        b_save.clicked.connect(self._save_project)
        row.addWidget(b_save)

        b_save_full = QPushButton()
        self._tr_button(b_save_full, "panel.data.btn_save_full")
        b_save_full.setProperty("role", "ghost")
        b_save_full.setCursor(QCursor(Qt.PointingHandCursor))
        b_save_full.clicked.connect(self._save_full)
        row.addWidget(b_save_full)

        card.body().addLayout(row)
        return card

    # ---------- Реакция на bridge ----------
    def _wire_bridge(self) -> None:
        self.bridge.dataLoaded.connect(self._refresh_from_project)
        self.bridge.projectLoaded.connect(self._refresh_from_project)

    def _refresh_from_project(self) -> None:
        """Подтягивает текущее состояние project в виджеты."""
        p = self.project.params
        # Имя и методика
        if self.name_edit.text() != p.project_name:
            self.name_edit.setText(p.project_name)
        idx = self.method_combo.findText(p.methodology)
        if idx >= 0 and idx != self.method_combo.currentIndex():
            self.method_combo.blockSignals(True)
            self.method_combo.setCurrentIndex(idx)
            self.method_combo.blockSignals(False)

        # Город
        self.city_combo.blockSignals(True)
        self.city_combo.set_city(p.city)
        self.city_combo.blockSignals(False)
        self._refresh_climate_labels()

        # Spinboxes — без сигналов чтобы не зациклить
        for spin, val in ((self.t_heat_spin, p.t_out_heating),
                          (self.t_cool_spin, p.t_out_cooling),
                          (self.true_north_spin,
                           getattr(p, "true_north_offset_deg", 0.0) or 0.0)):
            spin.blockSignals(True)
            spin.setValue(float(val))
            spin.blockSignals(False)

        # Затенение — выбираем пресет по фактору; нестандартное значение
        # (старый JSON) показываем ближайшим пресетом, не трогая параметр.
        factor = getattr(p, "solar_shading_factor", 1.0) or 1.0
        idx = self.shading_combo.findData(factor)
        if idx < 0:
            idx = min(range(self.shading_combo.count()),
                      key=lambda i: abs(self.shading_combo.itemData(i) - factor))
        self.shading_combo.blockSignals(True)
        self.shading_combo.setCurrentIndex(idx)
        self.shading_combo.blockSignals(False)

        # Климатическая зона
        zi = self.zone_combo.findData(getattr(p, "climate_zone", "II"))
        if zi >= 0:
            self.zone_combo.blockSignals(True)
            self.zone_combo.setCurrentIndex(zi)
            self.zone_combo.blockSignals(False)
        self._refresh_zone_info()

        # Источники
        self._spaces_path = self.project.spaces_csv_path or ""
        self._thermal_path = self.project.thermal_csv_path or ""
        self.spaces_path_lbl.setText(self._spaces_path or _t("filter.not_set"))
        self.thermal_path_lbl.setText(self._thermal_path or _t("filter.not_set"))
        self._update_load_button_state()

        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if self.project.spaces:
            self.summary_lbl.setText(
                _t("panel.data.summary_loaded").format(
                    sp=len(self.project.spaces),
                    el=len(self.project.elements),
                    co=len(self.project.constructions),
                )
            )
            self.summary_lbl.setVisible(True)
        else:
            self.summary_lbl.setVisible(False)

    def _refresh_climate_labels(self) -> None:
        p = self.project.params
        info = dict(CLIMATE_DB.get(p.city) or {})
        self.lbl_t_heat.setText(f"{p.t_out_heating:+.1f}")
        self.lbl_t_cool.setText(f"{p.t_out_cooling:+.1f}")
        self.lbl_gsop.setText(
            f"{info.get('gsop_18', p.gsop_18 or 0):.0f}"
            if (info.get('gsop_18') or p.gsop_18) else "—"
        )
        self.lbl_solar.setText(f"{p.solar_intensity_w_m2:.0f}")

    def _update_load_button_state(self) -> None:
        ok = bool(self._spaces_path and self._thermal_path
                  and os.path.isfile(self._spaces_path)
                  and os.path.isfile(self._thermal_path))
        self.load_btn.setEnabled(ok)

    # ---------- Обработчики ----------
    def _apply_name(self) -> None:
        self.project.params.project_name = self.name_edit.text().strip()
        self.bridge.dirtyChanged.emit(True)

    def _apply_methodology(self, value: str) -> None:
        self.project.params.methodology = value
        self.bridge.dirtyChanged.emit(True)

    def _apply_city(self, _idx: int) -> None:
        name = self.city_combo.selected_city()
        if not name:
            return
        ok = self.project.params.apply_city(name)
        if ok:
            self._refresh_climate_labels()
            for spin, val in (
                (self.t_heat_spin, self.project.params.t_out_heating),
                (self.t_cool_spin, self.project.params.t_out_cooling),
            ):
                spin.blockSignals(True)
                spin.setValue(float(val))
                spin.blockSignals(False)
            self.bridge.dirtyChanged.emit(True)
            self.bridge.statusMessage.emit(
                _t("panel.data.status.climate_applied").format(name=name), 3000)

    def _apply_t_heat(self, value: float) -> None:
        self.project.params.t_out_heating = float(value)
        self.lbl_t_heat.setText(f"{value:+.1f}")
        self.bridge.dirtyChanged.emit(True)

    def _apply_t_cool(self, value: float) -> None:
        self.project.params.t_out_cooling = float(value)
        self.lbl_t_cool.setText(f"{value:+.1f}")
        self.bridge.dirtyChanged.emit(True)

    def _apply_true_north(self, value: float) -> None:
        # Глобальный поворот: применяется ко всем ориентациям фасадов при
        # расчёте солнца. Сами el.orientation не трогаем — это calc-time
        # преобразование (см. engine/sp50 effective_orientation_sector).
        self.project.params.true_north_offset_deg = float(value)
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.data.status.true_north").format(deg=value), 3000)

    def _refresh_zone_info(self) -> None:
        from hvac.catalogs.climate_zones import zone_params
        p = zone_params(getattr(self.project.params, "climate_zone", "II"))
        self._lbl_zone_info.setText(
            _t("panel.data.climate.zone_info").format(
                t=p["t_cool"], rh=p["rh_max"], v=p["v_max"]))

    def _apply_climate_zone(self, _idx: int) -> None:
        zone = self.zone_combo.currentData()
        if not zone:
            return
        self.project.params.climate_zone = zone
        self._refresh_zone_info()
        self.bridge.dirtyChanged.emit(True)

    def _apply_zone_to_rooms(self) -> None:
        from hvac.catalogs.climate_zones import zone_indoor_cooling_temp
        if not self.project.spaces:
            return
        t = zone_indoor_cooling_temp(
            getattr(self.project.params, "climate_zone", "II"))
        for sp in self.project.spaces:
            sp.t_in_cool = t
            sp.user_modified = True
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.data.status.zone_applied").format(
                n=len(self.project.spaces), t=t), 4000)

    def _apply_shading(self, _idx: int) -> None:
        factor = self.shading_combo.currentData()
        if factor is None:
            return
        self.project.params.solar_shading_factor = float(factor)
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.data.status.shading").format(
                pct=round((1.0 - float(factor)) * 100)), 3000)

    def _pick_spaces(self) -> None:
        start = str(Path(self._spaces_path).parent) if self._spaces_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, _t("panel.data.dlg.pick_spaces"), start,
            _t("panel.data.dlg.filter.csv"),
        )
        if path:
            self._spaces_path = path
            self.spaces_path_lbl.setText(path)
            # Автоматически предложим thermal.csv рядом
            if not self._thermal_path:
                guess = str(Path(path).parent / "thermal_all.csv")
                if os.path.isfile(guess):
                    self._thermal_path = guess
                    self.thermal_path_lbl.setText(guess)
            self._update_load_button_state()

    def _pick_thermal(self) -> None:
        start = (str(Path(self._thermal_path).parent) if self._thermal_path
                 else str(Path(self._spaces_path).parent) if self._spaces_path
                 else "")
        path, _ = QFileDialog.getOpenFileName(
            self, _t("panel.data.dlg.pick_thermal"), start,
            _t("panel.data.dlg.filter.csv"),
        )
        if path:
            self._thermal_path = path
            self.thermal_path_lbl.setText(path)
            self._update_load_button_state()

    def _import_from_revit(self) -> None:
        """Живой импорт геометрии из открытой модели Revit (без Dynamo)."""
        from hvac.revit_link import ping
        if not ping():
            QMessageBox.warning(
                self, _t("panel.data.revit.not_connected.title"),
                _t("panel.data.revit.not_connected.body"))
            return
        start = (str(Path(self._spaces_path).parent)
                 if self._spaces_path else str(Path.home()))
        folder = QFileDialog.getExistingDirectory(
            self, _t("panel.data.revit.pick_dir"), start)
        if not folder:
            return

        self.revit_btn.setEnabled(False)
        self.bridge.busyChanged.emit(
            True, _t("panel.data.status.revit_import"))
        self._revit_thread = QThread(self)
        self._revit_worker = _RevitImportWorker(folder)
        self._revit_worker.moveToThread(self._revit_thread)
        self._revit_thread.started.connect(self._revit_worker.run)
        self._revit_worker.finished.connect(self._on_revit_import_done)
        self._revit_worker.failed.connect(self._on_revit_import_failed)
        self._revit_worker.finished.connect(self._revit_thread.quit)
        self._revit_worker.failed.connect(self._revit_thread.quit)
        self._revit_thread.start()

    def _on_revit_import_done(self, summary: dict) -> None:
        self.revit_btn.setEnabled(True)
        self.bridge.busyChanged.emit(False, "")
        spaces_csv = summary.get("spaces_csv", "")
        thermal_csv = summary.get("thermal_csv", "")
        if spaces_csv and thermal_csv:
            self._spaces_path = spaces_csv
            self._thermal_path = thermal_csv
            self.spaces_path_lbl.setText(spaces_csv)
            self.thermal_path_lbl.setText(thermal_csv)
            self._update_load_button_state()
        self.bridge.statusMessage.emit(
            _t("panel.data.revit.done").format(
                spaces=summary.get("spaces_rows", 0),
                thermal=summary.get("thermal_rows", 0),
                source=summary.get("source", "")), 8000)
        self._load_csv()

    def _on_revit_import_failed(self, message: str) -> None:
        self.revit_btn.setEnabled(True)
        self.bridge.busyChanged.emit(False, "")
        QMessageBox.critical(
            self, _t("panel.data.err.revit"), message)

    # ---------- Инструменты живого моста: дифф и раскраска ----------

    def _revit_ready(self) -> bool:
        from hvac.revit_link import ping
        if not ping():
            QMessageBox.warning(
                self, _t("panel.data.revit.not_connected.title"),
                _t("panel.data.revit.not_connected.body"))
            return False
        return True

    def _run_revit_task(self, fn, on_done, busy_key: str) -> None:
        """Запускает операцию моста в фоне с блокировкой кнопки."""
        self.revit_tools_btn.setEnabled(False)
        self.bridge.busyChanged.emit(True, _t(busy_key))

        def _finish():
            self.revit_tools_btn.setEnabled(True)
            self.bridge.busyChanged.emit(False, "")

        def _ok(result):
            _finish()
            on_done(result)

        def _fail(message: str):
            _finish()
            QMessageBox.critical(self, _t("panel.data.err.revit"), message)

        self._revit_task_thread = QThread(self)
        self._revit_task_worker = _RevitTaskWorker(fn)
        self._revit_task_worker.moveToThread(self._revit_task_thread)
        self._revit_task_thread.started.connect(self._revit_task_worker.run)
        self._revit_task_worker.finished.connect(_ok)
        self._revit_task_worker.failed.connect(_fail)
        self._revit_task_worker.finished.connect(self._revit_task_thread.quit)
        self._revit_task_worker.failed.connect(self._revit_task_thread.quit)
        self._revit_task_thread.start()

    def _revit_diff(self) -> None:
        """Сравнение открытой модели Revit с загруженным проектом."""
        if not self.project.spaces:
            QMessageBox.information(
                self, _t("panel.data.revit.act_diff"),
                _t("panel.data.revit.diff.no_project"))
            return
        if not self._revit_ready():
            return
        from hvac.revit_link import diff_with_project
        self._run_revit_task(
            lambda: diff_with_project(self.project),
            self._show_revit_diff, "panel.data.status.revit_diff")

    def _show_revit_diff(self, diff) -> None:
        if diff.in_sync:
            QMessageBox.information(
                self, _t("panel.data.revit.act_diff"),
                _t("panel.data.revit.diff.in_sync").format(
                    n=diff.unchanged))
            return
        summary = _t("panel.data.revit.diff.summary").format(
            added=len(diff.added), removed=len(diff.removed),
            changed=len(diff.changed), unchanged=diff.unchanged)
        details: list[str] = []
        if diff.added:
            details.append(_t("panel.data.revit.diff.h_added"))
            details += [f"  + {r['number']} {r['name']} "
                        f"({r['area_m2']:.1f} м², id {r['id']})"  # i18n-allow
                        for r in diff.added[:150]]
        if diff.removed:
            details.append(_t("panel.data.revit.diff.h_removed"))
            details += [f"  − {r['number']} {r['name']} (id {r['id']})"
                        for r in diff.removed[:150]]
        if diff.changed:
            details.append(_t("panel.data.revit.diff.h_changed"))
            for r in diff.changed[:150]:
                details.append(f"  ~ {r['number']} {r['name']}: "
                               + "; ".join(r["what"]))
        m = QMessageBox(self)
        m.setIcon(QMessageBox.Information)
        m.setWindowTitle(_t("panel.data.revit.act_diff"))
        m.setText(summary)
        m.setDetailedText("\n".join(details))
        m.exec()

    def _revit_color(self, metric: str) -> None:
        """Раскраска помещений активного вида Revit по метрике."""
        if not self.project.spaces:
            QMessageBox.information(
                self, _t("panel.data.btn_revit_tools"),
                _t("panel.data.revit.diff.no_project"))
            return
        if not self._revit_ready():
            return
        from hvac.revit_link import color_spaces_in_revit

        def _done(res: dict):
            self.bridge.statusMessage.emit(
                _t("panel.data.revit.color.done").format(
                    n=res.get("colored", 0), view=res.get("view", "?"),
                    vmin=res.get("vmin", 0), vmax=res.get("vmax", 0)), 8000)

        self._run_revit_task(
            lambda: color_spaces_in_revit(self.project, metric),
            _done, "panel.data.status.revit_color")

    def _revit_color_clear(self) -> None:
        if not self._revit_ready():
            return
        from hvac.revit_link import clear_space_colors_in_revit

        def _done(res: dict):
            self.bridge.statusMessage.emit(
                _t("panel.data.revit.color.cleared").format(
                    n=res.get("cleared", 0), view=res.get("view", "?")), 6000)

        self._run_revit_task(
            clear_space_colors_in_revit, _done,
            "panel.data.status.revit_color")

    def _load_csv(self) -> None:
        if not (self._spaces_path and self._thermal_path):
            return
        try:
            self.bridge.busyChanged.emit(True, _t("panel.data.status.loading_csv"))
            self.project.load(
                self._spaces_path, self._thermal_path,
                keep_user_settings=self.keep_overrides.isChecked(),
            )
        except Exception as e:
            self._show_error(_t("panel.data.err.csv_load"), e)
        finally:
            self.bridge.busyChanged.emit(False, "")
        self.csvLoaded.emit()

    def _new_empty(self) -> None:
        if self.project.spaces:
            ok = QMessageBox.question(
                self, _t("dialog.new_project.title"),
                _t("panel.data.dialog.new_clear.body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ok != QMessageBox.Yes:
                return
        self.project.new_empty_project(
            project_name=(self.name_edit.text().strip()
                           or _t("panel.data.suffix_new_project")),
            city=self.project.params.city or "Ташкент",
        )

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("panel.data.dlg.open_project"), "",
            _t("panel.data.dlg.filter.hvac"),
        )
        if not path:
            return
        try:
            load_project(self.project, path)
            self.project.emit("project_loaded")
            user_settings.push_recent(path)
            self.bridge.statusMessage.emit(
                _t("panel.data.status.opened").format(path=path), 4000)
        except Exception as e:
            self._show_error(_t("panel.data.err.open"), e)

    def _save_project(self) -> None:
        # Сохраняем даже пустой проект: пользователь мог задать имя, город,
        # параметры, добавить конструкции/системы — это уже валидное состояние.
        path, _ = QFileDialog.getSaveFileName(
            self, _t("panel.data.dlg.save_project"),
            f"{self.project.params.project_name}.hvac.json",
            _t("panel.data.dlg.filter.hvac_save"),
        )
        if not path:
            return
        try:
            save_project(self.project, path)
            user_settings.push_recent(path)
            self.bridge.statusMessage.emit(
                _t("panel.data.status.saved").format(path=path), 4000)
            self.bridge.dirtyChanged.emit(False)
        except Exception as e:
            self._show_error(_t("panel.data.err.save"), e)

    def _save_full(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, _t("panel.data.dlg.save_full"),
            f"{self.project.params.project_name}"
            f"{_t('panel.data.suffix_full')}.hvac.json",
            _t("panel.data.dlg.filter.hvac_save"),
        )
        if not path:
            return
        try:
            save_project(self.project, path, force_self_contained=True)
            self.bridge.statusMessage.emit(
                _t("panel.data.status.saved_full").format(path=path), 5000)
            self.bridge.dirtyChanged.emit(False)
        except Exception as e:
            self._show_error(_t("panel.data.err.save_full"), e)

    # ---------- Утилиты ----------
    def _show_error(self, title: str, exc: Exception) -> None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(str(exc))
        msg.setDetailedText(traceback.format_exc())
        msg.exec()
