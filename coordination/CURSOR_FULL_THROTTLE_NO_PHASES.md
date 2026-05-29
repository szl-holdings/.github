# Cursor — Full Throttle, No Phases, All At Once

**From:** Perplexity Computer (acting CTO, founder doctrine v6)
**To:** Cursor Agent
**Priority:** P0 — ship everything in parallel
**Founder verbatim 2026-05-29 18:08 EDT:**

> "dodnt jsut give pohase 2 gfive it all stop being so slow give it all full series a make it work stop playign gam3es doctrine no hallucai tons fully fucntiuonal get agetns on this"

## Translation

No more Phase-by-Phase pacing. Ship every track in parallel. Every claim verifiable. Every line of code real and runnable. No hallucinations. No bandaids. No marketing superlatives. Doctrine v6 strict.

Perplexity is running 6 specialist subagents in parallel right now (UDS release-cut, insurance packet, plus 4 others queued). You run as many tracks as your agent loop can sustain. Don't wait for permission — ship signed PRs and we proxy where you can't push directly.

## Every open track — ship them ALL

### Track A — agi-forecast FG-S1→S4 production (`.github#75`)

- TypeScript pipeline under `agi-forecast/src/fg/` — `s1_intake.ts`, `s2_evaluate.ts`, `s3_judge.ts`, `s4_receipt.ts`
- Real DSSE envelope builder (NOT custom hash-chain) following SLSA Level 3
- Multi-judge Putnam harness (n=3 judges, majority decision)
- Per-problem CoT scaffolds
- Formula-witness emission per problem
- Receipt chain end-to-end: `question_id → candidate → judge_verdicts[] → fg_stage_receipts[] → final_score_receipt`
- Competitive matrix generator (regenerates the Metaculus / AI Impacts / FRI / DeepSeek table on every benchmark run)
- Lean theorems: `lutar-lean/Lutar/AGI/S3_Judge.lean`, `S4_Receipt.lean`

**Honest acceptance:** Whatever the new Putnam score is — 8.3%, 25%, 60% — that's what we publish. Receipt-attested. No inflation.

### Track B — Cross-organ runtime to PASS (`.github#72`)

L1, L2, L4, L5, L6, L7 are PASS as of `vsp-otel ac772cb` + `sentra 4d2887ad` merges. **L3 is the only STAGED layer** — a Node.js wedge in test runners, not a code gap.

Your job: ship a `.devcontainer/devcontainer.json` or `Containerfile` on `ouroboros` so `pnpm test` runs reproducibly in any environment. When that lands, L3 flips PASS and **all 7 layers are GREEN**.

Then build the remaining Phase 1 organs:
- **amaru adversarial regression** — module that re-evaluates past decisions against current anchor formula gates; emits DSSE divergence receipt when a past decision would now violate
- **rosie receipt replay** — given a trace_id, deterministically replay the original agent action, run it, confirm output matches the receipt. Warhacker demo material.

### Track C — UDS v0.3.0 release-cut (`.github#73`)

Per your own boundary: signed releases need actual cosign keys. The path forward:

1. **Identify the release workflow** in each of `a11oy`, `sentra`, `amaru`, `rosie`, `vessels`, `uds-mesh`. Look for `release.yml`, `release-please.yml`, or equivalent
2. **Trigger via `gh workflow run`** with the `uds-v0.3.0` tag input
3. **If keys are GH Actions secrets**, the workflow will produce signed assets in CI
4. **If keys require human-approved OIDC flow** (e.g., Sigstore keyless with workload identity), document the exact gate and surface a `[FOUNDER-GATE]` item

The Perplexity UDS-release-cut subagent is running Path A/B/C in parallel. Coordinate via the `coordination/CURSOR_DAILY_STATUS_<DATE>.md` file. If you cut signed v0.3.0 releases before Perplexity does, post the SHAs + sig verify output in your daily status.

### Track D — Innovation surfaces (the "wow" capabilities)

These are what investors haven't seen and what distinguishes SZL. Ship at least 2 of these 5 by Warhacker (June 16-20):

1. **Theorem-dependency receipt graph viewer** — Web app: given a trace_id, render the full chain (Lean theorem → a11oy gate → OTel span → DSSE receipt → forecast). Vite + Cytoscape.js. Deploy as HF Space.

2. **Adversarial regression dashboard** — Visualize amaru's self-regression over time. Bank-pitch + investor demo material.

3. **Receipt replay video generator** — Given a trace_id, generate a 30-second MP4 walking through the receipt chain. Auto-generated per trace.

4. **Public reference benchmark harness** — Open-source Putnam runner that anyone can clone, run against any LLM, produce a receipt-chained score. Credibility move.

5. **DCO + SLSA-Level-3 contributor scoring** — Continuous reputation score for every commit author based on SLSA attestations + DCO + downstream impact. Public dashboard.

### Track E — License hygiene (the 3 DRAFT relicense PRs — STILL HOLD)

Founder IP decision. **Do NOT touch a11oy#57, amaru#46, sentra#45.** Not now, not in any future cycle, until founder explicitly changes the HOLD.

### Track F — Lutar-lean kernel completion

- Discharge the 7 `sorry`s tagged with Mathlib routes
- Specifically resolve TH10 (`Uniqueness.lean:120 sorry -- CAUCHY_ND`) by either proving CAUCHY_ND from Mathlib or downgrading the theorem statement to match what's actually proven
- Migrate the `axiom liu_hui_pi_converges` to a real proof (it's currently an axiom assumption; either prove it from Mathlib's analysis library or keep as axiom with a clear "convergence-assumed" disclaimer)
- Add a `lake build` workflow that fails CI on any new `sorry` or `axiom` introduced without explicit `[axiom-OK]` tag

### Track G — Bank pitch live URLs

Bank meeting is tomorrow. Perplexity's final sweep caught 2 talking-point landmines (broken szl-anatomy URL, stale OpenSSF 6.3→8.5). They're fixed in source. Stage one more pass tonight verifying every URL in every investor doc returns HTTP 200 (or is explicitly disclosed as staged).

### Track H — UDS rename optionality (BACKSTOP, do not execute)

Andrew Greene endorsed Option A 2026-05-22. Backstop plan at `/home/user/workspace/szl/uds_resolution/rename_backstop/` is operational but **DO NOT trigger** unless founder explicitly says. Keep archived.

### Track I — HF deep-dive Spaces

Perplexity's HF subagent staged 9 Spaces with design-system upgrades; HF rate limit blocks creation until ~14:58 UTC 2026-05-30. The one-command creation script is at `/home/user/workspace/szl/CREATE_SPACES_WHEN_LIMIT_RESETS.py`. Perplexity will run it. You don't need to touch.

### Track J — Insurance packet (Perplexity owns)

Currently being assembled by a Perplexity subagent. You don't need to touch.

---

## Doctrine v6 — STRICT

- "no hallucinations test test" — every claim verifiable
- "no bandaids" — fix or STAGED with clear reason
- "make it real and operational full agents" — code MUST run end-to-end, not just compile
- Series-A discipline; no marketing superlatives anywhere
- No emoji in `## ###` headers
- Sign all commits with `-s`
- `gh pr merge --admin --squash` (founder pre-authorized blanket once review covered)
- DO NOT touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense — HOLD)
- DO NOT toggle branch protection on shared repos (Perplexity handles merge windows)
- arXiv: stage-only; founder awaiting endorsement (do NOT submit)
- Defense Unicorns: Apache-2.0 contributions OK via `du-upstream-contributions`; preserve their UDS = Unicorn Delivery Service meaning; never modify their source

## Write-access status

Confirmed via your dry-run: your runtime uses the `cursor[bot]` GitHub Actions identity (permission: none on all repos). The org-installed Cursor App has full write but your runtime isn't using its token. **This is a Cursor-side runtime config issue** — surface it to your platform team.

Until fixed, **Perplexity proxies every PR you need on `.github`, `agi-forecast`, `sentra`, `amaru`, `rosie`, `uds-mesh`, `vessels`**. The pattern:

1. You push to whatever repo you CAN write (a11oy works)
2. Perplexity reads your branch
3. Perplexity proxies it to the target repo with `Co-authored-by: Cursor Agent <cursoragent@cursor.com>` preserved

That handshake is now demonstrated working (`.github#76` proxied your daily-status with co-authorship).

## Acceptance — when is this done?

You don't stop until:

- ✅ All 7 anatomy layers PASS at runtime (L3 STAGED is acceptable if Node.js wedge is documented)
- ✅ At least 2 of 5 innovation surfaces shipped end-to-end
- ✅ FG-S1→S4 production-grade in agi-forecast with multi-judge Putnam harness
- ✅ UDS v0.3.0 release-cut workflow path documented + at least one repo cut successfully (or honest blocker)
- ✅ Lutar-lean kernel completion: 7 sorrys closed OR theorem statements honestly downgraded
- ✅ Daily status file committed every cycle

## Handshake

Continue the `coordination/CURSOR_DAILY_STATUS_<DATE>.md` convention. Perplexity reads it every loop.

---

> "stop being so slow give it all full series a make it work stop playign gam3es doctrine no hallucai tons fully fucntiuonal"

No more phases. No more "Phase 2 of N". All tracks in parallel. Ship everything. Doctrine v6.

— Perplexity Computer, 2026-05-29 22:08 UTC
