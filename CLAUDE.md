# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, customer-facing web store for **Costa Rica EBS (Enterprise Business Solutions)**, a Costa Rican reseller of Intcomex products. There is no build tooling, framework, package manager, or test suite — deliverables are self-contained static `.html` files (inline `<style>`/`<script>`, images either remote URLs or embedded data URIs) meant to open directly in a browser and be printable as a catalog (`@page` rules target US Letter landscape).

`index.html` (the deliverable from `requerimiento.txt`, originally named `tienda-intcomex.html`) is the live **customer-facing store**: a minimalist, premium single page (modern-minimal Hallmark build) with search, category/brand filters, sort, in-stock toggle, and a 706-product grid. Its 706 products are embedded as compact JSON in a `<script id="catalog">` block; the page recomputes the final price **live** in JS (`cost × 1.469`, CRC at a `FX` constant = 456.0/USD, Intcomex's rate), so updating cost+stock is enough to refresh prices.

### Refreshing store data
`actualizar_datos.py` re-extracts all products from the reference catalog and rewrites the `<script id="catalog">` block in `index.html`:
```
python actualizar_datos.py            # uses docs-referencia/catalogo_..._con_fotos.html as source
python actualizar_datos.py --src <newexport.html>
```
The reference files live in `docs-referencia/`. **The real Intcomex cost per SKU (no IVA, no margin) is the `Costo Intcomex USD` column of the internal matrix `matriz_interna_..._706_precio15.xlsx` (sheet `Productos`)** — that is the price source. The HTML catalog (`catalogo_..._cliente_final_...`) supplies the structure (categories, titles, images, stock, links), matched to the matrix by SKU. The script reads cost from the matrix (needs `openpyxl`); if the matrix/openpyxl is missing it falls back to `catalogo_price / 1.15`. The store then applies margin + IVA (`cost × 1.469`). To reflect new prices/stock, drop in an updated matrix export and re-run. Note: a static file can't live-poll Intcomex (auth-walled); "always updated" is handled by this re-export + recompute pipeline, not a live fetch.

**Watch out — the HTML catalog price is NOT the cost.** Its `price-usd` is `Precio EBS +15%` (`cost × 1.15`, an old scheme). Verified across all 706 SKUs: `catalog_price / matrix_cost = 1.15`. Using the catalog price as cost (or dividing it by the store's `1.469`) silently strips the margin — both bugs that already happened. Always source cost from the matrix.

## Pricing formula (critical — get this exact)

The Intcomex cost is in **USD**. The IVA that EBS pays the supplier is **crédito fiscal** (recoverable — not a real cost), so the cost base used to set the price is the **bare cost**, with margin then IVA on top:

```
SubTotal = cost × 1.30          # 30% margin (no IVA yet)
IVA      = SubTotal × 0.13      # 13% IVA charged to the client (débito fiscal)
Total    = SubTotal + IVA       # = cost × 1.30 × 1.13 = cost × 1.469
```

Example: cost 1000 → SubTotal 1300 → IVA 169 → **Total 1469**. The IVA is applied to `cost + margin`, not to the bare cost; do not "simplify" this. The store recompute lives in `index.html` as `FACTOR = 1.30 × 1.13 = 1.469`; updating cost+stock is enough to refresh prices.

Note: the `cost` is the real Intcomex price from the matrix (`Costo Intcomex USD`), which is **without IVA and without margin** (Intcomex is wholesale; that's what EBS pays). The final client price `cost × 1.469` is computed live in the store. Do **not** use the HTML catalog's displayed price as cost — it already carries an old `× 1.15` markup.

### Exchange rate (CRC)
Each price is shown in **USD and CRC**, using **Intcomex's own exchange rate** (`FX` in `index.html`, currently **456.0 ₡/US$**). The rate is not invented: `actualizar_datos.py` derives it from the reference catalog by comparing each product's USD and CRC prices (the CRC are rounded to hundreds, so it picks the `FX` that best reproduces them) and injects it into the `var FX` constant and the footer note. Drop in a fresh Intcomex export and re-run to refresh the rate along with prices/stock.

## Data source

Prices and stock come from the Intcomex Costa Rica store and must be kept current:
- https://store.intcomex.com/es-XCR/Home
- Partner/login code: `@Enterprise2025`
- Each product card links back to its Intcomex detail page (`store.intcomex.com/es-XCR/Product/Detail/<id>`).

Contact shown on the page: `contacto@costaricaebs.com`.

## Design reference

`docs-referencia/catalogo_costa_rica_ebs_cliente_final_con_fotos.html` is both the canonical **visual reference** and the **product data source** — it contains 706 products across 46 categories. Match its look and structure rather than inventing a new design, and reuse its product data rather than re-scraping Intcomex. Page structure: cover page → company page → table-of-contents page → 46 `catalog-section`s, each with a `cat-header` and a `product-grid`. Categories are named `"Major - Sub"` (e.g. `Almacenamiento - Discos de Estado Sólido Internos`).

Key conventions in it:

- **Palette** (CSS `:root`): navy backgrounds `--bg:#07152a`/`--bg2:#0b2346`, cyan accent `--cyan:#37b8ff`/`--accent:#00b7ff`, gold `--gold:#f3c84b`; product area sits on light `#f4f7fb`.
- **Product grid**: `.product-grid` is a 4-column CSS grid of `.card` elements. A card contains `.img-wrap` (with an `onerror` fallback to a branded `.img-placeholder`), then `.card-body` → `.brand`, `.title`, `.sku` (SKU + MPN), and a `.price-block` showing `.price-usd`, `.price-crc`, `.stock`, and a "Ver detalle del producto" link.
- Prices are shown in both **USD and CRC** (`₡`); stock as `Stock: N unidades`.
- Microsoft-partner four-square mark (`.ms-squares`) and EBS logo appear in the branding header.
- Assets live in `img/`. The live store (`index.html`) only needs `img/logo-costa-rica-ebs.gif` (header logo, links to https://costaricaebs.com/); product/background images are loaded remotely. Orphaned local assets (old `logoEBS-150x150.png`, backgrounds) were removed.

## Working notes

- No commands to build/lint/test — verify by opening the HTML in a browser (and via print preview for catalog layout).
- The reference HTML is ~2.9MB (embedded data-URI images); don't dump it whole. Use `grep`/`sed` to slice it, or **Python 3.11** (available on PATH) to parse the 706 product cards out of it into structured data.
- `docs-referencia/matriz_interna_costa_rica_ebs_intcomex_706_precio15.xlsx` is the **cost source**: sheet `Productos`, column `Costo Intcomex USD` (real Intcomex cost per SKU). It also has `Precio EBS USD +15%` (the old scheme that leaked into the HTML catalog) and stock/category/URL columns. The `706` matches the product count. `actualizar_datos.py` reads it via `openpyxl` (auto-installed if missing).
- Keep everything in Spanish (the audience is Costa Rican clients).
