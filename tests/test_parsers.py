# -*- coding: utf-8 -*-
"""Тесты парсеров."""

import pytest
from hvac.parsers import parse_number, parse_area, azimuth_to_sector


class TestParseNumber:

    def test_int(self):
        assert parse_number(42) == 42.0

    def test_float(self):
        assert parse_number(3.14) == 3.14

    def test_simple_string(self):
        assert parse_number("210.00") == 210.0

    def test_with_units(self):
        assert parse_number("7.5 м²") == 7.5

    def test_comma_decimal(self):
        assert parse_number("12,3") == 12.3

    def test_with_plus_sign(self):
        assert parse_number("+420.42") == 420.42

    def test_negative(self):
        assert parse_number("-25.5") == -25.5

    def test_with_nbsp(self):
        assert parse_number("3\xa014") == 3.0  # 3, дальше пробел

    def test_empty(self):
        assert parse_number("") is None
        assert parse_number("   ") is None

    def test_none(self):
        assert parse_number(None) is None

    def test_no_number(self):
        assert parse_number("hello") is None


class TestParseArea:
    """parse_area = parse_number с фолбэком 0."""

    def test_valid(self):
        assert parse_area("7.5 м²") == 7.5

    def test_invalid(self):
        assert parse_area("") == 0.0
        assert parse_area(None) == 0.0


class TestAzimuthToSector:
    """Проверка перевода азимута в сектор."""

    @pytest.mark.parametrize("az,sect", [
        (0, "N"), (45, "NE"), (90, "E"), (135, "SE"),
        (180, "S"), (225, "SW"), (270, "W"), (315, "NW"),
        (10, "N"), (350, "N"),       # около севера
        (360, "N"), (720, "N"),      # период 360°
        (22.4, "N"), (22.6, "NE"),   # граница N/NE
    ])
    def test_cardinal_directions(self, az, sect):
        assert azimuth_to_sector(az) == sect

    def test_string_input(self):
        assert azimuth_to_sector("180.0") == "S"

    def test_none(self):
        assert azimuth_to_sector(None) == ""

    def test_empty(self):
        assert azimuth_to_sector("") == ""
