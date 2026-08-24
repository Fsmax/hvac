# -*- coding: utf-8 -*-
"""DXF-план и аксонометрии из связанных preliminary-артефактов HVAC Calc.

Модуль не выполняет расчёты и не меняет Revit-модель. Он проверяет исходный
``hvac-terminal-layout-request`` и два готовых response-файла Calc, после чего
создаёт план трасс, решёток и контуров помещений в DXF R2010. Опциональный
режим ``--axon`` дополнительно выпускает отдельную однолинейную аксонометрию
каждой системы из route-response.

CLI::

    python -m hvac.design_dxf --request request.json \
        --terminal terminal-response.json --route route-response.json \
        --out new-output-directory [--axon]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
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

AXON_RECEDING_AXIS_ANGLE_DEGREES = 45.0
"""Угол уходящей оси Y в косоугольной фронтальной проекции, градусы."""

AXON_DEPTH_SCALE = 0.5
"""Коэффициент укорочения уходящей оси Y (cabinet projection)."""

AXON_COS_45_HALF = (
    math.cos(math.radians(AXON_RECEDING_AXIS_ANGLE_DEGREES)) * AXON_DEPTH_SCALE
)
"""Добавка координаты Y к проектной X': ``cos(45°) * 0.5``."""

AXON_SIN_45_HALF = (
    math.sin(math.radians(AXON_RECEDING_AXIS_ANGLE_DEGREES)) * AXON_DEPTH_SCALE
)
"""Добавка координаты Y к проектной Y': ``sin(45°) * 0.5``."""

AXON_OUTPUT_PREFIX = "axon-"
AXON_TERMINAL_SYMBOL_SIZE_MM = 300.0
AXON_LABEL_GLYPH_WIDTH_FACTOR = 1.0
AXON_LABEL_PADDING_FACTOR = 0.35
AXON_LABEL_MAX_ATTEMPTS = 256

_PLAN_LAYER_ROLES = ("rooms", "ducts", "marks", "equipment")
_AXON_LAYER_ROLES = ("axonDucts", "axonCriticalDucts")
_LAYER_ROLES = _PLAN_LAYER_ROLES + _AXON_LAYER_ROLES
_HASH_PATTERN = re.compile(r"^[0-9A-F]{64}$")
_RECT_SIZE_PATTERN = re.compile(
    r"(?P<width>\d+(?:[.,]\d+)?)\s*[xXхХ×]\s*(?P<height>\d+(?:[.,]\d+)?)"
)
_ROUND_SIZE_PATTERN = re.compile(r"(?:[Øø⌀DД]\s*)?(?P<diameter>\d+(?:[.,]\d+)?)")
_WINDOWS_RESERVED_STEMS = {
    "AUX",
    "CLOCK$",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


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


@dataclass(frozen=True, slots=True)
class AxonNode:
    """Один узел route-графа, используемый в аксонометрии."""

    node_id: str
    position: tuple[float, float, float]
    kind: str


@dataclass(frozen=True, slots=True)
class AxonSegment:
    """Один проверенный участок системы для аксонометрического DXF."""

    segment_id: str
    node_a: str
    node_b: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    system_id: str
    kind: str
    size_label: str
    flow_m3h: float

    @property
    def annotation(self) -> str:
        """Подпись сечения и расхода без повторного расчёта сети."""

        return f"{self.size_label} · {self.flow_m3h:g} м³/ч"

    @property
    def is_riser(self) -> bool:
        """Явный стояк из авторитетного ``segment.kind`` route-response."""

        return self.kind == "riser"


@dataclass(frozen=True, slots=True)
class AxonTerminal:
    """Терминальный узел route-графа и доказанная марка terminal-response."""

    node: AxonNode
    placement: GrillePlacement


@dataclass(frozen=True, slots=True)
class AxonometryCounts:
    """Проверяемые счётчики исходного графа и сущностей одной аксонометрии."""

    nodes: int
    segment_polylines: int
    critical_segment_polylines: int
    terminal_inserts: int
    terminal_marks: int
    junction_points: int
    section_labels: int
    elevation_labels: int


@dataclass(frozen=True, slots=True)
class _AxonSystemDefinition:
    system_id: str
    critical_segment_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _TextBounds:
    left: float
    bottom: float
    right: float
    top: float

    def overlaps(self, other: "_TextBounds") -> bool:
        return not (
            self.right <= other.left
            or other.right <= self.left
            or self.top <= other.bottom
            or other.top <= self.bottom
        )


def project_axonometric_point(
    point: Sequence[float],
) -> tuple[float, float]:
    """Спроецировать ``(x, y, z)`` в абсолютные координаты ``(X', Y')``.

    Фронтальная плоскость X-Z сохраняет масштаб, а ось Y уходит под 45° с
    укорочением 0,5. Все координаты остаются в миллиметрах.
    """

    if len(point) != 3:
        raise DesignDxfInputError("axon point: ожидались три координаты (x, y, z)")
    x = _as_number(point[0], "axon point.x")
    y = _as_number(point[1], "axon point.y")
    z = _as_number(point[2], "axon point.z")
    return (
        x + y * AXON_COS_45_HALF,
        z + y * AXON_SIN_45_HALF,
    )


def unproject_axonometric_point(
    projected: Sequence[float],
    source_y_mm: float,
) -> tuple[float, float, float]:
    """Восстановить 3D-точку при сохранённой исходной координате Y.

    Само отображение 3D -> 2D не является взаимно однозначным. Эта функция
    служит контролируемым readback для точек, где глубина Y известна из
    route-response.
    """

    if len(projected) != 2:
        raise DesignDxfInputError("axon projected point: ожидались координаты (X', Y')")
    projected_x = _as_number(projected[0], "axon projected point.X")
    projected_y = _as_number(projected[1], "axon projected point.Y")
    source_y = _as_number(source_y_mm, "axon source y")
    return (
        projected_x - source_y * AXON_COS_45_HALF,
        source_y,
        projected_y - source_y * AXON_SIN_45_HALF,
    )


# Короткие алиасы удобны для CAD-адаптеров; длинные имена оставлены основными.
project_axon_point = project_axonometric_point
unproject_axon_point = unproject_axonometric_point


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


def _infer_floor_zero_mm(request: Mapping[str, Any]) -> float:
    """Получить datum этажа без ужесточения старого контракта plan.dxf."""

    elevations: list[float] = []
    raw_spaces = request.get("spaces")
    if not isinstance(raw_spaces, list):
        return 0.0
    for raw_space in raw_spaces:
        if not isinstance(raw_space, dict):
            continue
        geometry = raw_space.get("geometry")
        if not isinstance(geometry, dict):
            continue
        for key in ("zFloorMm", "floorElevationMm"):
            value = geometry.get(key)
            if (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
            ):
                elevations.append(float(value))
                break
    return min(elevations, default=0.0)


def _axon_output_name(system_id: str) -> str:
    """Сформировать безопасное write-once имя без изменения systemId."""

    if len(system_id) > 128:
        raise DesignDxfInputError("route.systems[].systemId: слишком длинное имя файла")
    if system_id in {".", ".."} or system_id.rstrip(" .") != system_id:
        raise DesignDxfInputError(
            f"route.systems[].systemId: небезопасное имя файла {system_id!r}"
        )
    if any(character in '<>:"/\\|?*' or ord(character) < 32 for character in system_id):
        raise DesignDxfInputError(
            f"route.systems[].systemId: небезопасное имя файла {system_id!r}"
        )
    stem = system_id.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_STEMS:
        raise DesignDxfInputError(
            f"route.systems[].systemId: зарезервированное имя файла {system_id!r}"
        )
    return f"{AXON_OUTPUT_PREFIX}{system_id}.dxf"


def _parse_axon_route(
    route: Mapping[str, Any],
) -> tuple[
    dict[str, AxonNode],
    tuple[AxonSegment, ...],
    tuple[_AxonSystemDefinition, ...],
]:
    """Строго разобрать данные, нужные только режиму аксонометрии."""

    nodes: dict[str, AxonNode] = {}
    for node_index, raw_node in enumerate(_as_list(route.get("nodes"), "route.nodes")):
        location = f"route.nodes[{node_index}]"
        node = _as_object(raw_node, location)
        node_id = _as_string(node.get("nodeId"), f"{location}.nodeId")
        if node_id in nodes:
            raise DesignDxfInputError(f"{location}.nodeId: дубликат {node_id!r}")
        nodes[node_id] = AxonNode(
            node_id=node_id,
            position=_as_point3(node.get("positionMm"), f"{location}.positionMm"),
            kind=_as_string(node.get("kind"), f"{location}.kind"),
        )

    segments: list[AxonSegment] = []
    segment_ids: set[str] = set()
    for segment_index, raw_segment in enumerate(
        _as_list(route.get("segments"), "route.segments")
    ):
        location = f"route.segments[{segment_index}]"
        segment = _as_object(raw_segment, location)
        segment_id = _as_string(segment.get("segmentId"), f"{location}.segmentId")
        if segment_id in segment_ids:
            raise DesignDxfInputError(
                f"{location}.segmentId: дубликат {segment_id!r}"
            )
        segment_ids.add(segment_id)
        node_a = _as_string(segment.get("a"), f"{location}.a")
        node_b = _as_string(segment.get("b"), f"{location}.b")
        if node_a not in nodes or node_b not in nodes:
            raise DesignDxfInputError(f"{location}: участок ссылается на неизвестный узел")
        flow_m3h = _as_number(segment.get("flowM3h"), f"{location}.flowM3h")
        if flow_m3h < 0:
            raise DesignDxfInputError(f"{location}.flowM3h: расход должен быть >= 0")
        segments.append(
            AxonSegment(
                segment_id=segment_id,
                node_a=node_a,
                node_b=node_b,
                start=nodes[node_a].position,
                end=nodes[node_b].position,
                system_id=_as_string(segment.get("systemId"), f"{location}.systemId"),
                kind=_as_string(segment.get("kind"), f"{location}.kind"),
                size_label=_segment_size_label(segment, location),
                flow_m3h=flow_m3h,
            )
        )

    raw_systems = _as_list(route.get("systems"), "route.systems")
    if not raw_systems:
        raise DesignDxfInputError("route.systems: для --axon нужна минимум одна система")
    definitions: list[_AxonSystemDefinition] = []
    seen_system_ids: set[str] = set()
    output_names: set[str] = set()
    segments_by_system: dict[str, set[str]] = defaultdict(set)
    for segment in segments:
        segments_by_system[segment.system_id].add(segment.segment_id)

    for system_index, raw_system in enumerate(raw_systems):
        location = f"route.systems[{system_index}]"
        system = _as_object(raw_system, location)
        system_id = _as_string(system.get("systemId"), f"{location}.systemId")
        if system_id in seen_system_ids:
            raise DesignDxfInputError(f"{location}.systemId: дубликат {system_id!r}")
        seen_system_ids.add(system_id)
        output_name = _axon_output_name(system_id).casefold()
        if output_name in output_names:
            raise DesignDxfInputError(
                f"{location}.systemId: коллизия имени axon-файла {system_id!r}"
            )
        output_names.add(output_name)

        critical_ids: list[str] = []
        for critical_index, value in enumerate(
            _as_list(
                system.get("criticalPathSegmentIds"),
                f"{location}.criticalPathSegmentIds",
            )
        ):
            critical_ids.append(
                _as_string(
                    value,
                    f"{location}.criticalPathSegmentIds[{critical_index}]",
                )
            )
        if len(critical_ids) != len(set(critical_ids)):
            raise DesignDxfInputError(
                f"{location}.criticalPathSegmentIds: повторяющийся segmentId"
            )
        foreign = set(critical_ids) - segments_by_system.get(system_id, set())
        if foreign:
            raise DesignDxfInputError(
                f"{location}.criticalPathSegmentIds: участки не принадлежат системе: "
                + ", ".join(sorted(foreign))
            )
        definitions.append(
            _AxonSystemDefinition(
                system_id=system_id,
                critical_segment_ids=frozenset(critical_ids),
            )
        )

    segment_system_ids = set(segments_by_system)
    if seen_system_ids != segment_system_ids:
        missing = sorted(segment_system_ids - seen_system_ids)
        empty = sorted(seen_system_ids - segment_system_ids)
        raise DesignDxfInputError(
            "route.systems: состав не соответствует route.segments "
            f"(missing={missing}, withoutSegments={empty})"
        )
    definitions.sort(key=lambda item: (item.system_id.casefold(), item.system_id))
    return nodes, tuple(segments), tuple(definitions)


def _match_axon_terminals(
    nodes: Mapping[str, AxonNode],
    placements: Sequence[GrillePlacement],
) -> dict[str, GrillePlacement]:
    """Связать terminal-node с моделью по уже проверенному XYZ-readback."""

    terminal_positions = Counter(
        node.position for node in nodes.values() if node.kind == "terminal"
    )
    _validate_terminal_readback(placements, terminal_positions)
    buckets: dict[tuple[float, float, float], deque[GrillePlacement]] = defaultdict(deque)
    for placement in sorted(placements, key=lambda item: item.placement_id):
        buckets[placement.position].append(placement)

    result: dict[str, GrillePlacement] = {}
    for node in sorted(nodes.values(), key=lambda item: item.node_id):
        if node.kind == "terminal":
            result[node.node_id] = buckets[node.position].popleft()
    return result


def _build_axonometry_systems(
    route: Mapping[str, Any],
    placements: Sequence[GrillePlacement],
    *,
    floor_zero_mm: float,
    dwg_map: DwgMap,
) -> tuple["DesignDxfAxonometry", ...]:
    """Собрать по route.systems отдельные неизменяемые модели листов."""

    nodes, segments, definitions = _parse_axon_route(route)
    terminal_placements = _match_axon_terminals(nodes, placements)
    result: list[DesignDxfAxonometry] = []
    for definition in definitions:
        system_segments = tuple(
            segment for segment in segments if segment.system_id == definition.system_id
        )
        node_ids = {
            node_id
            for segment in system_segments
            for node_id in (segment.node_a, segment.node_b)
        }
        system_nodes = tuple(node for node in nodes.values() if node.node_id in node_ids)
        terminals = tuple(
            AxonTerminal(node=node, placement=terminal_placements[node.node_id])
            for node in system_nodes
            if node.kind == "terminal"
        )
        result.append(
            DesignDxfAxonometry(
                system_id=definition.system_id,
                nodes=system_nodes,
                segments=system_segments,
                terminals=terminals,
                critical_segment_ids=definition.critical_segment_ids,
                floor_zero_mm=floor_zero_mm,
                dwg_map=dwg_map,
            )
        )
    return tuple(result)


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


def _upright_text_rotation(start: tuple[float, float], end: tuple[float, float]) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    rotation = math.degrees(math.atan2(delta_y, delta_x)) if delta_x or delta_y else 0.0
    if rotation > 90.0:
        rotation -= 180.0
    elif rotation < -90.0:
        rotation += 180.0
    return rotation


def _unit_direction(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        raise DesignDxfInputError(
            "axon projection: участок выродился в точку после проецирования"
        )
    return delta_x / length, delta_y / length


def _estimated_text_size(text: str, height: float) -> tuple[float, float]:
    return max(height, len(text) * height * AXON_LABEL_GLYPH_WIDTH_FACTOR), height


def _rotated_text_bounds(
    text: str,
    center: tuple[float, float],
    *,
    height: float,
    rotation_degrees: float,
) -> _TextBounds:
    width, text_height = _estimated_text_size(text, height)
    half_width = width / 2.0
    half_height = text_height / 2.0
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    corners = []
    for local_x, local_y in (
        (-half_width, -half_height),
        (-half_width, half_height),
        (half_width, half_height),
        (half_width, -half_height),
    ):
        corners.append(
            (
                center[0] + local_x * cosine - local_y * sine,
                center[1] + local_x * sine + local_y * cosine,
            )
        )
    padding = height * AXON_LABEL_PADDING_FACTOR
    return _TextBounds(
        left=min(point[0] for point in corners) - padding,
        bottom=min(point[1] for point in corners) - padding,
        right=max(point[0] for point in corners) + padding,
        top=max(point[1] for point in corners) + padding,
    )


class _DeterministicTextLayout:
    """Детерминированно сдвигает подписи вдоль заданного направления."""

    def __init__(self) -> None:
        self._occupied: list[_TextBounds] = []

    def place(
        self,
        text: str,
        anchor: tuple[float, float],
        direction: tuple[float, float],
        *,
        height: float,
        rotation_degrees: float,
    ) -> tuple[float, float]:
        direction_length = math.hypot(*direction)
        if direction_length == 0:
            unit_x, unit_y = 1.0, 0.0
        else:
            unit_x = direction[0] / direction_length
            unit_y = direction[1] / direction_length
        width, _ = _estimated_text_size(text, height)
        step = width + 2.0 * height * AXON_LABEL_PADDING_FACTOR

        for attempt in range(AXON_LABEL_MAX_ATTEMPTS):
            if attempt == 0:
                multiplier = 0
            else:
                distance_index = (attempt + 1) // 2
                multiplier = distance_index if attempt % 2 else -distance_index
            candidate = (
                anchor[0] + unit_x * step * multiplier,
                anchor[1] + unit_y * step * multiplier,
            )
            bounds = _rotated_text_bounds(
                text,
                candidate,
                height=height,
                rotation_degrees=rotation_degrees,
            )
            if not any(bounds.overlaps(occupied) for occupied in self._occupied):
                self._occupied.append(bounds)
                return candidate
        raise DesignDxfInputError(
            "axon labels: не удалось детерминированно устранить пересечение подписей"
        )


def _format_elevation(z_mm: float, floor_zero_mm: float) -> str:
    elevation_m = (z_mm - floor_zero_mm) / 1000.0
    if math.isclose(elevation_m, 0.0, abs_tol=5e-10):
        return "±0.000 м"
    return f"{elevation_m:+.3f} м"


class DesignDxfAxonometry:
    """Проверенная неизменяемая модель аксонометрии одной route-системы."""

    def __init__(
        self,
        *,
        system_id: str,
        nodes: Sequence[AxonNode],
        segments: Sequence[AxonSegment],
        terminals: Sequence[AxonTerminal],
        critical_segment_ids: frozenset[str],
        floor_zero_mm: float,
        dwg_map: DwgMap,
    ) -> None:
        self.system_id = system_id
        self.nodes = tuple(nodes)
        self.segments = tuple(segments)
        self.terminals = tuple(terminals)
        self.critical_segment_ids = critical_segment_ids
        self.floor_zero_mm = floor_zero_mm
        self.dwg_map = dwg_map

        if not self.nodes or not self.segments:
            raise DesignDxfInputError(
                f"route.systems[{system_id!r}]: аксонометрия не может быть пустой"
            )
        if not math.isfinite(floor_zero_mm):
            raise DesignDxfInputError("axon floor zero: ожидалось конечное число")
        missing_layers = [role for role in _AXON_LAYER_ROLES if role not in dwg_map.layers]
        if missing_layers:
            raise DesignDxfInputError(
                "dwg-layer-map.layers: для --axon отсутствуют roles "
                + ", ".join(missing_layers)
            )
        segment_ids = {segment.segment_id for segment in self.segments}
        if not critical_segment_ids <= segment_ids:
            raise DesignDxfInputError(
                f"route.systems[{system_id!r}]: критический путь содержит чужой участок"
            )
        terminal_node_ids = [terminal.node.node_id for terminal in self.terminals]
        if len(terminal_node_ids) != len(set(terminal_node_ids)):
            raise DesignDxfInputError(
                f"route.systems[{system_id!r}]: повторяющийся terminal-node"
            )

    @property
    def output_name(self) -> str:
        return _axon_output_name(self.system_id)

    @property
    def _riser_node_ids(self) -> frozenset[str]:
        return frozenset(
            node_id
            for segment in self.segments
            if segment.is_riser
            for node_id in (segment.node_a, segment.node_b)
        )

    @property
    def expected_counts(self) -> AxonometryCounts:
        riser_node_ids = self._riser_node_ids
        return AxonometryCounts(
            nodes=len(self.nodes),
            segment_polylines=len(self.segments),
            critical_segment_polylines=len(self.critical_segment_ids),
            terminal_inserts=len(self.terminals),
            terminal_marks=len(self.terminals),
            junction_points=sum(node.kind == "junction" for node in self.nodes),
            section_labels=len(self.segments),
            elevation_labels=sum(node.node_id in riser_node_ids for node in self.nodes),
        )

    def _projected_nodes(self) -> dict[str, tuple[float, float]]:
        projected = {
            node.node_id: project_axonometric_point(node.position) for node in self.nodes
        }
        for segment in self.segments:
            if projected[segment.node_a] == projected[segment.node_b]:
                raise DesignDxfInputError(
                    f"route.segments[{segment.segment_id!r}]: "
                    "участок выродился после axon-проекции"
                )
        return projected

    def build_document(self, *, text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM) -> Drawing:
        """Построить и проаудировать DXF R2010 одной системы в памяти."""

        if not math.isfinite(text_height_mm) or text_height_mm <= 0:
            raise DesignDxfInputError("text_height_mm: ожидалось конечное число > 0")

        document = ezdxf.new("R2010", units=units.MM)
        document.header["$INSUNITS"] = units.MM
        document.header["$PDMODE"] = 3
        for role in _LAYER_ROLES:
            layer = self.dwg_map.layers[role]
            document.layers.add(layer.name, color=layer.color)

        terminal_block = document.blocks.new(name=self.dwg_map.grille_block_name)
        terminal_block.add_circle((0.0, 0.0), radius=0.5, dxfattribs={"layer": "0"})
        terminal_block.add_line((-0.5, 0.0), (0.5, 0.0), dxfattribs={"layer": "0"})
        terminal_block.add_line((0.0, -0.5), (0.0, 0.5), dxfattribs={"layer": "0"})
        terminal_block.add_attdef(
            self.dwg_map.grille_mark_attribute,
            insert=(0.75, 0.0),
            text="",
            height=0.25,
            dxfattribs={"layer": "0"},
        )

        modelspace = document.modelspace()
        normal_layer = self.dwg_map.layers["axonDucts"].name
        critical_layer = self.dwg_map.layers["axonCriticalDucts"].name
        projected_nodes = self._projected_nodes()

        for segment in self.segments:
            layer = (
                critical_layer
                if segment.segment_id in self.critical_segment_ids
                else normal_layer
            )
            modelspace.add_lwpolyline(
                [projected_nodes[segment.node_a], projected_nodes[segment.node_b]],
                dxfattribs={"layer": layer},
            )

        for node in self.nodes:
            if node.kind == "junction":
                modelspace.add_point(
                    projected_nodes[node.node_id],
                    dxfattribs={"layer": normal_layer},
                )

        layout = _DeterministicTextLayout()
        for segment in self.segments:
            start = projected_nodes[segment.node_a]
            end = projected_nodes[segment.node_b]
            direction = _unit_direction(start, end)
            midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            rotation = _upright_text_rotation(start, end)
            position = layout.place(
                segment.annotation,
                midpoint,
                direction,
                height=text_height_mm,
                rotation_degrees=rotation,
            )
            layer = (
                critical_layer
                if segment.segment_id in self.critical_segment_ids
                else normal_layer
            )
            text = modelspace.add_text(
                segment.annotation,
                height=text_height_mm,
                dxfattribs={"layer": layer, "rotation": rotation},
            )
            text.set_placement(position, align=TextEntityAlignment.MIDDLE_CENTER)

        riser_node_ids = self._riser_node_ids
        critical_riser_node_ids = {
            node_id
            for segment in self.segments
            if segment.is_riser and segment.segment_id in self.critical_segment_ids
            for node_id in (segment.node_a, segment.node_b)
        }
        for node in self.nodes:
            if node.node_id not in riser_node_ids:
                continue
            annotation = _format_elevation(node.position[2], self.floor_zero_mm)
            anchor = projected_nodes[node.node_id]
            position = layout.place(
                annotation,
                anchor,
                (0.0, 1.0),
                height=text_height_mm,
                rotation_degrees=0.0,
            )
            layer = (
                critical_layer if node.node_id in critical_riser_node_ids else normal_layer
            )
            text = modelspace.add_text(
                annotation,
                height=text_height_mm,
                dxfattribs={"layer": layer},
            )
            text.set_placement(position, align=TextEntityAlignment.MIDDLE_CENTER)

        terminal_mark_height = max(1.0, text_height_mm * 0.75)
        for terminal in self.terminals:
            node_id = terminal.node.node_id
            projected = projected_nodes[node_id]
            incident = next(
                segment
                for segment in self.segments
                if node_id in (segment.node_a, segment.node_b)
            )
            other_node_id = (
                incident.node_b if incident.node_a == node_id else incident.node_a
            )
            outward = _unit_direction(projected_nodes[other_node_id], projected)
            mark_width, _ = _estimated_text_size(
                terminal.placement.model, terminal_mark_height
            )
            mark_anchor = (
                projected[0]
                + outward[0]
                * (
                    AXON_TERMINAL_SYMBOL_SIZE_MM / 2.0
                    + mark_width / 2.0
                    + terminal_mark_height * AXON_LABEL_PADDING_FACTOR
                ),
                projected[1]
                + outward[1]
                * (
                    AXON_TERMINAL_SYMBOL_SIZE_MM / 2.0
                    + mark_width / 2.0
                    + terminal_mark_height * AXON_LABEL_PADDING_FACTOR
                ),
            )
            mark_position = layout.place(
                terminal.placement.model,
                mark_anchor,
                outward,
                height=terminal_mark_height,
                rotation_degrees=0.0,
            )
            insert = modelspace.add_blockref(
                self.dwg_map.grille_block_name,
                projected,
                dxfattribs={
                    "layer": normal_layer,
                    "xscale": AXON_TERMINAL_SYMBOL_SIZE_MM,
                    "yscale": AXON_TERMINAL_SYMBOL_SIZE_MM,
                },
            )
            attribute = insert.add_attrib(
                self.dwg_map.grille_mark_attribute,
                terminal.placement.model,
                insert=mark_position,
                dxfattribs={"layer": normal_layer, "height": terminal_mark_height},
            )
            attribute.set_placement(
                mark_position,
                align=TextEntityAlignment.MIDDLE_CENTER,
            )

        _assert_audit_clean(document, f"in-memory axonometry {self.system_id}")
        return document

    def _readback_counts(self, document: Drawing) -> AxonometryCounts:
        modelspace = document.modelspace()
        normal_layer = self.dwg_map.layers["axonDucts"].name
        critical_layer = self.dwg_map.layers["axonCriticalDucts"].name
        axon_layers = {normal_layer, critical_layer}
        polylines = [
            entity
            for entity in modelspace.query("LWPOLYLINE")
            if entity.dxf.layer in axon_layers
        ]
        inserts = [
            entity
            for entity in modelspace.query("INSERT")
            if entity.dxf.layer == normal_layer
            and entity.dxf.name == self.dwg_map.grille_block_name
        ]
        texts = [
            entity
            for entity in modelspace.query("TEXT")
            if entity.dxf.layer in axon_layers
        ]
        section_labels = sum("м³/ч" in entity.dxf.text for entity in texts)
        return AxonometryCounts(
            nodes=len(self.nodes),
            segment_polylines=len(polylines),
            critical_segment_polylines=sum(
                entity.dxf.layer == critical_layer for entity in polylines
            ),
            terminal_inserts=len(inserts),
            terminal_marks=sum(len(insert.attribs) for insert in inserts),
            junction_points=sum(
                entity.dxf.layer == normal_layer for entity in modelspace.query("POINT")
            ),
            section_labels=section_labels,
            elevation_labels=len(texts) - section_labels,
        )

    def to_dxf(
        self,
        path: str | Path,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> AxonometryCounts:
        """Записать одну аксонометрию write-once, перечитать и сверить счётчики."""

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
            actual_counts = self._readback_counts(readback)
            if actual_counts != self.expected_counts:
                raise DesignDxfAuditError(
                    f"axon readback counts {self.system_id}: "
                    f"expected={self.expected_counts}, actual={actual_counts}"
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return actual_counts


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
        self.floor_zero_mm = _infer_floor_zero_mm(request)
        self._route_payload = route
        self._axonometry_cache: tuple[DesignDxfAxonometry, ...] | None = None

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

    @property
    def axonometries(self) -> tuple[DesignDxfAxonometry, ...]:
        """Лениво построить строгие модели всех route.systems."""

        if self._axonometry_cache is None:
            self._axonometry_cache = _build_axonometry_systems(
                self._route_payload,
                self.placements,
                floor_zero_mm=self.floor_zero_mm,
                dwg_map=self.dwg_map,
            )
        return self._axonometry_cache

    @property
    def axonometry_system_ids(self) -> tuple[str, ...]:
        return tuple(axonometry.system_id for axonometry in self.axonometries)

    def get_axonometry(self, system_id: str) -> DesignDxfAxonometry:
        """Вернуть одну аксонометрию по точному systemId."""

        for axonometry in self.axonometries:
            if axonometry.system_id == system_id:
                return axonometry
        raise DesignDxfInputError(f"route.systems: неизвестная система {system_id!r}")

    def axonometry_counts(self, system_id: str) -> AxonometryCounts:
        return self.get_axonometry(system_id).expected_counts

    def build_axonometry_document(
        self,
        system_id: str,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> Drawing:
        return self.get_axonometry(system_id).build_document(
            text_height_mm=text_height_mm
        )

    def to_axonometry_dxf(
        self,
        system_id: str,
        path: str | Path,
        *,
        text_height_mm: float = DEFAULT_TEXT_HEIGHT_MM,
    ) -> AxonometryCounts:
        return self.get_axonometry(system_id).to_dxf(
            path,
            text_height_mm=text_height_mm,
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
    parser.add_argument(
        "--out",
        required=True,
        help="новый каталог для plan.dxf и опциональных axon-<systemId>.dxf",
    )
    parser.add_argument(
        "--axon",
        action="store_true",
        help="дополнительно выпустить аксонометрию каждой route-системы",
    )
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
    published_names = [DXF_OUTPUT_NAME]
    try:
        plan = build_design_dxf(args.request, args.terminal, args.route)
        axonometries = plan.axonometries if args.axon else ()
        published_names.extend(axonometry.output_name for axonometry in axonometries)
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
            for axonometry in axonometries:
                axonometry.to_dxf(
                    staging_directory / axonometry.output_name,
                    text_height_mm=args.text_height_mm,
                )
            staging_directory.rename(output_directory)
    except (DesignDxfError, FileExistsError, OSError, RuntimeError) as exc:
        print(f"design-dxf: error: {exc}", file=sys.stderr)
        return 2

    for name in published_names:
        print(output_directory / name)
    return 0


__all__ = [
    "AXON_COS_45_HALF",
    "AXON_DEPTH_SCALE",
    "AXON_OUTPUT_PREFIX",
    "AXON_RECEDING_AXIS_ANGLE_DEGREES",
    "AXON_SIN_45_HALF",
    "AXON_TERMINAL_SYMBOL_SIZE_MM",
    "AxonometryCounts",
    "DEFAULT_LAYER_MAP_PATH",
    "DEFAULT_TEXT_HEIGHT_MM",
    "DXF_OUTPUT_NAME",
    "DesignDxfAxonometry",
    "DesignDxfAuditError",
    "DesignDxfError",
    "DesignDxfInputError",
    "DesignDxfPlan",
    "DxfEntityCounts",
    "build_design_dxf",
    "main",
    "project_axon_point",
    "project_axonometric_point",
    "unproject_axon_point",
    "unproject_axonometric_point",
]


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())
