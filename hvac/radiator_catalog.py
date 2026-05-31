# -*- coding: utf-8 -*-
"""Каталог отопительных приборов и подбор под расчётную нагрузку.

Тепловые характеристики приводятся к стандартным условиям EN 442:
температурный напор ΔTн = 50 K (Tпод/Tобр/Tпом = 75/65/20).

Пересчёт мощности на фактический температурный график:

    Q_факт = Q_номин · (ΔT_факт / ΔT_номин)^n

где n — экспонента теплоотдачи прибора (по EN 442):

    Чугунные секционные:     n ≈ 1.30
    Стальные панельные:      n ≈ 1.30
    Алюминиевые секционные:  n ≈ 1.34
    Биметаллические:         n ≈ 1.30
    Конвекторы:              n ≈ 1.35..1.40
    Тёплый пол:              n ≈ 1.10 (греющая поверхность)

ΔT — средний логарифмический температурный напор:

    ΔT = ((T_пд − T_пм) − (T_об − T_пм)) / ln((T_пд − T_пм)/(T_об − T_пм))

или арифметическое приближение (СП 60 п. 6.3):

    ΔT ≈ (T_пд + T_об)/2 − T_пм

Источники
---------
EN 442-2 (Radiators and convectors — Test methods and rating)
СП 60.13330.2020 п. 6.3, СП 60 Приложение В (методика подбора)
Каталоги Kermi (Therm-X2), Purmo (Compact), Rifar (Monolit, Base),
Global (Vox), Konner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


# ============================================================================
# Расчёт мощности при произвольном температурном графике
# ============================================================================

def log_mean_temp_diff(t_supply: float, t_return: float,
                       t_room: float) -> float:
    """Логарифмический средний температурный напор, K.

    ΔT = ((Tпд − Tпм) − (Tоб − Tпм)) / ln((Tпд − Tпм)/(Tоб − Tпм))

    При близких ΔT1 ≈ ΔT2 возвращает арифметическое.
    """
    a = t_supply - t_room
    b = t_return - t_room
    if a <= 0 or b <= 0:
        return 0.0
    if abs(a - b) < 0.1:
        return 0.5 * (a + b)
    return (a - b) / math.log(a / b)


def arithmetic_temp_diff(t_supply: float, t_return: float,
                         t_room: float) -> float:
    """Арифметический ΔT (СП 60 п. 6.3). Простое приближение."""
    return 0.5 * (t_supply + t_return) - t_room


def correct_power(q_nominal_w: float,
                   dt_actual: float,
                   dt_nominal: float = 50.0,
                   n: float = 1.30) -> float:
    """Q при фактическом ΔT из номинала по формуле EN 442.

        Q = Q_ном · (ΔT_факт / ΔT_ном)^n

    Если ΔT_факт ≤ 0 — прибор не отдаёт тепла.
    """
    if dt_actual <= 0 or dt_nominal <= 0:
        return 0.0
    return q_nominal_w * (dt_actual / dt_nominal) ** n


# ============================================================================
# Каталог
# ============================================================================

@dataclass
class RadiatorModel:
    """Один типоразмер прибора отопления.

    Q_nominal_w задано для условий EN 442 (75/65/20, ΔT_n = 50 K).
    Если у прибора задано section_count_per_step > 0 — это секционная
    модель: фактическое Q = section_count · q_per_section_w.
    """
    name: str                              # «Kermi FK0 22 500x1000»
    family: str = ""                       # «Стальной панельный», «Алюминий»
    height_mm: int = 0
    length_mm: int = 0                     # для секционных: длина одной секции
    depth_mm: int = 0
    q_nominal_w: float = 0.0               # при ΔT=50 K
    n_exponent: float = 1.30
    is_sectional: bool = False             # секционный (можно набирать секции)
    sections: int = 1                      # для записи о собранном радиаторе
    max_sections: int = 1                  # ограничение по производителю
    water_volume_l: float = 0.0
    weight_kg: float = 0.0
    note: str = ""

    def actual_power_w(self, t_supply: float, t_return: float,
                        t_room: float = 20.0,
                        use_log_mean: bool = True) -> float:
        """Фактическая мощность при заданном графике."""
        dt = (log_mean_temp_diff(t_supply, t_return, t_room)
              if use_log_mean else
              arithmetic_temp_diff(t_supply, t_return, t_room))
        return correct_power(self.q_nominal_w, dt,
                               dt_nominal=50.0, n=self.n_exponent)


# ============================================================================
# Генератор семейства Kermi FK0 / Purmo Compact
# ============================================================================
#
# Тепловой поток стального панельного радиатора с боковым подключением
# хорошо аппроксимируется линейной зависимостью от длины при фиксированной
# высоте и типе:
#
#     Q(L) = q_per_m · L_m
#
# Удельная мощность q_per_m (Вт на 1 м длины при ΔT=50K) по справочникам
# производителей (Kermi Therm-X2 FK0, Purmo Compact, Buderus K-Profil):

# Удельная мощность Q при ΔT=50K (Вт/м длины) по высоте и типу
KERMI_Q_PER_M: Dict[int, Dict[int, float]] = {
    # height_mm: {type11, type22, type33}
    300:  {11: 478, 22:  936, 33: 1366},
    400:  {11: 596, 22: 1170, 33: 1696},
    500:  {11: 722, 22: 1428, 33: 2076},
    600:  {11: 853, 22: 1684, 33: 2453},
    900:  {11: 1242, 22: 2454, 33: 3568},
}
# Удельный объём воды в радиаторе по высоте/типу (л/м длины)
KERMI_V_PER_M = {
    300:  {11: 1.7, 22: 3.1, 33: 4.5},
    400:  {11: 2.1, 22: 3.9, 33: 5.6},
    500:  {11: 2.6, 22: 4.6, 33: 6.9},
    600:  {11: 3.1, 22: 5.5, 33: 8.3},
    900:  {11: 4.4, 22: 8.0, 33: 12.1},
}
# Глубина (мм) одного типа
KERMI_DEPTH_MM = {11: 65, 22: 100, 33: 155}
# Длины из ряда производителя, мм
KERMI_LENGTHS_MM = [400, 500, 600, 700, 800, 900, 1000, 1200, 1400,
                     1600, 1800, 2000, 2300, 2600, 3000]

PURMO_Q_PER_M: Dict[int, Dict[int, float]] = {
    300:  {11: 471, 22:  922, 33: 1345},
    400:  {11: 589, 22: 1158, 33: 1689},
    500:  {11: 722, 22: 1428, 33: 2076},
    600:  {11: 865, 22: 1712, 33: 2492},
    900:  {11: 1245, 22: 2467, 33: 3592},
}
PURMO_LENGTHS_MM = KERMI_LENGTHS_MM
PURMO_DEPTH_MM = KERMI_DEPTH_MM


def _generate_panel_family(brand: str,
                             q_table: Dict[int, Dict[int, float]],
                             v_table: Dict[int, Dict[int, float]],
                             depth_mm: Dict[int, int],
                             lengths_mm: List[int]
                             ) -> List[RadiatorModel]:
    """Генерирует список RadiatorModel для семейства панельных радиаторов."""
    models: List[RadiatorModel] = []
    for h, by_type in q_table.items():
        for t, q_per_m in by_type.items():
            v_per_m = v_table.get(h, {}).get(t, 0.5 * t / 10)
            for L in lengths_mm:
                Lm = L / 1000.0
                q = q_per_m * Lm
                v = v_per_m * Lm
                w = 0.55 * q_per_m * Lm / 50.0   # вес ≈ 1 кг на 50 Вт
                models.append(RadiatorModel(
                    name=f"{brand} {t} {h}x{L}",
                    family=f"Стальной панельный {t}",
                    height_mm=h, length_mm=L, depth_mm=depth_mm[t],
                    q_nominal_w=q, n_exponent=1.30,
                    water_volume_l=v, weight_kg=w,
                ))
    return models


# ============================================================================
# Каталог типовых моделей
# ============================================================================
# Стальные панельные генерируются массово: 5 высот × 3 типа × 15 длин = 225
# моделей для каждого бренда. Алюминий/биметалл/чугун — секционные, заданы
# одной записью на секцию (max_sections учитывает ограничение производителя).
RADIATOR_CATALOG: List[RadiatorModel] = []

# ===== Kermi FK0 (Therm-X2) — полное семейство =====
RADIATOR_CATALOG.extend(_generate_panel_family(
    "Kermi FK0", KERMI_Q_PER_M, KERMI_V_PER_M,
    KERMI_DEPTH_MM, KERMI_LENGTHS_MM,
))

# ===== Purmo Compact =====
RADIATOR_CATALOG.extend(_generate_panel_family(
    "Purmo C", PURMO_Q_PER_M, KERMI_V_PER_M,
    PURMO_DEPTH_MM, PURMO_LENGTHS_MM,
))

# ===== Алюминиевые секционные =====
RADIATOR_CATALOG.extend([
    RadiatorModel("Global Vox 350 (секция)", "Алюминий", 350, 80, 95,
                  q_nominal_w=120, n_exponent=1.34, is_sectional=True,
                  max_sections=14, water_volume_l=0.20, weight_kg=1.0),
    RadiatorModel("Global Vox 500 (секция)", "Алюминий", 500, 80, 95,
                  q_nominal_w=185, n_exponent=1.34, is_sectional=True,
                  max_sections=14, water_volume_l=0.27, weight_kg=1.45),
    RadiatorModel("Global Vox 800 (секция)", "Алюминий", 800, 80, 95,
                  q_nominal_w=275, n_exponent=1.34, is_sectional=True,
                  max_sections=12, water_volume_l=0.38, weight_kg=2.0),
    RadiatorModel("Sira Alice 350 (секция)", "Алюминий", 350, 80, 95,
                  q_nominal_w=125, n_exponent=1.34, is_sectional=True,
                  max_sections=14, water_volume_l=0.22, weight_kg=1.05),
    RadiatorModel("Sira Alice 500 (секция)", "Алюминий", 500, 80, 95,
                  q_nominal_w=178, n_exponent=1.34, is_sectional=True,
                  max_sections=14, water_volume_l=0.27, weight_kg=1.42),
    RadiatorModel("Royal Thermo Indigo 500 (секция)", "Алюминий", 500, 80, 100,
                  q_nominal_w=195, n_exponent=1.34, is_sectional=True,
                  max_sections=14, water_volume_l=0.28, weight_kg=1.55),
])

# ===== Биметаллические =====
RADIATOR_CATALOG.extend([
    RadiatorModel("Rifar Base 200 (секция)", "Биметалл", 200, 80, 100,
                  q_nominal_w=104, n_exponent=1.30, is_sectional=True,
                  max_sections=14, water_volume_l=0.13, weight_kg=1.25),
    RadiatorModel("Rifar Base 350 (секция)", "Биметалл", 350, 80, 90,
                  q_nominal_w=136, n_exponent=1.30, is_sectional=True,
                  max_sections=14, water_volume_l=0.18, weight_kg=1.45),
    RadiatorModel("Rifar Base 500 (секция)", "Биметалл", 500, 80, 100,
                  q_nominal_w=204, n_exponent=1.30, is_sectional=True,
                  max_sections=14, water_volume_l=0.20, weight_kg=2.0),
    RadiatorModel("Rifar Monolit 350 (секция)", "Биметалл (моноблок)", 350, 80, 100,
                  q_nominal_w=134, n_exponent=1.30, is_sectional=True,
                  max_sections=12, water_volume_l=0.18, weight_kg=1.6),
    RadiatorModel("Rifar Monolit 500 (секция)", "Биметалл (моноблок)", 500, 80, 100,
                  q_nominal_w=196, n_exponent=1.30, is_sectional=True,
                  max_sections=12, water_volume_l=0.21, weight_kg=2.1),
    RadiatorModel("Royal Thermo BiLiner 500 (секция)", "Биметалл", 500, 80, 87,
                  q_nominal_w=171, n_exponent=1.30, is_sectional=True,
                  max_sections=14, water_volume_l=0.20, weight_kg=1.95),
    RadiatorModel("Sira RS Bimetal 500 (секция)", "Биметалл", 500, 80, 95,
                  q_nominal_w=181, n_exponent=1.30, is_sectional=True,
                  max_sections=14, water_volume_l=0.21, weight_kg=2.0),
])

# ===== Чугунные =====
RADIATOR_CATALOG.extend([
    RadiatorModel("МС-140-300 (секция)", "Чугун", 300, 93, 140,
                  q_nominal_w=120, n_exponent=1.30, is_sectional=True,
                  max_sections=10, water_volume_l=1.10, weight_kg=5.7),
    RadiatorModel("МС-140-500 (секция)", "Чугун", 500, 93, 140,
                  q_nominal_w=160, n_exponent=1.30, is_sectional=True,
                  max_sections=10, water_volume_l=1.45, weight_kg=7.1),
    RadiatorModel("МС-140-1200 (секция)", "Чугун", 388, 93, 140,
                  q_nominal_w=185, n_exponent=1.30, is_sectional=True,
                  max_sections=10, water_volume_l=1.50, weight_kg=8.1),
    RadiatorModel("Konner Modern 500 (секция)", "Чугун", 500, 80, 80,
                  q_nominal_w=110, n_exponent=1.30, is_sectional=True,
                  max_sections=10, water_volume_l=0.85, weight_kg=4.7),
    RadiatorModel("Konner Modern 300 (секция)", "Чугун", 300, 80, 80,
                  q_nominal_w=85, n_exponent=1.30, is_sectional=True,
                  max_sections=10, water_volume_l=0.65, weight_kg=3.8),
    RadiatorModel("Konner Lux 500 (секция)", "Чугун (дизайн)", 500, 90, 90,
                  q_nominal_w=120, n_exponent=1.30, is_sectional=True,
                  max_sections=8, water_volume_l=0.90, weight_kg=5.5),
])

# ===== Конвекторы =====
RADIATOR_CATALOG.extend([
    RadiatorModel("Универсал ТБ-100 (1 м)", "Конвектор настенный", 250, 1000, 130,
                  q_nominal_w=540, n_exponent=1.38, water_volume_l=2.2, weight_kg=8),
    RadiatorModel("Универсал ТБ-200 (1 м)", "Конвектор настенный", 350, 1000, 130,
                  q_nominal_w=820, n_exponent=1.38, water_volume_l=2.8, weight_kg=11),
    RadiatorModel("Универсал ТБ-300 (1 м)", "Конвектор настенный", 500, 1000, 130,
                  q_nominal_w=1120, n_exponent=1.38, water_volume_l=3.5, weight_kg=14),
    RadiatorModel("Минибрик-15 (внутрипольный)", "Конвектор внутрипольный",
                  150, 1000, 200, q_nominal_w=750, n_exponent=1.40,
                  water_volume_l=1.2, weight_kg=15),
])

# ===== Тёплый пол (виртуальная запись для подбора) =====
RADIATOR_CATALOG.extend([
    RadiatorModel("Тёплый пол REHAU 16x2", "Тёплый пол", 0, 100, 0,
                  q_nominal_w=85, n_exponent=1.10, is_sectional=True,
                  max_sections=200, water_volume_l=0.20, weight_kg=0.3,
                  note="Удельная мощность на 1 м² (~80 Вт/м²). max_sections — м²."),
])


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class RadiatorPick:
    """Результат подбора прибора отопления."""
    model: RadiatorModel
    sections: int                          # для секционных — сколько секций
    actual_power_w: float                  # фактическая Q при графике
    margin_pct: float                      # запас (Q_факт − Q_нужно)/Q_нужно
    note: str = ""


def select_radiator(
    required_power_w: float,
    t_supply: float = 80.0,
    t_return: float = 60.0,
    t_room: float = 20.0,
    *,
    family_filter: Optional[List[str]] = None,
    catalog: Optional[List[RadiatorModel]] = None,
    use_log_mean: bool = True,
    prefer_sectional: bool = False,
    min_margin: float = 0.0,
    max_margin: float = 0.50,
) -> Optional[RadiatorPick]:
    """Подбор одного отопительного прибора под требуемую нагрузку.

    Логика:
        - Для не-секционных: ищет модель в каталоге, чьё actual_power_w
          ближе всех к required_power_w сверху (с минимальным запасом).
        - Для секционных: считает число секций как ceil(Q/q_секции) и
          проверяет, не превышено ли max_sections.

    Параметры
    ---------
    family_filter      : список названий семейств (None — все)
    catalog            : альтернативный список моделей (по умолчанию глобальный)
    prefer_sectional   : True — приоритет секционных (более гибкий подбор)
    min_margin         : минимальный запас, доля (0.05 = +5%)
    max_margin         : максимально допустимый запас (1.00 = +100% — отказ)
    """
    cat = catalog if catalog is not None else RADIATOR_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]
    if not cat:
        return None

    candidates: List[RadiatorPick] = []
    for m in cat:
        q_unit = m.actual_power_w(t_supply, t_return, t_room,
                                    use_log_mean=use_log_mean)
        if q_unit <= 0:
            continue
        if m.is_sectional:
            need = math.ceil(required_power_w / q_unit * (1.0 + min_margin))
            if need > m.max_sections:
                continue
            need = max(need, 2)            # минимум 2 секции
            q_total = q_unit * need
        else:
            need = 1
            q_total = q_unit
            if q_total < required_power_w * (1.0 + min_margin):
                continue
        margin = (q_total - required_power_w) / required_power_w
        if margin > max_margin:
            continue
        candidates.append(RadiatorPick(
            model=m, sections=need,
            actual_power_w=q_total,
            margin_pct=margin * 100.0,
        ))

    if not candidates:
        return None

    # Предпочтения:
    # 1) prefer_sectional — секционные первыми
    # 2) Минимальный запас
    def _key(p: RadiatorPick):
        sec_priority = 0 if (prefer_sectional and p.model.is_sectional) else 1
        return (sec_priority, p.margin_pct)

    candidates.sort(key=_key)
    return candidates[0]


def select_radiators_for_spaces(
    spaces,
    t_supply: float = 80.0,
    t_return: float = 60.0,
    *,
    family_filter: Optional[List[str]] = None,
    prefer_sectional: bool = False,
) -> dict:
    """Подбор приборов для каждого помещения проекта.

    spaces : итерируемое из Space (используется space.heat_loss_w, t_in_heat).

    Возвращает {space_id: RadiatorPick | None}.
    """
    result: Dict[str, Optional[RadiatorPick]] = {}
    for sp in spaces:
        q = getattr(sp, "heat_loss_w", 0.0)
        if q <= 0:
            result[getattr(sp, "space_id", "")] = None
            continue
        t_room = getattr(sp, "t_in_heat", 20.0)
        pick = select_radiator(
            q, t_supply=t_supply, t_return=t_return, t_room=t_room,
            family_filter=family_filter, prefer_sectional=prefer_sectional,
        )
        result[getattr(sp, "space_id", "")] = pick
    return result
