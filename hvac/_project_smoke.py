# -*- coding: utf-8 -*-
"""SmokeSystemsMixin — управление системами дымоудаления (СДУ)
и подпора воздуха (СПВ), плюс расчёт расходов дыма и компенсации.

См. СП 7.13130.2013 (противодымная защита зданий).
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, List


class SmokeSystemsMixin:
    """Методы работы с системами дымоудаления и подпора воздуха."""

    def auto_assign_smoke_systems(self, overwrite: bool = False) -> Dict[str, int]:
        """Автоматическое присвоение систем дымоудаления и подпора.

        Дефолты (нормы расхода, площадь зоны, давление подпора, классы
        огнестойкости) берутся из активного норматива проекта
        `self.params.smoke_norm`. См. hvac/catalogs/smoke_norms.py.

        Логика:
        • Парковки  → СДУ (norm.parking_closed), деление на дымовые зоны
        • Склады    → СДУ (norm.warehouse_low)
        • Коридоры  → СДУ если длина > 15 м (norm.corridor)
        • Атриумы / большие торговые залы → СДУ
        • Лестницы / лифты → СПВ с подпором воздуха
        • Прочие    → СДУ не требуется

        Возвращает {n_smoke_systems, n_pressurization, n_spaces_assigned}.
        """
        from hvac.smoke import SmokeSystem
        from hvac.catalogs.smoke_norms import get_smoke_norm

        norm = get_smoke_norm(self.params.smoke_norm)
        n_smoke = n_pres = n_assigned = 0

        by_level_type = defaultdict(list)
        for sp in self.spaces:
            by_level_type[(sp.level, sp.room_type)].append(sp)

        # ===== Дымоудаление (СДУ) =====
        smoke_type_map = {
            "Гараж / автостоянка": ("parking_closed", "parking"),
            "Склад":                ("warehouse_low", "warehouse"),
            "Коридор":              ("corridor",      "corridor"),
            "Конференц-зал":        ("office_assembly", "atrium"),
            "Магазин / торговля":   ("trading_hall",  "trading_hall"),
            "Ресторан / кухня":     ("office_assembly", "trading_hall"),
        }
        for (level, room_type), spaces_list in by_level_type.items():
            if room_type not in smoke_type_map:
                continue
            # Только для коридоров: проверяем длину.
            # СП 7.13130.2013 п. 7.2 в): СДУ нужна, если длина коридора > 15 м.
            # √площади занижает длину для узких коридоров (30×2 м ≈ √60 = 7.7),
            # поэтому считаем длину как max(периметр/2 − ширина, max boundary)
            # из элементов ограждений. Если данных ограждений нет — fallback на
            # area / (минимальная типовая ширина 1.4 м).
            if room_type == "Коридор":
                spaces_list = [s for s in spaces_list
                               if self._corridor_length_m(s) > 15.0]
                if not spaces_list:
                    continue

            norm_key, purpose = smoke_type_map[room_type]
            norm_per_m2 = norm.norms_per_m2.get(norm_key, 24.0)
            max_zone = norm.max_zone_area_m2

            total_area = sum(s.area_m2 for s in spaces_list)
            n_zones = max(1, int(-(-total_area // max_zone)))

            level_short = level[:3].replace(" ", "")
            type_short = {"parking": "PRK", "warehouse": "WHS",
                          "corridor": "COR", "atrium": "ATR",
                          "trading_hall": "TRD"}.get(purpose, "GEN")
            sys_name = f"СДУ-{level_short}-{type_short}"

            if sys_name not in self.smoke_systems:
                self.smoke_systems[sys_name] = SmokeSystem(
                    name=sys_name,
                    system_type="smoke_removal",
                    purpose=purpose,
                    calc_method="norm_per_m2",
                    norm_per_m2=norm_per_m2,
                    max_zone_area_m2=max_zone,
                    makeup_ratio=norm.default_makeup_ratio,
                    t_smoke_C=norm.default_t_smoke_C,
                    fire_rating=norm.default_fire_rating,
                    note=f"Авто: {norm.title}; уровень {level}, тип {room_type}",
                )
                n_smoke += 1

            zone_area = 0
            zone_idx = 1
            for sp in spaces_list:
                if not overwrite and sp.smoke_system:
                    continue
                sp.smoke_system = sys_name
                if zone_area + sp.area_m2 > max_zone:
                    zone_idx += 1
                    zone_area = sp.area_m2
                else:
                    zone_area += sp.area_m2
                sp.smoke_zone_index = zone_idx
                n_assigned += 1

        # ===== Подпор воздуха (СПВ) =====
        pressurization_map = {
            "Лестница":     ("stairs",   "stairs"),
            "Лифт / шахта": ("elevator", "elevator"),
        }
        for sp in self.spaces:
            if sp.room_type not in pressurization_map:
                continue
            if not overwrite and sp.pressurization_system:
                continue

            rate_key, purpose = pressurization_map[sp.room_type]
            rate = norm.pressurization_rates_m3h.get(rate_key, 5000.0)

            level_short = sp.level[:3].replace(" ", "")
            sys_name = f"СПВ-{level_short}-{sp.number}"

            if sys_name not in self.smoke_systems:
                self.smoke_systems[sys_name] = SmokeSystem(
                    name=sys_name,
                    system_type="air_supply",
                    purpose=purpose,
                    calc_method=f"{rate_key}_pressure",
                    L_smoke_m3h=rate,   # для СПВ это расход подпора
                    pressure_pa=norm.default_pressure_pa,
                    note=f"Авто: {norm.title}; {sp.room_type}",
                )
                n_pres += 1
            sp.pressurization_system = sys_name
            n_assigned += 1

        self.emit("smoke_systems_changed")
        return {"n_smoke_systems": n_smoke,
                "n_pressurization": n_pres,
                "n_spaces_assigned": n_assigned}

    # ---------- Ручное управление СДУ / СПВ ----------
    def create_smoke_system_manual(self, name: str,
                                    system_type: str = "smoke_removal",
                                    purpose: str = "parking",
                                    calc_method: str = "norm_per_m2",
                                    fire_rating: str = "F400-120",
                                    note: str = "",
                                    **extra) -> "SmokeSystem":
        """Создаёт систему СДУ или СПВ вручную (без авто-присвоения).

        Имя должно быть уникальным. Помещения к системе не привязываются —
        это делается отдельным вызовом assign_spaces_to_smoke_system().

        Параметр system_type:
            'smoke_removal' — вытяжная СДУ
            'air_supply'    — приточная СПВ (подпор)

        Дополнительные именованные параметры (через **extra) пробрасываются
        в SmokeSystem: norm_per_m2, max_zone_area_m2, pressure_pa, t_smoke_C,
        makeup_ratio, L_smoke_m3h, а также плюм-параметры (fire_perimeter_m,
        layer_height_m, ks_sprinkler, n_corridor, kd_door, hrr_kw,
        convective_fraction, plume_height_m). Неизвестные поля молча
        отбрасываются.

        Поднимает ValueError если имя занято.
        """
        from hvac.smoke import SmokeSystem
        name = (name or "").strip()
        if not name:
            raise ValueError("Имя системы не может быть пустым")
        if name in self.smoke_systems:
            raise ValueError(f"Система с именем '{name}' уже существует")
        if system_type not in ("smoke_removal", "air_supply", "compensation"):
            raise ValueError(
                f"Неизвестный тип системы: {system_type!r}. "
                f"Допустимо: smoke_removal, air_supply, compensation")

        # Отбрасываем лишние kwargs, оставляем только поля SmokeSystem
        valid_fields = set(SmokeSystem.__dataclass_fields__.keys())
        clean_extra = {k: v for k, v in extra.items() if k in valid_fields}

        sm = SmokeSystem(
            name=name, system_type=system_type, purpose=purpose,
            calc_method=calc_method, fire_rating=fire_rating,
            note=note or "Создано вручную",
            **clean_extra,
        )
        self.smoke_systems[name] = sm
        self.emit("smoke_systems_changed")
        return sm

    def delete_smoke_system(self, name: str) -> int:
        """Удаляет систему дымоудаления/подпора и снимает её со всех
        помещений. Возвращает число отвязанных помещений."""
        if name not in self.smoke_systems:
            return 0
        n = 0
        for sp in self.spaces:
            if sp.smoke_system == name:
                sp.smoke_system = ""
                sp.smoke_zone_index = 0
                n += 1
            if sp.pressurization_system == name:
                sp.pressurization_system = ""
                n += 1
        del self.smoke_systems[name]
        self.emit("smoke_systems_changed")
        return n

    def assign_spaces_to_smoke_system(self,
                                       space_ids: List[str],
                                       system_name: str) -> int:
        """Назначает указанные помещения системе СДУ или СПВ.

        Тип назначения (smoke_system или pressurization_system) определяется
        автоматически по system_type существующей системы.
        """
        sm = self.smoke_systems.get(system_name)
        if sm is None:
            raise ValueError(f"Система '{system_name}' не найдена")
        n = 0
        is_pres = (sm.system_type == "air_supply")
        for sid in space_ids:
            sp = self._space_by_id.get(sid)
            if sp is None:
                continue
            if is_pres:
                sp.pressurization_system = system_name
            else:
                sp.smoke_system = system_name
            n += 1
        self.emit("smoke_systems_changed")
        return n

    def clear_smoke_assignment(self, space_ids: List[str],
                                kind: str = "smoke") -> int:
        """Снимает у помещений привязку к СДУ ('smoke') или СПВ
        ('pressurization'). Возвращает число затронутых помещений."""
        if kind not in ("smoke", "pressurization"):
            raise ValueError(
                f"kind должен быть 'smoke' или 'pressurization', "
                f"получено {kind!r}")
        n = 0
        for sid in space_ids:
            sp = self._space_by_id.get(sid)
            if sp is None:
                continue
            if kind == "smoke" and sp.smoke_system:
                sp.smoke_system = ""
                sp.smoke_zone_index = 0
                n += 1
            elif kind == "pressurization" and sp.pressurization_system:
                sp.pressurization_system = ""
                n += 1
        if n:
            self.emit("smoke_systems_changed")
        return n

    def set_smoke_zone_index(self, space_ids: List[str], idx: int) -> int:
        """Устанавливает номер дымовой зоны (smoke_zone_index) для
        выделенных помещений."""
        if idx < 0:
            raise ValueError("Номер дымовой зоны не может быть < 0")
        n = 0
        for sid in space_ids:
            sp = self._space_by_id.get(sid)
            if sp is None:
                continue
            sp.smoke_zone_index = idx
            n += 1
        if n:
            self.emit("smoke_systems_changed")
        return n

    def calculate_smoke_loads(self, fire_mode: str = "single_zone") -> Dict[str, Dict]:
        """Рассчитывает расходы дыма и подпора для каждой аварийной системы.

        fire_mode:
            'single_zone'    — один пожар в одной зоне (стандарт). Расход
                                СДУ = расход одной дымовой зоны (макс).
            'multiple_zones' — несколько одновременно (запас). Расход СДУ
                                = сумма по всем зонам.

        Возвращает {system_name: {L_smoke, L_makeup, n_zones, ...}}.
        """
        result: Dict[str, Dict] = {}

        spaces_by_system = defaultdict(list)
        for sp in self.spaces:
            if sp.smoke_system:
                spaces_by_system[sp.smoke_system].append(sp)

        for sys_name, sm in self.smoke_systems.items():
            spaces_list = spaces_by_system.get(sys_name, [])
            total_area = sum(s.area_m2 for s in spaces_list)
            n_spaces = len(spaces_list)

            # СПВ — расход уже задан
            if sm.system_type == "air_supply":
                result[sys_name] = {
                    "system_type": sm.system_type,
                    "purpose": sm.purpose,
                    "n_spaces": n_spaces,
                    "served_area_m2": total_area,
                    "n_zones": 1,
                    "L_smoke_m3h": sm.L_smoke_m3h,
                    "L_per_zone_m3h": sm.L_smoke_m3h,
                    "L_makeup_m3h": 0.0,
                    "t_smoke_C": 20.0,
                    "fire_rating": "—",
                    "pressure_pa": sm.pressure_pa,
                    "note": sm.note,
                }
                continue

            # СДУ — расчёт по выбранному методу через универсальный диспетчер
            from hvac.smoke_formulas import calc_smoke_flow_m3h

            plume_methods = ("kmk_zone_perimeter", "kmk_corridor",
                             "nfpa_plume_axi")
            if sm.calc_method == "manual":
                L_per_zone = sm.L_smoke_m3h
                n_zones = max(sm.n_zones, 1)
            elif sm.calc_method in plume_methods:
                # Формулы плюм-теории дают расход для ОДНОГО очага пожара
                # (расчётный сценарий). Деление помещений на зоны учитывается
                # только при компоновке СДУ (один клапан на зону), но не
                # суммирует расход. См. СП 7.13130.2013 п. 7.4, КМК Прил. 20.
                n_zones = max(1, int(-(-total_area // sm.max_zone_area_m2)))
                L_per_zone = calc_smoke_flow_m3h(sm, area_m2=0.0)
            else:
                # norm_per_m2 (упрощённо)
                n_zones = max(1, int(-(-total_area // sm.max_zone_area_m2)))
                area_per_zone = total_area / n_zones if n_zones > 0 else 0
                L_per_zone = calc_smoke_flow_m3h(sm, area_m2=area_per_zone)

            if fire_mode == "multiple_zones" and sm.calc_method not in plume_methods:
                # Запас «несколько зон одновременно» применим только к
                # упрощённому методу. Для плюм-теории это означало бы
                # одновременный пожар в нескольких очагах, что выходит за
                # рамки нормативного сценария.
                L_total = L_per_zone * n_zones
            else:
                L_total = L_per_zone   # один пожар в одной зоне

            L_makeup = L_total * sm.makeup_ratio

            sm.L_smoke_m3h = L_total
            sm.L_per_zone_m3h = L_per_zone
            sm.L_makeup_m3h = L_makeup
            sm.served_area_m2 = total_area
            sm.n_zones = n_zones

            result[sys_name] = {
                "system_type": sm.system_type,
                "purpose": sm.purpose,
                "n_spaces": n_spaces,
                "served_area_m2": total_area,
                "n_zones": n_zones,
                "L_smoke_m3h": L_total,
                "L_per_zone_m3h": L_per_zone,
                "L_makeup_m3h": L_makeup,
                "t_smoke_C": sm.t_smoke_C,
                "fire_rating": sm.fire_rating,
                "pressure_pa": sm.pressure_pa,
                "norm_per_m2": sm.norm_per_m2,
                "calc_method": sm.calc_method,
                "note": sm.note,
            }

        self.emit("smoke_loads_calculated")
        return result

    # ---------- Смена активного норматива ----------
    def apply_smoke_norm(self, code: str,
                          update_existing: bool = True,
                          only_auto: bool = True) -> Dict[str, int]:
        """Меняет активный норматив противодымной защиты проекта и
        (по запросу) переприменяет дефолты к уже созданным системам.

        Параметры
        ---------
        code            : код норматива ("SP7_RU", "KMK_UZ", "NFPA_92", "CUSTOM")
        update_existing : пересчитать ли параметры уже существующих систем
        only_auto       : True — обновлять только авто-созданные системы
                          (note начинается с 'Авто:'). Ручные не трогаем.

        Возвращает {n_updated_smoke, n_updated_pres, n_recalc_method}.

        n_recalc_method — сколько систем получило новый calc_method, потому
        что старый отсутствует в available_calc_methods нового норматива.
        """
        from hvac.catalogs.smoke_norms import SMOKE_NORMS, get_smoke_norm
        if code not in SMOKE_NORMS:
            raise ValueError(
                f"Неизвестный норматив {code!r}. "
                f"Допустимо: {list(SMOKE_NORMS.keys())}"
            )
        self.params.smoke_norm = code
        if not update_existing:
            self.emit("smoke_systems_changed")
            return {"n_updated_smoke": 0, "n_updated_pres": 0,
                    "n_recalc_method": 0}

        norm = get_smoke_norm(code)
        # Обратное отображение purpose → ключ в norms_per_m2 / pressurization
        smoke_key_by_purpose = {
            "parking":      "parking_closed",
            "warehouse":    "warehouse_low",
            "corridor":     "corridor",
            "atrium":       "office_assembly",
            "trading_hall": "trading_hall",
        }
        pres_key_by_purpose = {
            "stairs":    "stairs",
            "elevator":  "elevator",
            "vestibule": "vestibule",
            "refuge":    "refuge",
        }
        n_smoke = n_pres = n_method = 0
        available = set(norm.available_calc_methods)
        for sm in self.smoke_systems.values():
            if only_auto and not (sm.note or "").startswith("Авто:"):
                continue
            if sm.system_type == "air_supply":
                key = pres_key_by_purpose.get(sm.purpose)
                rate = norm.pressurization_rates_m3h.get(key)
                if rate is not None:
                    sm.L_smoke_m3h = rate
                sm.pressure_pa = norm.default_pressure_pa
                n_pres += 1
                continue
            # smoke_removal
            key = smoke_key_by_purpose.get(sm.purpose)
            if key is not None:
                sm.norm_per_m2 = norm.norms_per_m2.get(key, sm.norm_per_m2)
            sm.max_zone_area_m2 = norm.max_zone_area_m2
            sm.makeup_ratio = norm.default_makeup_ratio
            sm.t_smoke_C = norm.default_t_smoke_C
            sm.fire_rating = norm.default_fire_rating
            # Если текущий метод недоступен в новом нормативе —
            # переключаем на рекомендованный.
            if sm.calc_method not in available:
                sm.calc_method = norm.calc_method_recommended
                n_method += 1
            n_smoke += 1
        self.emit("smoke_systems_changed")
        return {"n_updated_smoke": n_smoke,
                "n_updated_pres": n_pres,
                "n_recalc_method": n_method}

    # ---------- Вспомогательные ----------
    def _corridor_length_m(self, space) -> float:
        """Оценка фактической длины коридора, м.

        Длинная сторона коридора нужна для применения СП 7.13130.2013 п. 7.2 в)
        («коридоры > 15 м»). √площади занижает длину для узких помещений.

        Приоритет:
        1. Максимальная boundary_length_m среди наружных стен/перегородок
           из выгрузки Revit (длинная сторона прямоугольника).
        2. Если ограждений нет — оценка через типовую ширину 1.6 м:
           L ≈ A / 1.6.
        """
        boundaries = [
            el.boundary_length_m for el in self.elements_for(space.space_id)
            if el.boundary_length_m > 0
        ]
        if boundaries:
            return max(boundaries)
        # Fallback: типовой коридор шириной 1.6 м
        return space.area_m2 / 1.6 if space.area_m2 > 0 else 0.0
