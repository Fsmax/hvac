---
name: revit-family
description: Семейства Revit — шаблоны .rft (пути и какой под что), создание и правка .rfa через API (NewFamilyDocument, EditFamily, FamilyManager), типы и параметры, коннекторы MEP, загрузка в проект. Использовать при авторинге или правке семейств, в том числе марок и оборудования ОВиК.
---

# Семейства Revit

## Где лежат шаблоны .rft

`C:\ProgramData\Autodesk\RVT 2026\Family Templates\Russian\` — 111 шаблонов,
метрические, русскоязычные. Подпапки: `Аннотации`, `Основные надписи`,
`Концептуальные формы`.

Что брать под задачу:

| Задача | Шаблон |
|---|---|
| Оборудование ОВиК (фанкойл, AHU, котёл) | `Метрическая система, оборудование.rft` |
| То же, настенное / потолочное | `…оборудование, настенное.rft` / `…потолочное.rft` |
| Сантехприбор | `Метрическая система, сантехнический прибор.rft` |
| Электрооборудование | `Метрическая система, электрооборудование.rft` |
| Произвольный объект | `Метрическая система, типовая модель.rft` |
| Объект на стене / потолке / полу | `…типовая модель на основе стены.rft` и т.п. |
| Марка, обозначение | `Аннотации\` |
| Рамка листа | `Основные надписи\` |

**Важно: фитингов воздуховодов и труб в русской папке нет.** Они только
в `English\`: `Metric Duct Elbow.rft`, `Metric Duct Tee.rft`,
`Metric Duct Cross.rft`, `Metric Duct Transition.rft`. Берём оттуда,
имена параметров внутри всё равно системные.

Библиотека готовых семейств: `C:\ProgramData\Autodesk\RVT 2026\Libraries\Russian\`
(разделы `Russia`, `Belarus`, `Ukraine`).

## Создание и правка через API

```csharp
// новое семейство из шаблона
Document fam = app.NewFamilyDocument(templatePath);

// правка уже загруженного в проект
Document fam = doc.EditFamily(family);

// правка .rfa с диска
Document fam = app.OpenDocumentFile(rfaPath);
```

**Каждый открытый документ семейства обязан быть закрыт.** Утёкший документ
блокирует любой последующий `EditFamily` на это же семейство до конца сессии
Revit — перезапуск Revit единственное лечение. Закрывать через один общий
путь выхода, с обработкой исключений.

Варианты завершения: перезагрузить в проект (`fam.LoadFamily(doc, options)`),
сохранить на диск (`SaveAs`), либо и то и другое, либо отбросить.
При перезагрузке нужен `IFamilyLoadOptions` — без него Revit спросит
пользователя и операция зависнет в фоне. Готовая реализация есть в
`Nice3point.Revit.Toolkit`, писать свою заново не обязательно.

Смотреть, что внутри чужого .rfa (параметры, типы, вложенные семейства,
коннекторы), удобнее всего RevitLookup — он открывает и семейства, и проекты.

## FamilyManager — параметры и типы

```csharp
FamilyManager fm = fam.FamilyManager;

FamilyParameter p = fm.AddParameter("Расход_воздуха",
        GroupTypeId.Mechanical, SpecTypeId.AirFlow, isInstance: false);

FamilyType t = fm.NewType("600x600");
fm.CurrentType = t;
fm.Set(p, UnitUtils.ConvertToInternalUnits(500, UnitTypeId.CubicMetersPerHour));
```

- Значения — во внутренних единицах (см. скилл `revit-api`).
- `isInstance: true` — параметр экземпляра, `false` — типа.
- Формула: `fm.SetFormula(p, "Ширина * 2")`; имена в формуле — как в семействе,
  то есть локализованные.
- Общий параметр: `fm.AddParameter(externalDefinition, group, isInstance)`.

## Коннекторы MEP в семействе

В документе семейства (шаблон оборудования):

```csharp
ConnectorElement.CreateDuctConnector(fam, DuctSystemType.SupplyAir,
        ConnectorProfileType.Rectangular, face);
ConnectorElement.CreatePipeConnector(fam, PipeSystemType.SupplyHydronic, face);
```

Привязываются к грани (`Face`) элемента геометрии, а не к точке.
Link Connectors из API недоступны — если нужна связка «втулка + свободный
фланец», делается собственным семейством, как в проекте Yangi Toshkent.

## Марки: текста метки в API нет

Изменить надпись существующей марки через API нельзя — это метка (label)
внутри семейства марки. Порядок: копия .rfa → правка метки в редакторе
семейств вручную → загрузка → `ChangeTypeId` на существующих марках.
Так делалась марка труб с длиной (`ADSK_M_Трубы_L`, формат `L= … м`).

## Готовый код

`D:\mcp-cad\RevitCortex-fork\src\RevitCortex.Tools\Families\`:

- `FamilyEditSupport.cs` — резолв цели (по id / имени / пути .rfa), открытие
  и корректное закрытие документа семейства. Основа, читать первой.
- `CreateFamilyTool.cs` — создание семейства из шаблона.
- `FamilyOperations.cs` — операции над FamilyManager.

Там же второй MCP-сервер RevitCortex (порт **8081**, отдельно от моста ОВиК
на 8080) с пятью собственными тулзами авторинга .rfa — при задаче на
семейства сначала проверь, не покрыта ли она ими.
