# -*- coding: utf-8 -*-
"""Headless-тесты панели «Ограждения»: высота таблицы подгоняется под число
строк (мало строк — низкая, много — с потолком и прокруткой).
Пропускается, если Qt-платформа недоступна.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space, BoundaryElement, Construction  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


def _el(eid, orient="N"):
    return BoundaryElement(
        space_id="s1", row_type="external_wall", is_exterior=True,
        element_id=eid, category="Walls", family="Base", type_name="T",
        boundary_length_m=3.0, space_height_m=3.0, approx_area_m2=9.0,
        element_area_m2=9.0, thickness_mm=200, function="", host_element_id="",
        boundary_space_count=1, construction_key="k0", orientation_deg=0.0,
        orientation=orient, u_value=0.5, net_area_m2=9.0, manual_entry=False)


def _panel(n_elements):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.boundaries_panel import BoundariesPanel
    p = HVACProject()
    p.params.apply_city("Ташкент")
    p.constructions["k0"] = Construction(
        key="k0", category="Walls", family="Base", type_name="T",
        thickness_mm=200, u_value=0.5, shgc=0.0)
    sp = Space(space_id="s1", number="R1", name="ROOM", level="L1",
               area_m2=20, volume_m3=60, height_m=3)
    p.spaces.append(sp)
    p._space_by_id["s1"] = sp
    p.elements = [_el(f"e{i}") for i in range(n_elements)]
    panel = BoundariesPanel(p, ProjectBridge(p))
    panel.show_space(sp)
    return panel


def test_height_fits_few_rows(qapp):
    panel = _panel(3)
    row_h = panel.table.verticalHeader().defaultSectionSize()
    # высота ≈ header + 3 строки (с небольшим допуском на рамку)
    assert panel.table.height() < (panel._MAX_VISIBLE_ROWS * row_h)
    assert panel.table.height() >= 3 * row_h


def test_height_capped_for_many_rows(qapp):
    panel = _panel(40)
    row_h = panel.table.verticalHeader().defaultSectionSize()
    cap = panel._MAX_VISIBLE_ROWS
    # потолок: не больше header + cap*row_h + небольшой запас на рамку
    assert panel.table.height() <= cap * row_h + 40
    # и заметно меньше, чем все 40 строк
    assert panel.table.height() < 40 * row_h


def test_height_grows_with_more_rows(qapp):
    assert _panel(6).table.height() > _panel(2).table.height()


def test_cell_combos_are_readonly_pickers(qapp):
    """Регрессия читаемости: комбобоксы-ячейки editable+read-only (текст
    рисуется через QLineEdit, как у остальных комбобоксов приложения), но
    печатать нельзя — только выбор из списка."""
    panel = _panel(1)
    for col in (1, 3, 5):  # конструкция / ориентация / наружное
        combo = panel.table.cellWidget(0, col)
        assert combo.isEditable() is True
        assert combo.lineEdit().isReadOnly() is True


def test_construction_combo_preserves_key(qapp):
    """userData (ключ конструкции) сохраняется при editable-комбобоксе."""
    panel = _panel(1)
    combo = panel.table.cellWidget(0, 1)
    assert combo.currentData() == "k0"
