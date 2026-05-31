@echo off
REM ============================================================
REM  HVAC Calculator — командный режим
REM  Использование:
REM    HVAC_cli.bat spaces.csv thermal.csv result.xlsx [-tхол] [-tтепл] [город]
REM
REM  Пример:
REM    HVAC_cli.bat D:\HVAC\spaces.csv D:\HVAC\thermal.csv result.xlsx -16 36 "Ташкент"
REM ============================================================

cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo HVAC Calculator - командный режим
    echo.
    echo Использование:
    echo    HVAC_cli.bat ^<spaces.csv^> ^<thermal.csv^> ^<result.xlsx^> [t_хол] [t_тепл] [город]
    echo.
    echo Для GUI используйте HVAC.bat
    echo.
    pause
    exit /b 1
)

python.exe hvac_calc.py cli %*
pause
