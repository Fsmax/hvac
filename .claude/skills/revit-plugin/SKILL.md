---
name: revit-plugin
description: Разработка плагина (add-in) для Revit — структура csproj под несколько версий Revit, манифест .addin, IExternalApplication/IExternalCommand, риббон, сборка и деплой, отладка, конфликт сборок dev+prod. Использовать при создании или правке .NET-плагина Revit.
---

# Плагин Revit (.NET)

Рабочий образец на этой машине: `D:\mcp-cad\RevitCortex-fork` — плагин,
собираемый под Revit 2023–2027 из одного проекта. Копируй подход оттуда,
а не с нуля.

## Целевой фреймворк

| Revit | Runtime | TargetFramework |
|---|---|---|
| 2023, 2024 | .NET Framework 4.8 | `net48` |
| 2025, 2026 | .NET 8 | `net8.0-windows` |
| 2027 | **.NET 10** | `net10.0-windows` |

Revit 2027 переехал на .NET 10 — под него нужен отдельный SDK, сборка
net8 туда не загрузится. Конфигурация `R27` в этом форке пока рассчитана
на старое предположение, при первой реальной сборке под 2027 её надо
править вместе с `global.json`.

SDK: `global.json` фиксирует `8.0.420` с `rollForward: latestMajor`.
На машине два dotnet — `C:\Users\black\.dotnet\dotnet.exe` (user-local,
им и собирается форк) и `C:\Program Files\dotnet`.

## Ссылки на API: NuGet вместо HintPath

Прямой `HintPath` на `C:\Program Files\Autodesk\Revit 2026\RevitAPI.dll`
работает, но привязывает сборку к установленной версии. Для мультиверсионного
проекта берут NuGet — версия пакета совпадает с годом Revit:

```xml
<ItemGroup>
  <PackageReference Include="Nice3point.Revit.Api.RevitAPI" Version="$(RevitVersion).*" />
  <PackageReference Include="Nice3point.Revit.Api.RevitAPIUI" Version="$(RevitVersion).*" />
</ItemGroup>
```

Пакеты уже помечены как `ExcludeAssets=runtime`, отдельно ставить
`Private=false` не нужно. Актуальные версии: `2026.4.0`, `2027.1.0`.
Альтернативы: `Revit_All_Main_Versions_API_x64`, официальный `Autodesk.Revit.SDK`.

## csproj: одна кодовая база под много версий

Конфигурации вида `Debug R26` / `Release R26`, и свойства выбираются условием:

```xml
<PropertyGroup Condition="$(Configuration.Contains('R26'))">
  <RevitVersion>2026</RevitVersion>
  <TargetFramework>net8.0-windows</TargetFramework>
  <DefineConstants>$(DefineConstants);REVIT2026_OR_GREATER</DefineConstants>
</PropertyGroup>

<ItemGroup>
  <Reference Include="RevitAPI">
    <HintPath>C:\Program Files\Autodesk\Revit $(RevitVersion)\RevitAPI.dll</HintPath>
    <Private>false</Private>   <!-- обязательно: не копировать в вывод -->
  </Reference>
</ItemGroup>
```

`Private=false` (CopyLocal off) для сборок Revit — иначе плагин потянет
свою копию RevitAPI.dll и Revit его не загрузит.

Различия версий API закрывай `#if REVIT2026_OR_GREATER`, а не отдельными
ветками репозитория.

## Манифест .addin

```xml
<?xml version="1.0" encoding="utf-8"?>
<RevitAddIns>
  <AddIn Type="Application">
    <Name>МойПлагин</Name>
    <Assembly>МойПлагин\МойПлагин.dll</Assembly>
    <FullClassName>МойПлагин.App</FullClassName>
    <AddInId>СВОЙ-НОВЫЙ-GUID</AddInId>
    <VendorId>ADSK-или-свой</VendorId>
  </AddIn>
</RevitAddIns>
```

`Type`: `Application` — грузится при старте Revit (риббон, события);
`Command` — одна кнопка/команда. `AddInId` должен быть уникальным GUID,
свой для каждого плагина.

### Изоляция сборок (Revit 2026+) — лечит конфликт версий зависимостей

С 2026 плагин можно грузить в отдельный AssemblyLoadContext, чтобы его
зависимости (Newtonsoft.Json и прочее) не сталкивались с версиями Revit
и других плагинов:

```xml
<RevitAddIns>
  <ManifestSettings>
    <UseRevitContext>False</UseRevitContext>
    <ContextName>МойКонтекст</ContextName>   <!-- необязательно -->
  </ManifestSettings>
  <AddIn Type="Application"> … </AddIn>
</RevitAddIns>
```

По умолчанию `UseRevitContext` = `True` (старое поведение). Настройка
действует на все AddIn в этом манифесте. Плагины из одной папки попадают
в один контекст; из разных папок — в разные, если не задан общий
`ContextName`. В Revit 2027 механизм расширен: зависимости между плагинами
объявляются явно. Программный доступ — `RevitAddInManifestSettings`.

Это, а не разные `AssemblyName`, — правильное лечение конфликта dev+prod
на 2026 и новее. Приём с переименованием сборки остаётся для 2023–2025.

Куда класть:

| Область | Путь |
|---|---|
| Пользователь | `%APPDATA%\Autodesk\Revit\Addins\2026` |
| Машина | `C:\ProgramData\Autodesk\Revit\Addins\2026` |

Оба каталога на этой машине уже существуют.

## Точки входа

```csharp
public class App : IExternalApplication {
    public Result OnStartup(UIControlledApplication a) {
        var panel = a.CreateRibbonPanel(Tab.AddIns, "Моя панель");
        panel.AddItem(new PushButtonData("cmd", "Кнопка",
            Assembly.GetExecutingAssembly().Location, "МойПлагин.MyCommand"));
        return Result.Succeeded;
    }
    public Result OnShutdown(UIControlledApplication a) => Result.Succeeded;
}

[Transaction(TransactionMode.Manual)]
public class MyCommand : IExternalCommand {
    public Result Execute(ExternalCommandData c, ref string msg, ElementSet e) {
        var doc = c.Application.ActiveUIDocument.Document;
        // транзакции открываем сами — режим Manual
        return Result.Succeeded;
    }
}
```

Работа из своего потока (сокет-сервер, таймер) — только через
`ExternalEvent.Create(handler)` + `Raise()`. Прямой вызов API вне контекста
Revit роняет приложение.

## Грабли, уже пойманные в этом форке

- **Конфликт сборок при dev+prod одновременно.** Два .addin (машинный prod
  и пользовательский dev) грузятся в один AppDomain. Если у сборок одинаковое
  простое имя — второй отвергается с `FileLoadException: Assembly with same
  name is already loaded`. Разный `AddInId` **не спасает**: коллизия на уровне
  CLR, а не манифеста. Решение: dev-сборке дать другой `AssemblyName`
  (`-p:DevBuild=true` → `МойПлагин.Dev`), `RootNamespace` не менять, чтобы
  `FullClassName` в .addin продолжал резолвиться.
- Плагин с длинной операцией имеет exec-timeout — если он исполняет внешний
  код, режь работу на батчи (см. `revit-bridge`).
- `"Failed to create command instance"` в логе Revit — сообщение мислейбл,
  на деле операция прошла успешно.

## Сборка и деплой

В форке готовые скрипты: `deploy-dev.ps1` (dev-профиль в user-scope),
`deploy-userscope.ps1`, `deploy-all-years.ps1`, `build-release.ps1`,
`check-install.ps1`. Не пиши свои — посмотри эти.

Отладка: Revit должен быть закрыт при копировании DLL (файл занят);
затем attach отладчиком к `Revit.exe`. Логи плагина полезнее пошаговой
отладки — Revit при исключении в API часто падает целиком.

## Инструменты и стартовые шаблоны

- **Шаблоны проектов**: `dotnet new install Nice3point.Revit.Templates` —
  готовые каркасы плагина, включая варианты с тестами (TUnit) и бенчмарком.
  Быстрее, чем собирать csproj вручную.
- **Nice3point.Revit.Toolkit** — обёртки над часто реализуемыми интерфейсами
  (`IExternalCommand`, `IFamilyLoadOptions`, обработчики внешних событий,
  контекст Revit). Снимает много шаблонного кода.
- **RevitLookup** (`lookup-foundation/RevitLookup`, ставится через WinGet или
  MSI) — интерактивный инспектор БД модели и .rfa. Первый инструмент, когда
  непонятно, где лежит нужный параметр или как связаны элементы.
- **pyRevit** — прототип идеи на Python внутри Revit до того, как писать
  компилируемый плагин.
- Справочники API: `revitapidocs.com`, `rvtdocs.com` (версии 2020–2027),
  примеры — репозиторий `jeremytammik/RevitSdkSamples`, SDK на портале APS.
