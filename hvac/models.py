# -*- coding: utf-8 -*-
"""Структуры данных проекта."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.room_equipment import RoomEquipment


@dataclass
class BoundaryElement:
    """Элемент ограждения помещения (стена / окно / дверь)."""
    space_id: str
    row_type: str           # external_wall | opening
    is_exterior: bool       # реально граничит с улицей?
    element_id: str
    category: str
    family: str
    type_name: str
    boundary_length_m: float
    space_height_m: float
    approx_area_m2: float
    element_area_m2: float
    thickness_mm: float
    function: str
    host_element_id: str
    boundary_space_count: int

    # Назначаемые при расчёте
    construction_key: str = ""
    orientation_deg: Optional[float] = None
    orientation: str = ""             # N/NE/E/SE/S/SW/W/NW
    u_value: float = 0.0
    net_area_m2: float = 0.0

    # ===== v3.8: Элемент введён вручную (а не из Revit) =====
    # Когда True — элемент полностью сохраняется в JSON.
    manual_entry: bool = False


@dataclass
class Space:
    """Помещение (Revit MEP Space или Architectural Room)."""
    space_id: str
    number: str
    name: str
    level: str
    area_m2: float
    volume_m3: float
    height_m: float = 0.0

    # Назначаемые
    room_type: str = "Прочее"
    t_in_heat: float = 20.0
    t_in_cool: float = 24.0
    occupancy_people: float = 0.0
    lighting_w_m2: float = 12.0
    equipment_w_m2: float = 10.0
    ach_inf: float = 0.5

    is_corner: bool = False
    has_floor_to_ground: bool = False
    has_roof: bool = False
    is_top_floor: bool = False
    # Перекрытие над неотапливаемым подвалом/техподпольем: коэф. n<1 по
    # КМК 2.01.04-18 Табл.3. 0 — нет такого пола; 0.6 — над неотап. подвалом
    # со световыми проёмами; 0.4 — над техподпольем ниже уровня земли;
    # 0.8 — над холодным подвалом с наружным воздухом. Снижает Q=U·A·Δt·n.
    floor_over_unheated_n: float = 0.0

    # Расчётная относительная влажность в помещении (для проверки точки росы).
    # Если 0 — используется значение по типу помещения из dew_point.ROOM_TYPE_RH_DESIGN.
    rh_design: float = 0.0

    # Помечает помещения, отредактированные пользователем
    user_modified: bool = False

    # Результаты расчёта (теплопотери / теплопоступления)
    heat_loss_w: float = 0.0
    heat_gain_w: float = 0.0
    heat_loss_breakdown: Dict[str, float] = field(default_factory=dict)
    heat_gain_breakdown: Dict[str, float] = field(default_factory=dict)

    # Разделение теплопоступлений на явную и скрытую (СП 60 / ASHRAE)
    heat_gain_sensible_w: float = 0.0
    heat_gain_latent_w: float = 0.0
    heat_gain_breakdown_sensible: Dict[str, float] = field(default_factory=dict)
    heat_gain_breakdown_latent: Dict[str, float] = field(default_factory=dict)

    # Диагностика источника остекления (для сравнения этажей):
    # "real"   — расчёт идёт по реальному витражу из Revit (shgc>0, A>0.1 м²)
    # "wwr"    — реального стекла нет, использована WWR-оценка
    # "none"   — нет ни витража, ни WWR (внутренняя комната или WWR=0)
    glazing_source: str = "none"

    # Результаты расчёта вентиляции
    supply_m3h: float = 0.0          # приток, м³/ч
    exhaust_m3h: float = 0.0         # вытяжка, м³/ч
    hood_m3h: float = 0.0            # зонт кухни, м³/ч
    ach_calculated: float = 0.0      # фактическая кратность, 1/ч
    ventilation_breakdown: Dict = field(default_factory=dict)
    vent_user_modified: bool = False  # ручная правка → не пересчитывать

    # ===== Санитарные приборы (для расчёта вытяжки санузлов) =====
    # Если задано (>0), вытяжка санузла считается по приборам, а не по площади:
    # ШНҚ 2.08.02-23 табл.19 — 100 м³/ч на унитаз, 50 м³/ч на писсуар.
    wc_count: int = 0            # число унитазов
    urinal_count: int = 0        # число писсуаров

    # ===== Бассейны: влагоудаление по испарению с зеркала воды =====
    # Если задана площадь зеркала (>0), приток бассейна берёт max с расходом
    # на удаление влаги (испарение зависит от t воды). СП 31-113.
    water_surface_m2: float = 0.0   # площадь зеркала воды, м²
    water_temp_c: float = 0.0       # t воды, °C (0 = типовая 28)

    # Назначение в системы (для подбора оборудования)
    system_heating: str = ""         # например "Котёл A" или "Блок B01"
    system_cooling: str = ""         # например "Чиллер 1" или "Блок A"
    system_ventilation: str = ""     # например "AHU-A" или "Блок OFC"

    # Привязка к контуру внутри ИТП / венткамеры (опционально).
    # Если пусто — помещение попадает в дефолтный контур системы.
    # Пример: одно помещение может одновременно иметь радиаторы (circuit_heating
    # = "Рад-1") И фанкойлы по холоду (circuit_cooling = "ФК-1") и быть
    # обслуженным AHU "ПВ-1" в зоне "Зона А" (duct_zone = "Зона А").
    circuit_heating: str = ""        # имя HeatingCircuit
    circuit_cooling: str = ""        # имя CoolingCircuit
    duct_zone: str = ""              # имя DuctZone внутри AHU

    # ===== Воздушное отопление / охлаждение =====
    # Помещение отапливается/охлаждается самим приточным воздухом (без
    # радиаторов/фанкойлов). Когда True — расход приточки подбирается так,
    # чтобы перекрыть теплопотери (зимой) / теплопоступления (летом):
    #   L = Q / (0.28·ρ·c·Δt),  Δt = |t_подачи − t_помещения|,
    # и берётся max с вентиляционной нормой. Температура подачи и предельный
    # Δt — из обслуживающей VentilationSystem (t_supply_air_heating/cooling).
    # См. hvac/air_heating.py.
    air_heating: bool = False        # воздушное отопление (зима)
    air_cooling: bool = False        # воздушное охлаждение (лето)

    # Аварийные системы (дымоудаление, подпор воздуха)
    smoke_system: str = ""           # "СДУ-B1-01" — система дымоудаления
    pressurization_system: str = ""  # "СПВ-Л1" — система подпора (для лестниц/лифтов)
    smoke_zone_index: int = 0        # номер дымовой зоны внутри одной СДУ (для больших помещений)

    # ===== v3.8: Конечное оборудование, установленное в помещении =====
    # Что РЕАЛЬНО стоит в комнате: радиатор / фанкойл / решётка / диффузор.
    # Заполняется вручную пользователем после расчёта нагрузок.
    # Используется для формирования сводной таблицы оборудования.
    # default=None означает «оборудование ещё не назначено».
    room_equipment: Optional["RoomEquipment"] = None

    # ===== v3.8: Помещение создано вручную (а не из Revit) =====
    # Когда True — помещение сохраняется полностью в JSON
    # (с площадью, объёмом и т.п.), без зависимости от CSV.
    manual_entry: bool = False

    def get_or_create_equipment(self) -> "RoomEquipment":
        """Возвращает room_equipment, создавая пустой при необходимости."""
        if self.room_equipment is None:
            from hvac.room_equipment import RoomEquipment
            self.room_equipment = RoomEquipment()
        return self.room_equipment


@dataclass
class Layer:
    """Слой многослойной конструкции.

    R слоя = thickness_mm / 1000 / lambda_w_mk (для непрозрачных).
    Для воздушных прослоек и тонких плёнок задаётся r_m2k_w напрямую
    (тогда lambda_w_mk игнорируется).
    """
    material: str = ""           # «Кирпич керамический полнотелый», «Минвата», ...
    thickness_mm: float = 0.0    # толщина слоя
    lambda_w_mk: float = 0.0     # теплопроводность, Вт/(м·К)
    density_kg_m3: float = 0.0   # плотность (справочно)
    r_m2k_w: float = 0.0         # прямой R слоя (для воздушных прослоек)
    note: str = ""


# Сопротивление теплоотдаче, м²·К/Вт (СП 50.13330 табл. 4).
# Rsi — внутренняя поверхность; Rse — наружная.
RSI_DEFAULT = 0.115             # стены / окна (αi = 8.7)
RSE_DEFAULT = 0.043             # наружные ограждения (αe = 23)
RSI_ROOF = 0.115
RSE_ROOF = 0.043
RSI_FLOOR = 0.172               # пол (αi = 5.8)
RSE_FLOOR = 0.043


def _rsi_rse_for(category: str) -> tuple[float, float]:
    """Возвращает (Rsi, Rse) для категории по СП 50 табл. 4."""
    if category in ("Покрытие",):
        return RSI_ROOF, RSE_ROOF
    if category in ("Пол",):
        return RSI_FLOOR, RSE_FLOOR
    return RSI_DEFAULT, RSE_DEFAULT


@dataclass
class Construction:
    """Запись каталога конструкций.

    Если задан список `layers` — поле `u_value` пересчитывается
    `compute_u()` по сумме R слоёв. Иначе используется значение,
    введённое пользователем напрямую (упрощённый режим).
    """
    key: str
    category: str
    family: str
    type_name: str
    thickness_mm: float
    u_value: float = 0.0
    shgc: float = 0.6
    note: str = ""
    layers: list = field(default_factory=list)   # list[Layer]

    def total_r_m2k_w(self) -> float:
        """Полное сопротивление R₀ = Rsi + Σ R_слоёв + Rse, м²·К/Вт.
        Возвращает 0 если слоёв нет."""
        if not self.layers:
            return 0.0
        rsi, rse = _rsi_rse_for(self.category)
        r = rsi + rse
        for layer in self.layers:
            if layer.r_m2k_w > 0:
                r += layer.r_m2k_w
            elif layer.lambda_w_mk > 0 and layer.thickness_mm > 0:
                r += (layer.thickness_mm / 1000.0) / layer.lambda_w_mk
        return r

    def compute_u(self) -> float:
        """U из слоёв. 0.0 если слои не заданы."""
        r = self.total_r_m2k_w()
        return 1.0 / r if r > 0 else 0.0

    def recompute_u_from_layers(self) -> bool:
        """Если есть слои — пересчитывает u_value. Возвращает True если пересчитано."""
        if self.layers:
            u = self.compute_u()
            if u > 0:
                self.u_value = u
                return True
        return False


@dataclass
class ProjectParameters:
    """Общие параметры проекта."""
    project_name: str = "Проект"
    city: str = "Ташкент"
    t_out_heating: float = -16.0
    t_out_cooling: float = 36.0
    daily_amplitude: float = 14.0
    solar_intensity_w_m2: float = 750.0
    gsop_18: float = 0.0          # ГСОП (t_в=+20°C, ≤8°C); имя «_18» историческое
    # Должно совпадать с именем зарегистрированного движка (hvac/engine).
    # Узбекистан по умолчанию: КМК (соответствует thermal_norm="KMK_UZ").
    methodology: str = "КМК 2.04.05-91 + КМК 2.01.04-18"
    inf_correction_k: float = 0.7
    safety_margin_heating: float = 1.10
    safety_margin_cooling: float = 1.15

    # Влагосодержание для расчёта скрытой теплоты инфильтрации.
    # Снаружи: типичное для лета. Тёплый влажный климат ≈12, средний ≈10, сухой ≈7 г/кг.
    # Внутри: при 24°C и 50% RH ≈ 9.3 г/кг.
    w_out_summer_g_kg: float = 8.0
    w_in_summer_g_kg: float = 9.3

    # Оценка остекления (если из Revit окна выгрузились неполно).
    # 0.0 — отключено (использовать только реальные данные из Revit).
    # 0.6 — типичный офис с витражами (60% наружной стены — стекло).
    # 0.4 — обычное здание с окнами.
    # При WWR > 0 программа добавляет виртуальные окна к каждой
    # наружной стене с заданным U_window и SHGC.
    # ВАЖНО: WWR применяется ТОЛЬКО к стенам помещений где НЕТ реальных
    # окон/витражей. Если в помещении уже есть стекло из Revit — оно
    # учитывается напрямую, и WWR на стены не накладывается.
    wwr_estimate: float = 0.0
    wwr_u_window: float = 1.8       # U витража / окна, Вт/(м²·К)
    wwr_shgc: float = 0.4           # коэффициент пропускания солнца

    # Коэффициент затенения солнца (жалюзи, маркизы, козырьки).
    # 1.0 — без затенения, 0.7 — внутренние жалюзи / тонировка,
    # 0.5 — внешние ламели / маркизы, 0.3 — глубокие ниши + жалюзи.
    solar_shading_factor: float = 1.0

    # Поворот True North относительно Project North, градусы.
    # Положительное значение = поворот ПРОТИВ часовой стрелки (как у
    # стандартной розы ветров: N=0, E=90, S=180, W=270).
    # Применяется ко всем orientation_deg перед солнечным расчётом и
    # вычислением сектора (N/NE/E/...).
    # Пример: если в Revit Project North направлен «вверх», а реальный
    # True North повёрнут на 45° против часовой (как на плане со стрелкой
    # N в верх-лево) — введите +45. Тогда стена, экспортнутая как N (0°),
    # будет в расчёте считаться как NE (45°).
    true_north_offset_deg: float = 0.0

    beta_orientation: Dict[str, float] = field(default_factory=lambda: {
        "N": 0.10, "NE": 0.10, "E": 0.05, "SE": 0.05,
        "S": 0.00, "SW": 0.00, "W": 0.05, "NW": 0.10, "": 0.05,
    })

    # Активный норматив противодымной защиты:
    #   "SP7_RU"  — СП 7.13130.2013 (по умолчанию)
    #   "KMK_UZ"  — КМК 2.04.05-22 (Узбекистан)
    #   "NFPA_92" — NFPA 92 (США)
    #   "CUSTOM"  — пользовательский профиль (редактируется в проекте)
    # См. hvac/catalogs/smoke_norms.py
    smoke_norm: str = "SP7_RU"

    # Активный норматив строительной теплотехники (Δt_н по таблицам):
    #   "KMK_UZ" — КМК 2.01.04-18 (Узбекистан, по умолчанию — основная норма)
    #   "SP_RU"  — СП 50.13330 (РФ)
    # См. hvac/dew_point.py (DT_NORM_BY_NORM).
    thermal_norm: str = "KMK_UZ"

    def apply_city(self, city_name: str) -> bool:
        """Применяет климат города из CLIMATE_DB. Возвращает True если нашло."""
        from hvac.catalogs.climate import CLIMATE_DB
        info = CLIMATE_DB.get(city_name)
        if not info:
            return False
        self.city = city_name
        self.t_out_heating = info["t_heat_092"]
        self.t_out_cooling = info["t_cool_095"]
        self.daily_amplitude = info["daily_amp"]
        self.solar_intensity_w_m2 = info["solar_vert"]
        self.gsop_18 = info.get("gsop_18", 0)
        return True
