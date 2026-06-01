# -*- coding: utf-8 -*-
"""HVACProject — главный класс-оркестратор: данные + расчёт + события.

Отвечает за:
- хранение состояния (помещения, ограждения, каталог конструкций, параметры);
- координацию загрузки / расчёта / сохранения;
- публикацию событий для UI (event-bus).

Чистый класс без зависимости от GUI — можно использовать в CLI, в тестах,
в web-API.

Функциональность разбита по миксинам:
- ManualEntryMixin     (hvac/_project_manual_entry.py)  — ручной ввод
- SmokeSystemsMixin    (hvac/_project_smoke.py)         — СДУ / СПВ
- V37ExtensionsMixin   (hvac/_project_extensions.py)    — DHW/energy/ducts/pipes
- ValidationMixin      (hvac/_project_validation.py)    — validate*
"""

from __future__ import annotations
from collections import defaultdict
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from hvac.models import Space, BoundaryElement, Construction, ProjectParameters
from hvac.data_loader import load_spaces, load_thermal
from hvac.catalogs.constructions import (
    build_construction_catalog, construction_key, normalize_category,
)
from hvac.catalogs.room_types import (
    auto_detect_room_type, apply_room_type_defaults,
)
from hvac.engine import get_engine

from hvac._project_manual_entry import ManualEntryMixin
from hvac._project_smoke import SmokeSystemsMixin
from hvac._project_extensions import V37ExtensionsMixin
from hvac._project_validation import ValidationMixin
from hvac._project_zoning import ZoningMixin

# Re-export для обратной совместимости (UI и io_excel импортируют отсюда)
from hvac.sizing_helpers import (  # noqa: F401
    suggest_ahu_size, suggest_boiler_size, suggest_chiller_size,
)

# Только для подсказок типов в аннотациях (избегаем циклических импортов:
# эти модули транзитивно импортируют project.py).
if TYPE_CHECKING:
    from hvac.duct_sizing import DuctNetwork
    from hvac.duct_network import DuctNetworkDetailed
    from hvac.pipe_sizing import PipeNetwork
    from hvac.ahu_process import AHUProcess
    from hvac.heating_hydraulics import HeatingHydraulicsResult
    from hvac.radiator_catalog import RadiatorPick
    from hvac.acoustics import AcousticAnalysis
    from hvac.underfloor import UnderfloorLoop
    from hvac.fancoil_catalog import FancoilPick
    from hvac.vrf import VRFSystem


# Поля Space, которые сохраняются как user override
_OVERRIDABLE_FIELDS = [
    "room_type", "t_in_heat", "t_in_cool", "occupancy_people",
    "lighting_w_m2", "equipment_w_m2", "ach_inf",
    "is_corner", "has_floor_to_ground", "has_roof", "is_top_floor",
    "floor_over_unheated_n",
]


class HVACProject(
    ManualEntryMixin,
    SmokeSystemsMixin,
    V37ExtensionsMixin,
    ValidationMixin,
    ZoningMixin,
):
    """Главный объект проекта."""

    def __init__(self) -> None:
        # Подписчики event-bus не должны сбрасываться вместе с проектом —
        # UI-панели подписываются один раз при старте.
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.params = ProjectParameters()
        self._reset_runtime_state()

    def _reset_runtime_state(self) -> None:
        """Сбрасывает все коллекции расчётных артефактов в пустое состояние.

        Не трогает `params` и `_listeners` — параметры перезаписываются явно
        вызывающим кодом (см. new_empty_project / load), а подписчиков UI
        нельзя терять при пересоздании проекта.

        Эта точка — единственное место, где перечисляются пустые коллекции,
        чтобы добавление нового состояния правилось в одном файле и
        не приводило к рассинхрону между __init__ и new_empty_project.
        """
        # Локальные импорты: модули hvac.equipment/hvac.smoke/hvac.dhw
        # импортируют project.py транзитивно через каталоги, потому держим
        # их внутри метода — избегаем циклов на этапе загрузки модуля.
        from hvac.equipment import (VentilationSystem, HeatingSystem,
                                     CoolingSystem, HeatingCircuit,
                                     CoolingCircuit, DuctZone)
        from hvac.smoke import SmokeSystem
        from hvac.dhw import DHWSystem

        # Базовое состояние (помещения, ограждения, каталог)
        self.spaces: List[Space] = []
        self.elements: List[BoundaryElement] = []
        self.constructions: Dict[str, Construction] = {}
        self.spaces_csv_path: str = ""
        self.thermal_csv_path: str = ""
        self._space_by_id: Dict[str, Space] = {}

        # Индекс {space_id: [elements]} для горячих циклов расчётных движков.
        # Ленивый: пересобирается при первом обращении после инвалидации.
        self._elements_by_space: Dict[str, List[BoundaryElement]] = {}
        self._elements_index_dirty: bool = True

        # Каталоги систем
        self.ventilation_systems: Dict[str, "VentilationSystem"] = {}
        self.heating_systems: Dict[str, "HeatingSystem"] = {}
        self.cooling_systems: Dict[str, "CoolingSystem"] = {}

        # Контуры внутри систем (радиаторы, тёплый пол, фанкойлы, калориферы)
        self.heating_circuits: Dict[str, "HeatingCircuit"] = {}
        self.cooling_circuits: Dict[str, "CoolingCircuit"] = {}
        self.duct_zones: Dict[str, "DuctZone"] = {}

        # Аварийные системы (дымоудаление + подпор воздуха)
        self.smoke_systems: Dict[str, "SmokeSystem"] = {}

        # ===== Расширения v3.7 =====
        self.dhw_systems: Dict[str, "DHWSystem"] = {}
        self.duct_networks: Dict[str, "DuctNetwork"] = {}
        self.pipe_networks: Dict[str, "PipeNetwork"] = {}
        self.cooling_pipe_networks: Dict[str, "PipeNetwork"] = {}
        self.energy_passport = None  # type: Optional["EnergyPassport"]
        self.condensation_results: List = []  # List[CondensationCheck]
        self.ahu_loads: Dict[str, Dict] = {}

        # ===== Расширения v4.1 =====
        self.ahu_processes: Dict[str, Dict[str, "AHUProcess"]] = {}
        self.heating_hydraulics_results: Dict[str, "HeatingHydraulicsResult"] = {}
        self.radiator_picks: Dict[str, "RadiatorPick"] = {}
        self.acoustics_results: Dict[str, "AcousticAnalysis"] = {}
        self.duct_networks_detailed: Dict[str, "DuctNetworkDetailed"] = {}

        # ===== v4.2 =====
        self.underfloor_loops: Dict[str, "UnderfloorLoop"] = {}
        self.fancoil_picks: Dict[str, "FancoilPick"] = {}
        self.vrf_systems: Dict[str, "VRFSystem"] = {}
        self.energy_simulation_result = None  # type: Optional["EnergySimulationResult"]
        self.equipment_specification = None   # type: Optional["Specification"]

    # ---------- Event bus ----------
    def subscribe(self, event: str, callback: Callable) -> None:
        """Подписка на событие проекта (data_loaded, spaces_changed, ...)."""
        self._listeners[event].append(callback)

    def emit(self, event: str, **kwargs) -> None:
        """Уведомить подписчиков о событии."""
        for cb in list(self._listeners.get(event, [])):
            try:
                cb(**kwargs)
            except Exception:
                # UI ошибки не должны крашить движок
                import traceback
                traceback.print_exc()

    # ---------- Доступ к помещениям ----------
    @property
    def space_by_id(self) -> Dict[str, Space]:
        return self._space_by_id

    def get_space(self, space_id: str) -> Optional[Space]:
        return self._space_by_id.get(space_id)

    # ---------- Индекс ограждений по space_id ----------
    def _invalidate_elements_index(self) -> None:
        """Помечает индекс elements_by_space как устаревший. Вызывать
        после любой модификации self.elements (add/remove/replace)."""
        self._elements_index_dirty = True

    def _rebuild_elements_index(self) -> None:
        idx: Dict[str, List[BoundaryElement]] = defaultdict(list)
        for el in self.elements:
            idx[el.space_id].append(el)
        self._elements_by_space = dict(idx)
        self._elements_index_dirty = False

    def elements_for(self, space_id: str) -> List[BoundaryElement]:
        """Возвращает список ограждений помещения через ленивый индекс.

        Заменяет паттерн `[e for e in project.elements if e.space_id == sid]`
        в горячих циклах расчётных движков (sp50, ventilation, ahu_load),
        валидации и расчёта периметра. На проекте 600 помещений × 6000
        ограждений снижает квадратичный скан до линейного.
        """
        if self._elements_index_dirty:
            self._rebuild_elements_index()
        return self._elements_by_space.get(space_id, [])

    # ---------- Загрузка ----------
    def new_empty_project(self, project_name: str = "Новый проект",
                          city: str = "Ташкент") -> None:
        """Сбрасывает проект на пустое состояние для ручного ввода.
        Не зависит от CSV-файлов."""
        self.params = ProjectParameters(project_name=project_name)
        self.params.apply_city(city)
        self._reset_runtime_state()
        self.emit("project_loaded")

    def load(self, spaces_csv: str, thermal_csv: str,
             keep_user_settings: bool = False) -> None:
        """Загружает CSV. При keep_user_settings=True сохраняет пользовательские
        правки для уже знакомых помещений и U-значений конструкций."""
        new_spaces = load_spaces(spaces_csv)
        # Передаём spaces в load_thermal — это позволяет определить
        # «наружные» стены, граничащие только с неотапливаемыми
        # пространствами (балконы, шахты).
        new_elements = load_thermal(thermal_csv, new_spaces)

        old_overrides: Dict[str, Space] = {}
        if keep_user_settings:
            old_overrides = {s.space_id: s for s in self.spaces if s.user_modified}
        old_constr = dict(self.constructions) if keep_user_settings else {}

        self.spaces = new_spaces
        self.elements = self._dedup_openings(new_elements)
        self._invalidate_elements_index()
        self.spaces_csv_path = spaces_csv
        self.thermal_csv_path = thermal_csv
        self._space_by_id = {sp.space_id: sp for sp in self.spaces}
        self.constructions = build_construction_catalog(self.elements)

        # Восстанавливаем U-значения из старого каталога
        for key, con in old_constr.items():
            if key in self.constructions:
                self.constructions[key].u_value = con.u_value
                self.constructions[key].shgc = con.shgc

        # Применяем дефолты или восстанавливаем правки пользователя
        for sp in self.spaces:
            if sp.space_id in old_overrides:
                old = old_overrides[sp.space_id]
                for fld in _OVERRIDABLE_FIELDS:
                    setattr(sp, fld, getattr(old, fld))
                sp.user_modified = True
            else:
                sp.room_type = auto_detect_room_type(sp.name)
                apply_room_type_defaults(sp)

        self._recompute_net_areas()
        self._mark_corner_rooms()
        self._auto_detect_floors_roofs()
        self.emit("data_loaded")

    def _dedup_openings(self, elements):
        """v3.8.2: убирает дубликаты проёмов (окон/дверей), возникавшие в
        выгрузке Revit до фикса в `revit_dynamo_hvac_write_csv.py`.

        Причина: если стена-хозяин разбита границей помещения на несколько
        сегментов, старый скрипт выгружал ВСЕ её инсерты на каждом сегменте.
        Один и тот же физический проём попадал в CSV несколько раз и при
        расчёте теплопоступлений от солнца давал кратное завышение.

        Дедуплицируем по паре (space_id, element_id) для row_type=='opening'.
        Стены (row_type=='external_wall') не трогаем — у непрямоугольных
        комнат это легитимно разные сегменты одной стены."""
        seen = set()
        deduped = []
        dropped = 0
        for el in elements:
            if el.row_type == "opening":
                key = (el.space_id, el.element_id)
                if key in seen:
                    dropped += 1
                    continue
                seen.add(key)
            deduped.append(el)
        if dropped:
            import logging
            logging.getLogger(__name__).warning(
                "Убрано %d дубликатов проёмов из выгрузки Revit "
                "(перевыгрузите CSV новой версией dynamo-скрипта).", dropped)
        return deduped

    def _recompute_net_areas(self) -> None:
        """Вычитает площади проёмов из площадей стен-хозяев."""
        openings_by_host: Dict[str, float] = {}
        for el in self.elements:
            if el.row_type == "opening" and el.is_exterior and el.host_element_id:
                key = f"{el.space_id}|{el.host_element_id}"
                openings_by_host[key] = openings_by_host.get(key, 0.0) + max(
                    el.element_area_m2, el.approx_area_m2
                )
        for el in self.elements:
            if el.row_type == "opening":
                el.net_area_m2 = max(el.element_area_m2, el.approx_area_m2)
            else:
                gross = el.approx_area_m2 if el.approx_area_m2 > 0 else el.element_area_m2
                key = f"{el.space_id}|{el.element_id}"
                opening = openings_by_host.get(key, 0.0)
                el.net_area_m2 = max(gross - opening, 0.0)

    def _mark_corner_rooms(self) -> None:
        """Помечает угловые помещения."""
        for sp in self.spaces:
            if sp.user_modified:
                continue
            ext = [e for e in self.elements
                   if e.space_id == sp.space_id
                   and e.row_type == "external_wall"
                   and e.is_exterior and e.net_area_m2 > 1.0]
            orientations = {e.orientation for e in ext if e.orientation}
            if len(orientations) >= 2:
                sp.is_corner = True
            elif len(ext) >= 2 and not orientations:
                # нет данных об ориентации — старый эвристический критерий
                sp.is_corner = True

    def _auto_detect_floors_roofs(self) -> None:
        """Автоопределение has_floor_to_ground и has_roof по уровням.

        Логика:
        - Помещения на самом нижнем уровне → has_floor_to_ground=True
          (если уровень содержит 'B' или 'basement' или индекс отрицательный)
        - Помещения на самом верхнем уровне → has_roof=True

        Можно переопределить вручную через UI (user_modified=True блокирует).
        """
        if not self.spaces:
            return
        levels = sorted({s.level for s in self.spaces})
        bottom_level = levels[0]
        top_level = levels[-1]

        # Bottom: ищем подвальные уровни. Признаки: B1, B2, Basement, Ground,
        # отрицательный индекс, или просто самый нижний.
        basement_keywords = ("b1", "b2", "b0", "basement", "подвал", "цоколь")
        basement_levels = set()
        for lvl in levels:
            ll = lvl.lower()
            if any(k in ll for k in basement_keywords):
                basement_levels.add(lvl)
        if not basement_levels:
            basement_levels.add(bottom_level)

        for sp in self.spaces:
            if sp.user_modified:
                continue
            # Пол по грунту — для всех помещений подвальных уровней
            if sp.level in basement_levels:
                sp.has_floor_to_ground = True
            # Покрытие — только самый верхний уровень
            if sp.level == top_level:
                sp.has_roof = True
                sp.is_top_floor = True

    # ---------- Каталог конструкций: статистика и обслуживание ----------
    def construction_usage(self) -> Dict[str, Dict[str, float]]:
        """Сколько элементов и какая суммарная площадь используют каждую конструкцию.

        Возвращает {construction_key: {"n_elements": int, "area_m2": float}}.
        Учитывает только наружные ограждения с присвоенным construction_key.
        """
        usage: Dict[str, Dict[str, float]] = {}
        for el in self.elements:
            if not el.is_exterior or not el.construction_key:
                continue
            row = usage.setdefault(el.construction_key,
                                    {"n_elements": 0, "area_m2": 0.0})
            row["n_elements"] += 1
            row["area_m2"] += el.net_area_m2 or 0.0
        return usage

    def remove_unused_constructions(self) -> int:
        """Удаляет из каталога записи, на которые не ссылается ни один элемент,
        а также служебные категории Revit (разделители помещений, колонны).

        Возвращает количество удалённых записей.
        """
        from hvac.data_loader import is_excluded_category
        used = set(self.construction_usage().keys())
        unused = [k for k, c in self.constructions.items()
                  if k not in used or is_excluded_category(c.category)]
        for k in unused:
            del self.constructions[k]
        if unused:
            self.emit("constructions_changed")
        return len(unused)

    def export_constructions_json(self, path: str) -> int:
        """Экспортирует каталог конструкций в отдельный JSON.

        Сохраняет все поля включая слои. Возвращает количество записей.
        """
        import json
        from dataclasses import asdict
        data = {
            "version": "1",
            "constructions": {k: asdict(c) for k, c in self.constructions.items()},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return len(self.constructions)

    def import_constructions_json(self, path: str,
                                  strategy: str = "merge") -> Dict[str, int]:
        """Импортирует каталог конструкций из JSON-файла.

        strategy:
            "replace"   — полная замена текущего каталога;
            "merge"     — добавить только отсутствующие ключи;
            "update_u"  — обновить U и SHGC у совпадающих ключей.

        Возвращает {"added": N, "updated": N, "skipped": N}.
        """
        import json
        from hvac.models import Construction, Layer
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        incoming = data.get("constructions", {})
        if strategy == "replace":
            self.constructions = {}

        added = updated = skipped = 0
        for key, info in incoming.items():
            layers_data = info.get("layers", []) or []
            valid = {k: v for k, v in info.items()
                     if k in Construction.__dataclass_fields__ and k != "layers"}
            new_c = Construction(**valid)
            new_c.layers = [
                Layer(**{kk: vv for kk, vv in (l or {}).items()
                         if kk in Layer.__dataclass_fields__})
                for l in layers_data
            ]
            existing = self.constructions.get(key)
            if existing is None:
                self.constructions[key] = new_c
                added += 1
            elif strategy == "update_u":
                existing.u_value = new_c.u_value
                existing.shgc = new_c.shgc
                if new_c.layers:
                    existing.layers = new_c.layers
                if new_c.note:
                    existing.note = new_c.note
                updated += 1
            else:
                skipped += 1

        self.emit("constructions_changed")
        return {"added": added, "updated": updated, "skipped": skipped}

    # ---------- Применение U-значений ----------
    def apply_constructions(self) -> None:
        """Заполняет u_value у каждого граничного элемента из каталога.

        Самоисцеление: если для элемента нет подходящей записи в каталоге
        (например потому что в исходном CSV не было такой конструкции, или
        normalize_category стал классифицировать иначе после обновления
        правил), запись создаётся на лету с дефолтными U и SHGC. Это
        гарантирует, что НИ ОДИН элемент не пропадёт из расчёта из-за
        отсутствующей конструкции.
        """
        from hvac.catalogs.constructions import (
            DEFAULT_U_BY_CATEGORY, DEFAULT_SHGC,
        )
        n_created = 0
        for el in self.elements:
            if not el.is_exterior:
                continue
            cat = normalize_category(el.category, el.family, el.type_name)
            key = construction_key(cat, el.family, el.type_name, el.thickness_mm)
            con = self.constructions.get(key)
            if con is None:
                con = Construction(
                    key=key,
                    category=cat,
                    family=el.family,
                    type_name=el.type_name,
                    thickness_mm=el.thickness_mm,
                    u_value=DEFAULT_U_BY_CATEGORY.get(cat, 0.5),
                    shgc=DEFAULT_SHGC.get(cat, 0.0),
                )
                self.constructions[key] = con
                n_created += 1
            el.construction_key = key
            el.u_value = con.u_value
        if n_created:
            import logging
            logging.getLogger(__name__).info(
                "apply_constructions: добавлено %d недостающих "
                "записей в каталог", n_created)

    # ---------- Расчёт ----------
    def recalculate(self) -> None:
        """Пересчитывает теплопотери и теплопоступления для всех помещений
        выбранным в params.methodology движком."""
        self.apply_constructions()
        engine = get_engine(self.params.methodology)
        for sp in self.spaces:
            sp.heat_loss_breakdown = engine.heat_loss(sp, self)
            sp.heat_gain_breakdown = engine.heat_gain(sp, self)
            sp.heat_loss_w = sp.heat_loss_breakdown.get("ИТОГО", 0.0)
            sp.heat_gain_w = sp.heat_gain_breakdown.get("ИТОГО", 0.0)
        self.emit("calculation_done")

    def calculate_ventilation(self, engine_name: str = None) -> None:
        """Пересчитывает вентиляцию по СП 60.13330 (или другой методике).
        Помещения с vent_user_modified=True не пересчитываются."""
        from hvac.engine.ventilation import get_ventilation_engine
        engine = get_ventilation_engine(engine_name)
        skipped = 0
        for sp in self.spaces:
            if sp.vent_user_modified:
                skipped += 1
                continue
            br = engine.calculate(sp, self)
            sp.ventilation_breakdown = br
            sp.supply_m3h = br.get("supply_m3h", 0.0)
            sp.exhaust_m3h = br.get("exhaust_m3h", 0.0)
            sp.hood_m3h = br.get("hood_m3h", 0.0)
            sp.ach_calculated = br.get("ach_calculated", 0.0)
        self.emit("ventilation_done", skipped=skipped)

    # ---------- Зоны / системы ----------
    def auto_assign_zones(self, mode: str = "by_prefix",
                          overwrite: bool = False,
                          system: str = "all") -> int:
        """Авто-присвоение зон помещениям + создание систем оборудования
        с дефолтными параметрами для каждой новой зоны.

        mode:
            'by_prefix' — по префиксу номера (B01-001 → "Блок B01")
            'by_level'  — по уровню (B1 (FFL) → "Уровень B1 (FFL)")
            'by_type_family' — по группе типов (Офис, Склад, etc.)
        """
        from hvac.equipment import (VentilationSystem, HeatingSystem,
                                     CoolingSystem)
        count = 0
        for sp in self.spaces:
            if mode == "by_prefix":
                if "-" in sp.number:
                    prefix = sp.number.split("-")[0]
                    zone = f"Блок {prefix}"
                else:
                    zone = f"Уровень {sp.level}"
            elif mode == "by_level":
                zone = f"Уровень {sp.level}"
            elif mode == "by_type_family":
                t = sp.room_type
                if t in ("Офис", "Конференц-зал"):
                    zone = "Офисный блок"
                elif t in ("Гостиничный номер", "Вестибюль"):
                    zone = "Гостиничный блок"
                elif t == "Гараж / автостоянка":
                    zone = "Парковка"
                elif t in ("Технич. помещение", "Серверная"):
                    zone = "Технические"
                elif t == "Санузел":
                    zone = "Санузлы"
                elif t in ("Лестница", "Лифт / шахта"):
                    zone = ""
                else:
                    zone = "Прочие"
            else:
                continue

            if system in ("heating", "all"):
                if overwrite or not sp.system_heating:
                    sp.system_heating = zone
                    count += 1
            if system in ("cooling", "all"):
                if overwrite or not sp.system_cooling:
                    sp.system_cooling = zone
            if system in ("ventilation", "all"):
                if overwrite or not sp.system_ventilation:
                    sp.system_ventilation = zone

        # Создаём системы оборудования с дефолтами для каждой новой зоны
        for sp in self.spaces:
            if sp.system_heating and sp.system_heating not in self.heating_systems:
                self.heating_systems[sp.system_heating] = HeatingSystem(
                    name=sp.system_heating)
            if sp.system_cooling and sp.system_cooling not in self.cooling_systems:
                self.cooling_systems[sp.system_cooling] = CoolingSystem(
                    name=sp.system_cooling)
            if sp.system_ventilation and sp.system_ventilation not in self.ventilation_systems:
                self.ventilation_systems[sp.system_ventilation] = VentilationSystem(
                    name=sp.system_ventilation)

        self.emit("zones_changed")
        return count

    # ---------- Расчёт нагрузок от приточных установок ----------
    def calculate_ahu_loads(self) -> Dict[str, Dict]:
        """Считает нагрузку на калорифер и охладитель каждой приточной установки.

        Делегирует расчёт в hvac.ahu_load (структурированная реализация
        с правильным учётом рекуператора через температуру за ним).

        Возвращает dict {system_name: {...}} (формат совместим со старым
        интерфейсом). Структурированные AHULoad доступны через
        hvac.ahu_load.aggregate_ahus(project).
        """
        from hvac import ahu_load
        ahu_load.aggregate_ahus(self)   # обновляет self.ahu_loads
        self.emit("ahu_loads_calculated")
        return self.ahu_loads

    # ---------- Сводки ----------
    def get_zone_summary(self, system: str = "heating") -> Dict[str, Dict]:
        """Сводка нагрузок по зонам выбранной системы.

        system: 'heating' | 'cooling' | 'ventilation'
        Возвращает {zone_name: {area_m2, n_spaces, q_w, q_sensible_w,
                                q_latent_w, supply_m3h, exhaust_m3h}}.
        """
        attr_map = {
            "heating": "system_heating",
            "cooling": "system_cooling",
            "ventilation": "system_ventilation",
        }
        zone_attr = attr_map.get(system, "system_heating")
        result: Dict[str, Dict] = {}
        for sp in self.spaces:
            zone = getattr(sp, zone_attr, "") or "(не назначено)"
            if zone not in result:
                result[zone] = {
                    "n_spaces": 0, "area_m2": 0.0,
                    "q_heating_w": 0.0, "q_cooling_w": 0.0,
                    "q_sensible_w": 0.0, "q_latent_w": 0.0,
                    "supply_m3h": 0.0, "exhaust_m3h": 0.0,
                    "hood_m3h": 0.0,
                }
            r = result[zone]
            r["n_spaces"] += 1
            r["area_m2"] += sp.area_m2
            r["q_heating_w"] += sp.heat_loss_w
            r["q_cooling_w"] += sp.heat_gain_w
            r["q_sensible_w"] += sp.heat_gain_sensible_w
            r["q_latent_w"] += sp.heat_gain_latent_w
            r["supply_m3h"] += sp.supply_m3h
            r["exhaust_m3h"] += sp.exhaust_m3h
            r["hood_m3h"] += sp.hood_m3h
        return result
