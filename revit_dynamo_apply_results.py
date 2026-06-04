# -*- coding: utf-8 -*-
# Dynamo CPython3 script for Revit 2026.
# Применяет результаты расчёта обратно в параметры Space/Room в Revit.
# Читает CSV, сформированный программой (Файл → Экспорт для Revit),
# с полным инженерным набором колонок:
#     space_id, space_number, space_name,
#     heating_load_w, cooling_load_w, cooling_sensible_w, cooling_latent_w,
#     supply_m3h, exhaust_m3h, ach,
#     t_in_heat, t_in_cool,
#     system_heating, system_cooling, system_ventilation,
#     circuit_heating, circuit_cooling, duct_zone
#
# Использование в Dynamo:
#   IN[0] : путь к CSV с результатами (например, "D:\HVAC\results_for_revit.csv")
#   IN[1] : имя параметра для теплопотерь   (необяз., по умолч. "Heating Load")
#   IN[2] : имя параметра для теплопоступл.  (необяз., по умолч. "Cooling Load")
#
# В проекте Revit создайте Project Parameters категории Spaces (или Rooms):
#   ЧИСЛОВЫЕ:  Heating Load, Cooling Load, Cooling Sensible Load,
#       Cooling Latent Load, Supply Airflow, Exhaust Airflow, Air Changes,
#       Heating Setpoint, Cooling Setpoint
#   ТЕКСТОВЫЕ (тип «Текст»): Heating System, Cooling System, Ventilation System,
#       Heating Circuit, Cooling Circuit, Duct Zone
#
# Числовые параметры можно создать двумя способами — скрипт сам определит,
# как писать значение:
#   • тип «Число» (без единиц) — значение пишется как есть: Вт, м³/ч, °C;
#   • типизированный параметр (HVAC > Мощность / Расход воздуха,
#     Электрика и т.п. / Температура) — значение автоматически переводится
#     во внутренние единицы Revit (для температуры с учётом смещения °C→K).
#
# Колонки, для которых параметр не найден, просто пропускаются — создавать
# нужно только те, что вам действительно требуются в модели.

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


def parse_float(s, default=0.0):
    if s is None:
        return default
    try:
        return float(str(s).strip().replace(",", "."))
    except Exception:
        return default


def find_param(element, names):
    """Первый записываемый параметр из списка имён, или None."""
    for n in names:
        try:
            param = element.LookupParameter(n)
        except Exception:
            param = None
        if param and not param.IsReadOnly:
            return param
    return None


def _to_internal(param, value, unit_type_id):
    """Переводит значение в СИ во внутренние единицы Revit, ЕСЛИ параметр
    типизирован единицей измерения (HVAC Power / Air Flow / Temperature и
    т.п.). Для безразмерного «Число» возвращает значение как есть.

    Это позволяет одному скрипту писать и в простые Number-параметры
    (значение «как есть»: Вт, м³/ч, °C), и в типизированные параметры
    Revit, которые в БД хранятся во внутренних единицах. Для температуры
    UnitUtils корректно учитывает смещение °C→K."""
    if unit_type_id is None:
        return value
    try:
        spec = param.Definition.GetDataType()
        if UnitUtils.IsMeasurableSpec(spec):
            return UnitUtils.ConvertToInternalUnits(float(value), unit_type_id)
    except Exception:
        pass
    return value


def set_number(element, names, value_w, unit_type_id=None):
    """Записывает числовое значение в первый найденный параметр.
    Double — с автоконверсией единиц (см. _to_internal); Integer —
    округление; String — форматирование текстом."""
    param = find_param(element, names)
    if param is None:
        return None  # параметр не создан — не ошибка, просто пропуск
    try:
        if param.StorageType == StorageType.Double:
            param.Set(float(_to_internal(param, value_w, unit_type_id)))
            return True
        if param.StorageType == StorageType.Integer:
            param.Set(int(round(float(value_w))))
            return True
        if param.StorageType == StorageType.String:
            param.Set("{0:.1f}".format(float(value_w)))
            return True
    except Exception:
        return False
    return False


def set_text(element, names, value):
    """Записывает текстовое значение (имя системы/контура) в строковый
    параметр. Пустые значения не пишутся, чтобы не затирать данные."""
    s = text(value).strip()
    if not s:
        return None
    param = find_param(element, names)
    if param is None:
        return None
    try:
        if param.StorageType == StorageType.String:
            param.Set(s)
            return True
    except Exception:
        return False
    return False  # параметр есть, но не текстовый


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

# Сопоставление колонок CSV параметрам Revit.
# Списки имён дают запасные варианты — берётся первый записываемый.
# heating/cooling начинаются с переопределяемого пользователем имени.
# Третий элемент — единица СИ для автоконверсии в типизированных
# параметрах Revit (None = безразмерное «Число», пишется как есть).
NUMERIC_FIELDS = [
    ("heating_load_w",     [heating_param_name, "Heating Load",
                            "Calculated Heating Load", "Design Heating Load"],
                           UnitTypeId.Watts),
    ("cooling_load_w",     [cooling_param_name, "Cooling Load",
                            "Calculated Cooling Load", "Design Cooling Load"],
                           UnitTypeId.Watts),
    ("cooling_sensible_w", ["Cooling Sensible Load", "Sensible Cooling Load"],
                           UnitTypeId.Watts),
    ("cooling_latent_w",   ["Cooling Latent Load", "Latent Cooling Load"],
                           UnitTypeId.Watts),
    ("supply_m3h",         ["Supply Airflow", "Supply Air Flow"],
                           UnitTypeId.CubicMetersPerHour),
    ("exhaust_m3h",        ["Exhaust Airflow", "Exhaust Air Flow"],
                           UnitTypeId.CubicMetersPerHour),
    ("ach",                ["Air Changes", "Air Changes per Hour", "ACH"], None),
    ("t_in_heat",          ["Heating Setpoint", "Heating Set Point"],
                           UnitTypeId.Celsius),
    ("t_in_cool",          ["Cooling Setpoint", "Cooling Set Point"],
                           UnitTypeId.Celsius),
]
TEXT_FIELDS = [
    ("system_heating",     ["Heating System"]),
    ("system_cooling",     ["Cooling System"]),
    ("system_ventilation", ["Ventilation System"]),
    ("circuit_heating",    ["Heating Circuit"]),
    ("circuit_cooling",    ["Cooling Circuit"]),
    ("duct_zone",          ["Duct Zone"]),
]


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
        written_params = 0
        skipped_params = set()   # имена колонок без найденного параметра
        failed_params = []       # реальные ошибки записи

        for r in rows:
            sid = (r.get("space_id") or "").strip()
            if not sid:
                continue
            element = spaces_by_id.get(sid)
            if element is None:
                miss_count += 1
                continue

            touched = False
            for col, names, unit in NUMERIC_FIELDS:
                if col not in r:
                    continue
                res = set_number(element, names, parse_float(r.get(col)), unit)
                if res is True:
                    written_params += 1
                    touched = True
                elif res is False:
                    failed_params.append("{0}: {1}".format(sid, col))
                else:
                    skipped_params.add(col)

            for col, names in TEXT_FIELDS:
                if col not in r:
                    continue
                res = set_text(element, names, r.get(col))
                if res is True:
                    written_params += 1
                    touched = True
                elif res is False:
                    failed_params.append("{0}: {1}".format(sid, col))
                else:
                    skipped_params.add(col)

            if touched:
                ok_count += 1

        TransactionManager.Instance.TransactionTaskDone()

        OUT = [
            "Готово",
            "Обновлено помещений: " + str(ok_count),
            "Записано значений параметров: " + str(written_params),
            "Помещений не найдено в модели: " + str(miss_count),
            ("Колонки без параметра в проекте (пропущены): "
             + (", ".join(sorted(skipped_params)) if skipped_params else "нет")),
            ("Ошибки записи (первые 10): "
             + (" | ".join(failed_params[:10]) if failed_params else "нет")),
        ]
