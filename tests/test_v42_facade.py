# -*- coding: utf-8 -*-
"""Тесты фасадов v4.2 и JSON roundtrip для underfloor/fancoils/VRF."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space


def _make_project():
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(5):
        sp = Space(
            space_id=f"r{i}", number=f"R-{i:03d}",
            name="Room", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            t_in_heat=20, t_in_cool=24,
            heat_loss_w=1800 + 150 * i,
            heat_gain_w=2500 + 200 * i,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


class TestFacadeUnderfloor:
    def test_design_loops(self):
        p = _make_project()
        result = p.design_underfloor_loops(pitch_mm=150, cover="tile")
        assert len(result) == 5
        for sid, loop in result.items():
            assert loop.q_actual_w > 0
            assert loop.pipe_length_m > 0
        assert p.underfloor_loops is result

    def test_event_emitted(self):
        p = _make_project()
        events = []
        p.subscribe("underfloor_designed", lambda: events.append(1))
        p.design_underfloor_loops()
        assert events == [1]


class TestFacadeFancoils:
    def test_select_for_all(self):
        p = _make_project()
        result = p.select_fancoils_for_project()
        assert result
        for pick in result.values():
            assert pick.actual_cool_w > 0

    def test_pipes_filter(self):
        p = _make_project()
        result = p.select_fancoils_for_project(pipes_filter=4)
        for pick in result.values():
            assert pick.model.pipes == 4


class TestFacadeVRF:
    def test_group_by_level(self):
        p = _make_project()
        # Добавим помещения на втором уровне
        for i in range(3):
            sp = Space(
                space_id=f"r2_{i}", number=f"R2-{i}",
                name="Room", level="L2",
                area_m2=20, volume_m3=60, height_m=3,
                heat_gain_w=2000,
            )
            p.spaces.append(sp)
            p._space_by_id[sp.space_id] = sp
        result = p.build_vrf_systems(group_by="level",
                                       indoor_family="Кассетный")
        assert "VRV-L1" in result
        assert "VRV-L2" in result

    def test_group_by_all(self):
        p = _make_project()
        # Кассетный имеет много типоразмеров — подойдёт для всех помещений
        result = p.build_vrf_systems(group_by="all",
                                       indoor_family="Кассетный")
        assert "VRV-all" in result
        sys = result["VRV-all"]
        assert sys.outdoor is not None
        assert len(sys.indoors) == 5


class TestJsonRoundtrip:
    def test_save_load_v42(self, tmp_path):
        from hvac.io_json import save_project, load_project
        p = _make_project()
        # ПРИМЕЧАНИЕ: не вызываем recalculate() — у помещений нет ограждений,
        # поэтому фактический пересчёт обнулил бы heat_loss_w / heat_gain_w.
        # Тест проверяет roundtrip результатов, а не сам расчёт.
        p.design_underfloor_loops()
        p.select_fancoils_for_project()
        p.build_vrf_systems(group_by="all", indoor_family="Кассетный")

        path = tmp_path / "v42.hvac.json"
        save_project(p, str(path), force_self_contained=True)

        p2 = HVACProject()
        load_project(p2, str(path))

        # Underfloor
        assert p2.underfloor_loops
        for sid, loop in p2.underfloor_loops.items():
            assert loop.pipe is not None
            assert loop.pipe_length_m > 0

        # Fancoils
        assert p2.fancoil_picks
        for pick in p2.fancoil_picks.values():
            assert pick.model.name
            assert pick.actual_cool_w > 0

        # VRF
        assert p2.vrf_systems
        sys = next(iter(p2.vrf_systems.values()))
        assert sys.outdoor is not None
        assert sys.outdoor.name
        assert len(sys.indoors) > 0
