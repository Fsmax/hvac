"""PostToolUse-хук: прогон тестов, относящихся к только что изменённому модулю.

На stdin приходит JSON вызова инструмента. Если правился файл `hvac/<name>.py`,
ищем `tests/test_<name>.py` и гоняем его. Падение теста возвращается модели
через additionalContext — правка при этом не откатывается, просто становится
видно, что она сломала.

Молчим, если: правился не файл пакета, теста для модуля нет, тесты прошли.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = r"C:\Python314\python.exe"
TIMEOUT = 120


def main() -> None:
    # вывод читает Claude Code, а не консоль Windows — принудительно UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    raw = (payload.get("tool_input", {}).get("file_path")
           or payload.get("tool_response", {}).get("filePath"))
    if not raw:
        return

    path = Path(raw)
    if path.suffix != ".py":
        return

    parts = [p.lower() for p in path.parts]
    if "hvac" not in parts:
        return
    # интересует только пакет D:\HVAC\hvac\..., не сам каталог проекта
    if parts.count("hvac") < 2 and path.parent.name.lower() != "hvac":
        return

    test = ROOT / "tests" / f"test_{path.stem}.py"
    if not test.exists():
        return

    try:
        res = subprocess.run(
            [PYTHON, "-m", "pytest", str(test), "-q", "--no-header"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=TIMEOUT,
            # окружение наследуем целиком: pytest и часть зависимостей стоят
            # в user site-packages (%APPDATA%\Python\Python314), обрезанный env
            # их не видит — "No module named pytest"
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                 "QT_QPA_PLATFORM": "offscreen"},
        )
    except Exception:
        return

    if res.returncode == 0:
        return

    tail = "\n".join((res.stdout or res.stderr).strip().splitlines()[-25:])
    print(json.dumps({
        "systemMessage": f"Тесты {test.name} упали после правки",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"Правка {path.name} уронила {test.name}. "
                f"Почини до перехода к следующему шагу.\n\n{tail}"
            ),
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
