# -*- coding: utf-8 -*-
"""ManualEntryMixin — ручной ввод помещений и ограждений (v3.8).

Используется когда проект собирается без CSV из Revit: пользователь
сам добавляет Space и BoundaryElement через UI.
"""

from __future__ import annotations
from typing import List, Optional

from hvac.models import Space, BoundaryElement, Construction
from hvac.catalogs.constructions import construction_key, normalize_category
from hvac.catalogs.room_types import apply_room_type_defaults


_ORIENT_DEG_MAP = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}


class ManualEntryMixin:
    """Методы ручного создания/удаления/редактирования помещений и ограждений."""

    # ---------- Помещения ----------
    def add_space(self, number: str, name: str, level: str,
                  area_m2: float, height_m: float = 3.0,
                  room_type: str = "Прочее",
                  volume_m3: Optional[float] = None,
                  space_id: Optional[str] = None) -> Space:
        """Создаёт новое помещение и добавляет в проект.

        Используется для ручного ввода (без Revit).
        Если space_id не задан — генерируется автоматически.
        Возвращает созданный объект Space.
        """
        if space_id is None:
            # Простой автоинкремент: M-001, M-002, ... (M = manual)
            existing = [s.space_id for s in self.spaces]
            i = 1
            while f"M-{i:04d}" in existing:
                i += 1
            space_id = f"M-{i:04d}"
        elif space_id in self._space_by_id:
            raise ValueError(f"space_id '{space_id}' уже существует")

        if volume_m3 is None:
            volume_m3 = area_m2 * height_m

        sp = Space(
            space_id=space_id,
            number=number,
            name=name,
            level=level,
            area_m2=area_m2,
            volume_m3=volume_m3,
            height_m=height_m,
            room_type=room_type,
            manual_entry=True,
            user_modified=True,
        )
        # Применяем типовые параметры по типу помещения
        apply_room_type_defaults(sp)
        sp.user_modified = True   # apply_room_type_defaults снимает флаг
        sp.manual_entry = True

        self.spaces.append(sp)
        self._space_by_id[space_id] = sp
        self.emit("spaces_changed")
        return sp

    def remove_space(self, space_id: str) -> bool:
        """Удаляет помещение и ВСЕ его ограждения. Возвращает True если удалено."""
        sp = self._space_by_id.pop(space_id, None)
        if sp is None:
            return False
        self.spaces = [s for s in self.spaces if s.space_id != space_id]
        self.elements = [e for e in self.elements if e.space_id != space_id]
        self._invalidate_elements_index()
        self.emit("spaces_changed")
        return True

    def update_space(self, space_id: str, **fields) -> bool:
        """Изменяет произвольные поля помещения. Помечает user_modified=True."""
        sp = self._space_by_id.get(space_id)
        if sp is None:
            return False
        for k, v in fields.items():
            if hasattr(sp, k):
                setattr(sp, k, v)
        sp.user_modified = True
        # Если изменились area_m2 или height_m — пересчитываем volume_m3
        if "area_m2" in fields or "height_m" in fields:
            if sp.height_m > 0 and sp.area_m2 > 0 and "volume_m3" not in fields:
                sp.volume_m3 = sp.area_m2 * sp.height_m
        self.emit("spaces_changed")
        return True

    # ---------- Ограждения ----------
    def add_element(self, space_id: str, row_type: str, category: str,
                    family: str, type_name: str,
                    area_m2: float,
                    is_exterior: bool = True,
                    orientation: str = "",
                    thickness_mm: float = 0.0,
                    u_value: float = 0.0,
                    shgc: float = 0.6,
                    element_id: Optional[str] = None,
                    host_element_id: str = "",
                    boundary_length_m: float = 0.0) -> BoundaryElement:
        """Создаёт новый граничный элемент (стена / окно / дверь) вручную.

        row_type: "external_wall" (для стен, перекрытий, покрытий) или "opening"
                  (для окон, витражей, дверей).
        Возвращает созданный BoundaryElement.
        """
        if space_id not in self._space_by_id:
            raise ValueError(f"Помещение '{space_id}' не найдено")

        if element_id is None:
            existing = {e.element_id for e in self.elements}
            i = 1
            while f"E-{space_id}-{i:03d}" in existing:
                i += 1
            element_id = f"E-{space_id}-{i:03d}"

        orient_deg = _ORIENT_DEG_MAP.get(orientation, None)

        sp = self._space_by_id[space_id]
        height = sp.height_m if sp.height_m > 0 else 3.0

        elem = BoundaryElement(
            space_id=space_id,
            row_type=row_type,
            is_exterior=is_exterior,
            element_id=element_id,
            category=category,
            family=family,
            type_name=type_name,
            boundary_length_m=boundary_length_m or (area_m2 / height if height else 0),
            space_height_m=height,
            approx_area_m2=area_m2,
            element_area_m2=area_m2,
            thickness_mm=thickness_mm,
            function="Exterior" if is_exterior else "Interior",
            host_element_id=host_element_id,
            boundary_space_count=1,
            orientation_deg=orient_deg,
            orientation=orientation,
            u_value=u_value,
            net_area_m2=area_m2,
            manual_entry=True,
        )
        self.elements.append(elem)
        self._invalidate_elements_index()

        # Обновляем каталог конструкций (если новая конструкция)
        cat = normalize_category(category, family, type_name)
        key = construction_key(cat, family, type_name, thickness_mm)
        elem.construction_key = key
        if key not in self.constructions:
            self.constructions[key] = Construction(
                key=key, category=cat, family=family, type_name=type_name,
                thickness_mm=thickness_mm, u_value=u_value, shgc=shgc,
            )
        else:
            if u_value > 0:
                self.constructions[key].u_value = u_value
            if shgc > 0 and cat in ("Окна", "Витраж"):
                self.constructions[key].shgc = shgc

        self._recompute_net_areas()
        self.emit("elements_changed")
        return elem

    def remove_element(self, element_id: str) -> bool:
        """Удаляет граничный элемент по его element_id."""
        before = len(self.elements)
        self.elements = [e for e in self.elements if e.element_id != element_id]
        if len(self.elements) == before:
            return False
        self._invalidate_elements_index()
        self._recompute_net_areas()
        self.emit("elements_changed")
        return True

    def update_element(self, element_id: str, **fields) -> bool:
        """Изменяет поля граничного элемента."""
        for e in self.elements:
            if e.element_id == element_id:
                for k, v in fields.items():
                    if hasattr(e, k):
                        setattr(e, k, v)
                if "orientation" in fields:
                    e.orientation_deg = _ORIENT_DEG_MAP.get(
                        e.orientation, e.orientation_deg)
                if "approx_area_m2" in fields or "element_area_m2" in fields:
                    self._recompute_net_areas()
                # Изменение space_id ломает индекс
                if "space_id" in fields:
                    self._invalidate_elements_index()
                self.emit("elements_changed")
                return True
        return False

    def get_room_elements(self, space_id: str) -> list:
        """Возвращает все граничные элементы помещения."""
        return list(self.elements_for(space_id))

    def duplicate_space(self, space_id: str,
                        new_number: Optional[str] = None) -> Optional[Space]:
        """Создаёт копию помещения вместе с его ограждениями.
        Возвращает новое помещение или None если исходное не найдено."""
        from copy import deepcopy
        src = self._space_by_id.get(space_id)
        if src is None:
            return None
        new_sp = deepcopy(src)
        # сгенерировать уникальный space_id
        existing = {s.space_id for s in self.spaces}
        i = 1
        while f"{src.space_id}-copy{i}" in existing:
            i += 1
        new_sp.space_id = f"{src.space_id}-copy{i}"
        if new_number is not None:
            new_sp.number = new_number
        else:
            new_sp.number = f"{src.number} (копия)"
        new_sp.user_modified = True
        new_sp.manual_entry = True
        # Копии не несут результаты расчёта от оригинала
        new_sp.heat_loss_w = 0.0
        new_sp.heat_gain_w = 0.0
        new_sp.heat_loss_breakdown = {}
        new_sp.heat_gain_breakdown = {}
        self.spaces.append(new_sp)
        self._space_by_id[new_sp.space_id] = new_sp

        # Скопировать ограждения
        for el in [e for e in self.elements if e.space_id == space_id]:
            new_el = deepcopy(el)
            new_el.space_id = new_sp.space_id
            existing_eids = {e.element_id for e in self.elements}
            j = 1
            while f"{el.element_id}-c{j}" in existing_eids:
                j += 1
            new_el.element_id = f"{el.element_id}-c{j}"
            new_el.manual_entry = True
            self.elements.append(new_el)

        self._invalidate_elements_index()
        self.emit("spaces_changed")
        return new_sp

    # ---------- Массовое создание по шаблону ----------
    def add_spaces_from_template(self, template) -> List[Space]:
        """Создаёт помещения по шаблону «N этажей × M квартир × K комнат».

        template — объект с полями:
            n_floors: int
            first_floor_number: int
            apartments_per_floor: int
            rooms_per_apartment: list[(name, room_type, area_m2)] (объекты
                с этими атрибутами)
            height_m: float
            level_prefix: str

        Возвращает список созданных помещений.
        """
        created: List[Space] = []
        for floor_offset in range(template.n_floors):
            floor_num = template.first_floor_number + floor_offset
            level_name = f"{template.level_prefix}{floor_num}"
            for apt_idx in range(1, template.apartments_per_floor + 1):
                for room in template.rooms_per_apartment:
                    number = f"{floor_num:02d}-{apt_idx:02d}-{room.name[:3]}"
                    name = f"кв.{apt_idx} · {room.name}"
                    sp = self.add_space(
                        number=number,
                        name=name,
                        level=level_name,
                        area_m2=room.area_m2,
                        height_m=template.height_m,
                        room_type=room.room_type,
                    )
                    created.append(sp)
        return created

    # ---------- Импорт из табличного файла ----------
    def import_spaces_from_excel(self, path: str,
                                 sheet: Optional[str] = None) -> int:
        """Импорт списка помещений из Excel.

        Ожидаемые колонки (заголовки регистронезависимые, синонимы поддерживаются):
            №, номер, number       — номер помещения
            имя, название, name    — название
            этаж, level, floor     — этаж
            тип, type              — тип (по справочнику)
            площадь, area, s, м²   — площадь, м²
            высота, height, h      — высота, м (опционально)

        Возвращает количество успешно добавленных строк.
        """
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise RuntimeError("Для импорта из Excel нужен openpyxl") from e
        wb = load_workbook(path, data_only=True)
        ws = wb[sheet] if sheet else wb.active
        rows = ws.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            return 0
        mapping = _resolve_header_mapping(headers)
        if "number" not in mapping or "area" not in mapping:
            raise ValueError(
                "В таблице должны быть колонки с номером и площадью.")
        n = self._import_rows(rows, mapping)
        self.emit("spaces_changed")
        return n

    def import_spaces_from_csv(self, path: str,
                               delimiter: Optional[str] = None) -> int:
        """Аналог import_spaces_from_excel но для CSV."""
        import csv
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            if delimiter is None:
                try:
                    dialect = csv.Sniffer().sniff(sample,
                                                  delimiters=",;\t|")
                    delimiter = dialect.delimiter
                except csv.Error:
                    delimiter = ","
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, None)
            if not headers:
                return 0
            mapping = _resolve_header_mapping(headers)
            if "number" not in mapping or "area" not in mapping:
                raise ValueError(
                    "В таблице должны быть колонки с номером и площадью.")
            n = self._import_rows(reader, mapping)
        self.emit("spaces_changed")
        return n

    def _import_rows(self, rows, mapping: dict) -> int:
        n = 0
        for row in rows:
            if row is None:
                continue
            row = list(row)
            number = _cell(row, mapping.get("number"))
            area = _cell_float(row, mapping.get("area"))
            if not number or not area:
                continue
            name = _cell(row, mapping.get("name")) or number
            level = _cell(row, mapping.get("level")) or "1 этаж"
            rtype = _cell(row, mapping.get("type")) or ""
            height = _cell_float(row, mapping.get("height")) or 3.0
            if not rtype:
                from hvac.catalogs.room_types import auto_detect_room_type
                rtype = auto_detect_room_type(name)
            try:
                self.add_space(number=str(number), name=str(name),
                                level=str(level), area_m2=area,
                                height_m=height, room_type=rtype)
                n += 1
            except ValueError:
                # Пропустить дубликаты, продолжить
                continue
        return n


# ===== Импорт-хелперы =====
_HEADER_SYNONYMS = {
    "number": ("№", "номер", "number", "no", "no."),
    "name":   ("имя", "название", "name", "title", "помещение"),
    "level":  ("этаж", "уровень", "level", "floor"),
    "type":   ("тип", "type", "room_type", "категория"),
    "area":   ("площадь", "area", "s", "м²", "m2", "sq m"),
    "height": ("высота", "height", "h", "h_m", "м"),
}


def _resolve_header_mapping(headers) -> dict:
    """Сопоставляет реальные заголовки таблицы с каноническими именами."""
    mapping: dict = {}
    for idx, raw in enumerate(headers):
        if raw is None:
            continue
        norm = str(raw).strip().lower()
        for canon, synonyms in _HEADER_SYNONYMS.items():
            if norm in synonyms or any(syn in norm for syn in synonyms):
                mapping.setdefault(canon, idx)
                break
    return mapping


def _cell(row, idx):
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    return str(v).strip() if v is not None else ""


def _cell_float(row, idx) -> float:
    if idx is None or idx >= len(row):
        return 0.0
    v = row[idx]
    if v is None:
        return 0.0
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0

    # ---------- Оборудование помещения ----------
    def set_room_equipment(self, space_id: str, **kwargs) -> bool:
        """Назначает поля оборудования для помещения.
        Создаёт RoomEquipment если ещё нет."""
        sp = self._space_by_id.get(space_id)
        if sp is None:
            return False
        eq = sp.get_or_create_equipment()
        for k, v in kwargs.items():
            if hasattr(eq, k):
                setattr(eq, k, v)
        self.emit("equipment_changed")
        return True
