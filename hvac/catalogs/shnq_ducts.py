# -*- coding: utf-8 -*-
"""Непроверенные нормы воздуховодов и воздухораспределения ШНҚ 2.04.05-22.

Модуль только загружает и фильтрует нормативный каталог. Он намеренно не связан
с ``duct_sizing`` и ``duct_network``: все записи имеют статус ``unverified`` либо
``unreadable`` и не должны влиять на расчёт до инженерной верификации.

В первоисточнике нет таблицы фиксированных скоростей для магистралей и ответвлений
по типам зданий. ``duct_velocity_limits()`` поэтому возвращает только фактически
найденные численные нормы отверстий/проёмов и не применяет скрытые подстановки.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast


NormStatus = Literal["unverified", "unreadable"]


class ShnqDuctCatalogError(ValueError):
    """Каталог ШНҚ не соответствует fail-fast контракту загрузчика."""


@dataclass(frozen=True, slots=True)
class DuctNormRange:
    """Числовой интервал; отсутствующая граница означает отсутствие ограничения."""

    minimum: float | None
    maximum: float | None
    minimum_inclusive: bool
    maximum_inclusive: bool


@dataclass(frozen=True, slots=True)
class DuctNormSource:
    """Точная ссылка на физическую страницу первоисточника."""

    document: str
    edition: str
    clause: str
    page_pdf: int
    table: str | None


@dataclass(frozen=True, slots=True)
class DuctNormEntry:
    """Одна нормативная запись вместе с областью применения и источником."""

    key: str
    value: float | None
    range: DuctNormRange | None
    unit: str
    applies_to: Mapping[str, tuple[str, ...]]
    source: DuctNormSource
    status: NormStatus
    note_ru: str


@dataclass(frozen=True, slots=True)
class DuctNormCatalog:
    """Типизированное неизменяемое представление JSON-каталога."""

    schema_version: str
    document: str
    edition: str
    entries: tuple[DuctNormEntry, ...]


_DOCUMENT = "ШНҚ 2.04.05-22"
_SCHEMA_VERSION = "1.0"
_KEY_RE = re.compile(r"^[a-z0-9]+(?:[._][a-z0-9]+)*$")
_TOP_LEVEL_KEYS = {"schemaVersion", "document", "edition", "entries"}
_ENTRY_BASE_KEYS = {"key", "unit", "appliesTo", "source", "status", "noteRu"}
_SOURCE_KEYS = {"document", "edition", "clause", "pagePdf", "table"}
_RANGE_KEYS = {"min", "max", "minInclusive", "maxInclusive"}


def _fail(message: str) -> ShnqDuctCatalogError:
    return ShnqDuctCatalogError(message)


def _reject_constant(value: str) -> None:
    raise _fail(f"Недопустимая JSON-константа: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _fail(f"Повторяющийся JSON-ключ: {key}")
        result[key] = value
    return result


def _as_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(f"{location}: ожидался объект")
    return cast(dict[str, Any], value)


def _as_non_empty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{location}: ожидалась непустая строка")
    return value


def _as_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(f"{location}: ожидалось число")
    number = float(value)
    if not math.isfinite(number):
        raise _fail(f"{location}: число должно быть конечным")
    return number


def _normalise(value: str) -> str:
    return value.strip().casefold()


def _expect_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise _fail(f"{location}: неверные поля; отсутствуют {missing}, лишние {extra}")


def _parse_range(raw: Any, location: str) -> DuctNormRange:
    data = _as_object(raw, location)
    _expect_keys(data, _RANGE_KEYS, location)

    minimum = None if data["min"] is None else _as_number(data["min"], f"{location}.min")
    maximum = None if data["max"] is None else _as_number(data["max"], f"{location}.max")
    if minimum is None and maximum is None:
        raise _fail(f"{location}: должна быть задана хотя бы одна граница")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise _fail(f"{location}: min не может быть больше max")

    min_inclusive = data["minInclusive"]
    max_inclusive = data["maxInclusive"]
    if not isinstance(min_inclusive, bool) or not isinstance(max_inclusive, bool):
        raise _fail(f"{location}: признаки включённости должны быть bool")
    if minimum is None and min_inclusive:
        raise _fail(f"{location}: minInclusive должен быть false без min")
    if maximum is None and max_inclusive:
        raise _fail(f"{location}: maxInclusive должен быть false без max")

    return DuctNormRange(
        minimum=minimum,
        maximum=maximum,
        minimum_inclusive=min_inclusive,
        maximum_inclusive=max_inclusive,
    )


def _parse_applies_to(raw: Any, location: str) -> Mapping[str, tuple[str, ...]]:
    data = _as_object(raw, location)
    if not data:
        raise _fail(f"{location}: объект не должен быть пустым")

    parsed: dict[str, tuple[str, ...]] = {}
    for dimension, raw_values in data.items():
        _as_non_empty_string(dimension, f"{location} key")
        if not isinstance(raw_values, list) or not raw_values:
            raise _fail(f"{location}.{dimension}: ожидался непустой массив")
        values = tuple(
            _as_non_empty_string(value, f"{location}.{dimension}[{index}]")
            for index, value in enumerate(raw_values)
        )
        if len({_normalise(value) for value in values}) != len(values):
            raise _fail(f"{location}.{dimension}: повторяющиеся значения")
        parsed[dimension] = values
    return MappingProxyType(parsed)


def _parse_source(
    raw: Any,
    *,
    document: str,
    edition: str,
    location: str,
) -> DuctNormSource:
    data = _as_object(raw, location)
    _expect_keys(data, _SOURCE_KEYS, location)

    source_document = _as_non_empty_string(data["document"], f"{location}.document")
    source_edition = _as_non_empty_string(data["edition"], f"{location}.edition")
    clause = _as_non_empty_string(data["clause"], f"{location}.clause")
    page_pdf = data["pagePdf"]
    table = data["table"]

    if source_document != document or source_edition != edition:
        raise _fail(f"{location}: документ и редакция должны совпадать с каталогом")
    if isinstance(page_pdf, bool) or not isinstance(page_pdf, int) or page_pdf <= 0:
        raise _fail(f"{location}.pagePdf: ожидался положительный int")
    if table is not None and (not isinstance(table, str) or not table.strip()):
        raise _fail(f"{location}.table: ожидалась непустая строка или null")

    return DuctNormSource(
        document=source_document,
        edition=source_edition,
        clause=clause,
        page_pdf=page_pdf,
        table=table,
    )


def _parse_entry(
    raw: Any,
    *,
    document: str,
    edition: str,
    index: int,
) -> DuctNormEntry:
    location = f"entries[{index}]"
    data = _as_object(raw, location)
    has_value = "value" in data
    has_range = "range" in data
    if has_value == has_range:
        raise _fail(f"{location}: требуется ровно одно из полей value и range")
    _expect_keys(
        data,
        _ENTRY_BASE_KEYS | ({"value"} if has_value else {"range"}),
        location,
    )

    key = _as_non_empty_string(data["key"], f"{location}.key")
    if not _KEY_RE.fullmatch(key):
        raise _fail(f"{location}.key: нестабильный ASCII-ключ {key!r}")
    unit = _as_non_empty_string(data["unit"], f"{location}.unit")
    note_ru = _as_non_empty_string(data["noteRu"], f"{location}.noteRu")
    status_raw = data["status"]
    if status_raw not in ("unverified", "unreadable"):
        raise _fail(f"{location}.status: недопустимый статус {status_raw!r}")
    status = cast(NormStatus, status_raw)

    value: float | None = None
    value_range: DuctNormRange | None = None
    if has_value:
        raw_value = data["value"]
        value = None if raw_value is None else _as_number(raw_value, f"{location}.value")
        if value is None and status != "unreadable":
            raise _fail(f"{location}: null разрешён только для unreadable")
        if value is not None and status != "unverified":
            raise _fail(f"{location}: числовое value требует статуса unverified")
    else:
        if status != "unverified":
            raise _fail(f"{location}: range требует статуса unverified")
        value_range = _parse_range(data["range"], f"{location}.range")

    return DuctNormEntry(
        key=key,
        value=value,
        range=value_range,
        unit=unit,
        applies_to=_parse_applies_to(data["appliesTo"], f"{location}.appliesTo"),
        source=_parse_source(
            data["source"],
            document=document,
            edition=edition,
            location=f"{location}.source",
        ),
        status=status,
        note_ru=note_ru,
    )


def _parse_catalog(raw: str) -> DuctNormCatalog:
    try:
        decoded = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_object_without_duplicates,
        )
    except ShnqDuctCatalogError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise _fail(f"Некорректный JSON: {exc}") from exc

    data = _as_object(decoded, "catalog")
    _expect_keys(data, _TOP_LEVEL_KEYS, "catalog")
    schema_version = _as_non_empty_string(data["schemaVersion"], "schemaVersion")
    document = _as_non_empty_string(data["document"], "document")
    edition = _as_non_empty_string(data["edition"], "edition")
    if schema_version != _SCHEMA_VERSION:
        raise _fail(f"Неподдерживаемая schemaVersion: {schema_version}")
    if document != _DOCUMENT:
        raise _fail(f"Неожиданный нормативный документ: {document}")

    raw_entries = data["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise _fail("entries: ожидался непустой массив")
    entries = tuple(
        _parse_entry(entry, document=document, edition=edition, index=index)
        for index, entry in enumerate(raw_entries)
    )
    keys = [entry.key for entry in entries]
    if len(set(keys)) != len(keys):
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        raise _fail(f"Повторяющиеся ключи записей: {duplicates}")

    return DuctNormCatalog(
        schema_version=schema_version,
        document=document,
        edition=edition,
        entries=entries,
    )


def load_shnq_duct_catalog() -> DuctNormCatalog:
    """Загрузить и строго проверить встроенный каталог ШНҚ 2.04.05-22."""

    resource = files("hvac.catalogs") / "data" / "shnq_2_04_05_22_ducts.json"
    return _parse_catalog(resource.read_text("utf-8"))


SHNQ_DUCTS = load_shnq_duct_catalog()
_ENTRY_BY_KEY = MappingProxyType({entry.key: entry for entry in SHNQ_DUCTS.entries})


def get_entry(key: str) -> DuctNormEntry | None:
    """Вернуть запись по стабильному ключу без каких-либо нормативных fallback."""

    return _ENTRY_BY_KEY.get(key)


def _matches(entry: DuctNormEntry, criteria: Mapping[str, str]) -> bool:
    for dimension, requested in criteria.items():
        available = entry.applies_to.get(dimension)
        if available is None or not isinstance(requested, str) or not requested.strip():
            return False
        normalised = {_normalise(value) for value in available}
        if "all" not in normalised and _normalise(requested) not in normalised:
            return False
    return True


def filter_entries(
    *,
    key_prefix: str | None = None,
    **applies_to: str,
) -> tuple[DuctNormEntry, ...]:
    """Отфильтровать записи по ``appliesTo`` с AND-семантикой.

    Токен ``all`` в записи является явным wildcard. Неизвестные измерения и
    значения дают пустой результат; подстановок типов здания нет.
    """

    if key_prefix is not None and not isinstance(key_prefix, str):
        return ()
    return tuple(
        sorted(
            (
                entry
                for entry in SHNQ_DUCTS.entries
                if (key_prefix is None or entry.key.startswith(key_prefix))
                and _matches(entry, applies_to)
            ),
            key=lambda entry: entry.key,
        )
    )


def duct_velocity_limits(kind: str, building: str) -> tuple[DuctNormEntry, ...]:
    """Вернуть нормы скорости для вида участка и здания вместе с source/status.

    Результат является кортежем: для одной пары могут существовать несколько
    ограничений. Пустой кортеж означает, что в оцифрованном первоисточнике нет
    соответствующего численного значения; это не повод использовать иной норматив.
    """

    return filter_entries(key_prefix="velocity.", kind=kind, building=building)


__all__ = [
    "DuctNormCatalog",
    "DuctNormEntry",
    "DuctNormRange",
    "DuctNormSource",
    "NormStatus",
    "SHNQ_DUCTS",
    "ShnqDuctCatalogError",
    "duct_velocity_limits",
    "filter_entries",
    "get_entry",
    "load_shnq_duct_catalog",
]
