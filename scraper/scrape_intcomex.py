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
import html as htmlmod
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


def inject_fx(fx, path=INDEX):
    """Escribe el tipo de cambio de Intcomex en la constante FX y en la nota del pie."""
    if not fx:
        return
    html = open(path, encoding="utf-8").read()
    html, n = re.subn(r'(var FX = )[0-9.]+(;)', lambda m: m.group(1) + str(fx) + m.group(2),
                      html, count=1)
    html = re.sub(r'(<span id="fxnote">)[^<]*(</span>)',
                  lambda m: m.group(1) + ("%.2f" % fx).replace(".", ",") + m.group(2),
                  html, count=1)
    open(path, "w", encoding="utf-8").write(html)
    if n != 1:
        print("Aviso: no se encontró 'var FX =' en index.html para actualizar.")


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


# --------------------------------------------------------------------------- #
#  Login automático (usuario+contraseña). En tu PC no hay captcha; si apareciera,
#  el robot lo detecta y te manda a hacer login manual (--login) una vez.
# --------------------------------------------------------------------------- #
LOGIN_URL = BASE + "/es-XCR/Account/Login"
IMG_BASE = BASE + "/images/products/"
FX = 456.0   # ₡ por US$ por defecto; se sobrescribe con el TC leído de Intcomex (scrape_fx)


def _logged_in(page):
    """¿La sesión quedó iniciada? Señales claras de la página privada (saludo / salir).
    OJO: NO mirar el captcha del chat en vivo (está oculto en todas las páginas)."""
    html = page.content()
    return bool(re.search(r"/Initial/Logout|Cerrar sesi|Bienvenido\b", html))


def scrape_fx(page):
    """Tipo de cambio del encabezado (lblTicker): 'US$1 = ₡459,01' -> 459.01.
    Toma el número DESPUÉS del '=' (no el '1' de 'US$1')."""
    m = re.search(r'id="lblTicker"[^>]*>(.*?)</span>', page.content(), re.S)
    if not m:
        return None
    n = re.search(r"=\s*\D*([0-9][0-9.,]*)", m.group(1))
    if not n:
        return None
    raw = n.group(1).replace(".", "").replace(",", ".")
    try:
        return round(float(raw), 4)
    except ValueError:
        return None


def auto_login(p, headful=False):
    """Inicia sesión escribiendo usuario/contraseña del .env y guarda la sesión."""
    user, pw, code = os.getenv("INTCOMEX_USER"), os.getenv("INTCOMEX_PASS"), os.getenv("INTCOMEX_CODE")
    if not user or not pw:
        sys.exit("Faltan INTCOMEX_USER / INTCOMEX_PASS en scraper/.env")
    browser = p.chromium.launch(headless=not headful)
    ctx = browser.new_context(locale="es-CR", viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)

    def fill_first(selectors, value):
        for sel in selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        return False

    fill_first(["input[type='email']", "input[name*='User' i]", "input[name*='Email' i]",
                "input[name*='Usuario' i]", "input[type='text']"], user)
    fill_first(["input[type='password']", "input[name*='Pass' i]"], pw)
    if code:
        fill_first(["input[name*='Code' i]", "input[name*='Codigo' i]", "input[name*='Partner' i]"], code)

    btn = page.query_selector("button[type='submit'], input[type='submit'], "
                              "button:has-text('Ingresar'), button:has-text('Iniciar')")
    if btn:
        btn.click()
    else:
        page.keyboard.press("Enter")
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(1500)

    if not _logged_in(page):
        os.makedirs(RECON, exist_ok=True)
        page.screenshot(path=os.path.join(RECON, "login_fallo.png"), full_page=True)
        open(os.path.join(RECON, "login_fallo.html"), "w", encoding="utf-8").write(page.content())
        browser.close()
        sys.exit("No se pudo iniciar sesión automáticamente. Revisá usuario/contraseña en .env "
                 "(o usá --login). Guardé recon/login_fallo.* para revisar.")
    ctx.storage_state(path=STATE)
    page.close()
    return browser, ctx


def get_context(p, headful=False):
    """Usa la sesión guardada si sigue válida; si no, hace login automático."""
    if os.path.exists(STATE):
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context(storage_state=STATE, locale="es-CR",
                                  viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        if not is_logged_out(page):
            page.close()
            return browser, ctx
        page.close(); browser.close()   # sesión expirada → re-login
    return auto_login(p, headful=headful)


# --------------------------------------------------------------------------- #
#  Recorrer TODO el catálogo (todas las categorías, todas las páginas)
# --------------------------------------------------------------------------- #
def discover_categories(page):
    """Códigos y nombres de categoría desde los enlaces del menú de la tienda."""
    page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    html = page.content()
    # categorías MAYORES: /Products/Category/cac?... title="Accesorios para Computadores"
    majors = {}
    for m in re.finditer(r'/Products/Category/([\w\-]+)\?[^"]*"\s+title="([^"]*)"', html):
        majors.setdefault(m.group(1), htmlmod.unescape(m.group(2)).strip())
    # SUBcategorías (hojas): /Products/ByCategory/cac.cable?... title="Cables"
    # Nombre final "Mayor - Sub"; el mayor sale del prefijo del código (cac.cable -> cac).
    cats = {}
    for m in re.finditer(r'/Products/ByCategory/([\w.\-]+)\?[^"]*"\s+title="([^"]*)"', html):
        code = m.group(1)
        sub = htmlmod.unescape(m.group(2)).strip()
        major = majors.get(code.split(".")[0], "")
        cats.setdefault(code, f"{major} - {sub}" if major else sub)
    for code in re.findall(r'/Products/ByCategory/([\w.\-]+)', html):
        cats.setdefault(code, code)
    return cats


def parse_listing(html):
    """Productos de la grilla de una categoría. Cada tarjeta es un bloque
    <div id="row_<recno>" ... data-recno="<recno>"> con data-sku, marca, precio y stock.
    Al cortar por ese bloque se ignora el carrusel lateral de 'Recientemente Vistos'."""
    out = []
    blocks = re.split(r'<div id="row_(\d+)"', html)  # [pre, recno, seg, recno, seg, ...]
    for i in range(1, len(blocks), 2):
        recno, seg = blocks[i], blocks[i + 1]
        price = re.search(r'font-price"><b>\$\s*([0-9.,]+)</b>', seg)
        sku = re.search(r'data-sku="([^"]*)"', seg)
        if not (price and sku):
            continue
        name = re.search(r'data-productname="([^"]*)"', seg) or re.search(r'class="product-name">\s*([^<]+?)\s*<', seg)
        brand = re.search(r'class="marca">\s*([^<]+?)\s*<', seg) or re.search(r'data-brand="([^"]*)"', seg)
        mpn = re.search(r'data-mpn="([^"]*)"', seg)
        img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', seg)
        # stock del local principal: span js-product-item-stock-<recno> -> "17 en La Uruca."
        stk = re.search(r'js-product-item-stock-%s"[^>]*>\s*([0-9.,]+)\s+en' % re.escape(recno), seg)
        out.append({
            "recno": recno,
            "sku": sku.group(1).strip(),
            "title": htmlmod.unescape(name.group(1)).strip() if name else "",
            "brand": htmlmod.unescape(brand.group(1)).strip() if brand else "",
            "mpn": mpn.group(1).strip() if mpn else "",
            "cost": float(price.group(1).replace(",", "")),
            "img": htmlmod.unescape(img.group(1).strip()) if img else "",
            "stock": int(stk.group(1).replace(",", "")) if stk else None,
        })
    return out


def _img_suffix(img):
    if img.startswith("/images/products/"):
        return img[len("/images/products/"):]
    if img.startswith("http"):
        return "|" + img
    if img.startswith("/"):
        return "|" + BASE + img
    return "|" + img if img else ""


def build_catalog(products):
    """Arma {cats, brands, rows} en el mismo formato que consume index.html."""
    cats, brands = [], []
    def idx(lst, v):
        if v not in lst:
            lst.append(v)
        return lst.index(v)
    rows = []
    for c in sorted(products, key=lambda x: (x.get("catname", ""), x.get("title", ""))):
        rows.append([
            idx(cats, c.get("catname", "")), idx(brands, c.get("brand", "")),
            c.get("title", ""), c.get("sku", ""), c.get("mpn", ""),
            c.get("cost", 0), c.get("stock") if c.get("stock") is not None else 0,
            _img_suffix(c.get("img", "")), c.get("recno", ""),
        ])
    return {"cats": cats, "brands": brands, "rows": rows}


def do_probe_cat(code, headful=True):
    """Vuelca 1 página de una categoría para validar estructura (stock, paginación)."""
    os.makedirs(RECON, exist_ok=True)
    with sync_playwright() as p:
        browser, ctx = get_context(p, headful=headful)
        page = ctx.new_page()
        url = "%s/es-XCR/Products/ByCategory/%s?r=True&p=1" % (BASE, code)
        print("Abriendo:", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector(".font-price, [data-productsku]", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        content = page.content()
        open(os.path.join(RECON, f"cat_{code}.html"), "w", encoding="utf-8").write(content)
        page.screenshot(path=os.path.join(RECON, f"cat_{code}.png"), full_page=True)
        cards = parse_listing(content)

        # --- diagnóstico (números, sin exponer costos) ---
        n_detail = len(re.findall(r"/Product/[Dd]etail/\d+", content))
        n_price = len(re.findall(r'font-price"><b>\$', content))
        n_sku = len(re.findall(r"Intcomex SKU:", content))
        con_stock = sum(1 for c in cards if c["stock"] is not None)
        n_grid = len(re.findall(r'<div id="row_\d+"', content))
        n_ingrese = len(re.findall(r"Ingrese para ver precio", content))
        print(f"Tarjetas de grilla (id=row_): {n_grid} | enlaces /detail: {n_detail} | precios: {n_price}")
        print(f"'Ingrese para ver precio': {n_ingrese} | parseados: {len(cards)} | con stock: {con_stock}")
        if n_ingrese and not n_price:
            print(">> La sesión NO tiene acceso a precios. Re-logueá: scrape_intcomex.py --auto-login")
        if cards:
            c = cards[0]   # sin imprimir el costo (dato sensible)
            print("Ejemplo -> SKU:", c["sku"], "| marca:", c["brand"], "| stock:", c["stock"])

        # Muestra CHICA y segura: recorta alrededor de la 1ª tarjeta de la grilla real.
        g = re.search(r'<div id="row_\d+"', content)
        pos = g.start() if g else 0
        zona = content[max(0, pos - 200):pos + 4500]
        zona = re.sub(r"<script[\s\S]*?</script>", "", zona)          # quita scripts
        zona = re.sub(r"\$\s*[0-9][0-9.,]*", "$ XX", zona)            # oculta costos
        zona = re.sub(r"\s+", " ", zona)
        open(os.path.join(RECON, f"cat_{code}_muestra.txt"), "w", encoding="utf-8").write(zona)
        print(f"Muestra para compartir: scraper/recon/cat_{code}_muestra.txt")
        browser.close()


def do_crawl(headful=False, delay=0.4, max_pages=300, limit_cats=None):
    global FX
    with sync_playwright() as p:
        browser, ctx = get_context(p, headful=headful)
        page = ctx.new_page()
        cats = discover_categories(page)
        fx = scrape_fx(page)            # tipo de cambio de Intcomex, en vivo
        if fx:
            FX = fx
        codes = list(cats)[:limit_cats] if limit_cats else list(cats)
        print(f"Categorías encontradas: {len(cats)}  | a recorrer: {len(codes)}  | TC Intcomex: {FX}")
        prods = {}
        for ci, code in enumerate(codes, 1):
            seen_cat = set()    # SKUs ya vistos en ESTA categoría
            for pg in range(1, max_pages + 1):
                url = "%s/es-XCR/Products/ByCategory/%s?r=True&p=%d" % (BASE, code, pg)
                # Carga resistente a fallos: una página lenta NO debe abortar todo el
                # crawl (perderíamos ~20 min y la corta ventana de sesión). Reintenta
                # una vez ante un error transitorio; si persiste, omite la categoría.
                try:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        page.wait_for_timeout(1500)
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    if is_logged_out(page):
                        sys.exit("La sesión expiró durante el recorrido. Volvé a correr (re-login automático).")
                    try:
                        page.wait_for_selector(".font-price, [data-productsku]", timeout=8000)
                    except Exception:
                        pass
                    page.wait_for_timeout(300)
                    cards = parse_listing(page.content())
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"    !! {code} pag {pg}: {type(e).__name__}: {str(e)[:140]} -- se omite y sigo")
                    break
                # Si la página no trae SKUs nuevos (vacía o Intcomex repitió la pág. 1),
                # llegamos al final de la categoría.
                nuevos = [c for c in cards if c["sku"] not in seen_cat]
                if not nuevos:
                    break
                for c in nuevos:
                    seen_cat.add(c["sku"])
                    c["catname"] = cats.get(code) or code
                    prods.setdefault(c["sku"], c)
                time.sleep(delay)
            print(f"  [{ci}/{len(codes)}] {code:<24} pág {pg}  acumulado: {len(prods)}")
        browser.close()

    if not prods:
        sys.exit("No se obtuvo ningún producto. Revisá la sesión / categorías.")
    data = build_catalog(list(prods.values()))
    html, _ = read_catalog()
    size = write_catalog(html, data)
    inject_fx(fx)   # actualiza el TC en la tienda solo si se leyó (inject_fx ignora None)
    json.dump(list(prods.values()), open(RESULTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nindex.html actualizado con TODO el catálogo: {len(data['rows'])} productos "
          f"({size} bytes de datos).  TC inyectado: {FX}")


def main():
    ap = argparse.ArgumentParser(description="Refresca/recorre la tienda desde Intcomex.")
    ap.add_argument("--login", action="store_true", help="Login manual y guardar sesión")
    ap.add_argument("--auto-login", action="store_true", help="Login automático (usuario/contraseña del .env)")
    ap.add_argument("--probe", metavar="RECNO", help="Volcar 1 página de detalle y validar selectores")
    ap.add_argument("--probe-cat", metavar="CODIGO", help="Volcar 1 página de una categoría (ej. cpt.notebook)")
    ap.add_argument("--crawl", action="store_true", help="Recorrer TODO el catálogo (todas las categorías)")
    ap.add_argument("--limit", type=int, help="Refrescar solo los primeros N productos (prueba)")
    ap.add_argument("--limit-cats", type=int, help="Recorrer solo las primeras N categorías (prueba de --crawl)")
    ap.add_argument("--headful", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--delay", type=float, default=0.6, help="Segundos de espera entre páginas/productos")
    a = ap.parse_args()

    if a.login:
        do_login()
    elif a.auto_login:
        with sync_playwright() as p:
            b, _ = auto_login(p, headful=a.headful)
            print("Login automático OK. Sesión guardada en:", STATE)
            b.close()
    elif a.probe:
        do_probe(a.probe)
    elif a.probe_cat:
        do_probe_cat(a.probe_cat, headful=a.headful)
    elif a.crawl:
        do_crawl(headful=a.headful, delay=a.delay, limit_cats=a.limit_cats)
    else:
        do_refresh(limit=a.limit, headful=a.headful, delay=a.delay)


if __name__ == "__main__":
    main()
