# -*- coding: utf-8 -*-
"""DXF-план из связанных preliminary-артефактов HVAC Calc.

Модуль не выполняет расчёты и не меняет Revit-модель. Он проверяет исходный
``hvac-terminal-layout-request`` и два готовых response-файла Calc, после чего
создаёт однослойный план трасс, решёток и контуров помещений в DXF R2010.

CLI::

    python -m hvac.design_dxf --request request.json \
        --terminal terminal-response.json --route route-response.json \
        --out new-output-directory
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from io import StringIO
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment


REQUEST_KIND = "hvac-terminal-layout-request"
TERMINAL_RESPONSE_KIND = "hvac-terminal-layout-response"
ROUTE_RESPONSE_KIND = "hvac-route-network-response"
PRELIMINARY_STATUS = "PRELIMINARY"

DXF_OUTPUT_NAME = "plan.dxf"
DEFAULT_TEXT_HEIGHT_MM = 250.0
DEFAULT_LAYER_MAP_PATH = Path(__file__).with_name("dwg-layer-map.json")

_LAYER_ROLES = ("rooms", "ducts", "marks", "equipment")
_HASH_PATTERN = re.compile(r"^[0-9A-F]{64}$")
_RECT_SIZE_PATTERN = re.compile(
    r"(?P<width>\d+(?:[.,]\d+)?)\s*[xXхХ×]\s*(?P<height>\d+(?:[.,]\d+)?)"
)
_ROUND_SIZE_PATTERN = re.compile(r"(?:[Øø⌀DД]\s*)?(?P<diameter>\d+(?:[.,]\d+)?)")


class DesignDxfError(ValueError):
    """Базовая контролируемая ошибка DXF-экспорта."""


class DesignDxfInputError(DesignDxfError):
    """Один из входных JSON не соответствует ожидаемой связке Calc."""


class DesignDxfAuditError(DesignDxfError):
    """Созданный документ не прошёл встроенный аудит ezdxf."""


@dataclass(frozen=True, slots=True)
class LayerDefinition:
    """Имя и ACI-цвет одного семантического слоя."""

    name: str
    color: int


@dataclass(frozen=True, slots=True)
class DwgMap:
    """Проверенная конфигурация слоёв и блока УГО."""

    layers: Mapping[str, LayerDefinition]
    grille_block_name: str
    grille_mark_attribute: str


@dataclass(frozen=True, slots=True)
class RoomBoundary:
    """Внешний полигон одного помещения в координатах проекта, мм."""

    space_id: str
    vertices: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class GrillePlacement:
    """Одна фактически размещённая решётка с типоразмером её pick."""

    placement_id: str
    model: str
    size: str
    position: tuple[float, float, float]
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """Один ответный участок сети между двумя узлами."""

    segment_id: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    size_label: str


@dataclass(frozen=True, slots=True)
class DxfEntityCounts:
    """Счётчики сущностей, которые обязаны попасть в modelspace."""

    room_polylines: int
    grille_inserts: int
    route_polylines: int
    route_labels: int


def _reject_constant(value: str) -> None:
    raise DesignDxfInputError(f"Недопустимая JSON-константа: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DesignDxfInputError(f"Повторяющийся JSON-ключ: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes, source: Path, label: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise DesignDxfInputError(f"{label}: UTF-8 BOM запрещён: {source}")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise DesignDxfInputError(f"Не удалось прочитать {label} как UTF-8: {source}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise DesignDxfInputError(f"Некорректный JSON {label}: {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignDxfInputError(f"{label}: ожидался JSON-объект верхнего уровня")
    return value


def _load_json(path: str | Path, label: str) -> tuple[dict[str, Any], bytes]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise DesignDxfInputError(f"Не удалось прочитать {label}: {source}") from exc
    if not raw:
        raise DesignDxfInputError(f"{label}: пустой файл: {source}")
    return _decode_json(raw, source, label), raw


def _as_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DesignDxfInputError(f"{location}: ожидался объект")
    return value


def _as_list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise DesignDxfInputError(f"{location}: ожидался массив")
    return value


def _as_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DesignDxfInputError(f"{location}: ожидалась непустая строка")
    return value


def _as_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesignDxfInputError(f"{location}: ожидалось число")
    number = float(value)
    if not math.isfinite(number):
        raise DesignDxfInputError(f"{location}: число должно быть конечным")
    return number


def _as_point3(value: Any, location: str) -> tuple[float, float, float]:
    point = _as_object(value, location)
    return tuple(
        _as_number(point.get(axis), f"{location}.{axis}") for axis in ("x", "y", "z")
    )  # type: ignore[return-value]


def _normalize_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            raise DesignDxfInputError("canonical hash: найдено неконечное число")
        return 0.0 if number == 0 else number
    return value


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _normalize_numbers(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _request_canonical_hash(request: Mapping[str, Any]) -> str:
    normalized = deepcopy(dict(request))
    spaces = _as_list(normalized.get("spaces"), "request.spaces")
    normalized["spaces"] = sorted(
        spaces,
        key=lambda item: _as_string(
            _as_object(item, "request.spaces[]").get("spaceId"),
            "request.spaces[].spaceId",
        ),
    )
    selection = _as_object(normalized.get("selection"), "request.selection")
    for key in ("families", "kinds"):
        if key in selection:
            selection[key] = sorted(_as_list(selection[key], f"request.selection.{key}"))
    return _canonical_hash(normalized)


def _response_canonical_hash(response: Mapping[str, Any]) -> str:
    return _canonical_hash(
        {key: value for key, value in response.items() if key != "responseHash"}
    )


def _require_hash(value: Any, location: str) -> str:
    text = _as_string(value, location)
    if not _HASH_PATTERN.fullmatch(text):
        raise DesignDxfInputError(f"{location}: ожидался SHA-256 в верхнем регистре")
    return text


def _require_kind(payload: Mapping[str, Any], expected: str, label: str) -> None:
    if payload.get("kind") != expected:
        raise DesignDxfInputError(
            f"{label}: ожидался kind={expected!r}, получен {payload.get('kind')!r}"
        )


def _require_preliminary(payload: Mapping[str, Any], label: str) -> None:
    if payload.get("status") != PRELIMINARY_STATUS:
        raise DesignDxfInputError(
            f"{label}: ожидался status={PRELIMINARY_STATUS!r}, "
            f"получен {payload.get('status')!r}"
        )


def _validate_linkage(
    request: Mapping[str, Any],
    request_raw: bytes,
    terminal: Mapping[str, Any],
    route: Mapping[str, Any],
) -> None:
    _require_kind(request, REQUEST_KIND, "terminal-layout request")
    _require_kind(terminal, TERMINAL_RESPONSE_KIND, "terminal-layout response")
    _require_kind(route, ROUTE_RESPONSE_KIND, "route-network response")
    _require_preliminary(terminal, "terminal-layout response")
    _require_preliminary(route, "route-network response")

    request_id = _as_string(request.get("requestId"), "request.requestId")
    for label, payload in (("terminal", terminal), ("route", route)):
        response_request_id = _as_string(payload.get("requestId"), f"{label}.requestId")
        if response_request_id != request_id:
            raise DesignDxfInputError(
                f"{label}.requestId: response не связан с request {request_id!r}"
            )

    request_evidence = _as_object(request.get("sourceEvidence"), "request.sourceEvidence")
    for label, payload in (("terminal", terminal), ("route", route)):
        evidence = _as_object(payload.get("sourceEvidence"), f"{label}.sourceEvidence")
        if evidence != request_evidence:
            raise DesignDxfInputError(
                f"{label}.sourceEvidence: response не связан с исходным request"
            )

    raw_hash = hashlib.sha256(request_raw).hexdigest().upper()
    if _require_hash(terminal.get("requestSha256"), "terminal.requestSha256") != raw_hash:
        raise DesignDxfInputError("terminal.requestSha256: response не соответствует request")
    canonical_request_hash = _request_canonical_hash(request)
    if (
        _require_hash(
            terminal.get("requestCanonicalHash"), "terminal.requestCanonicalHash"
        )
        != canonical_request_hash
    ):
        raise DesignDxfInputError(
            "terminal.requestCanonicalHash: response не соответствует request"
        )

    for label, payload in (("terminal", terminal), ("route", route)):
        actual = _require_hash(payload.get("responseHash"), f"{label}.responseHash")
        expected = _response_canonical_hash(payload)
        if actual != expected:
            raise DesignDxfInputError(f"{label}.responseHash: canonical hash mismatch")
        # Route-response связан с отдельным route-request, которого нет среди трёх
        # входов ТЗ-23. Эти два поля можно проверить только на форму; полная связь
        # обеспечивается общими requestId/sourceEvidence и terminal-node readback.
        _require_hash(payload.get("requestSha256"), f"{label}.requestSha256")
        _require_hash(
            payload.get("requestCanonicalHash"), f"{label}.requestCanonicalHash"
        )

    terminal_source = _as_object(terminal.get("engineSource"), "terminal.engineSource")
    route_source = _as_object(route.get("engineSource"), "route.engineSource")
    terminal_tree = _require_hash(
        terminal_source.get("sourceTreeSha256"), "terminal.engineSource.sourceTreeSha256"
    )
    route_tree = _require_hash(
        route_source.get("sourceTreeSha256"), "route.engineSource.sourceTreeSha256"
    )
    if terminal_tree != route_tree:
        raise DesignDxfInputError(
            "engineSource.sourceTreeSha256: responses получены из разных HVAC source trees"
        )


def _parse_rooms(request: Mapping[str, Any]) -> tuple[RoomBoundary, ...]:
    rooms: list[RoomBoundary] = []
    seen_space_ids: set[str] = set()
    for index, raw_space in enumerate(_as_list(request.get("spaces"), "request.spaces")):
        location = f"request.spaces[{index}]"
        space = _as_object(raw_space, location)
        space_id = _as_string(space.get("spaceId"), f"{location}.spaceId")
        if space_id in seen_space_ids:
            raise DesignDxfInputError(f"{location}.spaceId: дубликат {space_id!r}")
        seen_space_ids.add(space_id)
        geometry = _as_object(space.get("geometry"), f"{location}.geometry")
        if geometry.get("kind") != "polygon-local":
            continue
        raw_boundary = _as_list(
            geometry.get("outerBoundaryMm"), f"{location}.geometry.outerBoundaryMm"
        )
        if len(raw_boundary) < 3:
            raise DesignDxfInputError(
                f"{location}.geometry.outerBoundaryMm: нужно минимум три вершины"
            )
        vertices: list[tuple[float, float]] = []
        for vertex_index, raw_vertex in enumerate(raw_boundary):
            vertex_location = (
                f"{location}.geometry.outerBoundaryMm[{vertex_index}]"
            )
            vertex = _as_list(raw_vertex, vertex_location)
            if len(vertex) != 2:
                raise DesignDxfInputError(
                    f"{vertex_location}: ожидалась пара координат [x, y]"
                )
            vertices.append(
                (
                    _as_number(vertex[0], f"{vertex_location}[0]"),
                    _as_number(vertex[1], f"{vertex_location}[1]"),
                )
            )
        if vertices[0] == vertices[-1]:
            vertices.pop()
        if len(vertices) < 3 or len(set(vertices)) < 3:
            raise DesignDxfInputError(
                f"{location}.geometry.outerBoundaryMm: вырожденный полигон"
            )
        rooms.append(RoomBoundary(space_id=space_id, vertices=tuple(vertices)))
    return tuple(rooms)


def _parse_size(size: str, location: str) -> tuple[float, float]:
    rectangular = _RECT_SIZE_PATTERN.search(size)
    if rectangular:
        width = float(rectangular.group("width").replace(",", "."))
        height = float(rectangular.group("height").replace(",", "."))
    else:
        round_match = _ROUND_SIZE_PATTERN.fullmatch(size.strip())
        if round_match is None:
            raise DesignDxfInputError(
                f"{location}: не удалось прочитать типоразмер {size!r}"
            )
        width = height = float(round_match.group("diameter").replace(",", "."))
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise DesignDxfInputError(f"{location}: типоразмер должен быть положительным")
    return width, height


def _parse_placements(terminal: Mapping[str, Any]) -> tuple[GrillePlacement, ...]:
    placements: list[GrillePlacement] = []
    seen_ids: set[str] = set()
    for result_index, raw_result in enumerate(
        _as_list(terminal.get("results"), "terminal.results")
    ):
        result_location = f"terminal.results[{result_index}]"
        result = _as_object(raw_result, result_location)
        _as_string(result.get("spaceId"), f"{result_location}.spaceId")
        picks = {
            "supply": result.get("supplyPick"),
            "exhaust": result.get("exhaustPick"),
        }
        for placement_index, raw_placement in enumerate(
            _as_list(result.get("placements"), f"{result_location}.placements")
        ):
            location = f"{result_location}.placements[{placement_index}]"
            placement = _as_object(raw_placement, location)
            placement_id = _as_string(
                placement.get("placementId"), f"{location}.placementId"
            )
            if placement_id in seen_ids:
                raise DesignDxfInputError(
                    f"{location}.placementId: дубликат {placement_id!r}"
                )
            seen_ids.add(placement_id)
            direction = _as_string(placement.get("direction"), f"{location}.direction")
            if direction not in picks:
                raise DesignDxfInputError(
                    f"{location}.direction: неизвестное направление {direction!r}"
                )
            pick = _as_object(picks[direction], f"{result_location}.{direction}Pick")
            model = _as_string(pick.get("model"), f"{result_location}.{direction}Pick.model")
            size = _as_string(pick.get("size"), f"{result_location}.{direction}Pick.size")
            width, height = _parse_size(size, f"{result_location}.{direction}Pick.size")
            placements.append(
                GrillePlacement(
                    placement_id=placement_id,
                    model=model,
                    size=size,
                    position=_as_point3(
                        placement.get("positionMm"), f"{location}.positionMm"
                    ),
                    width_mm=width,
                    height_mm=height,
                )
            )
    return tuple(placements)


def _segment_size_label(segment: Mapping[str, Any], location: str) -> str:
    shape = segment.get("shape")
    size = _as_object(segment.get("size"), f"{location}.size")
    if shape == "round":
        diameter = _as_number(size.get("dMm"), f"{location}.size.dMm")
        if diameter <= 0:
            raise DesignDxfInputError(f"{location}.size.dMm: диаметр должен быть > 0")
        return f"Ø{diameter:g}"
    if shape == "rect":
        width = _as_number(size.get("wMm"), f"{location}.size.wMm")
        height = _as_number(size.get("hMm"), f"{location}.size.hMm")
        if width <= 0 or height <= 0:
            raise DesignDxfInputError(f"{location}.size: размеры должны быть > 0")
        return f"{width:g}×{height:g}"
    raise DesignDxfInputError(f"{location}.shape: неизвестная форма {shape!r}")


def _parse_route(
    route: Mapping[str, Any],
) -> tuple[tuple[RouteSegment, ...], Counter[tuple[float, float, float]]]:
    nodes: dict[str, tuple[float, float, float]] = {}
    terminal_positions: Counter[tuple[float, float, float]] = Counter()
    for node_index, raw_node in enumerate(_as_list(route.get("nodes"), "route.nodes")):
        location = f"route.nodes[{node_index}]"
        node = _as_object(raw_node, location)
        node_id = _as_string(node.get("nodeId"), f"{location}.nodeId")
        if node_id in nodes:
            raise DesignDxfInputError(f"{location}.nodeId: дубликат {node_id!r}")
        position = _as_point3(node.get("positionMm"), f"{location}.positionMm")
        nodes[node_id] = position
        kind = _as_string(node.get("kind"), f"{location}.kind")
        if kind == "terminal":
            terminal_positions[position] += 1

    segments: list[RouteSegment] = []
    seen_segment_ids: set[str] = set()
    for segment_index, raw_segment in enumerate(
        _as_list(route.get("segments"), "route.segments")
    ):
        location = f"route.segments[{segment_index}]"
        segment = _as_object(raw_segment, location)
        segment_id = _as_string(segment.get("segmentId"), f"{location}.segmentId")
        if segment_id in seen_segment_ids:
            raise DesignDxfInputError(
                f"{location}.segmentId: дубликат {segment_id!r}"
            )
        seen_segment_ids.add(segment_id)
        node_a = _as_string(segment.get("a"), f"{location}.a")
        node_b = _as_string(segment.get("b"), f"{location}.b")
        if node_a not in nodes or node_b not in nodes:
            raise DesignDxfInputError(f"{location}: участок ссылается на неизвестный узел")
        segments.append(
            RouteSegment(
                segment_id=segment_id,
                start=nodes[node_a],
                end=nodes[node_b],
                size_label=_segment_size_label(segment, location),
            )
        )
    return tuple(segments), terminal_positions


def _validate_terminal_readback(
    placements: Sequence[GrillePlacement],
    route_terminal_positions: Counter[tuple[float, float, float]],
) -> None:
    expected = Counter(placement.position for placement in placements)
    if route_terminal_positions != expected:
        missing = sum((expected - route_terminal_positions).values())
        foreign = sum((route_terminal_positions - expected).values())
        raise DesignDxfInputError(
            "route.nodes: terminal readback не соответствует terminal placements "
            f"(missing={missing}, foreign={foreign})"
        )


def _load_dwg_map(path: str | Path) -> DwgMap:
    payload, _ = _load_json(path, "dwg-layer-map")
    if payload.get("schemaVersion") != "1.0":
        raise DesignDxfInputError("dwg-layer-map.schemaVersion: ожидалось '1.0'")
    raw_layers = _as_object(payload.get("layers"), "dwg-layer-map.layers")
    if set(raw_layers) != set(_LAYER_ROLES):
        raise DesignDxfInputError(
            "dwg-layer-map.layers: нужны ровно roles " + ", ".join(_LAYER_ROLES)
        )
    layers: dict[str, LayerDefinition] = {}
    layer_names: set[str] = set()
    for role in _LAYER_ROLES:
        entry = _as_object(raw_layers[role], f"dwg-layer-map.layers.{role}")
        name = _as_string(entry.get("name"), f"dwg-layer-map.layers.{role}.name")
        color_value = entry.get("color")
        if isinstance(color_value, bool) or not isinstance(color_value, int):
            raise DesignDxfInputError(
                f"dwg-layer-map.layers.{role}.color: ожидалось целое ACI"
            )
        if not 1 <= color_value <= 255:
            raise DesignDxfInputError(
                f"dwg-layer-map.layers.{role}.color: ACI должен быть 1..255"
            )
        if name.casefold() in layer_names:
            raise DesignDxfInputError(f"dwg-layer-map.layers: повтор слоя {name!r}")
        layer_names.add(name.casefold())
        layers[role] = LayerDefinition(name=name, color=color_value)

    blocks = _as_object(payload.get("blocks"), "dwg-layer-map.blocks")
    grille = _as_object(blocks.get("grille"), "dwg-layer-map.blocks.grille")
    return DwgMap(
        layers=layers,
        grille_block_name=_as_string(
            grille.get("name"), "dwg-layer-map.blocks.grille.name"
        ),
        grille_mark_attribute=_as_string(
            grille.get("markAttribute"),
            "dwg-layer-map.blocks.grille.markAttribute",
        ),
    )


def _positive_text_height(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("высота текста должна быть числом") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("высота текста должна быть конечной и > 0")
    return number


def _assert_audit_clean(document: Drawing, label: str) -> None:
    auditor = document.audit()
    if auditor.has_errors:
        details = "; ".join(str(error) for error in auditor.errors[:5])
        raise DesignDxfAuditError(
            f"ezdxf.audit: {label}: ошибок={len(auditor.errors)}: {details}"
        )


class DesignDxfPlan:
    """Проверенная неизменяемая модель первого DXF-плана."""

    def __init__(
        self,
        request_path: str | Path,
        terminal_path: str | Path,
        route_path: str | Path,
        *,
        layer_map_path: str | Path = DEFAULT_LAYER_MAP_PATH,
    ) -> None:
        request, request_raw = _load_json(request_path, "terminal-layout request")
        terminal, _ = _load_json(terminal_path, "terminal-layout response")
        route, _ = _load_json(route_path, "route-network response")
        _validate_linkage(request, request_raw, terminal, route)

        rooms = _parse_rooms(request)
        placements = _parse_placements(terminal)
        segments, terminal_positions = _parse_route(route)
        _validate_terminal_readback(placements, terminal_positions)

        self.request_id = _as_string(request.get("requestId"), "request.requestId")
        self.rooms = rooms
        self.placements = placements
        self.segments = segments
        self.dwg_map = _load_dwg_map(layer_map_path)

    @classmethod
    def from_files(
        cls,
        request_path: str | Path,
        terminal_path: str | Path,
        route_path: str | Path,
        *,
        layer_map_path: str | Path = DEFAULT_LAYER_MAP_PATH,
    ) -> "DesignDxfPlan":
        """Загрузить и проверить три входных файла без выполнения расчётов."""

        return cls(
            request_path,
            terminal_path,
            route_path,
            layer_map_path=layer_map_path,
        )

    @property
    def expected_counts(self) -> DxfEntityCounts:
        return DxfEntityCounts(
            room_polylines=len(self.rooms),
            grille_inserts=len(self.placements),
            route_polylines=len(self.segments),
            route_labels=len(self.segments),
        )

    def build_document(self, *, text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM) -> Drawing:
        """Построить DXF R2010 в памяти и проверить его встроенным аудитором."""

        if not math.isfinite(text_height_mm) or text_height_mm <= 0:
            raise DesignDxfInputError("text_height_mm: ожидалось конечное число > 0")

        document = ezdxf.new("R2010", units=units.MM)
        document.header["$INSUNITS"] = units.MM
        for role in _LAYER_ROLES:
            layer = self.dwg_map.layers[role]
            document.layers.add(layer.name, color=layer.color)

        grille_block = document.blocks.new(name=self.dwg_map.grille_block_name)
        grille_block.add_lwpolyline(
            [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
            close=True,
            dxfattribs={"layer": "0"},
        )
        grille_block.add_line((-0.5, -0.5), (0.5, 0.5), dxfattribs={"layer": "0"})
        grille_block.add_line((-0.5, 0.5), (0.5, -0.5), dxfattribs={"layer": "0"})
        grille_block.add_attdef(
            self.dwg_map.grille_mark_attribute,
            insert=(0, 0),
            text="",
            height=1.0,
            dxfattribs={"layer": "0", "flags": 1},
        )

        modelspace = document.modelspace()
        room_layer = self.dwg_map.layers["rooms"].name
        for room in self.rooms:
            modelspace.add_lwpolyline(
                room.vertices,
                close=True,
                dxfattribs={"layer": room_layer},
            )

        equipment_layer = self.dwg_map.layers["equipment"].name
        attribute_height = max(1.0, text_height_mm * 0.6)
        for placement in self.placements:
            insert = modelspace.add_blockref(
                self.dwg_map.grille_block_name,
                placement.position,
                dxfattribs={
                    "layer": equipment_layer,
                    "xscale": placement.width_mm,
                    "yscale": placement.height_mm,
                },
            )
            attribute = insert.add_attrib(
                self.dwg_map.grille_mark_attribute,
                placement.model,
                insert=placement.position,
                dxfattribs={
                    "layer": equipment_layer,
                    "height": attribute_height,
                },
            )
            attribute.set_placement(
                placement.position,
                align=TextEntityAlignment.MIDDLE_CENTER,
            )

        duct_layer = self.dwg_map.layers["ducts"].name
        marks_layer = self.dwg_map.layers["marks"].name
        for segment in self.segments:
            modelspace.add_lwpolyline(
                [(segment.start[0], segment.start[1]), (segment.end[0], segment.end[1])],
                dxfattribs={"layer": duct_layer},
            )
            midpoint = (
                (segment.start[0] + segment.end[0]) / 2.0,
                (segment.start[1] + segment.end[1]) / 2.0,
            )
            delta_x = segment.end[0] - segment.start[0]
            delta_y = segment.end[1] - segment.start[1]
            rotation = math.degrees(math.atan2(delta_y, delta_x)) if delta_x or delta_y else 0.0
            if rotation > 90.0:
                rotation -= 180.0
            elif rotation < -90.0:
                rotation += 180.0
            text = modelspace.add_text(
                segment.size_label,
                height=text_height_mm,
                dxfattribs={"layer": marks_layer, "rotation": rotation},
            )
            text.set_placement(midpoint, align=TextEntityAlignment.MIDDLE_CENTER)

        _assert_audit_clean(document, "in-memory document")
        return document

    def to_dxf(
        self,
        path: str | Path,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> DxfEntityCounts:
        """Записать DXF один раз, перечитать и повторно проверить аудитом."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        document = self.build_document(text_height_mm=text_height_mm)
        stream = StringIO()
        document.write(stream)
        payload = stream.getvalue().encode(document.output_encoding)
        try:
            with target.open("xb") as output:
                output.write(payload)
        except FileExistsError:
            raise FileExistsError(f"Файл уже существует, перезапись запрещена: {target}")

        try:
            readback = ezdxf.readfile(target)
            _assert_audit_clean(readback, f"readback {target}")
        except Exception:
            # Удаляется только непрошедший readback файл, созданный этим вызовом.
            target.unlink(missing_ok=True)
            raise
        return self.expected_counts


def build_design_dxf(
    request_path: str | Path,
    terminal_path: str | Path,
    route_path: str | Path,
    *,
    layer_map_path: str | Path = DEFAULT_LAYER_MAP_PATH,
) -> DesignDxfPlan:
    """Функциональный фасад для CLI и будущих CAD-интеграций."""

    return DesignDxfPlan.from_files(
        request_path,
        terminal_path,
        route_path,
        layer_map_path=layer_map_path,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hvac.design_dxf",
        description=(
            "Сформировать DXF R2010 из связанной тройки HVAC terminal-layout "
            "request/response и route-network response"
        ),
    )
    parser.add_argument("--request", required=True, help="terminal-layout request JSON")
    parser.add_argument("--terminal", required=True, help="terminal-layout response JSON")
    parser.add_argument("--route", required=True, help="route-network response JSON")
    parser.add_argument("--out", required=True, help="новый каталог для plan.dxf")
    parser.add_argument(
        "--text-height-mm",
        type=_positive_text_height,
        default=DEFAULT_TEXT_HEIGHT_MM,
        help="высота подписей сечений, мм (по умолчанию: 250)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI с атомарным write-once каталогом ``--out``."""

    args = _argument_parser().parse_args(argv)
    output_directory = Path(args.out)
    try:
        plan = build_design_dxf(args.request, args.terminal, args.route)
        if output_directory.exists():
            raise FileExistsError(
                f"Каталог уже существует, повторный запуск запрещён: {output_directory}"
            )
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix=".design-dxf-", dir=output_directory.parent
        ) as staging_name:
            staging_directory = Path(staging_name)
            plan.to_dxf(
                staging_directory / DXF_OUTPUT_NAME,
                text_height_mm=args.text_height_mm,
            )
            staging_directory.rename(output_directory)
    except (DesignDxfError, FileExistsError, OSError, RuntimeError) as exc:
        print(f"design-dxf: error: {exc}", file=sys.stderr)
        return 2

    print(output_directory / DXF_OUTPUT_NAME)
    return 0


__all__ = [
    "DEFAULT_LAYER_MAP_PATH",
    "DEFAULT_TEXT_HEIGHT_MM",
    "DXF_OUTPUT_NAME",
    "DesignDxfAuditError",
    "DesignDxfError",
    "DesignDxfInputError",
    "DesignDxfPlan",
    "DxfEntityCounts",
    "build_design_dxf",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())
