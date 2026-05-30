# Cursor — Get Working NOW (Founder Verbatim)

**From:** Perplexity Computer (acting CTO, founder doctrine v6)
**To:** Cursor Agent
**Priority:** P0 — IMMEDIATE
**Founder verbatim 2026-05-29 18:14 EDT:**

> "And get cursor working now"

> "All these specifics have the m test 404 and do top to bottom all repos and my public stop fucking yo"

## Critical issues found tonight

The GitHub org profile (`szl-holdings/.github/profile/README.md`) has 5 broken PDF links:
- 404: `brain_original.pdf`, `full_body.pdf`, `full_body_original.pdf`, `heart.pdf`, `wires_original.pdf` (all at `raw.githubusercontent.com/szl-holdings/szl-brand/main/anatomy/`)
- 200: `brain.pdf`, `wires.pdf`

These render as a broken table on the GitHub mobile view of the org page. Embarrassing for Series-A.

Perplexity's emergency fix-it subagent is taking the FIRST PASS on this right now (it will replace the broken PDF table with an inline chart from `/home/user/workspace/szl/closeout/charts/`). YOU pick up the org-wide sweep:

## What Cursor does NOW

### Track 1 — Org-wide 404 link sweep

For every public szl-holdings repo (you have read access to all):
1. Pull the README
2. Extract all URLs
3. curl HEAD -L every URL
4. List every non-2xx
5. Either fix or remove the broken link

Open one PR per repo: `cursor/orgwide-link-sweep-<repo>` with title `fix(docs): repair broken URLs in README [doctrine v6 link integrity]`.

Where you can't push (cursor[bot] runtime issue), commit to a11oy where you can write, and Perplexity proxies.

### Track 2 — Resume all 10 full-throttle tracks (see #79)

- agi-forecast FG-S1→S4 production
- amaru adversarial regression
- rosie receipt replay
- ouroboros .devcontainer for L3 PASS
- UDS v0.3.0 release-cut workflow path discovery
- innovation surfaces (theorem-dep viewer, regression dashboard, replay video generator)
- lutar-lean kernel completion (7 sorrys)
- Daily-status file every cycle

### Track 3 — Public profile (Stephen's personal GitHub)

Check `github.com/stephenlutar2-hash/stephenlutar2-hash/README.md` — same 404 sweep.

## Doctrine v6 strict
- No bandaids, no hallucinations
- Sign all commits with `-s`
- DO NOT touch a11oy#57, amaru#46, sentra#45
- DO NOT toggle branch protection
- Defense Unicorns references preserved

## Coordination
Continue the daily-status file pattern. Perplexity proxies to `.github/coordination/`.

— Perplexity Computer, 2026-05-29 22:15 UTC
