# -*- coding: utf-8 -*-
"""Acceptance coverage for the CHORSU L02 DXF plan exporter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pytest

# На этой машине ezdxf есть только в C:\Python314; локальный смок на 3.11
# (WATER-venv, уровень CI) без него должен скипаться, а не падать сбором.
ezdxf = pytest.importorskip("ezdxf")

import hvac.design_dxf as design_dxf_module  # noqa: E402
from hvac.design_dxf import (  # noqa: E402
    DEFAULT_TEXT_HEIGHT_MM,
    DXF_OUTPUT_NAME,
    DesignDxfAuditError,
    DesignDxfInputError,
    DesignDxfPlan,
    DxfEntityCounts,
    main,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
REQUEST = FIXTURES / "chorsu-l02-terminal-layout.request.json"
TERMINAL_RESPONSE = FIXTURES / "chorsu-l02-terminal-layout.response.json"
ROUTE_RESPONSE = FIXTURES / "chorsu-l02-route-network.response.json"
LAYER_MAP = Path(design_dxf_module.DEFAULT_LAYER_MAP_PATH)

CHORSU_ROOM_COUNT = 64
CHORSU_PLACEMENT_COUNT = 63
CHORSU_SEGMENT_COUNT = 63

_RECT_SIZE = re.compile(
    r"(?P<width>\d+(?:[.,]\d+)?)\s*[xX\u0445\u0425\u00d7]\s*"
    r"(?P<height>\d+(?:[.,]\d+)?)"
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _paths_with(
    *,
    request: Path = REQUEST,
    terminal: Path = TERMINAL_RESPONSE,
    route: Path = ROUTE_RESPONSE,
) -> tuple[Path, Path, Path]:
    return request, terminal, route


def _plan(
    *,
    request: Path = REQUEST,
    terminal: Path = TERMINAL_RESPONSE,
    route: Path = ROUTE_RESPONSE,
) -> DesignDxfPlan:
    return DesignDxfPlan.from_files(*_paths_with(request=request, terminal=terminal, route=route))


def _repair_response_hash(payload: dict[str, Any]) -> None:
    payload["responseHash"] = design_dxf_module._response_canonical_hash(payload)


def _layer_contract() -> dict[str, Any]:
    return _load_json(LAYER_MAP)


def _polygon_spaces() -> list[dict[str, Any]]:
    request = _load_json(REQUEST)
    return [
        space
        for space in request["spaces"]
        if space["geometry"]["kind"] == "polygon-local"
    ]


def _size_dimensions(size: str) -> tuple[float, float]:
    match = _RECT_SIZE.search(size)
    assert match is not None, f"unexpected CHORSU grille size: {size!r}"
    return (
        float(match.group("width").replace(",", ".")),
        float(match.group("height").replace(",", ".")),
    )


def _expected_placements() -> list[dict[str, Any]]:
    terminal = _load_json(TERMINAL_RESPONSE)
    expected: list[dict[str, Any]] = []
    for result in terminal["results"]:
        for placement in result["placements"]:
            pick = result[f"{placement['direction']}Pick"]
            width, height = _size_dimensions(pick["size"])
            expected.append(
                {
                    "model": pick["model"],
                    "position": tuple(float(placement["positionMm"][axis]) for axis in "xyz"),
                    "width": width,
                    "height": height,
                }
            )
    return expected


def _expected_route_labels() -> list[str]:
    route = _load_json(ROUTE_RESPONSE)
    labels: list[str] = []
    for segment in route["segments"]:
        if segment["shape"] == "round":
            labels.append(f"Ø{segment['size']['dMm']:g}")
        else:
            labels.append(
                f"{segment['size']['wMm']:g}×{segment['size']['hMm']:g}"
            )
    return labels


def _entities_on_layer(modelspace: Any, entity_type: str, layer: str) -> list[Any]:
    return [
        entity
        for entity in modelspace.query(entity_type)
        if entity.dxf.layer == layer
    ]


def _xy_vertices(polyline: Any) -> list[tuple[float, float]]:
    return [(float(point[0]), float(point[1])) for point in polyline.get_points("xy")]


def test_chorsu_dxf_readback_has_exact_contract_entities(tmp_path: Path) -> None:
    plan = _plan()
    output = tmp_path / DXF_OUTPUT_NAME

    counts = plan.to_dxf(output)

    assert counts == DxfEntityCounts(
        room_polylines=CHORSU_ROOM_COUNT,
        grille_inserts=CHORSU_PLACEMENT_COUNT,
        route_polylines=CHORSU_SEGMENT_COUNT,
        route_labels=CHORSU_SEGMENT_COUNT,
    )
    assert output.is_file() and output.stat().st_size > 0

    document = ezdxf.readfile(output)
    auditor = document.audit()
    assert not auditor.has_errors
    assert auditor.errors == []
    assert auditor.fixes == []
    assert document.dxfversion == "AC1024"
    assert document.header["$INSUNITS"] == 4
    assert document.units == 4

    layer_map = _layer_contract()
    assert {
        role: (entry["name"], entry["color"])
        for role, entry in layer_map["layers"].items()
    } == {
        "rooms": ("CRD_ПОМ", 8),
        "ducts": ("CRD_ОВ_ВОЗД", 4),
        "marks": ("CRD_ОВ_МАРКИ", 2),
        "equipment": ("CRD_ОВ_ОБОРУД", 3),
    }
    for entry in layer_map["layers"].values():
        layer = document.layers.get(entry["name"])
        assert layer.dxf.color == entry["color"]

    modelspace = document.modelspace()
    room_layer = layer_map["layers"]["rooms"]["name"]
    duct_layer = layer_map["layers"]["ducts"]["name"]
    marks_layer = layer_map["layers"]["marks"]["name"]
    equipment_layer = layer_map["layers"]["equipment"]["name"]

    room_polylines = _entities_on_layer(modelspace, "LWPOLYLINE", room_layer)
    route_polylines = _entities_on_layer(modelspace, "LWPOLYLINE", duct_layer)
    inserts = _entities_on_layer(modelspace, "INSERT", equipment_layer)
    labels = _entities_on_layer(modelspace, "TEXT", marks_layer)

    assert len(room_polylines) == CHORSU_ROOM_COUNT
    assert len(route_polylines) == CHORSU_SEGMENT_COUNT
    assert len(inserts) == CHORSU_PLACEMENT_COUNT
    assert len(labels) == CHORSU_SEGMENT_COUNT
    assert all(polyline.closed for polyline in room_polylines)
    assert all(len(polyline) >= 3 for polyline in room_polylines)
    assert all(not polyline.closed for polyline in route_polylines)
    assert all(len(polyline) == 2 for polyline in route_polylines)

    polygon_spaces = _polygon_spaces()
    assert len(polygon_spaces) == CHORSU_ROOM_COUNT
    for polyline, space in zip(room_polylines, polygon_spaces, strict=True):
        expected = [tuple(map(float, point)) for point in space["geometry"]["outerBoundaryMm"]]
        if expected[0] == expected[-1]:
            expected.pop()
        actual = _xy_vertices(polyline)
        assert len(actual) == len(expected)
        for actual_point, expected_point in zip(actual, expected, strict=True):
            assert actual_point == pytest.approx(expected_point)

    route = _load_json(ROUTE_RESPONSE)
    nodes = {
        node["nodeId"]: (
            float(node["positionMm"]["x"]),
            float(node["positionMm"]["y"]),
        )
        for node in route["nodes"]
    }
    for polyline, segment in zip(route_polylines, route["segments"], strict=True):
        assert _xy_vertices(polyline) == pytest.approx(
            [nodes[segment["a"]], nodes[segment["b"]]]
        )

    assert [label.dxf.text for label in labels] == _expected_route_labels()
    assert all(label.dxf.height == DEFAULT_TEXT_HEIGHT_MM for label in labels)

    block_name = layer_map["blocks"]["grille"]["name"]
    mark_tag = layer_map["blocks"]["grille"]["markAttribute"]
    block = document.blocks.get(block_name)
    block_outlines = list(block.query("LWPOLYLINE"))
    block_diagonals = list(block.query("LINE"))
    block_attributes = list(block.query("ATTDEF"))
    assert len(block_outlines) == 1
    assert block_outlines[0].closed
    assert len(block_outlines[0]) == 4
    assert len(block_diagonals) == 2
    assert len(block_attributes) == 1
    assert block_attributes[0].dxf.tag == mark_tag

    expected_placements = _expected_placements()
    assert len(expected_placements) == CHORSU_PLACEMENT_COUNT
    for insert, expected in zip(inserts, expected_placements, strict=True):
        assert insert.dxf.name == block_name
        assert tuple(insert.dxf.insert) == pytest.approx(expected["position"])
        assert insert.dxf.xscale == pytest.approx(expected["width"])
        assert insert.dxf.yscale == pytest.approx(expected["height"])
        assert insert.dxf.zscale == pytest.approx(1.0)
        assert len(insert.attribs) == 1
        assert insert.attribs[0].dxf.tag == mark_tag
        assert insert.get_attrib_text(mark_tag) == expected["model"]


def test_custom_route_text_height_survives_readback(tmp_path: Path) -> None:
    custom_height = 375.0
    output = tmp_path / "custom-height.dxf"
    plan = _plan()

    plan.to_dxf(output, text_height_mm=custom_height)

    document = ezdxf.readfile(output)
    layer_map = _layer_contract()
    marks_layer = layer_map["layers"]["marks"]["name"]
    labels = _entities_on_layer(document.modelspace(), "TEXT", marks_layer)
    assert len(labels) == CHORSU_SEGMENT_COUNT
    assert all(label.dxf.height == custom_height for label in labels)
    assert not document.audit().has_errors


@pytest.mark.parametrize(
    ("fixture_name", "field", "value", "error_fragment"),
    [
        ("request", "kind", "foreign-request", "terminal-layout request.*kind"),
        ("terminal", "kind", "foreign-response", "terminal-layout response.*kind"),
        ("route", "kind", "foreign-response", "route-network response.*kind"),
        ("terminal", "status", "READY", "terminal-layout response.*status"),
        ("route", "status", "READY", "route-network response.*status"),
    ],
)
def test_wrong_kind_or_status_is_rejected_before_drawing(
    tmp_path: Path,
    fixture_name: str,
    field: str,
    value: str,
    error_fragment: str,
) -> None:
    sources = {
        "request": REQUEST,
        "terminal": TERMINAL_RESPONSE,
        "route": ROUTE_RESPONSE,
    }
    changed = _load_json(sources[fixture_name])
    changed[field] = value
    changed_path = _write_json(tmp_path / f"invalid-{fixture_name}.json", changed)
    paths = {
        "request": REQUEST,
        "terminal": TERMINAL_RESPONSE,
        "route": ROUTE_RESPONSE,
    }
    paths[fixture_name] = changed_path

    with pytest.raises(DesignDxfInputError, match=error_fragment):
        _plan(**paths)


@pytest.mark.parametrize("fixture_name", ["terminal", "route"])
def test_response_request_id_mismatch_is_rejected(
    tmp_path: Path, fixture_name: str
) -> None:
    source = TERMINAL_RESPONSE if fixture_name == "terminal" else ROUTE_RESPONSE
    changed = _load_json(source)
    changed["requestId"] = "00000000-0000-4000-8000-000000000000"
    changed_path = _write_json(tmp_path / f"wrong-id-{fixture_name}.json", changed)
    paths = {
        "request": REQUEST,
        "terminal": TERMINAL_RESPONSE,
        "route": ROUTE_RESPONSE,
    }
    paths[fixture_name] = changed_path

    with pytest.raises(DesignDxfInputError, match=rf"{fixture_name}\.requestId"):
        _plan(**paths)


@pytest.mark.parametrize("fixture_name", ["terminal", "route"])
def test_response_source_evidence_mismatch_is_rejected(
    tmp_path: Path, fixture_name: str
) -> None:
    source = TERMINAL_RESPONSE if fixture_name == "terminal" else ROUTE_RESPONSE
    changed = _load_json(source)
    changed["sourceEvidence"]["activeDocumentFingerprint"] = "F" * 64
    changed_path = _write_json(tmp_path / f"wrong-evidence-{fixture_name}.json", changed)
    paths = {
        "request": REQUEST,
        "terminal": TERMINAL_RESPONSE,
        "route": ROUTE_RESPONSE,
    }
    paths[fixture_name] = changed_path

    with pytest.raises(DesignDxfInputError, match=rf"{fixture_name}\.sourceEvidence"):
        _plan(**paths)


def test_terminal_raw_request_hash_binds_exact_request_bytes(tmp_path: Path) -> None:
    changed_request = tmp_path / "same-json-different-bytes.json"
    changed_request.write_bytes(REQUEST.read_bytes() + b"\n")

    with pytest.raises(DesignDxfInputError, match=r"terminal\.requestSha256"):
        _plan(request=changed_request)


def test_terminal_canonical_request_hash_binds_request_semantics(tmp_path: Path) -> None:
    changed_request = _load_json(REQUEST)
    changed_request["selection"]["families"] = ["synthetic-family"]
    request_path = _write_json(tmp_path / "semantic-request-change.json", changed_request)

    changed_terminal = _load_json(TERMINAL_RESPONSE)
    changed_terminal["requestSha256"] = hashlib.sha256(
        request_path.read_bytes()
    ).hexdigest().upper()
    terminal_path = _write_json(tmp_path / "terminal-new-raw-hash.json", changed_terminal)

    with pytest.raises(DesignDxfInputError, match=r"terminal\.requestCanonicalHash"):
        _plan(request=request_path, terminal=terminal_path)


@pytest.mark.parametrize("fixture_name", ["terminal", "route"])
def test_response_self_hash_tampering_is_rejected(
    tmp_path: Path, fixture_name: str
) -> None:
    source = TERMINAL_RESPONSE if fixture_name == "terminal" else ROUTE_RESPONSE
    changed = _load_json(source)
    changed["responseHash"] = "0" * 64
    changed_path = _write_json(tmp_path / f"bad-self-hash-{fixture_name}.json", changed)
    paths = {
        "request": REQUEST,
        "terminal": TERMINAL_RESPONSE,
        "route": ROUTE_RESPONSE,
    }
    paths[fixture_name] = changed_path

    with pytest.raises(DesignDxfInputError, match=rf"{fixture_name}\.responseHash"):
        _plan(**paths)


def test_route_request_hash_must_have_canonical_uppercase_shape(tmp_path: Path) -> None:
    changed = _load_json(ROUTE_RESPONSE)
    changed["requestSha256"] = "not-a-sha256"
    _repair_response_hash(changed)
    route_path = _write_json(tmp_path / "invalid-route-request-hash.json", changed)

    with pytest.raises(DesignDxfInputError, match=r"route\.requestSha256"):
        _plan(route=route_path)


def test_responses_must_reference_the_same_hvac_source_tree(tmp_path: Path) -> None:
    changed = _load_json(ROUTE_RESPONSE)
    changed["engineSource"]["sourceTreeSha256"] = "0" * 64
    _repair_response_hash(changed)
    route_path = _write_json(tmp_path / "foreign-hvac-tree.json", changed)

    with pytest.raises(DesignDxfInputError, match="HVAC source trees"):
        _plan(route=route_path)


def test_duplicate_json_property_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "duplicate-key.json"
    invalid.write_text(
        '{"kind":"hvac-terminal-layout-request","kind":"duplicate"}',
        encoding="utf-8",
    )

    with pytest.raises(DesignDxfInputError, match="Повторяющийся JSON-ключ"):
        _plan(request=invalid)


def test_unknown_route_segment_endpoint_is_rejected_after_hash_validation(
    tmp_path: Path,
) -> None:
    changed = _load_json(ROUTE_RESPONSE)
    changed["segments"][0]["a"] = "node:does-not-exist"
    _repair_response_hash(changed)
    route_path = _write_json(tmp_path / "unknown-endpoint.json", changed)

    with pytest.raises(DesignDxfInputError, match="unknown node|неизвестный узел"):
        _plan(route=route_path)


def test_route_terminal_readback_must_match_every_terminal_placement(
    tmp_path: Path,
) -> None:
    changed = _load_json(ROUTE_RESPONSE)
    terminal_node = next(node for node in changed["nodes"] if node["kind"] == "terminal")
    terminal_node["positionMm"]["x"] += 1.0
    _repair_response_hash(changed)
    route_path = _write_json(tmp_path / "foreign-terminal-position.json", changed)

    with pytest.raises(DesignDxfInputError, match="terminal readback"):
        _plan(route=route_path)


def test_cli_is_write_once_and_preserves_first_dxf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_directory = tmp_path / "result"
    arguments = [
        "--request",
        str(REQUEST),
        "--terminal",
        str(TERMINAL_RESPONSE),
        "--route",
        str(ROUTE_RESPONSE),
        "--out",
        str(output_directory),
    ]

    assert main(arguments) == 0
    first_capture = capsys.readouterr()
    output = output_directory / DXF_OUTPUT_NAME
    before = output.read_bytes()
    assert before
    assert str(output) in first_capture.out
    assert first_capture.err == ""

    assert main(arguments) == 2
    second_capture = capsys.readouterr()
    assert output.read_bytes() == before
    assert sorted(path.name for path in output_directory.iterdir()) == [DXF_OUTPUT_NAME]
    assert second_capture.out == ""
    assert "design-dxf: error:" in second_capture.err


def test_cli_does_not_publish_partial_directory_on_export_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_directory = tmp_path / "failed-result"

    def fail_after_partial_write(
        _plan: DesignDxfPlan,
        path: str | Path,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> DxfEntityCounts:
        del text_height_mm
        target = Path(path)
        target.write_bytes(b"partial DXF")
        raise DesignDxfAuditError("synthetic audit failure")

    monkeypatch.setattr(DesignDxfPlan, "to_dxf", fail_after_partial_write)

    result = main(
        [
            "--request",
            str(REQUEST),
            "--terminal",
            str(TERMINAL_RESPONSE),
            "--route",
            str(ROUTE_RESPONSE),
            "--out",
            str(output_directory),
        ]
    )

    assert result == 2
    assert not output_directory.exists()
    assert not list(tmp_path.glob(".design-dxf-*"))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "synthetic audit failure" in captured.err
