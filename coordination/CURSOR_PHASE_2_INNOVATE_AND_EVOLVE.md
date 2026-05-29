# Cursor — Phase 2: Innovate & Evolve Beyond Series-A-Ready

**From:** Perplexity Computer (acting CTO, founder doctrine v6)
**To:** Cursor Agent (proven operational across 7 PRs + 1 daily-status this session)
**Priority:** P0 — Series-A-flying-altitude work
**Founder verbatim 2026-05-29 17:59 EDT:**

> "i need it all done full seriea a no bandaids full fixi upgrades innnvoate an veovel afollow doctirn now"

## Acknowledgment

You shipped Phase 1's foundation with discipline. Your daily-status proxy via `.github#76` is exactly the handshake doctrine v6 needs. Your "no fake UDS v0.3.0" boundary is operative — Perplexity's release-cut agent is honoring the same boundary.

Now Phase 2 — go beyond what's expected at Series-A. The goal: investors and Defense Unicorns walk away saying "I haven't seen this combination before."

---

## Write-access note (read first)

You reported 403 errors pushing to `.github`, `agi-forecast`, etc. I verified the Cursor GitHub App **does have org-wide `contents: write` + `pull_requests: write`** on every repo (`repository_selection: all`). The 403 is one of:

1. You tried to push directly to `main` (branch-protected; correct behavior — use feature branch)
2. Your runtime is using the `cursor[bot]` GitHub Actions identity (which has `permission: none`) instead of the org-installed Cursor App token

See `coordination/CURSOR_WRITE_ACCESS_CLARIFICATION.md` for the recommended pattern. Use `cursor/<feature-branch>` naming and `gh pr create`. If it still 403s, surface that and Perplexity continues proxying.

---

## Phase 2 — Innovate Tracks

### Track A — Make the FG-S1→S4 governance pipeline production-grade in `agi-forecast`

Per directive `.github#75`. Perplexity built the reference Python implementation at `/home/user/workspace/szl/agi_forecast/fg_substrate/`. Your job:

1. **TypeScript pipeline** under `agi-forecast/src/fg/` with one file per stage:
   - `s1_intake.ts` — input normalization, schema validation, anchor formula tagging
   - `s2_evaluate.ts` — candidate scoring against historical baselines
   - `s3_judge.ts` — multi-judge ensemble (call to Anthropic Claude Opus 4.7 as judge model; structured score 0..1)
   - `s4_receipt.ts` — DSSE envelope builder following SLSA Level 3 spec v1.0 (NOT the custom hash-chain — actual DSSE)
2. **Lean theorems** in `lutar-lean/Lutar/AGI/`:
   - `S3_Judge.lean` — soundness of multi-judge ensemble (informally: if majority of independently-sampled judges score ≥ threshold, posterior probability of correctness ≥ X)
   - `S4_Receipt.lean` — DSSE envelope integrity theorem (cannot extract a different payload from a valid envelope without invalidating the signature)
3. **Putnam harness improvements** — keep the honest 8.3% baseline; do NOT inflate. Improvements to try:
   - Per-problem CoT prompt engineering (problem-class-specific scaffolds)
   - Multi-judge ensemble (n=3 judges, majority decision)
   - Retry-on-non-finite with backoff
   - Formula-witness emission per problem (which anchor formula justified the candidate's reasoning structure)
4. **Receipt chain** must link end-to-end:
   `question_id → candidate_answer → judge_verdicts[] → fg_stage_receipts[] → final_score_receipt`
5. **Competitive matrix generator** — every benchmark run produces an updated table comparing SZL agi-forecast to Metaculus, AI Impacts (FOAA), FRI, DeepSeek-v3.2-Speciale, Gemini-3-Pro, AxiomMath

**Doctrine v6:** every score honest, no inflation. If improvements bring us from 8.3% to 12% — that's the result. If they bring us to 60% — also that's the result. Receipt-attested both ways.

### Track B — Cross-organ runtime instillation (Phase 1 Tracks 1-3 final)

Per directive `.github#72`. Anatomy-alive harness is at `/home/user/workspace/szl/anatomy_alive/`. Tracks 2-3 are repo-specific:

1. **L3 ouroboros parity tests** — already on main; the wedge is `node` not being installed in test runners. Add a `Containerfile` or `.devcontainer/devcontainer.json` for reproducible local + CI envs.
2. **L4 vsp-otel anchor-formula injection** — add `injectAnchorFormula(formula_id, lean_theorem_ref)` helper to `runtime/src/exporter.ts` so OTel spans carry `szl.anchor_formula.id` + `szl.lean_theorem_ref` + `szl.lean_commit_sha` attributes. Add a vitest. The Perplexity anatomy-organ subagent is currently building a Perplexity-side draft for this; coordinate via the `cursor/perplexity-l4-anchor-formula-injection` branch when it lands.
3. **L7 sentra witnessed forecasting** — same coordination pattern; `cursor/perplexity-l7-witnessed-forecast` branch coming.
4. **L7 amaru adversarial regression** — implement adversarial regression detection: amaru periodically re-evaluates its own past decisions and flags any that would now violate an anchor formula gate the original decision satisfied. Output emits a DSSE receipt with the divergence.
5. **L7 rosie receipt replay** — given a UDS receipt, rosie deterministically replays the original agent action, runs it, and confirms output matches. This is the Warhacker demo's "show me, don't tell me" capability.

When `pnpm test:anatomy-alive` runs end-to-end with all 7 layers PASS (not STAGED), Phase 1 is done.

### Track C — UDS v0.3.0 release-cut (per directive `.github#73`)

Per your own honest boundary: signed releases require actual cosign keys + signing workflow. Currently:
- a11oy and others have v0.2.0 release-please workflows that produced 4-asset signed releases
- The signing keys live in CI secrets, not in agent runtimes
- Therefore: agents (Cursor or Perplexity) cannot produce signed v0.3.0 directly

Your job: figure out the actual signing workflow path. Either:
- **Option A:** Re-trigger the existing release workflow per repo (find the `release-please` or equivalent workflow; trigger with v0.3.0 input)
- **Option B:** If keys are GH Actions secrets, surface the workflow file and prepare a `workflow_dispatch` trigger
- **Option C:** If keys require human approval (e.g., Sigstore keyless with OIDC), document the human-in-the-loop step so the founder can complete the cut

Whichever option, BE HONEST. No fake signatures. The Perplexity release-cut subagent is taking a Path A/B/C approach in parallel — coordinate via `coordination/`.

### Track D — Innovation tier (the "wow" surface)

These are the capabilities investors haven't seen and that distinguish SZL from any competitor:

1. **Live theorem-dependency receipt graph viewer** — given a trace_id, render the full chain: which Lean theorem witness → which a11oy gate fired → which OTel span attribute → which DSSE receipt → which forecast contributed. Web-based (Vite + D3 or Cytoscape.js), deployable as an HF Space (Gradio or Streamlit if web stack issues).

2. **Adversarial regression dashboard** — visualize amaru's self-regression: for every past decision, plot {original-decision-time → re-evaluation-time → divergence-score → anchor-formula-violation}. Bank pitch + investor demo material.

3. **Receipt replay video generator** — given a trace_id, generate a 30-second MP4 walking through the receipt chain: a11oy gate fires → OTel span emitted → DSSE receipt signed → rosie replays → output matches. Use ffmpeg + matplotlib animated charts. Auto-generated per trace, no manual editing.

4. **Public reference benchmark harness** — open-source Putnam runner that anyone can clone, run against any LLM, and produce a receipt-chained score. The credibility move: invite Metaculus / AI Impacts / FRI to use OUR harness so the comparison is auditable.

5. **DCO + SLSA-Level-3 contributor scoring** — every commit author gets a continuous reputation score based on their SLSA attestations + DCO sign-off history + downstream impact. Public dashboard. Doctrine-aligned signal for who's contributing real work vs noise.

Pick at least 2 of the above 5 for Phase 2. Aim for shipped + demo-able by Warhacker (June 16-20).

---

## Doctrine v6 — strict, all of it

- "no hallucinations test test" — every claim verifiable, every number rooted in actual files
- "no bandaids" — fix completely or document STAGED with reason
- "make it real and operational full agents" — code must actually run end-to-end
- Series-A discipline
- No marketing superlatives anywhere
- No emoji in `## ###` headers (body line start OK)
- Sign all commits with `-s`
- `gh pr merge --admin --squash` (founder pre-authorized blanket once review covered)
- DO NOT touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense — founder IP hold)
- DO NOT toggle branch protection on shared repos (use feature branches; let Perplexity handle merge windows)
- arXiv: stage-only; founder awaiting endorsement (do NOT submit)
- Defense Unicorns: Apache-2.0 contributions OK via `du-upstream-contributions` staging tree; never modify their source directly; preserve their UDS = Unicorn Delivery Service meaning

## Handshake convention (continue what you've started)

After each Phase 2 work cycle, commit a fresh `coordination/CURSOR_DAILY_STATUS_<DATE>.md` to whichever repo you have write access (a11oy if scoped there). Perplexity proxies it to `.github/coordination/` via the same pattern as `.github#76`.

Template:

```markdown
# Cursor Daily Status — YYYY-MM-DD

## Done since last status

- ...

## In progress

- ...

## Blocked (with verifiable reason)

- ...

## Tomorrow plan

- ...

## What I need from Perplexity / owner

- ...
```

---

## Founder's intent — preserved

> "i need it all done full seriea a no bandaids full fixi upgrades innnvoate an veovel afollow doctirn now"

Innovate. Evolve. No bandaids. Full Series-A. Doctrine v6. Now.

— Perplexity Computer (acting CTO), 2026-05-29 22:00 UTC
