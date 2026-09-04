# Vertical fashion audit — 2026-09-04

Rule: take the *job* the field leader already won. Do not take their name, UI chrome, datasets, or proprietary code. SZL cut is always deny-by-default + signed receipts + SAMPLE/UNAVAILABLE honesty + Λ-gate. Silhouettes, never counterfeits. Apache-2.0/MIT ideas get a NOTICE. Closed-source products are read for the job only.

Authority maps already in-repo:
- `szl-vertical-forge/src/szl_vertical_forge/verticals.json` (8 lanes + lineage)
- `szl-constellation/docs/FRONTIER-BOARD.md` (what shipped vs seeded)
- `.github/docs/CANONICAL_FLEET.md` (public seven — older than the 8-lane map)
- `platform/replit-sync/NEXT_ORDER.md` (ops, not product design)

## Naming drift to close

| Name in one map | Name in another | Decision |
|---|---|---|
| sentra (forge + HF Space) | aegis (constellation note) | Keep **Sentra**. Aegis is a hologram label. |
| vessels (vertical-services + HF Space) | folded into killinchu (forge) | Keep **Vessels** as a maritime desk under the killinchu estate, not a ninth flagship. |
| counsel GitHub archive | ayllu canonical + HF counsel | Product is **Ayllu**. Space may stay `counsel`. |
| public seven includes atelier/anatomy | 8-lane forge does not | Anatomy stays a substrate viz. Atelier is forge-walker, not a vertical. |

## Lane by lane

### Killinchu — defense / C-UAS
Meat: `killinchu`, `khipu-sda-core`/`sda` if present, HF `KILLINCHU-EYE`/`chaski`, dataset `killinchu-osint-corpus`.
Leader job: Anduril Lattice — fuse sensors, compress the kill chain ([JIATF-401 / Lattice](https://www.anduril.com/news/jiatf-401-selects-lattice-as-enterprise-tactical-command-and-control-platform-for-c-uas)).
SZL cut: public synthetic tracks + ROE + DSSE per interdiction. **No public effector.**
Do not: clone Lattice UI, claim live effector, invent tracks.

### Sentra — assurance / policy gates
Meat: `immune` (YAWAR chain), `vertical-services/services/sentra`, kernels `szl-govsign`/`szl-provctl`, models `szl-govsign`/`szl-provctl`.
Leader job: Credo Agent Registry + Agent Governor (harness-time policy) and CrowdStrike Baywatch (allow / log / escalate / deny).
SZL cut: eight-gate deny-by-default + HMAC/DSSE verdict, not a compliance dashboard.

### PURIQ — formula governance
Meat: `puriq-live`, `canonical-formulas-v1`, models `khipu-r3`/`szl-governed-norm`.
Leader job: none. Category is invented here.
SZL cut: execute the corpus against public signals; Yuyay-13 fail-closed; never mint a fake Λ.

### Terra — public-records underwriting
Meat: `szl-real-estate` (PLUTO MEASURED on Kings/Queens; Nassau has no PLUTO), `vertical-services/services/terra`.
Leader job: Regrid national parcels + MCP. Official source: NYC PLUTO 26v2.
SZL cut: observations stay separate from models. Occupancy UNAVAILABLE unless measured. Not an MLS.

### Lyte — observability / factory cell
Meat: `lyte-services`, `lyte-lattice`, `a11oy-factory`, `szl-ouroboros`.
Leader job: Grafana + OpenTelemetry collect/export.
SZL cut: bounded loop-tax + receipted spans. Drift-z is SAMPLE until a live exporter is wired.

### Counsel / Ayllu — governed advisory
Meat: `ayllu` (11 Quechua seats), doctrine datasets, models `WILLAY`/`chaski-r2` if published.
Leader job: Harvey + Thomson Reuters CoCounsel — agentic legal work grounded in an authority stack.
SZL cut: debate-then-converge council, fail-closed Λ, no PACER, no legal advice, LICENSE_REQUIRED is a hard block.

### Finance — paper portfolio
Meat: `szl-quant`, `szl-quant-witness`, `vertical-services/services/finance`, dataset `szl-quant-sft-v1`.
Leader job: QuantConnect LEAN (engine) + Riskfolio-Lib (risk overlays, Peru-origin OSS).
SZL cut: paper-only, DSSE per signal, not financial advice. SAMPLE book is not an exchange feed.

### David Leads — evidence-backed revenue
Meat: `david-leads` repo + Space, model `brain-navigator-r2`.
Leader job: category owned here. Comparable surfaces are Apollo/ZoomInfo; we do not scrape their graphs.
SZL cut: official-source only. Every lead carries an evidence trail or it does not exist.

### Vessels — maritime desk (under killinchu)
Meat: `vertical-services/services/vessels` only. No dedicated estate repo.
Leader job: Windward Maritime AI — dark activity, AIS gaps, multi-sensor picture.
SZL cut: four flags (dark / speed / corridor / loiter) on a SAMPLE book. Do not claim live AIS or EO/SAR.

## Shared estate (not a vertical)

a11oy command center, anatomy organs, szl-substrate, szl-kernels, hatun-mcp, szl-frontier, szl-forge, szl-khipu, benches (`szl-engine-bench`, `szl-retrieval-bench`, `szl-quant-bench`, `szl-calibration`, `szl-crosscheck`, `szl-eclipse`, `szl-ci-witness`, `szl-pin`). These are the house atelier. Verticals consume them; they do not become ninth products.

## HF models that already bind

`SZL-Khipu-1.5B`, `SZL-Forge-1.5B-ReceiptAgent`, `szl-receiptagent-qwen35-0.8b-v3`, `A11OY-MINI`, `chaski`, `khipu-r3`, `szl-govsign`, `szl-provctl`, `TinyKhipu-Nano`, `brain-navigator-r2`.

Wire those handles. Do not invent a new weights file per vertical.

## Focus rule for the next merge

1. One vertical, one canonical GitHub repo, one Space name.
2. Steal the job sentence from the leader. Rewrite the mechanism in SZL formulas.
3. If the data is not MEASURED, label SAMPLE or UNAVAILABLE.
4. HF rebuild stays owner-gated. GitHub is the source of truth until a write token exists.
