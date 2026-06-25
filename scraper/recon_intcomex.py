#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RECONOCIMIENTO del portal Intcomex (Etapa 2 de la automatización).

Objetivo: iniciar sesión y GUARDAR el HTML + capturas de pantalla de las páginas
clave (login, una categoría/listado, un producto) para poder ver la estructura
real del sitio y construir luego el extractor con los selectores correctos.

NO extrae productos todavía: solo observa y documenta el sitio.

Uso (la primera vez conviene verlo en pantalla):
    pip install -r requirements.txt
    python -m playwright install chromium
    python recon_intcomex.py --headful

Resultados en  scraper/recon/ :
    01_inicio.html / .png        -> página de arranque
    02_login_form.html / .png    -> formulario de login detectado
    03_post_login.html / .png    -> página tras iniciar sesión
    campos_detectados.txt        -> inputs/botones encontrados (para mapear selectores)
"""
import os
import sys
import argparse
from dotenv import load_dotenv

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Falta Playwright. Corré:  pip install -r requirements.txt  &&  python -m playwright install chromium")

HERE = os.path.dirname(os.path.abspath(__file__))
RECON = os.path.join(HERE, "recon")
load_dotenv(os.path.join(HERE, ".env"))

USER = os.getenv("INTCOMEX_USER", "")
PASS = os.getenv("INTCOMEX_PASS", "")
CODE = os.getenv("INTCOMEX_CODE", "")
BASE = os.getenv("INTCOMEX_BASE", "https://store.intcomex.com/es-XCR/Home")


def dump(page, name):
    """Guarda HTML + screenshot de la página actual."""
    os.makedirs(RECON, exist_ok=True)
    html_path = os.path.join(RECON, name + ".html")
    png_path = os.path.join(RECON, name + ".png")
    try:
        open(html_path, "w", encoding="utf-8").write(page.content())
        page.screenshot(path=png_path, full_page=True)
        print(f"  guardado: {name}.html / .png   (url: {page.url})")
    except Exception as e:
        print(f"  no se pudo guardar {name}: {e}")


def describe_inputs(page):
    """Lista inputs y botones visibles para ayudar a mapear el formulario de login."""
    lines = [f"URL: {page.url}", ""]
    for tag in ("input", "button", "a"):
        els = page.query_selector_all(tag)
        lines.append(f"=== <{tag}> encontrados: {len(els)} ===")
        for el in els[:60]:
            attrs = {}
            for a in ("id", "name", "type", "placeholder", "href", "value", "class"):
                v = el.get_attribute(a)
                if v:
                    attrs[a] = v[:60]
            txt = (el.inner_text() or "").strip()[:40]
            if attrs or txt:
                lines.append(f"  {attrs}  texto={txt!r}")
        lines.append("")
    open(os.path.join(RECON, "campos_detectados.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("  guardado: campos_detectados.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headful", action="store_true", help="Mostrar el navegador (recomendado la 1ra vez)")
    ap.add_argument("--pause", action="store_true",
                    help="Pausar con el inspector de Playwright para hacer login a mano y grabar selectores")
    a = ap.parse_args()

    if not USER or not PASS:
        print("AVISO: INTCOMEX_USER / INTCOMEX_PASS vacíos en scraper/.env")
        print("       Podés correr igual con --pause para iniciar sesión a mano y observar el sitio.\n")

    os.makedirs(RECON, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.headful)
        ctx = browser.new_context(locale="es-CR", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        print(f"1) Abriendo {BASE} ...")
        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        dump(page, "01_inicio")
        describe_inputs(page)

        if a.pause:
            # Modo manual: iniciás sesión vos mismo y navegás; Playwright queda abierto
            # para inspeccionar elementos y copiar selectores reales.
            print("\n>> MODO PAUSA: iniciá sesión y navegá a mano.")
            print(">> Usá el inspector para copiar selectores. Cerralo para terminar.\n")
            page.pause()
            dump(page, "03_post_login")
            describe_inputs(page)
            browser.close()
            return

        # Intento automático de login: estos selectores son TENTATIVOS y casi seguro
        # habrá que ajustarlos con lo que muestre campos_detectados.txt.
        print("2) Intentando ubicar el formulario de login...")
        candidates_user = ["input[name='UserName']", "input[name='username']",
                           "input[type='email']", "#UserName", "#username", "#email"]
        candidates_pass = ["input[name='Password']", "input[name='password']",
                           "input[type='password']", "#Password", "#password"]
        u = next((s for s in candidates_user if page.query_selector(s)), None)
        pw = next((s for s in candidates_pass if page.query_selector(s)), None)

        if u and pw:
            print(f"   campo usuario: {u}   campo clave: {pw}")
            try:
                page.fill(u, USER)
                page.fill(pw, PASS)
                dump(page, "02_login_form")
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
                dump(page, "03_post_login")
                describe_inputs(page)
            except Exception as e:
                print(f"   error rellenando login: {e}")
        else:
            print("   No se detectó automáticamente el formulario.")
            print("   Revisá scraper/recon/campos_detectados.txt y volvé a correr con --pause.")
            dump(page, "02_login_form")

        browser.close()

    print("\nListo. Revisá la carpeta scraper/recon/ y compartime:")
    print("  - campos_detectados.txt")
    print("  - si el login funcionó (03_post_login.png)")
    print("Con eso construyo el extractor real (Etapa 3).")


if __name__ == "__main__":
    main()
