# Регистрация автозапуска JARVIS в Планировщике задач Windows.
#
# Запускать вручную, от имени владелицы (не от администратора):
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
# Удалить автозапуск:
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Remove
#
# Задача стартует start.bat при входе владелицы в Windows и перезапускает его,
# если бот упал. Скрипт ничего не запускает сам — только регистрирует задачу.

[CmdletBinding()]
param(
    [string]$TaskName = "JARVIS",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$start = Join-Path $root "start.bat"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Задача '$TaskName' удалена — автозапуск выключен."
    } else {
        Write-Host "Задачи '$TaskName' нет — удалять нечего."
    }
    return
}

if (-not (Test-Path $start)) {
    throw "Не найден $start — запусти скрипт из папки проекта JARVIS."
}
if (-not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    Write-Warning "Нет .venv — сначала создай окружение, иначе задача будет падать при старте."
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$start`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Личный агент JARVIS: Telegram-бот и Approvals API" | Out-Null

Write-Host "Задача '$TaskName' зарегистрирована: JARVIS стартует при входе в Windows."
Write-Host "Проверить:  Get-ScheduledTask -TaskName $TaskName"
Write-Host "Запустить сейчас:  Start-ScheduledTask -TaskName $TaskName"
