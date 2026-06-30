# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, customer-facing web store for **Costa Rica EBS (Enterprise Business Solutions)**, a Costa Rican reseller of Intcomex products. There is no build tooling, framework, package manager, or test suite — deliverables are self-contained static `.html` files (inline `<style>`/`<script>`, images either remote URLs or embedded data URIs) meant to open directly in a browser and be printable as a catalog (`@page` rules target US Letter landscape).

`index.html` (the deliverable from `requerimiento.txt`, originally named `tienda-intcomex.html`) is the live **customer-facing store**: a minimalist, premium single page (modern-minimal Hallmark build) with search, category/brand filters, sort, in-stock toggle, and a product grid covering **the full Intcomex catalog** (~2014 products as of 2026-06-29). The products are embedded as compact JSON in a `<script id="catalog">` block; the page recomputes the final price **live** in JS (`cost × 1.469`, CRC at a `FX` constant derived live from Intcomex — currently 459.01/USD), so updating cost+stock is enough to refresh prices.

**Product count is dynamic, not fixed.** The store mirrors whatever Intcomex's store has on the day it's scraped — the count rises and falls between runs (was 706 in the original reference catalog; ~2014 now). That is intentional and expected; never treat a specific number as "the" correct count or "fix" it back to 706.

### Refreshing store data (ACTIVE pipeline: the Intcomex scraper)

The live store is kept current by a **Playwright scraper in `scraper/`** that logs into the Intcomex partner portal, crawls the whole catalog, reads each product's **partner cost (costo de socio) and stock**, and rewrites the `<script id="catalog">` block in `index.html`. A Windows scheduled task runs it daily at 06:00 and pushes the result to GitHub Pages. Full operational guide: [`OPERACION.md`](OPERACION.md) and [`scraper/README.md`](scraper/README.md).

```powershell
# Full run (crawl whole store + commit/push index.html) — what the daily task runs:
cd scraper; powershell -ExecutionPolicy Bypass -File .\run_scrape.ps1
# Or just refresh prices/stock (no publish):
.\.venv\Scripts\python.exe scrape_intcomex.py --crawl
```

The store then applies margin + IVA on top of the scraped cost (`cost × 1.469`, computed live in JS), and the `FX` rate is read live from Intcomex (`scrape_fx`). Key operational gotchas:

- **Session is short-lived (~40 min).** When the log says the session expired (or every category shows `acumulado: 0` / `TC 456.0`), renew it once with `.\.venv\Scripts\python.exe scrape_intcomex.py --login` (manual captcha) and run the crawl **immediately after** — login and crawl must be back-to-back.
- `do_crawl` is resilient to slow pages (retries once, then skips that category and continues) so one timeout doesn't abort the whole ~20-min run.

**Legacy / backup pipeline (`actualizar_datos.py` + Excel matrix).** Before the scraper, the store was rebuilt from the static reference catalog in `docs-referencia/` (706 SKUs), with cost sourced from the `Costo Intcomex USD` column of `matriz_interna_..._706_precio15.xlsx` (sheet `Productos`). This is **no longer the active source** — keep it only as a fallback/reference. If you ever use it: the HTML catalog's `price-usd` is `Precio EBS +15%` (`cost × 1.15`), **not** the cost; sourcing cost from the catalog price silently strips the margin (a bug that already happened twice). Source cost from the matrix, never the catalog price.

## Pricing formula (critical — get this exact)

The Intcomex cost is in **USD**. The IVA that EBS pays the supplier is **crédito fiscal** (recoverable — not a real cost), so the cost base used to set the price is the **bare cost**, with margin then IVA on top:

```
SubTotal = cost × 1.30          # 30% margin (no IVA yet)
IVA      = SubTotal × 0.13      # 13% IVA charged to the client (débito fiscal)
Total    = SubTotal + IVA       # = cost × 1.30 × 1.13 = cost × 1.469
```

Example: cost 1000 → SubTotal 1300 → IVA 169 → **Total 1469**. The IVA is applied to `cost + margin`, not to the bare cost; do not "simplify" this. The store recompute lives in `index.html` as `FACTOR = 1.30 × 1.13 = 1.469`; updating cost+stock is enough to refresh prices.

Note: the `cost` is the real Intcomex **partner price (costo de socio)** — now read live per product by the scraper (formerly the matrix `Costo Intcomex USD`) — which is **without IVA and without margin** (Intcomex is wholesale; that's what EBS pays). The final client price `cost × 1.469` is computed live in the store. Do **not** use any displayed `Precio EBS +15%` value as cost — it already carries an old `× 1.15` markup.

### Exchange rate (CRC)
Each price is shown in **USD and CRC**, using **Intcomex's own exchange rate** (`FX` in `index.html`, currently **459.01 ₡/US$**). The rate is not invented: the scraper reads it live from Intcomex (`scrape_fx`) and injects it into the `var FX` constant and footer note on each run (the legacy `actualizar_datos.py` derived it instead by comparing each reference product's USD vs rounded-CRC prices). Re-run the scraper to refresh the rate along with prices/stock.

## Data source

Prices and stock come from the Intcomex Costa Rica store and must be kept current:
- https://store.intcomex.com/es-XCR/Home
- Partner/login code: `@Enterprise2025`
- Each product card links back to its Intcomex detail page (`store.intcomex.com/es-XCR/Product/Detail/<id>`).

Contact shown on the page: `contacto@costaricaebs.com`.

## Design reference

`docs-referencia/catalogo_costa_rica_ebs_cliente_final_con_fotos.html` is the canonical **visual reference** (it contains the original 706 products across 46 categories). Match its look and structure rather than inventing a new design. **Product data now comes from the live scraper, not this file** — don't reuse its embedded products as the catalog source. Page structure: cover page → company page → table-of-contents page → 46 `catalog-section`s, each with a `cat-header` and a `product-grid`. Categories are named `"Major - Sub"` (e.g. `Almacenamiento - Discos de Estado Sólido Internos`).

Key conventions in it:

- **Palette** (CSS `:root`): navy backgrounds `--bg:#07152a`/`--bg2:#0b2346`, cyan accent `--cyan:#37b8ff`/`--accent:#00b7ff`, gold `--gold:#f3c84b`; product area sits on light `#f4f7fb`.
- **Product grid**: `.product-grid` is a 4-column CSS grid of `.card` elements. A card contains `.img-wrap` (with an `onerror` fallback to a branded `.img-placeholder`), then `.card-body` → `.brand`, `.title`, `.sku` (SKU + MPN), and a `.price-block` showing `.price-usd`, `.price-crc`, `.stock`, and a "Ver detalle del producto" link.
- Prices are shown in both **USD and CRC** (`₡`); stock as `Stock: N unidades`.
- Microsoft-partner four-square mark (`.ms-squares`) and EBS logo appear in the branding header.
- Assets live in `img/`. The live store (`index.html`) only needs `img/logo-costa-rica-ebs.gif` (header logo, links to https://costaricaebs.com/); product/background images are loaded remotely. Orphaned local assets (old `logoEBS-150x150.png`, backgrounds) were removed.

## Working notes

- No commands to build/lint/test — verify by opening the HTML in a browser (and via print preview for catalog layout).
- The reference HTML is ~2.9MB (embedded data-URI images); don't dump it whole. Use `grep`/`sed` to slice it, or **Python 3.11** (available on PATH) to parse its product cards into structured data.
- The active data source is the **scraper** (`scraper/scrape_intcomex.py`, Playwright + its `.venv`); it reads partner cost + stock live and rewrites `index.html`. See [`OPERACION.md`](OPERACION.md) / [`scraper/README.md`](scraper/README.md). The scraper's `.env` and `storage_state.json` hold credentials/session and are gitignored — never commit them.
- `docs-referencia/matriz_interna_costa_rica_ebs_intcomex_706_precio15.xlsx` is the **legacy cost source** (706 SKUs): sheet `Productos`, column `Costo Intcomex USD`. Only relevant if falling back to `actualizar_datos.py` (reads it via `openpyxl`); the live store no longer uses it.
- Keep everything in Spanish (the audience is Costa Rican clients).
