# -*- coding: utf-8 -*-
"""Блоки здания: определение, назначение и сводка нагрузок по блокам.

Блок — крупная часть комплекса (башня отеля HTL, жильё RES, офис OFF,
подвалы B1/B2, подиум GFL/MFL, мезонин MZN). Раздел «Блоки» позволяет
разделить проект и работать по каждому блоку отдельно: фильтры в панелях
+ раздельная сводка нагрузок ОТ ПОМЕЩЕНИЙ (радиаторы/фанкойлы) и ОТ
УСТАНОВОК (калориферы/охладители приточек).

Правило определения блока (каноническое, выверено на CHORSU):
префикс НОМЕРА помещения главнее уровня — ресторан отеля на подиуме
(HTL-014 на GFL) принадлежит отелю, трансформаторная B01-093 — подвалу.
Уровень решает для помещений без «фирменного» префикса.

Разделение двухшаговое, по указанию пользователя:
  ШАГ 1 — помещения по блокам (assign_blocks);
  ШАГ 2 — системы по блокам (assign_system_blocks): установка целиком
          принадлежит ОДНОМУ блоку (VentilationSystem.block), вся её
          нагрузка (калорифер/охладитель) относится на этот блок. Блок
          системы определяется по коду имени («П-B1-05» → B1,
          «В-08-HTL-28» → HTL), иначе по преобладающему расходу
          обслуживаемых помещений; правится вручную.
Установка может обслуживать помещения соседних блоков — это показывается
информационно («обслуживает: …»), но нагрузка не дробится.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject

# Порядок вывода блоков в сводках/фильтрах (сверху вниз по зданию).
BLOCKS_ORDER = ["HTL", "RES", "OFF", "MZN", "MFL", "GFL", "B1", "B2"]

# Ключ «блок не определён» в сводках.
NO_BLOCK = ""

# Приоритет токенов в ИМЕНИ системы: башня главнее подвала и подиума
# («П-01-HTL-MFL» — установка отеля на уровне MFL → блок HTL).
_SYS_TOKEN_PRIORITY = ["HTL", "RES", "OFF", "OFC", "MZN", "B1", "B2",
                       "GFL", "MFL"]
_SYS_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])(HTL|RES|OFF|OFC|MZN|B1|B2|GFL|MFL)(?![A-Z0-9])")
# Кириллические двойники латинских букв в кодах систем («В-B1» и «В-В1»).
_CYR2LAT = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")


def _s(x) -> str:
    return str(x).strip() if x is not None else ""


def detect_block(sp) -> str:
    """Определяет блок помещения: сперва префикс номера, затем уровень.

    Возвращает код из BLOCKS_ORDER или "" (не определился).
    """
    lv = _s(getattr(sp, "level", "")).upper()
    n = _s(getattr(sp, "number", "")).upper()
    if "RES" in lv or n.startswith("RES"):
        return "RES"
    if "OFF" in lv or "OFC" in lv or n.startswith(("OFF", "OFC")):
        return "OFF"
    if "HTL" in lv or n.startswith("HTL"):
        return "HTL"
    if "MZN" in lv or n.startswith("MZN"):
        return "MZN"
    if "B1" in lv or n.startswith("B01"):
        return "B1"
    if "B2" in lv or n.startswith("B02"):
        return "B2"
    if "MFL" in lv:
        return "MFL"
    if "GFL" in lv:
        return "GFL"
    return NO_BLOCK


def block_of(sp) -> str:
    """Блок помещения — ТОЛЬКО назначенный (sp.block).

    Автоопределение (detect_block) применяется только явными действиями
    пользователя (кнопки «1./2.», «Переопределить всё»); никакого фолбэка
    «на лету» — иначе удаление/снятие блока молча откатывалось бы."""
    return _s(getattr(sp, "block", ""))


def assign_blocks(project: "HVACProject", overwrite: bool = False) -> int:
    """Заполняет Space.block автоопределением.

    overwrite=False — только пустые (ручные назначения сохраняются),
    overwrite=True — пересчитать всем. Возвращает число изменённых.
    """
    n = 0
    for sp in project.spaces:
        if not overwrite and _s(getattr(sp, "block", "")):
            continue
        b = detect_block(sp)
        if b != _s(getattr(sp, "block", "")):
            sp.block = b
            n += 1
    return n


def blocks_in_project(project: "HVACProject") -> List[str]:
    """Список блоков проекта: канонические, затем реестр (созданные
    пользователем, в т.ч. пустые — project.blocks), затем прочие
    встреченные (по алфавиту)."""
    present = {block_of(sp) for sp in project.spaces}
    for vs in getattr(project, "ventilation_systems", {}).values():
        present.add(_s(getattr(vs, "block", "")))
    present.discard(NO_BLOCK)
    registry = [_s(b) for b in getattr(project, "blocks", []) or [] if _s(b)]
    ordered = [b for b in BLOCKS_ORDER if b in present or b in registry]
    ordered += [b for b in registry
                if b not in ordered]                       # польз. порядок
    ordered += sorted(b for b in present
                      if b not in ordered)
    return ordered


def create_block(project: "HVACProject", name: str) -> bool:
    """Регистрирует блок (может быть пустым). False — уже есть."""
    name = _s(name)
    if not name:
        return False
    registry = getattr(project, "blocks", None)
    if registry is None:
        registry = project.blocks = []
    if name in registry or name in blocks_in_project(project):
        return False
    registry.append(name)
    return True


def rename_block(project: "HVACProject", old: str, new: str) -> Dict[str, int]:
    """Переименовывает блок везде: помещения, системы, реестр.
    Переименование в существующий блок = слияние.
    Возвращает {"rooms": n, "systems": n}."""
    old, new = _s(old), _s(new)
    n_rooms = n_sys = 0
    if not old or not new or old == new:
        return {"rooms": 0, "systems": 0}
    for sp in project.spaces:
        if _s(getattr(sp, "block", "")) == old:
            sp.block = new
            n_rooms += 1
    for coll in (getattr(project, "ventilation_systems", {}) or {},
                 getattr(project, "heating_systems", {}) or {},
                 getattr(project, "cooling_systems", {}) or {}):
        for sysobj in coll.values():
            if _s(getattr(sysobj, "block", "")) == old:
                sysobj.block = new
                n_sys += 1
    registry = getattr(project, "blocks", None) or []
    if old in registry:
        registry[registry.index(old)] = new
    if registry.count(new) > 1:
        registry[:] = [b for i, b in enumerate(registry)
                       if b != new or i == registry.index(new)]
    return {"rooms": n_rooms, "systems": n_sys}


def delete_block(project: "HVACProject", name: str) -> Dict[str, int]:
    """Удаляет блок: снимает его с помещений/систем и из реестра.
    Возвращает {"rooms": n, "systems": n}."""
    stats = rename_block(project, name, "__DEL__")
    # rename в спец-имя, затем очистка — чтобы не дублировать обходы
    for sp in project.spaces:
        if _s(getattr(sp, "block", "")) == "__DEL__":
            sp.block = NO_BLOCK
    for coll in (getattr(project, "ventilation_systems", {}) or {},
                 getattr(project, "heating_systems", {}) or {},
                 getattr(project, "cooling_systems", {}) or {}):
        for sysobj in coll.values():
            if _s(getattr(sysobj, "block", "")) == "__DEL__":
                sysobj.block = NO_BLOCK
    registry = getattr(project, "blocks", None) or []
    registry[:] = [b for b in registry if b not in (name, "__DEL__")]
    return stats


# Порядок уровней здания для сортировки: подвалы вниз, подиум, башня.
_LEVEL_RE = re.compile(r"\bL\s*(\d+)")


def level_sort_key(level: str) -> float:
    """Числовой ключ сортировки уровня: B2=-2, B1=-1, GFL=0, MZN=0.5,
    MFL=1, L02..L28 = 2..28; неизвестное — в конец."""
    lv = _s(level).upper()
    m = _LEVEL_RE.search(lv)
    if m:
        return float(m.group(1))
    if "B2" in lv:
        return -2.0
    if "B1" in lv:
        return -1.0
    if "GFL" in lv:
        return 0.0
    if "MZN" in lv:
        return 0.5
    if "MFL" in lv:
        return 1.0
    return 1e9


def ahu_block_flows(project: "HVACProject") -> Dict[str, Dict[str, Dict[str, float]]]:
    """Расходы каждой вент-системы по блокам.

    Возвращает {system: {block: {"supply": м³/ч, "exhaust": м³/ч}}}.
    Приток помещения идёт системе vent_system_supply, вытяжка+зонт —
    vent_system_exhaust (раздельная привязка учтена).
    """
    out: Dict[str, Dict[str, Dict[str, float]]] = {}

    def bucket(sys_name: str, blk: str) -> Dict[str, float]:
        by_blk = out.setdefault(sys_name, {})
        return by_blk.setdefault(blk, {"supply": 0.0, "exhaust": 0.0})

    for sp in project.spaces:
        blk = block_of(sp)
        s_sys = getattr(sp, "vent_system_supply", "") or _s(getattr(sp, "system_ventilation", ""))
        e_sys = getattr(sp, "vent_system_exhaust", "") or _s(getattr(sp, "system_ventilation", ""))
        if s_sys:
            bucket(s_sys, blk)["supply"] += float(getattr(sp, "supply_m3h", 0.0) or 0.0)
        if e_sys:
            bucket(e_sys, blk)["exhaust"] += (float(getattr(sp, "exhaust_m3h", 0.0) or 0.0)
                                              + float(getattr(sp, "hood_m3h", 0.0) or 0.0))
    return out


def detect_system_block(name: str,
                        flows_by_block: Optional[Dict[str, Dict[str, float]]] = None,
                        known_blocks=None) -> str:
    """Блок системы: по коду имени, затем по преобладающему расходу.

    Токены в имени («П-B1-05» → B1, «ПВ-02-OFF» → OFF); при нескольких
    токенах побеждает башня («П-01-HTL-MFL» → HTL). known_blocks —
    существующие блоки проекта: токен засчитывается, ТОЛЬКО если такой
    блок есть (иначе у пользовательской разбивки HOTEL/APARTMENT токены
    воскрешали бы старые коды). Без токена/совпадения — блок с наибольшим
    расходом (приток+вытяжка) обслуживаемых помещений.
    """
    latin = _s(name).upper().translate(_CYR2LAT)
    found = set(_SYS_TOKEN_RE.findall(latin))
    for tok in _SYS_TOKEN_PRIORITY:
        if tok in found:
            blk = "OFF" if tok == "OFC" else tok
            if known_blocks is None or blk in known_blocks:
                return blk
    if flows_by_block:
        best, best_flow = NO_BLOCK, 0.0
        for blk, f in flows_by_block.items():
            fl = f.get("supply", 0.0) + f.get("exhaust", 0.0)
            if blk and fl > best_flow:
                best, best_flow = blk, fl
        return best
    return NO_BLOCK


def system_block_of(project: "HVACProject", name: str,
                    flows_by_block: Optional[Dict[str, Dict[str, float]]] = None
                    ) -> str:
    """Блок системы — ТОЛЬКО назначенный (VentilationSystem.block).

    detect_system_block вызывается лишь из assign_system_blocks (шаг 2 /
    «Переопределить всё»); фолбэка «на лету» нет — см. block_of."""
    vs = project.ventilation_systems.get(name)
    return _s(getattr(vs, "block", "")) if vs is not None else ""


def assign_system_blocks(project: "HVACProject", overwrite: bool = False) -> int:
    """ШАГ 2: заполняет VentilationSystem.block (и heating/cooling-системам
    по токену имени). overwrite=False — только пустые. Возвращает число
    изменённых систем."""
    flows = ahu_block_flows(project)
    known = set(blocks_in_project(project))
    n = 0
    for name, vs in project.ventilation_systems.items():
        if not overwrite and _s(getattr(vs, "block", "")):
            continue
        b = detect_system_block(name, flows.get(name), known_blocks=known)
        if b != _s(getattr(vs, "block", "")):
            vs.block = b
            n += 1
    for coll in (getattr(project, "heating_systems", {}) or {},
                 getattr(project, "cooling_systems", {}) or {}):
        for name, sysobj in coll.items():
            if not overwrite and _s(getattr(sysobj, "block", "")):
                continue
            b = detect_system_block(name, known_blocks=known)
            if b != _s(getattr(sysobj, "block", "")):
                sysobj.block = b
                n += 1
    return n


def block_summary(project: "HVACProject",
                  ahu_loads: Optional[Dict[str, Dict]] = None) -> Dict[str, Dict]:
    """Сводка нагрузок по блокам: помещения + установки, раздельно.

    Возвращает {block: {
        n_spaces, area_m2,
        q_heat_rooms_w   — Σ теплопотерь помещений блока (только is_heated),
        q_cool_rooms_w   — Σ теплопоступлений (только is_cooled),
        supply_m3h, exhaust_m3h, hood_m3h — расходы помещений блока,
        ahu_q_heater_w   — Σ калориферов установок блока (целиком),
        ahu_q_cooler_w   — Σ охладителей (полная: явная+скрытая),
        q_heat_total_w   — помещения + калориферы,
        q_cool_total_w   — помещения + охладители,
        q_dhw_w          — Σ ГВС блока (пик с циркуляцией) — НЕ входит
                           в q_heat_total_w, показывается отдельно,
        ahus: [{name, supply_m3h, exhaust_m3h, q_heater_w, q_cooler_w,
                serves: [(блок, приток, вытяжка), …], multi_block}],
        sources: [{domain, name, unit_kw, units, total_kw, model}] —
                 подобранные котлы/чиллеры блока (Heating/CoolingSystem),
        dhw: [{name, q_w, v_daily_m3}] — системы ГВС блока,
    }}. Ключ "" = помещения/системы без блока.

    Установка целиком принадлежит своему блоку (VentilationSystem.block,
    иначе автоопределение) — нагрузки НЕ дробятся между блоками; список
    serves показывает, в какие блоки она реально раздаёт воздух.
    ahu_loads — dict как project.ahu_loads (по умолчанию берётся оттуда;
    если он пуст/устарел, вызовите project.calculate_ahu_loads()).
    """
    if ahu_loads is None:
        ahu_loads = getattr(project, "ahu_loads", {}) or {}

    def bucket(blk: str) -> Dict:
        if blk not in out:
            out[blk] = {
                "n_spaces": 0, "area_m2": 0.0,
                "q_heat_rooms_w": 0.0, "q_cool_rooms_w": 0.0,
                "supply_m3h": 0.0, "exhaust_m3h": 0.0, "hood_m3h": 0.0,
                "ahu_q_heater_w": 0.0, "ahu_q_cooler_w": 0.0,
                "q_heat_total_w": 0.0, "q_cool_total_w": 0.0,
                "q_dhw_w": 0.0,
                "ahus": [], "sources": [], "dhw": [],
            }
        return out[blk]

    out: Dict[str, Dict] = {}

    # --- помещения ---
    for sp in project.spaces:
        r = bucket(block_of(sp))
        r["n_spaces"] += 1
        r["area_m2"] += float(getattr(sp, "area_m2", 0.0) or 0.0)
        if getattr(sp, "is_heated", True):
            r["q_heat_rooms_w"] += float(getattr(sp, "heat_loss_w", 0.0) or 0.0)
        if getattr(sp, "is_cooled", True):
            r["q_cool_rooms_w"] += float(getattr(sp, "heat_gain_w", 0.0) or 0.0)
        r["supply_m3h"] += float(getattr(sp, "supply_m3h", 0.0) or 0.0)
        r["exhaust_m3h"] += float(getattr(sp, "exhaust_m3h", 0.0) or 0.0)
        r["hood_m3h"] += float(getattr(sp, "hood_m3h", 0.0) or 0.0)

    # --- установки: каждая целиком в СВОЁМ блоке (ШАГ 2) ---
    flows = ahu_block_flows(project)
    for sys_name in project.ventilation_systems:
        by_blk = flows.get(sys_name, {})
        load = ahu_loads.get(sys_name, {}) or {}
        blk = system_block_of(project, sys_name, by_blk)
        serves = sorted(
            ((b, f["supply"], f["exhaust"]) for b, f in by_blk.items()
             if f["supply"] > 0 or f["exhaust"] > 0),
            key=lambda x: -(x[1] + x[2]))
        q_heater = float(load.get("q_heater_w", 0.0) or 0.0)
        q_cooler = float(load.get("q_cooler_total_w", 0.0) or 0.0)
        r = bucket(blk)
        r["ahu_q_heater_w"] += q_heater
        r["ahu_q_cooler_w"] += q_cooler
        r["ahus"].append({
            "name": sys_name,
            "supply_m3h": float(load.get("supply_m3h", 0.0) or 0.0),
            "exhaust_m3h": float(load.get("exhaust_m3h", 0.0) or 0.0),
            "q_heater_w": q_heater,
            "q_cooler_w": q_cooler,
            "serves": serves,
            "multi_block": len(serves) > 1 or (
                len(serves) == 1 and serves[0][0] != blk),
        })

    # --- подобранные источники блока (котлы / чиллеры) ---
    for domain, systems in (("heating", project.heating_systems),
                            ("cooling", project.cooling_systems)):
        for s in systems.values():
            blk = _s(getattr(s, "block", ""))
            unit_kw = float(getattr(s, "design_capacity_kw", 0.0) or 0.0)
            units = int(getattr(s, "unit_count", 0) or 0)
            bucket(blk)["sources"].append({
                "domain": domain,
                "name": s.name,
                "unit_kw": unit_kw,
                "units": units,
                "total_kw": unit_kw * units,
                "model": getattr(s, "selected_model", "") or "",
            })

    # --- системы ГВС блока (dhw.py, стратегия by_block) ---
    for s in getattr(project, "dhw_systems", {}).values():
        blk = _s(getattr(s, "block", ""))
        q_w = float(getattr(s, "q_with_circulation_w", 0.0) or 0.0)
        r = bucket(blk)
        r["q_dhw_w"] += q_w
        r["dhw"].append({
            "name": s.name,
            "q_w": q_w,
            "v_daily_m3": float(getattr(s, "v_daily_total_m3", 0.0) or 0.0),
        })

    # зарегистрированные, но пока пустые блоки — нулевыми строками
    for b in getattr(project, "blocks", []) or []:
        if _s(b):
            bucket(_s(b))

    for r in out.values():
        r["ahus"].sort(key=lambda a: a["name"])
        r["sources"].sort(key=lambda s: (s["domain"], s["name"]))
        r["dhw"].sort(key=lambda s: s["name"])
        r["q_heat_total_w"] = r["q_heat_rooms_w"] + r["ahu_q_heater_w"]
        r["q_cool_total_w"] = r["q_cool_rooms_w"] + r["ahu_q_cooler_w"]

    # порядок ключей: канонические -> реестр -> прочие -> «(без блока)»
    ordered: Dict[str, Dict] = {}
    for b in blocks_in_project(project):
        if b in out:
            ordered[b] = out[b]
    for b in sorted(k for k in out if k not in ordered and k != NO_BLOCK):
        ordered[b] = out[b]
    if NO_BLOCK in out:
        ordered[NO_BLOCK] = out[NO_BLOCK]
    return ordered
