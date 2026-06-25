# registrar_tarea.ps1 — crea (o actualiza) la tarea programada de Windows que
# refresca precios/stock de la tienda todos los días.
#
# Ejecutar UNA vez, en una consola PowerShell NORMAL (no hace falta admin si la
# tarea corre solo con tu usuario):
#
#   powershell -ExecutionPolicy Bypass -File .\registrar_tarea.ps1
#
# Para cambiar la hora, editá $Hora abajo (formato 24h, ej. "03:30").

$Hora       = "06:00"
$NombreTarea = "EBS - Actualizar tienda Intcomex"

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $here "run_scrape.ps1"

if (-not (Test-Path $script)) { throw "No se encontró run_scrape.ps1 en $here" }

$accion  = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Hora
$config  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $NombreTarea -Action $accion -Trigger $trigger `
    -Settings $config -Description "Refresca costo y stock de index.html desde Intcomex." `
    -Force

Write-Host ""
Write-Host "Tarea registrada: '$NombreTarea'  (diaria a las $Hora)" -ForegroundColor Green
Write-Host "Probarla ya:   Start-ScheduledTask -TaskName '$NombreTarea'"
Write-Host "Ver estado:    Get-ScheduledTask -TaskName '$NombreTarea' | Get-ScheduledTaskInfo"
Write-Host "Quitarla:      Unregister-ScheduledTask -TaskName '$NombreTarea' -Confirm:`$false"
