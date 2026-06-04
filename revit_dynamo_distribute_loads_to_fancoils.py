# -*- coding: utf-8 -*-
# Dynamo CPython3 script for Revit 2026.
# Распределяет расчётную нагрузку помещений (Space) на фанкойлы
# (Mechanical Equipment), стоящие в этих помещениях.
#
# Если в одном помещении НЕСКОЛЬКО фанкойлов — нагрузка помещения делится
# между ними ПОРОВНУ: q_на_фанкойл = Q_помещения / N.
#
# Источник нагрузки — параметры Space, заполненные программой через
# «Файл → Экспорт для Revit» + revit_dynamo_apply_results.py
# (по умолчанию "Cooling Load" / "Heating Load" на категории Spaces).
#
# Результат пишется в параметры самого фанкойла (по умолчанию
# "Design Cooling Load" / "Design Heating Load"). Создайте их в проекте
# как Project/Shared Parameters категории Mechanical Equipment:
#   • тип «Число» — значение пишется как есть (Вт), ИЛИ
#   • типизированный HVAC «Мощность» — значение переводится во внутренние
#     единицы Revit автоматически (как в apply_results).
#
# Использование в Dynamo:
#   IN[0] : ключевые слова для отбора фанкойлов среди Mechanical Equipment,
#           через запятую (по умолч. "fancoil,фанкойл,фэнкойл,fcu").
#           Передайте "all" или "*" — взять ВСЁ оборудование категории.
#   IN[1] : имя параметра холода на Space (по умолч. "Cooling Load")
#   IN[2] : имя параметра тепла  на Space (по умолч. "Heating Load")

import clr

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    StorageType,
    UnitTypeId,
    UnitUtils,
)

doc = DocumentManager.Instance.CurrentDBDocument


def text(value):
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def clean_input(value):
    return text(value).strip().strip('"')


def id_value(element_id):
    try:
        return element_id.IntegerValue
    except Exception:
        try:
            return element_id.Value
        except Exception:
            return None


def is_measurable(forge_type_id):
    try:
        return UnitUtils.IsMeasurableSpec(forge_type_id)
    except Exception:
        return False


def find_writable_param(element, names):
    """Первый записываемый параметр из списка имён, или None."""
    for n in names:
        try:
            p = element.LookupParameter(n)
        except Exception:
            p = None
        if p and not p.IsReadOnly:
            return p
    return None


def find_value_param(element, names):
    """Первый параметр с заданным именем, у которого есть значение.
    Для ЧТЕНИЯ — годятся и read-only встроенные параметры."""
    for n in names:
        try:
            p = element.LookupParameter(n)
        except Exception:
            p = None
        if p is not None:
            try:
                if p.HasValue:
                    return p
            except Exception:
                return p
    return None


def read_watts(element, names, unit_type_id):
    """Читает числовой параметр, нормализуя к СИ (Вт). Для размерного
    Double переводит из внутренних единиц Revit; для безразмерного
    «Число» возвращает значение как есть (его и писал экспорт)."""
    p = find_value_param(element, names)
    if p is None:
        return None
    try:
        st = p.StorageType
        if st == StorageType.Double:
            raw = p.AsDouble()
            try:
                spec = p.Definition.GetDataType()
                if unit_type_id is not None and is_measurable(spec):
                    return UnitUtils.ConvertFromInternalUnits(raw, unit_type_id)
            except Exception:
                pass
            return raw
        if st == StorageType.Integer:
            return float(p.AsInteger())
        if st == StorageType.String:
            s = (p.AsString() or "").strip().replace(",", ".")
            return float(s) if s else None
    except Exception:
        return None
    return None


def to_internal(param, value_w, unit_type_id):
    """СИ → внутренние единицы Revit, если параметр размерный."""
    if unit_type_id is None:
        return value_w
    try:
        spec = param.Definition.GetDataType()
        if is_measurable(spec):
            return UnitUtils.ConvertToInternalUnits(float(value_w), unit_type_id)
    except Exception:
        pass
    return value_w


def set_watts(element, names, value_w, unit_type_id):
    """Записывает значение в Вт в первый найденный параметр.
    None — параметр не создан (не ошибка); False — ошибка записи."""
    p = find_writable_param(element, names)
    if p is None:
        return None
    try:
        if p.StorageType == StorageType.Double:
            p.Set(float(to_internal(p, value_w, unit_type_id)))
            return True
        if p.StorageType == StorageType.Integer:
            p.Set(int(round(float(value_w))))
            return True
        if p.StorageType == StorageType.String:
            p.Set("{0:.1f}".format(float(value_w)))
            return True
    except Exception:
        return False
    return False


# Все пространства модели — для геометрического fallback привязки.
_ALL_SPACES = list(FilteredElementCollector(doc)
                   .OfCategory(BuiltInCategory.OST_MEPSpaces)
                   .WhereElementIsNotElementType()
                   .ToElements())


def instance_space(fi):
    """Space, в котором стоит фанкойл. Сначала нативное свойство .Space,
    затем геометрия по точке размещения."""
    try:
        sp = fi.Space
        if sp is not None:
            return sp
    except Exception:
        pass
    pt = None
    try:
        pt = fi.Location.Point
    except Exception:
        pt = None
    if pt is None:
        return None
    for sp in _ALL_SPACES:
        try:
            if sp.IsPointInSpace(pt):
                return sp
        except Exception:
            continue
    return None


def family_type_text(fi):
    parts = []
    try:
        parts.append(fi.Symbol.Family.Name or "")
    except Exception:
        pass
    try:
        parts.append(fi.Name or "")
    except Exception:
        pass
    try:
        parts.append(fi.Symbol.Name or "")
    except Exception:
        pass
    return " ".join(parts).lower()


# ---------- разбор входов ----------

keywords = ["fancoil", "фанкойл", "фэнкойл", "fcu"]
take_all = False
cool_src = "Cooling Load"
heat_src = "Heating Load"

try:
    if len(IN) > 0 and IN[0]:
        raw = clean_input(IN[0])
        if raw.lower() in ("all", "*"):
            take_all = True
        else:
            keywords = [k.strip().lower() for k in raw.split(",") if k.strip()]
    if len(IN) > 1 and IN[1]:
        cool_src = clean_input(IN[1])
    if len(IN) > 2 and IN[2]:
        heat_src = clean_input(IN[2])
except Exception:
    pass

COOL_TARGET = ["Design Cooling Load", "Cooling Load"]
HEAT_TARGET = ["Design Heating Load", "Heating Load"]


def is_fancoil(fi):
    if take_all:
        return True
    t = family_type_text(fi)
    for kw in keywords:
        if kw in t:
            return True
    return False


equipment = list(FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_MechanicalEquipment)
                 .WhereElementIsNotElementType()
                 .ToElements())
fancoils = [e for e in equipment if is_fancoil(e)]

# Группировка фанкойлов по пространству
by_space = {}     # space_id -> [fancoil, ...]
space_obj = {}    # space_id -> Space
no_space = 0
for fc in fancoils:
    sp = instance_space(fc)
    if sp is None:
        no_space += 1
        continue
    sid = id_value(sp.Id)
    space_obj[sid] = sp
    by_space.setdefault(sid, []).append(fc)

TransactionManager.Instance.EnsureInTransaction(doc)

written = 0
skipped_no_param = 0
spaces_no_load = 0

for sid, fcs in by_space.items():
    n = len(fcs)
    sp = space_obj[sid]
    cool = read_watts(sp, [cool_src], UnitTypeId.Watts)
    heat = read_watts(sp, [heat_src], UnitTypeId.Watts)
    if (cool is None or cool == 0) and (heat is None or heat == 0):
        spaces_no_load += 1
    cool_each = (cool / n) if (cool is not None and n > 0) else None
    heat_each = (heat / n) if (heat is not None and n > 0) else None

    for fc in fcs:
        if cool_each is not None:
            r = set_watts(fc, COOL_TARGET, cool_each, UnitTypeId.Watts)
            if r is True:
                written += 1
            elif r is None:
                skipped_no_param += 1
        if heat_each is not None:
            r = set_watts(fc, HEAT_TARGET, heat_each, UnitTypeId.Watts)
            if r is True:
                written += 1
            elif r is None:
                skipped_no_param += 1

TransactionManager.Instance.TransactionTaskDone()

OUT = [
    "Готово",
    "Фанкойлов найдено: " + str(len(fancoils)),
    "Привязано к помещениям: " + str(sum(len(v) for v in by_space.values())),
    "Без помещения (пропущено): " + str(no_space),
    "Помещений с фанкойлами: " + str(len(by_space)),
    "Помещений без нагрузки в параметрах: " + str(spaces_no_load),
    "Записано значений: " + str(written),
    ("Внимание: на части фанкойлов нет целевого параметра "
     "(Design Cooling/Heating Load)") if skipped_no_param else "Целевые параметры найдены везде",
]
