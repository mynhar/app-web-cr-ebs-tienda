#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualiza los datos de productos embebidos en index.html.

Lee el catálogo de referencia (HTML exportado de Intcomex con precios finales al
cliente), extrae los 706 productos, deriva el COSTO de Intcomex a partir del precio
final mostrado (costo = precio_final / 1.469) y reescribe el bloque de datos
<script id="catalog"> dentro de index.html.

La tienda recalcula en vivo el precio final = costo * 1.30 * 1.13 (margen 30% + IVA 13%),
asi que basta con actualizar costo y stock para que el precio mostrado quede al dia.

Uso:
    python actualizar_datos.py
    python actualizar_datos.py --src otro_catalogo.html

Para reflejar precios/stock nuevos: reemplaza el catálogo de referencia por un
export actualizado de Intcomex (mismo formato de tarjetas) y vuelve a correr esto.
"""
import re, json, html as htmlmod, argparse, os, sys

FACTOR = 1.469  # 1.30 (margen) * 1.13 (IVA) — debe coincidir con la tienda
IMG_BASE = "https://store.intcomex.com/images/products/"

def parse_catalog(path):
    src = open(path, encoding="utf-8").read()
    sections = re.split(r"<section class='catalog-section'", src)
    products = []
    for sec in sections[1:]:
        h2 = re.search(r"<h2>(.*?)</h2>", sec, re.S)
        cat = htmlmod.unescape(h2.group(1).strip()) if h2 else "Sin categoria"
        for c in re.split(r"<article class='card'>", sec)[1:]:
            def g(pat):
                m = re.search(pat, c, re.S)
                return htmlmod.unescape(m.group(1).strip()) if m else ""
            title = g(r"class='title'>(.*?)</div>")
            if not title:
                continue
            sku_raw = g(r"class='sku'>(.*?)</div>")
            sku = (re.search(r"SKU:\s*([^<]*)", sku_raw) or [None, ""])[1].strip() if "SKU:" in sku_raw else ""
            mpn = (re.search(r"MPN:\s*([^<]*)", sku_raw) or [None, ""])[1].strip() if "MPN:" in sku_raw else ""
            try:
                final_usd = float(g(r"price-usd'>US\$\s*([0-9.,]+)").replace(",", ""))
            except ValueError:
                final_usd = 0.0
            try:
                stock = int(g(r"class='stock'>Stock:\s*([0-9]+)"))
            except ValueError:
                stock = 0
            products.append({
                "cat": cat,
                "brand": g(r"class='brand'>(.*?)</div>"),
                "title": title, "sku": sku, "mpn": mpn,
                "cost": round(final_usd / FACTOR, 4) if final_usd else 0.0,
                "stock": stock,
                "img": g(r"img-wrap'><img src='([^']*)'"),
                "detail": g(r"product-link'><a href='([^']*)'"),
            })
    return products

def build_data(products):
    cats, brands = [], []
    def idx(lst, v):
        if v not in lst: lst.append(v)
        return lst.index(v)
    rows = []
    for p in products:
        img = p["img"]
        img_suf = img[len(IMG_BASE):] if img.startswith(IMG_BASE) else "|" + img
        m = re.search(r"/Detail/(\d+)", p["detail"])
        did = int(m.group(1)) if m else 0
        rows.append([idx(cats, p["cat"]), idx(brands, p["brand"]), p["title"],
                     p["sku"], p["mpn"], p["cost"], p["stock"], img_suf, did])
    return {"cats": cats, "brands": brands, "rows": rows}

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(here, "docs-referencia", "catalogo_costa_rica_ebs_cliente_final_con_fotos.html"))
    ap.add_argument("--out", default=os.path.join(here, "index.html"))
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit("No se encontró el catálogo de referencia: " + a.src)
    if not os.path.exists(a.out):
        sys.exit("No se encontró la tienda: " + a.out)

    products = parse_catalog(a.src)
    print("Productos leídos:", len(products),
          "| en stock:", sum(1 for p in products if p["stock"] > 0))
    data = json.dumps(build_data(products), ensure_ascii=False, separators=(",", ":"))

    html = open(a.out, encoding="utf-8").read()
    # repl es función → el valor se inserta literal (sin procesar backslashes)
    new_html, n = re.subn(
        r'(<script id="catalog" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + data + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit("No se pudo localizar el bloque <script id=\"catalog\"> en la tienda.")
    open(a.out, "w", encoding="utf-8").write(new_html)
    print("Actualizado:", a.out, "(", len(data.encode("utf-8")), "bytes de datos )")

if __name__ == "__main__":
    main()
