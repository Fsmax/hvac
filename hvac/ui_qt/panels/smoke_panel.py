# -*- coding: utf-8 -*-
"""SmokePanel — системы дымоудаления (СДУ) и подпора воздуха (СПВ).

Возможности:
  • выбор активного норматива (СП 7.13130 / КМК 2.04.05-22 / NFPA 92 / Свой)
  • авто-присвоение систем по типам помещений
  • выбор сценария пожара (один очаг / несколько зон одновременно)
  • редактирование параметров каждой системы через SmokeSystemDialog
  • создание, удаление и копирование систем вручную
  • результаты расчёта в виде таблицы (L_smoke, L_makeup, n_zones, площадь)
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from hvac.catalogs.smoke_norms import SMOKE_NORMS, get_smoke_norm
from hvac.i18n import on_language_change, t as _t
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.card import Card
from hvac.ui_qt.widgets.smoke_system_dialog import (
    SmokeSystemDialog, _method_label, _purpose_label, _systype_label,
)


_HEADER_KEYS = (
    "panel.smoke.col.name",
    "panel.smoke.col.type",
    "panel.smoke.col.purpose",
    "panel.smoke.col.method",
    "panel.smoke.col.norm",
    "panel.smoke.col.spaces",
    "panel.smoke.col.area",
    "panel.smoke.col.flow",
    "panel.smoke.col.makeup",
    "panel.smoke.col.zones",
)


class SmokePanel(QWidget):
    """Главная панель раздела «Дымоудаление»."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        # ---------- Заголовок ----------
        head = QHBoxLayout()
        self._h = QLabel(_t("panel.smoke.title"))
        self._h.setProperty("role", "h1")
        head.addWidget(self._h)
        head.addStretch(1)
        outer.addLayout(head)

        # ---------- Параметры расчёта ----------
        self._params_card = Card(
            _t("panel.smoke.card.params.title"),
            _t("panel.smoke.card.params.sub"),
        )
        self._params_card._i18n_title_key = "panel.smoke.card.params.title"
        self._params_card._i18n_sub_key = "panel.smoke.card.params.sub"
        params_row = QHBoxLayout()

        self._norm_lbl = QLabel(_t("panel.smoke.norm"))
        params_row.addWidget(self._norm_lbl)
        self.norm_combo = QComboBox()
        for code, n in SMOKE_NORMS.items():
            self.norm_combo.addItem(n.title, userData=code)
        self._select_norm(project.params.smoke_norm)
        self.norm_combo.currentIndexChanged.connect(self._on_norm_changed)
        params_row.addWidget(self.norm_combo)

        params_row.addSpacing(12)
        self._scn_lbl = QLabel(_t("panel.smoke.scenario"))
        params_row.addWidget(self._scn_lbl)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(_t("panel.smoke.scenario.single"),
                                userData="single_zone")
        self.mode_combo.addItem(_t("panel.smoke.scenario.multiple"),
                                userData="multiple_zones")
        params_row.addWidget(self.mode_combo)

        params_row.addStretch(1)

        self.assign_btn = QPushButton(_t("panel.smoke.btn_assign"))
        self.assign_btn.setToolTip(_t("panel.smoke.btn_assign_tt"))
        self.assign_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.assign_btn.clicked.connect(self._auto_assign)
        params_row.addWidget(self.assign_btn)

        self.calc_btn = QPushButton(_t("panel.smoke.btn_calc"))
        self.calc_btn.setProperty("role", "primary")
        self.calc_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.calc_btn.clicked.connect(self._calc)
        params_row.addWidget(self.calc_btn)

        self._params_card.body().addLayout(params_row)
        outer.addWidget(self._params_card)

        # ---------- Таблица систем ----------
        self._table_card = Card(
            _t("panel.smoke.card.systems.title"),
            _t("panel.smoke.card.systems.sub"),
        )
        self._table_card._i18n_title_key = "panel.smoke.card.systems.title"
        self._table_card._i18n_sub_key = "panel.smoke.card.systems.sub"

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton(_t("panel.smoke.btn_add"))
        self.add_btn.clicked.connect(self._add_system)
        toolbar.addWidget(self.add_btn)

        self.edit_btn = QPushButton(_t("panel.smoke.btn_edit"))
        self.edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(self.edit_btn)

        self.dup_btn = QPushButton(_t("panel.smoke.btn_dup"))
        self.dup_btn.clicked.connect(self._duplicate_selected)
        toolbar.addWidget(self.dup_btn)

        self.del_btn = QPushButton(_t("panel.smoke.btn_delete"))
        self.del_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self.del_btn)

        toolbar.addStretch(1)
        self.summary_label = QLabel("")
        self.summary_label.setProperty("role", "muted")
        toolbar.addWidget(self.summary_label)
        self._table_card.body().addLayout(toolbar)

        self.table = QTableWidget(0, len(_HEADER_KEYS))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        widths = [140, 120, 160, 220, 130, 90, 110, 130, 140, 60]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.table.doubleClicked.connect(lambda *_: self._edit_selected())
        self._table_card.body().addWidget(self.table)
        # Card по умолчанию имеет вертикальную политику Maximum (чтобы не
        # растягиваться в сетке). Здесь карточка с таблицей должна заполнять
        # всё свободное место — иначе лишняя высота «утекает» в заголовок h1
        # и над «Параметрами» появляется огромный пустой блок.
        self._table_card.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding)
        outer.addWidget(self._table_card, stretch=1)

        # ---------- Сигналы ----------
        for sig in (bridge.dataLoaded, bridge.projectLoaded,
                    bridge.zonesChanged, bridge.smokeSystemsChanged,
                    bridge.smokeLoadsCalculated):
            sig.connect(self._refresh)
        on_language_change(lambda _lang: self.retranslate_ui())
        self._refresh()

    # ---------- Действия ----------
    def _select_norm(self, code: str) -> None:
        for i in range(self.norm_combo.count()):
            if self.norm_combo.itemData(i) == code:
                self.norm_combo.setCurrentIndex(i)
                return

    def _current_norm_code(self) -> str:
        return self.norm_combo.currentData() or "SP7_RU"

    def _current_fire_mode(self) -> str:
        return self.mode_combo.currentData() or "single_zone"

    def retranslate_ui(self) -> None:
        self._h.setText(_t("panel.smoke.title"))
        if hasattr(self._params_card, "set_title"):
            self._params_card.set_title(_t("panel.smoke.card.params.title"))
            self._params_card.set_subtitle(_t("panel.smoke.card.params.sub"))
            self._table_card.set_title(_t("panel.smoke.card.systems.title"))
            self._table_card.set_subtitle(_t("panel.smoke.card.systems.sub"))
        self._norm_lbl.setText(_t("panel.smoke.norm"))
        self._scn_lbl.setText(_t("panel.smoke.scenario"))

        # Mode combo — сохранить выбор по userData
        prev_mode = self.mode_combo.currentData()
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        self.mode_combo.addItem(_t("panel.smoke.scenario.single"),
                                userData="single_zone")
        self.mode_combo.addItem(_t("panel.smoke.scenario.multiple"),
                                userData="multiple_zones")
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == prev_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        self.mode_combo.blockSignals(False)

        self.assign_btn.setText(_t("panel.smoke.btn_assign"))
        self.assign_btn.setToolTip(_t("panel.smoke.btn_assign_tt"))
        self.calc_btn.setText(_t("panel.smoke.btn_calc"))
        self.add_btn.setText(_t("panel.smoke.btn_add"))
        self.edit_btn.setText(_t("panel.smoke.btn_edit"))
        self.dup_btn.setText(_t("panel.smoke.btn_dup"))
        self.del_btn.setText(_t("panel.smoke.btn_delete"))
        self.table.setHorizontalHeaderLabels([_t(k) for k in _HEADER_KEYS])
        self._refresh()

    def _on_norm_changed(self) -> None:
        code = self._current_norm_code()
        if code == self.project.params.smoke_norm:
            return
        # Если уже есть системы, спросим
        has_systems = bool(self.project.smoke_systems)
        update = True
        if has_systems:
            ans = QMessageBox.question(
                self, _t("panel.smoke.title.change_norm"),
                _t("panel.smoke.msg.change_norm").format(
                    title=get_smoke_norm(code).title),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if ans == QMessageBox.Cancel:
                self._select_norm(self.project.params.smoke_norm)
                return
            update = (ans == QMessageBox.Yes)
        try:
            stats = self.project.apply_smoke_norm(code, update_existing=update)
        except ValueError as e:
            QMessageBox.warning(self, _t("panel.smoke.title.err"), str(e))
            return
        msg = _t("panel.smoke.status.norm").format(
            title=get_smoke_norm(code).title)
        if update and stats["n_updated_smoke"] + stats["n_updated_pres"] > 0:
            msg += _t("panel.smoke.status.norm_upd").format(
                smoke=stats['n_updated_smoke'],
                pres=stats['n_updated_pres'])
            if stats["n_recalc_method"]:
                msg += _t("panel.smoke.status.norm_method").format(
                    n=stats['n_recalc_method'])
        self.bridge.statusMessage.emit(msg, 5000)
        self.bridge.dirtyChanged.emit(True)

    def _auto_assign(self) -> None:
        if not self.project.spaces:
            QMessageBox.information(
                self, _t("panel.smoke.title.no_data"),
                _t("panel.smoke.msg.no_data"))
            return
        overwrite = False
        # Если что-то уже назначено — спросим, перезаписывать ли
        any_assigned = any(
            sp.smoke_system or sp.pressurization_system
            for sp in self.project.spaces
        )
        if any_assigned:
            ans = QMessageBox.question(
                self, _t("panel.smoke.title.assign"),
                _t("panel.smoke.msg.assign_overwrite"),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if ans == QMessageBox.Cancel:
                return
            overwrite = (ans == QMessageBox.Yes)
        try:
            stats = self.project.auto_assign_smoke_systems(overwrite=overwrite)
        except Exception as e:
            QMessageBox.critical(self, _t("panel.smoke.title.err"), str(e))
            return
        self.bridge.statusMessage.emit(
            _t("panel.smoke.status.assigned").format(
                smoke=stats['n_smoke_systems'],
                pres=stats['n_pressurization'],
                n=stats['n_spaces_assigned']),
            6000,
        )
        self.bridge.dirtyChanged.emit(True)

    def _calc(self) -> None:
        if not self.project.smoke_systems:
            QMessageBox.information(
                self, _t("panel.smoke.title.no_systems"),
                _t("panel.smoke.msg.no_systems"))
            return
        try:
            self.project.calculate_smoke_loads(fire_mode=self._current_fire_mode())
        except Exception as e:
            QMessageBox.critical(
                self, _t("panel.smoke.title.calc_err"), str(e))
            return
        self.bridge.statusMessage.emit(_t("panel.smoke.status.calc_done"), 4000)
        self.bridge.dirtyChanged.emit(True)

    def _selected_system_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _add_system(self) -> None:
        from hvac.smoke import SmokeSystem
        tpl = SmokeSystem(name="")
        norm = get_smoke_norm(self._current_norm_code())
        tpl.calc_method = norm.calc_method_recommended
        tpl.makeup_ratio = norm.default_makeup_ratio
        tpl.t_smoke_C = norm.default_t_smoke_C
        tpl.fire_rating = norm.default_fire_rating
        tpl.max_zone_area_m2 = norm.max_zone_area_m2
        dlg = SmokeSystemDialog(self, system=tpl,
                                norm_code=self._current_norm_code(),
                                is_new=True)
        if dlg.exec() != QDialog.Accepted:
            return
        sm = dlg.system
        try:
            new_sm = self.project.create_smoke_system_manual(
                name=sm.name, system_type=sm.system_type,
                purpose=sm.purpose, calc_method=sm.calc_method,
                fire_rating=sm.fire_rating,
                note=sm.note or _t("panel.smoke.note_manual"),
                norm_per_m2=sm.norm_per_m2,
                max_zone_area_m2=sm.max_zone_area_m2,
                makeup_ratio=sm.makeup_ratio,
                t_smoke_C=sm.t_smoke_C,
                pressure_pa=sm.pressure_pa,
                L_smoke_m3h=sm.L_smoke_m3h,
                fire_perimeter_m=sm.fire_perimeter_m,
                layer_height_m=sm.layer_height_m,
                ks_sprinkler=sm.ks_sprinkler,
                corridor_door_width_m=sm.corridor_door_width_m,
                corridor_door_height_m=sm.corridor_door_height_m,
                corridor_public=sm.corridor_public,
                kd_door=sm.kd_door,
                hrr_kw=sm.hrr_kw,
                convective_fraction=sm.convective_fraction,
                plume_height_m=sm.plume_height_m,
            )
        except ValueError as e:
            QMessageBox.warning(self, _t("panel.smoke.title.err"), str(e))
            return
        # Обновляем таблицу напрямую, не полагаясь только на сигнал
        # smokeSystemsChanged: иначе добавленная система может «не
        # отобразиться» сразу после создания.
        self._refresh()
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.smoke.status.created").format(name=new_sm.name), 4000)

    def _edit_selected(self) -> None:
        name = self._selected_system_name()
        if not name:
            return
        sm = self.project.smoke_systems.get(name)
        if sm is None:
            return
        dlg = SmokeSystemDialog(self, system=sm,
                                norm_code=self._current_norm_code(),
                                is_new=False)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.system
        # Имя не менялось (поле заблокировано). Копируем все поля обратно.
        for fld in sm.__dataclass_fields__:
            if fld == "name":
                continue
            setattr(sm, fld, getattr(updated, fld))
        self.project.emit("smoke_systems_changed")
        self._refresh()
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.smoke.status.saved").format(name=name), 3000)

    def _duplicate_selected(self) -> None:
        name = self._selected_system_name()
        if not name:
            return
        src = self.project.smoke_systems.get(name)
        if src is None:
            return
        new_name, ok = QInputDialog.getText(
            self, _t("panel.smoke.title.dup"),
            _t("panel.smoke.msg.dup"),
            text=f"{name}{_t('panel.smoke.dup.suffix')}",
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name in self.project.smoke_systems:
            QMessageBox.warning(
                self, _t("panel.smoke.title.name_busy"),
                _t("panel.smoke.msg.name_busy").format(name=new_name))
            return
        from hvac.smoke import SmokeSystem
        clone = SmokeSystem(
            **{f: getattr(src, f) for f in SmokeSystem.__dataclass_fields__}
        )
        clone.name = new_name
        clone.note = (src.note + _t("panel.smoke.copy_suffix")).strip()
        self.project.smoke_systems[new_name] = clone
        self.project.emit("smoke_systems_changed")
        self._refresh()
        self.bridge.dirtyChanged.emit(True)

    def _delete_selected(self) -> None:
        name = self._selected_system_name()
        if not name:
            return
        ans = QMessageBox.question(
            self, _t("panel.smoke.title.del"),
            _t("panel.smoke.msg.del").format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        n = self.project.delete_smoke_system(name)
        self._refresh()
        self.bridge.statusMessage.emit(
            _t("panel.smoke.status.deleted").format(name=name, n=n), 4000)
        self.bridge.dirtyChanged.emit(True)

    # ---------- Обновление ----------
    def _refresh(self, *args: Any) -> None:
        # Гарантия, что комбобокс норматива отражает project.params
        if self._current_norm_code() != self.project.params.smoke_norm:
            self.norm_combo.blockSignals(True)
            self._select_norm(self.project.params.smoke_norm)
            self.norm_combo.blockSignals(False)

        systems = list(self.project.smoke_systems.values())
        # Кол-во помещений на каждой системе
        counts: Dict[str, int] = {}
        for sp in self.project.spaces:
            for key in (sp.smoke_system, sp.pressurization_system):
                if key:
                    counts[key] = counts.get(key, 0) + 1

        self.table.setRowCount(len(systems))
        sum_smoke = sum_makeup = 0.0
        for r, s in enumerate(systems):
            method_label = _method_label(s.calc_method)
            short_key = f"panel.smoke.short_method.{s.calc_method}"
            short_method = _t(short_key)
            if short_method == short_key:    # ключ не найден
                short_method = s.calc_method

            type_label = _systype_label(s.system_type)
            purpose_label = _purpose_label(s.purpose)

            norm_text = f"{s.norm_per_m2:.0f}" if s.system_type != "air_supply" else "—"

            cells = [
                s.name,
                type_label,
                purpose_label,
                short_method,
                norm_text,
                str(counts.get(s.name, 0)),
                f"{s.served_area_m2:.0f}" if s.served_area_m2 else "—",
                f"{s.L_smoke_m3h:,.0f}".replace(",", " ") if s.L_smoke_m3h else "—",
                (f"{s.L_makeup_m3h:,.0f}".replace(",", " ")
                 if s.L_makeup_m3h and s.system_type != "air_supply" else "—"),
                str(s.n_zones) if s.n_zones else "—",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c in (4, 5, 6, 7, 8, 9):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(method_label if c == 3 else (s.note or ""))
                self.table.setItem(r, c, item)
            if s.system_type == "smoke_removal":
                sum_smoke += s.L_smoke_m3h
                sum_makeup += s.L_makeup_m3h

        if systems:
            parts = [_t("panel.smoke.summary.total").format(n=len(systems))]
            if sum_smoke:
                parts.append(_t("panel.smoke.summary.flows").format(
                    smoke=sum_smoke / 1000, makeup=sum_makeup / 1000))
            self.summary_label.setText("   |   ".join(parts))
        else:
            self.summary_label.setText(_t("panel.smoke.summary.empty"))
