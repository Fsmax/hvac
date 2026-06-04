# -*- coding: utf-8 -*-
"""Редактор норм вентиляции по типам помещений (Qt).

Перенос окна «Нормы вентиляции — редактор» из старого Tkinter-интерфейса.
Слева — список типов помещений (встроенные СП + пользовательские), справа —
форма с параметрами расчётного норматива выбранного типа.

Изменения сохраняются глобально (в %APPDATA%/HVAC/user_norms.json на Windows
или ~/.config/HVAC/user_norms.json на Linux) и применяются ко всем проектам.
После сохранения можно сразу пересчитать вентиляцию текущего проекта.

Семантика полей-чисел: пустое поле = «не переопределять, брать значение СП».
Логические поля (чекбоксы): включённый = True сохраняется, выключенный — нет
(отсутствие флага и есть СП-дефолт). См. hvac.catalogs.user_norms.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hvac.catalogs import user_norms as un
from hvac.i18n import t as _t
from hvac.ui_qt.theme import tokens


# Описание полей формы. Тип:
#   "__sep__"  — разделитель-заголовок секции (key = i18n-ключ заголовка)
#   "__bool__" — чекбокс
#   "text"     — строка (примечание/норматив)
#   "float"    — число (пустое = не переопределять)
# Для не-разделителей: (kind, norm_key, i18n_label_key).
_FIELD_DEFS: List[Tuple[str, str, str]] = [
    ("__bool__", "is_NC",          "dlg.vent_norms.f.is_nc"),
    ("__bool__", "exhaust_only",   "dlg.vent_norms.f.exhaust_only"),
    ("__bool__", "has_hood",       "dlg.vent_norms.f.has_hood"),
    ("__bool__", "has_co_control", "dlg.vent_norms.f.has_co_control"),
    ("__sep__",  "dlg.vent_norms.sep.supply", ""),
    ("float",    "m3_per_person",       "dlg.vent_norms.f.m3_per_person"),
    ("float",    "m3_per_spectator",    "dlg.vent_norms.f.m3_per_spectator"),
    ("float",    "m3_per_m2",           "dlg.vent_norms.f.m3_per_m2"),
    ("float",    "min_ach",             "dlg.vent_norms.f.min_ach"),
    ("float",    "m3_per_kw_equipment", "dlg.vent_norms.f.m3_per_kw"),
    ("float",    "m3_per_car",          "dlg.vent_norms.f.m3_per_car"),
    ("__sep__",  "dlg.vent_norms.sep.exhaust", ""),
    ("float",    "balance",         "dlg.vent_norms.f.balance"),
    ("float",    "exhaust_per_m2",  "dlg.vent_norms.f.exhaust_per_m2"),
    ("float",    "exhaust_min",     "dlg.vent_norms.f.exhaust_min"),
    ("__sep__",  "dlg.vent_norms.sep.hood", ""),
    ("float",    "hood_factor",     "dlg.vent_norms.f.hood_factor"),
    ("__sep__",  "dlg.vent_norms.sep.desc", ""),
    ("text",     "note",            "dlg.vent_norms.f.note"),
]

_COLOR_CUSTOM = "#9933CC"   # фиолетовый — пользовательские типы


class VentilationNormsDialog(QDialog):
    """Окно редактирования норм вентиляции по типам помещений."""

    def __init__(self, project, bridge=None,
                 initial_type: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._current_type: Optional[str] = None
        self._form_widgets: Dict[str, QWidget] = {}

        self.setWindowTitle(_t("dlg.vent_norms.title"))
        self.resize(940, 660)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        # Подсказка про глобальную область действия.
        hint = QLabel(_t("dlg.vent_norms.scope_hint").format(
            path=un._user_norms_path()))   # noqa: SLF001
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        root.addWidget(hint)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        root.addWidget(split, stretch=1)

        root.addLayout(self._build_buttons())

        self._refresh_types_list()
        self._select_initial(initial_type)

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _build_left(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel(_t("dlg.vent_norms.types_group")))

        self.types_tree = QTreeWidget()
        self.types_tree.setColumnCount(2)
        self.types_tree.setHeaderLabels([
            _t("dlg.vent_norms.col_type"),
            _t("dlg.vent_norms.col_source"),
        ])
        self.types_tree.setRootIsDecorated(False)
        self.types_tree.setColumnWidth(0, 200)
        self.types_tree.currentItemChanged.connect(self._on_type_select)
        lay.addWidget(self.types_tree, stretch=1)

        btns = QHBoxLayout()
        self.btn_new = QPushButton(_t("dlg.vent_norms.btn_new"))
        self.btn_new.clicked.connect(self._add_new_type)
        self.btn_del = QPushButton(_t("dlg.vent_norms.btn_delete"))
        self.btn_del.clicked.connect(self._delete_type)
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        lay.addLayout(btns)
        return box

    def _build_right(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel(_t("dlg.vent_norms.params_group")))

        self.title_lbl = QLabel("")
        self.title_lbl.setProperty("role", "h2")
        lay.addWidget(self.title_lbl)

        self.status_lbl = QLabel("")
        self.status_lbl.setProperty("role", "muted")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        # Прокручиваемая форма.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QVBoxLayout(inner)
        form.setContentsMargins(4, 4, 12, 4)
        form.setSpacing(6)

        for kind, key, label_key in _FIELD_DEFS:
            if kind == "__sep__":
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                form.addSpacing(4)
                form.addWidget(line)
                sep_lbl = QLabel(_t(key))
                sep_lbl.setProperty("role", "h3")
                form.addWidget(sep_lbl)
                continue

            row = QHBoxLayout()
            lbl = QLabel(_t(label_key))
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(300)
            if kind == "__bool__":
                w: QWidget = QCheckBox()
            else:
                w = QLineEdit()
                w.setMaximumWidth(260 if kind == "text" else 120)
            row.addWidget(lbl, stretch=1)
            row.addWidget(w)
            form.addLayout(row)
            self._form_widgets[key] = w

        form.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)
        return box

    def _build_buttons(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.btn_reset = QPushButton(_t("dlg.vent_norms.btn_reset"))
        self.btn_reset.clicked.connect(self._reset_current)
        bar.addWidget(self.btn_reset)
        bar.addStretch(1)

        self.btn_cancel = QPushButton(_t("btn.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton(_t("dlg.vent_norms.btn_save"))
        self.btn_save.clicked.connect(lambda: self._save_and_close(False))
        self.btn_save_recalc = QPushButton(
            _t("dlg.vent_norms.btn_save_recalc"))
        self.btn_save_recalc.setProperty("role", "primary")
        self.btn_save_recalc.clicked.connect(
            lambda: self._save_and_close(True))
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_save_recalc)
        return bar

    # ------------------------------------------------------------------
    # Список типов
    # ------------------------------------------------------------------
    def _refresh_types_list(self, select: Optional[str] = None) -> None:
        self.types_tree.blockSignals(True)
        self.types_tree.clear()
        accent = QColor(tokens().get("accent", "#0066AA"))
        for t in un.get_builtin_room_types():
            if un.has_ventilation_override(t):
                item = QTreeWidgetItem([t, _t("dlg.vent_norms.src_sp_overridden")])
                item.setForeground(0, QBrush(accent))
            else:
                item = QTreeWidgetItem([t, _t("dlg.vent_norms.src_sp")])
            self.types_tree.addTopLevelItem(item)
        for t in un.get_custom_room_types():
            item = QTreeWidgetItem([t, _t("dlg.vent_norms.src_custom")])
            item.setForeground(0, QBrush(QColor(_COLOR_CUSTOM)))
            self.types_tree.addTopLevelItem(item)
        self.types_tree.blockSignals(False)
        if select is not None:
            self._select_type(select)

    def _select_type(self, room_type: str) -> bool:
        for i in range(self.types_tree.topLevelItemCount()):
            item = self.types_tree.topLevelItem(i)
            if item is not None and item.text(0) == room_type:
                self.types_tree.setCurrentItem(item)
                return True
        return False

    def _select_initial(self, initial_type: Optional[str]) -> None:
        wanted = initial_type if initial_type and self._type_exists(
            initial_type) else "Офис"  # i18n-allow (имя типа = ключ данных)
        if not self._select_type(wanted):
            first = self.types_tree.topLevelItem(0)
            if first is not None:
                self.types_tree.setCurrentItem(first)

    def _type_exists(self, room_type: str) -> bool:
        return room_type in un.get_all_room_types()

    # ------------------------------------------------------------------
    # Форма: загрузка / сбор
    # ------------------------------------------------------------------
    def _on_type_select(self, current: Optional[QTreeWidgetItem],
                        _previous=None) -> None:
        if current is None:
            return
        new_type = current.text(0)
        # Перед переключением — закэшировать (без записи на диск) правки
        # текущего типа, чтобы не потерять их при навигации.
        if self._current_type and self._current_type != new_type:
            try:
                vals = self._collect_form()
                un.set_ventilation_override(
                    self._current_type, vals, autosave=False)
            except (ValueError, KeyError):
                pass
        self._load_form(new_type)

    def _load_form(self, room_type: str) -> None:
        self._current_type = room_type
        norms = un.get_ventilation_norms(room_type)
        self.title_lbl.setText(room_type)

        if un.is_custom_type(room_type):
            self.status_lbl.setText(_t("dlg.vent_norms.status_custom"))
        elif un.has_ventilation_override(room_type):
            fields = ", ".join(sorted(un.get_raw_override(room_type).keys()))
            self.status_lbl.setText(
                _t("dlg.vent_norms.status_overridden").format(fields=fields))
        else:
            self.status_lbl.setText(_t("dlg.vent_norms.status_default"))

        for kind, key, _label in _FIELD_DEFS:
            if kind == "__sep__":
                continue
            w = self._form_widgets[key]
            val = norms.get(key)
            if kind == "__bool__":
                w.setChecked(bool(val))
            elif kind == "text":
                w.setText(str(val) if val is not None else "")
            else:  # float
                w.setText("" if val in (None, 0) else f"{val:g}")
        self._sync_button_state()

    def _collect_form(self) -> Dict:
        """Собирает значения формы. Пустые поля пропускаются. Бросает
        ValueError, если число не парсится."""
        result: Dict = {}
        for kind, key, label_key in _FIELD_DEFS:
            if kind == "__sep__":
                continue
            w = self._form_widgets[key]
            if kind == "__bool__":
                if w.isChecked():
                    result[key] = True
            elif kind == "text":
                s = w.text().strip()
                if s:
                    result[key] = s
            else:  # float
                s = w.text().strip().replace(",", ".")
                if not s:
                    continue
                try:
                    result[key] = float(s)
                except ValueError:
                    raise ValueError(
                        _t("dlg.vent_norms.err_not_number").format(
                            label=_t(label_key), val=s))
        return result

    def _sync_button_state(self) -> None:
        t = self._current_type
        is_custom = t is not None and bool(t) and un.is_custom_type(t)
        self.btn_del.setEnabled(is_custom)
        self.btn_reset.setEnabled(
            t is not None and bool(t) and not is_custom
            and un.has_ventilation_override(t))

    # ------------------------------------------------------------------
    # Действия с типами
    # ------------------------------------------------------------------
    def _add_new_type(self) -> None:
        name, ok = QInputDialog.getText(
            self, _t("dlg.vent_norms.new_title"),
            _t("dlg.vent_norms.new_prompt"))
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            un.add_custom_type(name, ventilation={}, thermal={},
                               autosave=False)
        except ValueError as e:
            QMessageBox.critical(self, _t("dlg.vent_norms.err_title"), str(e))
            return
        self._refresh_types_list(select=name)

    def _delete_type(self) -> None:
        t = self._current_type
        if not t:
            return
        if not un.is_custom_type(t):
            QMessageBox.information(
                self, _t("dlg.vent_norms.del_builtin_title"),
                _t("dlg.vent_norms.del_builtin_msg").format(t=t))
            return
        in_use = sum(1 for sp in self.project.spaces if sp.room_type == t)
        extra = ""
        if in_use:
            extra = _t("dlg.vent_norms.del_in_use").format(n=in_use)
        if QMessageBox.question(
                self, _t("dlg.vent_norms.del_confirm_title"),
                _t("dlg.vent_norms.del_confirm_msg").format(t=t, extra=extra)
        ) != QMessageBox.Yes:
            return
        un.delete_custom_type(t, autosave=False)
        self._current_type = None
        self.title_lbl.setText("")
        self.status_lbl.setText("")
        self._refresh_types_list()

    def _reset_current(self) -> None:
        t = self._current_type
        if not t:
            return
        if un.is_custom_type(t):
            QMessageBox.information(
                self, _t("dlg.vent_norms.info_title"),
                _t("dlg.vent_norms.reset_custom_msg"))
            return
        if not un.has_ventilation_override(t):
            QMessageBox.information(
                self, _t("dlg.vent_norms.info_title"),
                _t("dlg.vent_norms.reset_none_msg").format(t=t))
            return
        un.reset_ventilation_override(t, autosave=False)
        self._refresh_types_list(select=t)
        self._load_form(t)

    # ------------------------------------------------------------------
    # Сохранение
    # ------------------------------------------------------------------
    def _save_and_close(self, recalc: bool) -> None:
        t = self._current_type
        if t:
            try:
                vals = self._collect_form()
                un.set_ventilation_override(t, vals, autosave=False)
            except ValueError as e:
                QMessageBox.critical(
                    self, _t("dlg.vent_norms.err_title"), str(e))
                return
        try:
            path = un.save_to_disk()
        except OSError as e:
            QMessageBox.critical(
                self, _t("dlg.vent_norms.save_err_title"),
                _t("dlg.vent_norms.save_err_msg").format(e=e))
            return

        if recalc and self.project.spaces:
            self._recalculate(path)
        else:
            QMessageBox.information(
                self, _t("dlg.vent_norms.saved_title"),
                _t("dlg.vent_norms.saved_msg").format(path=path))
        self.accept()

    def _recalculate(self, path: str) -> None:
        # Новые нормы не перетирают помещения с ручными правками. Спрашиваем,
        # сбрасывать ли их, чтобы пересчёт реально применил норматив.
        manual = [sp for sp in self.project.spaces if sp.vent_user_modified]
        if manual and QMessageBox.question(
                self, _t("dlg.vent_norms.reset_manual_title"),
                _t("dlg.vent_norms.reset_manual_msg").format(n=len(manual))
        ) == QMessageBox.Yes:
            for sp in manual:
                sp.vent_user_modified = False
        try:
            self.project.calculate_ventilation()
        except Exception as e:   # noqa: BLE001 — показываем пользователю
            QMessageBox.critical(
                self, _t("dlg.vent_norms.calc_err_title"), str(e))
            return
        if self.bridge is not None:
            self.bridge.ventilationDone.emit(0)
        QMessageBox.information(
            self, _t("dlg.vent_norms.done_title"),
            _t("dlg.vent_norms.done_recalc_msg").format(path=path))

    # ------------------------------------------------------------------
    # Отмена: откатить незаписанные правки кэша к состоянию на диске.
    # ------------------------------------------------------------------
    def reject(self) -> None:
        un.reload_from_disk()
        super().reject()
