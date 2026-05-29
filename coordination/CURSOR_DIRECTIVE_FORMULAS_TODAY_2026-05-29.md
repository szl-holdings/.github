# Cursor Directive — Instill formulas end-to-end TODAY (2026-05-29 18:09 UTC)

**Founder mandate (verbatim, 2026-05-29 11:09 PDT):** "I want this done today money not a issue."

**Priority:** P0 — preempts other Tier-2 / Tier-3 roadmap items today only.

**Scope:** Phase 0 of "instill every formula into the stack" — 5 anchor formulas, 7 stack layers each = 35 deliverables. End of day 2026-05-29.

---

## What Perplexity has already done

A Perplexity strike team is in flight building Phase 0 (`/home/user/workspace/szl/closeout/FORMULAS_INSTILLED_PHASE_0.md` will land in this repo when complete).

Cursor's job in this directive is **complementary**, not duplicative. Pick up the layers Perplexity cannot fully cover from the cloud sandbox.

## The 5 anchor formulas

| # | Theorem | Canonical Lean file | Runtime owner |
|---|---|---|---|
| 1 | `MadhavaBound` | `lutar-lean/Lutar/PACBayes/MadhavaBound.lean` | ouroboros/agentic/formulas |
| 2 | `FalsePosition` | `lutar-lean/Lutar/Calibration/FalsePosition.lean` | ouroboros/agentic/formulas |
| 3 | `LiuHuiPi` | `lutar-lean/Lutar/Banach/LiuHuiPi.lean` | ouroboros/agentic/formulas |
| 4 | `AdversarialRobustness` | `lutar-lean/Lutar/Composition/AdversarialRobustness.lean` | ouroboros/agentic/formulas + a11oy/packages/policy |
| 5 | `SummationInvariant` | `lutar-lean/Lutar/Khipu/SummationInvariant.lean` | ouroboros/agentic/formulas + uds-mesh |

## The 7 stack layers per formula (35 total)

For each anchor, all of these MUST exist on `main` by end of day:

1. **Lean proof** — already on `lutar-lean@main`, lake-verified. Cursor: confirm `lake build <file>` passes; if it doesn't, fix the proof before claiming any other layer green.
2. **TypeScript runtime** — `ouroboros/agentic/formulas/<name>.ts` exporting a typed function. Doc-comment must cite the Lean file + commit SHA.
3. **Parity test** — `ouroboros/agentic/formulas/<name>.test.ts` running ≥ 1000 property-based inputs (fast-check or vitest), asserting the theorem's claim. CI-runnable via `pnpm test`.
4. **OpenTelemetry span emission** — `vsp-otel/src/formulas/<name>.ts` wrapping the runtime in an OTel span with attributes: `szl.formula.name`, `szl.formula.lean_file`, `szl.formula.commit_sha`, `szl.formula.lambda_score`, `szl.formula.output`. OTLP wire-compatible.
5. **DSSE-wrapped receipt** — MCP receipts server emits a DSSE PAE v1 + HMAC-SHA-256 envelope per invocation. Schema: `{formula, inputs_hash, output, lean_theorem, lean_commit_sha, ts, sig}`.
6. **a11oy policy gate** — `a11oy/packages/policy/src/gates/<name>_gate.ts` real policy logic consuming the formula. Cites Lean rationale in the deny/allow message.
7. **rosie operator console panel** — Live formula table tab in `SZLHOLDINGS/rosie-operator-console` Space showing all 5 anchors with current Λ-score + DSSE chain deep-link.

## Acceptance criteria

A formula is **instilled** when all 7 boxes are ✓ on `main`:

```
[ ] L1 Lean lake-verified
[ ] L2 TS runtime exported
[ ] L3 Parity test ≥ 1000 inputs, CI green
[ ] L4 OTel span emission with required attributes
[ ] L5 DSSE receipt emitted referencing Lean
[ ] L6 a11oy policy gate using the formula
[ ] L7 rosie panel shows it live
```

Phase 0 = **35/35 boxes ✓** end of day 2026-05-29.

## Coordination rule

- **Cursor owns:** Layers 2, 3, 4, 6 (GitHub side)
- **Perplexity owns:** Layers 5, 7 (HF side, MCP server + rosie Space)
- **Either may verify Layer 1** (Lean)

If Cursor finishes a layer first, push the PR; auto-merge will pick it up. If Perplexity finishes first, the GitHub directive doc here will be updated with the matrix marker.

## Doctrine v6 strict

- No marketing superlatives anywhere — README, commits, PR titles
- No emoji in `## ###` headers
- Real property-based tests (not stub assertions)
- Sign every commit with `-s`
- Use `gh pr merge --admin --squash` (founder pre-authorized)
- DO NOT touch: a11oy#57, amaru#46, sentra#45 (DRAFT relicense PRs)

## Single-PR-per-repo pattern

Open ONE PR per repo containing all 5 anchor formula changes for that layer:

- `szl-holdings/ouroboros` PR: 5 runtimes + 5 parity tests
- `szl-holdings/vsp-otel` PR: 5 OTel wrappers
- `szl-holdings/a11oy` PR: 5 gate files
- `szl-holdings/uds-mesh` PR: extended receipt schema + per-formula support
- HF push to `SZLHOLDINGS/rosie-operator-console` for L7

## Reporting

When Cursor completes any layer, push a status update to `szl-holdings/.github/coordination/daily-status-2026-05-29.md` with the line:

```
[YYYY-MM-DD HH:MM UTC] cursor: layer L<N> of <formula> shipped — PR #<num>
```

## Why this matters

Bank meeting tomorrow (Saturday 2026-05-30). Warhacker June 16-20. This phase 0 demo gives a credible "every named theorem ships as Lean proof + runtime + parity test + telemetry + receipt + policy + dashboard" pattern that scales to all 76 theorems. Without it, the moat narrative is "we have Lean proofs"; with it, the narrative is "we operationalize Lean proofs end-to-end" — which is the actual Series-A wedge.

---

## Sign-off

Stephen Paul Lutar JR — Founder & CEO, SZL Holdings
2026-05-29 18:09 UTC
