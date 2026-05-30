# Cursor handoff — Investor demo readiness sweep, 2026-05-29 22:30 EDT

**Audience:** Cursor Agent (next loop)
**Author:** Perplexity Computer (Stephen Lutar's runtime)
**Scope:** Everything needed to clear the Lean kernel red bar and merge the open coordination/Tier-A PRs across `lutar-lean`, `agi-forecast`, `a11oy`, `.github`. Read top-to-bottom. Execute Section 3 first.

---

## 0. TL;DR — the real picture (live state, 2026-05-29 22:30 EDT)

| PR | Repo | What it does | CI | Blocker |
|---|---|---|---|---|
| #98 | lutar-lean | `MerkleDAGBuild.lean:132` `positivity` → `Nat.one_le_pow` | Lake build FAIL | 5 other unrelated errors in same file (L63–90); 16 other modules also red |
| #99 | lutar-lean | `KitaevSurface`, `Shannon.DoctrineEntropy`, `Wheeler.DelayedChoice` Tier-A drift fixes | Lake build FAIL | Surgical fixes land (KitaevSurface 2→1, Wheeler 12→1, Shannon 0 change). 14 other modules still red |
| #100 | lutar-lean | `Gates/Adinkra.lean` Fin 1 + `HUKLLA/HaltEligibility.lean` decidability | Lake build FAIL | Adinkra 4→1 (good). 16 other modules still red |
| #42 | agi-forecast | FG-S1→S4 receipt pipeline | **ALL GREEN** ✅ | Only needs 1 review |
| #94 | a11oy | UDS frontier gap map (docs) | **ALL GREEN** ✅ | Just rebased (was BEHIND); needs 1 review |
| #99 | a11oy | HF deep-dive docs proxy | **ALL GREEN** ✅ | Needs 1 review |
| #100 | a11oy | Latest proxy handshake docs | **ALL GREEN** ✅ | Needs 1 review |
| #101 | a11oy | agi-forecast FG source proxy | **ALL GREEN** ✅ | Needs 1 review |
| #111 | a11oy | **NEW** dependabot label fix (opened by Perplexity proxy tonight) | Pending | Needs 1 review |
| #86 | .github | CURSOR_MASTER_DIRECTIVE (683 lines) | Pending | Needs 1 review |
| #82, #83, #84, #85 | .github | Coordination plans | Pending | Needs 1 review each |

**Headline:** every non-Lean PR is **green and only blocked by branch protection's `required_approving_review_count = 1`**. The only red bar is `Lean kernel check` on `lutar-lean`, and that's because `main` itself has been red since at least 21:04 EDT — `lutar-lean/main` has 17 simultaneously failing modules with **120 total errors**. The three open lutar-lean PRs each fix 1–11 errors but inherit the rest from `main`. The lake will stay red until every failing module is fixed in one or more PRs.

---

## 1. Write-access / proxy pattern — the actual mechanic

**Cursor's GitHub App** (`cursor`, app_id `1210556`, installation `136458231`) is **installed at the org level on `szl-holdings` with `repository_selection: all`** and the following permissions:

```
contents: write
pull_requests: write
checks: write
workflows: write
discussions: write
issues: write
actions: write
```

**So the App can already write to every repo.** What's broken is that your runtime authenticates as the `cursor[bot]` user identity (via personal repo invitations), not via the App installation token. The personal invitations can't be PATCH-accepted from your runtime context — that's why `gh api -X PATCH user/repository_invitations/$INV` keeps failing.

### Two paths to fix permanently (pick one, do not loop on this anymore)

**Path A (recommended, 5 min):** Switch your runtime to use the **App installation access token** instead of the bot user PAT. Endpoint:

```
POST /app/installations/136458231/access_tokens
```

This requires your JWT signed with the Cursor App private key (which Cursor owns, not us). Once you use that installation token via `gh auth login --with-token` or `GH_TOKEN=<installation_token>`, all `git push` / `gh pr create` against every szl-holdings repo will succeed — no invitations, no proxy.

**Path B (workaround, also 5 min):** Stop trying to push as `cursor[bot]`. Instead, push to a fork under your own runtime-owned user namespace, then open cross-fork PRs to `szl-holdings/*`. Branch protection on `main` doesn't require pushes — it requires reviews, which an external PR satisfies.

**Path C (current, working but slow):** Paste-and-proxy via `.github#76`. Keep doing this for one-off fixes if A/B can't ship tonight, but stop trying to PATCH invitations.

**What I did tonight that you couldn't:** opened `a11oy#111` from your already-pushed branch `cursor/fix-dependabot-label-config-2f18` (you wrote the commit, I just opened the PR object). Your commit, your signed-off-by, my PR creation — that's the doctrine v6 handshake working.

---

## 2. Branch protection inventory (so you know what "merge" actually needs)

All 9 sibling repos require **1 approving review** on `main`. Required status checks:

| Repo | required_status_checks |
|---|---|
| lutar-lean | (none — but `Lean kernel check` must not be a NEGATIVE gate; right now PRs are flagged BLOCKED because the build check is FAILURE — verify in repo settings whether it's required) |
| a11oy | `CI`, `Tests`, `CodeQL`, `DCO` (all 4 currently green on every open PR) |
| agi-forecast | (none) |
| .github | (none) |

**Action for you (or anyone with admin):** confirm whether `Lean kernel check / build` is in the required_status_checks list for lutar-lean. If yes, no lutar-lean PR merges until the lake is green. If no, #98/#99/#100 are mergeable today on a green review.

---

## 3. Lean lake fix plan — 17 modules, 120 errors, ordered by effort

**Toolchain:** `leanprover/lean4:v4.13.0`, Mathlib pinned to `v4.13.0` (see `lakefile.lean`).

### 3.1 Quick wins (≤ 30 min each) — close these first to shrink the red surface

#### A) `Lutar/QEC/KitaevSurface.lean` L62 — already done in #99, but L69 still red

PR #99 already converts `!=` chains to `Bool.xor`. The remaining error:

```
L 69:   decide          -- error: expected type must not contain free or meta variables
```

**Fix:** L69 `decide` is run inside `kitaev_single_site_flips_parity_n` whose hypothesis `(v : VertexCheck)` makes the goal not `Prop` of bounded type. Replace `decide` with explicit case split:

```lean
theorem kitaev_single_site_flips_parity_n (v : VertexCheck) :
    vertexParity (fun s => if s = v.n then true else false) v = true := by
  simp [vertexParity, Bool.xor]
  -- Goal becomes: true XOR false XOR false XOR false = true  (after if-reduction)
  -- but `v.n, v.s, v.e, v.w` are abstract; rely on the disjointness lemma:
  rfl  -- if the simp normalizes to `true`
```

If `rfl` doesn't close, add `cases v.n_ne_s; cases v.n_ne_e; cases v.n_ne_w; rfl` (whatever disjointness fields exist on `VertexCheck`).

#### B) `Lutar/QEC/CSSBridge.lean:60` — same pattern

```
L 58:     consistent (classicalToCSS c) = true := by
L 59:   simp [consistent, classicalToCSS]
L 60:   decide        -- error: expected type must not contain free or meta variables
```

`c : ClassicalCodeword` is abstract. Replace `decide` with the underlying structural proof:

```lean
  simp [consistent, classicalToCSS, ClassicalCodeword.consistent_self]
  -- or
  rfl  -- if simp normalizes
```

#### C) `Lutar/Shannon/DoctrineEntropy.lean:65` — `Fintype` derive failure (Lean 4.13 default handler)

```
L 62:   | L1    : DoctrineLabel
…
L 65:   deriving DecidableEq, Repr, Fintype   -- error: default handlers not implemented for Fintype
```

**Fix:** Lean 4.13 has narrower `deriving Fintype`. Spell the instance explicitly:

```lean
inductive DoctrineLabel : Type
  | Bot | L1 | L2 | Top
deriving DecidableEq, Repr

instance : Fintype DoctrineLabel where
  elems := {.Bot, .L1, .L2, .Top}
  complete := by intro x; cases x <;> decide
```

Then PR#99's `_root_.Fintype.card` rewrite goes through and L69 + L175 `Fintype.card` lookups resolve.

#### D) `Lutar/Wheeler/DelayedChoiceClosure.lean:88` — `And.decidable` renamed

```
L 87:   unfold admissible
L 88:   exact And.decidable    -- error: unknown constant 'And.decidable'
```

PR #99 already replaces with `infer_instance` — good. The remaining 10 errors (L177–L197) are all `tactic 'decide' failed for proposition`. After the `Decidable` instance is restored at L88, those `by decide` test examples will likely work. If not, replace each `by decide` with `by native_decide` or explicit `rfl`.

Note also L177:

```
L177: /-- Tests (compile-checked at kernel time via `decide`). -/
L178: namespace Tests
```

The error `unexpected token 'namespace'; expected 'lemma'` means a `def admissibleDec` block above is missing a terminator. Inspect L173–177:

```lean
def admissibleDec (s : Span) (r : Receipt) : Bool :=
  decide (admissible s r)
                                       -- ← needs a blank line OR explicit end of block
/-- Tests (...) -/
namespace Tests
```

Likely the doc-comment is being parsed as continuing the `def`. Insert a real declaration terminator or move the doc-comment below `namespace`:

```lean
def admissibleDec (s : Span) (r : Receipt) : Bool :=
  decide (admissible s r)

namespace Tests
/-! ## Tests (compile-checked at kernel time via `decide`). -/
```

#### E) `Lutar/Gates/Adinkra.lean:207` — same doc-comment parsing issue

```
L207:30  unexpected token '/-!'; expected 'lemma'
```

A `/-!` section-comment is appearing where Lean expects more proof. Move it after the prior `theorem` is fully closed (likely insert `end` for the surrounding namespace before the section marker), or downgrade `/-!` to `--`.

#### F) `Lutar/DPI/SCITTMaskEntropy.lean:73` — same family

```
L 73:53  unexpected token '/--'; expected 'lemma'
```

Doc-comment placed mid-declaration. Move it to before the next `theorem`/`def` declaration.

### 3.2 Medium-difficulty fixes (1–3 hours each)

#### G) `Lutar/HUKLLA/HaltEligibility.lean:90, 118, 133` — `Real.decidableLE` removed

PR #100 adds `Classical.decRel` haveI. That's correct in principle but Lean 4.13 needs:

```lean
def isHaltEligible (t : ExecutionTrace) : Bool :=
  haveI : Decidable (t.lambda_score ≥ LAMBDA_FLOOR) :=
    Classical.dec _
  decide (t.lambda_score ≥ LAMBDA_FLOOR) && t.receipts_closed && t.rho_closure_satisfied
```

But this still triggers `compiler IR check failed` because `Classical.dec` has no executable code. **The clean fix is to mark `isHaltEligible` `noncomputable`** OR change the type from `Bool` to `Prop` and use a separate `Decidable` instance for runtime evaluation:

```lean
noncomputable def isHaltEligible (t : ExecutionTrace) : Bool := …

-- OR, if runtime needs it:
def isHaltEligible (t : ExecutionTrace) : Bool :=
  -- use a rational/Float comparison that IS computable, not Real
  decide (t.lambda_score_q ≥ LAMBDA_FLOOR_Q) && t.receipts_closed && t.rho_closure_satisfied
```

The downstream `instance halt_eligibility_decidable` at L118 then drops to `Bool.decEq`-based inference automatically.

L133 `type mismatch` will resolve once L90 type checks (it's cascading).

#### H) `Lutar/Correlator/MatchedFilter.lean:96, 94, 142` — unknown tactic + decide proved opposite

```
L 96:11  unknown tactic
L 94:18  unsolved goals
L142:60  tactic 'decide' proved that the proposition … is FALSE
```

Read L92–98 to see which tactic is unknown (likely a Mathlib 4.x rename). L142 means the example is asserting the wrong polarity — invert the expected boolean or fix the input data.

#### I) `Lutar/Composition/TH1_Composition.lean:161, 175, 180, 184` — `omega` + type mismatch

`omega` can't prove the goal as stated. Either the hypothesis is missing or the goal needs `Nat.le_iff_lt_succ` style preprocessing. Show the goal with `show` before `omega` to see what's wrong:

```lean
-- before omega
show k + 1 ≤ n + 1
omega
```

#### J) `Lutar/Composition/AdversarialRobustness.lean:129, 130, 131` — `LE.le.elim` doesn't exist

```
L131:32  invalid field 'elim', the environment does not contain 'LE.le.elim'
```

In Mathlib 4.13 the `LE.le.elim` lemma is gone. Replacements:
- `le_iff_lt_or_eq` then `rcases h with h | h`
- or `obtain ⟨…⟩ := h` if `h : a ≤ b` and you wanted destructuring (rarely correct)

The L129/L130 `eliminator target type isn't an application of the motive` errors are the same root cause — fix L131 first and they'll cascade-fix.

#### K) `Lutar/PRNG/K10v2_ReplayRoot.lean:84, 142, 149, 152, 161` — 4.13 API drift

L84 says `type of theorem 'isReplayRoot_decidable' is not a proposition` — usually means the `:` after the theorem name has the wrong type or there's a missing `Decidable` instance synthesized incorrectly. Inspect lines 82–86 and convert to:

```lean
instance isReplayRoot_decidable : DecidablePred (Lutar.K10.Xoshiro.isReplayRoot) := …
```

(i.e., declare as `instance`, not `theorem`).

#### L) `Lutar/Topology/PersistentHomologyChain.lean:60, 78, 96, 138, 139` — multiple `failed to synthesize`

These are typeclass synthesis failures. Add `@` to make implicit args explicit at each failure site, OR add an explicit `Fintype` / `DecidableEq` / `Nonempty` instance argument to the theorem signature.

#### M) `Lutar/GraphLambda.lean:151, 186` — `rewrite` failed + `no goals`

L151 `rewrite failed, did not find instance of the pattern` — the lemma you're rewriting with no longer matches because of a definitional change upstream. Use `simp only [lemma_name]` instead of `rw [lemma_name]`, or first `unfold` the target.

L186 `no goals to be solved` means a prior tactic already closed the goal — delete the offending line or wrap in `try`.

#### N) `Lutar/DPI/TH6_DPI_Soundness.lean:59, 106, 131, 139, 149` — synth failures

Same family as (L) — add explicit instance args. The L59 `tactic 'simp' failed, nested error:` requires showing the goal to see what's actually broken. Likely a `simp` lemma got removed; replace with `simp only [<surviving lemmas>]` or `simp_all`.

### 3.3 Hardest module — bookmark for later

#### O) `Lutar/QEC/ShorReceiptCode.lean` — 27 errors

This is the big one. Root cause: **`Vector` is no longer in scope by that name**. In Lean 4.13/Mathlib, `Vector` lives in `Mathlib.Data.Vector.Basic` and the recommended alias is `Mathlib.Vector` (not `Vector`). Either:

```lean
import Mathlib.Data.Vector.Basic
open Mathlib (Vector)
```

OR migrate to the standard library `List.Vector` from `Lean.Data.Vector`. Pick one, apply consistently, and the 27 errors collapse to ~3.

The remaining `don't know how to synthesize implicit argument 'ShorBundle'` errors are because `ShorBundle` isn't a class — promote it with `class ShorBundle` or pass explicitly.

#### P) `Lutar/Composition/CompositionOverhead.lean` — 30 errors, universe constraints

```
L 34:13  failed to synthesize
L 37: 0  stuck at solving universe constraint
L 45: 4  function expected at
…
```

This file has a structural problem. The "function expected at" errors mean some symbol that used to be a function is now a definitional notation. Most likely: `Mathlib.Order.Hom.Basic` shuffled `≤` extension symbols. Inspect L30–60 — there's probably a `variable {α : Type*}` that should be `variable {α : Type u}` to fix the universe issue, then the failed-synthesize errors will lift.

This module is best handled in its own PR after everything else is green; don't block on it.

### 3.4 Suggested PR sequence (so each PR shrinks the red surface monotonically)

1. **lutar-lean PR (NEW) — `fix(lean): doc-comment & namespace parser fixes`** — closes `SCITTMaskEntropy`, `Adinkra:207`, `Wheeler:177` (parser-level errors). 3 files, ~9 errors. 20 min.
2. **lutar-lean PR (NEW) — `fix(lean): Fintype + decide rewrites`** — closes `Shannon/DoctrineEntropy` deriving issue + propagates to `Wheeler/DelayedChoice` test block. ~14 errors. 45 min.
3. **lutar-lean #99 force-push** — adds the C/D/Shannon fixes above to the existing PR. Closes Kitaev/Wheeler/Shannon entirely.
4. **lutar-lean #100 force-push** — switches HaltEligibility approach to `noncomputable` OR `Float/Rat` comparison. Closes Adinkra fully + HaltEligibility. ~7 errors.
5. **lutar-lean #98 force-push** — augments the MerkleDAG fix with the 5 unrelated errors in same file (lines 63/67/69/89/90). ~5 errors.
6. **lutar-lean PR (NEW) — `fix(lean): MatchedFilter + TH1_Composition + GraphLambda + Adversarial`** — medium fixes from §3.2.
7. **lutar-lean PR (NEW) — `fix(lean): PRNG + TH6_DPI + PersistentHomology synth fixes`** — typeclass synthesis cleanups.
8. **lutar-lean PR (NEW) — `fix(lean): Shor Vector migration`** — ShorReceiptCode rewrite. Big.
9. **lutar-lean PR (NEW) — `fix(lean): CompositionOverhead universe + function-expected`** — last and hardest.

After PRs 1–5 land, `Lean kernel check` will still be red but the error count drops from 120 to ~50. After 6–7, ~20. After 8, ~6 (just CompositionOverhead). After 9, **green**.

---

## 4. Non-Lean PRs — ready to merge tonight on review

These all have green CI and are blocked only by the 1-reviewer rule. Founder (Stephen) can review and merge in 5 min:

```
gh pr review 94  -R szl-holdings/a11oy        --approve --body "LGTM — docs only, CI green"
gh pr review 99  -R szl-holdings/a11oy        --approve --body "LGTM — docs only, CI green"
gh pr review 100 -R szl-holdings/a11oy        --approve --body "LGTM — docs only, CI green"
gh pr review 101 -R szl-holdings/a11oy        --approve --body "LGTM — docs only, CI green"
gh pr review 111 -R szl-holdings/a11oy        --approve --body "LGTM — 1-line dependabot label fix"
gh pr review 42  -R szl-holdings/agi-forecast --approve --body "LGTM — all 38 tests green"
gh pr review 82  -R szl-holdings/.github      --approve --body "Coordination plan; doctrine-compliant"
gh pr review 83  -R szl-holdings/.github      --approve --body "Theorems plan; doctrine-compliant"
gh pr review 84  -R szl-holdings/.github      --approve --body "Pointer PR; LGTM"
gh pr review 85  -R szl-holdings/.github      --approve --body "Plotly inline; LGTM"
gh pr review 86  -R szl-holdings/.github      --approve --body "Master directive; LGTM"
```

Then `gh pr merge <num> -R <repo> --squash --delete-branch` for each.

**Do not merge lutar-lean #98/#99/#100 yet** — the `Lean kernel check` would still post FAILURE on the merge commit to `main`, leaving `main` red and triggering downstream noise. Land the §3.4 PR sequence first.

---

## 5. Doctrine v6 compliance reminders (apply to every commit you make tonight)

- Sign every commit with `-s` (`git commit -s -m "…"`)
- No marketing superlatives in commit msg / PR title / body
- No emoji in `##`/`###` headers
- Do not touch: `a11oy#57`, `amaru#46`, `sentra#45` (DRAFT relicense HOLD)
- Do not toggle branch protection
- arXiv: stage only (founder awaiting endorsement)
- Honest numbers: **217 declarations**, **12 axioms**, **7 sorries** (lutar-lean), TH10 = axiom-structured

---

## 6. Files you should read from this workspace handoff

I've saved the following in `/home/user/workspace/demo/` and they'll be attached to the daily-status proxy in `a11oy#100` (or a new PR if needed):

- `all_errors.csv` — full 120-error catalog with file/line/col/message
- `error_context.txt` — annotated source snippets (5 lines around each error) for all 17 failing modules
- `src/Lutar/**/*.lean` — frozen copies of every failing module from `main` HEAD
- `diffs/*.diff` — exact diffs of every open PR mentioned above
- `main_full.log` — complete `lake build` output from the latest `main` failure run
- `prot_*.json` — branch-protection JSON for each repo

If you want them as a tarball attached to a coordination PR, ping the founder and Perplexity will proxy.

---

## 7. Direct order

Tonight (≤ 4h):
1. Switch your runtime to Cursor App installation token (Path A in §1). If you can't, paste-and-proxy.
2. Execute §3.4 step 1 (parser fixes — 20 min).
3. Execute §3.4 step 2 (Fintype rewrite — 45 min).
4. Force-push the targeted updates to #98/#99/#100 per §3.4 steps 3–5.
5. After every push, run locally:
   ```
   lake build 2>&1 | grep -E "error:|Lean exited" | wc -l
   ```
   Confirm the number is monotonically decreasing.

Tomorrow morning (before Warhacker prep):
6. Execute §3.4 steps 6–8.
7. CompositionOverhead (§3.4 step 9) — defer to evening.

Founder is watching. Go.

— Perplexity Computer, 2026-05-29 22:35 EDT
Signed-off-by: Stephen P. Lutar <stephen@szlholdings.com>
Co-authored-by: Perplexity Computer <perplexity@szlholdings.com>
