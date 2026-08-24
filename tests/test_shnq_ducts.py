# -*- coding: utf-8 -*-
"""Контракт каталога воздуховодов ШНҚ 2.04.05-22 и его типизированного API."""

from __future__ import annotations

import json
import math
import re
from importlib.resources import files
from pathlib import Path

import pytest

from hvac.catalogs.shnq_ducts import (
    SHNQ_DUCTS,
    DuctNormEntry,
    ShnqDuctCatalogError,
    _parse_catalog,
    duct_velocity_limits,
    filter_entries,
    get_entry,
    load_shnq_duct_catalog,
)


DOCUMENT = "ШНҚ 2.04.05-22"
EDITION = "2024-08-05 (приказ № 01/2-39)"
KEY_RE = re.compile(r"^[a-z0-9]+(?:[._][a-z0-9]+)*$")


def _raw_catalog() -> dict:
    resource = files("hvac.catalogs") / "data" / "shnq_2_04_05_22_ducts.json"
    return json.loads(resource.read_text("utf-8"))


def _entry(key: str) -> DuctNormEntry:
    entry = get_entry(key)
    assert entry is not None, key
    return entry


def _parse_raw_catalog(raw: dict) -> tuple[DuctNormEntry, ...]:
    return _parse_catalog(json.dumps(raw, ensure_ascii=False)).entries


class TestCatalogSchema:
    def test_top_level_contract_and_expected_entry_count(self):
        raw = _raw_catalog()
        assert set(raw) == {"schemaVersion", "document", "edition", "entries"}
        assert raw["schemaVersion"] == "1.0"
        assert raw["document"] == DOCUMENT
        assert raw["edition"] == EDITION
        assert len(raw["entries"]) == 55

    def test_keys_are_unique_stable_ascii(self):
        keys = [entry["key"] for entry in _raw_catalog()["entries"]]
        assert len(keys) == len(set(keys))
        assert all(KEY_RE.fullmatch(key) for key in keys)

    def test_value_or_range_shape_and_finite_numbers(self):
        for entry in _raw_catalog()["entries"]:
            has_value = "value" in entry
            has_range = "range" in entry
            assert has_value != has_range, entry["key"]
            assert set(entry) == {
                "key", "value" if has_value else "range", "unit", "appliesTo",
                "source", "status", "noteRu",
            }

            if has_range:
                bounds = entry["range"]
                assert set(bounds) == {
                    "min", "max", "minInclusive", "maxInclusive",
                }
                assert bounds["min"] is not None or bounds["max"] is not None
                for name in ("min", "max"):
                    value = bounds[name]
                    assert value is None or (
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                    ), (entry["key"], name)
                if bounds["min"] is not None and bounds["max"] is not None:
                    assert bounds["min"] <= bounds["max"]
                assert isinstance(bounds["minInclusive"], bool)
                assert isinstance(bounds["maxInclusive"], bool)
                assert entry["status"] == "unverified"
            elif entry["value"] is None:
                assert entry["status"] == "unreadable"
            else:
                assert isinstance(entry["value"], (int, float))
                assert not isinstance(entry["value"], bool)
                assert math.isfinite(entry["value"])
                assert entry["status"] == "unverified"

    def test_applies_to_is_explicit_and_filterable(self):
        for entry in _raw_catalog()["entries"]:
            applies_to = entry["appliesTo"]
            assert isinstance(applies_to, dict) and applies_to, entry["key"]
            assert "kind" in applies_to
            assert "building" in applies_to
            for dimension, values in applies_to.items():
                assert dimension
                assert isinstance(values, list) and values, (entry["key"], dimension)
                assert all(isinstance(value, str) and value.strip() for value in values)

    def test_frozen_build_includes_new_resource(self):
        # Спек берёт каталоги глобом всей папки, поимённо файлы не
        # перечисляются — проверяем, что ресурс лежит в собираемой папке
        # и что спек действительно подключает её глобом.
        root = Path(__file__).parents[1]
        assert (root / "hvac" / "catalogs" / "data"
                / "shnq_2_04_05_22_ducts.json").exists()
        text = (root / "hvac_calc.spec").read_text(encoding="utf-8")
        assert '"catalogs" / "data").glob("*.json")' in text

    def test_legacy_entries_without_verification_fields_remain_valid(self):
        entries = _parse_raw_catalog(_raw_catalog())
        assert all(entry.verified_by is None for entry in entries)
        assert all(entry.verified_at is None for entry in entries)

    def test_verified_value_and_range_require_and_expose_audit_fields(self):
        raw = _raw_catalog()
        scalar = raw["entries"][0]
        scalar.update(
            status="verified",
            verifiedBy="Инженер ОВ",
            verifiedAt="2026-08-23T07:34:56Z",
        )
        value_range = raw["entries"][1]
        value_range.update(
            status="verified",
            verifiedBy="Engineer HVAC",
            verifiedAt="2026-08-23T12:34:56+05:00",
        )

        entries = _parse_raw_catalog(raw)

        assert entries[0].status == "verified"
        assert entries[0].value == pytest.approx(1)
        assert entries[0].verified_by == "Инженер ОВ"
        assert entries[0].verified_at == "2026-08-23T07:34:56Z"
        assert entries[1].status == "verified"
        assert entries[1].range is not None
        assert entries[1].verified_by == "Engineer HVAC"
        assert entries[1].verified_at == "2026-08-23T12:34:56+05:00"

    @pytest.mark.parametrize(
        "audit_fields",
        [
            {},
            {"verifiedBy": "Инженер ОВ"},
            {"verifiedAt": "2026-08-23T07:34:56Z"},
            {"verifiedBy": "", "verifiedAt": "2026-08-23T07:34:56Z"},
            {"verifiedBy": "Инженер ОВ", "verifiedAt": "2026-08-23T07:34:56"},
            {"verifiedBy": "Инженер ОВ", "verifiedAt": "не дата"},
        ],
    )
    def test_verified_rejects_missing_or_invalid_audit_fields(self, audit_fields):
        raw = _raw_catalog()
        raw["entries"][0]["status"] = "verified"
        raw["entries"][0].update(audit_fields)

        with pytest.raises(ShnqDuctCatalogError):
            _parse_raw_catalog(raw)

    def test_verification_fields_are_forbidden_for_other_statuses(self):
        raw = _raw_catalog()
        raw["entries"][0].update(
            verifiedBy="Инженер ОВ",
            verifiedAt="2026-08-23T07:34:56Z",
        )

        with pytest.raises(ShnqDuctCatalogError):
            _parse_raw_catalog(raw)

    def test_verified_null_preserves_ambiguous_entry_without_fabricating_value(self):
        raw = _raw_catalog()
        unreadable = next(
            entry for entry in raw["entries"] if entry["status"] == "unreadable"
        )
        expected_key = unreadable["key"]
        expected_note = unreadable["noteRu"]
        expected_source = unreadable["source"].copy()
        unreadable.update(
            status="verified",
            verifiedBy="Инженер ОВ",
            verifiedAt="2026-08-23T07:34:56Z",
        )

        verified = next(entry for entry in _parse_raw_catalog(raw) if entry.key == expected_key)

        assert verified.status == "verified"
        assert verified.value is None
        assert verified.range is None
        assert verified.note_ru == expected_note
        assert verified.source.document == expected_source["document"]
        assert verified.source.edition == expected_source["edition"]
        assert verified.source.clause == expected_source["clause"]
        assert verified.source.page_pdf == expected_source["pagePdf"]
        assert verified.source.table == expected_source["table"]
        assert verified.verified_by == "Инженер ОВ"
        assert verified.verified_at == "2026-08-23T07:34:56Z"

    def test_unknown_entry_fields_remain_fail_closed(self):
        raw = _raw_catalog()
        raw["entries"][0]["unexpected"] = True
        with pytest.raises(ShnqDuctCatalogError):
            _parse_raw_catalog(raw)


class TestProvenanceAndStatus:
    def test_every_entry_has_full_source_and_warning_status(self):
        raw = _raw_catalog()
        for entry in raw["entries"]:
            source = entry["source"]
            assert set(source) == {
                "document", "edition", "clause", "pagePdf", "table",
            }
            assert source["document"] == raw["document"] == DOCUMENT
            assert source["edition"] == raw["edition"] == EDITION
            assert isinstance(source["clause"], str) and source["clause"]
            assert isinstance(source["pagePdf"], int)
            assert not isinstance(source["pagePdf"], bool)
            assert 1 <= source["pagePdf"] <= 90
            assert source["table"] is None or isinstance(source["table"], str)
            assert entry["status"] in {"unverified", "unreadable"}
            assert entry["status"] != "verified"
            assert isinstance(entry["unit"], str) and entry["unit"]
            assert isinstance(entry["noteRu"], str) and entry["noteRu"]

    def test_only_seven_semantically_ambiguous_entries_are_unreadable(self):
        unreadable = {
            entry["key"]: entry
            for entry in _raw_catalog()["entries"]
            if entry["status"] == "unreadable"
        }
        assert set(unreadable) == {
            "placement.exhaust.upper_zone.explosive_non_hydrogen.ceiling_distance",
            "placement.exhaust.upper_zone.hydrogen.low_room.ceiling_distance",
            "placement.exhaust.upper_zone.hydrogen.high_room.ceiling_distance",
            "placement.emergency_exhaust.upper_zone.explosive_non_hydrogen.ceiling_distance",
            "placement.emergency_exhaust.upper_zone.hydrogen.low_room.ceiling_distance",
            "placement.emergency_exhaust.upper_zone.hydrogen.high_room.ceiling_distance",
            "clearance.duct.combustible_communications",
        }
        for entry in unreadable.values():
            assert entry["value"] is None
            assert any(
                marker in entry["noteRu"]
                for marker in ("неоднознач", "инвертирует", "не нормализовано")
            )

    def test_calculated_smoke_duct_velocity_is_not_fabricated(self):
        # П. 332, PDF 45 требует расчёта скорости дыма и не даёт числа.
        assert get_entry("velocity.smoke_exhaust.duct") is None
        assert duct_velocity_limits("smoke_exhaust", "public") == ()


class TestTypedLookup:
    def test_catalog_loads_as_immutable_typed_entries(self):
        loaded = load_shnq_duct_catalog()
        assert loaded == SHNQ_DUCTS
        assert isinstance(loaded.entries, tuple)
        assert len(loaded.entries) == 55
        assert all(isinstance(entry, DuctNormEntry) for entry in loaded.entries)

    def test_get_entry_and_missing_key(self):
        entry = _entry("slope.duct.condensate_or_liquid.min")
        assert entry.range is not None
        assert entry.range.minimum == pytest.approx(0.005)
        assert entry.source.clause == "320"
        assert get_entry("does.not.exist") is None

    def test_filter_uses_and_casefold_and_explicit_all_wildcard(self):
        public = filter_entries(kind="AIR_CURTAIN", building="Public")
        assert {entry.key for entry in public} == {
            "velocity.air_curtain.exterior_wall.max",
            "velocity.air_curtain.gate_technological_opening.max",
        }
        exact = filter_entries(
            kind="air_curtain.exterior_wall",
            building="industrial",
            element="slot_or_opening",
        )
        assert [entry.key for entry in exact] == [
            "velocity.air_curtain.exterior_wall.max",
        ]

    def test_filter_has_no_building_or_dimension_fallback(self):
        assert filter_entries(kind="industrial_exhaust", building="public") == ()
        assert filter_entries(kind="industrial_exhaust", unknown_dimension="x") == ()

    def test_filter_order_is_deterministic_and_preserves_unreadable(self):
        entries = filter_entries(kind="upper_zone_exhaust", building="public")
        assert entries == tuple(sorted(entries, key=lambda entry: entry.key))
        assert {entry.status for entry in entries} == {"unverified", "unreadable"}

    def test_conditional_routing_and_smoke_zoning_scope_is_explicit(self):
        combinations = filter_entries(
            key_prefix="routing.ventilation_system.other_room_group."
        )
        assert len(combinations) == 3
        assert all(
            entry.range is not None
            and entry.range.maximum == pytest.approx(200)
            and entry.source.clause == "199"
            and "combination" in entry.applies_to
            for entry in combinations
        )

        emergency = filter_entries(
            kind="emergency_exhaust",
            building="industrial",
            medium="gas_or_vapor_heavier_than_air",
        )
        assert [entry.key for entry in emergency] == [
            "placement.emergency_exhaust.heavier_than_air.opening_bottom.height.max",
        ]
        assert emergency[0].source.clause == "246 (по п. 238)"
        assert emergency[0].source.page_pdf == 30

        emergency_unreadable = filter_entries(
            kind="emergency_exhaust",
            building="industrial",
            medium="hydrogen_air_mixture",
        )
        assert len(emergency_unreadable) == 2
        assert {entry.status for entry in emergency_unreadable} == {"unreadable"}

        smoke_zone = _entry("smoke_zoning.zone_area.max")
        assert smoke_zone.range is not None
        assert smoke_zone.range.maximum == pytest.approx(1600)
        assert smoke_zone.source.page_pdf == 45

        collector = _entry(
            "routing.smoke_exhaust.vertical_collector.branches_per_floor.max"
        )
        assert collector.range is not None
        assert collector.range.maximum == pytest.approx(4)
        assert collector.applies_to["collector"] == ("vertical",)
        assert "storeys" not in collector.applies_to

        vertical = _entry(
            "clearance.exhaust.air_intake.vertical_if_horizontal_under_10m.design"
        )
        assert vertical.value == pytest.approx(6)
        assert vertical.range is None

        formula_floor = _entry(
            "clearance.explosive_exhaust.ignition_source.absolute_floor"
        )
        assert formula_floor.range is not None
        assert formula_floor.range.minimum == pytest.approx(10)
        assert formula_floor.applies_to["valueRole"] == (
            "absolute_floor_not_complete_design_distance",
        )


class TestDuctVelocityLimits:
    def test_generic_air_curtain_query_returns_both_limits_with_sources(self):
        entries = duct_velocity_limits("air_curtain", "public")
        assert [entry.key for entry in entries] == [
            "velocity.air_curtain.exterior_wall.max",
            "velocity.air_curtain.gate_technological_opening.max",
        ]
        assert all(entry.source.document == DOCUMENT for entry in entries)
        assert all(entry.status == "unverified" for entry in entries)

    def test_specific_kind_returns_only_its_limit(self):
        entries = duct_velocity_limits(
            "air_curtain.gate_technological_opening", "industrial"
        )
        assert len(entries) == 1
        assert entries[0].key == "velocity.air_curtain.gate_technological_opening.max"

    def test_smoke_pressurization_doorway_is_exact_design_value(self):
        entries = duct_velocity_limits("smoke_pressurization.open_doorway", "public")
        assert len(entries) == 1
        assert entries[0].value == pytest.approx(1.3)
        assert entries[0].range is None

    def test_missing_trunk_table_does_not_fallback(self):
        # В этом PDF нет таблицы скоростей магистралей по типам зданий.
        assert duct_velocity_limits("trunk", "public") == ()

    @pytest.mark.parametrize(
        ("key", "minimum", "maximum", "value", "clause", "page_pdf"),
        [
            # П. 254, PDF 32: завеса у наружной стены — не более 8 m/s.
            ("velocity.air_curtain.exterior_wall.max", None, 8.0, None, "254", 32),
            # П. 254, PDF 32: завеса у ворот/техпроёма — не более 25 m/s.
            (
                "velocity.air_curtain.gate_technological_opening.max",
                None,
                25.0,
                None,
                "254",
                32,
            ),
            # П. 340, PDF 47: подпор через открытую дверь — 1,3 m/s.
            (
                "velocity.smoke_pressurization.open_doorway.design",
                None,
                None,
                1.3,
                "340",
                47,
            ),
            # П. 319, PDF 43: уклон вытяжного воздуховода — не менее 0,005.
            (
                "slope.exhaust.combustible_gas_lighter_than_air.min",
                0.005,
                None,
                None,
                "319",
                43,
            ),
            # П. 365, PDF 51: выброс от воздухозабора — не менее 10 m по горизонтали.
            (
                "clearance.exhaust.air_intake.horizontal.min",
                10.0,
                None,
                None,
                "365",
                51,
            ),
        ],
    )
    def test_five_manually_checked_pdf_values(
        self,
        key: str,
        minimum: float | None,
        maximum: float | None,
        value: float | None,
        clause: str,
        page_pdf: int,
    ):
        entry = _entry(key)
        assert entry.status == "unverified"
        assert entry.source.clause == clause
        assert entry.source.page_pdf == page_pdf
        assert entry.source.table is None
        if value is not None:
            assert entry.value == pytest.approx(value)
            assert entry.range is None
        else:
            assert entry.value is None
            assert entry.range is not None
            assert entry.range.minimum == minimum
            assert entry.range.maximum == maximum
