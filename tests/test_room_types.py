# -*- coding: utf-8 -*-
"""Тесты авто-определения типов помещений."""

import pytest
from hvac.catalogs.room_types import (
    auto_detect_room_type, apply_room_type_defaults, ROOM_TYPE_PRESETS,
    is_non_heated_type, is_non_cooled_type,
)
from hvac.models import Space


class TestAutoDetect:
    """Авто-определение типа по названию."""

    @pytest.mark.parametrize("name,expected", [
        ("OFFICE T1", "Офис"),
        ("Кабинет директора", "Офис"),
        ("STORAGE", "Склад"),
        ("Склад продукции", "Склад"),
        ("FIRE STAIR", "Лестница"),
        ("Лестница 1", "Лестница"),
        ("HOTEL ELEVATOR", "Лифт / шахта"),
        ("CARPARK", "Гараж / автостоянка"),
        ("MECHANICAL ROOM", "Технич. помещение"),
        ("TRANSFORMER ROOM", "Технич. помещение"),
        ("VESTIBULE", "Вестибюль"),
        ("Тамбур", "Вестибюль"),
        ("WC", "Санузел"),
        ("CORRIDOR", "Коридор"),
        ("Гостиничный номер 504", "Гостиничный номер"),
        ("Server room A", "Серверная"),
        ("Conference room", "Конференц-зал"),
    ])
    def test_known_names(self, name, expected):
        assert auto_detect_room_type(name) == expected

    def test_unknown(self):
        assert auto_detect_room_type("Какое-то странное помещение") == "Прочее"

    def test_empty(self):
        assert auto_detect_room_type("") == "Прочее"

    def test_none(self):
        assert auto_detect_room_type(None) == "Прочее"

    def test_priority_more_specific(self):
        """Более длинное ключевое слово должно побеждать."""
        # "Гостиничный номер" (длинное "hotel room") бьёт "Лифт" (короткое "номер" — wait)
        # Проверим: если в названии есть и "office", и "data center" — выбираем длинное
        result = auto_detect_room_type("office data center")
        # длина "office" = 6, "data center" = 11 → серверная
        assert result == "Серверная"

    def test_servery_is_kitchen_not_server_room(self):
        """Food servery is a kitchen/service area, not an IT server room."""
        assert auto_detect_room_type("SERVERY") == "Кухня"

    def test_server_must_be_a_separate_word(self):
        """The keyword 'server' must not match inside unrelated words."""
        assert auto_detect_room_type("OBSERVER ROOM") == "Прочее"


class TestApplyDefaults:

    def test_office_defaults(self):
        sp = Space(space_id="1", number="101", name="Office",
                   level="L1", area_m2=20.0, volume_m3=60.0,
                   room_type="Офис")
        apply_room_type_defaults(sp)
        assert sp.t_in_heat == 22   # design criteria заказчика (BOH/офис, зима 22°C)
        assert sp.t_in_cool == 24
        assert sp.lighting_w_m2 == 12
        # 20 / 10 = 2 человека
        assert sp.occupancy_people == 2.0

    def test_storage_defaults(self):
        sp = Space(space_id="1", number="201", name="Storage",
                   level="L1", area_m2=50.0, volume_m3=150.0,
                   room_type="Склад")
        apply_room_type_defaults(sp)
        assert sp.t_in_heat == 12     # склад холодный
        assert sp.lighting_w_m2 == 6

    def test_all_presets_have_required_keys(self):
        """Все пресеты должны содержать необходимые ключи."""
        required = ["keywords", "t_in_heat", "t_in_cool", "ach_inf",
                    "occupancy_density_m2_per_person",
                    "lighting_w_m2", "equipment_w_m2"]
        for room_type, preset in ROOM_TYPE_PRESETS.items():
            for key in required:
                assert key in preset, \
                    f"Тип '{room_type}' не содержит '{key}'"


class TestNonHeatedType:
    """Классификация неотапливаемых типов (для «Тепловой баланс» → «Авто»)."""

    @pytest.mark.parametrize("room_type", [
        "Лифт / шахта", "Гараж / автостоянка", "Балкон / терраса",
        "Технич. помещение", "Холодильная камера",
    ])
    def test_non_heated(self, room_type):
        assert is_non_heated_type(room_type) is True

    @pytest.mark.parametrize("room_type", [
        "Склад", "Лестница", "Офис", "Санузел", "Серверная",
        "Гостиничный номер", "Пожаробезопасная зона", "Прочее",
    ])
    def test_heated(self, room_type):
        assert is_non_heated_type(room_type) is False

    def test_unknown_type_is_heated(self):
        """Неизвестный тип → фолбэк «Прочее» (18 °C) → отапливается."""
        assert is_non_heated_type("Совершенно неизвестный тип") is False

    def test_threshold_matches_presets(self):
        """Признак согласован с t_in_heat пресета (порог 5 °C)."""
        from hvac.catalogs.room_types import NON_HEATED_MAX_T_HEAT
        for room_type, preset in ROOM_TYPE_PRESETS.items():
            expected = preset["t_in_heat"] <= NON_HEATED_MAX_T_HEAT
            assert is_non_heated_type(room_type) is expected, room_type


class TestNonCooledType:
    """Классификация неохлаждаемых типов (симметрично отоплению)."""

    @pytest.mark.parametrize("room_type", [
        "Лифт / шахта", "Гараж / автостоянка", "Балкон / терраса",
        "Технич. помещение",
    ])
    def test_non_cooled(self, room_type):
        assert is_non_cooled_type(room_type) is True

    @pytest.mark.parametrize("room_type", [
        "Офис", "Гостиничный номер", "Санузел", "Серверная", "Прочее",
        "Лестница", "Склад",
    ])
    def test_cooled(self, room_type):
        assert is_non_cooled_type(room_type) is False

    def test_cold_room_is_cooled_not_heated(self):
        """Холодильная камера: не отапливается, но охлаждается активно."""
        assert is_non_heated_type("Холодильная камера") is True
        assert is_non_cooled_type("Холодильная камера") is False

    def test_unknown_type_is_cooled(self):
        assert is_non_cooled_type("Совершенно неизвестный тип") is False

    def test_threshold_matches_presets(self):
        """Признак согласован с t_in_cool пресета (порог 30 °C)."""
        from hvac.catalogs.room_types import NON_COOLED_MIN_T_COOL
        for room_type, preset in ROOM_TYPE_PRESETS.items():
            expected = preset["t_in_cool"] >= NON_COOLED_MIN_T_COOL
            assert is_non_cooled_type(room_type) is expected, room_type
