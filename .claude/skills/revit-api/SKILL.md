---
name: revit-api
description: Справочник Revit API 2026 — единицы измерения (внутренние футы), транзакции, FilteredElementCollector, параметры и локализация, MEP (Space, системы, коннекторы, воздуховоды/трубы), геометрия и виды. Использовать при написании любого C# для Revit — через мост, в плагине или в семействе.
---

# Revit API 2026

Установка на этой машине: `C:\Program Files\Autodesk\Revit 2026`.
Сборки: `RevitAPI.dll`, `RevitAPIUI.dll` там же. Revit 2025+ — .NET 8,
Revit 2024 и старше — .NET Framework 4.8.

Быстрый эксперимент выполняется через мост (`send_code`) — см. скилл
`revit-bridge`. Здесь только сам API.

## Единицы — источник большинства ошибок

Внутренние единицы Revit **имперские, всегда**, независимо от единиц проекта:

| Величина | Внутри API |
|---|---|
| Длина | футы (ft) |
| Площадь | ft² — коэффициент **10.7639** к м² |
| Объём | ft³ |
| Расход воздуха | ft³/s (CFS), не м³/ч |
| Углы | радианы |
| Мощность, температура | **уже СИ** (Вт, К) — не конвертировать |

```csharp
double m2 = UnitUtils.ConvertFromInternalUnits(area, UnitTypeId.SquareMeters);
double ft = UnitUtils.ConvertToInternalUnits(3.5, UnitTypeId.Meters);
```

Ловушка, на которой уже обжигались: нагрузки `aec:number` пишутся в ваттах
как есть — умножение на 10.764 там неверно. Проверяй, что за величина,
прежде чем конвертировать.

## Транзакции

Любая запись — только внутри `Transaction`. Чтение — без неё.

```csharp
using (var t = new Transaction(doc, "Название в истории отмены")) {
    t.Start();
    // ...
    t.Commit();      // или t.RollBack()
}
```

- Вложенность — `SubTransaction`; группировка — `TransactionGroup` + `Assimilate()`.
- Транзакцию нельзя открыть внутри уже открытой на том же документе.
- `doc.Regenerate()` — если следующий шаг читает геометрию, созданную выше.
- Через мост `send_code` транзакция открывается плагином автоматически
  (`transaction_mode="auto"`); для чтения ставь `"none"`.
- API можно звать **только из контекста Revit**. Из своего потока — через
  `ExternalEvent` + `IExternalEventHandler`.

## Выборка элементов

```csharp
var spaces = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_MEPSpaces)
    .WhereElementIsNotElementType()
    .Cast<Space>().ToList();
```

- `new FilteredElementCollector(doc, viewId)` — только видимое на виде.
  **Для неоткрытых видов вернёт 0** — известная ловушка. Фильтруй по
  `LevelId`/`OwnerViewId`, а не по активному виду.
- `.OfClass(typeof(Duct))` быстрее, чем перебор всех элементов.
- `ElementId` в 2024+ — 64-битный: `id.Value`. `IntegerValue` устарел.

## Параметры

```csharp
var p = el.get_Parameter(BuiltInParameter.ROOM_AREA);   // надёжно
var q = el.LookupParameter("Расход");                   // зависит от языка!
```

Интерфейс Revit здесь русский, поэтому имена встроенных параметров
локализованы. Ищи по `BuiltInParameter`; `LookupParameter` по строке —
только для своих и общих параметров.

Запись: `p.Set(value)` — значение во внутренних единицах. `p.IsReadOnly`
проверяй заранее: например, встроенный `occupancy` у Space read-only,
свои значения писать в собственные параметры.

## MEP

- `Space` (OST_MEPSpaces) и `Room` — разные элементы. У ОВиК — Space.
  Неразмещённый Space имеет `Area == 0` и `Location == null`.
- Системы: `MEPSystem`, `MechanicalSystem`, `PipingSystem`;
  `system.DuctNetwork` / `PipingNetwork` — элементы системы.
- Соединения: `ConnectorManager` → `Connectors`; `c1.ConnectTo(c2)`.
  Врезка в магистраль — `doc.Create.NewTakeoffFitting(connector, mepCurve)`.
- Создание: `Duct.Create(doc, systemTypeId, ductTypeId, levelId, p1, p2)`,
  `Pipe.Create(...)`. Сечение задаётся после создания через параметры
  (`RBS_CURVE_WIDTH_PARAM` / `HEIGHT` / `DIAMETER_PARAM`).
- Расходы у созданных элементов = 0, пока нет расчётной системы — это
  нормально, сечение задаём вручную.

## Геометрия и виды

- `el.get_BoundingBox(null)` — в координатах модели; `null` вместо вида
  даёт габарит модели, а не вида.
- Пустой план чаще всего означает повреждённый гигантский `CropBox`,
  а не отсутствие элементов.
- Поворот плана: крутить надо элемент с `view.Id + 2`. Сам вид, CropBox
  и ExtentElem — no-op. Проверяй ShapeSet: пользовательский косой контур
  за поворотом не поедет.
- Марки: `IndependentTag.Create(doc, tagTypeId, viewId, reference, addLeader,
  orientation, point)`. Текст метки из API не меняется — это свойство
  семейства марки, правится в редакторе семейств.

## Что сломалось в 2026 (проверь, если код писался под 2024/2025)

- `new ElementId(int)` **удалён** — только `ElementId(Int64)`. Соответственно
  `IntegerValue` → `Value`.
- Переименованы BuiltInParameter: `OMNICLASS_CODE` → `CLASSIFICATION_CODE`,
  `UNIFORMAT_CODE` → `ASSEMBLY_CODE`; у балок и колонн видимое имя
  «Длина» стало «Системная длина» — поиск параметра по строке ломается.
- **Зоны ОВиК**: `Zone` объявлен устаревшим. Создание — через
  `GenericZone.CreateSketchBased()` / `GenericZone.CreateSpaceBased()`
  вместо `GenericZone.Create()`.
- Пересечения кривых: `SetComparisonResult` → `CurveIntersectResult`
  (`.Result`, `.GetOverlaps()`).
- Видовые экраны: `Viewport.ViewportPositioning` → класс `ViewPosition`
  со свойством `ViewAnchor`.
- Электрика переписана: `WireType` теперь ссылается на `ElementId` вместо
  перечислений; появились `ConductorMaterial`, `InsulationMaterial`,
  `ConductorSize`, `CableType` и др.
- Арматура: `RebarHookOrientation` → `RebarTerminationOrientation`,
  перегрузки `Rebar.CreateFromCurves()` устарели в пользу `BarTerminationsData`.
- CefSharp удалён из поставки Revit — плагин, тянувший его, не соберётся.

Ревизия версий: 2025–2026 — .NET 8, 2027 — .NET 10. Проверять поведение
на той версии, под которую собираешь.

## Справочник — офлайн, локально

Официальная справка Revit API 2026 (`RevitAPI.chm`) распакована в
`D:\mcp-cad\revit-api-2026\`. **Сигнатуру проверяй здесь, а не по памяти
и не поиском в сети** — страницы дают точный namespace, сборку и версию.

```
python D:\mcp-cad\revit-api-2026\revitapi.py "NewTakeoffFitting" -s
python D:\mcp-cad\revit-api-2026\revitapi.py Duct.Create -l 10
python D:\mcp-cad\revit-api-2026\revitapi.py UnitTypeId -s -n 2 -c 6000
```

`-s` печатает текст страницы, `-n` — сколько страниц, `-l` — длина списка,
`-c` — обрезка. Сами html названы GUID'ами, читать их напрямую бесполезно:
связь «имя → файл» лежит в `RevitAPI.hhk`, скрипт её и разбирает.
Человеку удобнее открыть `D:\2026.chm` обычным просмотрщиком.

Онлайн, когда нужного нет локально: `revitapidocs.com`, `rvtdocs.com`
(2020–2027, там же `news` с изменениями по годам). Примеры проектов —
`jeremytammik/RevitSdkSamples`.

Инспектировать живую модель — **RevitLookup** (вкладка «Надстройки»):
ткнуть в элемент → Snoop Current Selection, и видно реальные имена
параметров со значениями. Это дешевле, чем пробы через мост.

## Живые образцы кода

`D:\mcp-cad\RevitCortex-fork\src\RevitCortex.Tools\` — рабочий C# под этот же
Revit: создание элементов, семейства, IFC, выборки. Прежде чем писать с нуля,
загляни туда: `Elements\`, `Families\`, `Views\`.

Готовые Python-обёртки над частыми операциями — в `hvac/revit_link.py`
(`snapshot_spaces`, `probe_facades`, `tag_wall_exterior`, `import_from_revit`).
