# run_scrape.ps1 — corre el refresco de precios/stock y deja log.
# Pensado para el Programador de tareas de Windows (corrida desatendida).
#
# Uso manual:
#   powershell -ExecutionPolicy Bypass -File .\run_scrape.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = Join-Path $here ".venv\Scripts\python.exe"
$logs = Join-Path $here "logs"

# Corre git y registra su salida sin que PowerShell trate el stderr (que git
# usa para mensajes normales, ej. "To https://...") como error terminante.
# Devuelve el código de salida real de git.
function Invoke-Git {
    param([string[]]$Args, [string]$LogPath)
    & git @Args 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogPath -Append
    return $LASTEXITCODE
}

if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log   = Join-Path $logs "scrape_$stamp.log"

"== Inicio: $(Get-Date) ==" | Tee-Object -FilePath $log
& $py "-u" (Join-Path $here "scrape_intcomex.py") --crawl 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
"== Fin scrape: $(Get-Date)  (exit $code) ==" | Tee-Object -FilePath $log -Append

# --- Publicar en GitHub Pages: commit + push de index.html si cambió ---
$repo  = Split-Path -Parent $here          # raíz del repositorio (padre de scraper/)
$index = Join-Path $repo "index.html"
& git -C $repo diff --quiet -- $index
if ($LASTEXITCODE -ne 0) {
    "Cambios en index.html -> publicando en GitHub Pages..." | Tee-Object -FilePath $log -Append
    $fecha = Get-Date -Format "yyyy-MM-dd HH:mm"
    Invoke-Git -LogPath $log -Args @("-C", $repo, "add", "--", "index.html")                       | Out-Null
    Invoke-Git -LogPath $log -Args @("-C", $repo, "commit", "-m", "Actualizar precios y stock ($fecha)") | Out-Null
    $pushCode = Invoke-Git -LogPath $log -Args @("-C", $repo, "push", "origin", "main")
    if ($pushCode -eq 0) {
        "== Publicado: $(Get-Date) ==" | Tee-Object -FilePath $log -Append
    } else {
        "!! Fallo el push (git exit $pushCode); revisa la conexion/credenciales." | Tee-Object -FilePath $log -Append
    }
} else {
    "Sin cambios en index.html; no se publica nada." | Tee-Object -FilePath $log -Append
}

# Borra logs de más de 30 días
Get-ChildItem $logs -Filter "scrape_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
