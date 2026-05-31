# Архитектура HVAC Calculator v4.0

Расчёт ОВиК + ГВС: теплопотери, теплопоступления, вентиляция,
дымоудаление, ГВС, энергопаспорт, подбор воздуховодов и труб,
гидравлика отопления, акустика AHU, спецификация оборудования.
Нормативы: КМК Узбекистана + СП РФ (50, 60, 7, 30, 44, 113, 131),
с пресетами NFPA 92 и пользовательских профилей.

## Структура пакета

```
hvac_v4/
├── hvac_calc.py                # Точка входа (27 строк): GUI или CLI
├── ARCHITECTURE.md             # Этот файл
├── README.md / USER_GUIDE*.md  # Описание и руководство
│
├── hvac/                       # Главный пакет (~99 .py файлов)
│   ├── __init__.py             # Публичный API + __version__
│   ├── models.py               # Space, BoundaryElement, Construction, Layer, ProjectParameters
│   ├── parsers.py              # Парсеры строк (Revit CSV)
│   ├── data_loader.py          # Загрузка spaces.csv / thermal_all.csv
│   │
│   ├── project.py              # HVACProject — оркестратор + event-bus
│   ├── _project_manual_entry.py    # Mixin: ручной ввод помещений/ограждений
│   ├── _project_smoke.py           # Mixin: СДУ / СПВ (дымоудаление + подпор)
│   ├── _project_extensions.py      # Mixin: DHW / energy / ducts / pipes
│   ├── _project_validation.py      # Mixin: validate*
│   │
│   ├── catalogs/               # Справочники
│   │   ├── climate.py              # БД климата 85 городов
│   │   ├── room_types.py           # Типы помещений + авто-детект
│   │   ├── constructions.py        # Каталог конструкций
│   │   ├── construction_presets.py # Готовые конструкции (КМК / СП)
│   │   ├── materials.py            # Теплопроводности материалов
│   │   ├── smoke_norms.py          # СП 7 / КМК / NFPA 92 / Custom
│   │   ├── ventilation_norms.py    # СП 60 / СП 44 / СП 113
│   │   └── user_norms.py           # Пользовательские профили
│   │
│   ├── engine/                 # Strategy: расчётные движки
│   │   ├── base.py                 # ABC + реестр + air_density
│   │   ├── sp50.py                 # СП 50.13330 + СП 60.13330
│   │   └── ventilation.py          # Движок расчёта вентиляции
│   │
│   ├── ahu_load.py / ahu_process.py    # Нагрузки и психрометрия AHU
│   ├── psychro.py / psychro_chart.py   # Влажный воздух + i-d диаграмма
│   ├── duct_sizing.py / duct_network.py
│   │                           # Подбор сечений и аэродинамическая сеть
│   ├── pipe_sizing.py          # Гидравлика труб (Альтшуль)
│   ├── heating_hydraulics.py   # Подбор насосов и расширительных баков
│   ├── radiator_catalog.py / fancoil_catalog.py
│   │                           # Подбор радиаторов и фанкойлов
│   ├── underfloor.py / vrf.py  # Тёплый пол / VRF
│   ├── acoustics.py            # Акустический анализ AHU
│   ├── dew_point.py            # Проверка точки росы (СП 50 Прил. Е)
│   ├── dhw.py                  # ГВС (СП 30)
│   ├── energy.py               # Энергопаспорт (СП 50 Прил. Г, кВт·ч/(м²·год))
│   ├── energy_simulation.py    # 8760-часовая симуляция
│   ├── smoke.py / smoke_formulas.py
│   │                           # Дымоудаление и подпор воздуха
│   ├── specification.py        # Спецификация по ГОСТ 21.110
│   ├── templates.py            # Шаблоны помещений
│   ├── equipment.py            # Системы / контуры / зоны
│   ├── room_equipment.py       # Радиаторы / решётки в помещении
│   ├── sizing_helpers.py       # Подбор AHU/котла/чиллера
│   ├── reports.py              # Графики (Registry Pattern)
│   ├── i18n.py                 # Локализация (RU/UZ), live language switch
│   │
│   ├── io_excel.py             # Экспорт в 14-листовой Excel
│   ├── io_excel_equipment.py   # Лист спецификации
│   ├── io_pdf.py               # Пояснительная записка PDF
│   ├── io_json.py              # Сохранение/загрузка проекта
│   ├── io_revit.py             # CSV обратно в Revit
│   ├── io_hlgc.py              # Импорт/экспорт HLGC-таблиц
│   │
│   ├── cli.py                  # Командный режим
│   ├── ui_qt/                  # GUI на PySide6
│   │   ├── app.py                  # QApplication + run_gui()
│   │   ├── main_window.py          # Главное окно + sidebar + topbar
│   │   ├── bridge.py               # ProjectBridge: модель ↔ UI
│   │   ├── commands.py             # Командная палитра (Ctrl+K)
│   │   ├── export_center.py        # Единое окно экспорта
│   │   ├── settings.py             # Тема, autosave, recent files
│   │   ├── panels/                 # 16 функциональных панелей
│   │   ├── widgets/                # Карточки, чек-лист, sidebar, диалоги
│   │   └── theme/                  # dark.qss / light.qss
│   └── ui.legacy/              # Старый Tkinter-UI (не используется)
│
├── tests/                      # 607 unit-тестов
├── revit_dynamo_*.py           # Скрипты Dynamo для Revit
└── resources/                  # Иконки
```

## Применённые паттерны

### 1. Strategy Pattern (расчётные движки)

```python
class CalculationEngine(ABC):
    @abstractmethod
    def heat_loss(self, space, project) -> dict: ...

@register_engine
class SP50Engine(CalculationEngine):
    name = "СП 50.13330 + СП 60.13330"
    def heat_loss(self, space, project):
        ...
```

**Добавить новую методику** = создать класс в `hvac/engine/новая.py`,
импортировать в `hvac/engine/__init__.py`. UI автоматически покажет её
в выпадающем списке методик.

### 2. Registry Pattern (графики)

```python
@register_chart("Топ-20 по теплопотерям")
def chart_top_loss(project, fig):
    ax = fig.add_subplot(111)
    ...
```

**Добавить новый график** = функция с декоратором.

### 3. Event Bus (модель ↔ UI)

```python
project.subscribe("data_loaded", refresh_constructions)
project.subscribe("calculation_done", refresh_results)
project.emit("data_loaded")
```

События проекта: `project_loaded`, `data_loaded`, `spaces_changed`,
`elements_changed`, `constructions_changed`, `calculation_done`,
`ventilation_done`, `zones_changed`, `ahu_loads_calculated`,
`equipment_changed`. UI-панели подписываются и автоматически
обновляются — никаких прямых вызовов между панелями.

Исключения в подписчиках логируются через `traceback.print_exc()` и
**не пробрасываются** — UI-баг не должен крашить расчёт.

### 4. Mixin-композиция HVACProject

Чтобы не раздувать один файл, функциональность разбита по миксинам:

| Mixin                     | Файл                              | Что добавляет                            |
|---------------------------|-----------------------------------|------------------------------------------|
| `ManualEntryMixin`        | `_project_manual_entry.py`        | `add_space`, `add_element`, импорт CSV   |
| `SmokeSystemsMixin`       | `_project_smoke.py`               | СДУ / СПВ                                |
| `V37ExtensionsMixin`      | `_project_extensions.py`          | DHW / energy / ducts / pipes             |
| `ValidationMixin`         | `_project_validation.py`          | `validate*` методы                       |

### 5. Ленивый индекс elements_by_space

Расчётные движки (`engine/sp50.py`, `engine/ventilation.py`,
`ahu_load.py`) для каждого помещения отбирают его ограждения.
Раньше это был линейный скан всех `project.elements` для каждого
помещения — O(N·M). Сейчас `HVACProject` держит ленивый индекс
`{space_id: [elements]}`. Точки инвалидации:

- `project.load()` — массовая замена elements
- `ManualEntryMixin.add_element / remove_element / remove_space / duplicate_space`
- `io_json.load_project` после self-contained восстановления

Использовать вместо явной фильтрации:

```python
# Было:
elems = [e for e in project.elements
         if e.space_id == space.space_id and e.is_exterior]

# Стало:
elems = [e for e in project.elements_for(space.space_id) if e.is_exterior]
```

### 6. Единая точка сброса состояния

Все коллекции расчётных артефактов (`ventilation_systems`,
`heating_circuits`, `ahu_loads`, `radiator_picks`, …) создаются
в одном методе `HVACProject._reset_runtime_state()`. И `__init__`,
и `new_empty_project` вызывают его. Добавление нового поля состояния
правится в одном файле — без риска забыть сбросить его в другом
месте.

## Маршрут добавления новой функции

### Новая методика (например EN 12831)

1. `hvac/engine/en12831.py`:
   ```python
   from hvac.engine.base import CalculationEngine, register_engine

   @register_engine
   class EN12831Engine(CalculationEngine):
       @property
       def name(self): return "EN 12831 (Европа)"
       def heat_loss(self, space, project): ...
       def heat_gain(self, space, project): ...
   ```

2. В `hvac/engine/__init__.py` добавить `from hvac.engine import en12831  # noqa`.

3. UI на вкладке «Параметры» сам подхватит методику из реестра.

### Новый график

```python
# В hvac/reports.py:
@register_chart("Карта помещений (цветовая шкала)")
def chart_floor_map(project, fig):
    ax = fig.add_subplot(111)
    ...
```

В UI на панели «Графики» новый пункт появится автоматически.

### Новая Qt-панель

1. `hvac/ui_qt/panels/my_panel.py`:
   ```python
   from PySide6.QtWidgets import QWidget, QVBoxLayout

   class MyPanel(QWidget):
       def __init__(self, bridge):
           super().__init__()
           self.bridge = bridge
           self._build()
           bridge.project.subscribe("calculation_done", self._refresh)
       def _build(self): ...
       def _refresh(self, **_): ...
   ```

2. Зарегистрировать в sidebar (`hvac/ui_qt/main_window.py`).

### Использовать ядро без GUI

```python
from hvac import HVACProject
from hvac.io_excel import export_to_excel
from hvac.io_pdf  import export_to_pdf

p = HVACProject()
p.params.apply_city("Ташкент")
p.load("spaces.csv", "thermal.csv")
p.recalculate()
p.calculate_ventilation()
p.auto_assign_zones()
p.calculate_ahu_loads()

# Расширения v3.7
p.check_condensation_risk()
p.calculate_dhw(strategy="by_type")
p.calculate_energy_passport()
p.size_ducts(shape="round")
p.size_pipes(pipe_material="steel")

export_to_excel(p, "report.xlsx")
export_to_pdf(p, "report.pdf")
```

## Метрики (на момент v4.0)

| Аспект                       | Значение                          |
|------------------------------|-----------------------------------|
| Файлов Python в `hvac/`      | ~99                               |
| Unit-тестов                  | 607                               |
| Расчётных движков            | SP50Engine + VentilationEngine    |
| Excel-листов                 | 14                                |
| Qt-панелей                   | 16                                |
| Поддерживаемые нормативы     | СП 50/60/7/30/44/113/131, КМК UZ, NFPA 92 |

## Дальнейшие улучшения

- **YAML/JSON-каталоги** — внешние редактируемые файлы для
  `ROOM_TYPE_PRESETS` и `CLIMATE_DB`.
- **Логирование через `logging`** — настраиваемые уровни,
  единый формат, файл-приёмник.
- **CI/CD** — GitHub Actions, прогон тестов на каждый push.
- **mypy / pyright** — статическая типизация ядра.
- **Локализация** — UI полностью покрыт RU/UZ через `hvac/i18n.py`
  (~700 ключей, live retranslate через `on_language_change`).
  Защитный тест `tests/test_no_hardcoded_strings.py` ловит
  непереведённые UI-литералы. Дальше: вынести словари в
  `hvac/i18n/*.yaml`, при необходимости добавить EN.
- **strict-режим event bus** — флаг для проброса исключений
  подписчиков (упростит диагностику UI-багов).
