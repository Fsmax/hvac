# -*- coding: utf-8 -*-
"""Каталог нормативов противодымной защиты.

Поддерживаемые нормативные документы:
    • SP7_RU  — СП 7.13130.2013 (Российская Федерация)
    • KMK_UZ  — КМК 2.04.05-22  (Республика Узбекистан, ред. 2022 г.)
    • NFPA_92 — NFPA 92 (США, ред. 2018 г.)

ВАЖНО О ЗНАЧЕНИЯХ
==================

Все три документа в части расчёта расхода дымоудаления используют
ФИЗИЧЕСКИЕ формулы (плюм-теория, перепад давления, мощность пожара),
а не таблицы вида «м³/ч на 1 м² помещения». Подход «площадь × норма»,
который исторически применяется в РФ/СНГ-практике, — это эмпирическое
УПРОЩЕНИЕ, восходящее к СНиП 2.04.05-91*, и в действующих сводах в
явном виде ОТСУТСТВУЕТ.

Поэтому в норматив-профилях ниже:

    • поле `norm_per_m2` — практическое инженерное значение для быстрой
      оценки. Применять для предварительного подбора оборудования или
      когда полные данные по очагу пожара (HRR, периметр, высота слоя
      дыма) ещё не получены;

    • поле `calc_method_recommended` — указывает, какой РАСЧЁТНЫЙ метод
      даёт точный результат по конкретному нормативу (формулы реализованы
      в `hvac/smoke_formulas.py`).

Для проектной документации, проходящей экспертизу, использовать
рекомендованный метод и сверять значения с действующей редакцией
норматива.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SmokeNorm:
    """Описание одного нормативного документа по противодымной защите."""

    code: str                # машинный ID: "SP7_RU", "KMK_UZ", "NFPA_92", "CUSTOM"
    title: str               # человекочитаемое имя для UI
    reference: str           # точная ссылка на документ
    note: str = ""           # пояснение / ограничения

    # Упрощённые «практические» нормы расхода дыма, м³/ч на 1 м²
    # обслуживаемой площади. Использовать для быстрой оценки.
    norms_per_m2: Dict[str, float] = field(default_factory=dict)

    # Расход подпора воздуха в защищаемые объёмы (лестница / лифт /
    # тамбур-шлюз / зона безопасности МГН), м³/ч.
    pressurization_rates_m3h: Dict[str, float] = field(default_factory=dict)

    # Максимальная площадь одной дымовой зоны, м²
    max_zone_area_m2: float = 1600.0

    # Доля компенсирующей подачи к расходу дыма (0.7 = 70%)
    default_makeup_ratio: float = 0.7

    # Расчётная температура удаляемого дыма, °C
    default_t_smoke_C: float = 300.0

    # Класс огнестойкости вентилятора СДУ по умолчанию
    default_fire_rating: str = "F400-120"

    # Избыточное давление подпора в защищаемом объёме, Па
    default_pressure_pa: float = 20.0

    # Рекомендованный точный метод расчёта (см. smoke_formulas.py).
    # Допустимые значения:
    #   "norm_per_m2"          — упрощённо по площади
    #   "kmk_zone_perimeter"   — КМК Прил. 20, формула (3): G = 676.8·P·y^1.5·Ks
    #   "kmk_corridor"         — КМК Прил. 20, формула (1)/(2): G1 = 3420·n^1.5
    #   "nfpa_plume_axi"       — NFPA 92 п. 5.5.1, axisymmetric plume
    calc_method_recommended: str = "norm_per_m2"

    # Список доступных в этом нормативе методов (для выпадающего списка в UI)
    available_calc_methods: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# СП 7.13130.2013 (РФ)
# ---------------------------------------------------------------------------
# В самом своде формулы для м³/ч·м² отсутствуют. Перечисленные значения —
# инженерная практика РФ, восходящая к СНиП 2.04.05-91*, активно
# используется в проектной документации и пособиях АВОК / МДС.
SP7_RU = SmokeNorm(
    code="SP7_RU",
    title="СП 7.13130.2013 (РФ)",
    reference="Свод правил СП 7.13130.2013 «Отопление, вентиляция и "
              "кондиционирование. Требования пожарной безопасности», п. 7",
    note="Точный расчёт расхода дыма выполняется по формулам приложения "
         "(п. 7.5, методика [4]). Значения по типам — упрощённая "
         "инженерная практика, восходящая к СНиП 2.04.05-91*.",
    norms_per_m2={
        "parking_closed":    24.0,   # закрытая подземная парковка
        "parking_above":     18.0,   # надземная закрытая парковка
        "warehouse_low":     50.0,   # склад категории В4 и ниже
        "warehouse_high":   100.0,   # склад категорий В1–В3
        "corridor":          60.0,   # коридор (упрощённо; точно — формула)
        "office_assembly":   30.0,   # помещения сборки людей
        "trading_hall":      60.0,   # торговый зал
    },
    pressurization_rates_m3h={
        "stairs":     8000.0,   # лестничная клетка незадымляемая Н2/Н3
        "elevator":   5000.0,   # шахта лифта (один лифт)
        "vestibule":  3000.0,   # тамбур-шлюз
        "refuge":     3000.0,   # зона безопасности МГН (п. 7.15)
    },
    max_zone_area_m2=1600.0,        # п. 7.3 а): не более 1600 м² одной зоны
    default_makeup_ratio=0.7,        # п. 8.5: 70% от расхода СДУ
    default_t_smoke_C=300.0,
    default_fire_rating="F400-120",  # п. 7.11: типичное для большинства зон
    default_pressure_pa=20.0,        # п. 7.14: 20 Па избыточного
    calc_method_recommended="norm_per_m2",
    available_calc_methods=["norm_per_m2", "manual"],
)


# ---------------------------------------------------------------------------
# КМК 2.04.05-22 (Узбекистан, действующая редакция 2022 г.)
# ---------------------------------------------------------------------------
# Документ содержит детальные формулы плюм-теории в приложениях 20–22:
#   • Прил. 20, ф.(1):  G1 = 3420·n^1.5             — коридор/холл
#   • Прил. 20, ф.(2):  G1 = 4300·n^1.5·Kd          — коридор с дверями
#   • Прил. 20, ф.(3):  G = 676.8·P·y^1.5·Ks        — помещение ≤ 1600 м²
#   • Прил. 20, ф.(5):  G1 = 3584·Ad·[h0(ρin−ρ)ρin + 0.7V²ρin²]^0.5·Ks
#                                                    — атриум / многосветное
# Упрощённые значения ниже копируют инженерную практику СП 7 (КМК и
# СНиП 2.04.05-91 — общий корень) и должны использоваться только для
# предварительной оценки.
KMK_UZ = SmokeNorm(
    code="KMK_UZ",
    title="КМК 2.04.05-22 (Узбекистан)",
    reference="КМК 2.04.05-22 «Отопление, вентиляция и кондиционирование», "
              "Прил. 20–22 (формулы расчёта расхода дыма)",
    note="Действующая редакция содержит формулы плюм-теории. Для проектной "
         "документации использовать метод 'kmk_zone_perimeter' (помещения) "
         "и 'kmk_corridor' (коридоры). Значения по типам — копия инженерной "
         "практики, требует сверки с конкретным проектом.",
    norms_per_m2={
        "parking_closed":    24.0,
        "parking_above":     18.0,
        "warehouse_low":     50.0,
        "warehouse_high":   100.0,
        "corridor":          60.0,
        "office_assembly":   30.0,
        "trading_hall":      60.0,
    },
    pressurization_rates_m3h={
        "stairs":     8000.0,
        "elevator":   5000.0,
        "vestibule":  3000.0,
        "refuge":     3000.0,
    },
    max_zone_area_m2=1600.0,
    default_makeup_ratio=0.7,
    default_t_smoke_C=300.0,
    default_fire_rating="F400-120",
    default_pressure_pa=20.0,
    calc_method_recommended="kmk_zone_perimeter",
    available_calc_methods=[
        "norm_per_m2", "kmk_zone_perimeter", "kmk_corridor", "manual",
    ],
)


# ---------------------------------------------------------------------------
# NFPA 92 (США, ред. 2018 г.)
# ---------------------------------------------------------------------------
# NFPA 92 не использует подход «м³/ч на 1 м²» — все расчёты основаны на
# теории плюма (раздел 5.5):
#   • п. 5.5.1.1:  m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc   (z > zl)
#   • п. 5.5.2:    balcony spill plume                       — для атриумов
#   • п. 5.5.3:    window plume                              — для оконных
# Упрощённые значения в norms_per_m2 — справочные ориентиры из ASHRAE/SFPE
# Handbook для предварительной оценки (parking ≈ 0.5 cfm/sqft = 9 м³/ч·м²,
# atrium handbook tables и т.п.). НЕ являются нормативными требованиями
# NFPA 92.
NFPA_92 = SmokeNorm(
    code="NFPA_92",
    title="NFPA 92 (США, 2018)",
    reference="NFPA 92 Standard for Smoke Control Systems, 2018 ed., "
              "Section 5 (Smoke Management Calculations)",
    note="Стандарт основан на плюм-теории — нет норм «расход на м²». "
         "Используйте метод 'nfpa_plume_axi' с заданием HRR пожара и высоты "
         "слоя дыма. Значения в таблице ниже — справочные ориентиры "
         "ASHRAE/SFPE Handbook (НЕ нормативные требования NFPA).",
    norms_per_m2={
        # Источник: ASHRAE Smoke Control Handbook + IBC 909.8 practice
        "parking_closed":     9.0,   # ≈ 0.5 cfm/sqft (IBC mech. exhaust)
        "parking_above":      9.0,
        "warehouse_low":     27.0,   # ≈ 1.5 cfm/sqft typical
        "warehouse_high":    54.0,   # ≈ 3.0 cfm/sqft high challenge
        "corridor":          18.0,   # ≈ 1.0 cfm/sqft IBC base
        "office_assembly":   18.0,
        "trading_hall":      36.0,   # ≈ 2.0 cfm/sqft mall typical
    },
    pressurization_rates_m3h={
        # NFPA 92 п. 4.4: stairway pressurization, типичные значения
        "stairs":     6800.0,   # ≈ 4000 cfm типовая
        "elevator":   4250.0,   # ≈ 2500 cfm
        "vestibule":  2550.0,   # ≈ 1500 cfm
        "refuge":     2550.0,
    },
    max_zone_area_m2=4645.0,        # 50 000 sqft per IBC 909.6.3 typical
    default_makeup_ratio=0.85,       # п. 4.4.4: makeup < 95% mass of exhaust
    default_t_smoke_C=300.0,
    default_fire_rating="F400-120",  # эквивалент UL 2043 / 2 hr Class A
    default_pressure_pa=12.5,        # 0.05 in WC, п. 4.4.2 (12.5 Па)
    calc_method_recommended="nfpa_plume_axi",
    available_calc_methods=[
        "norm_per_m2", "nfpa_plume_axi", "manual",
    ],
)


# ---------------------------------------------------------------------------
# CUSTOM — пользовательский профиль
# ---------------------------------------------------------------------------
# Начальные значения скопированы с SP7_RU. Пользователь правит вручную
# через UI; изменения сохраняются в проектный JSON.
CUSTOM = SmokeNorm(
    code="CUSTOM",
    title="Свой профиль",
    reference="Пользовательские значения (редактируются в проекте)",
    note="Начальные значения скопированы с СП 7.13130.2013. "
         "Редактируйте таблицы под конкретные нормативные требования.",
    norms_per_m2=dict(SP7_RU.norms_per_m2),
    pressurization_rates_m3h=dict(SP7_RU.pressurization_rates_m3h),
    max_zone_area_m2=SP7_RU.max_zone_area_m2,
    default_makeup_ratio=SP7_RU.default_makeup_ratio,
    default_t_smoke_C=SP7_RU.default_t_smoke_C,
    default_fire_rating=SP7_RU.default_fire_rating,
    default_pressure_pa=SP7_RU.default_pressure_pa,
    calc_method_recommended="norm_per_m2",
    available_calc_methods=[
        "norm_per_m2", "kmk_zone_perimeter", "kmk_corridor",
        "nfpa_plume_axi", "manual",
    ],
)


# ---------------------------------------------------------------------------
# Реестр и доступ
# ---------------------------------------------------------------------------
SMOKE_NORMS: Dict[str, SmokeNorm] = {
    "SP7_RU":  SP7_RU,
    "KMK_UZ":  KMK_UZ,
    "NFPA_92": NFPA_92,
    "CUSTOM":  CUSTOM,
}

DEFAULT_SMOKE_NORM_CODE = "SP7_RU"


def get_smoke_norm(code: str) -> SmokeNorm:
    """Возвращает норматив по коду. Если код неизвестен — SP7_RU."""
    return SMOKE_NORMS.get(code, SP7_RU)


def list_smoke_norms() -> List[SmokeNorm]:
    """Список всех зарегистрированных нормативов (для UI)."""
    return list(SMOKE_NORMS.values())
