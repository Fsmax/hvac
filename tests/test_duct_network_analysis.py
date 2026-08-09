"""Contract tests for the strict, explicit-input duct-tree analysis facade."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from hvac.duct_network_analysis import (
    ANALYSIS_METHOD,
    ANALYSIS_PROFILE_VERSION,
    MAXIMUM_DEPTH,
    MAXIMUM_EDGES,
    DuctNetworkAnalysisError,
    DuctNetworkAnalysisSettings,
    DuctNetworkEdgeInput,
    analyze_duct_tree,
)


def _settings(
    rho: float = 1.2,
    friction: float = 0.02,
    margin: float = 1.1,
) -> DuctNetworkAnalysisSettings:
    return DuctNetworkAnalysisSettings(rho, friction, margin)


def _round_edge(
    edge_id: str,
    parent_id: str,
    *,
    terminal_flow: float = 0.0,
    length: float = 10.0,
    diameter: float = 400.0,
    zeta: float = 0.0,
    fixed: float = 0.0,
    terminal_pressure: float = 0.0,
) -> DuctNetworkEdgeInput:
    return DuctNetworkEdgeInput(
        edge_id=edge_id,
        parent_id=parent_id,
        terminal_flow_m3_h=terminal_flow,
        length_m=length,
        shape="round",
        diameter_mm=diameter,
        width_mm=0.0,
        height_mm=0.0,
        local_loss_coefficient=zeta,
        fixed_pressure_loss_pa=fixed,
        terminal_required_pressure_pa=terminal_pressure,
    )


def _rect_edge(
    edge_id: str,
    parent_id: str,
    *,
    terminal_flow: float,
    length: float,
    width: float,
    height: float,
    zeta: float = 0.0,
    fixed: float = 0.0,
    terminal_pressure: float = 0.0,
) -> DuctNetworkEdgeInput:
    return DuctNetworkEdgeInput(
        edge_id=edge_id,
        parent_id=parent_id,
        terminal_flow_m3_h=terminal_flow,
        length_m=length,
        shape="rect",
        diameter_mm=0.0,
        width_mm=width,
        height_mm=height,
        local_loss_coefficient=zeta,
        fixed_pressure_loss_pa=fixed,
        terminal_required_pressure_pa=terminal_pressure,
    )


def _result_edge(result, edge_id: str):
    return next(edge for edge in result.edges if edge.edge_id == edge_id)


class TestStrictCalculation:
    def test_derives_parent_flow_and_reports_all_pressure_parts(self):
        settings = _settings()
        inputs = [
            _round_edge("root", "", length=12.0, diameter=500.0, zeta=0.2),
            _round_edge(
                "a",
                "root",
                terminal_flow=1_000.0,
                length=5.0,
                diameter=250.0,
                zeta=0.5,
                fixed=10.0,
                terminal_pressure=20.0,
            ),
            _rect_edge(
                "b",
                "root",
                terminal_flow=2_000.0,
                length=8.0,
                width=400.0,
                height=200.0,
                zeta=0.3,
                fixed=15.0,
                terminal_pressure=30.0,
            ),
        ]

        result = analyze_duct_tree(inputs, settings=settings)

        assert result.profile_version == ANALYSIS_PROFILE_VERSION
        assert result.method == ANALYSIS_METHOD
        assert result.root_edge_id == "root"
        assert result.root_flow_m3_h == pytest.approx(3_000.0)
        assert result.edge_count == 3
        assert result.terminal_count == 2
        assert [edge.edge_id for edge in result.edges] == ["a", "b", "root"]
        assert [path.terminal_edge_id for path in result.paths] == ["a", "b"]

        root = _result_edge(result, "root")
        assert root.derived_flow_m3_h == pytest.approx(3_000.0)
        assert root.terminal_flow_m3_h == 0.0

        branch = _result_edge(result, "a")
        expected_area = pytest.approx(3.141592653589793 * 0.25**2 / 4.0)
        assert branch.cross_section_area_m2 == expected_area
        assert branch.hydraulic_diameter_m == pytest.approx(0.25)
        assert branch.velocity_m_s == pytest.approx((1_000.0 / 3_600.0) / expected_area.expected)
        assert branch.dynamic_pressure_pa == pytest.approx(
            0.5 * settings.rho_kg_m3 * branch.velocity_m_s**2
        )
        assert branch.friction_pressure_loss_pa == pytest.approx(
            settings.darcy_friction_factor
            * branch.length_m
            / branch.hydraulic_diameter_m
            * branch.dynamic_pressure_pa
        )
        assert branch.local_pressure_loss_pa == pytest.approx(
            0.5 * branch.dynamic_pressure_pa
        )
        assert branch.fixed_pressure_loss_pa == 10.0
        assert branch.terminal_required_pressure_pa == 20.0
        assert branch.total_pressure_loss_pa == pytest.approx(
            branch.friction_pressure_loss_pa
            + branch.local_pressure_loss_pa
            + 10.0
            + 20.0
        )

        critical = next(
            path
            for path in result.paths
            if path.terminal_edge_id == result.critical_terminal_edge_id
        )
        assert critical.edge_ids == result.critical_path_edge_ids
        assert critical.net_pressure_pa == result.critical_path_net_pressure_pa
        assert result.design_pressure_pa == pytest.approx(
            result.critical_path_net_pressure_pa * settings.design_margin_factor
        )
        assert result.flow_continuity_residual_m3_h == pytest.approx(0.0, abs=1e-12)
        assert result.uncertainty_propagation == "not-performed"
        for path in result.paths:
            assert path.equalization_pressure_difference_pa == pytest.approx(
                result.critical_path_net_pressure_pa - path.net_pressure_pa
            )

    def test_one_edge_tree_is_supported(self):
        result = analyze_duct_tree(
            [_round_edge("only", "", terminal_flow=900.0, terminal_pressure=25.0)],
            settings=_settings(),
        )

        assert result.root_edge_id == "only"
        assert result.root_flow_m3_h == 900.0
        assert result.critical_path_edge_ids == ("only",)

    def test_result_is_deterministic_for_input_order_and_pressure_ties(self):
        ordered = [
            _round_edge("root", ""),
            _round_edge("a", "root", terminal_flow=500.0),
            _round_edge("b", "root", terminal_flow=500.0),
        ]

        first = analyze_duct_tree(ordered, settings=_settings())
        second = analyze_duct_tree(list(reversed(ordered)), settings=_settings())

        assert first == second
        assert first.critical_terminal_edge_id == "a"

    def test_result_never_claims_sizing_balancing_fan_normative_or_mutation(self):
        result = analyze_duct_tree(
            [_round_edge("only", "", terminal_flow=1_000.0)],
            settings=_settings(),
        )

        assert result.sizing_performed is False
        assert result.balancing_performed is False
        assert result.fan_selected is False
        assert result.normative_compliance_claimed is False
        assert result.model_mutated is False
        assert result.uncertainty_propagation == "not-performed"

    def test_inputs_and_results_are_immutable(self):
        edge = _round_edge("only", "", terminal_flow=1_000.0)
        result = analyze_duct_tree([edge], settings=_settings())

        with pytest.raises(FrozenInstanceError):
            edge.length_m = 20.0
        with pytest.raises(FrozenInstanceError):
            result.root_edge_id = "changed"


class TestTopologyValidation:
    def test_requires_exactly_one_root(self):
        with pytest.raises(DuctNetworkAnalysisError, match="exactly one root"):
            analyze_duct_tree(
                [
                    _round_edge("a", "", terminal_flow=100.0),
                    _round_edge("b", "", terminal_flow=100.0),
                ],
                settings=_settings(),
            )

    def test_rejects_unknown_parent(self):
        with pytest.raises(DuctNetworkAnalysisError, match="unknown parent"):
            analyze_duct_tree(
                [_round_edge("a", "missing", terminal_flow=100.0)],
                settings=_settings(),
            )

    def test_rejects_disconnected_cycle_even_when_one_root_exists(self):
        with pytest.raises(DuctNetworkAnalysisError, match="cycle"):
            analyze_duct_tree(
                [
                    _round_edge("root", "", terminal_flow=100.0),
                    _round_edge("cycle-a", "cycle-b"),
                    _round_edge("cycle-b", "cycle-a"),
                ],
                settings=_settings(),
            )

    def test_rejects_duplicate_ids(self):
        duplicate = _round_edge("same", "", terminal_flow=100.0)
        with pytest.raises(DuctNetworkAnalysisError, match="duplicate edge_id"):
            analyze_duct_tree([duplicate, duplicate], settings=_settings())

    def test_leaves_must_have_flow_and_internal_edges_must_not(self):
        with pytest.raises(DuctNetworkAnalysisError, match="positive terminal flow"):
            analyze_duct_tree([_round_edge("root", "")], settings=_settings())

        with pytest.raises(DuctNetworkAnalysisError, match="non-leaf edge"):
            analyze_duct_tree(
                [
                    _round_edge("root", "", terminal_flow=100.0),
                    _round_edge("leaf", "root", terminal_flow=100.0),
                ],
                settings=_settings(),
            )

    def test_terminal_pressure_is_leaf_only(self):
        with pytest.raises(DuctNetworkAnalysisError, match="terminal_required_pressure_pa = 0"):
            analyze_duct_tree(
                [
                    _round_edge("root", "", terminal_pressure=10.0),
                    _round_edge("leaf", "root", terminal_flow=100.0),
                ],
                settings=_settings(),
            )

    def test_enforces_edge_depth_and_path_membership_caps(self):
        too_deep = []
        for index in range(MAXIMUM_DEPTH + 1):
            too_deep.append(
                _round_edge(
                    f"e{index:04d}",
                    "" if index == 0 else f"e{index - 1:04d}",
                    terminal_flow=100.0 if index == MAXIMUM_DEPTH else 0.0,
                )
            )
        with pytest.raises(DuctNetworkAnalysisError, match="depth limit"):
            analyze_duct_tree(too_deep, settings=_settings())

        path_heavy = []
        chain_length = MAXIMUM_DEPTH - 1
        for index in range(chain_length):
            path_heavy.append(
                _round_edge(
                    f"c{index:04d}",
                    "" if index == 0 else f"c{index - 1:04d}",
                )
            )
        hub_id = f"c{chain_length - 1:04d}"
        for index in range(102):
            path_heavy.append(
                _round_edge(f"leaf{index:03d}", hub_id, terminal_flow=100.0)
            )
        with pytest.raises(DuctNetworkAnalysisError, match="membership limit"):
            analyze_duct_tree(path_heavy, settings=_settings())

    def test_enforces_edge_cap_before_processing_rows(self):
        repeated = _round_edge("only", "", terminal_flow=100.0)
        with pytest.raises(DuctNetworkAnalysisError, match="edge limit"):
            analyze_duct_tree([repeated] * (MAXIMUM_EDGES + 1), settings=_settings())


class TestValueValidation:
    @pytest.mark.parametrize(
        "settings",
        [
            DuctNetworkAnalysisSettings(float("nan"), 0.02, 1.0),
            DuctNetworkAnalysisSettings(1.2, 0.0, 1.0),
            DuctNetworkAnalysisSettings(1.2, 0.02, 0.99),
            DuctNetworkAnalysisSettings(True, 0.02, 1.0),
        ],
    )
    def test_rejects_invalid_explicit_settings(self, settings):
        with pytest.raises(DuctNetworkAnalysisError):
            analyze_duct_tree(
                [_round_edge("only", "", terminal_flow=100.0)],
                settings=settings,
            )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("terminal_flow_m3_h", float("inf")),
            ("length_m", 0.0),
            ("local_loss_coefficient", -0.1),
            ("fixed_pressure_loss_pa", -1.0),
            ("terminal_required_pressure_pa", True),
        ],
    )
    def test_rejects_invalid_edge_numbers(self, field, value):
        values = {
            "edge_id": "only",
            "parent_id": "",
            "terminal_flow_m3_h": 100.0,
            "length_m": 10.0,
            "shape": "round",
            "diameter_mm": 400.0,
            "width_mm": 0.0,
            "height_mm": 0.0,
            "local_loss_coefficient": 0.0,
            "fixed_pressure_loss_pa": 0.0,
            "terminal_required_pressure_pa": 0.0,
        }
        values[field] = value
        with pytest.raises(DuctNetworkAnalysisError):
            analyze_duct_tree([DuctNetworkEdgeInput(**values)], settings=_settings())

    def test_shape_and_dimensions_are_exact(self):
        invalid = [
            DuctNetworkEdgeInput(
                "round-with-width", "", 100.0, 10.0, "round", 400.0, 1.0, 0.0, 0.0, 0.0, 0.0
            ),
            DuctNetworkEdgeInput(
                "rect-with-diameter", "", 100.0, 10.0, "rect", 1.0, 400.0, 200.0, 0.0, 0.0, 0.0
            ),
            DuctNetworkEdgeInput(
                "oval", "", 100.0, 10.0, "oval", 400.0, 0.0, 0.0, 0.0, 0.0, 0.0
            ),
        ]
        for edge in invalid:
            with pytest.raises(DuctNetworkAnalysisError):
                analyze_duct_tree([edge], settings=_settings())

    @pytest.mark.parametrize("edge_id", ["", " leading", "trailing ", "bad\nline"])
    def test_rejects_invalid_edge_identifiers(self, edge_id):
        with pytest.raises(DuctNetworkAnalysisError):
            analyze_duct_tree(
                [_round_edge(edge_id, "", terminal_flow=100.0)],
                settings=_settings(),
            )

    def test_settings_are_required_and_sequence_is_bounded(self):
        with pytest.raises(TypeError):
            analyze_duct_tree([_round_edge("only", "", terminal_flow=100.0)])
        with pytest.raises(DuctNetworkAnalysisError, match="sequence"):
            analyze_duct_tree(
                (_round_edge(str(index), "", terminal_flow=100.0) for index in range(1)),
                settings=_settings(),
            )
