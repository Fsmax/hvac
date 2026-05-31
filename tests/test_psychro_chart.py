# -*- coding: utf-8 -*-
"""Тесты построения i-d диаграммы."""

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from hvac.psychro_chart import (
    add_process_to_chart, build_id_chart, render_processes_for_ahu,
    save_id_chart,
)


class TestBuildChart:
    def test_empty_chart(self):
        fig = build_id_chart()
        ax = fig.axes[0]
        assert ax.get_xlabel().startswith("Влагосодержание")
        assert "энтальпия" in ax.get_ylabel().lower()

    def test_title_applied(self):
        fig = build_id_chart(title="Тест")
        assert fig.axes[0].get_title() == "Тест"

    def test_with_processes(self, tmp_path):
        from hvac.ahu_load import AHULoad
        from hvac.ahu_process import compute_ahu_process
        from hvac.models import ProjectParameters

        params = ProjectParameters()
        params.apply_city("Ташкент")
        load = AHULoad(
            system_name="ПВ-1", supply_m3_h=5000,
            t_supply_winter=18, t_supply_summer=18,
            t_indoor_avg_winter=22, t_indoor_avg_summer=24,
            has_recovery=True,
            recovery_eff_winter=0.65, recovery_eff_summer=0.55,
        )
        proc_w = compute_ahu_process(load, params, mode="winter")
        proc_s = compute_ahu_process(load, params, mode="summer")
        fig = build_id_chart(processes=[proc_w, proc_s])
        # Должны быть нанесены точки → коллекций ≥ некоторое число
        ax = fig.axes[0]
        # На графике хотя бы один маркер «o»
        markers = [l for l in ax.lines if l.get_marker() == "o"]
        assert len(markers) > 0

    def test_save_to_file(self, tmp_path):
        fig = build_id_chart()
        path = tmp_path / "chart.png"
        save_id_chart(fig, str(path))
        assert path.exists()
        assert path.stat().st_size > 1000   # не пустой PNG


class TestRenderHelper:
    def test_render_per_ahu(self):
        from hvac.ahu_load import AHULoad
        from hvac.ahu_process import compute_ahu_process
        from hvac.models import ProjectParameters

        params = ProjectParameters()
        params.apply_city("Ташкент")
        load = AHULoad(
            system_name="ПВ-1", supply_m3_h=3000,
            t_supply_winter=18, t_supply_summer=18,
            t_indoor_avg_winter=20, t_indoor_avg_summer=24,
            has_recovery=True,
            recovery_eff_winter=0.65, recovery_eff_summer=0.55,
        )
        ap = {
            "ПВ-1": {
                "winter": compute_ahu_process(load, params, mode="winter"),
                "summer": compute_ahu_process(load, params, mode="summer"),
            }
        }
        fig = render_processes_for_ahu(ap, "ПВ-1",
                                         modes=("winter", "summer"))
        assert "ПВ-1" in fig.axes[0].get_title()

    def test_missing_ahu_returns_empty(self):
        fig = render_processes_for_ahu({}, "несуществующая")
        # Должна быть пустая диаграмма без падения
        assert len(fig.axes) == 1
