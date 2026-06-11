# -*- coding: utf-8 -*-
"""Headless smoke-тест панели «Инженерия».

Проверяет, что панель и все 10 вкладок создаются и переводятся без
ошибок — страховка для разбиения engineering_panel на пакет.
Пропускается, если Qt недоступен (например CI без графической среды).
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover - среда без Qt-платформы
        pytest.skip(f"Qt-платформа недоступна: {exc}")
    return app


def _project() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(3):
        sp = Space(
            space_id=f"r{i}", number=f"R{i}", name="Офис", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            heat_gain_w=2000, heat_loss_w=1500, heat_gain_sensible_w=1500,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def test_panel_builds_with_all_tabs(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.engineering_panel import EngineeringPanel

    project = _project()
    panel = EngineeringPanel(project, ProjectBridge(project))

    tabs = panel.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == len(EngineeringPanel.TAB_KEYS) == 10

    # Перевод обходит виджеты всех вкладок — ловит сломанные ссылки.
    panel.retranslate_ui()
