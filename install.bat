@echo off
REM ============================================================
REM  HVAC Calculator - установка зависимостей
REM  Двойной клик - установит всё необходимое для запуска.
REM ============================================================

cd /d "%~dp0"

echo.
echo === Проверка Python ===
python --version
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Python не найден в PATH.
    echo Скачайте Python 3.11+ с https://www.python.org/downloads/
    echo При установке поставьте галочку "Add Python to PATH".
    pause
    exit /b 1
)

echo.
echo === Обновление pip ===
python -m pip install --upgrade pip

echo.
echo === Установка зависимостей из requirements.txt ===
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

echo.
echo === Проверка импорта ===
python -c "import PySide6, matplotlib, openpyxl, reportlab; print('OK: все модули загружаются')"
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Один из модулей не импортируется.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Установка завершена. Запуск программы: HVAC.bat
echo ============================================================
pause
