#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualiza los datos de productos embebidos en index.html.

Reescribe el bloque de datos <script id="catalog"> dentro de index.html y el tipo de
cambio de Intcomex (₡ por US$) en la constante FX de la tienda.

FUENTES:
  - El COSTO real de Intcomex (sin IVA, sin margen) por SKU sale de la matriz interna
    (xlsx), columna "Costo Intcomex USD". Esa es la fuente de precios.
  - La estructura (categorías, títulos, imágenes, stock, enlaces) sale del catálogo
    HTML de referencia, emparejando por SKU.

OJO: el precio que se ve en el catálogo HTML NO es el costo: es "Precio EBS +15%"
(costo * 1.15, un esquema viejo). Por eso el costo se toma de la matriz; si no está
openpyxl o la matriz, se usa como respaldo precio_catálogo / 1.15.

La tienda recalcula en vivo el precio final al cliente = costo * 1.30 * 1.13 =
costo * 1.469 (margen 30% y luego IVA 13%). El IVA que EBS paga al proveedor es
crédito fiscal (se recupera), así que no entra en el costo.

Uso:
    python actualizar_datos.py
    python actualizar_datos.py --src otro_catalogo.html

Para reflejar precios/stock nuevos: reemplaza el catálogo de referencia por un
export actualizado de Intcomex (mismo formato de tarjetas) y vuelve a correr esto.
"""
import re, json, html as htmlmod, argparse, os, sys

IMG_BASE = "https://store.intcomex.com/images/products/"
MARKUP_CATALOGO = 1.15  # el catálogo HTML trae costo * 1.15 (respaldo si falta la matriz)

def load_matrix_costs(path):
    """Costo real de Intcomex por SKU (columna 'Costo Intcomex USD' de la matriz xlsx).
    Devuelve {SKU: costo_usd}. Si no está openpyxl o el archivo, devuelve {} y el
    llamador cae al respaldo (precio_catálogo / 1.15)."""
    try:
        import openpyxl
    except ImportError:
        print("Aviso: openpyxl no instalado; uso precio_catálogo / 1.15 como costo.")
        return {}
    if not os.path.exists(path):
        print("Aviso: no se encontró la matriz:", path)
        return {}
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Productos"]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    iSKU, iCost = hdr.index("SKU"), hdr.index("Costo Intcomex USD")
    costs = {}
    for r in rows:
        if r[iSKU] is not None and isinstance(r[iCost], (int, float)):
            costs[str(r[iSKU]).strip()] = float(r[iCost])
    return costs

def parse_catalog(path, costs):
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
            # El precio del catálogo HTML es "Precio EBS +15%" (= costo * 1.15), NO el costo.
            # price-usd / price-crc se conservan solo para derivar el tipo de cambio (su ratio).
            try:
                cat_usd = float(g(r"price-usd'>US\$\s*([0-9.,]+)").replace(",", ""))
            except ValueError:
                cat_usd = 0.0
            try:
                cat_crc = float(re.sub(r"[^0-9]", "", g(r"price-crc'>[^0-9]*([0-9.,]+)")))
            except ValueError:
                cat_crc = 0.0
            try:
                stock = int(g(r"class='stock'>Stock:\s*([0-9]+)"))
            except ValueError:
                stock = 0
            # Costo real de Intcomex desde la matriz; respaldo: precio_catálogo / 1.15.
            cost = costs.get(sku)
            if cost is None:
                cost = cat_usd / MARKUP_CATALOGO if cat_usd else 0.0
            products.append({
                "cat": cat,
                "brand": g(r"class='brand'>(.*?)</div>"),
                "title": title, "sku": sku, "mpn": mpn,
                "cost": round(cost, 4),
                "usd": cat_usd, "crc": cat_crc,
                "stock": stock,
                "img": g(r"img-wrap'><img src='([^']*)'"),
                "detail": g(r"product-link'><a href='([^']*)'"),
            })
    return products

def derive_fx(products, default=456.0):
    """Tipo de cambio de Intcomex (₡ por US$), deducido de los pares USD/CRC del
    catálogo. Los CRC vienen redondeados a centenas, así que se elige el factor que
    mejor reproduce esos CRC (mínimo error de redondeo) en una rejilla de 0.1."""
    pairs = [(p["usd"], p["crc"]) for p in products if p.get("usd") and p.get("crc")]
    if not pairs:
        return default
    best_fx, best_err = default, None
    fx = 400.0
    while fx <= 700.0:
        err = sum(abs(round(u * fx / 100) * 100 - c) for u, c in pairs)
        if best_err is None or err < best_err:
            best_fx, best_err = round(fx, 1), err
        fx = round(fx + 0.1, 1)
    return best_fx

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
    ap.add_argument("--matriz", default=os.path.join(here, "docs-referencia", "matriz_interna_costa_rica_ebs_intcomex_706_precio15.xlsx"))
    ap.add_argument("--out", default=os.path.join(here, "index.html"))
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit("No se encontró el catálogo de referencia: " + a.src)
    if not os.path.exists(a.out):
        sys.exit("No se encontró la tienda: " + a.out)

    costs = load_matrix_costs(a.matriz)
    print("Costos de Intcomex desde la matriz:", len(costs), "SKU")
    products = parse_catalog(a.src, costs)
    usados = sum(1 for p in products if p["sku"] in costs)
    print("Productos leídos:", len(products),
          "| costo desde matriz:", usados,
          "| respaldo /1.15:", len(products) - usados,
          "| en stock:", sum(1 for p in products if p["stock"] > 0))
    fx = derive_fx(products)
    print("Tipo de cambio Intcomex (derivado):", fx, "CRC/USD")
    data = json.dumps(build_data(products), ensure_ascii=False, separators=(",", ":"))

    html = open(a.out, encoding="utf-8").read()
    # repl es función → el valor se inserta literal (sin procesar backslashes)
    new_html, n = re.subn(
        r'(<script id="catalog" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + data + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit("No se pudo localizar el bloque <script id=\"catalog\"> en la tienda.")
    # inyecta el tipo de cambio de Intcomex en la constante FX y en la nota del pie
    new_html, nfx = re.subn(r'(var FX = )[0-9.]+(;)',
                            lambda m: m.group(1) + str(fx) + m.group(2),
                            new_html, count=1)
    new_html = re.sub(r'(<span id="fxnote">)[^<]*(</span>)',
                      lambda m: m.group(1) + ("%.1f" % fx).replace(".", ",") + m.group(2),
                      new_html, count=1)
    if nfx != 1:
        print("Aviso: no se pudo actualizar la constante FX en la tienda.")
    open(a.out, "w", encoding="utf-8").write(new_html)
    print("Actualizado:", a.out, "(", len(data.encode("utf-8")), "bytes de datos )")

if __name__ == "__main__":
    main()
