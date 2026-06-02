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
