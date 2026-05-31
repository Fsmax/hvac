# -*- coding: utf-8 -*-
"""Тесты авто-определения типов помещений."""

import pytest
from hvac.catalogs.room_types import (
    auto_detect_room_type, apply_room_type_defaults, ROOM_TYPE_PRESETS,
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


class TestApplyDefaults:

    def test_office_defaults(self):
        sp = Space(space_id="1", number="101", name="Office",
                   level="L1", area_m2=20.0, volume_m3=60.0,
                   room_type="Офис")
        apply_room_type_defaults(sp)
        assert sp.t_in_heat == 20
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
