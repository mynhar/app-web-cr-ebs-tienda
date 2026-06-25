# Scraper Intcomex → tienda

Automatiza la extracción de precios y stock desde el portal de socios de Intcomex
Costa Rica y alimenta `../actualizar_datos.py`, que reescribe los datos embebidos
en `../index.html`.

> ⚠️ El scraping depende del diseño actual del sitio de Intcomex. Si Intcomex cambia
> su HTML, hay que ajustar los selectores. Es mantenimiento normal de un scraper.

## Requisitos (una sola vez)

```powershell
cd scraper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Credenciales

1. Copiá `.env.example` como `.env` (en esta misma carpeta).
2. Completá `INTCOMEX_USER`, `INTCOMEX_PASS`, `INTCOMEX_CODE`.
3. El `.env` está en `.gitignore`: **nunca** se sube al repositorio.

## Etapa 2 — Reconocimiento (lo próximo a hacer)

La primera vez conviene ver el navegador y, si el login automático falla, hacerlo a mano:

```powershell
python recon_intcomex.py --headful        # intenta login automático
# o, para iniciar sesión manualmente y observar el sitio:
python recon_intcomex.py --headful --pause
```

Esto genera en `scraper/recon/`:
- `01_inicio`, `02_login_form`, `03_post_login` (HTML + capturas)
- `campos_detectados.txt` — inputs/botones detectados

**Compartí esos archivos** (sobre todo `campos_detectados.txt` y la captura
`03_post_login.png`) para construir el extractor real.

## Etapa 3/4 — Extractor (`scrape_intcomex.py`)

Refresca **precio (costo de socio)** y **stock** de los 706 productos ya embebidos
en `../index.html`, consultando cada uno por su `recno` en su página de detalle, y
reescribe el bloque `<script id="catalog">`. No re-crawlea toda la tienda: solo
actualiza los productos existentes, preservando categorías.

> **Login con captcha:** el portal pide captcha, así que el login NO se automatiza.
> Se hace login manual UNA vez y se guarda la sesión (`storage_state.json`), que se
> reutiliza en las corridas automáticas hasta que expire (ahí se repite el login).

Comandos (usando el Python del entorno):

```powershell
# 1) Login manual (1 vez, o cuando la sesión expire). Iniciá sesión y cerrá el inspector.
.\.venv\Scripts\python.exe scrape_intcomex.py --login

# 2) (Opcional) Validar la extracción en 1 producto. Usá un recno real de la tienda.
.\.venv\Scripts\python.exe scrape_intcomex.py --probe 510852

# 3) Prueba rápida con 5 productos antes de la corrida completa.
.\.venv\Scripts\python.exe scrape_intcomex.py --limit 5

# 4) Corrida completa (706 productos; tarda ~10-25 min).
.\.venv\Scripts\python.exe scrape_intcomex.py
```

Salidas:
- `../index.html` queda actualizado (costo + stock).
- `productos.json` — registro de lo extraído por producto (para depurar fallos).

## Etapa 5 — Tarea programada de Windows

Para que se actualice solo todos los días:

```powershell
# Registrar la tarea (1 vez). Por defecto corre diaria a las 06:00; editá $Hora en el script.
powershell -ExecutionPolicy Bypass -File .\registrar_tarea.ps1
```

- `run_scrape.ps1` — wrapper que corre el scrape y deja log en `scraper/logs/`.
- `registrar_tarea.ps1` — crea la tarea "EBS - Actualizar tienda Intcomex".

Comandos útiles:
```powershell
Start-ScheduledTask -TaskName "EBS - Actualizar tienda Intcomex"            # probarla ya
Get-ScheduledTask -TaskName "EBS - Actualizar tienda Intcomex" | Get-ScheduledTaskInfo  # estado
Unregister-ScheduledTask -TaskName "EBS - Actualizar tienda Intcomex" -Confirm:$false   # quitarla
```

> **Sesión:** la tarea corre desatendida mientras la cookie de Intcomex siga válida.
> Cuando expire, el log mostrará "La sesión expiró"; ahí volvés a correr
> `scrape_intcomex.py --login` a mano una vez y listo.

## Publicación automática (GitHub Pages)

Tras refrescar precios, `run_scrape.ps1` hace `commit` + `push` de `index.html` a
`origin/main`, y GitHub Pages publica los precios nuevos solo. Solo commitea
`index.html` (no toca otros archivos) y solo si hubo cambios.

> Requiere que git pueda autenticarse sin pedir contraseña (Git Credential Manager
> ya guardado, que es el caso). Si alguna vez el push falla por credenciales, el log
> lo mostrará y basta con hacer un `git push` manual una vez para renovarlas.
