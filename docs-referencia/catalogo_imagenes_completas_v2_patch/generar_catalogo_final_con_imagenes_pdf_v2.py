"""
Costa Rica EBS S.A. - Generador final de catalogo con imagenes completas.

Objetivo:
- Descargar / reutilizar imagenes locales por SKU.
- Si Intcomex devuelve noimage o falla la descarga directa, intentar descubrir imagen desde la pagina de detalle.
- Generar HTML + PDF usando las imagenes locales, no imagenes remotas.
- Recalcular precio final: precio Intcomex USD x 1.13 IVA x 1.30 margen EBS.
- Mostrar solo precio final en USD y CRC.
- Mostrar stock solo como cantidad de unidades, sin ubicacion.
- Enlazar "Ficha fabricante" a pagina/busqueda oficial del fabricante por MPN/modelo.

Uso recomendado:
  py -m pip install -r requirements_catalogo_imagenes_v2.txt
  py -m playwright install chromium
  py generar_catalogo_final_con_imagenes_pdf_v2.py --deep-image-discovery --headful

Archivos esperados en la misma carpeta:
  - productos_intcomex_ebs_final_iva13_margen30.json
  - portada_catalogo_tecnologia_2026.png       (opcional)
  - logo_costa_rica_ebs.png                    (opcional)
  - pass.txt                                   (opcional, usuario linea 1 y password linea 2)

Salidas:
  - imagenes_intcomex\*.jpg/png/webp
  - catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.html
  - catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.pdf
  - reporte_imagenes_catalogo.csv
  - productos_catalogo_actualizado_imagenes.json
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    async_playwright = None
    PlaywrightTimeoutError = Exception

BASE = Path(__file__).resolve().parent
JSON_IN = BASE / "productos_intcomex_ebs_final_iva13_margen30.json"
IMG_DIR = BASE / "imagenes_intcomex"
HTML_OUT = BASE / "catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.html"
PDF_OUT = BASE / "catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.pdf"
REPORT_OUT = BASE / "reporte_imagenes_catalogo.csv"
JSON_OUT = BASE / "productos_catalogo_actualizado_imagenes.json"
COVER_PATH = BASE / "portada_catalogo_tecnologia_2026.png"
LOGO_PATH = BASE / "logo_costa_rica_ebs.png"
PASS_FILE = BASE / "pass.txt"
TC_CRC_USD = 456.01
IVA = 0.13
MARGEN_EBS = 0.30

COMPANY = "Costa Rica EBS S.A."
CONTACT = "Karen Maria Chavarria Sanchez | +506 6012-6082 | karen.chavarria@costaricaebs.com | www.costaricaebs.com"

MANUFACTURER_SEARCH = {
    "acer": "https://www.acer.com/us-en/search?q={q}",
    "apc": "https://www.apc.com/shop/us/en/search/{q}",
    "apple": "https://support.apple.com/search?query={q}",
    "asus": "https://www.asus.com/searchresult?searchType=products&searchKey={q}",
    "belkin": "https://www.belkin.com/search?q={q}",
    "brother": "https://support.brother.com/g/s/productsearch.aspx?c=us&lang=en&searchtext={q}",
    "canon": "https://www.usa.canon.com/search?q={q}",
    "corsair memory": "https://www.corsair.com/us/en/search?q={q}",
    "corsair": "https://www.corsair.com/us/en/search?q={q}",
    "dell": "https://www.dell.com/support/search/en-cr#q={q}",
    "epson": "https://epson.com/search/?text={q}",
    "eset": "https://www.eset.com/int/search/?q={q}",
    "forza": "https://www.forzaups.com/search?q={q}",
    "hp": "https://support.hp.com/us-en/search?q={q}",
    "hpe": "https://support.hpe.com/connect/s/search?language=en_US&q={q}",
    "jabra": "https://www.jabra.com/search?query={q}",
    "kingston": "https://www.kingston.com/en/search?keyword={q}",
    "kingston valueram": "https://www.kingston.com/en/search?keyword={q}",
    "klip xtreme": "https://www.klipxtreme.com/search?q={q}",
    "lenovo": "https://support.lenovo.com/us/en/search?query={q}",
    "logitech": "https://www.logitech.com/search?q={q}",
    "microsoft": "https://www.microsoft.com/search?q={q}",
    "motorola": "https://www.motorola.com/search?q={q}",
    "msi": "https://www.msi.com/search/{q}",
    "razer": "https://www.razer.com/search/{q}",
    "samsung": "https://www.samsung.com/us/search/searchMain/?searchTerm={q}",
    "sandisk": "https://www.westerndigital.com/search?q={q}",
    "startech.com": "https://www.startech.com/en-us/search?search_term={q}",
    "targus": "https://us.targus.com/search?q={q}",
    "tplink": "https://www.tp-link.com/us/search/?q={q}",
    "tp-link": "https://www.tp-link.com/us/search/?q={q}",
    "ubiquiti": "https://store.ui.com/us/en/search?query={q}",
    "wacom": "https://www.wacom.com/en-us/search?q={q}",
    "xiaomi": "https://www.mi.com/global/search?keyword={q}",
    "xtech": "https://www.xtechamericas.com/search?q={q}",
}


def safe_name(value: str, max_len: int = 110) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", (value or "").strip()).strip("_")
    return (value or "producto")[:max_len]


def parse_money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    s = s.replace("US$", "").replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def clean_category(cat: str) -> str:
    cat = (cat or "").strip()
    if not cat:
        return "Sin categoria"
    if " / " not in cat:
        return cat
    parts = [p.strip() for p in cat.split(" / ") if p.strip()]
    if not parts:
        return "Sin categoria"
    top = parts[0]
    rest = " ".join(parts[1:])
    rest = rest.replace(" - ", "-").replace("( ", "(").replace(" )", ")")
    rest = re.sub(r"\s+", " ", rest)
    if top.lower().startswith("destacados"):
        return "Destacados semanales y ofertas"
    return f"{top} - {rest}" if rest else top


def stock_units(item: dict) -> int:
    for key in ["stock_total_int", "stock_total"]:
        v = item.get(key)
        if v is None or v == "":
            continue
        try:
            return int(float(str(v).replace(",", ".")))
        except Exception:
            pass
    # fallback: first number from stock_detalle/disponibilidad_texto
    text = str(item.get("stock_detalle") or item.get("disponibilidad_texto") or "")
    nums = [int(n) for n in re.findall(r"\b\d+\b", text)]
    return nums[0] if nums else 0


def price_fields(item: dict) -> tuple[float, float, int]:
    costo = parse_money(item.get("precio_intcomex_usd")) or parse_money(item.get("precio_intcomex"))
    precio_usd = round(costo * (1 + IVA) * (1 + MARGEN_EBS), 2) if costo else 0.0
    precio_crc = int(round((precio_usd * TC_CRC_USD) / 100.0) * 100) if precio_usd else 0
    utilidad = round(precio_usd - costo, 2) if costo else 0.0
    return precio_usd, precio_crc, utilidad


def fmt_usd(value: float) -> str:
    return f"US${value:,.2f}" if value else "Consultar"


def fmt_crc(value: int) -> str:
    return f"CRC {value:,.0f}".replace(",", ".") if value else "Consultar"


def manufacturer_url(item: dict) -> str:
    brand = (item.get("marca") or "").strip().lower()
    mpn = (item.get("mpn") or "").strip()
    title = (item.get("titulo") or item.get("titulo_pdf") or "").strip()
    q = mpn or title
    q = q.replace("#", " ").strip()
    if not q:
        return str(item.get("producto_url") or "https://www.costaricaebs.com/")
    # use first two-three tokens for huge titles if no MPN
    if not mpn and len(q) > 80:
        q = " ".join(q.split()[:8])
    key = brand
    if key not in MANUFACTURER_SEARCH:
        # normalize common variants
        if "hp" == key or key.startswith("hp "):
            key = "hp"
        elif "dell" in key:
            key = "dell"
        elif "lenovo" in key:
            key = "lenovo"
        elif "kingston" in key:
            key = "kingston"
        elif "klip" in key:
            key = "klip xtreme"
        elif "xtech" in key:
            key = "xtech"
        elif "forza" in key:
            key = "forza"
        elif "apc" in key:
            key = "apc"
    template = MANUFACTURER_SEARCH.get(key)
    if template:
        return template.format(q=quote_plus(q))
    return f"https://www.google.com/search?q={quote_plus((item.get('marca') or '') + ' ' + q + ' official product') }"


def candidate_image_urls(item: dict) -> list[str]:
    urls = []
    original = str(item.get("imagen_url") or "").strip()
    if original and "noimage" not in original.lower():
        urls.append(original)
    sku = str(item.get("sku") or item.get("sku_show") or "").strip()
    mpn = str(item.get("mpn") or "").strip()
    raw_tokens = []
    if sku:
        raw_tokens.extend([sku, sku.replace("-B1", "").replace("-S", ""), sku.replace("-RC", "")])
    if mpn:
        raw_tokens.extend([mpn, mpn.replace("#", ""), mpn.replace("/", "_")])
    tokens = []
    seen = set()
    for t in raw_tokens:
        t = t.strip()
        if t and t not in seen:
            seen.add(t); tokens.append(t)
    bases = ["https://store.intcomex.com/images/products/"]
    suffixes = ["%20m.jpg", "%20M.jpg", "m.jpg", "M.jpg", "med.jpg", "_m.jpg", ".jpg", ".png", "%20m.png"]
    for token in tokens:
        quoted = quote_plus(token).replace("+", "%20")
        for suf in suffixes:
            urls.append(bases[0] + quoted + suf)
    # deduplicate
    out=[]; seen=set()
    for u in urls:
        if u not in seen:
            seen.add(u); out.append(u)
    return out[:30]


def url_ext(url: str, content_type: str = "") -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    path = urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def looks_like_image_bytes(data: bytes) -> bool:
    if len(data) < 800:
        return False
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF" or data[:6] in [b"GIF87a", b"GIF89a"]


def download_url(session: requests.Session, url: str, out: Path) -> tuple[bool, str]:
    try:
        fixed = requests.utils.requote_uri(url)
        r = session.get(fixed, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            return False, f"http_{r.status_code}"
        ctype = r.headers.get("content-type", "")
        if "image" not in ctype.lower() and not looks_like_image_bytes(r.content):
            return False, f"no_image_{ctype[:30]}"
        if not looks_like_image_bytes(r.content):
            return False, "small_or_invalid"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        return True, "ok"
    except Exception as exc:
        return False, f"err_{str(exc)[:60]}"


def local_image_path(item: dict, url: str) -> Path:
    sku = safe_name(str(item.get("sku") or item.get("sku_show") or "producto"), 80)
    h = hashlib.sha1(url.encode("utf-8", errors="ignore")).hexdigest()[:8]
    ext = url_ext(url)
    return IMG_DIR / f"{sku}_{h}{ext}"


def read_credentials() -> tuple[str | None, str | None]:
    if not PASS_FILE.exists():
        return None, None
    lines = [x.strip() for x in PASS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    return None, None


async def auto_login_if_needed(page, headful: bool) -> None:
    username, password = read_credentials()
    if not username or not password:
        print("No se encontro pass.txt; si Intcomex solicita login, completelo manualmente.")
        if headful:
            input("Presione ENTER cuando haya iniciado sesion en Intcomex...")
        return
    try:
        await page.goto("https://store.intcomex.com/es-XCR/Customer/Access", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    user_selectors = ["input[name='signInName']", "input#signInName", "input[type='email']", "input[name='email']", "input[name='username']", "input[type='text']"]
    pass_selectors = ["input[name='password']", "input#password", "input[type='password']"]
    for sel in user_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                await loc.fill(username)
                break
        except Exception:
            pass
    for sel in pass_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible(timeout=2500):
                await loc.fill(password)
                break
        except Exception:
            pass
    clicked = False
    for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Ingresar')", "button:has-text('Sign in')", "button:has-text('Iniciar')", "#next", "#continue"]:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible(timeout=2000):
                await loc.click()
                clicked = True
                break
        except Exception:
            pass
    if headful:
        print("Login automatico intentado. Si aparece MFA/SMS/captcha, completelo manualmente.")
        input("Cuando vea el WebStore o el producto, presione ENTER para continuar...")
    else:
        await page.wait_for_timeout(6000 if clicked else 2000)


async def discover_image_from_detail(page, item: dict) -> str | None:
    url = str(item.get("producto_url") or "").strip()
    if not url:
        return None
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1200)
        images = await page.evaluate("""
        () => Array.from(document.images).map(img => ({
            src: img.currentSrc || img.src || img.getAttribute('data-src') || '',
            w: img.naturalWidth || 0,
            h: img.naturalHeight || 0,
            alt: img.alt || '',
            cls: img.className || ''
        }))
        """)
    except Exception:
        return None
    candidates=[]
    for im in images:
        src = (im.get("src") or "").strip()
        if not src:
            continue
        src = urljoin(url, src)
        l = src.lower()
        if any(x in l for x in ["noimage", "logo", "sprite", "icon", "spinner", "loader", "blank", "pixel"]):
            continue
        w = int(im.get("w") or 0); h = int(im.get("h") or 0)
        score = 0
        if "/images/products/" in l:
            score += 100
        if "1worldsync" in l or "cdn" in l:
            score += 50
        score += min(w, 1000) / 10 + min(h, 1000) / 10
        if w >= 80 and h >= 80:
            candidates.append((score, src))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


async def deep_discover_images(failed_items: list[dict], headful: bool) -> None:
    if not failed_items:
        return
    if async_playwright is None:
        print("Playwright no esta instalado; no puedo hacer descubrimiento profundo de imagenes.")
        return
    print(f"Iniciando descubrimiento profundo de imagenes para {len(failed_items)} productos...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful)
        context = await browser.new_context(ignore_https_errors=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36")
        page = await context.new_page()
        await auto_login_if_needed(page, headful=headful)
        for i, item in enumerate(failed_items, 1):
            url = await discover_image_from_detail(page, item)
            if url:
                item["_deep_image_url"] = url
                print(f"[{i}/{len(failed_items)}] Imagen encontrada en detalle: {item.get('sku')} -> {url}")
            else:
                print(f"[{i}/{len(failed_items)}] Sin imagen en detalle: {item.get('sku')}")
        await browser.close()


def download_images(products: list[dict], args) -> None:
    IMG_DIR.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://store.intcomex.com/",
    })
    failed = []
    ok = 0
    for idx, item in enumerate(products, 1):
        if item.get("imagen_local"):
            p = Path(str(item["imagen_local"]))
            if not p.is_absolute():
                p = BASE / p
            if p.exists() and p.stat().st_size > 800:
                item["_image_file"] = str(p)
                item["_image_status"] = "cache_json"
                ok += 1
                continue
        found = False
        last_msg = "sin_url"
        for url in candidate_image_urls(item):
            out = local_image_path(item, url)
            if out.exists() and out.stat().st_size > 800:
                item["_image_file"] = str(out)
                item["_image_url_final"] = url
                item["_image_status"] = "cache"
                found = True
                break
            success, msg = download_url(session, url, out)
            last_msg = msg
            if success:
                item["_image_file"] = str(out)
                item["_image_url_final"] = url
                item["_image_status"] = "descargada"
                found = True
                break
        if found:
            ok += 1
        else:
            item["_image_status"] = last_msg
            failed.append(item)
        if idx % 50 == 0 or idx == len(products):
            print(f"Imagenes fase directa: {idx}/{len(products)} | OK/cache: {ok} | pendientes: {len(failed)}")

    if args.deep_image_discovery and failed:
        asyncio.run(deep_discover_images(failed, headful=args.headful))
        for item in failed:
            url = item.get("_deep_image_url")
            if not url:
                continue
            out = local_image_path(item, url)
            success, msg = download_url(session, url, out)
            if success:
                item["_image_file"] = str(out)
                item["_image_url_final"] = url
                item["_image_status"] = "detalle_descargada"
            else:
                item["_image_status"] = f"detalle_{msg}"

    # final count
    count = sum(1 for p in products if p.get("_image_file") and Path(str(p.get("_image_file"))).exists())
    print(f"Imagenes finales disponibles localmente: {count}/{len(products)}")


def prepare_products(products: list[dict]) -> list[dict]:
    for item in products:
        item["categoria_display"] = clean_category(item.get("categoria_limpia") or item.get("categoria") or "")
        item["stock_units"] = stock_units(item)
        usd, crc, utilidad = price_fields(item)
        item["precio_final_usd"] = usd
        item["precio_final_crc"] = crc
        item["utilidad_final_usd"] = utilidad
        item["precio_usd_display"] = fmt_usd(usd)
        item["precio_crc_display"] = fmt_crc(crc)
        item["titulo_display"] = (item.get("titulo_pdf") or item.get("titulo") or "").strip()
        item["marca_display"] = (item.get("marca") or "").strip()
        item["fabricante_url"] = manufacturer_url(item)
    return products


def write_report(products: list[dict]) -> None:
    fields = ["sku", "marca", "mpn", "categoria_display", "imagen_url", "_image_url_final", "_image_file", "_image_status", "producto_url", "fabricante_url"]
    with REPORT_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for item in products:
            w.writerow({k: item.get(k, "") for k in fields})


def slug(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9áéíóúñü]+", "-", s, flags=re.I).strip("-")
    return s[:90] or "categoria"


def write_html(products: list[dict]) -> None:
    cats = sorted({p["categoria_display"] for p in products}, key=lambda s: s.lower())
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["categoria_display"]].append(p)
    for cat in cats:
        by_cat[cat].sort(key=lambda p: ((p.get("marca_display") or "").lower(), (p.get("titulo_display") or "").lower()))
    css = """
    :root{--navy:#071B2D;--blue:#14A8E0;--muted:#64748B;--bg:#F4F8FC;--card:#fff;--line:#DDE8F2;--green:#DCFCE7;--greenText:#14532D;}
    *{box-sizing:border-box} body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:#0f172a} a{text-decoration:none;color:inherit}
    header{background:linear-gradient(120deg,#061625,#0b2740 65%,#101827);color:white;padding:28px 36px;position:sticky;top:0;z-index:10;box-shadow:0 6px 24px rgba(2,8,23,.18)}
    h1{margin:0;font-size:28px}.sub{margin:6px 0 0;color:#BBDCF2}.controls{display:grid;grid-template-columns:1fr 260px 180px;gap:12px;margin-top:18px}.controls input,.controls select{border:0;border-radius:12px;padding:13px;font-size:15px}.kpi{border-radius:12px;background:rgba(255,255,255,.1);padding:12px 14px;color:#EAF6FF}
    main{padding:28px 36px 60px}.note{background:#fff7ed;border:1px solid #fed7aa;color:#7c2d12;padding:14px 18px;border-radius:14px;margin-bottom:18px}.toc{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;margin-bottom:24px}.toc a{background:white;border:1px solid var(--line);border-radius:12px;padding:10px 12px;display:flex;justify-content:space-between;gap:10px}.toc b{color:var(--blue)}
    .cat-title{margin:28px 0 14px;padding:16px 18px;background:#0B1F33;color:white;border-radius:16px;display:flex;justify-content:space-between;gap:18px;align-items:center}.cat-title h2{margin:0;font-size:24px}.cat-title small{color:#BBDCF2}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:18px}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 8px 20px rgba(2,8,23,.05);display:flex;flex-direction:column;min-height:430px}.photo{height:185px;display:flex;align-items:center;justify-content:center;background:#fff;border-bottom:1px solid var(--line)}.photo img{max-width:92%;max-height:170px;object-fit:contain}.noimg{font-weight:700;color:#64748B}
    .body{padding:16px;display:flex;flex-direction:column;gap:8px;flex:1}.meta{display:flex;gap:6px;flex-wrap:wrap}.badge{background:#0B1F33;color:white;border-radius:999px;font-size:12px;padding:4px 8px;font-weight:700}.warn{background:#F97316}.title{font-size:17px;line-height:1.25;font-weight:700;min-height:58px}.desc,.cat{margin:0;color:#64748b;font-size:13px;line-height:1.3}.price{margin-top:auto;padding:12px;border-radius:14px;background:#EFF6FF;border:1px solid #DBEAFE}.price b{display:block;font-size:25px;color:#0B1F33}.price small{color:#334155;font-weight:700}.stock{border-radius:10px;padding:8px 10px;font-weight:700;font-size:13px;background:var(--green);color:var(--greenText)}.link{font-size:13px;color:#0B66B2;text-decoration:underline;margin-top:6px}footer{padding:22px 36px;color:#64748b;border-top:1px solid #e2e8f0;background:#fff}
    @media print{header{position:relative}.controls{display:none}.grid{grid-template-columns:repeat(3,1fr)}.card{break-inside:avoid}main{padding:18px}.toc{break-after:page}}
    """
    rows = ["<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Catalogo Costa Rica EBS</title><style>", css, "</style></head><body>"]
    rows.append(f"<header><h1>{html.escape(COMPANY)} - Catálogo de Tecnología 2026</h1><p class='sub'>Partner Oficial de Microsoft | {html.escape(CONTACT)}</p><div class='controls'><input id='q' placeholder='Buscar por producto, marca, SKU, MPN o categoría...'><select id='top'><option value=''>Todas las categorías</option>")
    tops = sorted({(p.get('categoria_display') or '').split(' - ')[0] for p in products})
    for t in tops:
        rows.append(f"<option value='{html.escape(t)}'>{html.escape(t)}</option>")
    rows.append(f"</select><div class='kpi'><b id='count'>{len(products)}</b> productos visibles</div></div></header><main>")
    rows.append("<div class='note'><b>Catálogo comercial para clientes.</b> Precios finales calculados con precio Intcomex + 13% IVA + 30% margen EBS. Se muestra únicamente precio final en USD y CRC. Stock expresado solo como cantidad de unidades.</div>")
    rows.append("<section class='toc'>")
    for cat in cats:
        rows.append(f"<a href='#{slug(cat)}'><span>{html.escape(cat)}</span><b>{len(by_cat[cat])}</b></a>")
    rows.append("</section>")
    for cat in cats:
        rows.append(f"<section class='cat-section' id='{slug(cat)}'><div class='cat-title'><h2>{html.escape(cat)}</h2><small>{len(by_cat[cat])} productos</small></div><div class='grid'>")
        for p in by_cat[cat]:
            img = Path(str(p.get('_image_file') or ''))
            rel = os.path.relpath(img, BASE).replace('\\','/') if img.exists() else ''
            cond = (p.get('condicion') or '').strip()
            cond_html = f"<span class='badge warn'>{html.escape(cond)}</span>" if cond else ""
            photo = f"<img src='{html.escape(rel)}' alt='{html.escape(p['titulo_display'])}' loading='lazy'>" if rel else "<span class='noimg'>Imagen no disponible</span>"
            search = " ".join([str(p.get('sku','')), str(p.get('mpn','')), p.get('marca_display',''), p.get('titulo_display',''), p.get('categoria_display','')]).lower()
            top = cat.split(' - ')[0]
            rows.append(f"""
            <article class='card' data-top='{html.escape(top)}' data-category='{html.escape(cat)}' data-search='{html.escape(search)}'>
              <a class='photo' href='{html.escape(p.get('fabricante_url') or '#')}' target='_blank' rel='noopener'>{photo}</a>
              <div class='body'>
                <div class='meta'><span class='badge'>{html.escape(p.get('marca_display') or '')}</span>{cond_html}</div>
                <div class='title'>{html.escape(p.get('titulo_display') or '')}</div>
                <p class='desc'>SKU: <b>{html.escape(str(p.get('sku') or ''))}</b> · MPN: {html.escape(str(p.get('mpn') or ''))}</p>
                <p class='cat'>{html.escape(cat)}</p>
                <div class='price'><b>{html.escape(p['precio_usd_display'])}</b><small>{html.escape(p['precio_crc_display'])}</small></div>
                <div class='stock'>Stock: {int(p.get('stock_units') or 0)} unidades</div>
                <a class='link' href='{html.escape(p.get('fabricante_url') or '#')}' target='_blank' rel='noopener'>Ficha fabricante</a>
              </div>
            </article>
            """)
        rows.append("</div></section>")
    rows.append(f"</main><footer>{html.escape(CONTACT)} | Precios sujetos a validación final de SKU, stock, tipo de cambio, flete, garantía, instalación y SLA.</footer>")
    rows.append("<script>const q=document.getElementById('q'),topSel=document.getElementById('top'),cards=[...document.querySelectorAll('.card')],count=document.getElementById('count');function f(){const s=(q.value||'').toLowerCase(),t=topSel.value;let n=0;cards.forEach(c=>{const show=(!s||c.dataset.search.includes(s))&&(!t||c.dataset.top===t);c.style.display=show?'flex':'none';if(show)n++});count.textContent=n}q.addEventListener('input',f);topSel.addEventListener('change',f);</script>")
    rows.append("</body></html>")
    HTML_OUT.write_text("".join(rows), encoding="utf-8")


# PDF helpers
W, H = landscape(letter)
MARGIN = 24
NAVY = colors.HexColor('#08192F')
NAVY2 = colors.HexColor('#0D2B52')
CYAN = colors.HexColor('#30B8FF')
LIGHT = colors.HexColor('#EAF3FF')
MUTED = colors.HexColor('#5C708A')
LINE = colors.HexColor('#D8E4F0')
PLACEHOLDER = colors.HexColor('#DFECF8')


def fit_text(text: str, max_width: float, font='Helvetica', size=10) -> str:
    txt = str(text or '')
    if stringWidth(txt, font, size) <= max_width:
        return txt
    ell = '...'
    while txt and stringWidth(txt + ell, font, size) > max_width:
        txt = txt[:-1]
    return txt + ell


def wrap_lines(text: str, width: float, font='Helvetica', size=10, max_lines=2) -> list[str]:
    words = str(text or '').split()
    lines=[]; cur=''
    for w in words:
        test=(cur+' '+w).strip()
        if stringWidth(test,font,size) <= width:
            cur=test
        else:
            if cur:
                lines.append(cur)
            cur=w
    if cur:
        lines.append(cur)
    if len(lines)>max_lines:
        lines=lines[:max_lines]
        lines[-1]=fit_text(lines[-1], width, font, size)
    return lines


def draw_wrapped(can, text, x, y, width, font='Helvetica', size=10, leading=12, max_lines=2, color=colors.black):
    can.setFont(font, size); can.setFillColor(color)
    yy=y
    for line in wrap_lines(text,width,font,size,max_lines):
        can.drawString(x, yy, line); yy -= leading
    return yy


def draw_image_fit(can, path: Path, x: float, y: float, w: float, h: float) -> bool:
    try:
        if not path.exists() or path.stat().st_size < 500:
            return False
        # Validate with Pillow; convert unsupported formats to RGB temp if needed
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            iw, ih = im.size
        if iw <= 0 or ih <= 0:
            return False
        scale = min(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        dx, dy = x + (w-dw)/2, y + (h-dh)/2
        can.drawImage(ImageReader(str(path)), dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
        return True
    except Exception:
        return False


def draw_footer(can, page_num: int):
    can.setStrokeColor(LINE); can.line(MARGIN, 20, W-MARGIN, 20)
    can.setFont('Helvetica', 7.5); can.setFillColor(MUTED)
    can.drawString(MARGIN, 8, CONTACT)
    can.drawRightString(W-MARGIN, 8, 'Precios sujetos a validacion final de SKU, stock, tipo de cambio, flete, garantia, instalacion y SLA.')
    can.drawRightString(W-MARGIN, 24, f'Pagina {page_num}')


def write_pdf(products: list[dict]) -> None:
    cats = sorted({p["categoria_display"] for p in products}, key=lambda s: s.lower())
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["categoria_display"]].append(p)
    for cat in cats:
        by_cat[cat].sort(key=lambda p: ((p.get("marca_display") or "").lower(), (p.get("titulo_display") or "").lower()))

    c = canvas.Canvas(str(PDF_OUT), pagesize=landscape(letter))
    page_num = 1
    # Cover
    if COVER_PATH.exists():
        c.drawImage(ImageReader(str(COVER_PATH)), 0, 0, width=W, height=H)
    else:
        c.setFillColor(NAVY); c.rect(0,0,W,H,stroke=0,fill=1)
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold',38); c.drawString(60,H-180,'Catalogo de Tecnologia 2026')
        c.setFillColor(CYAN); c.setFont('Helvetica-Bold',24); c.drawString(60,H-220,'Costa Rica EBS S.A.')
        c.setFillColor(LIGHT); c.setFont('Helvetica',14); c.drawString(60,H-250,CONTACT)
    c.showPage(); page_num += 1

    # Overview page
    c.setFillColor(NAVY); c.rect(0,0,W,H,stroke=0,fill=1)
    if LOGO_PATH.exists():
        c.drawImage(ImageReader(str(LOGO_PATH)), MARGIN, H-90, width=58, height=58, mask='auto')
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold',26); c.drawString(95,H-48,COMPANY)
    c.setFont('Helvetica',13); c.setFillColor(LIGHT); c.drawString(95,H-68,'Partner Oficial de Microsoft | Soluciones TI, Cloud, Seguridad e Infraestructura')
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold',28); c.drawString(MARGIN,H-135,'Catalogo comercial para clientes')
    c.setFont('Helvetica',14); c.setFillColor(LIGHT)
    draw_wrapped(c, 'Precios finales calculados con precio Intcomex + 13% IVA + 30% margen EBS. Se muestra solo precio final en dolares y colones; el stock se presenta solo como cantidad de unidades.', MARGIN, H-165, W-2*MARGIN, font='Helvetica', size=14, leading=18, max_lines=3, color=LIGHT)
    stats = [(str(len(products)),'productos'), (str(len(cats)),'categorias'), (str(sum(1 for p in products if p.get('_image_file') and Path(str(p.get('_image_file'))).exists())),'imagenes locales'), ('2026','catalogo vigente')]
    bw=168; bh=58; gap=12; y=H-270
    for i,(n,lbl) in enumerate(stats):
        x=MARGIN+i*(bw+gap)
        c.setFillColor(colors.Color(1,1,1,alpha=0.08)); c.setStrokeColor(colors.Color(1,1,1,alpha=0.18)); c.roundRect(x,y,bw,bh,12,stroke=1,fill=1)
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold',22); c.drawString(x+14,y+34,n)
        c.setFillColor(LIGHT); c.setFont('Helvetica',11); c.drawString(x+14,y+16,lbl)
    notes=[('Formula comercial','Precio final USD = Intcomex USD x 1.13 x 1.30. CRC = USD final x 456.01, redondeado.'),('Fotos','El PDF usa archivos locales descargados en imagenes_intcomex. Si Intcomex no ofrece imagen real, queda reportado en CSV.'),('Enlaces','El boton Ficha fabricante apunta a busqueda/ficha oficial del fabricante por MPN o modelo.'),('Cotizacion final','Sujeta a validacion de SKU, stock, IVA, tipo de cambio, flete, garantia, instalacion y SLA.')]
    cw=(W-2*MARGIN-12)/2; ch=78; sy=H-380
    for i,(t,tx) in enumerate(notes):
        row,col=divmod(i,2); x=MARGIN+col*(cw+12); yy=sy-row*(ch+12)
        c.setFillColor(colors.Color(1,1,1,alpha=0.07)); c.setStrokeColor(colors.Color(1,1,1,alpha=0.15)); c.roundRect(x,yy,cw,ch,12,stroke=1,fill=1)
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold',14); c.drawString(x+12,yy+56,t)
        draw_wrapped(c, tx, x+12, yy+40, cw-24, font='Helvetica', size=10, leading=12, max_lines=3, color=LIGHT)
    draw_footer(c,page_num); c.showPage(); page_num += 1

    # TOC
    c.bookmarkPage('indice')
    c.setFillColor(NAVY); c.rect(0,0,W,H,stroke=0,fill=1)
    if LOGO_PATH.exists():
        c.drawImage(ImageReader(str(LOGO_PATH)), MARGIN, H-82, width=50, height=50, mask='auto')
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold',28); c.drawString(85,H-48,'Indice de contenido')
    c.setFont('Helvetica',13); c.setFillColor(LIGHT); c.drawString(85,H-68,'Categorias ordenadas alfabeticamente. Clic en una categoria para ir a su seccion.')
    col_w=(W-2*MARGIN-20)/2; half=math.ceil(len(cats)/2); start_y=H-105; row_h=18
    for idx,cat in enumerate(cats):
        col=0 if idx<half else 1; row=idx if col==0 else idx-half
        x=MARGIN+col*(col_w+20); yy=start_y-row*row_h
        c.setFillColor(colors.Color(1,1,1,alpha=0.07)); c.setStrokeColor(colors.Color(1,1,1,alpha=0.12)); c.roundRect(x,yy-12,col_w,16,6,stroke=1,fill=1)
        c.setFillColor(colors.white); c.setFont('Helvetica',10); c.drawString(x+8,yy,fit_text(cat,col_w-70,'Helvetica',10))
        c.setFillColor(CYAN); c.drawRightString(x+col_w-8,yy,str(len(by_cat[cat])))
        c.linkRect('', f'cat{idx+1}', (x+4, yy-10, x+col_w-4, yy+4), relative=0, thickness=0)
    draw_footer(c,page_num); c.showPage(); page_num += 1

    cards_per_page = 6
    card_gap_x = 14; card_gap_y = 14
    usable_w = W - 2*MARGIN
    usable_h = H - 2*MARGIN - 46
    card_w = (usable_w - card_gap_x)/2
    card_h = (usable_h - 2*card_gap_y)/3

    for cat_idx, cat in enumerate(cats, 1):
        products_cat = by_cat[cat]
        pages = math.ceil(len(products_cat)/cards_per_page)
        for pidx in range(pages):
            if pidx == 0:
                c.bookmarkPage(f'cat{cat_idx}')
                c.addOutlineEntry(cat, f'cat{cat_idx}', level=0, closed=False)
            c.setFillColor(colors.HexColor('#F4F8FC')); c.rect(0,0,W,H,stroke=0,fill=1)
            c.setFillColor(NAVY2); c.roundRect(MARGIN,H-62,W-2*MARGIN,42,12,stroke=0,fill=1)
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold',17); c.drawString(MARGIN+16,H-42,fit_text(cat,W-2*MARGIN-140,'Helvetica-Bold',17))
            c.setFont('Helvetica',10); c.setFillColor(LIGHT); c.drawString(MARGIN+16,H-56,f"{len(products_cat)} productos en esta categoria")
            c.setFillColor(CYAN); c.setFont('Helvetica',10); c.drawRightString(W-MARGIN-10,H-47,'Volver al indice')
            c.linkRect('', 'indice', (W-MARGIN-100, H-58, W-MARGIN-10, H-34), relative=0, thickness=0)
            subset = products_cat[pidx*cards_per_page:(pidx+1)*cards_per_page]
            for j,item in enumerate(subset):
                row,col = divmod(j,2)
                x = MARGIN + col*(card_w+card_gap_x)
                y = H - 84 - (row+1)*card_h - row*card_gap_y
                c.setFillColor(colors.white); c.setStrokeColor(LINE); c.roundRect(x,y,card_w,card_h,14,stroke=1,fill=1)
                img_y = y + card_h - 74
                c.setFillColor(colors.white); c.roundRect(x+10,img_y,card_w-20,64,10,stroke=0,fill=1)
                img_path = Path(str(item.get('_image_file') or ''))
                if not draw_image_fit(c, img_path, x+14, img_y+3, card_w-28, 58):
                    c.setFillColor(PLACEHOLDER); c.roundRect(x+10,img_y,card_w-20,64,10,stroke=0,fill=1)
                    initials = (item.get('marca_display') or 'TI')[:2].upper()
                    c.setFillColor(NAVY2); c.circle(x+40,img_y+32,18,stroke=0,fill=1)
                    c.setFillColor(colors.white); c.setFont('Helvetica-Bold',11); c.drawCentredString(x+40,img_y+28,initials)
                    c.setFillColor(MUTED); c.setFont('Helvetica-Bold',8); c.drawString(x+68,img_y+34,'Imagen no disponible')
                    c.setFont('Helvetica',7.5); c.drawString(x+68,img_y+22,'Revisar reporte CSV')
                # brand and condition
                c.setFillColor(NAVY2); c.setFont('Helvetica-Bold',8.5); c.drawString(x+12, y+card_h-84, fit_text((item.get('marca_display') or '').upper(), 130, 'Helvetica-Bold', 8.5))
                cond=(item.get('condicion') or '').strip()
                if cond:
                    pill=fit_text(cond, 110, 'Helvetica-Bold', 7)
                    pill_w=stringWidth(pill,'Helvetica-Bold',7)+10
                    c.setFillColor(colors.HexColor('#FFF3CD')); c.setStrokeColor(colors.HexColor('#F0D98A')); c.roundRect(x+card_w-pill_w-12,y+card_h-90,pill_w,12,6,stroke=1,fill=1)
                    c.setFillColor(colors.HexColor('#7A5200')); c.setFont('Helvetica-Bold',7); c.drawCentredString(x+card_w-pill_w/2-12+pill_w/2,y+card_h-86,pill)
                end_y = draw_wrapped(c, item.get('titulo_display',''), x+12, y+card_h-100, card_w-24, font='Helvetica-Bold', size=10, leading=12, max_lines=2, color=colors.HexColor('#10213D'))
                c.setFont('Helvetica',8); c.setFillColor(MUTED); c.drawString(x+12,end_y-4,f"SKU: {item.get('sku','')}")
                c.drawString(x+12,end_y-15,f"MPN: {fit_text(str(item.get('mpn','')), card_w-50, 'Helvetica', 8)}")
                price_y = y+36
                c.setFillColor(colors.HexColor('#F6FBFF')); c.setStrokeColor(colors.HexColor('#DCEBF8')); c.roundRect(x+10,price_y,card_w-20,42,10,stroke=1,fill=1)
                c.setFillColor(NAVY2); c.setFont('Helvetica-Bold',15); c.drawString(x+18,price_y+25,item['precio_usd_display'])
                c.setFillColor(colors.HexColor('#1F5D97')); c.setFont('Helvetica-Bold',9); c.drawString(x+18,price_y+12,item['precio_crc_display'])
                c.setFillColor(colors.HexColor('#2C5F3B')); c.setFont('Helvetica-Bold',8); c.drawRightString(x+card_w-18,price_y+12,f"Stock: {int(item.get('stock_units') or 0)} unid.")
                c.setFont('Helvetica',8); c.setFillColor(colors.HexColor('#0B66B2')); c.drawString(x+12,y+16,'Ficha fabricante')
                if item.get('fabricante_url'):
                    c.linkURL(item['fabricante_url'], (x+12, y+12, x+100, y+24), relative=0, thickness=0)
            draw_footer(c,page_num); c.showPage(); page_num += 1
    c.save()


def load_products() -> list[dict]:
    if not JSON_IN.exists():
        matches = sorted(BASE.glob("productos*_iva13_margen30*.json")) or sorted(BASE.glob("productos*.json"))
        if not matches:
            print("No encuentro archivo de productos JSON en esta carpeta.")
            sys.exit(1)
        path = matches[0]
        print(f"Usando JSON encontrado: {path.name}")
    else:
        path = JSON_IN
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--deep-image-discovery', action='store_true', help='Visita pagina de detalle de Intcomex para productos sin imagen directa.')
    parser.add_argument('--headful', action='store_true', help='Abre navegador visible para login/MFA cuando se usa descubrimiento profundo.')
    parser.add_argument('--skip-download', action='store_true', help='No descarga imagenes; usa imagenes_intcomex existentes.')
    parser.add_argument('--delete-pass-after-login', action='store_true', help='Elimina pass.txt al finalizar.')
    args = parser.parse_args()

    products = prepare_products(load_products())
    print(f"Productos cargados: {len(products)}")
    if not args.skip_download:
        download_images(products, args)
    else:
        for item in products:
            # try to match existing files by SKU
            sku = safe_name(str(item.get('sku') or item.get('sku_show') or ''))
            candidates = list(IMG_DIR.glob(f"{sku}_*.*")) + list(IMG_DIR.glob(f"{sku}.*"))
            if candidates:
                item['_image_file'] = str(candidates[0])
                item['_image_status'] = 'cache_skip_download'
    write_report(products)
    JSON_OUT.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding='utf-8')
    write_html(products)
    write_pdf(products)

    images_ok = sum(1 for p in products if p.get('_image_file') and Path(str(p.get('_image_file'))).exists())
    missing = len(products) - images_ok
    print('\nRESULTADO')
    print(f"Productos: {len(products)}")
    print(f"Imagenes locales disponibles: {images_ok}")
    print(f"Pendientes/sin imagen real: {missing}")
    print(f"HTML: {HTML_OUT.name}")
    print(f"PDF: {PDF_OUT.name}")
    print(f"Reporte: {REPORT_OUT.name}")
    if args.delete_pass_after_login and PASS_FILE.exists():
        try:
            PASS_FILE.unlink()
            print('pass.txt eliminado localmente.')
        except Exception as exc:
            print(f'No se pudo eliminar pass.txt: {exc}')


if __name__ == '__main__':
    main()
