# -*- coding: utf-8 -*-
"""Формулы расчёта расхода дыма по нормативам КМК и NFPA.

Все функции возвращают расход в МАССОВЫХ единицах (кг/ч), плюс хелпер
`mass_to_volume_m3h` для перевода в объёмный расход через плотность
газа при заданной температуре.

Источники
---------
КМК 2.04.05-22 «Отопление, вентиляция и кондиционирование», Прил. 22
(совпадает со СНиП 2.04.05-91* Прил. 22):
    - формула (1): G = 3420·B·n·H^1.5         (коридор, жилые)
    - формула (2): G = 4300·B·n·H^1.5·Kd      (коридор, общественные)
    - формула (3): G = 676.8·P·y^1.5·Ks       (помещение ≤ 1600 м²)
      где B — ширина створки двери, H — высота двери (≤2.5 м),
      n — табличный коэф. от B, Kd — коэф. продолжительности открывания.

NFPA 92 (2018) Section 5.5.1 (axisymmetric plume):
    Limiting height of plume: zl = 0.166·Qc^(2/5)        [5.5.1.1c]
    Mass flow in plume:
        z >  zl :  m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc   [5.5.1.1a]
        z <= zl :  m = 0.032·Qc^(3/5)·z                      [5.5.1.1b]
    Qc — convective heat release rate (кВт), обычно Qc ≈ 0.7·Q.
    Возвращаемый m — в кг/с (по стандарту), переводим в кг/ч (×3600).
"""

from __future__ import annotations


# Универсальная газовая постоянная для воздуха, Дж/(кг·К)
R_AIR = 287.0
# Атмосферное давление на уровне моря, Па
P_ATM = 101_325.0


# ---------------------------------------------------------------------------
#  КМК 2.04.05-22 — формулы плюма для помещений и коридоров
# ---------------------------------------------------------------------------

def kmk_zone_perimeter_kg_h(fire_perimeter_m: float,
                             layer_height_m: float,
                             ks_sprinkler: float = 1.0) -> float:
    """КМК Прил. 20, формула (3): расход дыма из помещения, кг/ч.

        G = 676.8 · P · y^1.5 · Ks

    Параметры
    ---------
    fire_perimeter_m : P — периметр очага пожара, м. По нормативу
                       принимается max 12 м (при большем — расчёт по плюму
                       3-го рода, см. формулу (5)).
    layer_height_m   : y — высота от пола до нижней границы дымового слоя,
                       м. Минимум 2.5 м по нормативу.
    ks_sprinkler     : Ks = 1.0 без спринклеров, 1.2 — при наличии
                       автоматической системы пожаротушения.

    Применение
    ----------
    Для помещений с площадью ≤ 1600 м² и периметром очага ≤ 12 м.
    """
    if fire_perimeter_m <= 0 or layer_height_m <= 0:
        return 0.0
    P = min(fire_perimeter_m, 12.0)
    y = max(layer_height_m, 2.5)
    return 676.8 * P * (y ** 1.5) * ks_sprinkler


# Коэффициент n из таблицы КМК/СНиП 2.04.05 Прил.22 в зависимости от
# ширины большей створки двери B, м. Опорные точки B и значения n:
_CORRIDOR_B_POINTS = (0.6, 0.9, 1.2, 1.8, 2.4)
_CORRIDOR_N_RESIDENTIAL = (1.00, 0.82, 0.70, 0.51, 0.41)   # жилые (ф.1)
_CORRIDOR_N_PUBLIC = (1.05, 0.91, 0.80, 0.62, 0.50)        # общ./адм./произв. (ф.2)


def corridor_n_coefficient(door_width_m: float, is_public: bool = False) -> float:
    """Коэффициент n по табл. КМК/СНиП 2.04.05 Прил.22.

    Линейная интерполяция по ширине створки B между опорными точками
    (0.6…2.4 м); за пределами таблицы — clamp на крайние значения.
    """
    table = _CORRIDOR_N_PUBLIC if is_public else _CORRIDOR_N_RESIDENTIAL
    pts = _CORRIDOR_B_POINTS
    b = door_width_m
    if b <= pts[0]:
        return table[0]
    if b >= pts[-1]:
        return table[-1]
    for i in range(len(pts) - 1):
        if pts[i] <= b <= pts[i + 1]:
            k = (b - pts[i]) / (pts[i + 1] - pts[i])
            return table[i] + k * (table[i + 1] - table[i])
    return table[-1]


def kmk_corridor_kg_h(door_width_m: float, door_height_m: float = 2.0,
                      is_public: bool = False, kd_door: float = 1.0) -> float:
    """Расход дыма из коридора/холла, кг/ч — КМК/СНиП 2.04.05 Прил.22.

        жилые:         G = 3420 · B · n · H^1.5          (ф.1)
        общественные:  G = 4300 · B · n · H^1.5 · Kd     (ф.2)

    Параметры
    ---------
    door_width_m  : B — ширина большей открываемой створки двери из коридора
                    на лестничную клетку или наружу, м.
    door_height_m : H — высота двери, м. При H>2.5 принимается H=2.5.
    is_public     : True → общественные/адм.-быт./производственные (ф.2,
                    коэф. 4300, множитель Kd). False → жилые (ф.1, коэф. 3420).
    kd_door       : Kd — коэф. относительной продолжительности открывания
                    дверей (1.0 при эвакуации ≥25 чел через дверь, 0.8 при
                    <25). Применяется только в ф.2 (общественные).

    Коэффициент n берётся из таблицы Прил.22 по ширине B (см.
    corridor_n_coefficient).
    """
    if door_width_m <= 0 or door_height_m <= 0:
        return 0.0
    h = min(door_height_m, 2.5)
    n = corridor_n_coefficient(door_width_m, is_public)
    if is_public:
        return 4300.0 * door_width_m * n * (h ** 1.5) * kd_door
    return 3420.0 * door_width_m * n * (h ** 1.5)


# ---------------------------------------------------------------------------
#  NFPA 92 (2018) — axisymmetric plume
# ---------------------------------------------------------------------------

def nfpa_axisymmetric_plume_kg_s(hrr_kw: float,
                                  plume_height_m: float,
                                  convective_fraction: float = 0.7) -> float:
    """NFPA 92, п. 5.5.1: массовый расход в осесимметричном плюме, кг/с.

    Limiting height (п. 5.5.1.1c):
        zl = 0.166 · Qc^(2/5)

    При z > zl  (п. 5.5.1.1a):
        m = 0.071 · Qc^(1/3) · z^(5/3) + 0.0018 · Qc

    При z ≤ zl  (п. 5.5.1.1b — внутри пламени):
        m = 0.032 · Qc^(3/5) · z

    Параметры
    ---------
    hrr_kw              : Q — полная мощность тепловыделения пожара, кВт.
    plume_height_m      : z — высота от очага до нижней границы слоя дыма, м.
    convective_fraction : доля конвективной мощности от полной (Qc = α·Q).
                          Типично 0.7 для пламенного горения.

    Возвращает
    ----------
    Массовый расход в плюме, кг/с (затем умножить на 3600 для кг/ч).
    """
    if hrr_kw <= 0 or plume_height_m <= 0:
        return 0.0
    Qc = hrr_kw * convective_fraction        # convective HRR, kW
    zl = 0.166 * (Qc ** (2.0 / 5.0))         # limiting plume height
    z = plume_height_m
    if z > zl:
        return 0.071 * (Qc ** (1.0 / 3.0)) * (z ** (5.0 / 3.0)) + 0.0018 * Qc
    else:
        return 0.032 * (Qc ** (3.0 / 5.0)) * z


def nfpa_axisymmetric_plume_kg_h(hrr_kw: float,
                                  plume_height_m: float,
                                  convective_fraction: float = 0.7) -> float:
    """То же, что nfpa_axisymmetric_plume_kg_s, но в кг/ч (×3600)."""
    return nfpa_axisymmetric_plume_kg_s(
        hrr_kw, plume_height_m, convective_fraction) * 3600.0


# ---------------------------------------------------------------------------
#  Конвертация массового расхода в объёмный
# ---------------------------------------------------------------------------

def smoke_density_kg_m3(t_smoke_C: float) -> float:
    """Плотность сухого воздуха при заданной температуре, кг/м³.
    Используется как приближение для плотности дыма (его молекулярная
    масса близка к воздуху)."""
    T_K = t_smoke_C + 273.15
    if T_K <= 0:
        return 1.205
    return P_ATM / (R_AIR * T_K)


def mass_to_volume_m3h(mass_flow_kg_h: float, t_smoke_C: float) -> float:
    """Переводит массовый расход дыма (кг/ч) в объёмный (м³/ч)
    при заданной температуре дыма."""
    rho = smoke_density_kg_m3(t_smoke_C)
    if rho <= 0:
        return 0.0
    return mass_flow_kg_h / rho


# ---------------------------------------------------------------------------
#  Унифицированный диспетчер: calc_method → объёмный расход м³/ч
# ---------------------------------------------------------------------------

def calc_smoke_flow_m3h(system, area_m2: float) -> float:
    """Универсальная функция: рассчитывает расход одной дымовой зоны
    в м³/ч для любого calc_method у SmokeSystem.

    Параметры
    ---------
    system   : SmokeSystem с заполненными полями метода
    area_m2  : площадь одной дымовой зоны (для norm_per_m2)

    Возвращает
    ----------
    Объёмный расход дыма, м³/ч. Для неизвестных методов — 0.
    """
    method = system.calc_method
    t_smoke = system.t_smoke_C

    if method == "norm_per_m2":
        return area_m2 * system.norm_per_m2

    if method == "kmk_zone_perimeter":
        G_kg_h = kmk_zone_perimeter_kg_h(
            system.fire_perimeter_m,
            system.layer_height_m,
            system.ks_sprinkler,
        )
        return mass_to_volume_m3h(G_kg_h, t_smoke)

    if method == "kmk_corridor":
        G_kg_h = kmk_corridor_kg_h(
            system.corridor_door_width_m,
            system.corridor_door_height_m,
            is_public=system.corridor_public,
            kd_door=system.kd_door,
        )
        return mass_to_volume_m3h(G_kg_h, t_smoke)

    if method == "nfpa_plume_axi":
        G_kg_h = nfpa_axisymmetric_plume_kg_h(
            system.hrr_kw,
            system.plume_height_m,
            system.convective_fraction,
        )
        return mass_to_volume_m3h(G_kg_h, t_smoke)

    if method == "manual":
        # Ручной ввод — возвращаем как есть из L_smoke_m3h
        return system.L_smoke_m3h

    # Неизвестный метод — fallback на norm_per_m2
    return area_m2 * system.norm_per_m2
