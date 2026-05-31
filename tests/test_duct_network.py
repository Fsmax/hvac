# -*- coding: utf-8 -*-
"""Тесты детального аэродинамического расчёта сети."""

import pytest
from hvac.duct_network import (
    DuctEdge, DuctFitting, DuctNetworkDetailed, LOCAL_LOSS_COEFFICIENTS,
    make_simple_tree,
)


class TestDuctFitting:
    def test_known_kind(self):
        f = DuctFitting(kind="elbow_90_round_r15d")
        assert f.coefficient() == pytest.approx(0.22)

    def test_zeta_overrides_kind(self):
        f = DuctFitting(kind="elbow_90_round_r15d", zeta=1.5)
        assert f.coefficient() == pytest.approx(1.5)

    def test_quantity_multiplies(self):
        f = DuctFitting(kind="elbow_90_round_r15d", quantity=3)
        assert f.coefficient() == pytest.approx(0.22 * 3)

    def test_pressure_drop_v_squared(self):
        """Δp = ζ·ρv²/2. ζ=0.5, v=10 м/с → Δp = 0.5·1.2·100/2 = 30 Па."""
        f = DuctFitting(zeta=0.5)
        dp = f.pressure_drop_pa(velocity_m_s=10.0)
        assert dp == pytest.approx(30.0, rel=0.01)

    def test_extra_pressure_adds(self):
        """Фильтр: ζ=0 + 100 Па из каталога."""
        f = DuctFitting(extra_pressure_pa=100.0)
        dp = f.pressure_drop_pa(velocity_m_s=5.0)
        assert dp == pytest.approx(100.0)


class TestDuctEdge:
    def test_round_geometry(self):
        e = DuctEdge(edge_id="e1", flow_m3_h=1000.0, length_m=10.0,
                     shape="round", diameter_mm=315)
        e.compute()
        # v = (1000/3600) / (π·0.315²/4) = 0.278/0.0779 = 3.57 м/с
        assert e.velocity_m_s == pytest.approx(3.57, rel=0.02)
        # Δp_тр > 0
        assert e.dp_friction_pa > 0
        # Local = 0 без фитингов
        assert e.dp_local_pa == 0.0

    def test_rect_uses_hydraulic_diameter(self):
        e = DuctEdge(edge_id="e1", flow_m3_h=1500.0, length_m=5.0,
                     shape="rect", width_mm=400, height_mm=200)
        e.compute()
        assert e.velocity_m_s > 0
        assert e.dp_friction_pa > 0

    def test_local_loss_adds(self):
        e = DuctEdge(edge_id="e1", flow_m3_h=1000.0, length_m=5.0,
                     shape="round", diameter_mm=315,
                     fittings=[DuctFitting(kind="elbow_90_round_r15d")])
        e.compute()
        assert e.dp_local_pa > 0
        assert e.dp_total_pa == pytest.approx(
            e.dp_friction_pa + e.dp_local_pa)


class TestNetworkTopology:
    def test_simple_tree_branches(self):
        """Магистраль + 3 ветви → 3 пути от корня."""
        net = make_simple_tree(
            "ПВ-1",
            trunk_flow_m3_h=3000.0, trunk_len_m=15.0, trunk_d_mm=400,
            terminals=[
                ("Помещение A", 1000.0, 5.0, 250),
                ("Помещение B", 1000.0, 8.0, 250),
                ("Помещение C", 1000.0, 12.0, 250),
            ],
        )
        net.compute()
        assert len(net.branches) == 3
        # Каждая ветвь проходит через корень
        for b in net.branches:
            assert b.edges[0] == "trunk"

    def test_critical_branch_is_longest(self):
        """Самое длинное ответвление становится диктующим."""
        net = make_simple_tree(
            "ПВ-2",
            trunk_flow_m3_h=2000.0, trunk_len_m=10.0, trunk_d_mm=355,
            terminals=[
                ("ближнее", 1000.0, 2.0, 250),
                ("дальнее", 1000.0, 15.0, 250),
            ],
        )
        net.compute()
        critical = next(b for b in net.branches
                        if b.terminal_edge_id == net.critical_branch_id)
        assert critical.terminal_name == "дальнее"

    def test_balancing_dp_for_short_branches(self):
        """Не-диктующие ветви получают balancing_dp_pa > 0."""
        net = make_simple_tree(
            "ПВ-3",
            trunk_flow_m3_h=2000.0, trunk_len_m=10.0, trunk_d_mm=355,
            terminals=[
                ("A", 1000.0, 2.0, 250),
                ("B", 1000.0, 15.0, 250),
            ],
        )
        net.compute()
        sorted_branches = sorted(net.branches, key=lambda b: b.dp_total_pa)
        assert sorted_branches[0].balancing_dp_pa > 0
        assert sorted_branches[-1].balancing_dp_pa == 0.0   # сама диктующая


class TestFanSelection:
    def test_fan_flow_sums_terminals(self):
        net = make_simple_tree(
            "ПВ", 3000.0, 10.0, 400,
            terminals=[("A", 1500.0, 5.0, 280),
                       ("B", 1500.0, 5.0, 280)],
        )
        net.compute()
        assert net.fan_flow_m3_h == pytest.approx(3000.0)

    def test_fan_pressure_includes_safety(self):
        net = make_simple_tree(
            "ПВ", 1000.0, 10.0, 315,
            terminals=[("A", 1000.0, 5.0, 250)],
        )
        net.compute()
        critical = net.branches[0]
        # +10% запас по умолчанию
        assert net.fan_pressure_required_pa == pytest.approx(
            critical.dp_total_pa * 1.10, rel=0.001)

    def test_summary_keys(self):
        net = make_simple_tree(
            "ПВ", 1000.0, 5.0, 315,
            terminals=[("A", 1000.0, 3.0, 250)],
        )
        net.compute()
        s = net.summary()
        for key in ("n_edges", "n_terminals", "fan_flow_m3_h",
                     "fan_pressure_pa", "critical_branch",
                     "max_velocity_m_s"):
            assert key in s


class TestCustomFitting:
    def test_filter_with_catalog_pressure(self):
        """Фильтр задан как фиксированное Δp — не зависит от скорости."""
        net = DuctNetworkDetailed(system_name="test")
        net.add_edge(DuctEdge(
            edge_id="e1", parent_id="", flow_m3_h=2000.0,
            length_m=1.0, shape="round", diameter_mm=400,
            fittings=[DuctFitting(extra_pressure_pa=80.0, note="filter F7")],
            terminal_name="t", is_terminal=True,
        ))
        net.compute()
        assert net.branches[0].dp_total_pa >= 80.0
