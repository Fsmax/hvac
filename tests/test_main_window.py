# -*- coding: utf-8 -*-
"""Headless smoke-тест главного окна.

Проверяет, что MainWindow собирается: регистрируются команды (через
functools.partial), создаётся командная палитра (cmd_palette). Страховка
для типизации main_window. Пропускается, если Qt недоступен.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


def _project() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(3):
        sp = Space(
            space_id=f"r{i}", number=f"R{i}", name="Офис", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            heat_loss_w=1500, heat_gain_w=2000, heat_gain_sensible_w=1500,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def test_main_window_builds(qapp):
    from hvac.ui_qt.main_window import MainWindow

    w = MainWindow(_project())
    # Команды зарегистрированы (часть — через functools.partial).
    assert len(w.commands.all()) > 0
    # Палитра ещё не создана (ленивая), атрибут существует.
    assert w.cmd_palette is None


def test_smoke_panel_add_system_shows_row(qapp, monkeypatch):
    """Регрессия: «Добавить» в панели дымоудаления реально создаёт систему
    и сразу показывает её в таблице.

    Раньше код сравнивал ``dlg.exec() != dlg.Accepted`` — доступ к enum
    через экземпляр (``dlg.Accepted``) в новых PySide6 бросает
    AttributeError уже ПОСЛЕ закрытия диалога, исключение глоталось циклом
    событий, и система молча не добавлялась.
    """
    import hvac.ui_qt.panels.smoke_panel as sp_mod
    from hvac.ui_qt.bridge import ProjectBridge

    proj = _project()
    panel = sp_mod.SmokePanel(proj, ProjectBridge(proj))
    assert panel.table.rowCount() == 0

    # Диалог принимаем автоматически, подставив имя.
    def _fake_exec(self):
        self.name_edit.setText("СДУ-Т")
        self._on_ok()
        return self.result()

    monkeypatch.setattr(sp_mod.SmokeSystemDialog, "exec", _fake_exec)

    panel._add_system()

    assert "СДУ-Т" in proj.smoke_systems
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "СДУ-Т"


def test_smoke_panel_attach_spaces(qapp):
    """«Привязать помещения»: диалог с чекбоксами привязывает отмеченные
    помещения к выбранной СДУ/СПВ и отвязывает снятые; СПВ пишет в
    pressurization_system, не трогая привязку к СДУ."""
    from PySide6.QtCore import Qt

    import hvac.ui_qt.panels.smoke_panel as sp_mod
    from hvac.ui_qt.bridge import ProjectBridge

    proj = _project()
    sm = proj.create_smoke_system_manual(
        "СДУ-Т", calc_method="kmk_zone_perimeter")
    panel = sp_mod.SmokePanel(proj, ProjectBridge(proj))

    # Диалог: изначально ни одно помещение не привязано.
    dlg = sp_mod.SmokeAttachDialog(proj, sm)
    assert dlg.checked_ids() == set()
    assert dlg.table.rowCount() == 3

    # Чекбокс первой строки добавляет её space_id в выбор.
    item = dlg.table.item(0, 0)
    item.setCheckState(Qt.Checked)
    assert item.data(Qt.UserRole) in dlg.checked_ids()

    # Применение diff: привязка r0+r1, затем только r1 (r0 отвязывается).
    assert panel._apply_attachment(sm, {"r0", "r1"}) == (2, 0)
    assert proj._space_by_id["r0"].smoke_system == "СДУ-Т"
    assert panel._apply_attachment(sm, {"r1"}) == (0, 1)
    assert proj._space_by_id["r0"].smoke_system == ""
    assert proj._space_by_id["r1"].smoke_system == "СДУ-Т"

    # СПВ (air_supply) работает с pressurization_system.
    spv = proj.create_smoke_system_manual(
        "СПВ-Т", system_type="air_supply", purpose="stairs",
        calc_method="manual", L_smoke_m3h=8000.0)
    assert panel._apply_attachment(spv, {"r1"}) == (1, 0)
    assert proj._space_by_id["r1"].pressurization_system == "СПВ-Т"
    assert proj._space_by_id["r1"].smoke_system == "СДУ-Т"

    # Повторное открытие диалога показывает текущую привязку системы.
    dlg2 = sp_mod.SmokeAttachDialog(proj, sm)
    assert dlg2.checked_ids() == {"r1"}


def test_smoke_dialog_fire_perimeter_auto_checkbox(qapp):
    """Чекбокс авто-P (ф.4): включён — спин P заблокирован и значение не
    перезаписывается; выключен — ручной P сохраняется, флаг снимается."""
    from hvac.smoke import SmokeSystem
    from hvac.ui_qt.widgets.smoke_system_dialog import SmokeSystemDialog

    sm = SmokeSystem(name="СДУ-Т", calc_method="kmk_zone_perimeter",
                     fire_perimeter_m=5.0, fire_perimeter_auto=True)
    dlg = SmokeSystemDialog(None, system=sm, norm_code="KMK_UZ", is_new=False)
    assert dlg.fire_perim_auto_chk.isChecked()
    assert not dlg.fire_perim_spin.isEnabled()

    # Авто включён: OK не перетирает P значением спина
    dlg.fire_perim_spin.setValue(9.0)
    dlg._on_ok()
    assert dlg.system.fire_perimeter_auto is True
    assert dlg.system.fire_perimeter_m == 5.0

    # Ручной режим: спин разблокирован, значение сохраняется
    dlg2 = SmokeSystemDialog(None, system=dlg.system, norm_code="KMK_UZ",
                             is_new=False)
    dlg2.fire_perim_auto_chk.setChecked(False)
    assert dlg2.fire_perim_spin.isEnabled()
    dlg2.fire_perim_spin.setValue(9.0)
    dlg2._on_ok()
    assert dlg2.system.fire_perimeter_auto is False
    assert dlg2.system.fire_perimeter_m == 9.0


def test_data_panel_true_north_global_rotation(qapp):
    """Глобальный поворот сторон света: поле True North в панели «Данные»
    пишет project.params.true_north_offset_deg и применяется движком ко
    всем ориентациям (стена N при +45° считается как NE)."""
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.data_panel import DataPanel
    from hvac.parsers import effective_orientation

    proj = _project()
    panel = DataPanel(proj, ProjectBridge(proj))
    assert panel.true_north_spin.value() == 0.0

    panel.true_north_spin.setValue(45.0)
    assert proj.params.true_north_offset_deg == 45.0
    # Движок применяет глобальный поворот ко всем фасадам.
    assert effective_orientation("N", 0.0, 45.0) == "NE"

    # Значение подтягивается обратно из проекта.
    proj.params.true_north_offset_deg = -30.0
    panel._refresh_from_project()
    assert panel.true_north_spin.value() == -30.0


def test_data_panel_solar_shading_presets(qapp):
    """Защита от солнца (жалюзи): выбор пресета пишет solar_shading_factor;
    нестандартное значение показывается ближайшим пресетом, не меняя его."""
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.data_panel import DataPanel

    proj = _project()
    panel = DataPanel(proj, ProjectBridge(proj))
    factors = [panel.shading_combo.itemData(i)
               for i in range(panel.shading_combo.count())]
    assert factors == [1.0, 0.7, 0.5, 0.3]

    # Выбор «внешние ламели» (0.5) пишет параметр.
    panel.shading_combo.setCurrentIndex(2)
    assert proj.params.solar_shading_factor == 0.5

    # Кастомное значение из старого проекта → ближайший пресет, параметр цел.
    proj.params.solar_shading_factor = 0.6
    panel._refresh_from_project()
    assert panel.shading_combo.currentData() == 0.7   # ближайший к 0.6
    assert proj.params.solar_shading_factor == 0.6
