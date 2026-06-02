# -*- coding: utf-8 -*-
"""Headless-тесты ручной правки расходов воздуха в VentilationPanel.

Проверяют, что таблица вентиляции редактируема (регрессия: была read-only),
что правка ставит vent_user_modified и что последующий пересчёт
calculate_ventilation() это помещение не перетирает.
Пропускаются, если Qt-платформа недоступна.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


def _project(n: int = 1) -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(n):
        sp = Space(
            space_id=f"r{i}", number=f"R{i}", name="Офис", level="L1",
            area_m2=25, volume_m3=75, height_m=3, room_type="Офис",
            occupancy_people=2,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def _model(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.ventilation_panel import VentilationModel
    bridge = ProjectBridge(p)
    return VentilationModel(p, bridge), bridge


def _panel(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.ventilation_panel import VentilationPanel
    panel = VentilationPanel(p, ProjectBridge(p))
    # Детерминированный порядок для тестов: proxy-строка == source-строка.
    # (В реале сортировка включена и правка идёт по видимой строке — это
    # корректно; тут лишь убираем сорт, чтобы индексы совпадали с моделью.)
    panel.proxy.sort(-1)
    return panel


def test_supply_cell_is_editable(qapp):
    p = _project()
    model, _ = _model(p)
    idx = model.index(0, 5)  # колонка «Приток»
    assert model.flags(idx) & Qt.ItemIsEditable


def test_name_cell_is_not_editable(qapp):
    p = _project()
    model, _ = _model(p)
    idx = model.index(0, 1)  # колонка «Наименование»
    assert not (model.flags(idx) & Qt.ItemIsEditable)


def test_setdata_writes_supply_and_marks_modified(qapp):
    p = _project()
    model, _ = _model(p)
    idx = model.index(0, 5)
    assert model.setData(idx, "350", Qt.EditRole) is True
    assert p.spaces[0].supply_m3h == 350.0
    assert p.spaces[0].vent_user_modified is True
    # Кратность пересчитана по притоку: 350 / 75 ≈ 4.67
    assert p.spaces[0].ach_calculated == pytest.approx(350.0 / 75.0, rel=1e-3)


def test_editrole_returns_raw_number(qapp):
    p = _project()
    p.spaces[0].exhaust_m3h = 120.0
    model, _ = _model(p)
    idx = model.index(0, 6)  # «Вытяжка»
    assert model.data(idx, Qt.EditRole) == 120.0


def test_negative_value_clamped_to_zero(qapp):
    p = _project()
    model, _ = _model(p)
    assert model.setData(model.index(0, 6), "-50", Qt.EditRole) is True
    assert p.spaces[0].exhaust_m3h == 0.0


def test_garbage_value_rejected(qapp):
    p = _project()
    model, _ = _model(p)
    assert model.setData(model.index(0, 5), "abc", Qt.EditRole) is False
    assert p.spaces[0].vent_user_modified is False


def test_manual_edit_survives_recalculation(qapp):
    """Главная регрессия: после ручной правки пересчёт не перетирает значение."""
    p = _project()
    model, _ = _model(p)
    model.setData(model.index(0, 5), "999", Qt.EditRole)
    p.calculate_ventilation()
    assert p.spaces[0].supply_m3h == 999.0


# ---------- Групповая правка ----------

def test_bulk_set_applies_to_all_rows(qapp):
    p = _project(3)
    model, _ = _model(p)
    n = model.apply_bulk([0, 1, 2], 5, "set", 200.0)
    assert n == 3
    assert all(sp.supply_m3h == 200.0 for sp in p.spaces)
    assert all(sp.vent_user_modified for sp in p.spaces)


def test_bulk_scale_percent(qapp):
    p = _project(2)
    for sp in p.spaces:
        sp.exhaust_m3h = 100.0
    model, _ = _model(p)
    model.apply_bulk([0, 1], 6, "scale", 10.0)  # +10 %
    assert all(sp.exhaust_m3h == pytest.approx(110.0) for sp in p.spaces)


def test_bulk_by_ach_uses_volume(qapp):
    p = _project(2)  # volume_m3 = 75
    model, _ = _model(p)
    model.apply_bulk([0, 1], 5, "ach", 4.0)  # 4 объёма/ч → 300 м³/ч
    assert all(sp.supply_m3h == pytest.approx(300.0) for sp in p.spaces)
    assert all(sp.ach_calculated == pytest.approx(4.0) for sp in p.spaces)


def test_bulk_only_selected_rows(qapp):
    p = _project(3)
    model, _ = _model(p)
    model.apply_bulk([0, 2], 5, "set", 150.0)
    assert p.spaces[0].supply_m3h == 150.0
    assert p.spaces[1].supply_m3h == 0.0  # не выделено — не тронуто
    assert p.spaces[2].supply_m3h == 150.0
    assert p.spaces[1].vent_user_modified is False


def test_reset_manual_recomputes_and_clears_flag(qapp):
    p = _project(2)
    model, _ = _model(p)
    # Сначала ставим ручные значения...
    model.apply_bulk([0, 1], 5, "set", 9999.0)
    assert all(sp.vent_user_modified for sp in p.spaces)
    # ...затем сбрасываем — флаг снят, значение пересчитано движком (не 9999).
    n = model.reset_manual([0, 1])
    assert n == 2
    assert all(not sp.vent_user_modified for sp in p.spaces)
    assert all(sp.supply_m3h != 9999.0 for sp in p.spaces)


def test_reset_manual_skips_auto_rows(qapp):
    p = _project(2)
    model, _ = _model(p)
    # Ни одно помещение не правилось вручную → сбрасывать нечего.
    assert model.reset_manual([0, 1]) == 0


# ---------- Undo / Redo ----------

def test_setdata_is_undoable(qapp):
    p = _project()
    model, _ = _model(p)
    model.setData(model.index(0, 5), "300", Qt.EditRole)
    assert p.spaces[0].supply_m3h == 300.0
    assert model.can_undo()
    model.undo()
    assert p.spaces[0].supply_m3h == 0.0
    assert p.spaces[0].vent_user_modified is False  # снимок восстановил флаг
    assert model.can_redo()
    model.redo()
    assert p.spaces[0].supply_m3h == 300.0
    assert p.spaces[0].vent_user_modified is True


def test_bulk_is_undoable_in_one_step(qapp):
    p = _project(3)
    model, _ = _model(p)
    model.apply_bulk([0, 1, 2], 5, "set", 200.0)
    model.undo()  # одна отмена откатывает всю групповую правку
    assert all(sp.supply_m3h == 0.0 for sp in p.spaces)


def test_new_edit_clears_redo(qapp):
    p = _project(2)
    model, _ = _model(p)
    model.setData(model.index(0, 5), "100", Qt.EditRole)
    model.undo()
    assert model.can_redo()
    model.setData(model.index(1, 5), "200", Qt.EditRole)
    assert not model.can_redo()  # новая правка обнуляет redo-стек


def test_set_cells_groups_into_single_undo(qapp):
    p = _project(3)
    model, _ = _model(p)
    model.set_cells({(0, 5): 50.0, (1, 6): 60.0, (2, 7): 70.0})
    assert p.spaces[0].supply_m3h == 50.0
    assert p.spaces[1].exhaust_m3h == 60.0
    assert p.spaces[2].hood_m3h == 70.0
    model.undo()
    assert p.spaces[0].supply_m3h == 0.0
    assert p.spaces[1].exhaust_m3h == 0.0
    assert p.spaces[2].hood_m3h == 0.0


# ---------- Буфер обмена ----------

def test_clipboard_grid_parses_tsv(qapp):
    from PySide6.QtWidgets import QApplication
    from hvac.ui_qt.widgets.table_clipboard import clipboard_grid
    QApplication.clipboard().setText("10\t20\t30\n40\t50\t60\n")
    grid = clipboard_grid()
    assert grid == [["10", "20", "30"], ["40", "50", "60"]]


def test_copy_selection_to_tsv(qapp):
    from hvac.ui_qt.widgets.table_clipboard import selection_to_tsv
    p = _project(3)
    panel = _panel(p)
    p.spaces[0].supply_m3h = 100.0
    panel.model._reset()
    panel.table.selectAll()
    tsv = selection_to_tsv(panel.table)
    assert len(tsv.splitlines()) == 3
    assert tsv.splitlines()[0].count("\t") == 10  # 11 колонок (+ «Возд.»)


def test_paste_block_into_flows(qapp):
    from PySide6.QtWidgets import QApplication
    p = _project(2)
    panel = _panel(p)
    QApplication.clipboard().setText("10\t20\t30")
    panel.table.setCurrentIndex(panel.proxy.index(0, 5))
    panel._paste()
    assert p.spaces[0].supply_m3h == 10.0
    assert p.spaces[0].exhaust_m3h == 20.0
    assert p.spaces[0].hood_m3h == 30.0
    assert p.spaces[0].vent_user_modified is True


def test_paste_single_value_fills_selection(qapp):
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication
    p = _project(3)
    panel = _panel(p)
    QApplication.clipboard().setText("55")
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(3):
        sm.select(panel.proxy.index(r, 5), QItemSelectionModel.Select)
    panel._paste()
    assert all(sp.supply_m3h == 55.0 for sp in p.spaces)


def test_fill_down(qapp):
    from PySide6.QtCore import QItemSelectionModel
    p = _project(3)
    panel = _panel(p)
    panel.model.setData(panel.model.index(0, 5), "100", Qt.EditRole)
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(3):
        sm.select(panel.proxy.index(r, 5), QItemSelectionModel.Select)
    panel._fill_down()
    assert p.spaces[1].supply_m3h == 100.0
    assert p.spaces[2].supply_m3h == 100.0
