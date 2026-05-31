# -*- coding: utf-8 -*-
"""Диалог выбора шаблона типового здания."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.templates import (
    TEMPLATE_FACTORIES, BuildingTemplate, list_templates, make_template,
)


class TemplateDialog(QDialog):
    """Выбор и параметры шаблона типового здания.

    После accept() результат — атрибут `template` (BuildingTemplate)
    и `project_name`, `city`.
    """

    def __init__(self, parent: Optional[QWidget] = None,
                 default_city: Optional[str] = None):
        super().__init__(parent)
        if default_city is None:
            default_city = _t("dlg.tpl.default_city")
        self.setWindowTitle(_t("dlg.tpl.title"))
        self.setMinimumSize(720, 480)
        self.template: Optional[BuildingTemplate] = None
        self.project_name = ""
        self.city = default_city

        outer = QVBoxLayout(self)

        # Список шаблонов слева + параметры справа
        body = QHBoxLayout()
        outer.addLayout(body, stretch=1)

        # ===== Список =====
        list_box = QGroupBox(_t("dlg.tpl.gb_list"))
        list_layout = QVBoxLayout(list_box)
        self.list_widget = QListWidget()
        for tpl in list_templates():
            item = QListWidgetItem(tpl["title"])
            item.setData(Qt.UserRole, tpl["code"])
            item.setToolTip(tpl["description"])
            self.list_widget.addItem(item)
        self.list_widget.currentItemChanged.connect(self._on_select)
        list_layout.addWidget(self.list_widget)
        body.addWidget(list_box, stretch=1)

        # ===== Описание + параметры =====
        right = QVBoxLayout()
        body.addLayout(right, stretch=2)

        self.desc_label = QLabel(_t("dlg.tpl.choose"))
        self.desc_label.setProperty("role", "muted")
        self.desc_label.setWordWrap(True)
        right.addWidget(self.desc_label)

        # Общие
        common = QGroupBox(_t("dlg.tpl.gb_common"))
        common_form = QFormLayout(common)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(_t("dlg.tpl.project_name_ph"))
        common_form.addRow(_t("dlg.tpl.project_name"), self.name_edit)

        self.city_edit = QLineEdit(default_city)
        common_form.addRow(_t("dlg.tpl.city"), self.city_edit)

        right.addWidget(common)

        # Параметры конкретного шаблона
        self.params_stack = QStackedWidget()
        right.addWidget(self.params_stack)

        # Соответствие code → widget (build на лету)
        self._param_widgets: dict[str, tuple[int, QWidget]] = {}
        for code in TEMPLATE_FACTORIES.keys():
            w = self._build_param_widget(code)
            self.params_stack.addWidget(w)
            self._param_widgets[code] = (
                self.params_stack.indexOf(w), w)

        right.addStretch(1)

        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("dlg.tpl.btn_create"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Выбрать первый
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    # ---------- Параметры на шаблон ----------
    def _build_param_widget(self, code: str) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        if code == "office_open":
            spin = QSpinBox()
            spin.setRange(5, 500)
            spin.setValue(50)
            spin.setSuffix(_t("dlg.tpl.suffix.workplaces"))
            form.addRow(_t("dlg.tpl.row.workplaces"), spin)
            w._params = {"n_workplaces": spin}
        elif code == "office_cubicles":
            spin = QSpinBox()
            spin.setRange(2, 60)
            spin.setValue(12)
            spin.setSuffix(_t("dlg.tpl.suffix.cabinets"))
            form.addRow(_t("dlg.tpl.row.cabinets"), spin)
            w._params = {"n_rooms": spin}
        elif code == "school":
            spin = QSpinBox()
            spin.setRange(4, 60)
            spin.setValue(24)
            spin.setSuffix(_t("dlg.tpl.suffix.classes"))
            form.addRow(_t("dlg.tpl.row.classes"), spin)
            w._params = {"n_classes": spin}
        elif code == "hotel":
            n_spin = QSpinBox()
            n_spin.setRange(10, 500)
            n_spin.setValue(60)
            n_spin.setSuffix(_t("dlg.tpl.suffix.rooms"))
            form.addRow(_t("dlg.tpl.row.rooms"), n_spin)
            stars_spin = QSpinBox()
            stars_spin.setRange(2, 5)
            stars_spin.setValue(4)
            stars_spin.setSuffix(_t("dlg.tpl.suffix.stars"))
            form.addRow(_t("dlg.tpl.row.stars"), stars_spin)
            w._params = {"n_rooms": n_spin, "stars": stars_spin}
        elif code == "mall":
            spin = QSpinBox()
            spin.setRange(500, 50_000)
            spin.setValue(5000)
            spin.setSingleStep(500)
            spin.setSuffix(_t("dlg.tpl.suffix.m2"))
            form.addRow(_t("dlg.tpl.row.area"), spin)
            w._params = {"area_m2": spin}
        elif code == "residential":
            apt_spin = QSpinBox()
            apt_spin.setRange(4, 500)
            apt_spin.setValue(24)
            apt_spin.setSuffix(_t("dlg.tpl.suffix.apts"))
            form.addRow(_t("dlg.tpl.row.apts"), apt_spin)
            fl_spin = QSpinBox()
            fl_spin.setRange(2, 30)
            fl_spin.setValue(6)
            fl_spin.setSuffix(_t("dlg.tpl.suffix.floors"))
            form.addRow(_t("dlg.tpl.row.floors"), fl_spin)
            w._params = {"n_apartments": apt_spin, "n_floors": fl_spin}
        else:
            w._params = {}
        return w

    def _selected_code(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_select(self, *_):
        code = self._selected_code()
        if code is None:
            return
        from hvac.templates import make_template as _make
        tpl = _make(code)
        self.desc_label.setText(tpl.description)
        idx = self._param_widgets.get(code, (0, None))[0]
        self.params_stack.setCurrentIndex(idx)
        if not self.name_edit.text().strip():
            # Подсказка для имени
            self.name_edit.setPlaceholderText(
                _t("dlg.tpl.project_name_hint").format(title=tpl.title))

    def _on_ok(self):
        code = self._selected_code()
        if code is None:
            return
        # Собираем параметры
        widget = self._param_widgets.get(code, (0, None))[1]
        kwargs = {}
        if widget is not None:
            for k, ctrl in widget._params.items():
                kwargs[k] = ctrl.value()
        self.template = make_template(code, **kwargs)
        self.project_name = (self.name_edit.text().strip()
                             or self.template.title)
        self.city = self.city_edit.text().strip() or _t("dlg.tpl.default_city")
        self.accept()
