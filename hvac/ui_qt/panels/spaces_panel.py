# -*- coding: utf-8 -*-
"""SpacesPanel — таблица помещений с фильтрами, поиском, inline-edit.

Главный экран приложения: таблица всех помещений на всю ширину с цветовой
индикацией аномалий и Excel-режимом (поячейковое выделение, копирование/
вставка/протяжка столбца). Детали выделенного помещения (свойства +
ограждения) открываются в отдельном окне SpaceDetailWindow по кнопке
«Свойства…».
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QStyledItemDelegate, QTableView, QVBoxLayout, QWidget,
)

from hvac.catalogs.room_types import (
    apply_room_type_defaults, get_all_room_types,
)
from hvac.i18n import t as _t
from hvac.models import Space
from hvac.project import HVACProject
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.panels.boundaries_panel import BoundariesPanel
from hvac.ui_qt.panels.properties_panel import PropertiesPanel
from hvac.ui_qt.theme import tokens
from hvac.ui_qt.widgets.space_dialog import (
    BuildingTemplateDialog, SpaceDialog, SpaceEditDialog, SpaceEditResult,
)
from hvac.ui_qt.widgets.table_edit import (
    EditableTableModelMixin, TableEditBinder,
)


# Ключи перевода для заголовков колонок. Объявлены модульно, чтобы
# SpacesTableModel.headerData мог отдавать актуальное значение текущего
# языка без хранения title в самой колонке.
_COLUMN_TITLE_KEYS = [
    "panel.spaces.col.number",
    "panel.spaces.col.name",
    "panel.spaces.col.level",
    "panel.spaces.col.type",
    "panel.spaces.col.area",
    "panel.spaces.col.volume",
    "panel.spaces.col.t_heat",
    "panel.spaces.col.t_cool",
    "panel.spaces.col.occup",
    "panel.spaces.col.light",
    "panel.spaces.col.equip",
    "panel.spaces.col.q_heat",
    "panel.spaces.col.q_cool",
    "panel.spaces.col.density",
    "panel.spaces.col.zone",
]


# ===========================================================================
# Модель таблицы
# ===========================================================================


@dataclass
class Column:
    title_key: str           # i18n key — заголовок берётся через _t() в headerData
    key: str
    width: int
    editable: bool = False
    fmt: Optional[Callable[[Any], str]] = None
    getter: Optional[Callable[[Space], Any]] = None
    setter: Optional[Callable[[Space, Any], None]] = None
    align: int = int(Qt.AlignLeft | Qt.AlignVCenter)


def _fmt_num(v: float, digits: int = 1) -> str:
    if v is None:
        return ""
    return f"{v:.{digits}f}"


def _q_density(sp: Space) -> float:
    """Удельная теплопотеря Вт/м² — критерий аномалии."""
    if sp.area_m2 <= 0:
        return 0.0
    return sp.heat_loss_w / sp.area_m2


class SpacesTableModel(EditableTableModelMixin, QAbstractTableModel):
    """Модель таблицы поверх project.spaces.

    Реактивна на сигналы bridge — после dataLoaded / calculationDone
    модель полностью перевыпускается через layoutChanged.
    """

    # Поля для снимков undo/redo: редактируемые + производные от смены типа
    # (apply_room_type_defaults меняет температуры, людей, освещение и т.д.)
    # + системы + флаг ручной правки.
    _SNAP_FIELDS = (
        "number", "name", "level", "area_m2", "volume_m3", "height_m",
        "room_type", "t_in_heat", "t_in_cool", "occupancy_people",
        "lighting_w_m2", "equipment_w_m2", "ach_inf",
        "is_corner", "has_floor_to_ground", "has_roof", "is_top_floor",
        "floor_over_unheated_n",
        "system_heating", "system_cooling", "system_ventilation",
        "user_modified",
    )

    COLUMNS: List[Column] = [
        Column("panel.spaces.col.number",   "number",         80, editable=True,
               align=int(Qt.AlignLeft | Qt.AlignVCenter)),
        Column("panel.spaces.col.name",     "name",          220, editable=True,
               align=int(Qt.AlignLeft | Qt.AlignVCenter)),
        Column("panel.spaces.col.level",    "level",         110, editable=True),
        Column("panel.spaces.col.type",     "room_type",     150, editable=True),
        Column("panel.spaces.col.area",     "area_m2",        80, editable=True,
               fmt=lambda v: _fmt_num(v, 1),
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.volume",   "volume_m3",      90, editable=True,
               fmt=lambda v: _fmt_num(v, 1),
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.t_heat",   "t_in_heat",      70, editable=True,
               fmt=lambda v: f"{v:.1f}",
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.t_cool",   "t_in_cool",      70, editable=True,
               fmt=lambda v: f"{v:.1f}",
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.occup",    "occupancy_people", 70, editable=True,
               fmt=lambda v: _fmt_num(v, 1),
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.light",    "lighting_w_m2",  90, editable=True,
               fmt=lambda v: _fmt_num(v, 1),
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.equip",    "equipment_w_m2", 90, editable=True,
               fmt=lambda v: _fmt_num(v, 1),
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.q_heat",   "heat_loss_w",   110,
               fmt=lambda v: f"{(v or 0)/1000:.2f}",
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.q_cool",   "heat_gain_w",   110,
               fmt=lambda v: f"{(v or 0)/1000:.2f}",
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.density",  "_q_density",     80,
               fmt=lambda v: _fmt_num(v, 0),
               getter=_q_density,
               align=int(Qt.AlignRight | Qt.AlignVCenter)),
        Column("panel.spaces.col.zone",     "system_heating",130, editable=True),
    ]

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge
        self._init_edit_history()
        self._EDITABLE_COLS = {i for i, c in enumerate(self.COLUMNS)
                               if c.editable}
        # Сабскрайбимся на события, которые меняют содержимое
        bridge.dataLoaded.connect(self._full_reset)
        bridge.projectLoaded.connect(self._full_reset)
        bridge.calculationDone.connect(self._refresh_results)
        bridge.ventilationDone.connect(self._refresh_results)

    # ---- Qt API ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.project.spaces)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            # Резолвим через i18n каждый раз — заголовки переключаются вместе
            # с языком без пересоздания модели.
            return _t(self.COLUMNS[section].title_key)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if self.COLUMNS[index.column()].editable:
            base |= Qt.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        sp = self.project.spaces[index.row()]
        col = self.COLUMNS[index.column()]

        if role in (Qt.DisplayRole, Qt.EditRole):
            value = col.getter(sp) if col.getter else getattr(sp, col.key, "")
            if role == Qt.EditRole:
                return value
            return col.fmt(value) if col.fmt else (str(value) if value != "" else "")

        if role == Qt.TextAlignmentRole:
            return col.align

        if role == Qt.BackgroundRole:
            t = tokens()
            density = _q_density(sp)
            # Подсветка аномалий: >100 Вт/м² зимой
            if density > 100:
                return QBrush(QColor(t["danger"]).darker(280))
            if density > 70:
                return QBrush(QColor(t["warning"]).darker(280))
            return None

        if role == Qt.ForegroundRole:
            if sp.user_modified and index.column() == 3:
                return QBrush(QColor(tokens()["accent"]))
            return None

        if role == Qt.ToolTipRole:
            mod = _t("panel.spaces.tooltip.modified") if sp.user_modified else ""
            return _t("panel.spaces.tooltip").format(
                number=sp.number, name=sp.name,
                level=sp.level, type=sp.room_type, mod=mod)

        return None

    def setData(self, index: QModelIndex, value: Any,
                role: int = Qt.EditRole) -> bool:
        if role != Qt.EditRole or not index.isValid():
            return False
        return self.commit_cell(index.row(), index.column(), value)

    # ---- Хуки EditableTableModelMixin ----
    def _snapshot_row(self, row: int) -> dict:
        sp = self.project.spaces[row]
        return {f: getattr(sp, f) for f in self._SNAP_FIELDS}

    def _restore_row(self, row: int, snap: dict) -> None:
        sp = self.project.spaces[row]
        for f, v in snap.items():
            setattr(sp, f, v)

    # Числовые поля помещения, которые можно править массово (групповая
    # правка), даже если у них нет своей колонки в таблице.
    _NUMERIC_FIELDS = frozenset({
        "t_in_heat", "t_in_cool", "occupancy_people",
        "lighting_w_m2", "equipment_w_m2", "ach_inf",
    })

    def _write_field(self, sp, key: str, raw) -> bool:
        """Единая точка записи поля помещения с приведением типа и побочными
        эффектами. Используется и инлайн-правкой, и групповой. Возвращает
        False при недопустимом значении (вызывающий откатывает правку)."""
        if key == "room_type":
            sp.room_type = str(raw)
            apply_room_type_defaults(sp)
        elif key == "system_heating":
            sp.system_heating = str(raw)
        elif key in ("number", "name", "level"):
            # Текстовые поля — идентификация/расположение помещения.
            # Номер не должен становиться пустым (он используется в поиске
            # и заголовках), остальное допускаем любым текстом.
            text = str(raw).strip()
            if key == "number" and not text:
                return False
            setattr(sp, key, text)
        elif key == "area_m2":
            val = float(raw)
            if val < 0:
                return False
            sp.area_m2 = val
            # Держим геометрию согласованной: при фиксированной высоте
            # объём = площадь × высота.
            if sp.height_m > 0:
                sp.volume_m3 = val * sp.height_m
        elif key == "volume_m3":
            val = float(raw)
            if val < 0:
                return False
            sp.volume_m3 = val
            # При фиксированной площади пересчитываем высоту.
            if sp.area_m2 > 0:
                sp.height_m = val / sp.area_m2
        elif key in self._NUMERIC_FIELDS:
            val = float(raw)
            if val < 0:
                return False
            setattr(sp, key, val)
        else:
            setattr(sp, key, raw)
        sp.user_modified = True
        return True

    def _apply_cell(self, row: int, col: int, raw) -> bool:
        col_def = self.COLUMNS[col]
        if not col_def.editable:
            return False
        try:
            return self._write_field(self.project.spaces[row], col_def.key, raw)
        except (TypeError, ValueError):
            return False

    def bulk_set_field(self, rows: List[int], field_key: str, value) -> int:
        """Массовая правка одного поля у выбранных помещений (отменяемая).
        Поле может быть как колонкой таблицы, так и любым числовым/текстовым
        полем помещения (t лето, люди, освещение и т.д.)."""
        def mutate(rs):
            for r in rs:
                try:
                    self._write_field(self.project.spaces[r], field_key, value)
                except (TypeError, ValueError):
                    pass
        return self._commit(rows, mutate)

    def _cell_edit_value(self, row: int, col: int):
        return getattr(self.project.spaces[row], self.COLUMNS[col].key)

    # ---- Внутреннее ----
    def _full_reset(self, *args: Any) -> None:
        self.clear_edit_history()
        self.beginResetModel()
        self.endResetModel()

    def _refresh_results(self, *args: Any) -> None:
        if not self.project.spaces:
            return
        top = self.index(0, 0)
        bot = self.index(len(self.project.spaces) - 1, self.columnCount() - 1)
        self.dataChanged.emit(top, bot,
                              [Qt.DisplayRole, Qt.BackgroundRole])

    def space_at(self, row: int) -> Optional[Space]:
        if 0 <= row < len(self.project.spaces):
            return self.project.spaces[row]
        return None


# ===========================================================================
# Прокси-модель: поиск + фильтры
# ===========================================================================


class SpacesFilterProxy(QSortFilterProxyModel):
    """Текстовый поиск + фильтры по этажу/типу/зоне."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = ""
        self._level = ""
        self._type = ""
        self._zone = ""
        self.setDynamicSortFilter(True)

    def set_text(self, t: str) -> None:
        self._text = t.lower().strip()
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

    def filterAcceptsRow(self, source_row: int,
                         _parent: QModelIndex) -> bool:
        model = self.sourceModel()
        sp = model.space_at(source_row)
        if sp is None:
            return False
        if self._level and sp.level != self._level:
            return False
        if self._type and sp.room_type != self._type:
            return False
        if self._zone and (sp.system_heating or "") != self._zone:
            return False
        if self._text:
            hay = " ".join((sp.number, sp.name, sp.level,
                            sp.room_type, sp.system_heating or "")).lower()
            if self._text not in hay:
                return False
        return True


# ===========================================================================
# Делегаты для inline-edit
# ===========================================================================


class ComboDelegate(QStyledItemDelegate):
    """Выпадающий список значений в ячейке."""

    def __init__(self, options_provider: Callable[[], List[str]],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._provider = options_provider

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(True)   # позволяем ввести новое значение
        combo.addItems(self._provider())
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        value = index.model().data(index, Qt.EditRole) or ""
        editor.setCurrentText(str(value))

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


class NumberDelegate(QStyledItemDelegate):
    """Числовой редактор ячейки с заданным диапазоном/точностью.

    Нужен, потому что стандартный редактор Qt для float — QDoubleSpinBox с
    диапазоном 0…99.99, который «обрезал» бы площади/объёмы.
    """

    def __init__(self, minimum: float, maximum: float, decimals: int,
                 suffix: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._dec = decimals
        self._suffix = suffix

    def createEditor(self, parent, option, index):
        spin = QDoubleSpinBox(parent)
        spin.setRange(self._min, self._max)
        spin.setDecimals(self._dec)
        if self._suffix:
            spin.setSuffix(self._suffix)
        return spin

    def setEditorData(self, editor: QDoubleSpinBox, index: QModelIndex):
        try:
            editor.setValue(float(index.model().data(index, Qt.EditRole) or 0.0))
        except (TypeError, ValueError):
            editor.setValue(0.0)

    def setModelData(self, editor: QDoubleSpinBox, model, index):
        editor.interpretText()
        model.setData(index, editor.value(), Qt.EditRole)


# ===========================================================================
# Диалог групповой правки
# ===========================================================================


class SpacesBulkDialog(QDialog):
    """Групповая правка выделенных помещений.

    Поле выбирается из списка; редактор под него подбирается по «виду»:
    выпадающий список (тип/этаж/зона) или числовой спин (температуры,
    люди, освещение, оборудование, инфильтрация)."""

    # (ключ поля, i18n-ключ подписи, вид редактора)
    _FIELD_SPECS = (
        ("room_type",        "panel.spaces.col.type",    "combo_type"),
        ("level",            "panel.spaces.col.level",   "combo_level"),
        ("system_heating",   "panel.spaces.col.zone",    "combo_zone"),
        ("t_in_heat",        "panel.spaces.bulk.t_heat", "spin_t"),
        ("t_in_cool",        "panel.spaces.bulk.t_cool", "spin_t"),
        ("occupancy_people", "panel.spaces.bulk.occup",  "spin_people"),
        ("lighting_w_m2",    "panel.spaces.bulk.light",  "spin_wm2"),
        ("equipment_w_m2",   "panel.spaces.bulk.equip",  "spin_wm2"),
        ("ach_inf",          "panel.spaces.bulk.inf",    "spin_ach"),
    )

    def __init__(self, n_selected: int, room_types, zones, levels=(),
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_t("panel.spaces.bulk.title"))
        self.setModal(True)
        form = QFormLayout(self)

        self.field_combo = QComboBox()
        self.stack = QStackedWidget()
        # Параллельно _FIELD_SPECS: (вид, виджет) для чтения значения.
        self._editors: List[tuple] = []
        for key, label_key, kind in self._FIELD_SPECS:
            self.field_combo.addItem(_t(label_key), key)
            w = self._make_editor(kind, room_types, zones, levels)
            self._editors.append((kind, w))
            self.stack.addWidget(w)
        form.addRow(_t("panel.spaces.bulk.field"), self.field_combo)
        form.addRow(_t("panel.spaces.bulk.value"), self.stack)
        self.field_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        hint = QLabel(_t("panel.spaces.bulk.hint").format(n=n_selected))
        hint.setProperty("role", "muted")
        form.addRow(hint)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(_t("btn.apply"))
        box.button(QDialogButtonBox.Cancel).setText(_t("btn.cancel"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    @staticmethod
    def _make_editor(kind: str, room_types, zones, levels) -> QWidget:
        if kind in ("combo_type", "combo_level", "combo_zone"):
            c = QComboBox()
            c.setEditable(True)
            c.addItems(list({"combo_type": room_types, "combo_level": levels,
                             "combo_zone": zones}[kind]))
            return c
        s = QDoubleSpinBox()
        if kind == "spin_t":
            s.setRange(-50.0, 50.0); s.setDecimals(1); s.setSuffix(" °C")
            s.setValue(20.0)
        elif kind == "spin_people":
            s.setRange(0.0, 1000.0); s.setDecimals(1)
        elif kind == "spin_wm2":
            s.setRange(0.0, 500.0); s.setDecimals(1); s.setSuffix(" Вт/м²")
        elif kind == "spin_ach":
            s.setRange(0.0, 10.0); s.setDecimals(2); s.setSuffix(" 1/ч")
        return s

    def result_value(self):
        """Возвращает (field_key, value)."""
        idx = self.field_combo.currentIndex()
        key = self.field_combo.currentData()
        kind, w = self._editors[idx]
        if kind.startswith("combo"):
            return key, w.currentText()
        return key, w.value()


# ===========================================================================
# Отдельное окно деталей помещения
# ===========================================================================


class SpaceDetailWindow(QDialog):
    """Плавающее немодальное окно: свойства помещения + ограждения.

    Раньше эти панели жили в правой части SpacesPanel и занимали пол-экрана.
    Вынесены в отдельное окно, чтобы таблица помещений была на всю ширину
    (Excel-режим). Окно следует за выбором строки в таблице — но только пока
    открыто, поэтому навигация по таблице при закрытом окне не пересобирает
    тяжёлую таблицу ограждений."""

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle(_t("panel.spaces.detail.title"))
        self.resize(620, 860)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        split = QSplitter(Qt.Vertical)
        split.setHandleWidth(6)
        self.props = PropertiesPanel(project, bridge)
        split.addWidget(self.props)
        self.boundaries = BoundariesPanel(project, bridge)
        split.addWidget(self.boundaries)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([320, 480])
        lay.addWidget(split)

    def show_space(self, sp: Optional[Space]) -> None:
        self.props.show_space(sp)
        self.boundaries.show_space(sp)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(_t("panel.spaces.detail.title"))


# ===========================================================================
# Сама панель
# ===========================================================================


class SpacesPanel(QWidget):
    """Полноширинная таблица помещений; детали — в отдельном окне."""

    spaceSelected = Signal(object)  # Space | None

    def __init__(self, project: HVACProject, bridge: ProjectBridge,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.bridge = bridge

        self._build_ui()
        self._wire_signals()
        self._refresh_filter_options()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # Шапка
        head = QHBoxLayout()
        self.title_lbl = QLabel(_t("panel.spaces.title"))
        self.title_lbl.setProperty("role", "h1")
        head.addWidget(self.title_lbl)

        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("role", "muted")
        head.addSpacing(12)
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        outer.addLayout(head)

        # Тулбар с поиском и фильтрами
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("panel.spaces.search.ph"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(280)
        toolbar.addWidget(self.search, stretch=2)

        self.level_filter = QComboBox()
        self.level_filter.setMinimumWidth(140)
        self._level_filter_lbl = QLabel(_t("panel.spaces.filter.level"))
        toolbar.addWidget(_label_with_widget(self._level_filter_lbl,
                                              self.level_filter))

        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(160)
        self._type_filter_lbl = QLabel(_t("panel.spaces.filter.type"))
        toolbar.addWidget(_label_with_widget(self._type_filter_lbl,
                                              self.type_filter))

        self.zone_filter = QComboBox()
        self.zone_filter.setMinimumWidth(160)
        self._zone_filter_lbl = QLabel(_t("panel.spaces.filter.zone"))
        toolbar.addWidget(_label_with_widget(self._zone_filter_lbl,
                                              self.zone_filter))

        toolbar.addStretch(1)

        # Кнопки ручного управления
        self.b_add = QPushButton(_t("btn.add_space"))
        self.b_add.clicked.connect(self._on_add)
        toolbar.addWidget(self.b_add)

        self.b_edit = QPushButton(_t("btn.edit_space"))
        self.b_edit.clicked.connect(self._on_edit)
        toolbar.addWidget(self.b_edit)

        # Открывает отдельное окно «Свойства + Ограждения» выбранного помещения.
        self.b_detail = QPushButton(_t("btn.space_detail"))
        self.b_detail.clicked.connect(self._open_detail)
        toolbar.addWidget(self.b_detail)

        self.b_del = QPushButton(_t("btn.delete"))
        self.b_del.clicked.connect(self._on_delete)
        toolbar.addWidget(self.b_del)

        self.b_dup = QPushButton(_t("btn.duplicate"))
        self.b_dup.clicked.connect(self._on_duplicate)
        toolbar.addWidget(self.b_dup)

        self.b_import = QPushButton(_t("btn.import"))
        self.b_import.clicked.connect(self._on_import)
        toolbar.addWidget(self.b_import)

        self.b_template = QPushButton(_t("btn.template"))
        self.b_template.clicked.connect(self._on_template)
        toolbar.addWidget(self.b_template)

        outer.addLayout(toolbar)

        # Splitter: таблица | свойства
        # --- Таблица (на всю ширину панели) ---
        self.table = QTableView()
        self.model = SpacesTableModel(self.project, self.bridge, self)
        self.proxy = SpacesFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        # Сортировка по «сырому» значению (EditRole), а не по форматированной
        # строке — иначе числовые колонки (S, V, Люди, Q) сортировались бы
        # лексически («10» < «9»).
        self.proxy.setSortRole(Qt.EditRole)
        self.table.setModel(self.proxy)

        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        # Поячейковое выделение (как в Excel): можно выделить столбец «Люди»
        # у группы помещений и вставить/протянуть одно значение, не затрагивая
        # остальные поля строки. Текущая строка по-прежнему ведёт окно деталей.
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, col in enumerate(SpacesTableModel.COLUMNS):
            self.table.setColumnWidth(i, col.width)
        # Excel-горячие клавиши: Ctrl+C/V/D, Ctrl+Z/Y (буфер/fill-down/undo).
        self._edit = TableEditBinder(self.table, self.proxy, self.model,
                                     self.bridge)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Делегаты для редактируемых колонок
        type_col = next(i for i, c in enumerate(SpacesTableModel.COLUMNS)
                        if c.key == "room_type")
        self.table.setItemDelegateForColumn(
            type_col, ComboDelegate(get_all_room_types, self.table))

        zone_col = next(i for i, c in enumerate(SpacesTableModel.COLUMNS)
                        if c.key == "system_heating")
        self.table.setItemDelegateForColumn(
            zone_col, ComboDelegate(self._existing_zones, self.table))

        # Этаж — выпадающий список известных этажей (можно ввести новый).
        level_col = next(i for i, c in enumerate(SpacesTableModel.COLUMNS)
                         if c.key == "level")
        self.table.setItemDelegateForColumn(
            level_col, ComboDelegate(self._known_levels, self.table))

        # Числовые ячейки: площадь / объём / зимняя tв / люди. Свой делегат —
        # иначе стандартный QDoubleSpinBox Qt обрезал бы значения на 99.99.
        for key, lo, hi, dec, suf in (
            ("area_m2",   0.0, 1_000_000.0, 2, " м²"),
            ("volume_m3", 0.0, 10_000_000.0, 2, " м³"),
            ("t_in_heat", -50.0, 50.0, 1, " °C"),
            ("t_in_cool", -50.0, 50.0, 1, " °C"),
            ("occupancy_people", 0.0, 100_000.0, 1, ""),
            ("lighting_w_m2", 0.0, 500.0, 1, " Вт/м²"),
            ("equipment_w_m2", 0.0, 500.0, 1, " Вт/м²"),
        ):
            ci = next(i for i, c in enumerate(SpacesTableModel.COLUMNS)
                      if c.key == key)
            self.table.setItemDelegateForColumn(
                ci, NumberDelegate(lo, hi, dec, suf, self.table))

        outer.addWidget(self.table, stretch=1)

        # --- Окно деталей (Свойства + Ограждения) ---
        # Отдельное немодальное окно, чтобы таблица была на всю ширину.
        # self.props / self.boundaries — алиасы для совместимости со старым
        # кодом (_on_edit, _on_row_changed).
        self.detail = SpaceDetailWindow(self.project, self.bridge, self)
        self.props = self.detail.props
        self.boundaries = self.detail.boundaries
        self._current_space: Optional[Space] = None

    def _wire_signals(self) -> None:
        self.search.textChanged.connect(self.proxy.set_text)
        self.level_filter.currentTextChanged.connect(self.proxy.set_level)
        self.type_filter.currentTextChanged.connect(self.proxy.set_type)
        self.zone_filter.currentTextChanged.connect(self.proxy.set_zone)

        self.bridge.dataLoaded.connect(self._refresh_filter_options)
        self.bridge.projectLoaded.connect(self._refresh_filter_options)
        self.bridge.zonesChanged.connect(self._refresh_filter_options)
        self.bridge.calculationDone.connect(self._refresh_count)
        self.bridge.dataLoaded.connect(self._refresh_count)

        sel = self.table.selectionModel()
        sel.currentRowChanged.connect(self._on_row_changed)
        self.proxy.layoutChanged.connect(self._refresh_count)

    # ---- Реакция на события ----
    def _refresh_filter_options(self, *args: Any) -> None:
        levels = sorted({s.level for s in self.project.spaces if s.level})
        types = sorted({s.room_type for s in self.project.spaces
                        if s.room_type})
        zones = sorted({s.system_heating for s in self.project.spaces
                        if s.system_heating})

        all_label = _t("filter.all")
        for combo, items in (
            (self.level_filter, levels),
            (self.type_filter, types),
            (self.zone_filter, zones),
        ):
            current = combo.currentText() or all_label
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(items)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)
        self._refresh_count()

    def _refresh_count(self, *args: Any) -> None:
        total = len(self.project.spaces)
        visible = self.proxy.rowCount()
        if total == 0:
            text = _t("panel.spaces.count_empty")
        elif visible == total:
            text = _t("panel.spaces.count_total").format(n=total)
        else:
            text = _t("panel.spaces.count_filtered").format(
                visible=visible, total=total)
        self.count_lbl.setText(text)

    def select_space(self, space_id: str) -> None:
        """Выделяет помещение по space_id и прокручивает к нему. Если строка
        скрыта фильтром — сбрасывает фильтры, чтобы помещение стало видимым.
        Используется навигацией из панели «Проблемы»."""
        row = next((i for i, s in enumerate(self.project.spaces)
                    if s.space_id == space_id), -1)
        if row < 0:
            return
        src = self.model.index(row, 0)
        pidx = self.proxy.mapFromSource(src)
        if not pidx.isValid():
            # Сбрасываем фильтры (сигналы combo/search обновят прокси).
            self.search.clear()
            for combo in (self.level_filter, self.type_filter,
                          self.zone_filter):
                combo.setCurrentIndex(0)
            pidx = self.proxy.mapFromSource(src)
        if pidx.isValid():
            self.table.setCurrentIndex(pidx)
            self.table.scrollTo(pidx, QAbstractItemView.PositionAtCenter)
            self.table.setFocus()

    # ===== Групповая правка / контекстное меню =====
    def _selected_source_rows(self) -> List[int]:
        sel = self.table.selectionModel()
        if sel is None:
            return []
        # selectedIndexes(), а не selectedRows(): при поячейковом выделении
        # «строка целиком» не выделяется, но строку каждой выбранной ячейки
        # учитываем для групповой правки.
        return sorted({self.proxy.mapToSource(idx).row()
                       for idx in sel.selectedIndexes()})

    def _bulk_edit(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(self, _t("panel.spaces.bulk.title"),
                                    _t("panel.spaces.bulk.no_selection"))
            return
        dlg = SpacesBulkDialog(len(rows), get_all_room_types(),
                               self._existing_zones(), self._known_levels(),
                               self)
        if dlg.exec() != QDialog.Accepted:
            return
        field_key, value = dlg.result_value()
        n = self.model.bulk_set_field(rows, field_key, value)
        self.bridge.statusMessage.emit(
            _t("panel.spaces.bulk.applied").format(n=n), 4000)

    def _set_rooms_exterior(self, is_exterior: bool) -> None:
        """Помечает все стены/проёмы выделенных помещений внутренними
        (is_exterior=False — теплопотери только от инфильтрации) или
        наружными (True — полный расчёт через ограждения). Восстанавливает
        действие «🏠 Сделать внутренними» из старого интерфейса."""
        rows = self._selected_source_rows()
        if not rows:
            QMessageBox.information(self, _t("panel.spaces.env.menu"),
                                    _t("panel.spaces.bulk.no_selection"))
            return
        ids = {self.project.spaces[r].space_id for r in rows}
        label = (_t("panel.spaces.env.lbl_external") if is_exterior
                 else _t("panel.spaces.env.lbl_internal"))
        target = [e for sid in ids for e in self.project.elements_for(sid)
                  if e.row_type in ("external_wall", "opening")
                  and e.is_exterior != is_exterior]
        if not target:
            QMessageBox.information(
                self, _t("panel.spaces.env.menu"),
                _t("panel.spaces.env.nothing").format(n=len(ids), label=label))
            return
        ans = QMessageBox.question(
            self, _t("panel.spaces.env.confirm.title"),
            _t("panel.spaces.env.confirm.body").format(
                rooms=len(ids), elems=len(target), label=label),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        n = self.project.set_rooms_exterior(ids, is_exterior)
        self.project.recalculate()   # обновит колонки Q (calculationDone)
        self.bridge.dirtyChanged.emit(True)
        self.bridge.statusMessage.emit(
            _t("panel.spaces.env.done").format(elems=n, rooms=len(ids)), 5000)

    def _show_context_menu(self, pos) -> None:
        if not self.project.spaces:
            return
        rows = self._selected_source_rows()
        sel = self.table.selectionModel()
        has_sel = bool(sel and sel.selectedIndexes())
        menu = QMenu(self)
        act_bulk = menu.addAction(_t("panel.spaces.bulk.menu"))
        menu.addSeparator()
        # Ограждения выделенных помещений: массово «внутренние»/«наружные».
        env_menu = menu.addMenu(_t("panel.spaces.env.menu"))
        act_internal = env_menu.addAction(_t("panel.spaces.env.make_internal"))
        act_external = env_menu.addAction(_t("panel.spaces.env.make_external"))
        act_internal.setEnabled(bool(rows))
        act_external.setEnabled(bool(rows))
        menu.addSeparator()
        act_copy = menu.addAction(_t("tableedit.ctx.copy"))
        act_paste = menu.addAction(_t("tableedit.ctx.paste"))
        act_fill = menu.addAction(_t("tableedit.ctx.fill_down"))
        menu.addSeparator()
        act_undo = menu.addAction(_t("tableedit.ctx.undo"))
        act_redo = menu.addAction(_t("tableedit.ctx.redo"))
        act_bulk.setEnabled(bool(rows))
        act_copy.setEnabled(has_sel)
        act_fill.setEnabled(has_sel)
        act_undo.setEnabled(self.model.can_undo())
        act_redo.setEnabled(self.model.can_redo())
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_bulk:
            self._bulk_edit()
        elif chosen is act_internal:
            self._set_rooms_exterior(False)
        elif chosen is act_external:
            self._set_rooms_exterior(True)
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

    def _on_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        sp: Optional[Space] = None
        if current.isValid():
            source_idx = self.proxy.mapToSource(current)
            sp = self.model.space_at(source_idx.row())
        self._current_space = sp
        # Окно деталей пересобираем только когда оно открыто — иначе быстрая
        # навигация по таблице не тратила бы время на тяжёлую таблицу
        # ограждений (десятки комбобоксов на помещение).
        if self.detail.isVisible():
            self.detail.show_space(sp)
        self.spaceSelected.emit(sp)

    def _open_detail(self) -> None:
        """Открывает (или поднимает на передний план) окно «Свойства +
        Ограждения» для текущего помещения."""
        if self._current_space is None:
            self._current_space = self._selected_space()
        self.detail.show_space(self._current_space)
        self.detail.show()
        self.detail.raise_()
        self.detail.activateWindow()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Уходя с раздела «Помещения», прячем плавающее окно деталей, чтобы
        # оно не висело поверх других вкладок.
        detail = getattr(self, "detail", None)
        if detail is not None:
            detail.hide()
        super().hideEvent(event)

    # ===== Ручное управление помещениями =====
    def _selected_space(self) -> Space | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        src = self.proxy.mapToSource(idx)
        return self.model.space_at(src.row())

    def _known_levels(self) -> List[str]:
        return sorted({s.level for s in self.project.spaces if s.level})

    def _on_add(self) -> None:
        dlg = SpaceDialog(self, known_levels=self._known_levels())
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.result_value()
        if not v.number:
            QMessageBox.warning(self, _t("panel.spaces.dlg.no_number.title"),
                                  _t("panel.spaces.dlg.no_number.body"))
            return
        try:
            sp = self.project.add_space(
                number=v.number, name=v.name or v.number,
                level=v.level or _t("panel.spaces.default_level"),
                area_m2=v.area_m2,
                height_m=v.height_m, room_type=v.room_type)
        except ValueError as e:
            QMessageBox.warning(self, _t("panel.spaces.dlg.not_added"), str(e))
            return
        self.bridge.dirtyChanged.emit(True)
        self.model._full_reset()
        self._refresh_filter_options()
        # Выделить добавленное помещение
        for row, s in enumerate(self.project.spaces):
            if s.space_id == sp.space_id:
                src_idx = self.model.index(row, 0)
                self.table.setCurrentIndex(self.proxy.mapFromSource(src_idx))
                break

    def _on_edit(self) -> None:
        sp = self._selected_space()
        if sp is None:
            QMessageBox.information(self, _t("dlg.space.title_edit"),
                                    _t("panel.spaces.bulk.no_selection"))
            return
        height = sp.height_m
        if height <= 0 and sp.area_m2 > 0 and sp.volume_m3 > 0:
            height = sp.volume_m3 / sp.area_m2
        initial = SpaceEditResult(
            number=sp.number, name=sp.name, level=sp.level,
            room_type=sp.room_type, area_m2=sp.area_m2, height_m=height,
            volume_m3=sp.volume_m3, t_in_heat=float(sp.t_in_heat),
            t_in_cool=float(sp.t_in_cool),
            wc_count=int(getattr(sp, "wc_count", 0) or 0),
            urinal_count=int(getattr(sp, "urinal_count", 0) or 0),
            water_surface_m2=float(getattr(sp, "water_surface_m2", 0.0) or 0.0),
            water_temp_c=float(getattr(sp, "water_temp_c", 0.0) or 0.0),
            spectator_count=int(getattr(sp, "spectator_count", 0) or 0),
            car_count=int(getattr(sp, "car_count", 0) or 0))
        dlg = SpaceEditDialog(self, initial=initial,
                              known_levels=self._known_levels())
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.result_value()
        if not v.number:
            QMessageBox.warning(self, _t("panel.spaces.dlg.no_number.title"),
                                _t("panel.spaces.dlg.no_number.body"))
            return
        sp.number = v.number
        sp.name = v.name
        sp.level = v.level
        sp.room_type = v.room_type
        sp.area_m2 = v.area_m2
        sp.height_m = v.height_m
        sp.volume_m3 = v.volume_m3
        sp.t_in_heat = v.t_in_heat
        sp.t_in_cool = v.t_in_cool
        sp.wc_count = v.wc_count
        sp.urinal_count = v.urinal_count
        sp.water_surface_m2 = v.water_surface_m2
        sp.water_temp_c = v.water_temp_c
        sp.spectator_count = v.spectator_count
        sp.car_count = v.car_count
        sp.user_modified = True
        self.bridge.dirtyChanged.emit(True)
        # Точечно перерисовываем строку (не сбрасывая историю inline-правок),
        # обновляем фильтры (этаж/№ могли измениться) и панель свойств.
        try:
            row = self.project.spaces.index(sp)
            top = self.model.index(row, 0)
            bot = self.model.index(row, self.model.columnCount() - 1)
            self.model.dataChanged.emit(top, bot)
        except ValueError:
            self.model._full_reset()
        self._refresh_filter_options()
        self.props.show_space(sp)

    def _on_delete(self) -> None:
        sp = self._selected_space()
        if sp is None:
            return
        # Используем индекс elements_by_space — быстрее, чем линейный скан.
        n_elems = len(self.project.elements_for(sp.space_id))
        msg = _t("panel.spaces.dlg.delete.body").format(
            number=sp.number, name=sp.name)
        if n_elems:
            msg += _t("panel.spaces.dlg.delete.elems").format(n=n_elems)
        ans = QMessageBox.question(self, _t("panel.spaces.dlg.delete.title"),
                                    msg, QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        self.project.remove_space(sp.space_id)
        self.bridge.dirtyChanged.emit(True)
        self.model._full_reset()
        self._refresh_filter_options()

    def _on_duplicate(self) -> None:
        sp = self._selected_space()
        if sp is None:
            return
        new_sp = self.project.duplicate_space(sp.space_id)
        if new_sp is None:
            return
        self.bridge.dirtyChanged.emit(True)
        self.model._full_reset()
        self._refresh_filter_options()

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("panel.spaces.dlg.import.title"), "",
            _t("panel.spaces.dlg.import.filter"))
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                n = self.project.import_spaces_from_csv(path)
            else:
                n = self.project.import_spaces_from_excel(path)
        except Exception as e:
            QMessageBox.critical(self, _t("panel.spaces.dlg.import_err"), str(e))
            return
        self.bridge.dirtyChanged.emit(True)
        self.model._full_reset()
        self._refresh_filter_options()
        self.bridge.statusMessage.emit(
            _t("panel.spaces.status.imported").format(n=n, path=path), 5000)

    def _on_template(self) -> None:
        dlg = BuildingTemplateDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        tpl = dlg.result_value()
        if not tpl.rooms_per_apartment:
            QMessageBox.warning(self, _t("panel.spaces.dlg.tpl_empty.title"),
                                 _t("panel.spaces.dlg.tpl_empty.body"))
            return
        created = self.project.add_spaces_from_template(tpl)
        self.bridge.dirtyChanged.emit(True)
        self.model._full_reset()
        self._refresh_filter_options()
        self.bridge.statusMessage.emit(
            _t("panel.spaces.status.tpl_created").format(n=len(created)), 5000)

    def _existing_zones(self) -> List[str]:
        zones = sorted({s.system_heating for s in self.project.spaces
                        if s.system_heating})
        if not zones:
            # Эти имена попадут в spaces.system_heating и сохранятся
            # в JSON — поэтому держим их фиксированными (без перевода),
            # чтобы при смене языка не было дублей "Зона A" / "Zona A".
            zones = ["Зона A", "Зона B"]
        return zones

    # ---------- Локализация ----------
    def retranslate_ui(self) -> None:
        """Обновляет все подписи после смены языка."""
        self.title_lbl.setText(_t("panel.spaces.title"))
        self.search.setPlaceholderText(_t("panel.spaces.search.ph"))
        self._level_filter_lbl.setText(_t("panel.spaces.filter.level"))
        self._type_filter_lbl.setText(_t("panel.spaces.filter.type"))
        self._zone_filter_lbl.setText(_t("panel.spaces.filter.zone"))
        self.b_add.setText(_t("btn.add_space"))
        self.b_edit.setText(_t("btn.edit_space"))
        self.b_detail.setText(_t("btn.space_detail"))
        self.b_del.setText(_t("btn.delete"))
        self.b_dup.setText(_t("btn.duplicate"))
        self.b_import.setText(_t("btn.import"))
        self.b_template.setText(_t("btn.template"))
        # Заголовки колонок таблицы — модель отдаёт их через _t() в headerData;
        # сообщаем Qt, что header-секции стоит перерисовать.
        self.model.headerDataChanged.emit(
            Qt.Horizontal, 0, self.model.columnCount() - 1)
        self.detail.retranslate_ui()
        # Опции фильтров (значение "(все)") пересобираем
        self._refresh_filter_options()
        self._refresh_count()


def _label_with_widget(lbl: QLabel, widget: QWidget) -> QWidget:
    """Маленький layout «подпись + поле» для тулбара. Принимает готовый
    QLabel — чтобы вызывающий мог хранить ссылку и обновить текст
    после смены языка."""
    wrap = QWidget()
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lbl.setProperty("role", "muted")
    lay.addWidget(lbl)
    lay.addWidget(widget, stretch=1)
    wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return wrap
