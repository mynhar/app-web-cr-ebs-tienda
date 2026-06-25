#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extractor Intcomex -> tienda (Etapa 3/4).

Refresca PRECIO (costo de socio) y STOCK de los 706 productos ya embebidos en
../index.html, consultando cada producto por su `recno` en su página de detalle,
y reescribe el bloque <script id="catalog"> de la tienda.

IMPORTANTE sobre el precio:
    El portal de Intcomex muestra el COSTO de socio directamente (ej. "$ 0.72").
    La tienda (index.html) recalcula el precio final = costo * 1.469 (margen 30% + IVA 13%).
    Por eso aquí guardamos el costo TAL CUAL lo da el portal (sin dividir por 1.469).
    (Esto difiere de actualizar_datos.py, que parte de un catálogo con precios finales.)

LOGIN (captcha):
    El login del portal tiene captcha, así que NO se automatiza el formulario.
    En su lugar se guarda la sesión tras un login manual y se reutiliza:

        python scrape_intcomex.py --login     # 1 vez (o cuando la sesión expire)
        python scrape_intcomex.py --probe 510852   # validar 1 detalle (opcional)
        python scrape_intcomex.py --limit 5   # prueba rápida con 5 productos
        python scrape_intcomex.py             # corrida completa (706)

La sesión se guarda en  storage_state.json  (en .gitignore, no se sube).
"""
import os
import re
import sys
import json
import time
import argparse
from dotenv import load_dotenv

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Falta Playwright. Corré:  pip install -r requirements.txt  &&  python -m playwright install chromium")

HERE = os.path.dirname(os.path.abspath(__file__))
RECON = os.path.join(HERE, "recon")
STATE = os.path.join(HERE, "storage_state.json")
INDEX = os.path.normpath(os.path.join(HERE, "..", "index.html"))
RESULTS = os.path.join(HERE, "productos.json")

load_dotenv(os.path.join(HERE, ".env"))
BASE = "https://store.intcomex.com"
HOME = os.getenv("INTCOMEX_BASE", BASE + "/es-XCR/Home")
DETAIL = BASE + "/es-XCR/Product/Detail/{recno}"
SEARCH = BASE + "/es-XCR/Products/ByKeyword?term={sku}"

# Índices de columna en cada fila del catálogo embebido (ver actualizar_datos.build_data)
COL_TITLE, COL_SKU, COL_COST, COL_STOCK, COL_DID = 2, 3, 5, 6, 8


# --------------------------------------------------------------------------- #
#  Catálogo embebido en index.html
# --------------------------------------------------------------------------- #
def read_catalog(path=INDEX):
    html = open(path, encoding="utf-8").read()
    m = re.search(r'<script id="catalog" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        sys.exit("No se encontró el bloque <script id=\"catalog\"> en " + path)
    return html, json.loads(m.group(1))


def write_catalog(html, data, path=INDEX):
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    new_html, n = re.subn(
        r'(<script id="catalog" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + blob + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit("No se pudo reescribir el bloque <script id=\"catalog\">.")
    open(path, "w", encoding="utf-8").write(new_html)
    return len(blob.encode("utf-8"))


# --------------------------------------------------------------------------- #
#  Extracción de precio + stock de una página de producto
# --------------------------------------------------------------------------- #
def parse_price(text):
    """'$ 0.72' / 'US$ 1,234.50' -> 0.72 / 1234.5 ; '' si no se reconoce."""
    m = re.search(r"\$\s*([0-9][0-9.,]*)", text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        return round(float(raw), 4)
    except ValueError:
        return None


def parse_stock(text):
    """Suma todas las cantidades tipo 'N en <localidad>' que aparezcan en el texto."""
    nums = re.findall(r"(\d+)\s+en\s+", text)
    if nums:
        return sum(int(n) for n in nums)
    return None


def extract(page, recno):
    """Devuelve (cost, stock) del producto PRINCIPAL de la página de detalle.

    La página de detalle trae además productos destacados y relacionados, cada uno
    con su propio `.font-price` y su propio stock. Por eso apuntamos a selectores
    específicos del producto principal:
      - precio: dentro de `.linkArea` (el panel de compra; aparece una sola vez).
      - stock:  span `js-product-item-stock-<recno>` (clavado al recno del producto).
    """
    cost = stock = None

    # Precio del producto principal: <div class="...font-price"><b>$ 0.72</b></div> dentro de .linkArea
    el = page.query_selector(".linkArea .font-price")
    if el:
        cost = parse_price(el.inner_text())

    # Stock del producto principal: span específico por recno -> "17 en La Uruca."
    se = page.query_selector(".js-product-item-stock-%s" % recno)
    if se:
        txt = se.inner_text() or ""
        stock = parse_stock(txt)
        if stock is None:
            stock = 0  # span presente sin número => sin stock local

    # Producto sin precio/disponibilidad para la cuenta (descontinuado o fuera de
    # catálogo): el portal muestra "Ingrese para ver precio y disponibilidad".
    # Lo marcamos AGOTADO (stock 0) para no mostrar disponibilidad engañosa; el
    # costo se deja como estaba (cost=None => no se sobrescribe).
    if cost is None and stock is None:
        if "Ingrese para ver precio" in (page.query_selector(".linkArea").inner_text()
                                         if page.query_selector(".linkArea") else ""):
            stock = 0

    return cost, stock


# --------------------------------------------------------------------------- #
#  Navegador / sesión
# --------------------------------------------------------------------------- #
def make_context(p, headful=False):
    if not os.path.exists(STATE):
        sys.exit("No hay sesión guardada. Corré primero:  python scrape_intcomex.py --login")
    browser = p.chromium.launch(headless=not headful)
    ctx = browser.new_context(storage_state=STATE, locale="es-CR",
                              viewport={"width": 1366, "height": 900})
    return browser, ctx


def is_logged_out(page):
    """Detecta expiración de sesión (redirección al login)."""
    return "/Account/Login" in page.url or "/AccountAjax/SignIn" in page.url


# --------------------------------------------------------------------------- #
#  Modos
# --------------------------------------------------------------------------- #
def do_login():
    """Abre el navegador para login manual y guarda la sesión."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(locale="es-CR", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        print("\n>> Iniciá sesión MANUALMENTE en la ventana del navegador.")
        print(">> Cuando estés dentro (ya logueado), cerrá el inspector para guardar la sesión.\n")
        page.pause()
        ctx.storage_state(path=STATE)
        browser.close()
    print("Sesión guardada en:", STATE)


def do_probe(recno):
    """Vuelca el HTML+captura de una página de detalle para validar selectores."""
    os.makedirs(RECON, exist_ok=True)
    with sync_playwright() as p:
        browser, ctx = make_context(p, headful=True)
        page = ctx.new_page()
        url = DETAIL.format(recno=recno)
        print("Abriendo:", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        if is_logged_out(page):
            sys.exit("La sesión expiró. Corré:  python scrape_intcomex.py --login")
        open(os.path.join(RECON, f"detalle_{recno}.html"), "w", encoding="utf-8").write(page.content())
        page.screenshot(path=os.path.join(RECON, f"detalle_{recno}.png"), full_page=True)
        cost, stock = extract(page, recno)
        print(f"Extraído -> costo: {cost}   stock: {stock}")
        print(f"Guardado: scraper/recon/detalle_{recno}.html / .png")
        browser.close()


def do_refresh(limit=None, headful=False, delay=0.6):
    html, data = read_catalog()
    rows = data["rows"]
    targets = [(i, r) for i, r in enumerate(rows) if r[COL_DID]]
    if limit:
        targets = targets[:limit]
    print(f"Productos a refrescar: {len(targets)} (de {len(rows)} totales)")

    updated, failed, results = 0, [], []
    with sync_playwright() as p:
        browser, ctx = make_context(p, headful=headful)
        page = ctx.new_page()
        for n, (i, r) in enumerate(targets, 1):
            recno, sku = r[COL_DID], r[COL_SKU]
            try:
                page.goto(DETAIL.format(recno=recno), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(400)
                if is_logged_out(page):
                    print("\n!! La sesión expiró. Guardá de nuevo con --login y reintentá.")
                    break
                cost, stock = extract(page, recno)
                if cost is not None:
                    r[COL_COST] = cost
                if stock is not None:
                    r[COL_STOCK] = stock
                if cost is not None or stock is not None:
                    updated += 1
                else:
                    failed.append((recno, sku))
                results.append({"recno": recno, "sku": sku, "cost": cost, "stock": stock})
            except Exception as e:
                failed.append((recno, sku))
                results.append({"recno": recno, "sku": sku, "error": str(e)[:120]})
            if n % 25 == 0 or n == len(targets):
                print(f"  {n}/{len(targets)}  (ok: {updated}, fallos: {len(failed)})")
            time.sleep(delay)
        browser.close()

    json.dump(results, open(RESULTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if updated:
        size = write_catalog(html, data)
        print(f"\nindex.html actualizado: {updated} productos ({size} bytes de datos).")
    else:
        print("\nNo se actualizó ningún producto; index.html quedó intacto.")
    if failed:
        print(f"Sin datos en {len(failed)} productos (ver productos.json). Ejemplos:",
              ", ".join(f"{rc}/{sk}" for rc, sk in failed[:5]))


def main():
    ap = argparse.ArgumentParser(description="Refresca precio/stock de la tienda desde Intcomex.")
    ap.add_argument("--login", action="store_true", help="Login manual y guardar sesión")
    ap.add_argument("--probe", metavar="RECNO", help="Volcar 1 página de detalle y validar selectores")
    ap.add_argument("--limit", type=int, help="Refrescar solo los primeros N productos (prueba)")
    ap.add_argument("--headful", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--delay", type=float, default=0.6, help="Segundos de espera entre productos")
    a = ap.parse_args()

    if a.login:
        do_login()
    elif a.probe:
        do_probe(a.probe)
    else:
        do_refresh(limit=a.limit, headful=a.headful, delay=a.delay)


if __name__ == "__main__":
    main()
