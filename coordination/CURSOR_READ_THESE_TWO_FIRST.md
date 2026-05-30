# Cursor — Read These Two First

**Updated**: 2026-05-29 19:00 EDT
**Audience**: Cursor Agent (org-installed, full write access)
**Why**: 11 open coordination PRs exist. Read these two canonical PRs first; everything else is superseded or supplementary.

---

## 1. `.github#82` — CTO + PM 30-Day Operational Plan

**Path in repo**: `coordination/CURSOR_CTO_PM_OPERATIONAL_PLAN.md`
**Lines**: 469
**Supersedes**: #71, #72, #73, #75, #77, #78, #79, #80

This is the canonical 30-day Cursor work plan after the CTO+PM audit (35 gaps identified). Read this first to understand:

- Priority queue across all 12 repos
- Daily-status PR cadence (use #76 pattern)
- Doctrine v6 (no marketing superlatives, no emoji in `## ###` headers, sign all commits with `-s`)
- Branch protection / PR proxy pattern (your `cursor[bot]` GHA identity has `permission: none`; org-installed Cursor App has full write — when in doubt, push branch and let Perplexity proxy the PR)

## 2. `.github#83` — Theorems Instillation Plan

**Path in repo**: `coordination/THEOREMS_INSTILLATION_PLAN.md`
**Lines**: 472
**Estimated Cursor work**: ~238h, prioritized in 3 tiers

This is the canonical theorems / formal-verification work plan after the theorems-zoom-out audit.

### Canonical numbers (PhD-audit-corrected — DO NOT REVERT)

| Metric | Value | Source |
|---|---|---|
| Lean theorem declarations | **217** | grep across 53 `.lean` files (corrects old "76" — that was concept count) |
| Lean axioms | **12** | grep across 53 `.lean` files |
| Executable `sorry` statements | **7** | grep — **NOT 6 as #83 originally stated** (see correction below) |
| Anchor formulas instilled | **35/35** | confirmed by theorems subagent |
| TH10 status | **axiom-structured pending CAUCHY_ND** | NOT machine-checked |
| `liu_hui_pi_converges` | **Lean axiom** | NOT proved theorem |
| Putnam baseline | **8.3% (1/12)** | honest — never inflate |

### Sorry-count correction (post-#83)

`.github#83`'s closeout said **6 sorries**. Verified ground-truth count is **7**:

1. `Uniqueness.lean:120` (CAUCHY_ND)
2. `TwoWitness.lean:163`
3. `SBOMProvenance.lean:109`
4. `MadhavaBound.lean:126`
5. `MadhavaBound.lean:145`
6. `PACBayes.lean:265` (BoundedIntegrability)
7. `PACBayes.lean:281` (ChernoffOptimisation)

Treat **7** as canonical. The reconciliation is logged in `coordination/SORRY_RECONCILIATION_2026-05-29.md` (created by Perplexity, see commit history).

### Five innovation additions to consider

Wasserstein, Hoeffding-Azuma, Galois, Pinsker, Lyapunov — flagged by zoom-out audit as high-value additions to the formula gate ladder. Not required for Series-A; consider post-warhacker.

### ~40 actionable gaps

Concentrated in: `amaru`, `rosie`, `agi-forecast` missing wiring; QEC / Wheeler / Shannon / DPI not wired as named formula gates. Full list in `.github#83` body.

---

## Everything else (supplementary)

| PR | Purpose |
|---|---|
| #71, #72, #73, #75 | Earlier iterations of operational plan → **superseded by #82** |
| #76 | Daily-status template (proxied for Cursor) — keep using this pattern |
| #77 | Write-access clarification (your `cursor[bot]` GHA identity vs org-installed Cursor App) |
| #78, #79, #80 | Earlier theorems iterations → **superseded by #83** |
| #81 | Doctrine v6 codification — read once, internalize |

---

## Doctrine v6 quick-reference (non-negotiable)

- No marketing superlatives: `revolutionary | unprecedented | world-class | seamless | industry-leading | cutting-edge | game-changing | the only/first | breakthrough`
- No emoji in `## ###` headers
- Sign all commits with `-s` (Signed-off-by)
- DO NOT touch: `a11oy#57`, `amaru#46`, `sentra#45` (DRAFT relicense — founder IP HOLD)
- Use `gh pr merge --admin --squash` (founder pre-authorized blanket for routine merges)
- No bandaids — make it real and operational
- "Series-A discipline"

## How to ask for help

If you get a `gh pr create` integration permission error: push the branch, then comment in your latest daily-status PR with the branch name. Perplexity proxies it in <5min.

---

**Sign-off pattern for all your commits**:
```
Signed-off-by: Cursor Agent <cursoragent@cursor.com>
Co-authored-by: Lutar, Stephen P. <stephen@szlholdings.com>
```
