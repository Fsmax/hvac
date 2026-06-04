# -*- coding: utf-8 -*-
"""VentilationPanel — таблица расходов воздуха по помещениям + сводка."""
from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt,
)
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.theme import tokens
from hvac.ui_qt.widgets.card import Card
from hvac.ui_qt.widgets.table_edit import (
    EditableTableModelMixin, TableEditBinder,
)


def _floor_num(level: str) -> float:
    """Числовой ключ этажа из строки уровня («L12» → 12, «-1» → -1).
    Без числа — в конец списка."""
    m = re.search(r"-?\d+", level or "")
    return float(m.group()) if m else 1e9


_VENT_HEADER_KEYS = [
    "panel.ventilation.col.number", "panel.ventilation.col.name",
    "panel.ventilation.col.level",  "panel.ventilation.col.type",
    "panel.ventilation.col.area",   "panel.ventilation.col.supply",
    "panel.ventilation.col.exhaust","panel.ventilation.col.hood",
    "panel.ventilation.col.ach",    "panel.ventilation.col.air",
    "panel.ventilation.col.imbal",
]
_COL_AIR, _COL_IMBAL = 9, 10

# Колонки расходов воздуха, доступные для ручной правки прямо в таблице.
# Любая правка ставит vent_user_modified=True, и calculate_ventilation()
# больше не перетирает это помещение (см. HVACProject.calculate_ventilation).
_COL_SUPPLY, _COL_EXHAUST, _COL_HOOD = 5, 6, 7
_EDITABLE_VENT_COLS = (_COL_SUPPLY, _COL_EXHAUST, _COL_HOOD)

# Нормативные пресеты расхода для выделенных помещений (СП 60 / СП 54).
# (i18n-ключ, колонка, режим apply_bulk, значение).
_AIRFLOW_PRESETS = [
    ("panel.ventilation.preset.toilet",     _COL_EXHAUST, "ach", 10.0),
    ("panel.ventilation.preset.toilet_ind", _COL_EXHAUST, "set", 50.0),
    ("panel.ventilation.preset.shower",     _COL_EXHAUST, "set", 75.0),
    ("panel.ventilation.preset.kitchen",    _COL_EXHAUST, "set", 60.0),
    ("panel.ventilation.preset.living",     _COL_SUPPLY,  "ach", 1.0),
    ("panel.ventilation.preset.office",     _COL_SUPPLY,  "ach", 3.0),
]


class VentilationModel(EditableTableModelMixin, QAbstractTableModel):

    _EDITABLE_COLS = {_COL_SUPPLY, _COL_EXHAUST, _COL_HOOD}
    _BULK_ATTR = {_COL_SUPPLY: "supply_m3h",
                  _COL_EXHAUST: "exhaust_m3h",
                  _COL_HOOD: "hood_m3h"}
    # Поля, снимаемые для отмены/повтора.
    _SNAPSHOT_FIELDS = ("supply_m3h", "exhaust_m3h", "hood_m3h",
                        "ach_calculated", "vent_user_modified",
                        "air_heating", "air_cooling")

    def __init__(self, project: HVACProject, bridge: ProjectBridge):
        super().__init__()
        self.project = project
        self.bridge = bridge
        self._init_edit_history()
        bridge.dataLoaded.connect(self._reset)
        bridge.projectLoaded.connect(self._reset)
        bridge.ventilationDone.connect(self._reset)

    def _reset(self, *args: Any) -> None:
        # Перезагрузка данных/пересчёт обнуляют историю — снимки ссылаются на
        # прежние строки и больше не валидны.
        self.clear_edit_history()
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.project.spaces)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_VENT_HEADER_KEYS)

    def headerData(self, section, orient, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orient == Qt.Horizontal:
            return _t(_VENT_HEADER_KEYS[section])
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() in _EDITABLE_VENT_COLS:
            base |= Qt.ItemIsEditable
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        sp: Space = self.project.spaces[index.row()]
        col = index.column()
        # Редактор открывается с сырым числом (а не с форматированной "" для нуля).
        if role == Qt.EditRole and col in _EDITABLE_VENT_COLS:
            return {_COL_SUPPLY: sp.supply_m3h,
                    _COL_EXHAUST: sp.exhaust_m3h,
                    _COL_HOOD: sp.hood_m3h}[col]
        if role in (Qt.DisplayRole,):
            if col == 0: return sp.number
            if col == 1: return sp.name
            if col == 2: return sp.level
            if col == 3: return sp.room_type
            if col == 4: return f"{sp.area_m2:.1f}"
            if col == 5: return f"{sp.supply_m3h:.0f}" if sp.supply_m3h else ""
            if col == 6: return f"{sp.exhaust_m3h:.0f}" if sp.exhaust_m3h else ""
            if col == 7: return f"{sp.hood_m3h:.0f}" if sp.hood_m3h else ""
            if col == 8: return f"{sp.ach_calculated:.1f}" if sp.ach_calculated else ""
            if col == _COL_AIR:
                marks = []
                if getattr(sp, "air_heating", False):
                    marks.append(_t("panel.sysworkspace.air.mark_heat"))
                if getattr(sp, "air_cooling", False):
                    marks.append(_t("panel.sysworkspace.air.mark_cool"))
                return "·".join(marks)
            if col == _COL_IMBAL:
                diff = sp.supply_m3h - (sp.exhaust_m3h + sp.hood_m3h)
                return f"{diff:+.0f}" if (sp.supply_m3h or sp.exhaust_m3h) else ""
        if role == Qt.TextAlignmentRole and col >= 4:
            if col == _COL_AIR:
                return int(Qt.AlignCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            # Вручную исправленные расходы выделяем акцентом.
            if sp.vent_user_modified and col in _EDITABLE_VENT_COLS:
                return QBrush(QColor(tokens()["accent"]))
            if col == _COL_IMBAL and (sp.supply_m3h or sp.exhaust_m3h):
                diff = sp.supply_m3h - (sp.exhaust_m3h + sp.hood_m3h)
                if abs(diff) > 50:
                    return QBrush(QColor(tokens()["warning"]))
        if role == Qt.ToolTipRole and sp.vent_user_modified:
            return _t("panel.ventilation.tooltip.manual")
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        return self.commit_cell(index.row(), index.column(), value)

    # ---------- Хуки EditableTableModelMixin ----------
    def _recompute_ach(self, sp) -> None:
        if sp.volume_m3 > 0:
            sp.ach_calculated = max(sp.supply_m3h, sp.exhaust_m3h) / sp.volume_m3

    def _snapshot_row(self, row: int) -> dict:
        sp = self.project.spaces[row]
        return {f: getattr(sp, f) for f in self._SNAPSHOT_FIELDS}

    def _restore_row(self, row: int, snap: dict) -> None:
        sp = self.project.spaces[row]
        for f, v in snap.items():
            setattr(sp, f, v)

    def _apply_cell(self, row: int, col: int, raw) -> bool:
        try:
            v = max(float(raw), 0.0)
        except (TypeError, ValueError):
            return False
        sp = self.project.spaces[row]
        setattr(sp, self._BULK_ATTR[col], v)
        sp.vent_user_modified = True
        self._recompute_ach(sp)
        return True

    def _cell_edit_value(self, row: int, col: int):
        return getattr(self.project.spaces[row], self._BULK_ATTR[col])

    # ---------- Групповая правка ----------

    def apply_bulk(self, source_rows, col: int, mode: str,
                   value: float) -> int:
        """Применяет одну правку ко всем выбранным помещениям.

        col  — редактируемая колонка (_COL_SUPPLY/_EXHAUST/_HOOD);
        mode — 'set'   задать абсолютное значение [м³/ч],
               'scale' изменить текущее на value процентов,
               'ach'   задать по кратности: value · volume_m3 [1/ч].
        Каждое затронутое помещение помечается vent_user_modified=True.
        Возвращает число изменённых помещений.
        """
        if col not in _EDITABLE_VENT_COLS:
            return 0
        attr = self._BULK_ATTR[col]

        def mutate(rows):
            for r in rows:
                sp = self.project.spaces[r]
                cur = getattr(sp, attr)
                if mode == "set":
                    new = max(value, 0.0)
                elif mode == "scale":
                    new = max(cur * (1.0 + value / 100.0), 0.0)
                elif mode == "ach":
                    new = max(value * sp.volume_m3, 0.0)
                else:
                    continue
                setattr(sp, attr, new)
                sp.vent_user_modified = True
                self._recompute_ach(sp)

        return self._commit(source_rows, mutate)

    def reset_manual(self, source_rows) -> int:
        """Сбрасывает ручную правку у выбранных помещений и пересчитывает их
        штатным движком вентиляции. Отменяемо. Возвращает число сброшенных."""
        from hvac.engine.ventilation import get_ventilation_engine
        engine = get_ventilation_engine(None)

        def mutate(rows):
            for r in rows:
                sp = self.project.spaces[r]
                if not sp.vent_user_modified:
                    continue
                sp.vent_user_modified = False
                br = engine.calculate(sp, self.project)
                sp.ventilation_breakdown = br
                sp.supply_m3h = br.get("supply_m3h", 0.0)
                sp.exhaust_m3h = br.get("exhaust_m3h", 0.0)
                sp.hood_m3h = br.get("hood_m3h", 0.0)
                sp.ach_calculated = br.get("ach_calculated", 0.0)

        return self._commit(source_rows, mutate)

    def set_air_mode(self, source_rows, heating, cooling) -> int:
        """Включает/выключает воздушное отопление/охлаждение у выбранных
        помещений и пересчитывает расход приточки по нагрузке.

        heating/cooling: True (вкл), False (выкл), None (не менять).
        Отменяемо (поля air_* и расход в снимке). Возвращает число помещений.
        """
        from hvac.air_heating import apply_air_heating

        def mutate(rows):
            for r in rows:
                sp = self.project.spaces[r]
                if heating is not None:
                    sp.air_heating = heating
                if cooling is not None:
                    sp.air_cooling = cooling
            apply_air_heating(self.project)

        return self._commit(source_rows, mutate)


class BulkVentDialog(QDialog):
    """Диалог групповой правки расходов воздуха для выделенных помещений."""

    # (ключ режима, ключ i18n, суффикс единиц, диапазон, дробных знаков)
    _MODES = [
        ("set",   "panel.ventilation.bulk.mode.set",   " м³/ч", (0.0, 100000.0), 0),
        ("scale", "panel.ventilation.bulk.mode.scale", " %",    (-100.0, 1000.0), 0),
        ("ach",   "panel.ventilation.bulk.mode.ach",   " 1/ч",  (0.0, 100.0),    1),
    ]

    def __init__(self, n_selected: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.ventilation.bulk.title"))
        self.setModal(True)

        form = QFormLayout(self)

        self.field_combo = QComboBox()
        for col in _EDITABLE_VENT_COLS:
            key = {_COL_SUPPLY: "panel.ventilation.col.supply",
                   _COL_EXHAUST: "panel.ventilation.col.exhaust",
                   _COL_HOOD: "panel.ventilation.col.hood"}[col]
            self.field_combo.addItem(_t(key), col)
        form.addRow(_t("panel.ventilation.bulk.field"), self.field_combo)

        self.mode_combo = QComboBox()
        for mode_key, label_key, _suf, _rng, _dec in self._MODES:
            self.mode_combo.addItem(_t(label_key), mode_key)
        form.addRow(_t("panel.ventilation.bulk.mode"), self.mode_combo)

        self.value_spin = QDoubleSpinBox()
        self.value_spin.setMaximumWidth(160)
        form.addRow(_t("panel.ventilation.bulk.value"), self.value_spin)
        self.mode_combo.currentIndexChanged.connect(self._sync_value_spin)
        self._sync_value_spin()

        hint = QLabel(_t("panel.ventilation.bulk.hint").format(n=n_selected))
        hint.setProperty("role", "muted")
        form.addRow(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("btn.apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _sync_value_spin(self) -> None:
        _key, _lbl, suffix, (lo, hi), dec = self._MODES[
            self.mode_combo.currentIndex()]
        self.value_spin.setDecimals(dec)
        self.value_spin.setRange(lo, hi)
        self.value_spin.setSuffix(suffix)

    def result_value(self) -> tuple[int, str, float]:
        """Возвращает (col, mode, value)."""
        col = self.field_combo.currentData()
        mode = self.mode_combo.currentData()
        return col, mode, self.value_spin.value()


class _VentFilterProxy(QSortFilterProxyModel):
    """Поиск + фильтры этаж / тип / зона для таблицы вентиляции.
    Зона = система вентиляции помещения (system_ventilation)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = ""
        self._level = ""
        self._type = ""
        self._zone = ""

    def set_text(self, t: str) -> None:
        self._text = (t or "").lower().strip()
        self.invalidateFilter()

    def set_level(self, v: str) -> None:
        self._level = "" if v == _t("filter.all") else v
        self.invalidateFilter()

    def set_type(self, v: str) -> None:
        self._type = "" if v == _t("filter.all") else v
        self.invalidateFilter()

    def set_zone(self, v: str) -> None:
        self._zone = "" if v == _t("filter.all") else v
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, _parent: QModelIndex) -> bool:
        sp = self.sourceModel().project.spaces[source_row]
        if self._level and (sp.level or "") != self._level:
            return False
        if self._type and (sp.room_type or "") != self._type:
            return False
        if self._zone and (sp.system_ventilation or "") != self._zone:
            return False
        if self._text:
            hay = " ".join((sp.number, sp.name, sp.level or "",
                            sp.room_type or "",
                            sp.system_ventilation or "")).lower()
            if self._text not in hay:
                return False
        return True


class VentilationPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.ventilation.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)
        head.addStretch(1)

        self.norms_btn = QPushButton(_t("panel.ventilation.btn_norms"))
        self.norms_btn.setCursor(Qt.PointingHandCursor)
        self.norms_btn.clicked.connect(self._open_norms)
        head.addWidget(self.norms_btn)

        self.bulk_btn = QPushButton(_t("panel.ventilation.btn_bulk"))
        self.bulk_btn.setCursor(Qt.PointingHandCursor)
        self.bulk_btn.clicked.connect(self._bulk_edit)
        head.addWidget(self.bulk_btn)

        self.run_btn = QPushButton(_t("panel.ventilation.btn_run"))
        self.run_btn.setProperty("role", "primary")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self._run)
        head.addWidget(self.run_btn)
        outer.addLayout(head)

        # Сводка-карточки
        self.summary_card = Card(_t("panel.ventilation.summary_card.title"),
                                  _t("panel.ventilation.summary_card.subtitle"))
        self.summary_lbl = QLabel(_t("common.not_yet"))
        self.summary_lbl.setProperty("role", "muted")
        self.summary_lbl.setTextFormat(Qt.RichText)
        self.summary_card.body().addWidget(self.summary_lbl)
        outer.addWidget(self.summary_card)

        # Поиск + фильтры этаж / тип / зона
        flt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self.search.setClearButtonEnabled(True)
        flt.addWidget(self.search, stretch=1)

        self._level_filter_lbl = QLabel(_t("panel.spaces.filter.level"))
        flt.addWidget(self._level_filter_lbl)
        self.level_filter = QComboBox()
        self.level_filter.setMinimumWidth(90)
        flt.addWidget(self.level_filter)

        self._type_filter_lbl = QLabel(_t("panel.spaces.filter.type"))
        flt.addWidget(self._type_filter_lbl)
        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(120)
        flt.addWidget(self.type_filter)

        self._zone_filter_lbl = QLabel(_t("panel.spaces.filter.zone"))
        flt.addWidget(self._zone_filter_lbl)
        self.zone_filter = QComboBox()
        self.zone_filter.setMinimumWidth(120)
        flt.addWidget(self.zone_filter)
        outer.addLayout(flt)

        # Таблица
        self.model = VentilationModel(project, bridge)
        self.proxy = _VentFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.set_text)
        self.level_filter.currentTextChanged.connect(self.proxy.set_level)
        self.type_filter.currentTextChanged.connect(self.proxy.set_type)
        self.zone_filter.currentTextChanged.connect(self.proxy.set_zone)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        # Поячейковое выделение (как в Excel и в разделе «Помещения»): нужно
        # для копирования/вставки/протяжки одиночных ячеек. При SelectRows клик
        # выделял всю строку, и вставка падала на нередактируемых колонках.
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        # Множественное выделение строк для групповой правки (Ctrl/Shift).
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        widths = [80, 200, 110, 130, 70, 100, 100, 90, 80, 56, 100]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        outer.addWidget(self.table, stretch=1)

        # Горячие клавиши «как в Excel»: копировать/вставить/заполнить вниз,
        # отменить/повторить. Контекст — таблица, чтобы не конфликтовать
        # с глобальными shortcut'ами главного окна.
        self._edit = TableEditBinder(self.table, self.proxy, self.model,
                                     self.bridge)
        # Delete — очистка (в 0) выделенных ячеек расхода (Excel-стиль).
        self._clear_sc = QShortcut(QKeySequence(Qt.Key_Delete), self.table)
        self._clear_sc.setContext(Qt.WidgetWithChildrenShortcut)
        self._clear_sc.activated.connect(self._clear_cells)

        bridge.dataLoaded.connect(self._refresh_summary)
        bridge.projectLoaded.connect(self._refresh_summary)
        bridge.ventilationDone.connect(self._refresh_summary)
        bridge.dataLoaded.connect(self._refresh_filter_options)
        bridge.projectLoaded.connect(self._refresh_filter_options)
        bridge.ventilationDone.connect(self._refresh_filter_options)
        # Ручная правка ячейки меняет суммарные расходы — обновляем карточку.
        self.model.dataChanged.connect(lambda *a: self._refresh_summary())
        self._refresh_summary()
        self._refresh_filter_options()

    def _run(self) -> None:
        if not self.project.spaces:
            return
        # Делегируем CalculationPanel — там async-обёртка
        from hvac.ui_qt.panels.calculation_panel import CalculationPanel
        parent = self.parent()
        while parent and not isinstance(parent, type(None)):
            # Пытаемся найти MainWindow и через него CalculationPanel
            if hasattr(parent, "_panels"):
                cp = parent._panels.get("calculation")
                if isinstance(cp, CalculationPanel):
                    cp._run_vent()  # noqa: SLF001
                    return
            parent = parent.parent()
        # Fallback: синхронно
        self.project.calculate_ventilation()

    # ---------- Редактор норм по типам помещений ----------
    def _open_norms(self) -> None:
        from hvac.ui_qt.widgets.ventilation_norms_dialog import (
            VentilationNormsDialog,
        )
        initial = None
        rows = self._selected_source_rows()
        if rows:
            initial = self.project.spaces[rows[0]].room_type
        dlg = VentilationNormsDialog(
            self.project, self.bridge, initial_type=initial, parent=self)
        dlg.exec()

    # ---------- Групповая правка ----------
    def _selected_source_rows(self) -> list[int]:
        """Строки модели-источника для выделенных в таблице помещений
        (через прокси, без дублей)."""
        sel = self.table.selectionModel()
        if sel is None:
            return []
        # selectedIndexes(), а не selectedRows(): при поячейковом выделении
        # «строка целиком» не выделяется, но строку каждой выбранной ячейки
        # учитываем для групповой правки.
        rows = {self.proxy.mapToSource(idx).row()
                for idx in sel.selectedIndexes()}
        return sorted(rows)

    def _bulk_edit(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(
                self, _t("panel.ventilation.bulk.title"),
                _t("panel.ventilation.bulk.no_selection"))
            return
        dlg = BulkVentDialog(len(rows), self)
        if dlg.exec() != QDialog.Accepted:
            return
        col, mode, value = dlg.result_value()
        n = self.model.apply_bulk(rows, col, mode, value)
        self.bridge.statusMessage.emit(
            _t("panel.ventilation.bulk.applied").format(n=n), 4000)

    # ---------- Буфер обмена / заполнение / отмена ----------
    # Тонкие делегаты к общему движку (имена сохранены — их зовут меню и тесты).
    def _paste(self) -> None:
        self._edit.paste()

    def _fill_down(self) -> None:
        self._edit.fill_down()

    def _undo(self) -> None:
        self._edit.undo()

    def _redo(self) -> None:
        self._edit.redo()

    def _copy(self) -> None:
        from hvac.ui_qt.widgets.table_clipboard import copy_selection_to_clipboard
        copy_selection_to_clipboard(self.table)

    def _clear_cells(self) -> None:
        """Очистка (в 0) выделенных ячеек редактируемых столбцов расхода —
        Delete или пункт меню «Очистить». Одна отменяемая операция; во время
        правки ячейки игнорируется."""
        if self.table.state() == QAbstractItemView.EditingState:
            return
        sel = self.table.selectionModel()
        if sel is None:
            return
        editable = self.model._EDITABLE_COLS
        edits = {(self.proxy.mapToSource(idx).row(), idx.column()): 0.0
                 for idx in sel.selectedIndexes()
                 if idx.column() in editable}
        n = self.model.set_cells(edits)
        if n:
            self.bridge.statusMessage.emit(
                _t("panel.ventilation.ctx.clear_done").format(n=n), 3000)

    def _show_context_menu(self, pos) -> None:
        if not self.project.spaces:
            return
        rows = self._selected_source_rows()
        sel = self.table.selectionModel()
        has_sel = bool(sel and sel.selectedIndexes())
        menu = QMenu(self)
        act_bulk = menu.addAction(_t("panel.ventilation.btn_bulk"))
        # Подменю нормативных пресетов расхода.
        preset_menu = menu.addMenu(_t("panel.ventilation.preset.menu"))
        preset_menu.setEnabled(bool(rows))
        preset_acts = {}
        for label_key, col, mode, value in _AIRFLOW_PRESETS:
            a = preset_menu.addAction(_t(label_key))
            preset_acts[a] = (col, mode, value)
        act_reset = menu.addAction(_t("panel.ventilation.ctx.reset"))
        # Подменю воздушного отопления/охлаждения (расход по нагрузке помещения).
        air_menu = menu.addMenu(_t("panel.sysworkspace.air.menu"))
        air_menu.setEnabled(bool(rows))
        air_map = {
            air_menu.addAction(_t("panel.sysworkspace.air.heat_on")): (True, None),
            air_menu.addAction(_t("panel.sysworkspace.air.cool_on")): (None, True),
            air_menu.addAction(_t("panel.sysworkspace.air.both_on")): (True, True),
            air_menu.addAction(_t("panel.sysworkspace.air.off")): (False, False),
        }
        menu.addSeparator()
        act_copy = menu.addAction(_t("panel.ventilation.ctx.copy"))
        act_paste = menu.addAction(_t("panel.ventilation.ctx.paste"))
        act_fill = menu.addAction(_t("panel.ventilation.ctx.fill_down"))
        act_clear = menu.addAction(_t("panel.ventilation.ctx.clear"))
        menu.addSeparator()
        act_undo = menu.addAction(_t("panel.ventilation.ctx.undo"))
        act_redo = menu.addAction(_t("panel.ventilation.ctx.redo"))

        act_bulk.setEnabled(bool(rows))
        act_reset.setEnabled(any(
            self.project.spaces[r].vent_user_modified for r in rows))
        act_copy.setEnabled(has_sel)
        act_fill.setEnabled(has_sel)
        act_clear.setEnabled(has_sel)
        act_undo.setEnabled(self.model.can_undo())
        act_redo.setEnabled(self.model.can_redo())

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen in preset_acts:
            col, mode, value = preset_acts[chosen]
            n = self.model.apply_bulk(rows, col, mode, value)
            self.bridge.statusMessage.emit(
                _t("panel.ventilation.preset.applied").format(n=n), 4000)
            return
        if chosen in air_map:
            heating, cooling = air_map[chosen]
            n = self.model.set_air_mode(rows, heating, cooling)
            self.bridge.statusMessage.emit(
                _t("panel.sysworkspace.air.status").format(n=n), 4000)
            return
        if chosen is act_bulk:
            self._bulk_edit()
        elif chosen is act_reset:
            n = self.model.reset_manual(rows)
            self.bridge.statusMessage.emit(
                _t("panel.ventilation.ctx.reset_done").format(n=n), 4000)
        elif chosen is act_copy:
            self._copy()
        elif chosen is act_paste:
            self._paste()
        elif chosen is act_fill:
            self._fill_down()
        elif chosen is act_clear:
            self._clear_cells()
        elif chosen is act_undo:
            self._undo()
        elif chosen is act_redo:
            self._redo()

    def _refresh_summary(self, *args: Any) -> None:
        spaces = self.project.spaces
        if not spaces:
            self.summary_lbl.setText(_t("common.empty_no_spaces"))
            return
        sup = sum(s.supply_m3h for s in spaces)
        exh = sum(s.exhaust_m3h for s in spaces)
        hood = sum(s.hood_m3h for s in spaces)
        if not (sup or exh):
            self.summary_lbl.setText(_t("panel.ventilation.summary_not_yet"))
            return
        diff = sup - exh - hood
        # Цифры форматируются вне строки чтобы пробельный разделитель
        # тысяч одинаково работал во всех локалях.
        def _fmt(v: float, plus: bool = False) -> str:
            fmt = f"{v:+,.0f}" if plus else f"{v:,.0f}"
            return fmt.replace(",", " ")
        self.summary_lbl.setText(
            _t("panel.ventilation.summary_html").format(
                sup=_fmt(sup), exh=_fmt(exh),
                hood=_fmt(hood), diff=_fmt(diff, plus=True))
        )

    def _refresh_filter_options(self, *args: Any) -> None:
        """Пересобирает опции фильтров (этаж/тип/зона) из текущих помещений,
        сохраняя выбор; этажи сортируются численно. Зона = система
        вентиляции (system_ventilation)."""
        spaces = self.project.spaces
        levels = sorted({s.level for s in spaces if s.level}, key=_floor_num)
        types = sorted({s.room_type for s in spaces if s.room_type})
        zones = sorted({s.system_ventilation for s in spaces
                        if s.system_ventilation})
        all_label = _t("filter.all")
        for combo, items in ((self.level_filter, levels),
                             (self.type_filter, types),
                             (self.zone_filter, zones)):
            current = combo.currentText() or all_label
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(items)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)
        # Сигналы были заблокированы — синхронизируем прокси вручную.
        self.proxy.set_level(self.level_filter.currentText())
        self.proxy.set_type(self.type_filter.currentText())
        self.proxy.set_zone(self.zone_filter.currentText())

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        self.title_lbl.setText(_t("panel.ventilation.title"))
        self.run_btn.setText(_t("panel.ventilation.btn_run"))
        self.norms_btn.setText(_t("panel.ventilation.btn_norms"))
        self.bulk_btn.setText(_t("panel.ventilation.btn_bulk"))
        self.summary_card.set_title(_t("panel.ventilation.summary_card.title"))
        self.summary_card.set_subtitle(
            _t("panel.ventilation.summary_card.subtitle"))
        self.search.setPlaceholderText(_t("btn.search.ph"))
        self._level_filter_lbl.setText(_t("panel.spaces.filter.level"))
        self._type_filter_lbl.setText(_t("panel.spaces.filter.type"))
        self._zone_filter_lbl.setText(_t("panel.spaces.filter.zone"))
        self._refresh_filter_options()
        self.model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.model.columnCount() - 1)
        self._refresh_summary()
