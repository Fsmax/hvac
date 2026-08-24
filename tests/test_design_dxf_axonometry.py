# -*- coding: utf-8 -*-
"""TZ-31 acceptance coverage for deterministic HVAC axonometry DXFs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ezdxf
import pytest

import hvac.design_dxf as design_dxf_module
from hvac.design_dxf import (
    AXON_TERMINAL_SYMBOL_SIZE_MM,
    DEFAULT_TEXT_HEIGHT_MM,
    DXF_OUTPUT_NAME,
    AxonometryCounts,
    DesignDxfAuditError,
    DesignDxfAxonometry,
    DesignDxfPlan,
    GrillePlacement,
    main,
    project_axonometric_point,
    unproject_axonometric_point,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
CHORSU_REQUEST = FIXTURES / "chorsu-l02-terminal-layout.request.json"
CHORSU_TERMINAL = FIXTURES / "chorsu-l02-terminal-layout.response.json"
CHORSU_ROUTE = FIXTURES / "chorsu-l02-route-network.response.json"
SA01_ROUTE = FIXTURES / "hvac-route-network.response.json"

AXON_LAYER = "CRD_ОВ_АКСО"
CRITICAL_LAYER = "CRD_ОВ_АКСО_ДИКТ"
AXON_LAYERS = {AXON_LAYER, CRITICAL_LAYER}

CHORSU_COUNTS = {
    "EA-CHORSU-L02": AxonometryCounts(
        nodes=29,
        segment_polylines=28,
        critical_segment_polylines=1,
        terminal_inserts=28,
        terminal_marks=28,
        junction_points=0,
        section_labels=28,
        elevation_labels=0,
    ),
    "SA-CHORSU-L02": AxonometryCounts(
        nodes=36,
        segment_polylines=35,
        critical_segment_polylines=1,
        terminal_inserts=35,
        terminal_marks=35,
        junction_points=0,
        section_labels=35,
        elevation_labels=0,
    ),
}

SA01_COUNTS = AxonometryCounts(
    nodes=23,
    segment_polylines=22,
    critical_segment_polylines=12,
    terminal_inserts=6,
    terminal_marks=6,
    junction_points=15,
    section_labels=22,
    elevation_labels=2,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _position(raw_node: dict[str, Any]) -> tuple[float, float, float]:
    point = raw_node["positionMm"]
    return tuple(float(point[axis]) for axis in "xyz")


def _entities_on_axon_layers(modelspace: Any, entity_type: str) -> list[Any]:
    return [
        entity
        for entity in modelspace.query(entity_type)
        if entity.dxf.layer in AXON_LAYERS
    ]


def _xy_vertices(polyline: Any) -> list[tuple[float, float]]:
    return [
        (float(point[0]), float(point[1]))
        for point in polyline.get_points("xy")
    ]


def _text_signature(text: Any) -> tuple[str, float, float, float, float, str]:
    _alignment, anchor, _second_anchor = text.get_placement()
    assert anchor is not None
    return (
        text.dxf.text,
        float(anchor.x),
        float(anchor.y),
        float(text.dxf.height),
        float(text.dxf.rotation),
        text.dxf.layer,
    )


def _assert_r2010_mm_and_clean(document: Any) -> None:
    auditor = document.audit()
    assert not auditor.has_errors
    assert auditor.errors == []
    assert auditor.fixes == []
    assert document.dxfversion == "AC1024"
    assert document.header["$INSUNITS"] == 4
    assert document.units == 4


def _assert_axon_document(
    document: Any,
    axonometry: DesignDxfAxonometry,
    expected: AxonometryCounts,
) -> None:
    _assert_r2010_mm_and_clean(document)
    assert document.layers.get(AXON_LAYER).dxf.color == 4
    assert document.layers.get(CRITICAL_LAYER).dxf.color == 1

    modelspace = document.modelspace()
    polylines = _entities_on_axon_layers(modelspace, "LWPOLYLINE")
    normal_polylines = [
        entity for entity in polylines if entity.dxf.layer == AXON_LAYER
    ]
    critical_polylines = [
        entity for entity in polylines if entity.dxf.layer == CRITICAL_LAYER
    ]
    assert len(polylines) == expected.segment_polylines
    assert len(normal_polylines) == (
        expected.segment_polylines - expected.critical_segment_polylines
    )
    assert len(critical_polylines) == expected.critical_segment_polylines
    assert {entity.dxf.handle for entity in normal_polylines}.isdisjoint(
        entity.dxf.handle for entity in critical_polylines
    )

    projected_nodes = {
        node.node_id: project_axonometric_point(node.position)
        for node in axonometry.nodes
    }
    for polyline, segment in zip(polylines, axonometry.segments, strict=True):
        expected_layer = (
            CRITICAL_LAYER
            if segment.segment_id in axonometry.critical_segment_ids
            else AXON_LAYER
        )
        assert polyline.dxf.layer == expected_layer
        assert not polyline.closed
        assert len(polyline) == 2
        assert _xy_vertices(polyline) == pytest.approx(
            [projected_nodes[segment.node_a], projected_nodes[segment.node_b]]
        )

    inserts = [
        entity
        for entity in modelspace.query("INSERT")
        if entity.dxf.layer == AXON_LAYER
        and entity.dxf.name == axonometry.dwg_map.grille_block_name
    ]
    assert len(inserts) == expected.terminal_inserts
    assert sum(len(insert.attribs) for insert in inserts) == expected.terminal_marks
    assert [
        insert.get_attrib_text(axonometry.dwg_map.grille_mark_attribute)
        for insert in inserts
    ] == [terminal.placement.model for terminal in axonometry.terminals]
    for insert, terminal in zip(inserts, axonometry.terminals, strict=True):
        expected_position = projected_nodes[terminal.node.node_id]
        assert (float(insert.dxf.insert.x), float(insert.dxf.insert.y)) == pytest.approx(
            expected_position
        )
        assert insert.dxf.xscale == pytest.approx(AXON_TERMINAL_SYMBOL_SIZE_MM)
        assert insert.dxf.yscale == pytest.approx(AXON_TERMINAL_SYMBOL_SIZE_MM)
        assert len(insert.attribs) == 1
        attribute = insert.attribs[0]
        assert attribute.dxf.tag == axonometry.dwg_map.grille_mark_attribute
        assert attribute.dxf.text == terminal.placement.model
        assert attribute.dxf.layer == AXON_LAYER

    points = [
        entity
        for entity in modelspace.query("POINT")
        if entity.dxf.layer == AXON_LAYER
    ]
    assert len(points) == expected.junction_points
    expected_junction_positions = [
        projected_nodes[node.node_id]
        for node in axonometry.nodes
        if node.kind == "junction"
    ]
    for point, expected_position in zip(
        points, expected_junction_positions, strict=True
    ):
        assert (float(point.dxf.location.x), float(point.dxf.location.y)) == (
            pytest.approx(expected_position)
        )

    texts = _entities_on_axon_layers(modelspace, "TEXT")
    section_labels = [entity for entity in texts if "м³/ч" in entity.dxf.text]
    elevation_labels = [entity for entity in texts if "м³/ч" not in entity.dxf.text]
    assert len(section_labels) == expected.section_labels
    assert len(elevation_labels) == expected.elevation_labels
    assert [entity.dxf.text for entity in section_labels] == [
        segment.annotation for segment in axonometry.segments
    ]
    for label, segment in zip(section_labels, axonometry.segments, strict=True):
        expected_layer = (
            CRITICAL_LAYER
            if segment.segment_id in axonometry.critical_segment_ids
            else AXON_LAYER
        )
        assert label.dxf.layer == expected_layer


def _chorsu_plan() -> DesignDxfPlan:
    return DesignDxfPlan.from_files(CHORSU_REQUEST, CHORSU_TERMINAL, CHORSU_ROUTE)


def _sa01_axonometry() -> tuple[
    dict[str, Any], tuple[GrillePlacement, ...], DesignDxfAxonometry
]:
    route = _load_json(SA01_ROUTE)
    terminal_nodes = [node for node in route["nodes"] if node["kind"] == "terminal"]
    placements = tuple(
        GrillePlacement(
            placement_id=f"synthetic-placement:{index:02d}",
            model=f"T-{index:02d}",
            size="300×150",
            position=_position(node),
            width_mm=300.0,
            height_mm=150.0,
        )
        for index, node in enumerate(terminal_nodes, start=1)
    )
    assert [placement.model for placement in placements] == [
        "T-01",
        "T-02",
        "T-03",
        "T-04",
        "T-05",
        "T-06",
    ]
    dwg_map = design_dxf_module._load_dwg_map(
        design_dxf_module.DEFAULT_LAYER_MAP_PATH
    )
    axonometries = design_dxf_module._build_axonometry_systems(
        route,
        placements,
        floor_zero_mm=0.0,
        dwg_map=dwg_map,
    )
    assert len(axonometries) == 1
    return route, placements, axonometries[0]


def test_chorsu_plan_has_exact_axonometry_systems_and_counts() -> None:
    plan = _chorsu_plan()

    assert plan.axonometry_system_ids == ("EA-CHORSU-L02", "SA-CHORSU-L02")
    assert [axonometry.output_name for axonometry in plan.axonometries] == [
        "axon-EA-CHORSU-L02.dxf",
        "axon-SA-CHORSU-L02.dxf",
    ]
    for system_id, expected in CHORSU_COUNTS.items():
        axonometry = plan.get_axonometry(system_id)
        assert axonometry.expected_counts == expected
        assert plan.axonometry_counts(system_id) == expected
        assert len(axonometry.nodes) == expected.nodes
        assert len(axonometry.segments) == expected.segment_polylines
        assert len(axonometry.terminals) == expected.terminal_inserts
        assert len(axonometry.critical_segment_ids) == (
            expected.critical_segment_polylines
        )


def test_cli_axon_publishes_plan_and_two_clean_chorsu_system_files_write_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_directory = tmp_path / "chorsu-dxf"
    arguments = [
        "--request",
        str(CHORSU_REQUEST),
        "--terminal",
        str(CHORSU_TERMINAL),
        "--route",
        str(CHORSU_ROUTE),
        "--out",
        str(output_directory),
        "--axon",
    ]

    assert main(arguments) == 0
    first_capture = capsys.readouterr()
    expected_names = [
        DXF_OUTPUT_NAME,
        "axon-EA-CHORSU-L02.dxf",
        "axon-SA-CHORSU-L02.dxf",
    ]
    assert sorted(path.name for path in output_directory.iterdir()) == sorted(
        expected_names
    )
    assert first_capture.out.splitlines() == [
        str(output_directory / name) for name in expected_names
    ]
    assert first_capture.err == ""

    plan = _chorsu_plan()
    plan_document = ezdxf.readfile(output_directory / DXF_OUTPUT_NAME)
    _assert_r2010_mm_and_clean(plan_document)
    for axonometry in plan.axonometries:
        document = ezdxf.readfile(output_directory / axonometry.output_name)
        _assert_axon_document(
            document,
            axonometry,
            CHORSU_COUNTS[axonometry.system_id],
        )

    before = {
        name: (output_directory / name).read_bytes() for name in expected_names
    }
    assert main(arguments) == 2
    second_capture = capsys.readouterr()
    assert second_capture.out == ""
    assert "design-dxf: error:" in second_capture.err
    assert {
        name: (output_directory / name).read_bytes() for name in expected_names
    } == before


def test_sa01_manual_projection_and_inverse_with_retained_y() -> None:
    _route, _placements, axonometry = _sa01_axonometry()
    first_three = axonometry.nodes[:3]
    assert [(node.node_id, node.position) for node in first_three] == [
        ("node:8b08397e47fac54f:000001", (-2000.0, 1000.0, 2600.0)),
        ("node:8b08397e47fac54f:000002", (0.0, 1000.0, 2600.0)),
        ("node:8b08397e47fac54f:000003", (2000.0, -2000.0, 2600.0)),
    ]
    manually_calculated = [
        (-1646.4466094067263, 2953.553390593274),
        (353.5533905932738, 2953.553390593274),
        (1292.8932188134524, 1892.8932188134524),
    ]

    projected = [project_axonometric_point(node.position) for node in first_three]
    for projected_point, expected_point in zip(
        projected, manually_calculated, strict=True
    ):
        assert projected_point == pytest.approx(expected_point)
    for node, projected_point in zip(first_three, projected, strict=True):
        assert unproject_axonometric_point(
            projected_point, node.position[1]
        ) == pytest.approx(node.position)


def test_sa01_file_has_exact_entities_labels_models_and_collision_free_text(
    tmp_path: Path,
) -> None:
    route, placements, axonometry = _sa01_axonometry()
    assert route["systems"][0]["systemId"] == "SA-01"
    assert axonometry.system_id == "SA-01"
    assert axonometry.expected_counts == SA01_COUNTS
    assert [terminal.placement for terminal in axonometry.terminals] == list(placements)

    output = tmp_path / "axon-SA-01.dxf"
    assert axonometry.to_dxf(output) == SA01_COUNTS
    assert output.is_file() and output.stat().st_size > 0

    document = ezdxf.readfile(output)
    _assert_axon_document(document, axonometry, SA01_COUNTS)
    modelspace = document.modelspace()

    polylines = _entities_on_axon_layers(modelspace, "LWPOLYLINE")
    assert sum(entity.dxf.layer == AXON_LAYER for entity in polylines) == 10
    assert sum(entity.dxf.layer == CRITICAL_LAYER for entity in polylines) == 12

    texts = _entities_on_axon_layers(modelspace, "TEXT")
    section_labels = [entity for entity in texts if "м³/ч" in entity.dxf.text]
    elevation_labels = [entity for entity in texts if "м³/ч" not in entity.dxf.text]
    assert len(section_labels) == 22
    assert all("Ø" in entity.dxf.text for entity in section_labels)
    assert all("м³/ч" in entity.dxf.text for entity in section_labels)
    assert sorted(entity.dxf.text for entity in elevation_labels) == [
        "+0.500 м",
        "+2.600 м",
    ]
    assert all(entity.dxf.layer == CRITICAL_LAYER for entity in elevation_labels)

    bounds: list[tuple[str, Any]] = []
    for text in texts:
        signature = _text_signature(text)
        bounds.append(
            (
                signature[0],
                design_dxf_module._rotated_text_bounds(
                    signature[0],
                    (signature[1], signature[2]),
                    height=signature[3],
                    rotation_degrees=signature[4],
                ),
            )
        )
    for index, (left_text, left_bounds) in enumerate(bounds):
        for right_text, right_bounds in bounds[index + 1 :]:
            assert not left_bounds.overlaps(right_bounds), (
                f"overlapping axon labels: {left_text!r} and {right_text!r}"
            )

    first_document = axonometry.build_document()
    second_document = axonometry.build_document()
    assert [
        _text_signature(entity)
        for entity in _entities_on_axon_layers(first_document.modelspace(), "TEXT")
    ] == [
        _text_signature(entity)
        for entity in _entities_on_axon_layers(second_document.modelspace(), "TEXT")
    ]


def test_cli_axon_failure_does_not_publish_partial_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_directory = tmp_path / "failed-axon-result"

    def fail_after_partial_axon_write(
        _axonometry: DesignDxfAxonometry,
        path: str | Path,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> AxonometryCounts:
        del text_height_mm
        Path(path).write_bytes(b"partial axon DXF")
        raise DesignDxfAuditError("synthetic axon audit failure")

    monkeypatch.setattr(
        DesignDxfAxonometry,
        "to_dxf",
        fail_after_partial_axon_write,
    )

    result = main(
        [
            "--request",
            str(CHORSU_REQUEST),
            "--terminal",
            str(CHORSU_TERMINAL),
            "--route",
            str(CHORSU_ROUTE),
            "--out",
            str(output_directory),
            "--axon",
        ]
    )

    assert result == 2
    assert not output_directory.exists()
    assert not list(tmp_path.glob(".design-dxf-*"))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "synthetic axon audit failure" in captured.err
