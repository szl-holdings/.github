# Cursor Directive — Make the SZL Anatomy real and operational TODAY

**Founder mandate (verbatim, 2026-05-29 11:11 PDT):** "We want the anatomy real to make sure to ad fit cursor to"

**Priority:** P0 (same priority as the formulas directive; runs in parallel)

**Scope:** Turn the [szl-anatomy](https://huggingface.co/spaces/SZLHOLDINGS/szl-anatomy) Space from a beautiful diagram into a live, operational 7-organ control plane. Each organ becomes a real endpoint backed by real code emitting real telemetry.

---

## Current state (what exists)

- `SZLHOLDINGS/szl-anatomy` Space — static HTML with 7 organ sections, beautiful visuals, no live data
- Each organ has a metaphor (brain=amaru, heart=yuyay, blood=yawar, immune=huklla, skeleton=Λ-spine, nervous=otel, wires=kallpa) but no live signal
- 8 organ PNG images + 1 composed body graph already in `SZLHOLDINGS/szl-visual-identity`

## Target state (what "real" means)

Each of the 7 organs gets all 5 of these in production:

1. **A real HTTP endpoint** returning the organ's current live state as JSON
2. **A real metric** the endpoint serves (not a hardcoded number)
3. **A Lean theorem citation** anchoring the organ's invariant
4. **A DSSE-wrapped receipt** emitted on every endpoint hit
5. **A live tile** in the szl-anatomy Space pulling from the endpoint via fetch()

When done: an investor clicks any organ on the Space → JS fetches the live endpoint → sees real current data + the Lean theorem governing the organ + a DSSE receipt timestamp.

---

## The 7 organs (per-organ deliverable matrix)

| Organ | Component | Endpoint | Real metric | Lean theorem |
|---|---|---|---|---|
| Brain / amaru | `szl-holdings/amaru` | `/api/anatomy/brain` | 7-chakra scheduler current step + last-5 receipt SHAs | `Lutar/Composition/AdversarialRobustness` |
| Heart / yuyay | `szl-holdings/ouroboros` | `/api/anatomy/heart` | Current Λ-axis pulse (1 number ∈ [0,1]) + Ouroboros 32-module green-count | `Lutar/PACBayes/MadhavaBound` |
| Blood / yawar | `szl-holdings/uds-mesh` | `/api/anatomy/blood` | Total receipts emitted (lifetime) + receipts/min (last 60 min) | `Lutar/Khipu/SummationInvariant` |
| Immune / huklla | `szl-holdings/sentra` + `szl-holdings/a11oy` | `/api/anatomy/immune` | 6 gate states (each: open/closed) + 248 a11oy assertion green-count | `Lutar/Composition/AdversarialRobustness` |
| Skeleton / Λ-spine | `szl-holdings/lutar-lean` | `/api/anatomy/skeleton` | 76 theorems · 134 lake-verified · 241 skeleton · 1 residual sorry (live from theorems_index.json) | (the spine cites them all) |
| Nervous / otel | `szl-holdings/vsp-otel` | `/api/anatomy/nervous` | OTel exporter health + last span emit timestamp + 9 Λ-axis weights | `Lutar/Calibration/FalsePosition` |
| Wires / kallpa | `szl-holdings/uds-mesh` + `szl-holdings/rosie` | `/api/anatomy/wires` | Cross-component fabric health: 7-organ connectivity matrix | `Lutar/Banach/LiuHuiPi` |

---

## Coordination split

**Cursor owns (GitHub side):**
- Layer A: Implement the 7 endpoints in their canonical repos
  - `amaru/src/api/anatomy/brain.ts` (or .py — match repo's stack)
  - `ouroboros/src/api/anatomy/heart.py`
  - `uds-mesh/src/api/anatomy/blood.py` and `wires.py`
  - `sentra/src/api/anatomy/immune.ts` (or .py)
  - `lutar-lean/scripts/api/skeleton.py` (reads theorems_index.json)
  - `vsp-otel/src/api/anatomy/nervous.ts`
- Layer B: Make each endpoint emit a DSSE PAE v1 + HMAC-SHA-256 envelope on every hit (reuse the existing pattern from `uds-mesh`)
- Layer C: Add CI tests that hit each endpoint + assert the response shape

**Perplexity owns (HF side):**
- Layer D: Deploy the 7 endpoints as Gradio API routes on the existing `SZLHOLDINGS/<organ>-platform` Spaces (or a new `SZLHOLDINGS/szl-anatomy-api` Space if cross-component)
- Layer E: Update the `SZLHOLDINGS/szl-anatomy` Space's index.html to add JS `fetch()` calls to each endpoint, render the live tiles, and link the DSSE receipt + Lean theorem
- Layer F: Add OTel span emission per endpoint hit (so anatomy access is itself observable)

---

## Acceptance criteria (35/35)

A organ is "real" when all 5 boxes are ✓:

```
For each of 7 organs:
  [ ] A — HTTP endpoint returns real data (JSON, schema-validated, < 200ms)
  [ ] B — DSSE receipt emitted on every hit, signed
  [ ] C — Lean theorem cited in response + Space tile
  [ ] D — Live tile in szl-anatomy Space pulls from endpoint
  [ ] E — Real metric (not hardcoded), changes between hits
```

That's 35 boxes total. Target: end of day 2026-05-29.

---

## Doctrine v6 strict

- Real endpoints, real data, real DSSE — no stub responses
- No marketing superlatives in any commit or response
- Sign all commits with `-s`
- Use `gh pr merge --admin --squash` (founder pre-authorized)
- DO NOT touch: a11oy#57, amaru#46, sentra#45 (DRAFT relicense PRs)
- Honest "what this is NOT" preserved on the Space (no medical claims; the metaphor is visual framing only)

---

## Reporting

When Cursor finishes a layer, append to `szl-holdings/.github/coordination/daily-status-2026-05-29.md`:

```
[YYYY-MM-DD HH:MM UTC] cursor: anatomy organ <name> layer <A/B/C> shipped — PR #<num>
```

---

## Why this matters

Right now the anatomy is the most beautiful artifact in the SZL ecosystem and the LEAST operational. Making it real reverses that — it becomes the most operational AND the most visually-arresting. Bank meeting tomorrow + Warhacker June 16-20: a live, clickable anatomy where every organ has a real receipt is the "this is operational, not slideware" demo moment.

---

## Sign-off

Stephen Paul Lutar JR — Founder & CEO, SZL Holdings
2026-05-29 18:11 UTC
