# -*- coding: utf-8 -*-
"""Системы дымоудаления (СДУ) и подпора воздуха (СПВ).

Аварийные системы пожарной безопасности. Параметры дефолтов и набор
доступных calc_method зависят от активного норматива проекта
(`project.params.smoke_norm`) — см. `hvac/catalogs/smoke_norms.py`.

Типы систем:
  • smoke_removal — вытяжная СДУ (удаление дыма)
  • air_supply    — приточная СПВ (подпор в защищаемый объём:
                    лестница, лифт, тамбур-шлюз)
  • compensation  — компенсирующая подача (вместе с СДУ)

Методы расчёта расхода (calc_method):
  • norm_per_m2         — упрощённо: L = area × norm
  • kmk_zone_perimeter  — КМК Прил. 20 ф.(3): G = 676.8·P·y^1.5·Ks
  • kmk_corridor        — КМК Прил. 22 ф.(1)/(2): G = K·B·n(B)·H^1.5 [·Kd]
  • nfpa_plume_axi      — NFPA 92 п. 5.5.1: m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc
  • corridor_formula    — упрощённая формула для коридоров > 15 м (наследие)
  • kmk_pressurization  — подпор по скорости в открытой двери
                          (ШНК 2.04.05-22 п.340: L = 3600·v·F·n, v=1,3 м/с)
  • stairs_pressure     — подпор по нормативу для лестниц (табличный, наследие)
  • elevator_pressure   — подпор для лифтовых шахт (табличный, наследие)
  • manual              — расход задаёт пользователь
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SmokeSystem:
    """Система дымоудаления или подпора воздуха."""
    name: str                              # "СДУ-B1-01", "СПВ-Л1"
    system_type: str = "smoke_removal"     # smoke_removal / air_supply / compensation
    purpose: str = "parking"               # parking / warehouse / corridor / atrium /
                                            # stairs / elevator / vestibule / refuge

    # Метод расчёта
    calc_method: str = "norm_per_m2"
    norm_per_m2: float = 24.0              # м³/ч на 1 м² (для norm_per_m2)
    max_zone_area_m2: float = 1600.0       # максимум одной дымовой зоны
    pressure_pa: float = 20.0              # избыточное давление, Па (для air_supply)

    # ===== Параметры для формул плюм-теории (КМК / NFPA) =====
    # КМК 2.04.05-22, Прил. 20:
    fire_perimeter_m: float = 12.0         # P — периметр очага пожара, м (ф.3, max 12)
    layer_height_m: float = 2.5            # y — высота свободной от дыма зоны, м (мин 2.5)
    ks_sprinkler: float = 1.0              # Ks: 1.0 без спринклеров, 1.2 — со спринклерами
    # Коридор/холл, КМК 2.04.05-22 Прил.22 ф.(1)/(2): G = K·B·n(B)·H^1.5·[Kd]
    corridor_door_width_m: float = 1.2     # B — ширина большей створки двери, м
    corridor_door_height_m: float = 2.0    # H — высота двери, м (при >2.5 → 2.5)
    corridor_public: bool = True           # True — общ./адм.-быт./произв. (4300·Kd),
                                            # False — жилые (3420)
    kd_door: float = 1.0                   # Kd — коэф. продолжит. открывания (только ф.2)
    # NFPA 92, п. 5.5.1 (axisymmetric plume):
    hrr_kw: float = 5000.0                 # Q — мощность тепловыделения пожара, кВт
    convective_fraction: float = 0.7       # доля конвективной мощности (Qc = 0.7·Q)
    plume_height_m: float = 6.0            # z — высота от очага до слоя дыма, м

    # ===== Подпор воздуха (СПВ), ШНК 2.04.05-22 §7, пп. 340–341 =====
    # Метод kmk_pressurization: L = 3600 · v · F_door · n_open_doors
    door_area_m2: float = 1.8              # F — площадь проёма двери (большей створки), м²
    v_door_m_s: float = 1.3                # v — скорость в открытой двери (п. 340: 1,3 м/с)
    n_open_doors: int = 1                  # число одновременно открытых дверей
    pres_max_pa: float = 150.0             # макс. давление на закрытых дверях эвакуации (п. 341)

    # Расчётные значения (заполняются программой)
    L_smoke_m3h: float = 0.0               # суммарный расход дыма
    L_makeup_m3h: float = 0.0              # компенсирующая подача (70-80% от L_smoke)
    served_area_m2: float = 0.0            # обслуживаемая площадь
    n_zones: int = 1                       # количество дымовых зон (расчётное)
    n_zones_manual: int = 0                # ручное число дымовых зон (0 = авто по площади)
    L_per_zone_m3h: float = 0.0            # расход одной дымовой зоны (для подбора вент.)

    # Параметры дыма / воздуха
    t_smoke_C: float = 300.0               # расчётная температура дыма
    makeup_ratio: float = 0.7              # доля компенсирующей подачи (0.7 = 70%)

    # Огнестойкость оборудования
    fire_rating: str = "F400-120"          # класс огнестойкости (t°C - время в мин)
    note: str = ""


# Типовые нормативы (по умолчанию, пользователь может переопределить).
# Источник: СП 7.13130.2013 / КМК 2.04.05.
DEFAULT_SMOKE_NORMS = {
    # Расход дыма, м³/ч на 1 м²
    "parking_closed":    24.0,        # закрытая подземная парковка
    "parking_above":     18.0,        # надземная закрытая парковка
    "warehouse_low":     50.0,        # склад с малой пожарной нагрузкой
    "warehouse_high":    100.0,       # склад с высокой пожарной нагрузкой
    "corridor":          60.0,        # коридор (упрощённо, точный по формуле)
    "office_assembly":   30.0,        # помещения сборки людей
    "trading_hall":      60.0,        # торговый зал
}


# Типовой расход подпора, м³/ч (упрощённо; точный — по площади дверей)
DEFAULT_PRESSURIZATION_RATES = {
    "stairs":    8000.0,       # лестничная клетка (один пролёт)
    "elevator":  5000.0,       # шахта лифта
    "vestibule": 3000.0,       # тамбур-шлюз
    "refuge":    3000.0,       # зона безопасности МГН
}
