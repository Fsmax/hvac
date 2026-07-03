# -*- coding: utf-8 -*-
"""Пояснительная записка по противодымной защите: вывод формул ШНК 2.04.05-22.

Для каждой системы СДУ (дымоудаление) и СПВ (подпор воздуха) формирует
структурированное пояснение:
    формула → исходные данные → подстановка → результат → пункт норматива,
которое затем рендерится в DOCX (см. hvac/io_docx.py, раздел «Дымоудаление»).

Источник методики: ШНК 2.04.05-22 «Иситиш, вентиляция ва кондициялаш»,
Прил. 20 (расход дыма) и §7, пп. 323–341 (подпор воздуха).
"""

from __future__ import annotations
from typing import Dict, List


def _fmt(x: float, nd: int = 0) -> str:
    """Число в «русском» виде: разряды — пробел, дробная часть — запятая."""
    try:
        s = f"{x:,.{nd}f}"
    except (ValueError, TypeError):
        return str(x)
    return s.replace(",", " ").replace(".", ",")


def build_smoke_explanations(project) -> List[Dict]:
    """Возвращает список пояснений по системам противодымной защиты.

    Каждый элемент — dict с ключами: name, kind ('СДУ'/'СПВ'),
    method_title, formula, ref, inputs [(label, value)], substitution,
    results [(label, value)], checks [str].
    """
    from hvac.smoke_formulas import (
        corridor_n_coefficient, kmk_corridor_kg_h, kmk_zone_perimeter_kg_h,
        smoke_density_kg_m3, mass_to_volume_m3h, pressurization_open_door_m3h,
    )

    loads = project.calculate_smoke_loads()
    out: List[Dict] = []

    for name, sm in sorted(project.smoke_systems.items()):
        d = loads.get(name, {})
        m = sm.calc_method

        # ============ СПВ — подпор воздуха ============
        if sm.system_type == "air_supply":
            if m == "kmk_pressurization":
                v, F, n = sm.v_door_m_s, sm.door_area_m2, sm.n_open_doors
                L = pressurization_open_door_m3h(F, v, n)
                out.append({
                    "name": name, "kind": "СПВ",
                    "method_title": "Подпор воздуха по скорости в открытой двери",
                    "formula": "L = 3600 · v · F · n",
                    "ref": "ШНК 2.04.05-22, §7, п. 340 (скорость 1,3 м/с в проёме "
                           "открытой двери при пожаре); п. 341 (давление 20…150 Па).",
                    "inputs": [
                        ("v — нормативная скорость в проёме двери, м/с", _fmt(v, 2)),
                        ("F — площадь проёма (большая створка), м²", _fmt(F, 2)),
                        ("n — число одновременно открытых дверей", str(n)),
                    ],
                    "substitution": (f"L = 3600 · {_fmt(v, 2)} · {_fmt(F, 2)} · {n} = "
                                     f"{_fmt(L)} м³/ч"),
                    "results": [("Расход подпора L, м³/ч", _fmt(L))],
                    "checks": [
                        f"Избыточное давление в защищаемом объёме — не менее "
                        f"{_fmt(sm.pressure_pa, 0)} Па (п. 341).",
                        f"Давление на закрытых дверях путей эвакуации — не более "
                        f"{_fmt(getattr(sm, 'pres_max_pa', 150.0), 0)} Па (п. 341).",
                        "Для двупольной двери принята площадь большей створки (п. 341).",
                    ],
                })
            else:
                L = sm.L_smoke_m3h
                out.append({
                    "name": name, "kind": "СПВ",
                    "method_title": "Подпор воздуха (табличное/принятое значение)",
                    "formula": "L = const (по нормативу/проекту)",
                    "ref": "ШНК 2.04.05-22, §7, пп. 339–341.",
                    "inputs": [("Назначение", str(sm.purpose))],
                    "substitution": f"L = {_fmt(L)} м³/ч (принято)",
                    "results": [("Расход подпора L, м³/ч", _fmt(L))],
                    "checks": [
                        "Рекомендуется уточнить расчётом по скорости в открытой "
                        "двери (метод kmk_pressurization, п. 340).",
                    ],
                })
            continue

        # ============ СДУ — дымоудаление ============
        t = sm.t_smoke_C
        rho = smoke_density_kg_m3(t)
        makeup = d.get("L_makeup_m3h")

        if m == "kmk_corridor":
            B, H = sm.corridor_door_width_m, sm.corridor_door_height_m
            Hc = min(H, 2.5)
            nB = corridor_n_coefficient(B, sm.corridor_public)
            G = kmk_corridor_kg_h(B, H, sm.corridor_public, sm.kd_door)
            L = mass_to_volume_m3h(G, t)
            if sm.corridor_public:
                formula = "G₁ = 4300 · B · n · H^1,5 · Kd"
                subs = (f"G₁ = 4300 · {_fmt(B, 2)} · {_fmt(nB, 2)} · "
                        f"{_fmt(Hc, 2)}^1,5 · {_fmt(sm.kd_door, 2)} = {_fmt(G)} кг/ч")
                ref = "ШНК 2.04.05-22, Прил. 20, ф.(2) — общественные/адм.-быт./произв."
            else:
                formula = "G₁ = 3420 · B · n · H^1,5"
                subs = (f"G₁ = 3420 · {_fmt(B, 2)} · {_fmt(nB, 2)} · "
                        f"{_fmt(Hc, 2)}^1,5 = {_fmt(G)} кг/ч")
                ref = "ШНК 2.04.05-22, Прил. 20, ф.(1) — жилые здания."
            inputs = [
                ("B — ширина большей створки двери, м", _fmt(B, 2)),
                ("n — коэф. по табл. Прил. 20 (от B)", _fmt(nB, 2)),
                ("H — высота двери (при H>2,5 → 2,5), м", _fmt(Hc, 2)),
            ]
            if sm.corridor_public:
                inputs.append(("Kd — коэф. продолж. открывания (1,0/0,8)",
                               _fmt(sm.kd_door, 2)))
            inputs += [
                ("t — расчётная температура дыма, °C", _fmt(t, 0)),
                ("ρ — плотность дыма при t, кг/м³", _fmt(rho, 3)),
            ]
            out.append({
                "name": name, "kind": "СДУ",
                "method_title": "Дымоудаление из коридора/холла",
                "formula": formula, "ref": ref, "inputs": inputs,
                "substitution": (subs + f";  L = G/ρ = {_fmt(G)}/{_fmt(rho, 3)} = "
                                 f"{_fmt(L)} м³/ч"),
                "results": [
                    ("Массовый расход дыма G, кг/ч", _fmt(G)),
                    ("Объёмный расход L (при t дыма), м³/ч", _fmt(L)),
                    ("Компенсирующая подача (≈70%), м³/ч",
                     _fmt(makeup if makeup is not None else L * 0.7)),
                ],
                "checks": [
                    "Один дымоприёмник обслуживает участок коридора ≤ 30 м; "
                    "не более 2 дымоприёмников на этаж на систему (п. 328).",
                    "Уд. вес дыма 6 Н/м³, t = 300 °C (п. 332).",
                    "Расход — на один очаг пожара (одна дымовая зона), п. 326.",
                ],
            })

        elif m == "kmk_zone_perimeter":
            Pf = min(sm.fire_perimeter_m, 12.0)
            y = max(sm.layer_height_m, 2.5)
            G = kmk_zone_perimeter_kg_h(sm.fire_perimeter_m, sm.layer_height_m,
                                        sm.ks_sprinkler)
            L = mass_to_volume_m3h(G, t)
            out.append({
                "name": name, "kind": "СДУ",
                "method_title": "Дымоудаление из помещения (по периметру очага)",
                "formula": "G = 676,8 · Pf · y^1,5 · Ks",
                "ref": "ШНК 2.04.05-22, Прил. 20, ф.(3); периметр — ф.(4): "
                       "Pf = 0,38·√A ≤ 12 м.",
                "inputs": [
                    ("Pf — периметр очага пожара (≤12 м), м", _fmt(Pf, 2)),
                    ("y — высота нижней границы дыма (≥2,5 м), м", _fmt(y, 2)),
                    ("Ks — 1,0 без АУПТ / 1,2 со спринклерами", _fmt(sm.ks_sprinkler, 2)),
                    ("t — расчётная температура дыма, °C", _fmt(t, 0)),
                    ("ρ — плотность дыма при t, кг/м³", _fmt(rho, 3)),
                ],
                "substitution": (f"G = 676,8 · {_fmt(Pf, 2)} · {_fmt(y, 2)}^1,5 · "
                                 f"{_fmt(sm.ks_sprinkler, 2)} = {_fmt(G)} кг/ч;  "
                                 f"L = G/ρ = {_fmt(L)} м³/ч"),
                "results": [
                    ("Массовый расход дыма G, кг/ч", _fmt(G)),
                    ("Объёмный расход L (при t дыма), м³/ч", _fmt(L)),
                    ("Компенсирующая подача (≈70%), м³/ч",
                     _fmt(makeup if makeup is not None else L * 0.7)),
                ],
                "checks": [
                    "Площадь одной дымовой зоны ≤ 1600 м² (п. 330).",
                    "Уд. вес дыма 6 Н/м³, t = 300 °C (п. 332).",
                ],
            })

        else:
            # norm_per_m2 (упрощённо) или иной метод
            A = d.get("served_area_m2", sm.served_area_m2)
            q = sm.norm_per_m2
            L = d.get("L_smoke_m3h", A * q)
            out.append({
                "name": name, "kind": "СДУ",
                "method_title": "Дымоудаление (упрощённо: расход на 1 м²)",
                "formula": "L = A · q",
                "ref": "Инженерная практика (наследие СНиП 2.04.05-91*). Для "
                       "экспертизы уточнить по периметру очага (ф.3, Прил. 20).",
                "inputs": [
                    ("A — обслуживаемая площадь зоны, м²", _fmt(A)),
                    ("q — удельный расход, м³/(ч·м²)", _fmt(q, 1)),
                    ("Число дымовых зон (≤1600 м² каждая)", str(d.get("n_zones", 1))),
                ],
                "substitution": f"L = {_fmt(A)} · {_fmt(q, 1)} = {_fmt(L)} м³/ч (на зону)",
                "results": [
                    ("Расход дыма L, м³/ч", _fmt(L)),
                    ("Компенсирующая подача (≈70%), м³/ч",
                     _fmt(makeup if makeup is not None else L * 0.7)),
                ],
                "checks": [
                    "Площадь одной дымовой зоны ≤ 1600 м² (п. 330).",
                ],
            })

    # Прикрепляем примечание системы (тип лестницы, уровень, допущения по дверям)
    for _e, (_n, _sm) in zip(out, sorted(project.smoke_systems.items())):
        _nt = getattr(_sm, "note", "")
        if _nt:
            _e["note"] = _nt
    return out
