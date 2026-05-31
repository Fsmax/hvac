@echo off
REM ============================================================
REM  HVAC Calculator — запуск GUI
REM  Двойной клик → откроется главное окно программы.
REM  Чёрная консоль не показывается (pythonw.exe).
REM ============================================================

REM Переход в папку, где лежит этот .bat (поддерживает запуск через ярлык)
cd /d "%~dp0"

REM Запускаем GUI через pythonw (без консоли)
start "" pythonw.exe hvac_calc.py

REM Если pythonw не найден, fallback на python
if errorlevel 9009 (
    echo pythonw.exe не найден, запускаем через python.exe
    start "" python.exe hvac_calc.py
)
