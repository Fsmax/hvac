# -*- coding: utf-8 -*-
"""Headless-тесты Excel-правок (буфер/fill-down/undo/групповая) в разделах
«Помещения» и «Конструкции» поверх общего движка table_edit.

Пропускаются, если Qt-платформа недоступна.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space, Construction  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


# ======================= Помещения =======================

def _spaces_project(n=4):
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(n):
        sp = Space(space_id=f"r{i}", number=f"R{i}", name="x", level="L1",
                   area_m2=20, volume_m3=60, height_m=3,
                   room_type="Офис", t_in_heat=20.0)
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def _spaces_panel(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.spaces_panel import SpacesPanel
    panel = SpacesPanel(p, ProjectBridge(p))
    panel.proxy.sort(-1)  # детерминированный порядок: proxy == source
    return panel


def _col(key):
    from hvac.ui_qt.panels.spaces_panel import SpacesTableModel
    return next(i for i, c in enumerate(SpacesTableModel.COLUMNS)
               if c.key == key)


def test_spaces_editable_columns(qapp):
    p = _spaces_project()
    panel = _spaces_panel(p)
    assert panel.model._EDITABLE_COLS == {_col("number"),
                                          _col("name"),
                                          _col("level"),
                                          _col("area_m2"),
                                          _col("volume_m3"),
                                          _col("room_type"),
                                          _col("t_in_heat"),
                                          _col("system_heating")}


def test_spaces_text_fields_editable(qapp):
    """Регрессия: имя/этаж/номер помещения правятся прямо в таблице,
    правка отменяется, пустой номер отклоняется."""
    p = _spaces_project()
    panel = _spaces_panel(p)
    m = panel.model
    sp = p.spaces[0]
    old_number, old_name = sp.number, sp.name

    # Имя правится и отменяется (одиночная правка → один undo).
    assert m.setData(m.index(0, _col("name")), "ПЕРЕИМЕНОВАНО", Qt.EditRole)
    assert sp.name == "ПЕРЕИМЕНОВАНО"
    m.undo()
    assert sp.name == old_name

    # Этаж правится.
    assert m.setData(m.index(0, _col("level")), "L42", Qt.EditRole)
    assert sp.level == "L42"

    # Пустой номер недопустим.
    assert not m.setData(m.index(0, _col("number")), "   ", Qt.EditRole)
    assert sp.number == old_number


def test_spaces_area_volume_keep_geometry_consistent(qapp):
    """Площадь/объём правятся в таблице и держат геометрию согласованной:
    объём = площадь × высота. Отрицательные значения отклоняются."""
    p = _spaces_project()
    panel = _spaces_panel(p)
    m = panel.model
    sp = p.spaces[0]
    sp.area_m2, sp.height_m, sp.volume_m3 = 20.0, 3.0, 60.0

    # Правка площади — объём следует за ней (высота фиксирована).
    assert m.setData(m.index(0, _col("area_m2")), 25.0, Qt.EditRole)
    assert sp.area_m2 == 25.0
    assert sp.volume_m3 == 75.0

    # Правка объёма — пересчитывается высота (площадь фиксирована).
    assert m.setData(m.index(0, _col("volume_m3")), 100.0, Qt.EditRole)
    assert sp.volume_m3 == 100.0
    assert sp.height_m == 4.0

    # Отрицательная площадь недопустима.
    assert not m.setData(m.index(0, _col("area_m2")), -1.0, Qt.EditRole)


def test_space_edit_dialog_applies_and_keeps_geometry(qapp, monkeypatch):
    """Окно «Изменить…» правит помещение целиком и держит геометрию
    согласованной; пустой номер отклоняется (исходный сохраняется)."""
    from PySide6.QtWidgets import QMessageBox
    from hvac.ui_qt.panels import spaces_panel as spx

    # Модальные предупреждения не должны блокировать headless-тест.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))

    p = _spaces_project()
    panel = _spaces_panel(p)
    panel.table.setCurrentIndex(panel.proxy.index(0, 0))
    sp = panel._selected_space()
    sp.area_m2, sp.height_m, sp.volume_m3, sp.t_in_heat = 20.0, 3.0, 60.0, 24.0

    def _accept(self):
        self.name_edit.setText("ПЕРЕИМЕНОВАНО")
        self.level_combo.setCurrentText("L07")
        self.area_spin.setValue(30.0)        # высота фиксирована -> объём 90
        self.t_heat_spin.setValue(21.0)
        self.accept()
        return self.result()

    monkeypatch.setattr(spx.SpaceEditDialog, "exec", _accept)
    panel._on_edit()
    assert sp.name == "ПЕРЕИМЕНОВАНО"
    assert sp.level == "L07"
    assert sp.area_m2 == 30.0
    assert sp.height_m == 3.0
    assert sp.volume_m3 == 90.0
    assert sp.t_in_heat == 21.0
    assert sp.user_modified is True

    # Пустой номер -> правка отклоняется, номер не меняется.
    old_number = sp.number
    monkeypatch.setattr(
        spx.SpaceEditDialog, "exec",
        lambda self: (self.number_edit.setText("   "),
                      self.accept(), self.result())[-1])
    panel._on_edit()
    assert sp.number == old_number


def test_spaces_room_type_edit_undo_restores_derived(qapp):
    p = _spaces_project()
    panel = _spaces_panel(p)
    m = panel.model
    p.spaces[0].t_in_heat = 20.0
    m.commit_cell(0, _col("room_type"), "Склад")
    assert p.spaces[0].room_type == "Склад"
    assert p.spaces[0].user_modified is True
    # apply_room_type_defaults сместил t_in_heat; undo должен вернуть всё.
    m.undo()
    assert p.spaces[0].room_type == "Офис"
    assert p.spaces[0].user_modified is False
    assert p.spaces[0].t_in_heat == 20.0


def test_spaces_group_set_via_set_cells(qapp):
    p = _spaces_project()
    panel = _spaces_panel(p)
    col = _col("t_in_heat")
    n = panel.model.set_cells({(r, col): 22.5 for r in range(4)})
    assert n == 4
    assert all(abs(s.t_in_heat - 22.5) < 1e-9 for s in p.spaces)
    panel.model.undo()
    assert all(abs(s.t_in_heat - 20.0) < 1e-9 for s in p.spaces)


def test_spaces_bulk_dialog_result(qapp):
    from hvac.ui_qt.panels.spaces_panel import SpacesBulkDialog
    dlg = SpacesBulkDialog(3, ["Офис", "Склад"], ["Зона A"])
    # по умолчанию первое поле — room_type
    key, val = dlg.result_value()
    assert key == "room_type"
    assert val in ("Офис", "Склад")


def test_spaces_fill_down(qapp):
    p = _spaces_project(3)
    panel = _spaces_panel(p)
    col = _col("t_in_heat")
    panel.model.commit_cell(0, col, "25")
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(3):
        sm.select(panel.proxy.index(r, col), QItemSelectionModel.Select)
    panel._edit.fill_down()
    assert abs(p.spaces[1].t_in_heat - 25.0) < 1e-9
    assert abs(p.spaces[2].t_in_heat - 25.0) < 1e-9


def test_spaces_paste_single_value(qapp):
    p = _spaces_project(3)
    panel = _spaces_panel(p)
    col = _col("t_in_heat")
    QApplication.clipboard().setText("18")
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(3):
        sm.select(panel.proxy.index(r, col), QItemSelectionModel.Select)
    panel._edit.paste()
    assert all(abs(s.t_in_heat - 18.0) < 1e-9 for s in p.spaces)


# ======================= Конструкции =======================

def _constr_project():
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i, (cat, u) in enumerate([("Стены", 0.5), ("Окна", 2.0),
                                  ("Покрытие", 0.3)]):
        c = Construction(key=f"k{i}", category=cat, family="F",
                         type_name=f"T{i}", thickness_mm=200,
                         u_value=u, shgc=0.0)
        p.constructions[c.key] = c
    return p


def _constr_panel(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.constructions_panel import ConstructionsPanel
    panel = ConstructionsPanel(p, ProjectBridge(p))
    panel.proxy.sort(-1)
    return panel


def test_constructions_u_edit_undo_survives_self_reload(qapp):
    """Ключевая регрессия: правка U эмитит constructions_changed → _reload,
    но история отмены сохраняется (состав каталога не изменился)."""
    p = _constr_project()
    panel = _constr_panel(p)
    m = panel.model
    old = m._items[0].u_value
    m.commit_cell(0, m.COL_U, "0.25")
    assert m._items[0].u_value == 0.25
    assert m.can_undo()  # история пережила self-reload
    m.undo()
    assert m._items[0].u_value == old


def test_constructions_u_edit_clears_layers_and_undo_restores(qapp):
    from hvac.models import Layer
    p = _constr_project()
    p.constructions["k0"].layers = [Layer(material="кирпич", thickness_mm=250,
                                          lambda_w_mk=0.7)]
    panel = _constr_panel(p)
    m = panel.model
    row = next(i for i, c in enumerate(m._items) if c.key == "k0")
    m.commit_cell(row, m.COL_U, "0.4")
    assert m._items[row].layers == []   # правка U сбросила слои
    m.undo()
    assert len(m._items[row].layers) == 1  # undo вернул слой


def test_constructions_bulk_set_u_undoable(qapp):
    p = _constr_project()
    panel = _constr_panel(p)
    m = panel.model
    n = m.bulk_set_u([0, 1, 2], 0.9)
    assert n == 3
    assert all(c.u_value == 0.9 for c in m._items)
    m.undo()
    assert [c.u_value for c in m._items] != [0.9, 0.9, 0.9]


def test_constructions_paste_u_column(qapp):
    p = _constr_project()
    panel = _constr_panel(p)
    m = panel.model
    QApplication.clipboard().setText("0.15")
    sm = panel.table.selectionModel()
    sm.clearSelection()
    for r in range(m.rowCount()):
        sm.select(panel.proxy.index(r, m.COL_U), QItemSelectionModel.Select)
    panel._edit.paste()
    assert all(abs(c.u_value - 0.15) < 1e-9 for c in m._items)
