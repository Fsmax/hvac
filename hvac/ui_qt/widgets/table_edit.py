# -*- coding: utf-8 -*-
"""Единый движок табличных правок: undo/redo на снимках полей + привязка
горячих клавиш Excel-стиля (копировать/вставить/заполнить вниз/отменить/
повторить) к QTableView.

Модель наследует EditableTableModelMixin и реализует хуки:
- класс-атрибут _EDITABLE_COLS : множество индексов редактируемых колонок;
- _row_count()                : число строк (по умолчанию rowCount());
- _snapshot_row(row) -> dict  : снимок ВСЕХ полей, которые правка может
                                затронуть (для корректной отмены побочных
                                эффектов вроде apply_room_type_defaults);
- _restore_row(row, snap)     : восстановление строки из снимка;
- _apply_cell(row, col, raw)  : приведение типа + запись + побочные эффекты,
                                без emit; вернуть False при невалидном вводе
                                (и НЕ менять состояние в этом случае);
- _cell_edit_value(row, col)  : текущее значение ячейки (для «заполнить вниз»).
Опционально: _after_change(rows) — доп. события (например constructions_changed).

Требует self.bridge (ProjectBridge) — для dirtyChanged.

TableEditBinder привязывает горячие клавиши к (table, proxy, model).
"""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from hvac.i18n import t as _t
from hvac.ui_qt.widgets.table_clipboard import clipboard_grid, install_copy


class EditableTableModelMixin:
    """Добавляет QAbstractTableModel-у undo/redo и групповые правки."""

    _EDITABLE_COLS: set = set()
    _UNDO_LIMIT = 200

    def _init_edit_history(self) -> None:
        self._undo_stack: list = []
        self._redo_stack: list = []

    # ---- хуки, переопределяемые моделью ----
    def _row_count(self) -> int:
        return self.rowCount()

    def _snapshot_row(self, row: int) -> dict:
        raise NotImplementedError

    def _restore_row(self, row: int, snap: dict) -> None:
        raise NotImplementedError

    def _apply_cell(self, row: int, col: int, raw) -> bool:
        raise NotImplementedError

    def _cell_edit_value(self, row: int, col: int):
        raise NotImplementedError

    def _after_change(self, rows: List[int]) -> None:
        pass

    # ---- инфраструктура ----
    def _snapshot(self, rows) -> dict:
        return {r: self._snapshot_row(r) for r in rows}

    def _emit_rows_changed(self, rows) -> None:
        if not rows:
            return
        top = self.index(min(rows), 0)
        bot = self.index(max(rows), self.columnCount() - 1)
        self.dataChanged.emit(top, bot)

    def _restore(self, snap: dict) -> None:
        for r, s in snap.items():
            if 0 <= r < self._row_count():
                self._restore_row(r, s)
        rows = list(snap.keys())
        self._emit_rows_changed(rows)
        self.bridge.dirtyChanged.emit(True)
        self._after_change(rows)

    def _commit(self, rows, mutate) -> int:
        rows = [r for r in dict.fromkeys(rows) if 0 <= r < self._row_count()]
        if not rows:
            return 0
        before = self._snapshot(rows)
        mutate(rows)
        after = self._snapshot(rows)
        changed = [r for r in rows if before[r] != after[r]]
        if not changed:
            return 0
        self._undo_stack.append(({r: before[r] for r in changed},
                                 {r: after[r] for r in changed}))
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._emit_rows_changed(changed)
        self.bridge.dirtyChanged.emit(True)
        self._after_change(changed)
        return len(changed)

    def clear_edit_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> int:
        if not self._undo_stack:
            return 0
        before, after = self._undo_stack.pop()
        self._redo_stack.append((before, after))
        self._restore(before)
        return len(before)

    def redo(self) -> int:
        if not self._redo_stack:
            return 0
        before, after = self._redo_stack.pop()
        self._undo_stack.append((before, after))
        self._restore(after)
        return len(after)

    def commit_cell(self, row: int, col: int, raw) -> bool:
        """Одиночная правка из делегата (вызывать из setData)."""
        if col not in self._EDITABLE_COLS:
            return False
        flag = {"ok": True}

        def mutate(_rows):
            if not self._apply_cell(row, col, raw):
                flag["ok"] = False

        self._commit([row], mutate)
        return flag["ok"]

    def set_cells(self, edits: Dict) -> int:
        """Применяет {(row, col): raw} как одну отменяемую операцию
        (вставка, заполнение вниз, групповая правка). Возвращает число
        изменённых строк."""
        valid = {(r, c): v for (r, c), v in edits.items()
                 if c in self._EDITABLE_COLS and 0 <= r < self._row_count()}
        if not valid:
            return 0
        rows = [r for (r, _c) in valid]

        def mutate(_rows):
            for (r, c), v in valid.items():
                self._apply_cell(r, c, v)

        return self._commit(rows, mutate)


class TableEditBinder:
    """Привязывает Ctrl+C/V/D/Z/Y к QTableView с моделью EditableTableModelMixin.

    proxy — QSortFilterProxyModel поверх модели (или None, если вид смотрит
    прямо в модель).
    """

    def __init__(self, table, proxy, model, bridge):
        self.table = table
        self.proxy = proxy
        self.model = model
        self.bridge = bridge
        install_copy(table)
        for seq, slot in (
            (QKeySequence.Paste, self.paste),
            (QKeySequence("Ctrl+D"), self.fill_down),
            (QKeySequence.Undo, self.undo),
            (QKeySequence.Redo, self.redo),
            (QKeySequence("Ctrl+Shift+Z"), self.redo),
        ):
            sc = QShortcut(seq, table)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

    # ---- маппинг прокси ↔ источник ----
    def _src_row(self, idx) -> int:
        return self.proxy.mapToSource(idx).row() if self.proxy else idx.row()

    def _src_index(self, prow: int, pcol: int):
        if self.proxy:
            return self.proxy.mapToSource(self.proxy.index(prow, pcol))
        return self.model.index(prow, pcol)

    def _view_rows(self) -> int:
        return self.proxy.rowCount() if self.proxy else self.model.rowCount()

    # ---- операции ----
    def paste(self) -> None:
        grid = clipboard_grid()
        if not grid:
            return
        editable = self.model._EDITABLE_COLS
        sel = self.table.selectionModel()
        edits: dict = {}
        if len(grid) == 1 and len(grid[0]) == 1:
            val = grid[0][0]
            if sel is None:
                return
            for idx in sel.selectedIndexes():
                if idx.column() in editable:
                    edits[(self._src_row(idx), idx.column())] = val
        else:
            anchor = self.table.currentIndex()
            if not anchor.isValid():
                return
            for i, line in enumerate(grid):
                prow = anchor.row() + i
                if prow >= self._view_rows():
                    break
                for j, cell in enumerate(line):
                    pcol = anchor.column() + j
                    if pcol not in editable:
                        continue
                    si = self._src_index(prow, pcol)
                    edits[(si.row(), pcol)] = cell
        n = self.model.set_cells(edits)
        if n:
            self.bridge.statusMessage.emit(
                _t("tableedit.paste").format(n=n), 3000)

    def fill_down(self) -> None:
        sel = self.table.selectionModel()
        if sel is None:
            return
        editable = self.model._EDITABLE_COLS
        by_col: dict = {}
        for idx in sel.selectedIndexes():
            if idx.column() in editable:
                by_col.setdefault(idx.column(), []).append(idx)
        edits: dict = {}
        for col, idxs in by_col.items():
            idxs.sort(key=lambda i: i.row())
            top_row = self._src_row(idxs[0])
            val = self.model._cell_edit_value(top_row, col)
            for idx in idxs[1:]:
                edits[(self._src_row(idx), col)] = val
        n = self.model.set_cells(edits)
        if n:
            self.bridge.statusMessage.emit(
                _t("tableedit.fill").format(n=n), 3000)

    def undo(self) -> None:
        n = self.model.undo()
        if n:
            self.bridge.statusMessage.emit(
                _t("tableedit.undo").format(n=n), 2500)

    def redo(self) -> None:
        n = self.model.redo()
        if n:
            self.bridge.statusMessage.emit(
                _t("tableedit.redo").format(n=n), 2500)
