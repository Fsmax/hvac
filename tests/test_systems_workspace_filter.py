# -*- coding: utf-8 -*-
"""Headless-тест выпадающих фильтров (этаж / тип / зона) в разделе
«Системы и оборудование». Пропускается, если Qt-платформа недоступна."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.i18n import t as _t  # noqa: E402
from hvac.models import Space  # noqa: E402
from hvac.project import HVACProject  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt недоступен: {exc}")


def _project():
    p = HVACProject()
    p.params.apply_city("Ташкент")
    rows = [
        ("R1", "L02", "Офис",    "Котёл A"),
        ("R2", "L12", "Спальня", "Котёл A"),
        ("R3", "L22", "Офис",    "Котёл B"),
        ("R4", "L02", "Ванная",  ""),
    ]
    for i, (num, lvl, typ, sysh) in enumerate(rows):
        sp = Space(space_id=f"r{i}", number=num, name="x", level=lvl,
                   area_m2=20, volume_m3=60, height_m=3,
                   room_type=typ, t_in_heat=20.0)
        sp.system_heating = sysh
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def _panel(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.systems_workspace import SystemsWorkspacePanel
    panel = SystemsWorkspacePanel(p, ProjectBridge(p))
    panel._refresh()
    return panel


def _items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def _visible_numbers(panel):
    out = set()
    for r in range(panel.table.rowCount()):
        if not panel.table.isRowHidden(r):
            it = panel.table.item(r, 0)
            if it is not None:
                out.add(it.text())
    return out


def test_filter_options_populated(qapp):
    panel = _panel(_project())
    alll = _t("filter.all")
    # этажи отсортированы по числу, а не лексически
    assert _items(panel.level_filter) == [alll, "L02", "L12", "L22"]
    assert set(_items(panel.type_filter)) == {alll, "Ванная", "Офис", "Спальня"}
    # домен по умолчанию — отопление: зона = system_heating
    assert set(_items(panel.zone_filter)) == {alll, "Котёл A", "Котёл B"}


def test_level_filter(qapp):
    panel = _panel(_project())
    panel.level_filter.setCurrentText("L02")
    assert _visible_numbers(panel) == {"R1", "R4"}


def test_type_filter(qapp):
    panel = _panel(_project())
    panel.type_filter.setCurrentText("Офис")
    assert _visible_numbers(panel) == {"R1", "R3"}


def test_zone_filter_is_domain_system(qapp):
    panel = _panel(_project())
    panel.zone_filter.setCurrentText("Котёл A")
    assert _visible_numbers(panel) == {"R1", "R2"}


def test_combined_filters(qapp):
    panel = _panel(_project())
    panel.level_filter.setCurrentText("L02")
    panel.zone_filter.setCurrentText("Котёл A")
    assert _visible_numbers(panel) == {"R1"}


def _select_all_rows(panel):
    from PySide6.QtCore import QItemSelectionModel
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(panel.table.rowCount()):
        sm.select(panel.table.model().index(r, 0),
                  QItemSelectionModel.Select | QItemSelectionModel.Rows)


def test_selection_excludes_filtered_out_rows(qapp):
    """Регресс: скрытые фильтром помещения остаются «выделенными» в
    QTableWidget, но _selected_ids() должен возвращать только видимые."""
    panel = _panel(_project())
    _select_all_rows(panel)
    panel.level_filter.setCurrentText("L02")  # видимы только R1, R4
    p = panel.project
    assert {p._space_by_id[i].number for i in panel._selected_ids()} == {"R1", "R4"}


def test_assignment_ignores_filtered_out_rooms(qapp):
    """Регресс главного бага: при назначении (drag&drop/кнопки) над
    выделением не должна затрагиваться комната, скрытая фильтром."""
    p = _project()
    panel = _panel(p)
    _select_all_rows(panel)
    panel.level_filter.setCurrentText("L02")  # видимы только R1 (r0), R4 (r3)
    # эмулируем drop на узел «Котёл C» — назначается текущее видимое выделение
    panel._assign_to_system("Котёл C")
    assert p._space_by_id["r0"].system_heating == "Котёл C"   # R1 видим → изменён
    assert p._space_by_id["r3"].system_heating == "Котёл C"   # R4 видим → изменён
    assert p._space_by_id["r1"].system_heating == "Котёл A"   # R2 скрыт → без изменений
    assert p._space_by_id["r2"].system_heating == "Котёл B"   # R3 скрыт → без изменений
