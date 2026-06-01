# -*- coding: utf-8 -*-
"""ConstructionsPanel — каталог конструкций.

Колонки: Категория, Семейство, Тип, δ мм, U, R, R_норм, SHGC,
Использовано (N эл. / Σ площ.), Примечание.

Возможности:
- Inline-правка U и SHGC (двойной клик)
- Bulk-edit: выделить несколько строк → ввести U
- Применение пресета к выделенным строкам
- Редактор слоёв (двойной клик по R)
- Подсветка: U выше типичного для категории — красный; R ниже R_норм — оранжевый фон
- Удаление неиспользуемых
- Импорт/экспорт каталога в JSON
"""
from __future__ import annotations

from typing import Any, Callable, List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from hvac.catalogs.constructions import (
    DEFAULT_U_BY_CATEGORY, r_norm_for,
)
from hvac.catalogs.construction_presets import (
    PRESETS, apply_preset, presets_for_category,
)
from hvac.i18n import on_language_change, t as _t
from hvac.models import Construction
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.widgets.layers_editor import LayersEditor
from hvac.ui_qt.widgets.table_edit import (
    EditableTableModelMixin, TableEditBinder,
)


# Коэффициент «подозрительно высокого» U — выше типичного × этот фактор
_HIGH_U_FACTOR = 2.0


_HEADER_KEYS = (
    "panel.constructions.col.category",
    "panel.constructions.col.family",
    "panel.constructions.col.type",
    "panel.constructions.col.th",
    "panel.constructions.col.u",
    "panel.constructions.col.r",
    "panel.constructions.col.rnorm",
    "panel.constructions.col.shgc",
    "panel.constructions.col.used",
    "panel.constructions.col.area",
    "panel.constructions.col.note",
)


class ConstructionsModel(EditableTableModelMixin, QAbstractTableModel):
    COL_CATEGORY = 0
    COL_FAMILY = 1
    COL_TYPE = 2
    COL_TH = 3
    COL_U = 4
    COL_R = 5
    COL_RNORM = 6
    COL_SHGC = 7
    COL_USED = 8
    COL_AREA = 9
    COL_NOTE = 10
    EDITABLE = {COL_U, COL_SHGC, COL_NOTE}
    _EDITABLE_COLS = EDITABLE
    # Поля для снимков undo/redo (правка U сбрасывает слои и дописывает note).
    _SNAP_FIELDS = ("u_value", "shgc", "note", "thickness_mm")

    def __init__(self, project: HVACProject, bridge: ProjectBridge):
        super().__init__()
        self.project = project
        self.bridge = bridge
        self._items: List[Construction] = []
        self._usage: dict = {}
        self._item_keys: List[str] = []
        self._init_edit_history()
        # Полная перезагрузка данных обнуляет историю; точечная правка U/SHGC
        # (constructionsChanged) — нет: _reload чистит историю только если
        # изменился состав/порядок каталога (см. ниже).
        bridge.dataLoaded.connect(self._reload)
        bridge.projectLoaded.connect(self._reload)
        bridge.constructionsChanged.connect(self._reload)
        self._reload()

    def _reload(self, *args: Any) -> None:
        new_items = sorted(
            self.project.constructions.values(),
            key=lambda c: (c.category, c.family or "", c.type_name or ""),
        )
        new_keys = [c.key for c in new_items]
        # Снимки undo адресуют строки по индексу: если состав или порядок
        # каталога изменился (загрузка проекта, импорт, удаление) — история
        # недействительна. Если изменились лишь значения (U/SHGC/note) —
        # ключи те же, порядок тот же, историю сохраняем.
        if new_keys != self._item_keys:
            self.clear_edit_history()
        self.beginResetModel()
        self._items = new_items
        self._item_keys = new_keys
        self._usage = self.project.construction_usage()
        self.endResetModel()

    def construction_at(self, row: int) -> Construction:
        return self._items[row]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_HEADER_KEYS)

    def headerData(self, section, orient, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orient == Qt.Horizontal:
            return _t(_HEADER_KEYS[section])
        return None

    def retranslate(self) -> None:
        self.headerDataChanged.emit(
            Qt.Horizontal, 0, self.columnCount() - 1)

    def flags(self, index):
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() in self.EDITABLE:
            base |= Qt.ItemIsEditable
        return base

    def _r_norm(self, c: Construction) -> float:
        p = self.project.params
        return r_norm_for(
            c.category, p.gsop_18 or 0.0,
            building_type=self._building_type(),
            thermal_norm=getattr(p, "thermal_norm", "KMK_UZ"),
            n_floors=self._n_floors(),
        )

    def _building_type(self) -> str:
        """Тип здания для выбора категории нормы (по составу помещений)."""
        from hvac.energy import detect_building_type
        return detect_building_type(self.project)

    def _n_floors(self) -> int:
        """Число этажей (по уникальным уровням) — выбор res_low/res_high КМК."""
        return len({sp.level for sp in self.project.spaces if sp.level}) or 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        c = self._items[index.row()]
        col = index.column()
        usage = self._usage.get(c.key, {})

        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == self.COL_CATEGORY:
                return c.category
            if col == self.COL_FAMILY:
                return c.family or ""
            if col == self.COL_TYPE:
                return c.type_name or ""
            if col == self.COL_TH:
                return f"{c.thickness_mm:.0f}" if c.thickness_mm else ""
            if col == self.COL_U:
                if role == Qt.DisplayRole:
                    return f"{c.u_value:.3f}" if c.u_value else ""
                return c.u_value
            if col == self.COL_R:
                if c.layers:
                    r = c.total_r_m2k_w()
                    return f"{r:.3f}" if r else ""
                if c.u_value > 0:
                    return f"{1.0 / c.u_value:.3f}"
                return ""
            if col == self.COL_RNORM:
                rn = self._r_norm(c)
                return f"{rn:.2f}" if rn else ""
            if col == self.COL_SHGC:
                if role == Qt.DisplayRole:
                    return f"{c.shgc:.2f}" if c.shgc else ""
                return c.shgc
            if col == self.COL_USED:
                return str(usage.get("n_elements", 0))
            if col == self.COL_AREA:
                a = usage.get("area_m2", 0.0)
                return f"{a:.1f}" if a else ""
            if col == self.COL_NOTE:
                return c.note or ""

        if role == Qt.TextAlignmentRole and col in (
                self.COL_TH, self.COL_U, self.COL_R, self.COL_RNORM,
                self.COL_SHGC, self.COL_USED, self.COL_AREA):
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if role == Qt.BackgroundRole:
            # R ниже нормы → оранжевый фон в колонке R
            if col == self.COL_R and c.u_value > 0:
                rn = self._r_norm(c)
                r_fact = c.total_r_m2k_w() if c.layers else 1.0 / c.u_value
                if rn > 0 and r_fact > 0 and r_fact < rn:
                    return QBrush(QColor(255, 200, 120, 90))
            # Аномально высокий U → красный фон
            if col == self.COL_U:
                default_u = DEFAULT_U_BY_CATEGORY.get(c.category, 0)
                if default_u and c.u_value > default_u * _HIGH_U_FACTOR:
                    return QBrush(QColor(255, 130, 130, 90))
            # Конструкция не используется → серый фон строки
            if usage.get("n_elements", 0) == 0:
                return QBrush(QColor(160, 160, 160, 40))

        if role == Qt.ToolTipRole:
            if col == self.COL_R and c.layers:
                return self._layers_tooltip(c)
            if col == self.COL_RNORM:
                rn = self._r_norm(c)
                if rn:
                    return _t("panel.constructions.tt.rnorm").format(
                        gsop=self.project.params.gsop_18)
        return None

    @staticmethod
    def _layers_tooltip(c: Construction) -> str:
        lines = [_t("panel.constructions.tt.layers")]
        for i, l in enumerate(c.layers, 1):
            if l.r_m2k_w > 0 and not l.lambda_w_mk:
                lines.append(_t("panel.constructions.tt.layer_r").format(
                    i=i, material=l.material, r=l.r_m2k_w))
            else:
                lines.append(_t("panel.constructions.tt.layer_full").format(
                    i=i, material=l.material,
                    th=l.thickness_mm, lam=l.lambda_w_mk))
        return "<br>".join(lines)

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        return self.commit_cell(index.row(), index.column(), value)

    # ---- Хуки EditableTableModelMixin ----
    def _snapshot_row(self, row: int) -> dict:
        c = self._items[row]
        snap = {f: getattr(c, f) for f in self._SNAP_FIELDS}
        snap["layers"] = list(c.layers)
        return snap

    def _restore_row(self, row: int, snap: dict) -> None:
        c = self._items[row]
        for f, v in snap.items():
            if f == "layers":
                c.layers = list(v)
            else:
                setattr(c, f, v)

    def _apply_cell(self, row: int, col: int, raw) -> bool:
        c = self._items[row]
        try:
            if col == self.COL_U:
                c.u_value = float(raw)
                # Ручная правка U перекрывает слои — помечаем в note.
                if c.layers:
                    c.note = (c.note or "") + _t("panel.constructions.note_manual_u")
                    c.layers = []
            elif col == self.COL_SHGC:
                c.shgc = float(raw)
            elif col == self.COL_NOTE:
                c.note = str(raw)
            else:
                return False
        except (TypeError, ValueError):
            return False
        return True

    def _cell_edit_value(self, row: int, col: int):
        c = self._items[row]
        return {self.COL_U: c.u_value, self.COL_SHGC: c.shgc,
                self.COL_NOTE: c.note}[col]

    def _after_change(self, rows) -> None:
        # Правка U в каталоге должна СРАЗУ доходить до элементов: el.u_value
        # копируется из каталога только в apply_constructions(), иначе проверка
        # конденсации / повторный подбор труб используют устаревший U.
        self.project.apply_constructions()
        # Обновляем зависимые панели (расчёт использует U). Триггерит _reload,
        # но он сохраняет историю, т.к. состав каталога не меняется.
        self.project.emit("constructions_changed")

    # Bulk-операции (отменяемые через единый _commit)
    def bulk_set_u(self, rows: List[int], u_value: float) -> int:
        def mutate(rs):
            for row in rs:
                c = self._items[row]
                c.u_value = u_value
                if c.layers:
                    c.layers = []
        return self._commit(rows, mutate)

    def bulk_apply_preset(self, rows: List[int], preset_name: str) -> int:
        def mutate(rs):
            for row in rs:
                apply_preset(self._items[row], preset_name)
        return self._commit(rows, mutate)


# ===========================================================================
class PresetDialog(QDialog):
    """Выбор пресета — фильтр по категории + просмотр сводки."""

    def __init__(self, default_category: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.constructions.dlg.preset_title"))
        self.resize(560, 320)

        form = QFormLayout(self)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(
            [_t("panel.constructions.dlg.all")]
            + sorted({p.category for p in PRESETS.values()}))
        if default_category:
            idx = self.cat_combo.findText(default_category)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)
        form.addRow(_t("panel.constructions.dlg.category"), self.cat_combo)

        self.preset_combo = QComboBox()
        form.addRow(_t("panel.constructions.dlg.preset"), self.preset_combo)

        self.desc_lbl = QLabel()
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setProperty("role", "muted")
        form.addRow(self.desc_lbl)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

        self.cat_combo.currentTextChanged.connect(self._refresh_presets)
        self.preset_combo.currentTextChanged.connect(self._refresh_desc)
        self._refresh_presets(self.cat_combo.currentText())

    def _refresh_presets(self, category: str) -> None:
        self.preset_combo.clear()
        if category == _t("panel.constructions.dlg.all"):
            names = list(PRESETS.keys())
        else:
            names = [p.name for p in presets_for_category(category)]
        self.preset_combo.addItems(names)
        self._refresh_desc(self.preset_combo.currentText())

    def _refresh_desc(self, name: str) -> None:
        p = PRESETS.get(name)
        if not p:
            self.desc_lbl.setText("")
            return
        self.desc_lbl.setText(_t("panel.constructions.dlg.preset_desc").format(
            description=p.description, category=p.category, n=len(p.layers)))

    def selected_preset(self) -> str:
        return self.preset_combo.currentText()


# ===========================================================================
class ConstructionsPanel(QWidget):
    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._translators: List[Callable[[], None]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ===== Заголовок =====
        head = QHBoxLayout()
        self._h = QLabel(_t("panel.constructions.title"))
        self._h.setProperty("role", "h1")
        head.addWidget(self._h)
        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("role", "muted")
        head.addSpacing(12)
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        outer.addLayout(head)

        self._sub = QLabel(_t("panel.constructions.hint"))
        self._sub.setTextFormat(Qt.RichText)
        self._sub.setWordWrap(True)
        self._sub.setProperty("role", "muted")
        outer.addWidget(self._sub)

        # ===== Тулбар =====
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("panel.constructions.search_ph"))
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, stretch=1)

        self.cat_filter = QComboBox()
        self.cat_filter.addItem(_t("panel.constructions.filter_all"), "")
        for cat in ("Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол"):
            self.cat_filter.addItem(cat, cat)
        bar.addWidget(self.cat_filter)

        self._buttons: List[tuple[QPushButton, str]] = []
        for key, slot in [
            ("panel.constructions.btn_preset",  self._apply_preset),
            ("panel.constructions.btn_bulk_u",  self._bulk_edit_u),
            ("panel.constructions.btn_layers",  self._edit_layers),
            ("panel.constructions.btn_remove",  self._remove_unused),
            ("panel.constructions.btn_export",  self._export_catalog),
            ("panel.constructions.btn_import",  self._import_catalog),
        ]:
            b = QPushButton(_t(key))
            b.clicked.connect(slot)
            bar.addWidget(b)
            self._buttons.append((b, key))
        outer.addLayout(bar)

        # ===== Таблица =====
        self.model = ConstructionsModel(project, bridge)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.cat_filter.currentTextChanged.connect(self._apply_cat_filter)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        widths = [120, 170, 230, 60, 70, 70, 70, 60, 80, 100, 260]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.table.doubleClicked.connect(self._on_double_click)
        # Excel-горячие клавиши: Ctrl+C/V/D, Ctrl+Z/Y (буфер/fill-down/undo).
        self._edit = TableEditBinder(self.table, self.proxy, self.model,
                                     self.bridge)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        outer.addWidget(self.table, stretch=1)

        self.model.modelReset.connect(self._refresh_count)
        bridge.dataLoaded.connect(self._refresh_count)
        bridge.projectLoaded.connect(self._refresh_count)
        bridge.constructionsChanged.connect(self._refresh_count)
        bridge.calculationDone.connect(self.model._reload)  # обновить использ.
        on_language_change(lambda _lang: self.retranslate_ui())
        self._refresh_count()

    # ---------- helpers ----------
    def _apply_cat_filter(self, *_: Any) -> None:
        text = self.cat_filter.currentData() or ""
        # Простейшая реализация — фильтруем строку по колонке "Категория"
        self.proxy.setFilterKeyColumn(ConstructionsModel.COL_CATEGORY if text else -1)
        self.proxy.setFilterFixedString(text if text else self.search.text())

    def _refresh_count(self, *args: Any) -> None:
        total = len(self.project.constructions)
        usage = self.project.construction_usage()
        used = len(usage)
        unused = total - used
        if total:
            self.count_lbl.setText(_t("panel.constructions.count").format(
                total=total, used=used, unused=unused))
        else:
            self.count_lbl.setText(_t("panel.constructions.count_empty"))

    def retranslate_ui(self) -> None:
        self._h.setText(_t("panel.constructions.title"))
        self._sub.setText(_t("panel.constructions.hint"))
        self.search.setPlaceholderText(_t("panel.constructions.search_ph"))
        # Сохраняем текущий userData фильтра, перезаполняем
        current_data = self.cat_filter.currentData()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem(_t("panel.constructions.filter_all"), "")
        for cat in ("Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол"):
            self.cat_filter.addItem(cat, cat)
        for i in range(self.cat_filter.count()):
            if self.cat_filter.itemData(i) == current_data:
                self.cat_filter.setCurrentIndex(i)
                break
        self.cat_filter.blockSignals(False)
        for btn, key in self._buttons:
            btn.setText(_t(key))
        self.model.retranslate()
        self._refresh_count()

    def _selected_source_rows(self) -> List[int]:
        rows = set()
        for idx in self.table.selectionModel().selectedRows():
            rows.add(self.proxy.mapToSource(idx).row())
        return sorted(rows)

    def _show_context_menu(self, pos) -> None:
        if not self.project.constructions:
            return
        sel = self.table.selectionModel()
        has_sel = bool(sel and sel.selectedIndexes())
        rows = self._selected_source_rows()
        menu = QMenu(self)
        act_bulk = menu.addAction(_t("panel.constructions.btn_bulk_u"))
        act_preset = menu.addAction(_t("panel.constructions.btn_preset"))
        menu.addSeparator()
        act_copy = menu.addAction(_t("tableedit.ctx.copy"))
        act_paste = menu.addAction(_t("tableedit.ctx.paste"))
        act_fill = menu.addAction(_t("tableedit.ctx.fill_down"))
        menu.addSeparator()
        act_undo = menu.addAction(_t("tableedit.ctx.undo"))
        act_redo = menu.addAction(_t("tableedit.ctx.redo"))
        act_bulk.setEnabled(bool(rows))
        act_preset.setEnabled(bool(rows))
        act_copy.setEnabled(has_sel)
        act_fill.setEnabled(has_sel)
        act_undo.setEnabled(self.model.can_undo())
        act_redo.setEnabled(self.model.can_redo())
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_bulk:
            self._bulk_edit_u()
        elif chosen is act_preset:
            self._apply_preset()
        elif chosen is act_copy:
            from hvac.ui_qt.widgets.table_clipboard import (
                copy_selection_to_clipboard,
            )
            copy_selection_to_clipboard(self.table)
        elif chosen is act_paste:
            self._edit.paste()
        elif chosen is act_fill:
            self._edit.fill_down()
        elif chosen is act_undo:
            self._edit.undo()
        elif chosen is act_redo:
            self._edit.redo()

    # ---------- действия ----------
    def _on_double_click(self, idx) -> None:
        col = idx.column()
        if col == ConstructionsModel.COL_R:
            self._edit_layers()

    def _edit_layers(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(
                self, _t("panel.constructions.title.layers"),
                _t("panel.constructions.msg.layers_pick"))
            return
        if len(rows) > 1:
            QMessageBox.information(
                self, _t("panel.constructions.title.layers"),
                _t("panel.constructions.msg.layers_one"))
            return
        c = self.model.construction_at(rows[0])
        dlg = LayersEditor(c, self)
        if dlg.exec() == QDialog.Accepted:
            c.layers = dlg.get_layers()
            c.recompute_u_from_layers()
            self.model._reload()
            self.project.apply_constructions()   # пересчитанный U → элементы
            self.bridge.dirtyChanged.emit(True)
            self.project.emit("constructions_changed")

    def _apply_preset(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(
                self, _t("panel.constructions.title.preset"),
                _t("panel.constructions.msg.preset_pick"))
            return
        default_cat = self.model.construction_at(rows[0]).category
        dlg = PresetDialog(default_cat, self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.selected_preset()
        if not name:
            return
        n = self.model.bulk_apply_preset(rows, name)
        self.bridge.statusMessage.emit(
            _t("panel.constructions.status.preset").format(name=name, n=n),
            4000)

    def _bulk_edit_u(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(
                self, _t("panel.constructions.title.bulk"),
                _t("panel.constructions.msg.bulk_pick"))
            return
        value, ok = QInputDialog.getDouble(
            self, _t("panel.constructions.title.bulk"),
            _t("panel.constructions.msg.bulk_prompt").format(n=len(rows)),
            0.5, 0.05, 10.0, 3)
        if not ok:
            return
        n = self.model.bulk_set_u(rows, value)
        self.bridge.statusMessage.emit(
            _t("panel.constructions.status.bulk").format(u=value, n=n),
            4000)

    def _remove_unused(self) -> None:
        usage = self.project.construction_usage()
        unused_count = sum(1 for k in self.project.constructions
                           if k not in usage)
        if not unused_count:
            QMessageBox.information(
                self, _t("panel.constructions.title.cleanup"),
                _t("panel.constructions.msg.unused_none"))
            return
        ans = QMessageBox.question(
            self, _t("panel.constructions.title.remove"),
            _t("panel.constructions.msg.remove_ask").format(n=unused_count),
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        n = self.project.remove_unused_constructions()
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.constructions.status.removed").format(n=n), 4000)

    def _export_catalog(self) -> None:
        path, _f = QFileDialog.getSaveFileName(
            self, _t("panel.constructions.title.export"),
            "constructions.json", "JSON (*.json)")
        if not path:
            return
        n = self.project.export_constructions_json(path)
        self.bridge.statusMessage.emit(
            _t("panel.constructions.status.exported").format(n=n, path=path),
            4000)

    def _import_catalog(self) -> None:
        path, _f = QFileDialog.getOpenFileName(
            self, _t("panel.constructions.title.import"), "", "JSON (*.json)")
        if not path:
            return
        merge_label = _t("panel.constructions.import.merge")
        update_label = _t("panel.constructions.import.update")
        replace_label = _t("panel.constructions.import.replace")
        strategy, ok = QInputDialog.getItem(
            self, _t("panel.constructions.title.import_strategy"),
            _t("panel.constructions.msg.import_strategy"),
            [merge_label, update_label, replace_label],
            0, editable=False)
        if not ok:
            return
        key = strategy.split(" — ", 1)[0]
        try:
            stats = self.project.import_constructions_json(path, strategy=key)
        except Exception as e:
            QMessageBox.critical(
                self, _t("panel.constructions.title.import_err"), str(e))
            return
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.constructions.status.imported").format(
                added=stats['added'], updated=stats['updated'],
                skipped=stats['skipped']),
            5000)
