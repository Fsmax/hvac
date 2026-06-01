# -*- coding: utf-8 -*-
"""Шаблоны типовых зданий.

Создают стартовый проект с типовым набором помещений и параметров.
Полезно для:
    • быстрого старта нового проекта без полной выгрузки из Revit;
    • демонстрации возможностей программы;
    • тестового объекта для отработки методики.

Доступные шаблоны:
    • office_open       — открытый офис на N м²
    • office_cubicles   — офис с кабинетами
    • school            — школа на N классов
    • hotel             — гостиница на N номеров
    • mall              — торговый центр
    • residential       — многоквартирный жилой дом

Параметры шаблонов согласованы с СП 60.13330, СП 30.13330, СП 113.13330,
КМК 2.04.05-22 (для Узбекистана). Цифры можно переопределить через
аргументы фабричных функций.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from hvac.models import Space


@dataclass
class TemplateRoom:
    """Описание одной типовой комнаты шаблона."""
    name: str
    room_type: str
    area_m2: float
    height_m: float = 3.0
    count: int = 1
    occupancy_people: float = 0.0
    lighting_w_m2: float = 12.0
    equipment_w_m2: float = 10.0
    level: str = "L1"
    note: str = ""


@dataclass
class BuildingTemplate:
    """Шаблон типового здания."""
    code: str                              # office_open / school / ...
    title: str                             # «Открытый офис»
    description: str = ""
    default_city: str = "Ташкент"
    default_methodology: str = "КМК 2.04.05-91 + КМК 2.01.04-18"
    rooms: List[TemplateRoom] = None       # type: ignore[assignment]

    def __post_init__(self):
        if self.rooms is None:
            self.rooms = []


# ============================================================================
# Каталог шаблонов
# ============================================================================

def _office_open(n_workplaces: int = 50,
                  level: str = "L2") -> BuildingTemplate:
    """Открытый офис. По СП 44 / СН 2.2.4 на 1 рабочее место 6 м²."""
    area_per_seat = 6.0
    open_area = n_workplaces * area_per_seat
    rooms = [
        TemplateRoom(name="Open Space", room_type="Офис",
                      area_m2=open_area, occupancy_people=n_workplaces,
                      lighting_w_m2=12, equipment_w_m2=15, level=level),
        TemplateRoom(name="Переговорная M", room_type="Конференц-зал",
                      area_m2=18, occupancy_people=8,
                      lighting_w_m2=12, equipment_w_m2=8, level=level,
                      count=2),
        TemplateRoom(name="Переговорная L", room_type="Конференц-зал",
                      area_m2=35, occupancy_people=14,
                      lighting_w_m2=12, equipment_w_m2=8, level=level),
        TemplateRoom(name="Кабинет руководителя", room_type="Офис",
                      area_m2=22, occupancy_people=2,
                      lighting_w_m2=10, equipment_w_m2=12, level=level,
                      count=2),
        TemplateRoom(name="Кухня-комната отдыха", room_type="Ресторан / кухня",
                      area_m2=18, occupancy_people=6, lighting_w_m2=10,
                      equipment_w_m2=15, level=level),
        TemplateRoom(name="Серверная", room_type="Серверная",
                      area_m2=8, lighting_w_m2=8, equipment_w_m2=300,
                      level=level, note="Тепловыделение от серверов"),
        TemplateRoom(name="Санузел М", room_type="Санузел", area_m2=8,
                      lighting_w_m2=10, equipment_w_m2=2, level=level),
        TemplateRoom(name="Санузел Ж", room_type="Санузел", area_m2=8,
                      lighting_w_m2=10, equipment_w_m2=2, level=level),
        TemplateRoom(name="Коридор", room_type="Коридор",
                      area_m2=max(open_area * 0.18, 30),
                      lighting_w_m2=6, equipment_w_m2=2, level=level),
    ]
    return BuildingTemplate(
        code="office_open",
        title="Открытый офис",
        description=f"Open-space офис на {n_workplaces} рабочих мест "
                    f"+ переговорные, кабинеты, кухня, серверная.",
        rooms=rooms,
    )


def _office_cubicles(n_rooms: int = 12,
                     level: str = "L2") -> BuildingTemplate:
    """Офис с кабинетами 2-4 рабочих места в комнате."""
    rooms = []
    for i in range(n_rooms):
        rooms.append(TemplateRoom(
            name=f"Кабинет {i + 1}", room_type="Офис",
            area_m2=18, occupancy_people=3,
            lighting_w_m2=12, equipment_w_m2=15, level=level,
        ))
    rooms.extend([
        TemplateRoom(name="Приёмная", room_type="Офис",
                      area_m2=22, occupancy_people=2, level=level),
        TemplateRoom(name="Переговорная", room_type="Конференц-зал",
                      area_m2=30, occupancy_people=10, level=level),
        TemplateRoom(name="Кухня", room_type="Ресторан / кухня",
                      area_m2=12, occupancy_people=4, level=level),
        TemplateRoom(name="Санузел", room_type="Санузел",
                      area_m2=6, level=level, count=2),
        TemplateRoom(name="Коридор", room_type="Коридор",
                      area_m2=40, level=level),
    ])
    return BuildingTemplate(
        code="office_cubicles",
        title="Офис с кабинетами",
        description=f"Офис кабинетной структуры на {n_rooms} кабинетов.",
        rooms=rooms,
    )


def _school(n_classes: int = 24) -> BuildingTemplate:
    """Школа на N классов (СанПиН 2.4.2.2821-10, СП 60 п. 5.3)."""
    rooms = []
    # Классы на 25 учеников по 60-65 м² (СанПиН: ≥ 2.5 м² на ученика).
    for i in range(n_classes):
        level = f"L{(i // 8) + 1}"
        rooms.append(TemplateRoom(
            name=f"Класс {i + 1}", room_type="Класс / аудитория",
            area_m2=65, occupancy_people=25,
            lighting_w_m2=15, equipment_w_m2=8, level=level,
        ))
    rooms.extend([
        TemplateRoom(name="Спортзал", room_type="Спортзал",
                      area_m2=288, height_m=6.0,
                      occupancy_people=30, lighting_w_m2=15,
                      equipment_w_m2=3, level="L1"),
        TemplateRoom(name="Актовый зал", room_type="Конференц-зал",
                      area_m2=180, height_m=4.5,
                      occupancy_people=200, level="L1"),
        TemplateRoom(name="Столовая", room_type="Ресторан / кухня",
                      area_m2=180, occupancy_people=100,
                      lighting_w_m2=15, equipment_w_m2=30, level="L1"),
        TemplateRoom(name="Кухня-пищеблок", room_type="Ресторан / кухня",
                      area_m2=80, occupancy_people=10,
                      lighting_w_m2=15, equipment_w_m2=200, level="L1"),
        TemplateRoom(name="Библиотека", room_type="Класс / аудитория",
                      area_m2=60, occupancy_people=20, level="L2"),
        TemplateRoom(name="Холл", room_type="Вестибюль",
                      area_m2=180, level="L1"),
        TemplateRoom(name="Санузел М", room_type="Санузел",
                      area_m2=18, level="L1", count=4),
        TemplateRoom(name="Санузел Ж", room_type="Санузел",
                      area_m2=18, level="L1", count=4),
        TemplateRoom(name="Коридор", room_type="Коридор",
                      area_m2=120, level="L1", count=3),
    ])
    return BuildingTemplate(
        code="school",
        title="Школа",
        description=f"Школа на {n_classes} классов: учебные кабинеты, "
                    f"спортзал, столовая, актовый зал.",
        rooms=rooms,
    )


def _hotel(n_rooms: int = 60, stars: int = 4) -> BuildingTemplate:
    """Гостиница. СП 257.1325800 / КМК 2.04.05-22."""
    area_per_room = 26 if stars >= 4 else 22
    rooms = []
    floors = max(1, (n_rooms + 19) // 20)
    rooms_per_floor = n_rooms // floors
    for f in range(floors):
        for i in range(rooms_per_floor):
            rooms.append(TemplateRoom(
                name=f"Номер {f + 1}.{i + 1:02d}",
                room_type="Гостиничный номер",
                area_m2=area_per_room, occupancy_people=2,
                lighting_w_m2=10, equipment_w_m2=8,
                level=f"L{f + 1}",
            ))
        rooms.append(TemplateRoom(
            name=f"Холл этажа {f + 1}", room_type="Вестибюль",
            area_m2=40, level=f"L{f + 1}"))
        rooms.append(TemplateRoom(
            name=f"Коридор этажа {f + 1}", room_type="Коридор",
            area_m2=80, level=f"L{f + 1}"))
        rooms.append(TemplateRoom(
            name=f"Бельевая этажа {f + 1}", room_type="Технич. помещение",
            area_m2=8, level=f"L{f + 1}"))

    # Общественные помещения
    rooms.extend([
        TemplateRoom(name="Лобби", room_type="Вестибюль",
                      area_m2=200, height_m=4.5,
                      occupancy_people=40, level="L1"),
        TemplateRoom(name="Ресторан", room_type="Ресторан / кухня",
                      area_m2=180, occupancy_people=80,
                      lighting_w_m2=15, equipment_w_m2=25, level="L1"),
        TemplateRoom(name="Кухня ресторана", room_type="Ресторан / кухня",
                      area_m2=70, occupancy_people=8,
                      equipment_w_m2=250, level="L1"),
        TemplateRoom(name="Конференц-зал", room_type="Конференц-зал",
                      area_m2=120, occupancy_people=80, level="L1"),
        TemplateRoom(name="Фитнес/СПА", room_type="Спортзал",
                      area_m2=80, occupancy_people=15, level="-L1"),
        TemplateRoom(name="Прачечная", room_type="Технич. помещение",
                      area_m2=40, equipment_w_m2=80, level="-L1"),
        TemplateRoom(name="Парковка", room_type="Гараж / автостоянка",
                      area_m2=600, height_m=2.5, level="-L1"),
    ])
    return BuildingTemplate(
        code="hotel",
        title=f"Гостиница {stars}*",
        description=f"Гостиница {stars}* на {n_rooms} номеров с лобби, "
                    f"рестораном, спа, парковкой.",
        rooms=rooms,
    )


def _mall(area_m2: int = 5000) -> BuildingTemplate:
    """Торговый центр. СП 113.13330 (для парковки) + СП 60."""
    rooms = []
    n_shops = max(area_m2 // 200, 10)
    shop_area = (area_m2 * 0.55) / n_shops
    for i in range(int(n_shops)):
        rooms.append(TemplateRoom(
            name=f"Магазин {i + 1}", room_type="Магазин / торговля",
            area_m2=shop_area, occupancy_people=shop_area * 0.05,
            lighting_w_m2=20, equipment_w_m2=15, level="L1",
        ))
    rooms.extend([
        TemplateRoom(name="Атриум", room_type="Магазин / торговля",
                      area_m2=area_m2 * 0.10, height_m=10,
                      occupancy_people=area_m2 * 0.005, level="L1"),
        TemplateRoom(name="Фуд-корт", room_type="Ресторан / кухня",
                      area_m2=area_m2 * 0.08, occupancy_people=80,
                      lighting_w_m2=18, equipment_w_m2=50, level="L2"),
        TemplateRoom(name="Кинотеатр", room_type="Конференц-зал",
                      area_m2=300, occupancy_people=200, level="L2"),
        TemplateRoom(name="Подземная парковка",
                      room_type="Гараж / автостоянка",
                      area_m2=area_m2 * 0.8, height_m=2.5, level="-L1"),
        TemplateRoom(name="Технический этаж",
                      room_type="Технич. помещение",
                      area_m2=area_m2 * 0.05, level="L3"),
        TemplateRoom(name="Туалеты", room_type="Санузел",
                      area_m2=30, count=4, level="L1"),
        TemplateRoom(name="Коридор", room_type="Коридор",
                      area_m2=area_m2 * 0.12, count=2, level="L1"),
    ])
    return BuildingTemplate(
        code="mall",
        title="Торговый центр",
        description=f"ТРЦ площадью {area_m2} м²: магазины, фуд-корт, "
                    f"парковка.",
        rooms=rooms,
    )


def _residential(n_apartments: int = 24, n_floors: int = 6
                  ) -> BuildingTemplate:
    """Многоквартирный жилой дом."""
    rooms = []
    per_floor = max(n_apartments // n_floors, 1)
    for f in range(n_floors):
        for i in range(per_floor):
            apt_n = f * per_floor + i + 1
            level = f"L{f + 1}"
            # Типовая 2-комнатная квартира 60 м²
            rooms.extend([
                TemplateRoom(name=f"Кв {apt_n} — Гостиная",
                              room_type="Жилая комната",
                              area_m2=22, occupancy_people=2,
                              level=level),
                TemplateRoom(name=f"Кв {apt_n} — Спальня",
                              room_type="Жилая комната",
                              area_m2=14, occupancy_people=2, level=level),
                TemplateRoom(name=f"Кв {apt_n} — Кухня",
                              room_type="Ресторан / кухня",
                              area_m2=10, equipment_w_m2=30,
                              level=level),
                TemplateRoom(name=f"Кв {apt_n} — Ванная",
                              room_type="Санузел", area_m2=5, level=level),
                TemplateRoom(name=f"Кв {apt_n} — Прихожая",
                              room_type="Коридор", area_m2=4,
                              lighting_w_m2=8, equipment_w_m2=2,
                              level=level),
            ])
        # Общие помещения этажа
        rooms.append(TemplateRoom(
            name=f"Лестничная клетка L{f + 1}",
            room_type="Лестница", area_m2=20, level=f"L{f + 1}"))
        rooms.append(TemplateRoom(
            name=f"Лифтовая шахта L{f + 1}",
            room_type="Лифт / шахта", area_m2=6, level=f"L{f + 1}"))
        rooms.append(TemplateRoom(
            name=f"МОП этажа {f + 1}", room_type="Коридор",
            area_m2=30, lighting_w_m2=8, equipment_w_m2=2,
            level=f"L{f + 1}"))

    # Цоколь / подвал
    rooms.append(TemplateRoom(
        name="Тепловой пункт (ИТП)", room_type="Технич. помещение",
        area_m2=18, equipment_w_m2=200, level="B1"))
    rooms.append(TemplateRoom(
        name="Электрощитовая", room_type="Технич. помещение",
        area_m2=15, equipment_w_m2=100, level="B1"))
    rooms.append(TemplateRoom(
        name="Венткамера", room_type="Технич. помещение",
        area_m2=30, equipment_w_m2=50, level="B1"))

    return BuildingTemplate(
        code="residential",
        title="Жилой дом",
        description=f"Многоквартирный жилой дом на {n_apartments} квартир, "
                    f"{n_floors} этажей.",
        rooms=rooms,
    )


# ============================================================================
# Реестр шаблонов
# ============================================================================

TEMPLATE_FACTORIES: Dict[str, Callable] = {
    "office_open":     _office_open,
    "office_cubicles": _office_cubicles,
    "school":          _school,
    "hotel":           _hotel,
    "mall":            _mall,
    "residential":     _residential,
}


def list_templates() -> List[Dict[str, str]]:
    """Возвращает список шаблонов в виде [{code, title, description}]."""
    items = []
    for code, factory in TEMPLATE_FACTORIES.items():
        # Создаём с дефолтными параметрами только для метаданных
        tpl = factory()
        items.append({
            "code": code,
            "title": tpl.title,
            "description": tpl.description,
        })
    return items


def make_template(code: str, **kwargs) -> BuildingTemplate:
    """Создаёт шаблон по коду с возможностью переопределить параметры."""
    factory = TEMPLATE_FACTORIES.get(code)
    if factory is None:
        raise ValueError(
            f"Неизвестный шаблон: {code}. Доступно: "
            f"{list(TEMPLATE_FACTORIES.keys())}"
        )
    return factory(**kwargs)


# ============================================================================
# Применение шаблона к HVACProject
# ============================================================================

def apply_template(project, template: BuildingTemplate,
                    *, project_name: Optional[str] = None,
                    city: Optional[str] = None) -> int:
    """Заменяет содержимое проекта набором помещений из шаблона.

    Возвращает количество созданных помещений.
    """
    name = project_name or template.title
    project.new_empty_project(project_name=name,
                                city=city or template.default_city)
    n = 0
    for room in template.rooms:
        for i in range(room.count):
            suffix = f"-{i + 1}" if room.count > 1 else ""
            sp = Space(
                space_id=f"sp_{n + 1:04d}",
                number=f"{room.level}-{n + 1:03d}",
                name=room.name + suffix,
                level=room.level,
                area_m2=room.area_m2,
                volume_m3=room.area_m2 * room.height_m,
                height_m=room.height_m,
                room_type=room.room_type,
                occupancy_people=room.occupancy_people,
                lighting_w_m2=room.lighting_w_m2,
                equipment_w_m2=room.equipment_w_m2,
                manual_entry=True,
            )
            project.spaces.append(sp)
            project._space_by_id[sp.space_id] = sp
            n += 1
    project.emit("data_loaded")
    project.emit("spaces_changed")
    return n
