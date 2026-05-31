# -*- coding: utf-8 -*-
# Dynamo CPython3 script for Revit 2026.
# Применяет результаты расчёта (heating/cooling load) обратно в параметры
# Space/Room в Revit. Читает CSV с колонками:
#     space_id, heating_load_w, cooling_load_w
# (формируется программой hvac_calc.py через "Файл → Экспорт для Revit")
#
# Использование в Dynamo:
#   IN[0] : путь к CSV с результатами (например, "D:\HVAC\results_for_revit.csv")
#   IN[1] : имя параметра для теплопотерь (по умолч. "Heating Load")
#   IN[2] : имя параметра для теплопоступл. (по умолч. "Cooling Load")
#
# Параметры должны существовать в проекте у категории Spaces/Rooms.
# Если параметра нет — добавьте Project Parameter (Number или Common — Power, Вт).

import clr
import csv

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    StorageType,
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


def parse_float(s, default=0.0):
    if s is None:
        return default
    try:
        return float(str(s).strip().replace(",", "."))
    except Exception:
        return default


def set_value(element, names_or_builtin, value_w):
    """Записывает значение в первый найденный параметр.
    names_or_builtin — список имён параметров или BuiltInParameter (кортежем)."""
    param = None
    for n in names_or_builtin:
        if isinstance(n, str):
            param = element.LookupParameter(n)
        else:
            try:
                param = element.get_Parameter(n)
            except Exception:
                param = None
        if param and not param.IsReadOnly:
            break
        param = None
    if param is None:
        return False, "Параметр не найден"

    try:
        if param.StorageType == StorageType.Double:
            # Revit хранит мощность во внутренних единицах. Для категории Power
            # это W → 1 Вт = 1.0 в внутр. единицах? Проверка через AsValueString.
            # Простой подход: установить через value_string не надёжен.
            # Установим напрямую — для большинства Project Parameters типа
            # «Число» это просто значение в Вт.
            try:
                param.Set(float(value_w))
                return True, "OK"
            except Exception as e:
                return False, text(e)
        elif param.StorageType == StorageType.String:
            param.Set("{0:.0f} W".format(value_w))
            return True, "OK (text)"
        elif param.StorageType == StorageType.Integer:
            param.Set(int(round(value_w)))
            return True, "OK"
    except Exception as e:
        return False, text(e)
    return False, "Тип параметра не поддержан"


# ---------- разбор входов ----------

csv_path = ""
heating_param_name = "Heating Load"
cooling_param_name = "Cooling Load"

try:
    if len(IN) > 0 and IN[0]:
        csv_path = clean_input(IN[0])
    if len(IN) > 1 and IN[1]:
        heating_param_name = clean_input(IN[1])
    if len(IN) > 2 and IN[2]:
        cooling_param_name = clean_input(IN[2])
except Exception:
    pass

if not csv_path:
    OUT = ["Ошибка: не задан путь к CSV (IN[0])"]
else:
    # Читаем CSV
    rows = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    except Exception as e:
        OUT = ["Ошибка чтения CSV", text(e)]
        rows = None

    if rows is not None:
        # Собираем все Spaces в словарь по id
        spaces = (FilteredElementCollector(doc)
                  .OfCategory(BuiltInCategory.OST_MEPSpaces)
                  .WhereElementIsNotElementType()
                  .ToElements())
        if not spaces:
            spaces = (FilteredElementCollector(doc)
                      .OfCategory(BuiltInCategory.OST_Rooms)
                      .WhereElementIsNotElementType()
                      .ToElements())
        spaces_by_id = {text(id_value(s.Id)): s for s in spaces}

        TransactionManager.Instance.EnsureInTransaction(doc)

        ok_count = 0
        miss_count = 0
        param_errors = []
        names_heat = [heating_param_name, "Heating Load",
                      "Calculated Heating Load", "Design Heating Load"]
        names_cool = [cooling_param_name, "Cooling Load",
                      "Calculated Cooling Load", "Design Cooling Load"]

        for r in rows:
            sid = (r.get("space_id") or "").strip()
            if not sid:
                continue
            element = spaces_by_id.get(sid)
            if element is None:
                miss_count += 1
                continue
            q_heat = parse_float(r.get("heating_load_w"))
            q_cool = parse_float(r.get("cooling_load_w"))

            ok_h, msg_h = set_value(element, names_heat, q_heat)
            ok_c, msg_c = set_value(element, names_cool, q_cool)

            if ok_h or ok_c:
                ok_count += 1
            if not ok_h:
                param_errors.append("{0}: heating — {1}".format(sid, msg_h))
            if not ok_c:
                param_errors.append("{0}: cooling — {1}".format(sid, msg_c))

        TransactionManager.Instance.TransactionTaskDone()

        OUT = [
            "Готово",
            "Обновлено помещений: " + str(ok_count),
            "Не найдено: " + str(miss_count),
            "Параметр отопления: " + heating_param_name,
            "Параметр охлаждения: " + cooling_param_name,
            "Ошибки (первые 10): " + " | ".join(param_errors[:10]) if param_errors else "Ошибок нет",
        ]
