# -*- coding: utf-8 -*-
"""Расчёт вентиляции по ШНҚ 2.08.02-23 (Strategy Pattern).

Возвращает для каждого помещения:
  • supply_m3h          — приток, м³/ч
  • exhaust_m3h         — вытяжка, м³/ч
  • hood_m3h            — зонт (только для кухонь)
  • fresh_air_per_person — норма свежего воздуха, м³/ч·чел
  • ach_calculated      — фактическая кратность (1/час)
  • method              — какой критерий стал решающим
  • warnings            — список предупреждений

Чтобы добавить другую методику (ASHRAE 62.1, КМК) — создайте новый класс
с @register_ventilation_engine и реализуйте calculate().
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Type

from hvac.catalogs.user_norms import get_ventilation_norms


def _pool_moisture_airflow(space, project, a_water: float) -> float:
    """Приток на удаление влаги с зеркала бассейна, м³/ч (СП 31-113).

    Испарение W = A · q_исп, где удельное испарение q [кг/(м²·ч)] зависит
    от t воды (для занятого бассейна ≈0.2 при 28°C). Расход воздуха:
        L = W·1000 / (ρ · Δd),  Δd = d_возд − d_приток [г/кг], ρ≈1.2 кг/м³.
    Влагосодержание воздуха помещения считается по t и расчётной φ.
    """
    from hvac.dew_point import saturation_pressure_pa, _resolve_rh

    t_w = getattr(space, "water_temp_c", 0.0) or 28.0
    # Удельное испарение, кг/(м²·ч): занятый бассейн ≈0.2 при 28°C.
    q_evap = max(0.05, 0.2 + 0.012 * (t_w - 28.0))
    w_kg_h = a_water * q_evap

    # Влагосодержание воздуха помещения (г/кг) по t воздуха и φ.
    t_air = space.t_in_cool if space.t_in_cool > 0 else 28.0
    rh = _resolve_rh(space) / 100.0
    p_v = rh * saturation_pressure_pa(t_air)
    d_room = 622.0 * p_v / (101325.0 - p_v)
    # Влагосодержание приточного (наружного) воздуха — из параметров проекта.
    d_supply = getattr(project.params, "w_out_summer_g_kg", 8.0)
    delta_d = max(d_room - d_supply, 1.0)        # защита от деления на ~0

    return w_kg_h * 1000.0 / (1.2 * delta_d)


class VentilationEngine(ABC):
    """Абстрактный движок расчёта вентиляции."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Отображаемое имя методики."""

    @abstractmethod
    def calculate(self, space, project) -> Dict:
        """Расчёт для одного помещения. Возвращает разбивку."""


# Реестр движков вентиляции (отдельный от теплового!)
_VENT_REGISTRY: Dict[str, Type[VentilationEngine]] = {}


def register_ventilation_engine(cls: Type[VentilationEngine]) -> Type[VentilationEngine]:
    instance = cls()
    _VENT_REGISTRY[instance.name] = cls
    return cls


def get_ventilation_engine(name: str = None) -> VentilationEngine:
    if name and name in _VENT_REGISTRY:
        return _VENT_REGISTRY[name]()
    # дефолтный — первый зарегистрированный
    cls = next(iter(_VENT_REGISTRY.values()))
    return cls()


def list_ventilation_engines() -> List[str]:
    return list(_VENT_REGISTRY.keys())


# ---------- Реализация ШНҚ 2.08.02-23 ----------


@register_ventilation_engine
class ShNK0802VentilationEngine(VentilationEngine):
    """Расчёт вентиляции по ШНҚ 2.08.02-23 «Жамоат бинолари ва иншоотлари»
    (для типов вне ШНҚ — фолбэк на СП 60 / СП 44 / СП 113)."""

    @property
    def name(self) -> str:
        return "ШНҚ 2.08.02-23"

    def calculate(self, space, project) -> Dict:
        # Эффективные нормы: пользовательский override (если есть) + СП-дефолт.
        # Поддерживает и custom-типы помещений.
        norms = get_ventilation_norms(space.room_type)
        result = {
            "supply_m3h": 0.0,
            "exhaust_m3h": 0.0,
            "hood_m3h": 0.0,
            "fresh_air_per_person": norms.get("m3_per_person", 0),
            "ach_calculated": 0.0,
            "method": "",
            "warnings": [],
            "note": norms.get("note", ""),
        }

        # 1. Помещения без вентиляции (лестницы, лифты)
        if norms.get("is_NC"):
            result["method"] = "Не вентилируется (NC)"
            return result

        # 2. Только вытяжка (туалеты)
        if norms.get("exhaust_only"):
            # 2a. Если заданы приборы — считаем по ШНҚ 2.08.02-23 табл.19:
            # 100 м³/ч на унитаз, 50 м³/ч на писсуар (точнее, чем по площади).
            wc = int(getattr(space, "wc_count", 0) or 0)
            urinal = int(getattr(space, "urinal_count", 0) or 0)
            if wc or urinal:
                exh = wc * 100.0 + urinal * 50.0
                result["exhaust_m3h"] = exh
                result["supply_m3h"] = 0.0   # из перетока
                result["method"] = (
                    f"По приборам ({wc}×100 + {urinal}×50 м³/ч)")
                result["ach_calculated"] = (
                    exh / space.volume_m3 if space.volume_m3 else 0)
                return result
            exh = norms.get("exhaust_per_m2", 0) * space.area_m2
            exh = max(exh, norms.get("exhaust_min", 50))
            result["exhaust_m3h"] = exh
            result["supply_m3h"] = 0.0   # из перетока
            result["method"] = f"Только вытяжка: {norms.get('exhaust_per_m2', 0)} м³/ч·м²"
            result["ach_calculated"] = exh / space.volume_m3 if space.volume_m3 else 0
            return result

        # 3. Обычный расчёт: max из 3-4 критериев
        candidates: List[tuple] = []

        # По людям
        m3_pp = norms.get("m3_per_person", 0)
        if m3_pp > 0 and space.occupancy_people > 0:
            L = space.occupancy_people * m3_pp
            candidates.append((L, f"По людям ({space.occupancy_people:.1f} чел × {m3_pp} м³/ч)"))

        # По площади
        m3_m2 = norms.get("m3_per_m2", 0)
        if m3_m2 > 0:
            L = space.area_m2 * m3_m2
            candidates.append((L, f"По площади ({space.area_m2:.1f} м² × {m3_m2} м³/ч·м²)"))

        # По кратности (минимальная)
        min_ach = norms.get("min_ach", 0)
        if min_ach > 0 and space.volume_m3 > 0:
            L = space.volume_m3 * min_ach
            candidates.append((L, f"По кратности (V={space.volume_m3:.1f} м³ × {min_ach} 1/ч)"))

        # По тепловыделениям оборудования (для серверных и техпомещений)
        m3_kw = norms.get("m3_per_kw_equipment", 0)
        if m3_kw > 0:
            q_kw = space.equipment_w_m2 * space.area_m2 / 1000
            if q_kw > 0:
                L = q_kw * m3_kw
                candidates.append((L, f"По тепловыделению ({q_kw:.2f} кВт × {m3_kw} м³/ч·кВт)"))

        # По влагоудалению (бассейны) — если задана площадь зеркала воды
        a_water = getattr(space, "water_surface_m2", 0.0) or 0.0
        if a_water > 0:
            L = _pool_moisture_airflow(space, project, a_water)
            if L > 0:
                candidates.append(
                    (L, f"По влагоудалению ({a_water:.0f} м² зеркала)"))

        if not candidates:
            result["warnings"].append("Нет данных для расчёта")
            return result

        # Берём максимум
        supply, method = max(candidates, key=lambda t: t[0])
        result["supply_m3h"] = supply
        result["method"] = method

        # Дисбаланс: balance<0 — отрицательное давление (exhaust > supply),
        # balance>0 — избыточное (supply > exhaust)
        balance = norms.get("balance", 0.0) / 100.0
        result["exhaust_m3h"] = supply * (1.0 - balance)

        # Зонт кухни — отделяется как часть вытяжки
        if norms.get("has_hood"):
            hood_factor = norms.get("hood_factor", 0.4)
            result["hood_m3h"] = result["exhaust_m3h"] * hood_factor

        # Фактическая кратность
        if space.volume_m3 > 0:
            result["ach_calculated"] = supply / space.volume_m3

        # Предупреждения
        if space.volume_m3 > 0:
            ach = supply / space.volume_m3
            if ach > 10:
                result["warnings"].append(
                    f"Очень высокая кратность {ach:.1f} 1/ч — проверьте расчёт"
                )
            if min_ach > 0 and ach < min_ach * 0.9:
                result["warnings"].append(
                    f"Кратность {ach:.1f} ниже норматива {min_ach}"
                )

        # Парковки: расход нормируется по выбросу CO (динамика въезда/выезда).
        # В модели нет числа машин, поэтому принят упрощённый расчёт по
        # площади — помечаем это предупреждением, чтобы инженер проверил.
        if norms.get("has_co_control"):
            result["warnings"].append(
                "Парковка: проверьте расход по выбросу CO (СП 113 / ШНҚ); "
                "упрощённо принято по площади."
            )

        return result


# Историческое имя — движок раньше назывался по СП 60. Оставляем алиас,
# чтобы не ломать импорты (тесты, внешний код).
SP60VentilationEngine = ShNK0802VentilationEngine
