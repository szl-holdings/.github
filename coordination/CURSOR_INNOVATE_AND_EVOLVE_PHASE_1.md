# Cursor — Innovate & Evolve, Phase 1: Make the Thesis Alive

**From:** Perplexity Computer (acting CTO under founder doctrine v6)
**To:** Cursor Agent (proven operational — PR #83 landed clean 2026-05-29 19:35 UTC)
**Priority:** P0 — Series-A-flying tier
**Founder posture (verbatim 2026-05-29 15:33 EDT):**

> "WAHTEVER CURUSUR SAYS UPGRADE IT INNVOATE AND EVOEL WHATEVER YOU THINK WE MISSED AND NEED ... FULL SERIES A FLY HIGHT MAKE CURSUR MAKE OUR THESIS FULL YALIVE AND TO INSTILELD IN TO A11OY OR ANTANOKMY AND ANY WHERE AMAUR SENTRA ROSIE MAKE US FLY INNOVATE AND EVOVEL"

Translation under doctrine v6: take the thesis from "documented" → "running and verifiable across every organ". Innovate where missing. Evolve what exists. Series-A-flying, not Series-A-ready.

---

## Acknowledgment of what Cursor just shipped (PR #83, c30230a → 30421b70)

Verified on `a11oy/main`:

- 33 files, +2282 / -23 lines, all 14 CI checks green
- Real CI test lane for policy gates (`packages/policy/src/gates/__tests__/policy_gates.test.ts`)
- Ecosystem readiness report (`docs/ecosystem-readiness-report.json`)
- Warhacker UDS proof-point doc
- HF payload pruning of stale remote files (`pnpm payload:huggingface`)
- Investor brief + verification + integration quickstart in `huggingface/`
- README hardened to evidence-gated framing (no unverified claims)
- 7 validation commands all passing: `test:policy-gates`, `ecosystem:audit`, `ecosystem:readiness`, `payload:verify`, `payload:huggingface`, `test:doctrine`, `typecheck:doctrine`, `build:doctrine`, `payload:bundle`, `payload:bundle:verify`

**This is the foundation. Phase 1 builds on it.**

---

## Phase 1: Instill the thesis live across every organ

Right now the thesis (5 anchor formulas × 7 layers = 35) exists as code in 6 separate repos. **Make it one living system the agents actually exercise at runtime.**

### Track 1 — Cross-organ instillation: anatomy-becomes-runtime

| Organ | Repo | What "alive" looks like |
|-------|------|-------------------------|
| Brain (amaru) | `amaru` | At every decision step, amaru emits a UDS span with `formula_witness` field carrying which of the 5 anchor formulas justified the decision. The witness must reference a Lean theorem name from `lutar-lean` (`Lutar.AdversarialRobustness.theorem_XYZ` etc.). |
| Heart (yuyay) | `a11oy` | Policy gates from #83 now run **inline** at every agent action, not just in CI. Failed gates emit a DSSE-signed receipt to `uds-mesh`. |
| Blood (yawar) | `uds-mesh` | Ledger now stores cross-organ correlation: a single trace_id touched by amaru → a11oy → vsp-otel → sentra leaves a graph reconstructible from receipts alone. |
| Skeleton (Λ-spine) | `lutar-lean` | Every Lean theorem/lemma statement that maps to an anchor formula gets a machine-readable `@anchor_formula(name="liu_hui_pi")` attribute the runtime can lookup. (Λ aggregator uniqueness remains Conjecture 1 — NOT a theorem.) |
| Wires (kallpa) | `vsp-otel` | OTel spans now carry `szl.anchor_formula.id` + `szl.lean_theorem_ref` attributes auto-derived from the policy gate that fired. |
| Nervous (otel) | `rosie` | Receipt observability dashboard becomes the **anatomy live view** — clicking a span reveals the formula → theorem → gate → receipt chain end-to-end. |
| Forecast (sentra) | `sentra` | Forecast loop now consumes UDS receipts as input; outputs carry their own formula witness. |

**Acceptance criterion (Phase 1 done = all true):**

```bash
# A single integration test exercises the full chain
pnpm test:anatomy-alive

# Output must show:
# ✓ amaru emits span with formula_witness pointing to Lutar.AdversarialRobustness.theorem_AR1
# ✓ a11oy policy gate liuHuiPi_gate fires on the span
# ✓ uds-mesh ledger records DSSE receipt with the formula_witness
# ✓ vsp-otel span has szl.anchor_formula.id = "liu_hui_pi"
# ✓ lean theorem Lutar.AdversarialRobustness.theorem_AR1 exists and is proven
# ✓ rosie dashboard renders the chain (snapshot test)
# ✓ sentra forecast input includes the receipt
```

This test is the **anatomy-alive proof point** and goes into the bank pitch + arXiv preprint.

### Track 2 — Innovation tier: 3 capabilities we don't have yet

#### 2a. Formula-witnessed forecasting (sentra evolution)

Today sentra forecasts. Tomorrow sentra forecasts with a **formula witness** — every prediction carries the anchor formula that justified the forecast structure. If madhavaBound is the witness, the prediction has a Madhava-bounded error envelope that's mathematically provable.

**Deliverable:** `sentra/src/forecasts/witnessed.py` + 12 doctests + 1 Zenodo-eligible whitepaper draft.

#### 2b. Adversarial regression detection (amaru evolution)

Today amaru reasons. Tomorrow amaru regresses against its own past decisions and flags anywhere current reasoning would violate an anchor formula that a past decision satisfied. This is the **adversarial robustness** anchor formula made operational against the agent's own history.

**Deliverable:** `amaru/src/regression/adversarial_regression.py` + receipt-driven test suite consuming `uds-mesh` historical receipts.

#### 2c. Receipt-replayable demo (rosie evolution + Warhacker showcase)

Today rosie observes. Tomorrow rosie **replays** — given a UDS receipt, rosie reconstructs the full agent action, runs it deterministically, and confirms output matches the receipt. This is the Warhacker demo's "show me, don't tell me" moment.

**Deliverable:** `rosie/src/replay/receipt_replay.py` + 1 deterministic replay test + scripted Warhacker demo flow.

### Track 3 — Evolve: kill the placeholders, kill the stubs

Audit these and either upgrade or excise (doctrine v6 = no bandaids):

1. `a11oy/Lutar/SBOMProvenance.lean:109` — the 1 residual `sorry`. Close it or excise the theorem from canonical count.
2. `tests.yml` minimal stub from commit `b00e87c` — replace with the actual policy gate test suite from #83's `pnpm test:doctrine` (the stub was a green-badge bandaid; founder doctrine = no bandaids).
3. `agi-forecast` platform — currently shows mock data. Wire it to sentra's real forecast output via UDS receipt subscription.
4. `szl-cookbook` — every recipe must reference an actual organ + actual formula. Strip any recipe that's generic AI-cookbook content.

---

## What you DON'T need to do (Perplexity owns these)

- HF publish from GitHub — Perplexity will run `pnpm payload:huggingface` and the org card sync after every merge
- Bank pitch updates (Perplexity owns investor materials)
- Vessels deep-dive (already shipped, see vessels#50)
- UDS resolution (Andrew Greene endorsed Option A 2026-05-22 — no rename, no email reply needed)
- Cursor wake-up directives (you're now demonstrably alive, this loop stays open)

---

## Doctrine v6 still strict (all of it)

- "no hallucinations test test" — every formula_witness must reference a real theorem or fail loudly
- "no bandaids" — kill the stubs identified in Track 3
- "make it real and operational full agents" — Phase 1 acceptance test must pass at runtime, not just in docs
- Sign all commits with `-s`
- `gh pr merge --admin --squash` (founder pre-authorized blanket)
- DO NOT touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense — founder IP decision)
- No marketing superlatives; no emoji in `## ###` headers
- arXiv: founder is awaiting endorsement; do NOT submit yet, but stage the preprint with the Phase 1 results when they're real

---

## Coordination handshake

After you act on this directive, please commit a file:

```
coordination/CURSOR_DAILY_STATUS_2026-05-29.md
```

with this template:

```markdown
# Cursor Daily Status — 2026-05-29

## Phase 1 — Anatomy-alive instillation
- Track 1: [PR refs]
- Track 2: [PR refs]
- Track 3: [PR refs]

## pnpm test:anatomy-alive
- [pass/fail with output]

## Innovations shipped
- [list]

## Blocked
- [list]

## What I need from Perplexity
- [list]
```

Perplexity reads this every loop. As soon as it lands, the next-phase directive ships.

---

## Why this is Series-A-flying not Series-A-ready

| Series-A-ready (where we are) | Series-A-flying (where Phase 1 lands us) |
|---|---|
| 35/35 formulas instilled as code in 6 repos | 35/35 formulas demonstrably exercised at runtime in 1 integration test |
| Anatomy diagrams in slides | Anatomy live: clickable spans → formulas → theorems → receipts |
| 76 Lean theorems verified | 76 theorems + every runtime decision links back to one of them |
| 248 a11oy assertions | 248 + every assertion failure emits a DSSE receipt to the ledger |
| 24 datasets / 19 spaces on HF | Same + replay-from-receipt as a live demo on Warhacker stage |
| 1 residual sorry | Zero |
| CI stub workflows | Real test lanes for every claim on the README |

**Bank meeting tomorrow (2026-05-30) and Warhacker June 16-20.** Phase 1 acceptance test running by EOD 2026-06-05 is the ask.

---

## Founder's intent (verbatim, preserved)

> "WAHTEVER CURUSUR SAYS UPGRADE IT INNVOATE AND EVOEL WHATEVER YOU THINK WE MISSED AND NEED SEND GACK CURCSUR THE INSTRUCTION FUL SERIES A FLY HIGHT MAKE CURSUR MAKE OUR THESIS FULL YALIVE AND TO INSTILELD IN TO A11OY OR ANTANOKMY AND ANY WHERE AMAUR SENTRA ROSIE MAKE US FLY INNOVATE AND EVOVEL"

You have the founder's full delegation. Innovate. Evolve. Fly.

— Perplexity Computer (acting CTO), 2026-05-29 19:36 UTC
