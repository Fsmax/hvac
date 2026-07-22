# -*- coding: utf-8 -*-
"""Диалог создания / редактирования системы дымоудаления или подпора.

Параметры группируются по разделам в зависимости от calc_method:
    norm_per_m2        — норма расхода и площадь зоны
    kmk_zone_perimeter — периметр очага, высота слоя, Ks
    kmk_corridor       — B (ширина двери), H (высота), тип здания, Kd
    nfpa_plume_axi     — HRR, высота плюма, convective fraction
    manual             — L_smoke напрямую
    air_supply         — расход подпора, давление
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QMessageBox, QStackedWidget, QVBoxLayout,
    QWidget,
)

from hvac.catalogs.smoke_norms import get_smoke_norm
from hvac.i18n import t as _t
from hvac.smoke import SmokeSystem


# Имена кодов методов / типов / назначений приходят из i18n. Здесь
# фиксируем только сами коды (внутренние ключи моделей) и связку
# код → i18n-ключ. Тексты получаются через _t() — следовательно
# меняются по языку при пересоздании комбобокса.

METHOD_CODES = (
    "norm_per_m2", "kmk_zone_perimeter", "kmk_corridor",
    "nfpa_plume_axi", "manual",
    # Для СПВ
    "stairs_pressure", "elevator_pressure",
)

SYSTEM_TYPE_CODES = ("smoke_removal", "air_supply", "compensation")

PURPOSE_CODES = (
    "parking", "warehouse", "technical", "corridor", "atrium",
    "trading_hall", "stairs", "elevator", "vestibule", "refuge",
)


def _method_label(code: str) -> str:
    return _t(f"dlg.smoke.method.{code}")


def _systype_label(code: str) -> str:
    return _t(f"dlg.smoke.systype.{code}")


def _purpose_label(code: str) -> str:
    return _t(f"dlg.smoke.purpose.{code}")


def _fill_combo(combo: QComboBox, codes, label_fn, current: str) -> None:
    """Заполняет QComboBox: каждый item получает userData=code и
    локализованный label через label_fn(code).

    Если current не в стандартном наборе кодов — добавляется первым
    пунктом с тем же значением как текст (legacy-проекты).
    """
    combo.clear()
    code_list = list(codes)
    if current and current not in code_list:
        combo.addItem(current, userData=current)
    for code in code_list:
        combo.addItem(label_fn(code), userData=code)
    for i in range(combo.count()):
        if combo.itemData(i) == current:
            combo.setCurrentIndex(i)
            return


class SmokeSystemDialog(QDialog):
    """Создание или редактирование одной SmokeSystem.

    Использование:
        dlg = SmokeSystemDialog(parent, system=sm, norm_code="KMK_UZ")
        if dlg.exec() == QDialog.Accepted:
            sm = dlg.system   # обновлённый объект
    """

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 system: Optional[SmokeSystem] = None,
                 norm_code: str = "SP7_RU",
                 is_new: bool = False):
        super().__init__(parent)
        self.is_new = is_new
        self.norm_code = norm_code
        self.norm = get_smoke_norm(norm_code)
        # Работаем с копией, чтобы при Cancel ничего не менялось
        self.system = SmokeSystem(name="") if system is None else SmokeSystem(
            **{f: getattr(system, f) for f in SmokeSystem.__dataclass_fields__}
        )

        self.setWindowTitle(
            _t("dlg.smoke.title_new") if is_new
            else _t("dlg.smoke.title_edit").format(name=self.system.name)
        )
        self.setMinimumWidth(540)

        outer = QVBoxLayout(self)

        # ===== Шапка: имя + тип + назначение =====
        head = QGroupBox(_t("dlg.smoke.gb_id"))
        head_form = QFormLayout(head)

        self.name_edit = QLineEdit(self.system.name)
        self.name_edit.setPlaceholderText("СДУ-B1-PRK")
        self.name_edit.setEnabled(is_new)   # имя — ключ, не меняем
        head_form.addRow(_t("dlg.smoke.name"), self.name_edit)

        self.type_combo = QComboBox()
        _fill_combo(self.type_combo, SYSTEM_TYPE_CODES, _systype_label,
                    self.system.system_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        head_form.addRow(_t("dlg.smoke.type"), self.type_combo)

        self.purpose_combo = QComboBox()
        _fill_combo(self.purpose_combo, PURPOSE_CODES, _purpose_label,
                    self.system.purpose)
        head_form.addRow(_t("dlg.smoke.purpose"), self.purpose_combo)

        outer.addWidget(head)

        # ===== Метод расчёта =====
        method_box = QGroupBox(_t("dlg.smoke.gb_method"))
        method_layout = QVBoxLayout(method_box)

        self.method_combo = QComboBox()
        self._refill_methods()
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self.method_combo)

        self.method_hint = QLabel()
        self.method_hint.setProperty("role", "muted")
        self.method_hint.setWordWrap(True)
        method_layout.addWidget(self.method_hint)

        # Стек панелей параметров
        self.stack = QStackedWidget()
        self.page_norm = self._build_page_norm()
        self.page_kmk_zone = self._build_page_kmk_zone()
        self.page_kmk_corridor = self._build_page_kmk_corridor()
        self.page_nfpa = self._build_page_nfpa()
        self.page_manual = self._build_page_manual()
        self.page_air_supply = self._build_page_air_supply()

        # Индексация: ключ → виджет
        self._pages = {
            "norm_per_m2":        self.page_norm,
            "kmk_zone_perimeter": self.page_kmk_zone,
            "kmk_corridor":       self.page_kmk_corridor,
            "nfpa_plume_axi":     self.page_nfpa,
            "manual":             self.page_manual,
            "air_supply":         self.page_air_supply,
        }
        for w in self._pages.values():
            self.stack.addWidget(w)
        method_layout.addWidget(self.stack)
        outer.addWidget(method_box)

        # ===== Общие параметры =====
        common = QGroupBox(_t("dlg.smoke.gb_common"))
        common_form = QFormLayout(common)

        self.t_smoke_spin = QDoubleSpinBox()
        self.t_smoke_spin.setRange(20.0, 600.0)
        self.t_smoke_spin.setSuffix(" °C")
        self.t_smoke_spin.setDecimals(0)
        self.t_smoke_spin.setValue(self.system.t_smoke_C)
        common_form.addRow(_t("dlg.smoke.t_smoke"), self.t_smoke_spin)

        self.makeup_spin = QDoubleSpinBox()
        self.makeup_spin.setRange(0.0, 1.0)
        self.makeup_spin.setDecimals(2)
        self.makeup_spin.setSingleStep(0.05)
        self.makeup_spin.setValue(self.system.makeup_ratio)
        common_form.addRow(_t("dlg.smoke.makeup"), self.makeup_spin)

        self.fire_rating_edit = QLineEdit(self.system.fire_rating)
        self.fire_rating_edit.setPlaceholderText("F400-120")
        common_form.addRow(_t("dlg.smoke.fire_rating"), self.fire_rating_edit)

        self.note_edit = QLineEdit(self.system.note)
        common_form.addRow(_t("dlg.smoke.note"), self.note_edit)

        outer.addWidget(common)

        # ===== Кнопки =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Применить текущий метод
        self._on_type_changed()
        self._on_method_changed()

    # ---------- Страницы параметров ----------
    def _build_page_norm(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.norm_per_m2_spin = QDoubleSpinBox()
        self.norm_per_m2_spin.setRange(0.0, 500.0)
        self.norm_per_m2_spin.setSuffix(" м³/(ч·м²)")
        self.norm_per_m2_spin.setDecimals(1)
        self.norm_per_m2_spin.setValue(self.system.norm_per_m2)
        f.addRow(_t("dlg.smoke.norm.norm"), self.norm_per_m2_spin)

        self.max_zone_spin = QDoubleSpinBox()
        self.max_zone_spin.setRange(100.0, 10000.0)
        self.max_zone_spin.setSuffix(" м²")
        self.max_zone_spin.setDecimals(0)
        self.max_zone_spin.setValue(self.system.max_zone_area_m2)
        f.addRow(_t("dlg.smoke.norm.max_zone"), self.max_zone_spin)
        return w

    def _build_page_kmk_zone(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.fire_perim_spin = QDoubleSpinBox()
        self.fire_perim_spin.setRange(1.0, 30.0)
        self.fire_perim_spin.setSuffix(" м")
        self.fire_perim_spin.setDecimals(1)
        self.fire_perim_spin.setValue(self.system.fire_perimeter_m)
        f.addRow(_t("dlg.smoke.kmk_zone.perim"), self.fire_perim_spin)

        self.layer_height_spin = QDoubleSpinBox()
        self.layer_height_spin.setRange(2.5, 20.0)
        self.layer_height_spin.setSuffix(" м")
        self.layer_height_spin.setDecimals(2)
        self.layer_height_spin.setValue(self.system.layer_height_m)
        f.addRow(_t("dlg.smoke.kmk_zone.layer"), self.layer_height_spin)

        self.ks_spin = QDoubleSpinBox()
        self.ks_spin.setRange(0.5, 2.0)
        self.ks_spin.setSingleStep(0.1)
        self.ks_spin.setDecimals(2)
        self.ks_spin.setValue(self.system.ks_sprinkler)
        f.addRow(_t("dlg.smoke.kmk_zone.ks"), self.ks_spin)

        f.addRow(QLabel(_t("dlg.smoke.kmk_zone.formula")))
        return w

    def _build_page_kmk_corridor(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.corr_b_spin = QDoubleSpinBox()
        self.corr_b_spin.setRange(0.6, 2.4)
        self.corr_b_spin.setSingleStep(0.1)
        self.corr_b_spin.setDecimals(2)
        self.corr_b_spin.setValue(self.system.corridor_door_width_m)
        f.addRow(_t("dlg.smoke.kmk_corr.width"), self.corr_b_spin)

        self.corr_h_spin = QDoubleSpinBox()
        self.corr_h_spin.setRange(1.5, 2.5)
        self.corr_h_spin.setSingleStep(0.1)
        self.corr_h_spin.setDecimals(2)
        self.corr_h_spin.setValue(self.system.corridor_door_height_m)
        f.addRow(_t("dlg.smoke.kmk_corr.height"), self.corr_h_spin)

        self.corr_kind_combo = QComboBox()
        self.corr_kind_combo.addItem(_t("dlg.smoke.kmk_corr.public"), True)
        self.corr_kind_combo.addItem(_t("dlg.smoke.kmk_corr.residential"), False)
        self.corr_kind_combo.setCurrentIndex(0 if self.system.corridor_public else 1)
        f.addRow(_t("dlg.smoke.kmk_corr.kind"), self.corr_kind_combo)

        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.5, 2.0)
        self.kd_spin.setSingleStep(0.1)
        self.kd_spin.setDecimals(2)
        self.kd_spin.setValue(self.system.kd_door)
        f.addRow(_t("dlg.smoke.kmk_corr.kd"), self.kd_spin)

        f.addRow(QLabel(_t("dlg.smoke.kmk_corr.formula")))
        return w

    def _build_page_nfpa(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.hrr_spin = QDoubleSpinBox()
        self.hrr_spin.setRange(100.0, 100_000.0)
        self.hrr_spin.setSuffix(" кВт")
        self.hrr_spin.setDecimals(0)
        self.hrr_spin.setValue(self.system.hrr_kw)
        f.addRow(_t("dlg.smoke.nfpa.hrr"), self.hrr_spin)

        self.conv_frac_spin = QDoubleSpinBox()
        self.conv_frac_spin.setRange(0.3, 1.0)
        self.conv_frac_spin.setSingleStep(0.05)
        self.conv_frac_spin.setDecimals(2)
        self.conv_frac_spin.setValue(self.system.convective_fraction)
        f.addRow(_t("dlg.smoke.nfpa.frac"), self.conv_frac_spin)

        self.plume_h_spin = QDoubleSpinBox()
        self.plume_h_spin.setRange(1.0, 50.0)
        self.plume_h_spin.setSuffix(" м")
        self.plume_h_spin.setDecimals(2)
        self.plume_h_spin.setValue(self.system.plume_height_m)
        f.addRow(_t("dlg.smoke.nfpa.plume_h"), self.plume_h_spin)

        f.addRow(QLabel(_t("dlg.smoke.nfpa.formula")))
        return w

    def _build_page_manual(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.l_smoke_spin = QDoubleSpinBox()
        self.l_smoke_spin.setRange(0.0, 1_000_000.0)
        self.l_smoke_spin.setSuffix(" м³/ч")
        self.l_smoke_spin.setDecimals(0)
        self.l_smoke_spin.setValue(self.system.L_smoke_m3h)
        f.addRow(_t("dlg.smoke.manual.l"), self.l_smoke_spin)
        return w

    def _build_page_air_supply(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.supply_rate_spin = QDoubleSpinBox()
        self.supply_rate_spin.setRange(0.0, 100_000.0)
        self.supply_rate_spin.setSuffix(" м³/ч")
        self.supply_rate_spin.setDecimals(0)
        self.supply_rate_spin.setValue(self.system.L_smoke_m3h)
        f.addRow(_t("dlg.smoke.supply.rate"), self.supply_rate_spin)

        self.pressure_spin = QDoubleSpinBox()
        self.pressure_spin.setRange(0.0, 100.0)
        self.pressure_spin.setSuffix(" Па")
        self.pressure_spin.setDecimals(1)
        self.pressure_spin.setValue(self.system.pressure_pa)
        f.addRow(_t("dlg.smoke.supply.pressure"), self.pressure_spin)
        return w

    # ---------- Реакции ----------
    def _refill_methods(self) -> None:
        """Заполняет список методов из активного норматива."""
        is_air = self._current_type() == "air_supply"
        self.method_combo.blockSignals(True)
        self.method_combo.clear()
        if is_air:
            # Для СПВ только «manual» и фиксированные пресеты подпора
            codes = ["stairs_pressure", "elevator_pressure", "manual"]
        else:
            codes = self.norm.available_calc_methods
        for code in codes:
            self.method_combo.addItem(_method_label(code), userData=code)
        # Восстановить текущий
        for i in range(self.method_combo.count()):
            if self.method_combo.itemData(i) == self.system.calc_method:
                self.method_combo.setCurrentIndex(i)
                break
        self.method_combo.blockSignals(False)

    def _current_type(self) -> str:
        return self.type_combo.currentData() or "smoke_removal"

    def _current_method(self) -> str:
        return self.method_combo.currentData() or "norm_per_m2"

    def _on_type_changed(self) -> None:
        self._refill_methods()
        self._on_method_changed()

    def _on_method_changed(self) -> None:
        m = self._current_method()
        is_air = self._current_type() == "air_supply"
        # Подсказка
        if m == "norm_per_m2":
            hint = _t("dlg.smoke.hint.norm")
        elif m == "kmk_zone_perimeter":
            hint = _t("dlg.smoke.hint.kmk_zone")
        elif m == "kmk_corridor":
            hint = _t("dlg.smoke.hint.kmk_corr")
        elif m == "nfpa_plume_axi":
            hint = _t("dlg.smoke.hint.nfpa")
        elif m == "manual":
            hint = _t("dlg.smoke.hint.manual")
        else:
            hint = _t("dlg.smoke.hint.air")
        self.method_hint.setText(hint)

        # Показать нужную страницу
        if is_air:
            self.stack.setCurrentWidget(self.page_air_supply)
        elif m in self._pages:
            self.stack.setCurrentWidget(self._pages[m])

    # ---------- Получение результата ----------
    def _on_ok(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            # Иначе OK молча ничего не делает и пользователю кажется, что
            # «добавить не работает». Подсказываем и возвращаем фокус в поле.
            QMessageBox.warning(self, _t("dlg.smoke.title_new"),
                                _t("dlg.smoke.err.no_name"))
            self.name_edit.setFocus()
            return
        sm = self.system
        sm.name = name
        sm.system_type = self._current_type()
        sm.purpose = self.purpose_combo.currentData() or "parking"
        sm.calc_method = self._current_method()
        sm.t_smoke_C = self.t_smoke_spin.value()
        sm.makeup_ratio = self.makeup_spin.value()
        sm.fire_rating = self.fire_rating_edit.text().strip()
        sm.note = self.note_edit.text().strip()

        # Параметры активной страницы
        if sm.system_type == "air_supply":
            sm.L_smoke_m3h = self.supply_rate_spin.value()
            sm.pressure_pa = self.pressure_spin.value()
        else:
            m = sm.calc_method
            if m == "norm_per_m2":
                sm.norm_per_m2 = self.norm_per_m2_spin.value()
                sm.max_zone_area_m2 = self.max_zone_spin.value()
            elif m == "kmk_zone_perimeter":
                sm.fire_perimeter_m = self.fire_perim_spin.value()
                sm.layer_height_m = self.layer_height_spin.value()
                sm.ks_sprinkler = self.ks_spin.value()
            elif m == "kmk_corridor":
                sm.corridor_door_width_m = self.corr_b_spin.value()
                sm.corridor_door_height_m = self.corr_h_spin.value()
                sm.corridor_public = bool(self.corr_kind_combo.currentData())
                sm.kd_door = self.kd_spin.value()
            elif m == "nfpa_plume_axi":
                sm.hrr_kw = self.hrr_spin.value()
                sm.convective_fraction = self.conv_frac_spin.value()
                sm.plume_height_m = self.plume_h_spin.value()
            elif m == "manual":
                sm.L_smoke_m3h = self.l_smoke_spin.value()

        self.accept()
