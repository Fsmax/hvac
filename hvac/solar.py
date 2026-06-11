# -*- coding: utf-8 -*-
"""Солнечная геометрия и облучённость вертикальных фасадов из EPW.

EPW даёт только глобальную горизонтальную радиацию (GHI) — для
теплопоступлений через окна её нужно разнести по фасадам. Алгоритм
классический (Duffie & Beckman, «Solar Engineering of Thermal Processes»):

    1. Положение солнца (высота/азимут) по широте, долготе, часу года
       с уравнением времени и поправкой на часовой пояс.
    2. Разделение GHI на прямую и рассеянную составляющие по корреляции
       Эрбса (Erbs et al., 1982) через индекс прозрачности kT.
    3. Облучённость вертикальной поверхности = прямая по углу падения
       + изотропная рассеянная (вид на полнеба) + отражённая от земли.

Точность инженерная (±15% к измерениям на фасаде) — достаточно для
почасовой оценки теплопоступлений в hvac/energy_simulation.py.
"""

from __future__ import annotations

import math
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.weather import WeatherData

# Солнечная постоянная, Вт/м²
SOLAR_CONSTANT = 1367.0

# Альбедо подстилающей поверхности (трава/городская застройка)
GROUND_ALBEDO = 0.2

# Компасные азимуты секторов ориентации (N=0, по часовой)
ORIENT_AZIMUTH_DEG: Dict[str, float] = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}


def solar_position(lat_deg: float, lon_deg: float, tz_offset_h: float,
                   hour_of_year: int) -> tuple[float, float]:
    """Высота и азимут солнца (градусы) в данный час года.

    hour_of_year — 0..8759, местное поясное время (как в EPW); час h
    трактуется как середина интервала (h + 0.5), чтобы радиация за час
    соответствовала среднему положению солнца.
    Возвращает (altitude_deg, azimuth_deg); азимут компасный (N=0, E=90).
    """
    n = hour_of_year // 24 + 1                       # день года 1..365
    local_h = hour_of_year % 24 + 0.5

    # Уравнение времени, мин (Spencer/приближение Duffie & Beckman)
    b = math.radians(360.0 * (n - 81) / 364.0)
    eot_min = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)

    # Истинное солнечное время, ч
    solar_h = local_h + (4.0 * (lon_deg - 15.0 * tz_offset_h) + eot_min) / 60.0
    omega = math.radians(15.0 * (solar_h - 12.0))    # часовой угол

    # Склонение солнца
    decl = math.radians(23.45 * math.sin(math.radians(360.0 * (284 + n) / 365.0)))
    phi = math.radians(lat_deg)

    sin_alt = (math.sin(phi) * math.sin(decl)
               + math.cos(phi) * math.cos(decl) * math.cos(omega))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.degrees(math.asin(sin_alt))

    # Азимут от юга (запад положительный) → компасный от севера
    az_south = math.degrees(math.atan2(
        math.sin(omega),
        math.cos(omega) * math.sin(phi) - math.tan(decl) * math.cos(phi)))
    az = (180.0 + az_south) % 360.0
    return alt, az


def split_ghi_erbs(ghi: float, altitude_deg: float,
                   day_of_year: int) -> tuple[float, float]:
    """Делит GHI на (DNI, DHI) по корреляции Эрбса.

    DNI — прямая нормальная, DHI — рассеянная горизонтальная, Вт/м².
    При солнце ниже 2° над горизонтом вся радиация считается рассеянной
    (иначе деление на малый sin(alt) даёт нефизичные DNI).
    """
    if ghi <= 0.0:
        return 0.0, 0.0
    sin_alt = math.sin(math.radians(altitude_deg))
    if sin_alt < 0.035:                              # ~2° над горизонтом
        return 0.0, ghi

    g_on = SOLAR_CONSTANT * (
        1.0 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0)))
    g0h = g_on * sin_alt                             # внеатмосферная гориз.
    kt = min(ghi / g0h, 1.0)                         # индекс прозрачности

    if kt <= 0.22:
        kd = 1.0 - 0.09 * kt
    elif kt <= 0.80:
        kd = (0.9511 - 0.1604 * kt + 4.388 * kt ** 2
              - 16.638 * kt ** 3 + 12.336 * kt ** 4)
    else:
        kd = 0.165

    dhi = kd * ghi
    dni = (ghi - dhi) / sin_alt
    return dni, dhi


def vertical_irradiance(ghi: float, altitude_deg: float, azimuth_deg: float,
                        surface_azimuth_deg: float, day_of_year: int,
                        albedo: float = GROUND_ALBEDO) -> float:
    """Облучённость вертикальной поверхности данной ориентации, Вт/м²."""
    if ghi <= 0.0:
        return 0.0
    dni, dhi = split_ghi_erbs(ghi, altitude_deg, day_of_year)

    # Угол падения на вертикальную поверхность:
    # cosθ = cos(alt)·cos(az_солнца − az_поверхности)
    cos_inc = (math.cos(math.radians(altitude_deg))
               * math.cos(math.radians(azimuth_deg - surface_azimuth_deg)))
    beam = dni * max(0.0, cos_inc)
    diffuse = 0.5 * dhi                              # изотропное полнеба
    ground = 0.5 * albedo * ghi
    return beam + diffuse + ground


def facade_irradiance_year(wd: "WeatherData") -> Dict[str, List[float]]:
    """Почасовая облучённость 8 фасадов (N/NE/../NW) за год, Вт/м².

    Возвращает {сектор: [8760 значений]}. Если в файле нет радиации или
    координат (wd.has_solar == False) — все нули.
    """
    n_hours = len(wd.ghi_w_m2)
    out: Dict[str, List[float]] = {
        k: [0.0] * n_hours for k in ORIENT_AZIMUTH_DEG}
    if not wd.has_solar:
        return out

    for h in range(n_hours):
        ghi = wd.ghi_w_m2[h]
        if ghi <= 0.0:
            continue
        alt, az = solar_position(
            wd.latitude, wd.longitude, wd.tz_offset_h, h)
        if alt <= 0.0:
            continue
        day = h // 24 + 1
        for sector, s_az in ORIENT_AZIMUTH_DEG.items():
            out[sector][h] = vertical_irradiance(ghi, alt, az, s_az, day)
    return out
