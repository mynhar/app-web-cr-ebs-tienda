# Operación — Actualización automática de la tienda

Guía rápida para operar y resolver problemas de la actualización de precios y stock
de la tienda (`index.html`) desde Intcomex. Para el detalle técnico, ver
[scraper/README.md](scraper/README.md).

## Qué hace, en una línea

Todos los días a las **06:00**, una tarea de Windows refresca el **costo** y el
**stock** de los 706 productos desde el portal de Intcomex y publica el resultado en
**GitHub Pages**. No hay que hacer nada salvo cuando expira la sesión de Intcomex.

## Flujo automático

```
Tarea diaria 06:00 ─► run_scrape.ps1 ─► scrape_intcomex.py (refresca 706 productos)
                                              └─► git commit + push de index.html ─► GitHub Pages
```

- Carpeta de trabajo: `c:\mi-sitio-web\app-web-cr-ebs-tienda\scraper`
- Python del entorno: `scraper\.venv\Scripts\python.exe`
- Logs de cada corrida: `scraper\logs\scrape_AAAAMMDD_HHMMSS.log`

---

## Tareas comunes

### Verificar que la última corrida salió bien
Abrí el log más reciente en `scraper\logs\` y buscá al final:
- `index.html actualizado: N productos` → el refresco funcionó.
- `== Publicado: ... ==` → se subió a GitHub Pages.

### Correr la actualización ahora (manual)
```powershell
Start-ScheduledTask -TaskName "EBS - Actualizar tienda Intcomex"
```
O directamente, viendo la salida en pantalla:
```powershell
cd c:\mi-sitio-web\app-web-cr-ebs-tienda\scraper
powershell -ExecutionPolicy Bypass -File .\run_scrape.ps1
```

### Ver estado / próxima ejecución de la tarea
```powershell
Get-ScheduledTask -TaskName "EBS - Actualizar tienda Intcomex" | Get-ScheduledTaskInfo
```

### Cambiar la hora de ejecución
Editá `$Hora` en `scraper\registrar_tarea.ps1` y volvé a correr:
```powershell
powershell -ExecutionPolicy Bypass -File .\registrar_tarea.ps1
```

---

## Resolución de problemas

### El log dice "La sesión expiró"
La cookie de Intcomex caducó (pasa cada varias semanas). Renovala una vez:
```powershell
cd c:\mi-sitio-web\app-web-cr-ebs-tienda\scraper
.\.venv\Scripts\python.exe scrape_intcomex.py --login
```
Iniciá sesión en el navegador, cerrá el inspector y listo: vuelve a quedar automático.

### Muchos productos con "Sin datos" / fallos
Suele ser la sesión a punto de expirar o un cambio en el sitio de Intcomex.
1. Renová la sesión (`--login`, ver arriba).
2. Validá un producto: `.\.venv\Scripts\python.exe scrape_intcomex.py --probe 510852`
   - Debe imprimir `costo: 0.72   stock: 17` (o el stock del día).
   - Si da `None`, Intcomex cambió el HTML: hay que ajustar los selectores en
     `scrape_intcomex.py` (función `extract`, selectores `.linkArea .font-price` y
     `.js-product-item-stock-<recno>`). El probe guarda el HTML en `scraper\recon\`
     para inspeccionarlo.

### El precio se ve mal en la tienda (todos iguales o disparados)
El portal entrega el **costo de socio** y la tienda calcula el precio final
`costo × 1.469` (margen 30% + IVA 13%). Si algo se ve raro, revisá `productos.json`
(último extracto por producto) para ver qué costo se leyó.

### El push a GitHub falló (credenciales)
El log mostrará un error de `git push`. Renová las credenciales con un push manual:
```powershell
cd c:\mi-sitio-web\app-web-cr-ebs-tienda
git push origin main
```
Si pide usuario/clave, completalo una vez (Git Credential Manager lo recuerda).

### Los cambios no aparecen en el sitio
1. Confirmá que el commit se subió: `git -C c:\mi-sitio-web\app-web-cr-ebs-tienda log --oneline -3`
2. GitHub Pages tarda 1–2 minutos en publicar tras el push.
3. Forzá recarga sin caché en el navegador (Ctrl+F5).

---

## Cosas que NO hay que tocar

- `index.html` se reescribe solo (el bloque `<script id="catalog">`). No editar a mano.
- `scraper\.env` y `scraper\storage_state.json` tienen credenciales/sesión: nunca se
  suben al repo (están en `.gitignore`).

## Resumen de mantenimiento

| Cada cuánto | Qué hacer |
|---|---|
| Diario | Nada (corre solo). |
| Cada varias semanas | Renovar sesión con `--login` cuando el log lo pida. |
| Si Intcomex rediseña el sitio | Ajustar selectores en `scrape_intcomex.py`. |
