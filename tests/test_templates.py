# -*- coding: utf-8 -*-
"""Тесты шаблонов типовых зданий."""

import pytest
from hvac.templates import (
    TEMPLATE_FACTORIES, apply_template, list_templates, make_template,
)
from hvac.project import HVACProject


class TestRegistry:
    def test_six_templates(self):
        assert len(list_templates()) == 6
        codes = [t["code"] for t in list_templates()]
        for expected in ("office_open", "office_cubicles", "school",
                          "hotel", "mall", "residential"):
            assert expected in codes

    def test_make_unknown_raises(self):
        with pytest.raises(ValueError):
            make_template("nonexistent")


class TestOfficeOpen:
    def test_default(self):
        tpl = make_template("office_open")
        assert tpl.rooms
        assert any(r.room_type == "Серверная" for r in tpl.rooms)
        assert any(r.room_type == "Санузел" for r in tpl.rooms)

    def test_n_workplaces_scales_open_area(self):
        small = make_template("office_open", n_workplaces=10)
        big = make_template("office_open", n_workplaces=100)
        open_small = next(r for r in small.rooms if r.name == "Open Space")
        open_big = next(r for r in big.rooms if r.name == "Open Space")
        assert open_big.area_m2 > open_small.area_m2 * 5


class TestSchool:
    def test_default_24_classes(self):
        tpl = make_template("school")
        classes = [r for r in tpl.rooms if r.room_type == "Класс / аудитория"]
        # 24 класса + библиотека
        assert len(classes) >= 24

    def test_has_essentials(self):
        tpl = make_template("school")
        names = [r.name for r in tpl.rooms]
        assert any("Спортзал" in n for n in names)
        assert any("Столовая" in n for n in names)


class TestHotel:
    def test_default_60_rooms(self):
        tpl = make_template("hotel")
        n_rooms = sum(r.count for r in tpl.rooms
                      if r.room_type == "Гостиничный номер")
        # Около 60 (может слегка отличаться из-за деления по этажам)
        assert 50 <= n_rooms <= 60

    def test_stars_affect_area(self):
        small = make_template("hotel", stars=3)
        big = make_template("hotel", stars=5)
        s = next(r for r in small.rooms
                  if r.room_type == "Гостиничный номер")
        b = next(r for r in big.rooms
                  if r.room_type == "Гостиничный номер")
        assert b.area_m2 > s.area_m2


class TestResidential:
    def test_default(self):
        tpl = make_template("residential")
        living = [r for r in tpl.rooms
                  if r.room_type == "Жилая комната"]
        kitchens = [r for r in tpl.rooms
                    if r.room_type == "Кухня"]
        # Каждая квартира — 2 жилые + 1 кухня (24 квартиры = 48 жилых)
        assert len(living) >= 40
        assert len(kitchens) >= 20

    def test_has_basement_services(self):
        tpl = make_template("residential")
        names = [r.name for r in tpl.rooms]
        assert any("ИТП" in n for n in names)
        assert any("Электрощитовая" in n for n in names)


class TestApplyTemplate:
    def test_applies_to_empty_project(self):
        project = HVACProject()
        tpl = make_template("office_open", n_workplaces=20)
        n = apply_template(project, tpl, project_name="Тест офис")
        assert n > 0
        assert project.params.project_name == "Тест офис"
        assert len(project.spaces) == n

    def test_overwrites_existing(self):
        project = HVACProject()
        from hvac.models import Space
        project.spaces.append(Space(
            space_id="old", number="OLD", name="Old", level="L1",
            area_m2=10, volume_m3=30, height_m=3))
        project._space_by_id["old"] = project.spaces[0]

        tpl = make_template("school")
        apply_template(project, tpl)
        # Старое помещение удалено
        assert "old" not in project._space_by_id

    def test_applies_to_city(self):
        project = HVACProject()
        tpl = make_template("residential", n_apartments=6, n_floors=2)
        apply_template(project, tpl, city="Самарканд")
        assert project.params.city == "Самарканд"
