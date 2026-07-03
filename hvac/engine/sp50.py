# -*- coding: utf-8 -*-
"""Расчётный движок по СП 50.13330 (теплопотери) и СП 60.13330
(теплопоступления).

Формула теплопотерь:
    Q = Σ K·F·(tв − tн)·n·(1 + Σβ) + Qинф − Qбыт

Формула теплопоступлений (упрощённый блочный расчёт):
    Q = Q_огражд + Q_солн + Q_люди + Q_свет + Q_обор + Q_вент
"""

from __future__ import annotations
from typing import Dict
from hvac.engine.base import CalculationEngine, register_engine, air_density
from hvac.catalogs.constructions import DEFAULT_U_BY_CATEGORY
from hvac.parsers import effective_orientation


# Проектные часы (солнечное время), по которым ищется пиковая солнечная
# нагрузка. На каждый час солнце в одной точке неба, поэтому при суммировании
# по фасадам не складываются утренний и вечерний максимумы (учёт
# одновременности).
SOLAR_DESIGN_HOURS = (8, 10, 12, 14, 16, 18)

# Доля проектной вертикальной радиации (I_solar), падающей на фасад данной
# ориентации в каждый из SOLAR_DESIGN_HOURS. Максимум каждой строки совпадает
# с прежними пиковыми коэффициентами (N=0.20 … W=0.95), но теперь пики разнесены
# во времени: комната с остеклением на один фасад сохраняет свой пик, а угловая
# или сквозная больше не получает сумму несовпадающих пиков. 0.20 — рассеянная
# радиация (как у северного фасада весь день).
SOLAR_HOURLY_FACTOR = {
    #       08     10     12     14     16     18
    "N":  (0.20,  0.20,  0.20,  0.20,  0.20,  0.20),
    "NE": (0.55,  0.35,  0.20,  0.20,  0.20,  0.20),
    "E":  (0.85,  0.55,  0.22,  0.20,  0.20,  0.20),
    "SE": (0.70,  0.75,  0.50,  0.25,  0.20,  0.20),
    "S":  (0.30,  0.55,  0.65,  0.55,  0.30,  0.20),
    "SW": (0.20,  0.25,  0.50,  0.85,  0.75,  0.30),
    "W":  (0.20,  0.20,  0.22,  0.55,  0.95,  0.60),
    "NW": (0.20,  0.20,  0.20,  0.30,  0.55,  0.50),
    # Неизвестная ориентация — консервативно держим пик во все часы.
    "":   (0.65,  0.65,  0.65,  0.65,  0.65,  0.65),
}

# Коэффициент аккумуляции солнечной теплоты остеклением (CLF, метод CLTD/CLF,
# СП 60 / ASHRAE). Часть прошедшей радиации поглощается массивом ограждений и
# отдаётся в помещение со сдвигом по времени, поэтому пиковая нагрузка на холод
# меньше мгновенно прошедшей радиации. 0.75 — здание средней массивности.
SOLAR_CLF = 0.75

# Сопротивление R для 4-зонного расчёта пола по грунту (СП 50.13330 прил. Е).
# Полоса 2 м от внутренней поверхности наружной стены.
FLOOR_ZONE_R_M2K_W = {
    1: 2.1,    # Зона I (внешние 2 м по периметру)
    2: 4.3,    # Зона II
    3: 8.6,    # Зона III
    4: 14.2,   # Зона IV (центр)
}


def _floor_4zone_areas(area_m2: float, perimeter_m: float) -> Dict[int, float]:
    """Разбивка площади пола на 4 зоны по СП 50.13330 прил. Е.
    
    Зона I — полоса 2 м вдоль наружных стен (углы 2×2 м считаются ДВАЖДЫ).
    Зона II — следующие 2 м внутрь.
    Зона III — следующие 2 м.
    Зона IV — оставшаяся центральная часть.
    
    Возвращает {1: F_I, 2: F_II, 3: F_III, 4: F_IV}.
    """
    if perimeter_m <= 0 or area_m2 <= 0:
        return {1: area_m2, 2: 0, 3: 0, 4: 0}
    
    zones = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    remaining = area_m2
    
    # Зона I: 2 м вдоль ВСЕХ наружных стен.
    # Площадь = 2 × периметр (углы 2×2 учтены дважды, как требует СП).
    f1 = min(2 * perimeter_m, remaining)
    zones[1] = f1
    remaining -= f1
    if remaining <= 0:
        return zones
    
    # Зона II: 2 м внутрь, минус 4 угла 2×2 = -16 м² (из периметра уходит 4×2 м с каждой стороны)
    # Эффективный периметр для зоны II: P - 16 м (если положителен)
    p2_effective = max(perimeter_m - 16, 0)
    f2 = min(2 * p2_effective, remaining)
    zones[2] = f2
    remaining -= f2
    if remaining <= 0:
        return zones
    
    # Зона III: ещё минус 16
    p3_effective = max(perimeter_m - 32, 0)
    f3 = min(2 * p3_effective, remaining)
    zones[3] = f3
    remaining -= f3
    if remaining <= 0:
        return zones
    
    # Зона IV: всё оставшееся
    zones[4] = remaining
    return zones


def _calc_floor_loss_4zone(area_m2: float, perimeter_m: float,
                            dt: float) -> float:
    """Теплопотери через пол по грунту по 4-зонному методу СП 50.13330."""
    if dt <= 0 or area_m2 <= 0:
        return 0.0
    zones = _floor_4zone_areas(area_m2, perimeter_m)
    q = 0.0
    for zone_num, f in zones.items():
        if f > 0:
            r = FLOOR_ZONE_R_M2K_W[zone_num]
            q += f * dt / r
    return q


# Коэффициенты распределения теплоты от оборудования по типам помещений.
# (Доля явной / доля скрытой). Сумма = 1.0
EQUIPMENT_SENSIBLE_RATIO = {
    "Офис": 0.90,                  # компьютеры — почти всё явное
    "Серверная": 0.95,             # сервера — практически только явное
    "Жилая комната": 0.85,
    "Гостиничный номер": 0.85,
    "Магазин / торговля": 0.85,
    "Ресторан / зал": 0.80,        # зал: техника невелика, в осн. явная
    "Кухня": 0.55,                 # бытовая плита → заметная скрытая (пар)
    "Горячий цех": 0.45,           # плиты, пароконвектоматы → много скрытой
    "Технич. помещение": 0.95,
    "Прочее": 0.85,
}


def _latent_infiltration_w(L_m3h: float, delta_w_g_kg: float) -> float:
    """Скрытая теплота инфильтрации.
    Q = m_dot · Δw · h_fg, где h_fg ≈ 2500 кДж/кг при 20°C.
    В практичных единицах: Q[Вт] = 0.83 · L[м³/ч] · Δw[г/кг]"""
    return 0.83 * L_m3h * delta_w_g_kg


def infiltration_flow_m3h(space, params, has_exterior: bool = True,
                          has_transfer_donor: bool = False) -> float:
    """Расход инфильтрующегося НАРУЖНОГО воздуха, который догревают радиаторы
    помещения, м³/ч (КМК 2.04.05-91 / СП 60.13330).

    Логика по балансу механической вентиляции:
    - НЕТ механической вентиляции (приток=0 и вытяжка=0) → естественный
      воздухообмен по ach_inf (как раньше): G = ach_inf · V.
    - ЕСТЬ механическая вентиляция → приточный наружный воздух греет калорифер
      приточной установки ОТДЕЛЬНО (нагрузка AHU, не радиаторов). Радиаторы
      догревают только подсос:
        * подпор (приток ≥ вытяжки+зонт) → помещение под избыточным давлением,
          инфильтрация ≈ фон (params.infiltration_min_ach · V);
        * преобладание вытяжки (кухни с зонтами) → подсасывается недостающий
          воздух: G = (вытяжка + зонт − приток).
      Итог: G = max(infiltration_min_ach · V, вытяжка + зонт − приток).

    has_transfer_donor=True — у ЧИСТО ВЫТЯЖНОГО помещения (приток=0, без зонта:
    санузел) есть смежное помещение с притоком. Тогда весь расход вытяжки
    восполняется ПЕРЕТОКОМ из соседа при внутренней t, а наружную долю этого
    перетока греет приточная установка соседа (баланс _balance_transfer_air).
    На приборы данного помещения ложится только фон по оболочке
    (G = infiltration_min_ach · V), а не полный расход вытяжки. Иначе вытяжка
    санузла считается дважды: и на радиаторе санузла как наружный воздух
    (раздутые Вт/м²), и на калорифере приточки соседа.

    has_exterior=False — ВНУТРЕННЕЕ помещение (нет наружных ограждений). Прямого
    воздухообмена с улицей нет: и естественная инфильтрация, и подсос на дефицит
    вытяжки восполняются ПЕРЕТОКОМ из смежных помещений при внутренней
    температуре. Наружный воздух за этот переток кондиционирует приточная
    установка смежного помещения, поэтому на приборы данного помещения нагрузка
    от инфильтрации не ложится (иначе — двойной счёт по зданию). Типичный
    случай — внутренние санузлы (exhaust_only): без этого правила им вешается
    полный расход вытяжки при наружной t (раздутые Вт/м²).
    """
    if not has_exterior:
        return 0.0
    sup = getattr(space, "supply_m3h", 0.0) or 0.0
    hood = getattr(space, "hood_m3h", 0.0) or 0.0
    exh = (getattr(space, "exhaust_m3h", 0.0) or 0.0) + hood
    if sup <= 0.0 and exh <= 0.0:
        return (space.ach_inf or 0.0) * (space.volume_m3 or 0.0)
    floor = getattr(params, "infiltration_min_ach", 0.0) * (space.volume_m3 or 0.0)
    if sup <= 0.0 and hood <= 0.0 and has_transfer_donor:
        # Чисто вытяжное помещение (санузел) со смежным донором (приток>0):
        # расход вытяжки восполняется перетоком при внутренней t, его наружную
        # долю греет приточка соседа. На приборы — только фон по оболочке.
        return floor
    deficit = max(0.0, exh - sup)
    return max(deficit, floor)


def _has_supplied_neighbor(space, project) -> bool:
    """Есть ли у помещения смежное (по общей стене) помещение с притоком > 0.

    Такой сосед — донор перетока: его приток восполняет вытяжку данного
    помещения (типично санузел ← номер). Сосед берётся по общему Revit-id
    стены (element_id), как в _internal_partition_flux; перегородки тоже.
    """
    seen: set = set()
    for el in project.elements_for(space.space_id):
        if el.row_type != "external_wall":
            continue
        for nid in project.wall_neighbor_space_ids(el.element_id, space.space_id):
            if nid in seen:
                continue
            seen.add(nid)
            nb = project._space_by_id.get(nid)
            if nb is not None and (getattr(nb, "supply_m3h", 0.0) or 0.0) > 0.0:
                return True
    return False


def _internal_partition_flux(space, project, params, cooling: bool) -> float:
    """Тепловой поток через ВНУТРЕННИЕ перегородки к/от смежных помещений иной
    температуры, Вт (КМК 2.04.05-91: учитывается при Δt ≥ min_dt).

    cooling=False — теплопотери зимой к более ХОЛОДНЫМ соседям;
    cooling=True  — теплопоступления летом от более ТЁПЛЫХ соседей.

    Сосед за стеной берётся по общему Revit-id стены (element_id). Если стена
    граничит с несколькими помещениями, её площадь делится между ними поровну
    (точное разбиение по сегментам доступно только из геометрии Revit).
    Учитываются только стены (не проёмы) и только перепад в «невыгодную»
    сторону (потери зимой / приток тепла летом).
    """
    min_dt = getattr(params, "internal_partition_min_dt", 3.0)
    u_default = getattr(params, "u_internal_partition", 1.5)
    t_self = space.t_in_cool if cooling else space.t_in_heat
    q = 0.0
    for el in project.elements_for(space.space_id):
        if el.is_exterior or el.row_type != "external_wall":
            continue
        area = el.net_area_m2 or el.approx_area_m2 or 0.0
        if area <= 0:
            continue
        nb_ids = project.wall_neighbor_space_ids(el.element_id, space.space_id)
        if not nb_ids:
            continue
        share = area / len(nb_ids)
        u = el.u_value if el.u_value > 0 else u_default
        for nid in nb_ids:
            nb = project._space_by_id.get(nid)
            if nb is None:
                continue
            dt = (nb.t_in_cool - t_self) if cooling else (t_self - nb.t_in_heat)
            if dt >= min_dt:
                q += u * share * dt
    return q


def _room_has_real_glazing(elems, constructions) -> bool:
    """Содержит ли помещение реальное остекление из Revit?

    Критерий: хотя бы один элемент имеет конструкцию с SHGC>0 и
    нетто-площадь > 0.1 м². Используется чтобы решить, нужно ли
    дополнительно моделировать виртуальное окно через WWR-оценку.
    """
    for e in elems:
        con = constructions.get(e.construction_key)
        if con is not None and con.shgc > 0 and e.net_area_m2 > 0.1:
            return True
    return False


def _wwr_split(el, params, has_real_glazing: bool,
               is_glazed: bool = False) -> tuple[float, float]:
    """Делит площадь стены на (wall_area, window_area) с учётом WWR-оценки.

    Применяется только если у помещения нет реального остекления и
    элемент — наружная стена с заметной площадью. Иначе возвращает
    (исходная площадь, 0) — то есть WWR не применяется.

    Параметр is_glazed дополнительно исключает прозрачные конструкции
    из WWR-моделирования (нужно для heat_loss, где glazed-элементы идут
    в общий цикл; в heat_gain glazed обрабатывается отдельно и сюда не
    попадает).
    """
    if (params.wwr_estimate > 0
            and not has_real_glazing
            and not is_glazed
            and el.row_type == "external_wall"
            and el.net_area_m2 > 1.0):
        window_area = el.net_area_m2 * params.wwr_estimate
        return el.net_area_m2 - window_area, window_area
    return el.net_area_m2, 0.0


@register_engine
class SP50Engine(CalculationEngine):
    """СП 50.13330 + СП 60.13330 (РФ/СНГ)."""

    @property
    def name(self) -> str:
        return "СП 50.13330 + СП 60.13330"

    # ---------- надбавки (точки расширения для других норм) ----------
    def _corner_room_addition(self, space, ext_elems) -> float:
        """Добавочная надбавка β на угловое помещение (≥2 наружных стен).

        В СП 50.13330 эта надбавка СНиП 2.04.05-91 отменена → 0.0.
        КМК 2.04.05-91 её сохраняет — переопределяется в KMKEngine.
        """
        return 0.0

    # ---------- теплопотери ----------
    def heat_loss(self, space, project) -> Dict[str, float]:
        p = project.params
        dt = space.t_in_heat - p.t_out_heating
        if dt <= 0:
            return {"ИТОГО": 0.0}

        breakdown: Dict[str, float] = {}
        q_trans = 0.0

        elems = [e for e in project.elements_for(space.space_id) if e.is_exterior]
        has_real_glazing = _room_has_real_glazing(elems, project.constructions)
        # Надбавка на угловое помещение (норма-зависимая: СП 50 = 0, КМК = 0.05)
        corner_add = self._corner_room_addition(space, elems)

        # Поворот True North → Project North (если задан)
        tn_offset = getattr(p, "true_north_offset_deg", 0.0)

        for el in elems:
            if el.u_value <= 0 or el.net_area_m2 <= 0:
                continue
            # Эффективная ориентация с учётом поворота True North
            eff_orient = effective_orientation(el.orientation,
                                                el.orientation_deg,
                                                tn_offset)
            n_coef = 1.0
            beta = 0.0
            beta += p.beta_orientation.get(eff_orient, 0.05)
            # Надбавка на угловое помещение (+0.05) из СНиП 2.04.05-91 / КМК
            # 2.04.05-91; в СП 50.13330 отменена (corner_add=0 в SP50Engine).
            beta += corner_add
            if space.height_m > 4.0:
                beta += min((space.height_m - 4.0) * 0.02, 0.15)

            # WWR применяется только к стенам (НЕ к существующему стеклу)
            # и только если в помещении нет реального остекления
            con = project.constructions.get(el.construction_key)
            is_glazed = con is not None and con.shgc > 0
            wall_area, window_area = _wwr_split(el, p, has_real_glazing,
                                                 is_glazed=is_glazed)

            # Часть стены
            if wall_area > 0:
                q_wall = el.u_value * wall_area * dt * n_coef * (1.0 + beta)
                q_trans += q_wall
                cat = el.category if el.row_type == "external_wall" else "Проёмы"
                breakdown[cat] = breakdown.get(cat, 0.0) + q_wall

            # Виртуальное окно (WWR)
            if window_area > 0:
                q_win = p.wwr_u_window * window_area * dt * n_coef * (1.0 + beta)
                q_trans += q_win
                breakdown["Окна (WWR)"] = breakdown.get("Окна (WWR)", 0.0) + q_win

        # Пол по грунту (4-зонный расчёт по СП 50.13330 прил. Е)
        if space.has_floor_to_ground:
            # Периметр наружных стен помещения
            perimeter = sum(
                e.boundary_length_m for e in project.elements_for(space.space_id)
                if e.row_type == "external_wall" and e.is_exterior
            )
            # Если периметр = 0 (внутреннее помещение подвала), используем
            # упрощённую оценку периметра по площади: P ≈ 4·√A
            if perimeter <= 0:
                perimeter = 4 * (space.area_m2 ** 0.5)
            q_floor = _calc_floor_loss_4zone(space.area_m2, perimeter, dt)
            q_trans += q_floor
            breakdown["Пол по грунту"] = q_floor

            # Подземные стены (для подвальных помещений с контактом с грунтом).
            # Площадь подземной стены: периметр × высота, U_eff ≈ 0.45 / 1.5
            # (грунт даёт доп. R ≈ 1.5 м²К/Вт).
            # Применяется только если у помещения нет учтённых наружных стен,
            # или если их площадь меньше периметра × высоты.
            ext_wall_area = sum(
                e.net_area_m2 for e in project.elements_for(space.space_id)
                if e.row_type == "external_wall" and e.is_exterior
            )
            potential_underground = perimeter * space.height_m
            underground_area = max(potential_underground - ext_wall_area, 0)
            if underground_area > 0 and space.height_m > 0:
                # U подземной стены = 1 / (1/U_wall + R_ground)
                u_wall = DEFAULT_U_BY_CATEGORY["Стены"]
                R_ground = 1.5  # доп. сопротивление грунта, СП 50 прил. Е
                u_eff = 1.0 / (1.0/u_wall + R_ground)
                q_underground = u_eff * underground_area * dt
                q_trans += q_underground
                breakdown["Стены в грунте"] = q_underground

        # Перекрытие над неотапливаемым подвалом/техподпольем (КМК Табл.3):
        # Q = U·A·Δt·n, где n<1 учитывает «тёплую» зону под полом.
        if space.floor_over_unheated_n > 0:
            u_floor = DEFAULT_U_BY_CATEGORY.get("Пол", 0.35)
            q_floor_unh = (u_floor * space.area_m2 * dt
                           * space.floor_over_unheated_n)
            q_trans += q_floor_unh
            breakdown["Пол над неотап."] = q_floor_unh

        # Совмещённое покрытие.
        # Применяем средние надбавки по СП 50.13330: высота + N-ориентация
        # (покрытие условно считается горизонтальным с n=1).
        if space.has_roof or space.is_top_floor:
            u_roof = DEFAULT_U_BY_CATEGORY["Покрытие"]
            beta_roof = p.beta_orientation.get("N", 0.10)
            if space.height_m > 4.0:
                beta_roof += min((space.height_m - 4.0) * 0.02, 0.15)
            q_roof = u_roof * space.area_m2 * dt * (1.0 + beta_roof)
            q_trans += q_roof
            breakdown["Покрытие"] = q_roof

        # Внутренние перегородки к более холодным смежным помещениям
        # (КМК 2.04.05-91). Для внутренних помещений (склад рядом, лестница,
        # коридор иной t) это часто единственная статья теплопотерь.
        q_partition = _internal_partition_flux(space, project, p, cooling=False)
        if q_partition > 0:
            q_trans += q_partition
            breakdown["Внутр. перегородки"] = q_partition

        breakdown["Через ограждения"] = q_trans

        # Инфильтрация: Q = 0.28 · L · ρ · c · ΔT · k. Расход с учётом баланса
        # мех. вентиляции (приточный воздух греет AHU отдельно) — см.
        # infiltration_flow_m3h. Внутреннее помещение (ограждения есть, но среди
        # них нет наружных) → инфильтрация 0 (make-up перетоком). Если геометрия
        # не задана вовсе — консервативно считаем помещение наружным.
        all_elems = project.elements_for(space.space_id)
        has_ext = (not all_elems) or any(e.net_area_m2 > 0 for e in elems)
        has_donor = _has_supplied_neighbor(space, project)
        L_inf = infiltration_flow_m3h(space, p, has_exterior=has_ext,
                                      has_transfer_donor=has_donor)
        rho = air_density(p.t_out_heating)
        c = 1.005
        q_inf = 0.28 * L_inf * rho * c * dt * p.inf_correction_k
        breakdown["Инфильтрация"] = q_inf

        # Бытовые тепловыделения (СП 50.13330 п. 5.2) — поправка для ГОДОВОГО
        # энергобаланса (см. energy.py). Для КВАРТИР RES из пиковой Q их НЕ
        # вычитаем: приборы, источник и расход теплоносителя подбираются по
        # полным теплопотерям (СП 60 / СНиП 2.04.05 — расчётный случай без
        # бытовых и солнечных поступлений). Для прочих «жилых» (гостиничные
        # HTL и т.п.) сохраняем прежний вычет. RES определяем по номеру —
        # как в data_loader.py:416.
        q_bytovaya = 0.0
        is_res = (space.number or "").upper().startswith("RES")
        if space.room_type == "Жилая комната" and not is_res:
            q_bytovaya = 17.0 * space.area_m2
            breakdown["Бытовые (−)"] = -q_bytovaya

        total = (q_trans + q_inf - q_bytovaya) * p.safety_margin_heating
        breakdown["ИТОГО"] = total
        return breakdown

    # ---------- теплопоступления ----------
    def heat_gain(self, space, project) -> Dict[str, float]:
        """Расчёт теплопоступлений с разделением явная/скрытая.
        Возвращает breakdown с суммарными значениями. Раздельные явные/скрытые
        пишутся в space.heat_gain_breakdown_sensible / _latent."""
        p = project.params
        dt = p.t_out_cooling - space.t_in_cool
        
        # Контейнеры для явной и скрытой
        sensible: Dict[str, float] = {}
        latent: Dict[str, float] = {}

        # CLTD упрощённо: ΔT + 30% от суточной амплитуды
        cltd = dt + p.daily_amplitude * 0.3

        elems = [e for e in project.elements_for(space.space_id) if e.is_exterior]
        # Если в помещении уже есть выгруженное стекло из Revit —
        # WWR-оценка отключается, чтобы не было двойного учёта
        # (реальный витраж + виртуальный WWR).
        has_real_glazing = _room_has_real_glazing(elems, project.constructions)

        q_trans = 0.0
        # Солнце копим раздельно по проектным часам — на каждый час солнце в
        # одной точке неба, поэтому пики разных фасадов не складываются.
        # Пиковая нагрузка = максимум по часам (учёт одновременности).
        solar_by_hour = [0.0] * len(SOLAR_DESIGN_HOURS)
        wwr_applied = False

        # Поворот True North → Project North (если задан)
        tn_offset = getattr(p, "true_north_offset_deg", 0.0)

        def _add_solar(shgc: float, area: float, orient: str) -> None:
            base = shgc * area * p.solar_intensity_w_m2 * p.solar_shading_factor
            factors = SOLAR_HOURLY_FACTOR.get(orient, SOLAR_HOURLY_FACTOR[""])
            for i, f in enumerate(factors):
                solar_by_hour[i] += base * f

        for el in elems:
            if el.u_value <= 0 or el.net_area_m2 <= 0:
                continue
            con = project.constructions.get(el.construction_key)
            is_glazed = con is not None and con.shgc > 0
            # Эффективная ориентация с учётом True North
            eff_orient = effective_orientation(el.orientation,
                                                el.orientation_deg,
                                                tn_offset)

            if is_glazed:
                # Реальное стекло из Revit: всю площадь учитываем как окно
                q_trans += el.u_value * el.net_area_m2 * cltd
                _add_solar(con.shgc, el.net_area_m2, eff_orient)
                continue

            # Сплошная стена. Если WWR>0 и в помещении НЕТ реального стекла —
            # моделируем виртуальное окно. Если стекло уже есть — оставляем
            # стену как стену.
            wall_area, window_area = _wwr_split(el, p, has_real_glazing)
            q_trans += el.u_value * wall_area * cltd
            if window_area > 0:
                q_trans += p.wwr_u_window * window_area * cltd
                _add_solar(p.wwr_shgc, window_area, eff_orient)
                wwr_applied = True

        # Пик по часам с поправкой на аккумуляцию массивом (CLF).
        q_solar = max(solar_by_hour) * SOLAR_CLF

        # Зафиксировать источник остекления для диагностики по этажам:
        # «real» — реальный витраж из Revit, «wwr» — оценка по WWR,
        # «none» — нет ни того, ни другого (внутренняя комната).
        if has_real_glazing:
            space.glazing_source = "real"
        elif wwr_applied:
            space.glazing_source = "wwr"
        else:
            space.glazing_source = "none"

        if space.has_roof or space.is_top_floor:
            q_trans += DEFAULT_U_BY_CATEGORY["Покрытие"] * space.area_m2 * (cltd + 10)

        # Через ограждения — 100% явная
        sensible["Через ограждения"] = q_trans
        latent["Через ограждения"] = 0.0

        # Внутренние перегородки от более ТЁПЛЫХ смежных помещений (напр. склад
        # +28° рядом с офисом +24°) — 100% явная теплота (КМК 2.04.05-91).
        sensible["Внутр. перегородки"] = _internal_partition_flux(
            space, project, p, cooling=True)
        latent["Внутр. перегородки"] = 0.0

        # Солнечная радиация — 100% явная
        sensible["Солнечная радиация"] = q_solar
        latent["Солнечная радиация"] = 0.0

        # Люди: 75 Вт явная + 55 Вт скрытая = 130 Вт/чел (сидячая работа, СП 60)
        sensible["Люди"] = space.occupancy_people * 75.0
        latent["Люди"] = space.occupancy_people * 55.0

        # Освещение — 100% явная
        sensible["Освещение"] = space.area_m2 * space.lighting_w_m2
        latent["Освещение"] = 0.0

        # Оборудование — по таблице ratio для типа помещения
        q_eq_total = space.area_m2 * space.equipment_w_m2
        ratio = EQUIPMENT_SENSIBLE_RATIO.get(space.room_type, 0.85)
        sensible["Оборудование"] = q_eq_total * ratio
        latent["Оборудование"] = q_eq_total * (1.0 - ratio)

        # Инфильтрация / вентиляция
        # Явная: 0.28 · L · ρ · c · ΔT
        # Скрытая: 0.83 · L · Δw (где Δw — разница влагосодержаний г/кг)
        # Расход с учётом баланса мех. вентиляции — см. infiltration_flow_m3h.
        # Внутреннее помещение → инфильтрация 0 (как в heat_loss).
        all_elems = project.elements_for(space.space_id)
        has_ext = (not all_elems) or any(e.net_area_m2 > 0 for e in elems)
        has_donor = _has_supplied_neighbor(space, project)
        L = infiltration_flow_m3h(space, p, has_exterior=has_ext,
                                  has_transfer_donor=has_donor)
        rho = air_density(p.t_out_cooling)
        sensible["Инфильтрация/вентиляция"] = 0.28 * L * rho * 1.005 * dt
        delta_w = p.w_out_summer_g_kg - p.w_in_summer_g_kg
        latent["Инфильтрация/вентиляция"] = _latent_infiltration_w(L, delta_w)

        # Суммы (объединённый breakdown для совместимости — total)
        breakdown: Dict[str, float] = {}
        for key in sensible:
            breakdown[key] = sensible[key] + latent[key]

        # Применяем запас и суммируем
        total_sensible = sum(sensible.values()) * p.safety_margin_cooling
        total_latent = sum(latent.values()) * p.safety_margin_cooling
        total = total_sensible + total_latent

        breakdown["ИТОГО"] = total
        sensible["ИТОГО"] = total_sensible
        latent["ИТОГО"] = total_latent

        # Сохраняем sensible/latent в space (для Excel и отчётов)
        space.heat_gain_sensible_w = total_sensible
        space.heat_gain_latent_w = total_latent
        space.heat_gain_breakdown_sensible = sensible
        space.heat_gain_breakdown_latent = latent

        return breakdown
