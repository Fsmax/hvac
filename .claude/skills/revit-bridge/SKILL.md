---
name: revit-bridge
description: Протокол работы с живым Revit через сокет-мост hvac.revit_link — отправка C#, батчи, транзакции, откат. Использовать при любой задаче, где надо прочитать или изменить открытую модель Revit (марки, спейсы, воздуховоды, трубы, параметры, виды, цветовые схемы), а также при написании разовых скриптов в D:\Nurbek\_extract.
---

# Мост в живой Revit

## Запуск

Мост требует **C:\Python314**, не `.venv` проекта (venv пакета `hvac-mcp` сломан):

```python
import sys; sys.path.insert(0, r"D:\HVAC")
from hvac import revit_link as rl
assert rl.ping()          # False → Revit закрыт или выключен 'Revit MCP Switch'
```

Транспорт: JSON-RPC по сокету `127.0.0.1:8080`. RevitCortex-форк — отдельный
сервер на `8081`, для авторинга семейств (`.rfa`), к этому мосту отношения не имеет.

## Три жёстких ограничения

1. **Буфер запроса 8 КБ.** `send_code` минифицирует C# (снимает отступы,
   пустые строки, строки-комментарии), но длинный код всё равно не влезет.
   Не генерируй простыни — выноси данные в `parameters`, а не в тело кода.
2. **У плагина есть exec-timeout.** Массовую операцию режь на батчи
   **~20 элементов** на вызов. Больше — обрыв в середине.
3. **Одна транзакция за вызов.** Обрыв на середине батча оставляет уже
   применённое в модели. Отката средствами Revit нет — `.rvt` не под git.

Из (2)+(3) следует основной паттерн: цикл по батчам на стороне Python,
после каждого успешного батча — дозапись id в файл отката.

## Шаблон записи

```python
import json, pathlib
OUT = pathlib.Path(r"D:\Nurbek\_extract\<задача>_ids.json")
done = json.loads(OUT.read_text()) if OUT.exists() else []

CS = """
var ids = new List<string>();
foreach (var raw in parameters) {
    var id = new ElementId(Convert.ToInt64(raw));
    var el = document.GetElement(id);
    // ... правка ...
    ids.Add(el.Id.ToString());
}
return Newtonsoft.Json.JsonConvert.SerializeObject(ids);
"""

for i in range(0, len(targets), 20):
    batch = [str(x) for x in targets[i:i+20]]
    got = rl.send_code(CS, parameters=batch, timeout=180)
    done += got
    OUT.write_text(json.dumps(done))     # откат пишем ПОСЛЕ каждого батча
    print(i, len(done))
```

Чтение — то же самое, но `transaction_mode="none"` и без файла отката.

## Ловушки, проверенные на этих моделях

- `"Failed to create command instance"` в логе Revit — **это успех**.
  Сообщение мислейбл, не считать ошибкой и не повторять вызов.
- Коллектор по активному виду возвращает 0 для неоткрытых видов —
  фильтруй по `LevelId`/`OwnerViewId`, а не по активному виду.
- Пустой план ≠ пустая модель: причиной был повреждённый гигантский CropBox.
  Лечится сбросом экстентов по уровню.
- Повернуть план = повернуть элемент `view.Id + 2`. Сам вид, CropBox и
  ExtentElem — no-op. Проверяй ShapeSet: косой пользовательский контур
  за поворотом не едет.
- Встроенный `occupancy` у Space — read-only. Пиши в свои параметры.
- `aec:number` — ватты как есть, **не** умножать на 10.764.
- Меток (labels) в API нет. Чтобы изменить текст марки — правка семейства
  в UI + `ChangeTypeId` на существующих марках.
- Link Connectors в API отсутствуют — соединять через собственное семейство.
- Сироты после массовой операции ловятся XY-пробой по координатам.

## Что сделано ранее — переиспользуй, не переизобретай

`hvac/revit_link.py` уже содержит готовые операции: `import_from_revit`,
`write_results_to_revit`, `snapshot_spaces`, `diff_with_project`,
`color_spaces_in_revit`, `tag_wall_exterior`, `detect_roof_spaces`,
`probe_facades`, `snapshot_equipment`, `check_revit_params`.
Прежде чем писать новый C#, проверь, нет ли нужного тут.

Разовые скрипты по объектам — `D:\Nurbek\_extract\` (chorsu_*, blockc_tags/…),
там же лежат их файлы отката.
