# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, customer-facing web store for **Costa Rica EBS (Enterprise Business Solutions)**, a Costa Rican reseller of Intcomex products. There is no build tooling, framework, package manager, or test suite — deliverables are self-contained static `.html` files (inline `<style>`/`<script>`, images either remote URLs or embedded data URIs) meant to open directly in a browser and be printable as a catalog (`@page` rules target US Letter landscape).

`index.html` (the deliverable from `requerimiento.txt`, originally named `tienda-intcomex.html`) is the live **customer-facing store**: a minimalist, premium single page (modern-minimal Hallmark build) with search, category/brand filters, sort, in-stock toggle, and a 706-product grid. Its 706 products are embedded as compact JSON in a `<script id="catalog">` block; the page recomputes the final price **live** in JS (`cost × 1.469`, CRC at a `FX` constant ≈ 456.5/USD), so updating cost+stock is enough to refresh prices.

### Refreshing store data
`actualizar_datos.py` re-extracts all products from the reference catalog and rewrites the `<script id="catalog">` block in `index.html`:
```
python actualizar_datos.py            # uses catalogo_..._con_fotos.html as source
python actualizar_datos.py --src <newexport.html>
```
The reference catalog shows **final client prices**, so the script derives cost = `finalUSD / 1.469`. To reflect new Intcomex prices/stock, drop in an updated catalog export (same card markup) and re-run. Note: a static file can't live-poll Intcomex (auth-walled); "always updated" is handled by this re-export + recompute pipeline, not a live fetch.

## Pricing formula (critical — get this exact)

The Intcomex cost is in **USD**. The final customer price for Costa Rica is computed as:

```
SubTotal = cost × 1.30          # 30% margin
IVA      = SubTotal × 0.13      # 13% IVA, applied on cost+margin — NOT on bare cost
Total    = SubTotal + IVA       # = cost × 1.30 × 1.13 = cost × 1.469
```

Example: cost 1000 → SubTotal 1300 → IVA 169 → **Total 1469**. The IVA is deliberately applied to `cost + margin`, not to the bare cost; do not "simplify" this.

Note: the prices already shown in the reference catalog (`..._cliente_final_...`) are **final client prices** (`cost × 1.469`), not raw Intcomex cost. To recover cost from them, divide by `1.469`.

## Data source

Prices and stock come from the Intcomex Costa Rica store and must be kept current:
- https://store.intcomex.com/es-XCR/Home
- Partner/login code: `@Enterprise2025`
- Each product card links back to its Intcomex detail page (`store.intcomex.com/es-XCR/Product/Detail/<id>`).

Contact shown on the page: `contacto@costaricaebs.com`.

## Design reference

`catalogo_costa_rica_ebs_cliente_final_con_fotos.html` is both the canonical **visual reference** and the **product data source** — it contains 706 products across 46 categories. Match its look and structure rather than inventing a new design, and reuse its product data rather than re-scraping Intcomex. Page structure: cover page → company page → table-of-contents page → 46 `catalog-section`s, each with a `cat-header` and a `product-grid`. Categories are named `"Major - Sub"` (e.g. `Almacenamiento - Discos de Estado Sólido Internos`).

Key conventions in it:

- **Palette** (CSS `:root`): navy backgrounds `--bg:#07152a`/`--bg2:#0b2346`, cyan accent `--cyan:#37b8ff`/`--accent:#00b7ff`, gold `--gold:#f3c84b`; product area sits on light `#f4f7fb`.
- **Product grid**: `.product-grid` is a 4-column CSS grid of `.card` elements. A card contains `.img-wrap` (with an `onerror` fallback to a branded `.img-placeholder`), then `.card-body` → `.brand`, `.title`, `.sku` (SKU + MPN), and a `.price-block` showing `.price-usd`, `.price-crc`, `.stock`, and a "Ver detalle del producto" link.
- Prices are shown in both **USD and CRC** (`₡`); stock as `Stock: N unidades`.
- Microsoft-partner four-square mark (`.ms-squares`) and EBS logo appear in the branding header.
- Assets live in `img/` (logo `logoEBS-150x150.png`, backgrounds, product photos).

## Working notes

- No commands to build/lint/test — verify by opening the HTML in a browser (and via print preview for catalog layout).
- The reference HTML is ~2.9MB (embedded data-URI images); don't dump it whole. Use `grep`/`sed` to slice it, or **Python 3.11** (available on PATH) to parse the 706 product cards out of it into structured data.
- `matriz_interna_costa_rica_ebs_intcomex_706_precio15.xlsx` is an internal pricing matrix (the `706` matches the product count), not part of the shipped page.
- Keep everything in Spanish (the audience is Costa Rican clients).
