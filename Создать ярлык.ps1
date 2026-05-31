# ============================================================
#  Создаёт ярлык "HVAC Calculator" на рабочем столе
#  Запуск:
#    1. Правой кнопкой на этом файле → "Выполнить с PowerShell"
#    либо
#    2. В PowerShell:  .\Создать ярлык.ps1
# ============================================================

# Корень проекта = папка, где лежит этот скрипт
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Пути
$BatFile     = Join-Path $ProjectRoot "HVAC.bat"
$Desktop     = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "HVAC Calculator.lnk"

# Проверка что .bat существует
if (-not (Test-Path $BatFile)) {
    Write-Host "Ошибка: не найден $BatFile" -ForegroundColor Red
    Write-Host "Положите этот .ps1 в ту же папку, где лежит HVAC.bat" -ForegroundColor Yellow
    pause
    exit 1
}

# Найдём pythonw.exe для иконки (стандартная python-иконка лучше cmd-иконки)
$PythonwPath = ""
try {
    $cmd = Get-Command pythonw.exe -ErrorAction Stop
    $PythonwPath = $cmd.Source
} catch {
    try {
        $cmd = Get-Command python.exe -ErrorAction Stop
        $PythonwPath = $cmd.Source
    } catch {}
}

# Создаём ярлык через COM-объект WScript.Shell
$WScript = New-Object -ComObject WScript.Shell
$Shortcut = $WScript.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = $BatFile
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description      = "HVAC Calculator - расчёт ОВиК (теплопотери, вентиляция, гидравлика)"
$Shortcut.WindowStyle      = 7   # 7 = свернуть консоль bat-файла

# Иконка: пробуем python.exe, если есть; иначе дефолтная
if ($PythonwPath -and (Test-Path $PythonwPath)) {
    $Shortcut.IconLocation = "$PythonwPath,0"
}

$Shortcut.Save()

Write-Host ""
Write-Host "Ярлык создан: $ShortcutPath" -ForegroundColor Green
Write-Host ""
Write-Host "Можете запускать программу с рабочего стола двойным кликом." -ForegroundColor Cyan
Write-Host ""
pause
