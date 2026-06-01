# -*- coding: utf-8 -*-
"""ZoningMixin — ручное зонирование: системы, контуры и назначение помещений.

Раньше единственным способом наполнить системы оборудования было
авто-присвоение (`auto_assign_zones`). На практике зонирование и
систематизация помещений — ручная инженерная работа: проектировщик сам
решает, какое помещение в какую систему (источник: котёл / чиллер / AHU) и
какой контур (радиаторы / тёплый пол / фанкойлы / зона воздуховодов) входит.

Этот миксин даёт ядру полноценный CRUD для трёх доменов и массовое
назначение помещений, на которое опирается панель «Зоны и системы».
Сам выбор «что куда» делает пользователь — авто-присвоение остаётся лишь
необязательным черновым помощником.

Единая модель домена (`_DOMAINS`) убирает дублирование между отоплением,
холодом и вентиляцией: у каждого свои поля `Space`, свои словари систем и
контуров и свои dataclass'ы из `hvac.equipment`. Вентиляция асимметрична —
её «контур» это `DuctZone` (поле `duct_zone`, родитель `parent_ahu`,
без `circuit_type`), поэтому домен хранит имена полей, а не хардкодит их.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from hvac.equipment import (
    HeatingSystem, CoolingSystem, VentilationSystem,
    HeatingCircuit, CoolingCircuit, DuctZone,
    HEATING_CIRCUIT_TYPES, COOLING_CIRCUIT_TYPES,
    HEATING_CIRCUIT_DEFAULTS, COOLING_CIRCUIT_DEFAULTS,
)


# Поля Space, описывающие зонирование (для снимков undo в UI и io_json).
ZONING_SPACE_FIELDS = (
    "system_heating", "system_cooling", "system_ventilation",
    "circuit_heating", "circuit_cooling", "duct_zone",
)


@dataclass(frozen=True)
class _Domain:
    """Описание одного домена зонирования (отопление / холод / вентиляция)."""
    key: str                       # "heating" | "cooling" | "ventilation"
    space_system: str              # имя поля Space с именем системы
    space_circuit: str             # имя поля Space с именем контура/зоны
    systems_attr: str              # имя атрибута HVACProject со словарём систем
    circuits_attr: str             # имя атрибута со словарём контуров/зон
    system_cls: Type               # dataclass системы
    circuit_cls: Type              # dataclass контура/зоны
    circuit_parent_field: str      # поле контура, ссылающееся на систему
    circuit_types: Optional[List[str]]  # допустимые circuit_type (None у вент.)
    circuit_defaults: Optional[Dict]    # {type: (t_sup, t_ret)} или None


_DOMAINS: Dict[str, _Domain] = {
    "heating": _Domain(
        key="heating",
        space_system="system_heating", space_circuit="circuit_heating",
        systems_attr="heating_systems", circuits_attr="heating_circuits",
        system_cls=HeatingSystem, circuit_cls=HeatingCircuit,
        circuit_parent_field="parent_system",
        circuit_types=HEATING_CIRCUIT_TYPES,
        circuit_defaults=HEATING_CIRCUIT_DEFAULTS,
    ),
    "cooling": _Domain(
        key="cooling",
        space_system="system_cooling", space_circuit="circuit_cooling",
        systems_attr="cooling_systems", circuits_attr="cooling_circuits",
        system_cls=CoolingSystem, circuit_cls=CoolingCircuit,
        circuit_parent_field="parent_system",
        circuit_types=COOLING_CIRCUIT_TYPES,
        circuit_defaults=COOLING_CIRCUIT_DEFAULTS,
    ),
    "ventilation": _Domain(
        key="ventilation",
        space_system="system_ventilation", space_circuit="duct_zone",
        systems_attr="ventilation_systems", circuits_attr="duct_zones",
        system_cls=VentilationSystem, circuit_cls=DuctZone,
        circuit_parent_field="parent_ahu",
        circuit_types=None,
        circuit_defaults=None,
    ),
}

ZONING_DOMAINS = tuple(_DOMAINS.keys())


class ZoningMixin:
    """Ручной CRUD систем/контуров + массовое назначение помещений.

    Все методы работают через домен ("heating"/"cooling"/"ventilation"),
    что исключает три почти одинаковых ветки кода. После любой мутации
    публикуется событие `zones_changed`, и подписанные панели (сводка,
    «Оборудование») обновляются автоматически.
    """

    # ---------- доступ к домену ----------
    @staticmethod
    def zoning_domains() -> tuple:
        return ZONING_DOMAINS

    @staticmethod
    def _domain(domain: str) -> _Domain:
        d = _DOMAINS.get(domain)
        if d is None:
            raise ValueError(f"Unknown zoning domain: {domain!r}")
        return d

    def systems_of(self, domain: str) -> Dict:
        """Словарь {имя: dataclass-системы} выбранного домена."""
        return getattr(self, self._domain(domain).systems_attr)

    def circuits_of(self, domain: str) -> Dict:
        """Словарь {имя: dataclass-контура/зоны} выбранного домена."""
        return getattr(self, self._domain(domain).circuits_attr)

    def circuit_parent(self, domain: str, circuit_name: str) -> str:
        """Имя системы-родителя для контура (или '' если контур не найден)."""
        c = self.circuits_of(domain).get(circuit_name)
        if c is None:
            return ""
        return getattr(c, self._domain(domain).circuit_parent_field, "")

    def circuits_of_system(self, domain: str, system_name: str) -> List[str]:
        """Имена контуров, принадлежащих системе (отсортированы)."""
        pf = self._domain(domain).circuit_parent_field
        return sorted(
            name for name, c in self.circuits_of(domain).items()
            if getattr(c, pf, "") == system_name
        )

    def circuit_types_for(self, domain: str) -> List[str]:
        """Допустимые типы контуров домена ([] для вентиляции)."""
        return list(self._domain(domain).circuit_types or [])

    def zoning_space_fields(self, domain: str) -> tuple:
        """(имя поля системы, имя поля контура) у Space для домена."""
        d = self._domain(domain)
        return d.space_system, d.space_circuit

    # ---------- системы (CRUD) ----------
    def add_zone_system(self, domain: str, name: str, **kwargs) -> str:
        """Создаёт систему домена (если ещё нет). Возвращает её имя.

        Лишние kwargs, не входящие в dataclass, отбрасываются — удобно
        прокидывать форму редактирования без точной фильтрации на стороне UI.
        """
        name = (name or "").strip()
        if not name:
            return ""
        d = self._domain(domain)
        systems = self.systems_of(domain)
        if name not in systems:
            valid = {k: v for k, v in kwargs.items()
                     if k in d.system_cls.__dataclass_fields__ and k != "name"}
            systems[name] = d.system_cls(name=name, **valid)
            self.emit("zones_changed")
        return name

    def rename_zone_system(self, domain: str, old: str, new: str) -> bool:
        """Переименовывает систему и чинит все ссылки (помещения + контуры).

        Возвращает False, если old не найдено, new пустое или уже занято.
        """
        new = (new or "").strip()
        systems = self.systems_of(domain)
        if old not in systems or not new or new in systems:
            return False
        d = self._domain(domain)
        sysobj = systems.pop(old)
        sysobj.name = new
        systems[new] = sysobj
        # помещения, ссылающиеся на старое имя
        for sp in self.spaces:
            if getattr(sp, d.space_system, "") == old:
                setattr(sp, d.space_system, new)
        # контуры, чей родитель — переименованная система
        for c in self.circuits_of(domain).values():
            if getattr(c, d.circuit_parent_field, "") == old:
                setattr(c, d.circuit_parent_field, new)
        self.emit("zones_changed")
        return True

    def remove_zone_system(self, domain: str, name: str) -> bool:
        """Удаляет систему: снимает назначение у помещений и удаляет её контуры.

        Возвращает False, если системы нет.
        """
        d = self._domain(domain)
        systems = self.systems_of(domain)
        if name not in systems:
            return False
        circuits = self.circuits_of(domain)
        # удаляем дочерние контуры и снимаем их с помещений
        child = self.circuits_of_system(domain, name)
        for cname in child:
            circuits.pop(cname, None)
        for sp in self.spaces:
            if getattr(sp, d.space_system, "") == name:
                setattr(sp, d.space_system, "")
            if getattr(sp, d.space_circuit, "") in child:
                setattr(sp, d.space_circuit, "")
        systems.pop(name, None)
        self.emit("zones_changed")
        return True

    # ---------- контуры / зоны (CRUD) ----------
    def add_zone_circuit(self, domain: str, name: str, parent_system: str,
                         circuit_type: str = "", **kwargs) -> str:
        """Создаёт контур (зону) домена. Родительская система создаётся
        автоматически, если её ещё нет. Возвращает имя контура.

        Для отопления/холода применяется температурный график по умолчанию
        для выбранного circuit_type (если t_supply/t_return не заданы явно).
        """
        name = (name or "").strip()
        if not name:
            return ""
        d = self._domain(domain)
        circuits = self.circuits_of(domain)
        if name in circuits:
            return name
        if parent_system:
            self.add_zone_system(domain, parent_system)
        fields = d.circuit_cls.__dataclass_fields__
        valid = {k: v for k, v in kwargs.items()
                 if k in fields and k not in ("name", d.circuit_parent_field)}
        valid[d.circuit_parent_field] = parent_system
        if "circuit_type" in fields and d.circuit_types:
            ctype = circuit_type or d.circuit_types[0]
            valid["circuit_type"] = ctype
            if d.circuit_defaults and ctype in d.circuit_defaults \
                    and "t_supply" not in valid and "t_return" not in valid:
                t_sup, t_ret = d.circuit_defaults[ctype]
                if "t_supply" in fields:
                    valid["t_supply"] = t_sup
                if "t_return" in fields:
                    valid["t_return"] = t_ret
        circuits[name] = d.circuit_cls(name=name, **valid)
        self.emit("zones_changed")
        return name

    def rename_zone_circuit(self, domain: str, old: str, new: str) -> bool:
        """Переименовывает контур и чинит ссылки в помещениях."""
        new = (new or "").strip()
        circuits = self.circuits_of(domain)
        if old not in circuits or not new or new in circuits:
            return False
        d = self._domain(domain)
        c = circuits.pop(old)
        c.name = new
        circuits[new] = c
        for sp in self.spaces:
            if getattr(sp, d.space_circuit, "") == old:
                setattr(sp, d.space_circuit, new)
        self.emit("zones_changed")
        return True

    def remove_zone_circuit(self, domain: str, name: str) -> bool:
        """Удаляет контур: снимает его с помещений (система остаётся)."""
        d = self._domain(domain)
        circuits = self.circuits_of(domain)
        if name not in circuits:
            return False
        for sp in self.spaces:
            if getattr(sp, d.space_circuit, "") == name:
                setattr(sp, d.space_circuit, "")
        circuits.pop(name, None)
        self.emit("zones_changed")
        return True

    # ---------- назначение помещений ----------
    def assign_rooms_to_system(self, domain: str, space_ids,
                               system_name: str) -> int:
        """Назначает помещениям систему домена. Создаёт систему при
        необходимости. Если у помещения был контур ДРУГОЙ системы — он
        снимается (контур не может «висеть» вне своей системы).

        Возвращает число изменённых помещений.
        """
        d = self._domain(domain)
        system_name = (system_name or "").strip()
        if system_name:
            self.add_zone_system(domain, system_name)
        ids = set(space_ids)
        n = 0
        for sp in self.spaces:
            if sp.space_id not in ids:
                continue
            changed = False
            if getattr(sp, d.space_system, "") != system_name:
                setattr(sp, d.space_system, system_name)
                changed = True
            cur_circuit = getattr(sp, d.space_circuit, "")
            if cur_circuit and self.circuit_parent(domain, cur_circuit) != system_name:
                setattr(sp, d.space_circuit, "")
                changed = True
            n += 1 if changed else 0
        if n:
            self.emit("zones_changed")
        return n

    def assign_rooms_to_circuit(self, domain: str, space_ids,
                                circuit_name: str) -> int:
        """Назначает помещениям контур (зону). Система помещения
        синхронизируется с родителем контура. Возвращает число изменённых.
        """
        d = self._domain(domain)
        circuit_name = (circuit_name or "").strip()
        parent = self.circuit_parent(domain, circuit_name) if circuit_name else ""
        ids = set(space_ids)
        n = 0
        for sp in self.spaces:
            if sp.space_id not in ids:
                continue
            changed = False
            if getattr(sp, d.space_circuit, "") != circuit_name:
                setattr(sp, d.space_circuit, circuit_name)
                changed = True
            if circuit_name and getattr(sp, d.space_system, "") != parent:
                setattr(sp, d.space_system, parent)
                changed = True
            n += 1 if changed else 0
        if n:
            self.emit("zones_changed")
        return n

    def clear_rooms_assignment(self, domain: str, space_ids,
                               what: str = "all") -> int:
        """Снимает назначение у помещений.

        what: "system" — только систему (и контур, т.к. он без системы повисает),
              "circuit" — только контур, "all" — и то и другое.
        Возвращает число изменённых помещений.
        """
        d = self._domain(domain)
        ids = set(space_ids)
        n = 0
        for sp in self.spaces:
            if sp.space_id not in ids:
                continue
            changed = False
            if what in ("system", "all"):
                if getattr(sp, d.space_system, ""):
                    setattr(sp, d.space_system, "")
                    changed = True
                if getattr(sp, d.space_circuit, ""):
                    setattr(sp, d.space_circuit, "")
                    changed = True
            elif what == "circuit":
                if getattr(sp, d.space_circuit, ""):
                    setattr(sp, d.space_circuit, "")
                    changed = True
            n += 1 if changed else 0
        if n:
            self.emit("zones_changed")
        return n

    # ---------- снимки для undo ----------
    def snapshot_zoning(self, space_ids) -> Dict[str, Dict[str, str]]:
        """Снимок полей зонирования для набора помещений (для отмены в UI)."""
        ids = set(space_ids)
        snap: Dict[str, Dict[str, str]] = {}
        for sp in self.spaces:
            if sp.space_id in ids:
                snap[sp.space_id] = {f: getattr(sp, f, "")
                                     for f in ZONING_SPACE_FIELDS}
        return snap

    def restore_zoning(self, snapshot: Dict[str, Dict[str, str]]) -> int:
        """Восстанавливает поля зонирования из снимка. Возвращает число строк."""
        n = 0
        for sid, fields in snapshot.items():
            sp = self._space_by_id.get(sid)
            if sp is None:
                continue
            for f, v in fields.items():
                setattr(sp, f, v)
            n += 1
        if n:
            self.emit("zones_changed")
        return n
