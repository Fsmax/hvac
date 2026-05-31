# -*- coding: utf-8 -*-
"""Оборудование: приточные установки, котлы, чиллеры.

Каждая система имеет имя (например "П1", "Котёл A", "Чиллер 1") и
индивидуальные параметры. Помещения ссылаются на имена через
sp.system_ventilation / system_heating / system_cooling.

При расчёте нагрузки от приточки программа берёт параметры
конкретной AHU (КПД рекуператора, температура подачи) и считает
индивидуальную нагрузку для каждой установки.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Типы контуров (HeatingCircuit.circuit_type / CoolingCircuit.circuit_type)
# ---------------------------------------------------------------------------

HEATING_CIRCUIT_TYPES = [
    "radiator",        # радиаторы / конвекторы (типично 80/60)
    "floor",           # тёплый пол (типично 45/35, со смесительным узлом)
    "fancoil",         # фанкойлы по теплу (2-трубные: общая с холодом; 4-тр.: 60/40)
    "ahu_heater",      # калорифер приточной установки (60/40 или 80/60)
]

COOLING_CIRCUIT_TYPES = [
    "fancoil",         # фанкойлы (типично 7/12)
    "ahu_cooler",      # охладитель приточной установки (7/12)
    "chilled_beam",    # охлаждаемые балки (типично 14/17 — для борьбы с конденсатом)
]


# Дефолты по типу контура: (t_supply, t_return)
HEATING_CIRCUIT_DEFAULTS = {
    "radiator":    (80.0, 60.0),
    "floor":       (45.0, 35.0),
    "fancoil":     (60.0, 40.0),
    "ahu_heater":  (80.0, 60.0),
}

COOLING_CIRCUIT_DEFAULTS = {
    "fancoil":      (7.0, 12.0),
    "ahu_cooler":   (7.0, 12.0),
    "chilled_beam": (14.0, 17.0),
}


@dataclass
class HeatingCircuit:
    """Контур отопления внутри HeatingSystem (ИТП / котельной).

    Один источник тепла обычно питает 2-4 независимых контура:
    радиаторы, тёплый пол, фанкойлы, калориферы AHU. У каждого свой
    насос, своя температура подачи/обратки и свой расход.
    """
    name: str                              # "ТП-1", "Рад-1", "AHU-1"
    parent_system: str = ""                # имя HeatingSystem (ИТП)
    circuit_type: str = "radiator"         # см. HEATING_CIRCUIT_TYPES

    # Температурный график контура (может отличаться от родительской системы:
    # например котёл 80/60, тёплый пол 45/35 через смесительный узел)
    t_supply: float = 80.0
    t_return: float = 60.0
    has_mixing_node: bool = False          # есть смесительный узел?

    # Привязка к AHU (только для circuit_type='ahu_heater'):
    # имя VentilationSystem, чей калорифер питается этим контуром
    serves_ahu: str = ""

    # Подобранный циркуляционный насос (заполняется после гидравл. расчёта)
    pump_model: str = ""
    pump_flow_m3_h: float = 0.0
    pump_head_m: float = 0.0
    pump_head_reserve: float = 1.3         # запас на загрязнение/балансировку

    # Материал труб для этого контура (steel / pex / ppr)
    pipe_material: str = "steel"

    note: str = ""


@dataclass
class CoolingCircuit:
    """Контур холодоснабжения внутри CoolingSystem (чиллер / VRF-вода)."""
    name: str
    parent_system: str = ""
    circuit_type: str = "fancoil"          # см. COOLING_CIRCUIT_TYPES

    t_supply: float = 7.0
    t_return: float = 12.0

    serves_ahu: str = ""                   # для circuit_type='ahu_cooler'

    pump_model: str = ""
    pump_flow_m3_h: float = 0.0
    pump_head_m: float = 0.0
    pump_head_reserve: float = 1.3

    pipe_material: str = "steel"
    insulated: bool = True                 # для холода обычно изолируется

    note: str = ""


@dataclass
class DuctZone:
    """Зона воздуховодов внутри VentilationSystem (AHU).

    Универсальная модель: годится и для VAV-зон, и для постоянного расхода.
    Если has_vav=False — зона работает на постоянном расходе (CAV).
    """
    name: str                              # "Зона А", "Этаж 2"
    parent_ahu: str = ""                   # имя VentilationSystem
    has_vav: bool = False                  # VAV (переменный расход)?

    # Требуемое статическое давление в зоне (для подбора магистрального
    # вентилятора AHU и/или зонного доводчика)
    static_pressure_pa: float = 0.0

    # Если в зоне есть вспомогательный (зонный) вентилятор — его параметры
    has_zone_fan: bool = False
    zone_fan_flow_m3_h: float = 0.0
    zone_fan_pressure_pa: float = 0.0

    note: str = ""


@dataclass
class VentilationSystem:
    """Приточная / вытяжная / приточно-вытяжная установка (AHU)."""
    name: str                              # "П1", "ПВ-A", "В1"
    system_type: str = "supply_exhaust"    # "supply" / "exhaust" / "supply_exhaust"

    # Рекуперация тепла
    has_recovery: bool = False
    recovery_efficiency_winter: float = 0.0  # 0..1, КПД зимой
    recovery_efficiency_summer: float = 0.0  # КПД летом (обычно ниже)

    # Температура подаваемого воздуха (после AHU)
    t_supply_winter: float = 16.0          # обычно 16-18°C
    t_supply_summer: float = 18.0          # обычно 16-18°C

    # Влагосодержание подачи летом (для контроля осушения)
    w_supply_summer: float = 9.3           # г/кг, при 24°C/50% RH

    # Привязка калорифера/охладителя AHU к контурам ИТП.
    # Используется, чтобы добавить нагрузку AHU в гидравлический расчёт
    # соответствующего контура отопления / холодоснабжения.
    heating_circuit: str = ""              # имя HeatingCircuit (питает калорифер)
    cooling_circuit: str = ""              # имя CoolingCircuit (питает охладитель)

    note: str = ""


@dataclass
class HeatingSystem:
    """Источник тепла: котёл, тепловой насос, центральное отопление."""
    name: str                              # "Котёл A", "ТП-1"
    system_type: str = "boiler_gas"        # "boiler_gas" / "boiler_electric" /
                                            # "heat_pump" / "central"
    t_supply: float = 80.0                 # температура теплоносителя, °C
    t_return: float = 60.0                 # обратки, °C
    fuel: str = "gas"                      # "gas" / "electric" / "diesel" / "central"
    efficiency: float = 0.92               # КПД источника
    note: str = ""


@dataclass
class CoolingSystem:
    """Источник холода: чиллер, VRF, сплит-система."""
    name: str                              # "Чиллер 1"
    system_type: str = "chiller_air"       # "chiller_air" / "chiller_water" /
                                            # "vrf" / "split"
    t_supply: float = 7.0                  # температура хладоносителя, °C
    t_return: float = 12.0                 # обратки, °C
    cop: float = 3.5                       # коэффициент эффективности (EER/COP)
    refrigerant: str = "R410A"
    note: str = ""
