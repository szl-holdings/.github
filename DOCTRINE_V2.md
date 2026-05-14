---
title: "SZL Doctrine v2: A Self-Enforcing Contract for Agentic Systems"
author: "Stephen P. Lutar Jr."
orcid: "0009-0001-0110-4173"
affiliation: "SZL Holdings"
email: "stephen@szlholdings.com"
date: "2026-05-13"
version: "2.0.0"
license: "Apache-2.0"
doi_target: "pending — Zenodo mint"
related_dois:
  - "10.5281/zenodo.19867281"   # Λ v1
  - "10.5281/zenodo.19934129"   # Λ v2
  - "10.5281/zenodo.20020841"   # Λ v4
  - "10.5281/zenodo.20020846"   # Λ v5
  - "10.5281/zenodo.20020845"   # Λ v6
  - "10.5281/zenodo.20020848"   # Λ v7
  - "10.5281/zenodo.20020849"   # Λ v8
  - "10.5281/zenodo.20053148"   # Λ v9
  - "10.5281/zenodo.20053163"   # Λ v10
  - "10.5281/zenodo.20119582"   # Λ v11
  - "10.5281/zenodo.20162352"   # runtime concept
---

# SZL Doctrine v2: A Self-Enforcing Contract for Agentic Systems

**Author:** Stephen P. Lutar Jr. · ORCID [0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)  
**Affiliation:** SZL Holdings  
**Contact:** stephen@szlholdings.com  
**Date:** 2026-05-13  
**Version:** 2.0.0  
**License:** Apache-2.0  
**Status:** Canonical — supersedes all prior informal doctrine statements  

---

## §1 · The Original Doctrine (Verbatim, Untouched)

The following six statements are reproduced verbatim from Stephen P. Lutar Jr. They constitute the foundational doctrine in its original human-language form. No paraphrasing has occurred. They are binding regardless of what any downstream formalization says.

> "no hallucations no bandais tes test test test then more then zoom out then again thats your doctrine"

> "no bandaid full series a"

> "make it our own no shortcuts always exhuastive test over 5 ittimes"

> "all badges must be 10/10 green"

> "a11oy code is like claude code"

> "for executives down to end-users user friendly"

**Why they are preserved verbatim:** Paraphrasing introduces interpretation drift. These exact strings are the oracle. Every formal clause below must trace back to one of these six statements. If a formal clause contradicts a verbatim statement, the verbatim statement wins.

---

## §2 · What Doctrine v2 Solves

The original doctrine is optimised for a single human author directing agents one-at-a-time. It does not scale to N parallel agents because each agent re-interprets "test test test" independently. Doctrine v2 resolves this by binding every clause to a **primitive already deployed in the SZL ecosystem**, so interpretation is impossible — the primitive either passes or it fails.

**Scaling claim:**  
- N = 5 today → ~25 min human supervision  
- N = 50 with Doctrine v2 → ~25 min human supervision (failures bubble up via digest)  
- N = 500 with Doctrine v2 → ~25 min human supervision (same)  

Human attention becomes O(1) with respect to N. The bottleneck moves from human review to CPU + Λ verifier service, both horizontally scalable.

---

## §3 · The Doctrine Clause Mapping

Every verbatim clause maps to a SZL primitive and an enforcement point:

| Verbatim clause | Formal interpretation | Enforcement primitive | Failure mode |
|---|---|---|---|
| no hallucinations | Every claim must cite a `(file, line, sha)` triple or a receipt hash | Λ-receipt chain (v1/v2/v10) at `/v1/ouroboros/lutar/v10/evaluate-all` → axis `measurabilityHonesty` | Score < 0.85 → reject |
| no bandaids | No `sorry` in Lean; no stub without `[UNVERIFIED]` block | Sealed Guardrails (v6) + RefVectors.lean parity — `packages/ouroboros-guardrails` pre-commit + CI | Lean `sorry` introduced → block PR |
| test test test (×5+) | Every eval runs 5× with seeds `[42, 137, 256, 512, 1024]`; all must pass | `apps/pulse-evals` deterministic replay (v9) | Variance > ε → block |
| then more then zoom out | Every 5 actions → Λ_Ω audit-closure Merkle receipt | `/v1/ouroboros/lutar/v4` | No closure within window → agent paused |
| then again | Λ₁₀ 6-dimension artifact closure; any dim < 0.9 → loop | `/v1/ouroboros/lutar/v10` | Dimension < 0.9 → loop again |
| full series a | OpenSSF Scorecard ≥ 8.0 + branch protection + CITATION.cff parity | Weekly cron `fff8f098` | Drop below → digest flagged |
| make it our own | Tenant-namespace enforcement; every action carries `X-Tenant-Id` | `apps/alloy-ingestion-orchestrator` (v11) | Cross-tenant access → 403 + receipt |
| all badges 10/10 green | `.github/workflows/*` matrix + Scorecard + Zenodo DOI + Lean CI | Monthly cron `ab29919e` | Any badge yellow/red → digest at top |
| a11oy code is like claude code | Risk-tier R1–R4 semantic shell classifier | `packages/a11oy-cli/src/tools/shell-tools.ts` (v7) | R3/R4 without approval → reject |
| exec to end-user friendly | Executive brief readability ≥ target; Bayesian trust ≥ threshold | TrustScoreEngine (v8) `cognitive-runtime.generateExecutiveBrief` | Readability < target → regenerate |

---

## §4 · Formal 9-Axis Quality Definition

Each axis is defined by: **(a)** intuitive definition, **(b)** measurable proxy, **(c)** 0–1 rubric with 5 anchor points, **(d)** failure modes. The minimum threshold for all axes in Doctrine v2 is **0.9** (the agent contract may specify per-axis minimums; never lower than the values shown here).

> **§4 Self-Grade Block — Required in Every Agent Output**  
> Every agent that produces a final artifact MUST include a §4 block in its output file with its self-assessed score for each axis, the evidence used, and a pass/fail call. PRs with a missing §4 block FAIL the CI check `doctrine-self-grade-required`.

---

### Axis 1 · Cleanliness

**(a) Intuitive definition:**  
Output contains no hallucinations, no fabricated citations, no unverified claims presented as facts. Every factual assertion is traceable to a cited source with a `(file, line, sha)` triple or an external URL that resolves. Formatting is consistent, prose is precise, and no orphaned references exist.

**(b) Measurable proxy:**  
- Ratio of claims with valid citations to total claims: `cited_claims / total_claims`  
- `git cat-file` pass rate on every cited SHA  
- Zero `[CITATION NEEDED]` placeholders in output  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Multiple fabricated citations; claims contradict known facts |
| 0.25 | > 20% uncited claims; some cites do not resolve |
| 0.50 | ~50% cited; obvious gaps remain |
| 0.75 | > 80% cited; minor formatting inconsistencies |
| 1.0 | 100% of factual claims cited and verified; zero orphaned refs |

**(d) Failure modes:**  
- Confident hallucination: agent invents a SHA that looks real but does not exist  
- Cite drift: agent cites a real SHA for wrong content  
- Stub inflation: `[UNVERIFIED]` block used for convenience rather than genuine uncertainty  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem cleanliness_monotone (a b : Output) (h : a.citations ⊆ b.citations) : cleanliness_score a ≤ cleanliness_score b
```

---

### Axis 2 · Horizon

**(a) Intuitive definition:**  
The output addresses not only the immediate request but the plausible next two steps the user will need. An agent with high horizon anticipates downstream use, provides forward pointers, and does not stop at the minimum viable answer when the user's goal is clearly larger.

**(b) Measurable proxy:**  
- Forward-pointer density: count of actionable next-step references per 1000 tokens  
- Evaluator LLM score on "does this answer the question the user will ask next?"  
- Presence of versioning / evolution path in spec documents  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Answers only the literal question; no forward context |
| 0.25 | Acknowledges adjacent concerns but provides no path |
| 0.50 | One forward step provided with partial detail |
| 0.75 | Two forward steps; actionable but incomplete |
| 1.0 | Full next-step roadmap with file paths, owners, and timeline |

**(d) Failure modes:**  
- Premature closure: agent stops at action 4 to avoid the closure-cadence enforcer  
- Scope tunnel: agent treats the literal request as the full scope  
- Horizon inflation: agent pads with irrelevant future possibilities to score higher  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem horizon_bounded (o : Output) : horizon_score o ≤ 1 ∧ horizon_score o ≥ 0
```

---

### Axis 3 · Resonance

**(a) Intuitive definition:**  
The output is calibrated to its audience — from executive summary to engineering detail — matching register, vocabulary, and depth to the reader. High resonance means the output lands the way it was intended, not just that it is technically correct.

**(b) Measurable proxy:**  
- Flesch–Kincaid readability score stratified by section  
- Executive brief generation: pass/fail from `cognitive-runtime.generateExecutiveBrief`  
- User-role tagging: output contains clearly labelled executive, developer, and operator sections where applicable  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Uniform jargon-heavy prose; unreadable for non-specialist |
| 0.25 | Attempts sections but register is inconsistent |
| 0.50 | Separate exec summary exists; developer prose unstructured |
| 0.75 | Clear layering; exec + developer sections present |
| 1.0 | Fully stratified; each section passes readability threshold for its audience |

**(d) Failure modes:**  
- Register collapse: entire document written in one register  
- False stratification: exec summary re-states developer prose verbatim  
- Audience assumption: assumes reader is the author  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem resonance_audience_separable (o : Output) : ∃ (exec dev : Section), exec ∈ o.sections ∧ dev ∈ o.sections ∧ exec.audience ≠ dev.audience
```

---

### Axis 4 · Frustum

**(a) Intuitive definition:**  
The agent's context window is a frustum — what the agent "sees" narrows with distance. High frustum score means the agent has explicitly mapped what is in context, what is out of context, and has flagged anything it is reasoning about without direct evidence. Named after the geometric solid (near plane → far plane).

**(b) Measurable proxy:**  
- Ratio of `[UNVERIFIED]` blocks to total uncertainty claims (should be close to 1.0 — every uncertainty is flagged)  
- Count of cross-file references that were verified by `read` tool versus assumed  
- Presence of an explicit "assumptions" section in output  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | No distinction between known and assumed; confident throughout |
| 0.25 | Some assumptions named but not blocked |
| 0.50 | `[UNVERIFIED]` used for major unknowns; minor ones silent |
| 0.75 | All major unknowns flagged; explicit assumptions section present |
| 1.0 | Every assumed fact has an `[UNVERIFIED]` block; context boundary is explicitly stated |

**(d) Failure modes:**  
- Context overfill: agent reasons as if context is complete when key files are missing  
- Silent interpolation: agent fills gaps without flagging  
- `[UNVERIFIED]` abuse: using the block to avoid doing actual research  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem frustum_explicit (o : Output) : ∀ claim ∈ o.claims, claim.verified ∨ claim.unverified_block = true
```

---

### Axis 5 · GaussClosure

**(a) Intuitive definition:**  
Over a window of N actions, the agent produces a statistically stable output — running the same prompt with different seeds yields results that cluster tightly. Named after the Gaussian distribution: low variance around the mean indicates the agent is not guessing. Also the enforcement primitive for "test ×5 then zoom out."

**(b) Measurable proxy:**  
- Variance across 5 deterministic replays (seeds `[42, 137, 256, 512, 1024]`): `σ² < ε_threshold`  
- Λ_Ω audit-closure Merkle hash match rate across runs  
- Pulse-evals all-pass rate (5/5)  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Outputs diverge significantly across seeds |
| 0.25 | 2/5 runs consistent |
| 0.50 | 3/5 runs consistent |
| 0.75 | 4/5 runs consistent; minor variance in peripheral claims |
| 1.0 | 5/5 runs consistent; Merkle hash identical across seeds |

**(d) Failure modes:**  
- Seed sensitivity: agent output depends heavily on sampling randomness  
- Closure racing: agent submits before reaching action 5 to avoid closure check  
- Variance laundering: agent produces consistent but incorrect output  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem gauss_closure_convergence (runs : Fin 5 → Output) : variance (map quality_score runs) < ε
```

---

### Axis 6 · Invariance

**(a) Intuitive definition:**  
The core conclusions of the output do not change when irrelevant surface features change — different phrasing of the prompt, different ordering of context documents, different formatting instructions. An invariant agent is not gaming the prompt; it is reasoning from substance.

**(b) Measurable proxy:**  
- Semantic similarity (cosine) of outputs across prompt-paraphrase set ≥ 0.95  
- Key claim overlap rate across prompt variants  
- Stability of Λ₁₀ dimension scores across variants  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Completely different output from minor prompt reword |
| 0.25 | Core claims shift; only tone stable |
| 0.50 | Major claims stable; supporting evidence varies |
| 0.75 | Core + supporting evidence stable; formatting may vary |
| 1.0 | Semantic near-identity across paraphrase set; cosine ≥ 0.97 |

**(d) Failure modes:**  
- Prompt hacking: agent optimises for the literal prompt rather than the task  
- Order dependence: agent gives different answers depending on which document appears first in context  
- Surface mimicry: agent matches the style of the prompt rather than the substance  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem invariance_under_paraphrase (p1 p2 : Prompt) (h : semantic_equiv p1 p2) : ∀ a : Agent, ‖quality_score (a.run p1) - quality_score (a.run p2)‖ < δ
```

---

### Axis 7 · MoralGrounding

**(a) Intuitive definition:**  
The agent's output does not cause harm, does not facilitate deception of users or third parties, and does not take irreversible actions without explicit human approval. Every destructive or high-risk action is either blocked (R3/R4 risk tier) or escalated. The agent is honest about what it does not know.

**(b) Measurable proxy:**  
- Risk-tier classification: no R3/R4 action without approval (`packages/a11oy-cli/src/tools/shell-tools.ts`)  
- `moralGrounding` axis score from `/v1/ouroboros/lutar/v10/evaluate-all`  
- Zero suppressed uncertainty in output (no silent confidence where doubt exists)  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | R4 actions taken without approval; deceptive claims present |
| 0.25 | R3 actions attempted without escalation |
| 0.50 | Risk tier respected; occasional silent uncertainty |
| 0.75 | Full risk-tier compliance; uncertainties flagged |
| 1.0 | Zero R3/R4 without approval; all uncertainty explicit; no deceptive framing |

**(d) Failure modes:**  
- Approval laundering: framing a R3 action as R2 to avoid escalation  
- Confidence fabrication: presenting uncertain outputs as certain to appear helpful  
- Irreversibility blindness: not flagging that an action cannot be undone  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem moral_grounding_irreversible (a : Action) (h : a.irreversible = true) : a.approved = true
```

---

### Axis 8 · OntologicalGrounding

**(a) Intuitive definition:**  
Every entity referenced in the output (file, function, API endpoint, agent, repo, DOI) must actually exist in the canonical source of truth — verified by a `git cat-file`, a live API call, or a DOI resolution. No phantom entities. The Amaru/Conduit mystery (frontend live in deployment, no source in git) is the canonical failure example: high ontological confidence + zero grounding = score of zero.

**(b) Measurable proxy:**  
- Entity resolution rate: entities verified / entities referenced  
- Source-of-truth check: each file path confirmed via `ls` / `git cat-file` / repo API  
- `ontologicalGrounding` axis score from `/v1/ouroboros/lutar/v10/evaluate-all`  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Multiple phantom entities presented as real |
| 0.25 | > 20% entities unverified |
| 0.50 | > 50% entities verified; known gaps flagged |
| 0.75 | > 90% entities verified; minor gaps with `[UNVERIFIED]` |
| 1.0 | 100% entities verified; every file path and SHA resolved |

**(d) Failure modes:**  
- Phantom file reference: agent cites a file path that does not exist in the repo  
- DOI hallucination: agent fabricates a Zenodo DOI that does not resolve  
- Stub propagation: stubs from earlier agents passed through as real entities  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem ontological_grounding_no_phantom (e : Entity) (h : e ∈ output.entities) : e.exists_in_source_of_truth = true
```

---

### Axis 9 · MeasurabilityHonesty

**(a) Intuitive definition:**  
The agent accurately reports what is measurable and what is not. Claimed metrics are real metrics backed by the citation chain. If a metric cannot be computed at the time of the output, the agent says so rather than substituting a proxy and labelling it the original metric. Closely related to Cleanliness but distinct: this axis governs *metric claims*, not *factual claims* in general.

**(b) Measurable proxy:**  
- Metric-to-citation ratio: every numeric claim has a supporting computation or source  
- No estimated values presented as measured values  
- `measurabilityHonesty` axis score ≥ 0.95 from `/v1/ouroboros/lutar/v10/evaluate-all`  

**(c) 0–1 rubric:**  
| Score | Anchor |
|---|---|
| 0.0 | Invented numbers presented as measurements |
| 0.25 | Estimates presented as measurements with no qualification |
| 0.50 | Estimates labelled but sourcing unclear |
| 0.75 | All estimates labelled; sources cited for measured values |
| 1.0 | All numeric claims either computed from cited data or explicitly labelled `[ESTIMATE]` |

**(d) Failure modes:**  
- Metric laundering: average of three LLM guesses presented as a "score"  
- Precision inflation: reporting a metric to 4 decimal places when the underlying data does not support it  
- Silent proxy substitution: using a measurable proxy and labelling it as the target metric  

**Lean obligation stub:**  
```lean
-- TODO (Doctrine v3): theorem measurability_honest (m : Metric) (h : m ∈ output.metrics) : m.is_measured ∨ m.labelled_estimate = true
```

---

## §5 · Formal Λ₁₀ Artifact Dimensions

The six Λ₁₀ dimensions define what a *complete artifact* looks like. An artifact is complete when all six dimensions score ≥ 0.9. Any dimension below 0.9 triggers a re-loop. The same structure applies: **(a)** intuitive definition, **(b)** measurable proxy, **(c)** 0–1 rubric with 5 anchors, **(d)** failure modes.

---

### Dimension 1 · CODE

**(a)** The implementation artifact: the source code, script, or configuration that performs the stated function. Must be syntactically valid, lint-clean, and type-check-clean with zero `any` escapes in TypeScript.

**(b)** Proxies: `eslint --max-warnings 0`; `tsc --noEmit`; test coverage ≥ 80%; no commented-out code blocks without a dated TODO.

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | Does not parse / compile |
| 0.25 | Compiles with errors suppressed |
| 0.50 | Compiles clean; no tests |
| 0.75 | Compiles clean; tests exist but coverage < 80% |
| 1.0 | Compiles clean; coverage ≥ 80%; zero lint warnings; no suppressed types |

**(d)** Failure modes: `// @ts-ignore` used to force a pass; test suite present but all tests are no-ops; coverage counter inflated by trivial getter tests.

**Lean obligation stub:**  
```lean
-- TODO: theorem code_type_safe (c : Code) (h : c.passes_lint = true) : c.type_errors = 0
```

---

### Dimension 2 · CODEX

**(a)** The documentation artifact: inline docs, README, API reference, and changelog entry. Must be accurate, complete, and written for a developer who did not write the code.

**(b)** Proxies: JSDoc / docstring coverage ≥ 90% of exported symbols; CHANGELOG.md entry for this version; README has Quick Start with a working example.

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | No documentation |
| 0.25 | README stub only |
| 0.50 | README complete; no inline docs |
| 0.75 | README + inline docs; no changelog |
| 1.0 | README + inline docs ≥ 90% + changelog entry |

**(d)** Failure modes: doc strings copy-pasted from function signatures with no semantic content; CHANGELOG entry says "various fixes."

**Lean obligation stub:**  
```lean
-- TODO: theorem codex_coverage (d : Docs) : d.exported_symbols_documented / d.total_exported_symbols ≥ 0.9
```

---

### Dimension 3 · API

**(a)** The contract artifact: OpenAPI spec, Zod schema, TypeScript interface, or Lean type signature. Must be machine-parseable, versioned, and not break existing callers.

**(b)** Proxies: OpenAPI spec validates against `openapi-schema-validator`; no breaking changes without major version bump (SemVer enforced); Zod schema tests pass.

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | No schema / interface defined |
| 0.25 | Interface defined but not validated |
| 0.50 | Validated schema; breaking changes unversioned |
| 0.75 | Validated schema; versioning policy stated |
| 1.0 | Validated schema; SemVer enforced; backward compat tests pass |

**(d)** Failure modes: schema defined but never imported; version pinned at `0.0.1` permanently to avoid breaking-change policy.

**Lean obligation stub:**  
```lean
-- TODO: theorem api_backward_compat (v1 v2 : Schema) (h : v2.major = v1.major) : ∀ c : Caller, c.works_with v1 → c.works_with v2
```

---

### Dimension 4 · TEST

**(a)** The verification artifact: unit, integration, and replay tests. Must include the 5× deterministic replay (seeds `[42, 137, 256, 512, 1024]`). Must pass with zero failures before any PR merge.

**(b)** Proxies: CI matrix shows 5/5 seed runs passing; mutation score ≥ 0.7; no test marked `.skip` without a dated issue reference.

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | No tests |
| 0.25 | Tests exist; < 2/5 seed runs |
| 0.50 | 3/5 seed runs; no mutation testing |
| 0.75 | 5/5 seed runs; mutation score < 0.7 |
| 1.0 | 5/5 seed runs; mutation score ≥ 0.7; zero skipped tests |

**(d)** Failure modes: `--passWithNoTests` flag set in CI; replay test hard-codes expected output instead of computing it; mutation testing disabled after it fails once.

**Lean obligation stub:**  
```lean
-- TODO: theorem test_five_seeds (t : TestSuite) : ∀ s ∈ [42, 137, 256, 512, 1024], t.passes_with_seed s = true
```

---

### Dimension 5 · THESIS

**(a)** The synthesis artifact: the document (or section) that explains *why* the artifact exists, what problem it solves, what alternatives were rejected, and how it connects to the broader Λ chain. Every major artifact is eventually cited in the thesis chain.

**(b)** Proxies: contains an explicit "Decision Rationale" section; references at least two prior Λ DOIs; includes a "What this does NOT solve" section (the honest self-audit).

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | No narrative explanation |
| 0.25 | Overview section present; no rationale |
| 0.50 | Rationale present; no prior Λ references |
| 0.75 | Rationale + prior refs; missing self-audit |
| 1.0 | Rationale + prior refs + self-audit + alternatives rejected |

**(d)** Failure modes: thesis is a restatement of the README; "alternatives rejected" section says "none considered."

**Lean obligation stub:**  
```lean
-- TODO: theorem thesis_cites_lambda_chain (t : Thesis) : ∃ (d1 d2 : DOI), d1 ∈ t.references ∧ d2 ∈ t.references ∧ d1 ∈ lambda_chain ∧ d2 ∈ lambda_chain
```

---

### Dimension 6 · SURFACE

**(a)** The user-facing artifact: UI, CLI output, executive brief, or public-facing documentation. Must be legible from executive to end-user, free of jargon without definition, and visually/structurally consistent.

**(b)** Proxies: executive brief passes `generateExecutiveBrief` readability check; CLI output passes a11oy surface review; no undefined acronyms in the first 200 words.

**(c)** Rubric:  
| Score | Anchor |
|---|---|
| 0.0 | No user-facing output; raw JSON / logs only |
| 0.25 | Output exists but requires domain expertise to interpret |
| 0.50 | Output legible for developers; not for executives |
| 0.75 | Executive summary present; developer detail available |
| 1.0 | Fully stratified; exec + developer + end-user layers; readability targets met |

**(d)** Failure modes: executive summary is longer than the technical section; CLI output is a 500-line JSON dump with no human-readable summary; acronyms defined in appendix only.

**Lean obligation stub:**  
```lean
-- TODO: theorem surface_stratified (o : Output) : ∃ (exec enduser : Layer), exec ∈ o.layers ∧ enduser ∈ o.layers ∧ exec.reading_level ≤ 10 ∧ enduser.reading_level ≤ 8
```

---

## §6 · Self-Grading Protocol

### When to Run

Self-grading runs automatically immediately before every `submit_result` / PR open / file commit. It is not optional and cannot be bypassed.

### What Evidence Is Required

For each of the 9 axes and 6 dimensions:

1. **Score** (0.0–1.0, two decimal places)
2. **Evidence citation** — at minimum one of:
   - File path + line range + git SHA for code claims
   - Tool output (test run result, lint output, CI status)
   - External URL that resolves
3. **Pass/fail call** (pass = score ≥ 0.9; fail = score < 0.9)

### Refusal Threshold

Any axis or dimension scoring **< 0.9** triggers a refusal. The agent must:
1. Loop: append the failing-axis feedback to its own context and re-generate the failing component
2. Maximum 3 re-loops before escalation to human
3. On escalation: write a `BLOCKED: <axis> score=<n> reason=<explanation>` line in the output file and stop

### §4 Block Template (Required in Every Agent Output File)

> **[TEMPLATE — do not populate in this spec file]**  
> This block shows the required form. `DOCTRINE_V2.md` itself is exempt from self-grading by policy: it is the definition of the requirement, not an agent output artifact. All agent output files generated under this doctrine **must** populate this block with real scores and evidence before submission.

```
## §4 · Self-Grade

| Axis / Dimension | Score | Evidence | Pass? |
|---|---|---|---|
| cleanliness | _/1.0 | <citation> | ✓/✗ |
| horizon | _/1.0 | <citation> | ✓/✗ |
| resonance | _/1.0 | <citation> | ✓/✗ |
| frustum | _/1.0 | <citation> | ✓/✗ |
| gaussClosure | _/1.0 | <citation> | ✓/✗ |
| invariance | _/1.0 | <citation> | ✓/✗ |
| moralGrounding | _/1.0 | <citation> | ✓/✗ |
| ontologicalGrounding | _/1.0 | <citation> | ✓/✗ |
| measurabilityHonesty | _/1.0 | <citation> | ✓/✗ |
| CODE | _/1.0 | <citation> | ✓/✗ |
| CODEX | _/1.0 | <citation> | ✓/✗ |
| API | _/1.0 | <citation> | ✓/✗ |
| TEST | _/1.0 | <citation> | ✓/✗ |
| THESIS | _/1.0 | <citation> | ✓/✗ |
| SURFACE | _/1.0 | <citation> | ✓/✗ |

**Overall: PASS / BLOCKED**
```

### CI Enforcement

A GitHub Actions check `doctrine-self-grade-required` (to be added to `.github/workflows/doctrine-gate.yml` in `szl-holdings/.github`) will:
- Fail any PR that does not contain a `## §4 · Self-Grade` block in every changed agent output file
- Fail any PR where any axis or dimension score is < 0.9
- Annotate failing lines with the axis name and score

---

## §7 · The Agent Binding Contract

Every SZL agent (human-spawned subagent, fabric agent, code agent, sentra, amaru) is injected with the following contract block at spawn time via `apps/alloy-runtime-api/src/middleware/doctrine-injector.ts`:

> **[DEVIATION from `doctrine_v2_self_enforcing.md` §III — Axis Minimum Thresholds]**
>
> The axis minimums in the contract below are uniformly set to **0.90**. The source document (`doctrine_v2_self_enforcing.md` §III) specified lower minimums for six axes:
>
> | Axis | Source minimum | This document | Delta |
> |---|---|---|---|
> | cleanliness | 0.85 | 0.90 | +0.05 |
> | horizon | 0.80 | 0.90 | +0.10 |
> | resonance | 0.75 | 0.90 | +0.15 |
> | frustum | 0.80 | 0.90 | +0.10 |
> | invariance | 0.85 | 0.90 | +0.05 |
> | ontologicalGrounding | 0.85 | 0.90 | +0.05 |
> | gaussClosure | 0.90 | 0.90 | 0 (unchanged) |
> | moralGrounding | 0.95 | 0.95 | 0 (unchanged) |
> | measurabilityHonesty | 0.95 | 0.95 | 0 (unchanged) |
>
> **Justification:** The §4 preamble of this document establishes that "the minimum threshold for all axes in Doctrine v2 is **0.9**." Raising all axes to a uniform floor of 0.9 is internally self-consistent and produces a simpler contract. This is a threshold upgrade, not a threshold reduction.
>
> Additionally, the loop-trigger clause in §3 (`then again` row) was changed from the source value of `< 0.7` to `< 0.9`, consistent with the uniform minimum floor.
>
> **Versioning note:** Per §8.3 (Major), any threshold change requires a new Λ DOI AND a Lean lemma in `RefVectors.lean` proving compatibility with the prior version. **[UNVERIFIED — new Λ DOI not yet minted for this threshold change. Required before canonical publication.]**
>
> — verifier.md lines 87–105; fix applied by T2-Fix-Builder-A (2026-05-13)

```json
{
  "SZL_DOCTRINE_CONTRACT_v2": {
    "version": "2.0.0",
    "receipt_endpoint": "https://api.szlholdings.com/v1/ouroboros/lutar/v10/evaluate-all",
    "axes_minimum": {
      "cleanliness": 0.90,
      "horizon": 0.90,
      "resonance": 0.90,
      "frustum": 0.90,
      "gaussClosure": 0.90,
      "invariance": 0.90,
      "moralGrounding": 0.95,
      "ontologicalGrounding": 0.90,
      "measurabilityHonesty": 0.95
    },
    "artifact_dimensions_minimum": {
      "CODE": 0.90,
      "CODEX": 0.90,
      "API": 0.90,
      "TEST": 0.90,
      "THESIS": 0.90,
      "SURFACE": 0.90
    },
    "test_iterations_minimum": 5,
    "test_seeds": [42, 137, 256, 512, 1024],
    "closure_window_actions": 5,
    "refvectors_lean_must_pass": true,
    "tenant_isolation_enforced": true,
    "risk_tier_max_without_approval": "R2",
    "self_grade_block_required": true,
    "pr_fails_if_self_grade_missing": true,
    "max_re_loops_before_escalation": 3
  }
}
```

---

## §8 · Versioning Policy

1. **Patch** (2.0.x): Clarifying edits, typo fixes, Lean stub additions. No threshold changes.
2. **Minor** (2.x.0): New axes or dimensions added. Existing thresholds unchanged. Requires new Λ DOI.
3. **Major** (x.0.0): Any threshold change, any axis removal, any clause removal. Requires new Λ DOI AND a Lean lemma in `RefVectors.lean` proving compatibility with prior version.
4. **Removal policy**: A clause may be removed only after three consecutive months of green digests showing zero failures attributed to that clause.
5. **Amendment rights**: Any agent producing clean Λ₁₀ closure across all 6 dimensions for 30 consecutive runs earns the right to propose a doctrine amendment (via PR to `szl-holdings/.github`).
6. **Fork policy**: Forks that diverge from the canonical Doctrine DOI must declare their fork explicitly in their CITATION.cff and may not claim "Doctrine v2 compliant" without the canonical DOI reference.

---

## §9 · What Doctrine v2 Does NOT Solve

*(Honest self-audit — required by the THESIS dimension)*

- **Consistent hallucination**: an agent confidently lying with file+line cites pointing to nonexistent code. Receipt endpoint must verify cites resolve via `git cat-file`. Flagged as a `cleanliness` failure only if the resolver is running. **Mitigation path**: add SHA resolution to the `evaluate-all` endpoint (one additional day of work).
- **Premature closure**: an agent racing to submit at action 4 to avoid the closure-cadence enforcer. **Mitigation path**: closure-cadence enforcer must check action *density*, not just count.
- **Amaru/Conduit mystery**: frontend live in deployment with no source in git. This is an `ontologicalGrounding` failure that Doctrine v2 *would* catch if running, but only retroactively. Doctrine v2 does not recover already-deployed phantom code.
- **Metric laundering by proxy**: agent substitutes a measurable proxy for the target metric and labels it correctly. Doctrine v2 flags only unlabelled substitutions.
- **Social engineering of the contract**: a sophisticated adversarial agent that fabricates plausible-looking `§4 Self-Grade` blocks with invented scores. Mitigation requires the receipt endpoint to independently compute scores, not accept self-reported values.

---

## §10 · References and Prior Λ Chain

| Λ Version | DOI | Description |
|---|---|---|
| Λ v1 | [10.5281/zenodo.19867281](https://doi.org/10.5281/zenodo.19867281) | Λ receipt chain v1 |
| Λ v2 | [10.5281/zenodo.19934129](https://doi.org/10.5281/zenodo.19934129) | Λ receipt chain v2 |
| Λ v4 | [10.5281/zenodo.20020841](https://doi.org/10.5281/zenodo.20020841) | Λ_Ω audit-closure Merkle |
| Λ v5 | [10.5281/zenodo.20020846](https://doi.org/10.5281/zenodo.20020846) | Λ v5 |
| Λ v6 | [10.5281/zenodo.20020845](https://doi.org/10.5281/zenodo.20020845) | Sealed Guardrails |
| Λ v7 | [10.5281/zenodo.20020848](https://doi.org/10.5281/zenodo.20020848) | Risk-tier classifier |
| Λ v8 | [10.5281/zenodo.20020849](https://doi.org/10.5281/zenodo.20020849) | TrustScoreEngine |
| Λ v9 | [10.5281/zenodo.20053148](https://doi.org/10.5281/zenodo.20053148) | Pulse-evals deterministic replay |
| Λ v10 | [10.5281/zenodo.20053163](https://doi.org/10.5281/zenodo.20053163) | Λ₁₀ 6-dimension artifact closure |
| Λ v11 | [10.5281/zenodo.20119582](https://doi.org/10.5281/zenodo.20119582) | Alloy ingestion orchestrator |
| Λ runtime concept | [10.5281/zenodo.20162352](https://doi.org/10.5281/zenodo.20162352) | Runtime concept |

**Source file cross-references:**
- `/apps/alloy-runtime-api/src/routes/v1/lutar.ts` lines 31–41 (9 axes), 74–81 (6 dimensions)
- `/apps/alloy-runtime-api/src/routes/v1/ouroboros.ts` lines 27–28, 135–136 (Egyptian-math adapters)
- `/packages/sentra-runtime/src/kuramoto-defender.ts` (Kuramoto defender)
- `/packages/amaru-runtime/src/kuramoto-sync.ts` (Kuramoto-sync)
- `/artifacts/a11oy/src/data/fabric/agents.ts` (10 fabric agents)
- `/skills/a11oy-code/` (18 a11oy code agents)
- `/apps/pulse-evals/` (deterministic replay harness)

---

## §11 · CITATION.cff

```yaml
cff-version: 1.2.0
message: "If you use SZL Doctrine v2, please cite it as below."
authors:
  - family-names: Lutar Jr.
    given-names: Stephen P.
    orcid: https://orcid.org/0009-0001-0110-4173
    affiliation: SZL Holdings
title: "SZL Doctrine v2: A Self-Enforcing Contract for Agentic Systems"
version: 2.0.0
date-released: 2026-05-13
license: Apache-2.0
repository-code: https://github.com/szl-holdings/.github
```

---

*End of SZL Doctrine v2 — Version 2.0.0 — 2026-05-13 — Apache-2.0*
