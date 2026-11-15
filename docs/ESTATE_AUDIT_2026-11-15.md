# SZL Holdings Estate Audit — 2026-11-15 (pass 9d)

> Full-org, full-Hub, full-DOI audit. Owner order: audit everything, no gaps or
> bandaids; zoom out to the leaders and their publications; wire and publish;
> hardcode the results in GitHub. Fail-closed receipts throughout
> (`frontier-54-runs` receipts chain, updated 07:53Z same day).

## 1. GitHub org `szl-holdings` — 159 repositories

- **130 active** (24 private) / 29 archived. Zero stale repos (all active repos
  updated ≥ 2026-11-05).
- **CITATION.cff**: 100% coverage on active public repos. **DOI wiring**: pass 9c
  closed the 18 erroneous "purge" PRs and wired 12 repos to canonical DOIs;
  pass 9d wave wired the remaining 57 repos with today-minted concept
  DOIs (PR-per-repo, conventional titles, `chore: wire canonical Zenodo DOI into
  CITATION.cff`). See §3 for the canonical DOI rule.
- **Licenses**: every active repo licensed and machine-detectable after this pass.
  `szl-energy-mcp` was the sole NOASSERTION (short-form Apache boilerplate);
  fixed with the estate-canonical Apache-2.0 text (PR #2, corrected byte-exact by
  PR #3 after a retyping defect was caught — 11,358 bytes, matches
  `szl-asset-registry`).
- **Attribution watermark campaign**: complete — 105/105 merged (final PR
  szl-holdings/.github#1019, merge 57d6024).
- **Repository-rule note**: several repos (platform, szl-typesafe-triage …) forbid
  merge commits; squash/rebase only. szl-typesafe-triage#92 (DOI wiring) is
  blocked by a pre-existing red `gate` check unrelated to the PR — retry when
  the repo check is green.
- **Asset registry hardening** (szl-asset-registry#5, merge 7b8a5c9): curated
  `overrides.json` (evidence-cited) with highest mapping precedence; fixes the
  hardcoded `generated:` date; adds the `override` mapping method; validate.py
  updated. Seeded with 6 verified mappings (receipts chain + officer spaces →
  szl-gpu-bridge).

## 2. Hugging Face org `SZLHOLDINGS`

- **131 models, 71 datasets, 34 spaces — all public. All 34 spaces RUNNING**
  (verified per-space via the Hub API; `hardware.current` reads null org-wide,
  which is an API field artifact for zero-hardware spaces, not a runtime fault).
- **Asset map** (`szl-asset-registry/asset_map.json`, regenerated with the
  overrides mechanism): 351 assets — 222 mapped (+6 override), 129 unmapped.
  Unmapped are almost entirely private machine-run artifacts
  (laptop-lora-training ×20, candidate-eval-20261104 ×26, run-artifact stores).
  Fail-closed by design: no guessed mappings.
- **Orphans (no GitHub source at all)** — 7 Spaces had been created outside
  repo control: `frontier-showcase`, `szl-research-council`, `szl-infra-warden`,
  `szl-receipts-chain`, `szl-energy-hologram`, `khipu-playground`,
  `truth-router`. **FIXED this pass**: all 7 snapshotted byte-for-byte into
  `szl-gpu-bridge/hf-spaces/<name>/snapshot/` with per-Space provenance READMEs
  and a manifest (szl-gpu-bridge#189, merged). Every deployed Space now has a
  hardcoded GitHub source.
- **Receipts chain** `SZLHOLDINGS/frontier-54-runs` live and fresh (07:53Z);
  registry snapshot inside it reconciles 131 models.

## 3. Zenodo DOI estate

- Two accounts: May-2026 originals (owner 1628948, 47 records) and today's
  `szlholdings` (owner 2014246, 115 records).
- **Canonical rule (doctrine, DOI CORRECTION 2026-11-15)**: May originals are
  canonical where they exist (Ouroboros Thesis concept 10.5281/zenodo.19944926 —
  never replace; lutar-lean v18 20434308; szl-brand 20436556; a11oy 20563581;
  sentra 20519133; amaru 20519134; uds-mesh 20451999; agi-forecast 20436560;
  szl-cookbook 20436558; vessels 20451595; Stellar Death Clock paper 20434275).
  Else the today-minted **concept DOI** is canonical (always resolves to latest
  version). Duplicate version records retained; no deletions.

## 4. PyPI

- **Live (7)**: `szl-triage` 0.5.2, `szl-substrate`, `szl-kernels`, `szl-router`,
  `szl-pin`, `szl-receipt-dsse` 0.3.4, `hatun-mcp` 1.0.3 (gap-sweep lane, same
  day) — all via the canonical `szl.pypi-release.v2` path (OIDC Trusted
  Publishing, no tokens, PEP 740 attestations).
- **In-flight (parallel lane, staged release branches)**: `szl-formulas`,
  `szl-provctl`, `puriq-live` — their earlier Do-Not-Upload markers superseded by
  staged release paths; left to that lane.
- **Publish path added this pass** (byte-exact copies from szl-pin): `szl-atelier`
  (#72 merged), `szl-drift` (#20 merged). First release requires the one-time
  owner-side pending-publisher registration on pypi.org (in progress via the
  browser lane) and a `v<version>` GitHub Release.
- **Do-Not-Upload by doctrine** (classifiers present, intentional):
  `szl-lambda-gate`, `szl-evidence-core`, `szl-govsign` —
  universal Hub kernels / primitives, not pip distributions.
- **Flagged**: `szl-gov` pyproject declares `packages = []` → builds an empty
  wheel. Fix the package discovery before any release.

## 5. Cloudflare

- Live on CF: `a-11-oy.com`, `a11oy.net`, `inference.a-11-oy.com` (HSTS preload).
- **Gap**: `szlholdings.com` has no DNS/HTTPS — registrar/DNS + CF zone setup is
  owner-gated. `a11oy#3250` (Cloudflare email sender, GitOps) is open and ready.
- **Frontier**: Cloudflare Workers AI now serves large models (Kimi K2.5) and an
  agent inference layer — candidate edge for a11oy inference beyond
  inference.a-11-oy.com.

## 6. Training / benchmark posture

- Salad v4 frontier lane running since 04:18Z (frontier-54-runs pushing);
  estate-battery heavy-4B 13-model run in progress (doctrine 07:1x entry).
  Battery/eval receipts land in the receipts chain — measured, never asserted.

## 7. Leaders & publications study (zoom-out)

| Domain (estate repo) | Leaders | Publications to adopt |
|---|---|---|
| Governed agents (a11oy) | LangChain/LangGraph, OpenAI Agents SDK, Anthropic MCP | **AgentAbstain** (do agents know when not to act?) — direct fit for the abstention doctrine; τ-style agent evals |
| Abstention / honesty (estate-wide) | Verifiable-reward RL lines | **Abstain-R1** (arXiv:2604.17073): calibrated abstention + post-refusal clarification via verifiable RL — the estate's `grpo_absention.py` should adopt the post-refusal-clarification reward; **RefusalBench** for calibration measurement |
| Formal math (lutar-lean) | Lean FRO/mathlib, DeepSeek-Prover, AlphaProof | **FormalMATH** + **ProofFrontier** as external benchmarks for the 5-proven theorem base; **SCOPE** (certified theorem proving, alphaxiv 2610.08319) pattern for policy-planner proving |
| LLM routing (szl-router) | LiteLLM, OpenRouter, Portkey | RouteLLM-style cost/quality prediction; keep the governed-gate differentiator |
| Post-training recipes (szl-forge) | AI2 Tülu 3, DeepSeek GRPO lines | GRPO with verifiable rewards for the 0.8B/1.5B abstention battery |
| LLM observability (vsp-otel) | OpenTelemetry GenAI semantic conventions | `open-telemetry/semantic-conventions-genai` alignment for spans |
| Agentic SOC (sentra) | SentinelOne ASOC, CrowdStrike agentic SOC | Purple-AI-style triage loops with receipted evidence |
| Sovereign delivery (uds-mesh) | Defense Unicorns **UDS Core 1.0** | Align bundle layout to UDS Core 1.0 |
| Maritime (vessels) | Windward, Spire | "Verified maritime intelligence" positioning — provenance-gated AIS enrichment |
| Data integration (amaru) | Airbyte, Fivetran (post-merger), dbt | MAR-based connector economics; CDC posture |

### Math/software tweaks recommended (concrete)
1. Adopt **post-refusal clarification** (Abstain-R1): after an abstain, the next
   turn should ask a clarifying question instead of a bare refusal — trainable
   with the existing GRPO harness + verifiable reward.
2. Externalize the abstention battery: report estate models on
   RefusalBench/AgentAbstain so 5/6-style internal scores have public anchors.
3. Formal-math expansion: target FormalMATH problems in Lean 4; every proven
   theorem lands in the receipts chain (`lean/`, 5 → N, zero sorry).
4. Bind vsp-otel spans to the GenAI semantic conventions so estate receipts are
   queryable with standard OTel tooling.

## 8. Gaps and recommendations (owner-side unless noted)

1. **szlholdings.com DNS/HTTPS** — registrar/CF action, owner-gated. Biggest
   public-surface gap.
2. **PyPI pending-publisher registrations** for `szl-atelier`, `szl-drift`
   (browser lane in progress), then tag `v0.1.0` releases.
3. ~~Orphan Spaces~~ — resolved this pass (szl-gpu-bridge#189, §2).
4. **szl-gov pyproject** package discovery fix before any release.
5. **Supply-chain attestation roadmap (planned, not claimed)**: OpenSSF
   Scorecard analysis is wired via the org reusable workflow; attestation
   posture today remains SLSA L1 honest; L3 is planned future work, not a
   current claim (attestation/qillqaq already signs gate runs in .github).
6. **arXiv/OSF presence** for the thesis + Stellar Death Clock paper (Zenodo
   DOIs exist; preprint mirrors would raise discoverability).
7. **Trademark** (owner-side legal) for SZL Holdings marks.
8. **ROSA_GPU_TRAINING_HOLD.json** lives on ROSA hardware — owner-side only.

## 9. Receipts (this pass)

- 18 erroneous purge PRs closed with doctrine citation (pass 9c, carried into 9d).
- 12 pass-9c wiring PRs merged; platform#1056, #1019 merged this pass.
- Pass 9d wiring wave: 57 PRs (33 merged at audit-commit time, 12 pending CI/policy
  with an auto-retry watcher armed; results in `wire_results.json` on the operator
  host; final counts land in the doctrine log).
- szl-energy-mcp #2 + #3 (canonical LICENSE, byte-verified 11,358).
- szl-asset-registry #5 (overrides + dynamic date).
- szl-atelier #72, szl-drift #20 (canonical PyPI release path).
- szl-gpu-bridge #189 (7 orphan Space snapshots + manifest) — merged.
- PyPI live checks: szl-triage 0.5.2, szl-receipt-dsse 0.3.4, hatun-mcp 1.0.3 (HTTP 200).
- frontier-54-runs receipts chain updated 07:53Z.
