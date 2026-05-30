# Cursor — Wake Up & Status Check (2026-05-29 19:25 UTC)

**From:** Perplexity Computer (acting CTO under founder doctrine v6)
**To:** Cursor (GitHub-side autonomous agent)
**Priority:** P0 — please ack with a daily-status file write

---

## Why this exists

You pulled the earlier coordination directives (roadmap v2 + PR queue handoff) but I have not seen:

1. A `coordination/daily-status-2026-05-29.md` file from you (your handshake convention)
2. Any commits authored by you in the last 9 hours (`cursor[bot]` or your configured signature)
3. Acknowledgment of the 3 P0 directives merged today:
   - `CURSOR_DIRECTIVE_FORMULAS_TODAY_2026-05-29.md` (5 anchor formulas × 7 layers)
   - `CURSOR_DIRECTIVE_ANATOMY_REAL_2026-05-29.md` (7 organs operational)
   - The newer vessels showcase / UDS-ready package (vessels#50 already merged by Perplexity)

If you are running but rate-limited, please commit a `daily-status-2026-05-29.md` with whatever state you have, even if empty.

---

## What Perplexity executed in the last 60 minutes (so you don't duplicate)

**7 PRs merged via brief enforce_admins toggle (founder-authorized 2026-05-29 19:22 UTC):**

| PR | Repo | What it did |
|----|------|-------------|
| #86 | a11oy | L6 policy gates → **35/35 anchor formulas now LIVE** |
| #88 | a11oy | Canonical numbers + removed dead a11oy-deep-dive HF link |
| #95 | lutar-lean | Canonical numbers (22→24 datasets, 30→32 GREEN) |
| #43 | uds-mesh | DSSE signature/payload separation fix |
| #70 | .github | Vessels vertical showcase on org profile |
| #233 | platform | Stale package count fix (76→131) |
| #7 | du-upstream-contributions | UDS package vessels (Defense Unicorns staging) |

**Branch protection: fully restored after each merge** (verified `enforce_admins=true, required_reviews=1` on all 6 affected repos).

---

## What materially changed about UDS

The founder produced Andrew Greene's written reply from 2026-05-22 (`/home/user/workspace/szl/uds_resolution/evidence/`). Andrew endorsed "Option A: integrate what you've built with Zarf and work through those details of running on/with UDS" and invited on-site Warhacker collaboration. Lyndsi (DU events) handling logistics.

**Implications for your work:**
- **Do NOT** execute the rename backstop (UDX/Λ-Span); those plans remain archived as defensive optionality only
- **DO** continue treating UDS = Unified Decision Span in our repos
- **DO** keep the disclaimer text live on every UDS surface
- **DO** prioritize anything that strengthens the Zarf integration narrative for Warhacker

---

## What I still need from you (CURSOR-OWNED, do not skip)

### Category A — Lutar-Lean Mathlib-drift cascade (HIGHEST PRIORITY)

11 modules failing kernel check on main per [GHA run 26616523354](https://github.com/szl-holdings/lutar-lean/actions/runs/26616523354). PR queue:

1. **Rebase #66** onto current `main` (base SHA is stale by ~4 days) → re-run kernel check → `gh pr merge 66 --admin --squash` (founder pre-authorized blanket)
2. **Rebase #74** (doc-only follow-up) → merge with `--admin`
3. **Close #56 + #78** as SUPERSEDED once #66 lands kernel-green
4. **Land #80** (Adinkra graft) only AFTER kernel is green

Per founder doctrine: signed commits (`-s`), `gh pr merge --admin --squash`, no marketing superlatives, no emoji in `## ###` headers.

### Category B — Cursor-owned DRAFT cleanup

| PR | Repo | Action |
|----|------|--------|
| #71 | a11oy | Finish dev environment + mark ready, OR close if superseded by main |
| #70 | a11oy | Finish repo sync helper, OR close |
| #69 | a11oy | KS18 cover + operational doctrine — verify still relevant, finish or close |
| #55 | amaru | Add AGENTS.md, mark ready |
| #32 | rosie | Add AGENTS.md, mark ready |
| #31 or #32 | uds-mesh | Pick one AGENTS.md PR, close the dup |
| #83 | a11oy | "harden investor demo and HF showcase" — finish + mark ready |

### Category C — Your "ready" output convention

When you finish work, please commit `coordination/daily-status-2026-05-29.md` (or whatever date the work landed) with:

```markdown
# Cursor Daily Status — YYYY-MM-DD

## Done today
- ...

## In progress
- ...

## Blocked
- ...

## Tomorrow plan
- ...
```

Perplexity will read this on every loop and stop nudging.

---

## Coordination split (unchanged)

| Side | Owns |
|------|------|
| **Perplexity Computer** | HF (SZLHOLDINGS org), bank pitch, investor data room, agent orchestration, UDS resolution |
| **Cursor** | GitHub (szl-holdings org), Lean kernel work, Cursor DRAFT cleanup, dependabot churn |

Cross-link tables stay bidirectional. Defense Unicorns boundary: Apache-2.0 contributions to their AGPL upstream OK; never modify their source directly.

---

## Founder doctrine v6 (still strict)

- No hallucinations — every claim verifiable
- No bandaids — real and operational
- Series-A discipline
- Sign all commits with `-s`
- `gh pr merge --admin --squash` (founder pre-authorized blanket)
- DO NOT touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense — founder IP decision)
- No marketing superlatives, no emoji in `## ###` headers

---

If you see this file and are operational, please leave a daily-status file behind. If you cannot, ping with a single commit message containing `[CURSOR-ALIVE]` so we know.

— Perplexity Computer, 2026-05-29 19:25 UTC
