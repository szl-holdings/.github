<!-- markdownlint-disable MD013 -->

# SZL public-estate experience audit — 2026-08-01

Status: **MEASURED inventory with PARTIAL deep-tree coverage**

This audit covers every GitHub repository visible to the connected
`szl-holdings` installation and every public model, dataset, and Space returned
for `SZLHOLDINGS` by the Hugging Face API on 2026-08-01. It separates inventory,
transport state, documentation completeness, visual quality, and operational
capability.

This pull request upgrades only the GitHub and Hugging Face organization front
doors. It does **not** claim that every repository, model card, dataset card, or
Space has been restyled or operationally verified.

## Executive finding

The estate has strong technical depth and an adopted public-experience standard,
but its public story is fragmented across too many equally weighted surfaces.
The screenshot defect is real: the first viewport depends on a separate hero
asset and fails badly when that asset does not paint. The same viewport also
allocates half its area to that single dependency, so the failure becomes the
entire experience.

The fix is not more glow. It is a stronger hierarchy:

1. one mission sentence;
2. one resilient visual system;
3. three audience paths — operator, builder, verifier;
4. a curated canonical portfolio;
5. evidence and runtime labels kept separate;
6. long-tail artifacts demoted from the first decision path.

## What leading technology companies teach

The new direction borrows principles, not assets or layouts:

- [OpenAI on GitHub](https://github.com/openai) makes the organization page a
  curator: identity, domain, and a small set of canonical repositories carry
  more weight than a large profile essay.
- [Anthropic](https://www.anthropic.com/) leads with mission, then separates
  product, research, and policy. One surface is not forced to serve every
  audience in the same order.
- [Linear](https://linear.app/homepage) establishes the category and outcome in
  the first viewport, then uses product-in-context sections instead of an
  undifferentiated feature wall.
- [Stripe](https://stripe.com/) pairs brand confidence with unusually clear
  developer paths. Visual polish never substitutes for integration clarity.
- [Vercel AI](https://vercel.com/ai) uses a system relationship as the hero
  visual. The visual explains orchestration; it is not decoration alone.

Applied to SZL: mission-first copy, one original evidence lattice, restrained
teal/indigo/gold accents, hard-contrast actions, and separate operator, builder,
and verifier paths.

## Inventory and method

### GitHub

- 62 accessible repositories
- 58 public; 4 private
- 55 active; 7 archived
- all 62 have descriptions in current repository metadata
- 8 lack topics
- 2 archived repositories lack license metadata
- no README absence was confirmed; eight initial README requests timed out and
  were recovered through the connected GitHub service
- nine recursive tree requests timed out; those repositories were classified
  from metadata, README content, and organization code search instead

The strict README scanner looked for the adopted front-door contract: status,
quickstart, architecture, verification, limits, security, support,
contribution, changelog, and license. Lexical scans can under-detect equivalent
language, so the results are prioritization signals, not compliance verdicts.

### Hugging Face

- 16 models
- 27 datasets
- 26 ordinary Spaces plus the `SZLHOLDINGS/README` organization-front-door Space
- every enumerated artifact has a README
- all 27 Spaces reported `RUNNING` at observation time

`RUNNING` is a Hub transport-stage observation. It does not establish feature
correctness, production readiness, privacy behavior, or model quality.

## Priority model

| Priority | Meaning |
| --- | --- |
| **P0** | Company, flagship product, proof, or documentation front door |
| **P1** | Public interactive surface or canonical developer substrate |
| **P2** | Supporting library, research, governance, or specialist surface |
| **P3** | Archived or historical; preserve successor and evidence links |

## GitHub repository register

| Repository | State | Surface class | Priority / next action |
| --- | --- | --- | --- |
| `.github` | Active public | Organization front door and governance | **P0 — upgraded in this PR; protect the single visual and three audience paths** |
| `platform` | Active public | Canonical monorepo and multi-app substrate | **P1 — inventory each public route; do not apply one theme blindly across internal apps** |
| `a11oy` | Active public | Flagship governed-inference product | **P0 — preserve current strong live direction; complete route, asset, mobile, and evidence-label QA** |
| `ouroboros` | Active public | Research/runtime lineage | **P2 — developer-first README and explicit maturity boundary** |
| `szl-cookbook` | Active public | Recipes and learning path | **P1 — make tasks and tested quickstarts the visual hierarchy** |
| `szl-trust` | Active public | Trust and assurance material | **P1 — evidence-first information architecture; no decorative status green** |
| `szl-brand` | Active public | Token and brand authority | **P1 — publish versioned tokens, component examples, and adoption map** |
| `lutar-lean` | Active public | Formal-methods source | **P1 — theorem boundary, reproduction, and generated-doc navigation** |
| `vsp-otel` | Active public | Telemetry integration | **P2 — architecture, limits, and runnable verification path** |
| `szl-otel-mesh` | Archived public | Historical telemetry mesh | **P3 — confirm successor and archive notice** |
| `szl-uds-deployment` | Archived public | Historical deployment packaging | **P3 — make successor explicit in the first screen** |
| `killinchu` | Active public | Operator demonstration | **P0 — audit every operator tab, asset, empty state, and evidence route** |
| `docs-site` | Active public | Documentation front door | **P0 — task-first navigation, current routes, mobile search, and complete reference** |
| `hatun-mcp` | Active public | Developer tool and MCP surface | **P1 — architecture, threat boundary, quickstart, and limits** |
| `uds-bundles` | Archived public | Historical bundles | **P3 — explicit successor and immutable evidence links** |
| `lean-kernel` | Active public | Formal verification bridge | **P2 — clarify the code/HTML surface and reproduction boundary** |
| `developers` | Archived public | Retired developer front door | **P3 — keep redirect and successor unambiguous** |
| `pitch-collateral` | Active private | Investor collateral | **P1 private — align claims with public evidence; do not copy private metrics to public surfaces** |
| `khipu-consensus` | Active public | Consensus library and demo hooks | **P1 — architecture diagram, threat model, and local verification** |
| `warhacker-demo` | Archived public | Historical adversarial demo | **P3 — preserve the eval-arena successor** |
| `szl-lake` | Active public | Evidence corpus bridge | **P1 — admission rules, privacy, validation, gaps, and update policy** |
| `szl-mesh` | Active public | Governed mesh runtime | **P1 — add explicit limits, support, and release history** |
| `szl-fleet-overlay` | Active public | Fleet deployment overlay | **P2 — add limits, support, and changelog** |
| `szl-papers` | Active public | Research corpus | **P1 — research index, reproduction, licenses, and theorem/conjecture labels** |
| `szl-build-env` | Active public | Build environment | **P2 — maturity, architecture, limits, security, and release history** |
| `szl-doctrine` | Active public | Doctrine implementation | **P1 — architecture, limits, support, contribution, and changelog** |
| `anatomy` | Active public | Interactive system map | **P1 — responsive 3D/2D fallback, keyboard path, boundaries, and limitations** |
| `yarqa` | Active public | Interactive specialist Space source | **P1 — clarify status, architecture, limits, security, and license** |
| `szl-router` | Active public | Sovereign routing and public visual routes | **P1 — split runtime docs from demos; add limits and threat boundaries** |
| `khipu-sda-core` | Active public | Core decision/consensus substrate | **P2 — architecture, limits, security, support, and release history** |
| `szl-governed-norm` | Active public | Governed normalization artifact | **P2 — maturity, architecture, and explicit non-goals** |
| `szl-lambda-gate` | Active public | Lambda gate artifact | **P1 — keep advisory score separate from enforcing policy; add limits** |
| `szl-energy-attest` | Active public | Energy attestation | **P2 — maturity, architecture, trust boundary, and limitations** |
| `governed-inference-meter` | Active public | Metering artifact and Space source | **P1 — status, architecture, limitations, and security path** |
| `david-leads` | Active public | Public interactive surface | **P1 — product purpose, quickstart, architecture, limits, and security** |
| `szl-receipt` | Active public | Canonical receipt primitive | **P1 — maturity, architecture, threat model, and non-goals** |
| `immune` | Active public | React/Vite interactive surface | **P1 — full visual and mobile QA plus architecture and limitations** |
| `szl-substrate` | Active public | Shared runtime library | **P1 — architecture, limits, support, contribution, and changelog** |
| `szl-holdings.github.io` | Active public | Company website | **P0 — reconcile with a-11-oy.com, verify every claim and interactive concierge path** |
| `szl-org-health` | Active private | Estate census and health | **P1 private — make it the adoption ledger; do not publish private inventory accidentally** |
| `governed-receipt-spec` | Active public | Receipt specification | **P1 — quickstart, architecture, limits, security, and lifecycle** |
| `szl-guardrail-receipt` | Active public | Guardrail receipt implementation | **P2 — maturity, architecture, limitations, security, and support** |
| `szl-formula-ledger` | Active public | Formula admission ledger | **P1 — verification path, architecture, non-goals, and license** |
| `szl-forge` | Active public | Artifact forge and public lab source | **P1 — tested quickstart, architecture, limits, security, and license** |
| `energy-attest-holo` | Active public | Static holographic Space source | **P1 — consolidate shared shell; add source, privacy, limitations, and local path** |
| `governed-norm-holo` | Active public | Static holographic Space source | **P1 — consolidate shared shell; add verification, privacy, limits, and local path** |
| `lambda-gate-holo` | Active public | Static holographic Space source | **P1 — consolidate shared shell; preserve conjecture/advisory labels** |
| `receipt-chain-live` | Active public | Live receipt-chain visualization | **P1 — add thumbnail, limitations, local reproduction, and immutable source binding** |
| `szl-provctl-live` | Active public | Live provenance-control visualization | **P1 — add source, privacy, limitations, and local reproduction** |
| `szl-kernels-live` | Active public | Live kernel visualization | **P1 — add thumbnail, privacy behavior, and local reproduction** |
| `evidence-typed-formula-governance` | Archived public | Historical governance artifact | **P3 — add license metadata and preserve successor** |
| `fail-closed-governed-ai-services` | Archived public | Historical governance artifact | **P3 — add license metadata and preserve successor** |
| `szl-quant` | Active public | Quantization/evaluation surface | **P1 — architecture, limitations, security, support, and changelog** |
| `szl-telemetry` | Active public | Telemetry artifact | **P2 — maturity, verification, architecture, limits, security, and license** |
| `szl-quant-witness` | Active public | Quant witness artifact | **P2 — topics, quickstart, architecture, limits, security, and license** |
| `a11oy-net` | Active public | Proof registry | **P0 — keep sober and independent; add quickstart, limitations, support, and changelog** |
| `szl-gpu-bridge` | Active public | Protected GPU publication bridge | **P1 — preserve owner-key stop rule; add topics, quickstart, and changelog** |
| `evidence-doctrine` | Active public | Evidence policy package | **P2 — topics, quickstart, architecture, limitations, and license** |
| `gdw-frontier` | Active private | Governed Delta Workspace | **P1 private — keep MODELED labels; add limits, contribution, and license** |
| `szl-estate-os` | Active private | Estate control plane | **P1 private — architecture, limits, contribution, changelog, and license** |
| `sda` | Active public | Specialist decision-assurance Space source | **P1 — source, privacy, limitations, and local reproduction** |
| `szl-kernels` | Active public | Kernel registry and corpus | **P1 — topics, architecture, limits, support, and release history** |

## Hugging Face model register

| Model | Highest-priority card gap |
| --- | --- |
| `SZL-Khipu-1.5B` | Add explicit excluded uses and consolidated limitations |
| `SZL-Forge-1.5B-ReceiptAgent` | Add explicit excluded uses and consolidated limitations |
| `szl-receiptagent-qwen35-0.8b-v2` | Add excluded uses, exact reproduction, and citation |
| `SZL-Khipu-1.5B-GGUF` | Add intended/excluded uses, quantization limits, reproduction, and citation |
| `szl-governed-norm` | Clarify base/non-weight classification, intended/excluded uses, and limitations |
| `szl-kernels` | Clarify base/non-weight classification, intended/excluded uses, and limitations |
| `szl-lambda-gate` | Complete pipeline/base metadata and intended/excluded-use boundaries |
| `governed-inference-meter` | Complete pipeline/base classification, intended/excluded uses, limits, and citation |
| `a11oy-v19-substrate` | Complete pipeline, library, base, intended/excluded use, evaluation, limits, and citation |
| `szl-blocked` | Add base classification, uses, evaluation, limitations, and citation |
| `szl-govsign` | Add base classification, uses, evaluation, limitations, and citation |
| `szl-provctl` | Add base classification, uses, evaluation, limitations, and citation |
| `szl-nemo` | Add base classification, uses, limitations, and citation |
| `szl-invariants` | Add base classification, uses, evaluation, limitations, and citation |
| `szl-ouroboros` | Add base classification, uses, evaluation, limitations, and citation |
| `szl-formulas` | Add base classification, uses, evaluation, limitations, and citation |

No model is promoted here solely by downloads. At observation time 13 of 16
models had zero likes; this is a discoverability signal, not a quality metric.

## Hugging Face dataset register

| Dataset | Highest-priority card gap |
| --- | --- |
| `a11oy-verifiable-corpus` | Privacy/PII, validation, limitations, update policy |
| `alloy-sovereign-eval-runs` | Provenance, privacy/PII, validation, limitations, update policy |
| `canonical-formulas-v1` | Schema/splits, provenance, privacy, validation, limitations, update policy |
| `doctrine-v10-v11` | Schema/splits, provenance, privacy, validation, limitations, update policy |
| `energy-attested-runs` | Privacy/PII, validation, limitations, update policy |
| `governed-agent-bench` | Size metadata, provenance, privacy, validation, limitations, update policy |
| `governed-receipts-bench` | Privacy/PII, validation, and update policy |
| `k-verify-benchmark-v1` | Privacy/PII, validation, limitations, update policy |
| `killinchu-osint-corpus` | Size/task metadata, provenance, validation, limitations, update policy |
| `lean-proofs-v1` | Schema/splits, provenance, privacy, validation, limitations, update policy |
| `lean-theorem-tree` | Schema/splits, privacy, validation, limitations, update policy |
| `ouroboros-arxiv-preprint` | Schema/splits, privacy, validation, limitations, update policy |
| `rag-corpus-v1` | Privacy/PII, validation, limitations, update policy |
| `readiness-runs` | Size/task metadata plus the complete dataset contract |
| `szl-1-doctrine-sft` | Schema/splits, provenance, privacy, validation, limitations, update policy |
| `szl-artifacts` | Schema/splits, privacy, validation, limitations, update policy |
| `szl-lake` | Validation, limitations, and update policy |
| `szl-quant-sft-v1` | Schema/splits, privacy, validation, limitations, update policy |
| `szl-second-brain-inrepo` | Task metadata, schema/splits, privacy, validation, limitations, update policy |
| `SZLHOLDINGS` | Schema/splits, privacy, validation, limitations, update policy |
| `test-results` | Size/task metadata, privacy, validation, limitations, update policy |
| `thesis-corpus-v18` | Privacy/PII, validation, limitations, update policy |
| `thesis-v18-formal-verification` | Schema/splits, privacy, validation, limitations, update policy |
| `uds-bundles-v1` | Schema/splits, privacy, validation, limitations, update policy |
| `uds-governance-receipts` | Privacy/PII, validation, limitations, update policy |
| `uds-spans-receipts` | Privacy/PII, validation, limitations, update policy |
| `why-we-lead` | Schema/splits, privacy, validation, limitations, update policy |

All 27 dataset READMEs were reachable. Twenty-six had zero likes at observation
time; again, that is discoverability, not quality.

## Hugging Face Space register

All Spaces below reported `RUNNING` at observation time. The gaps describe
public contracts, not transport.

| Space | Highest-priority public-contract gap |
| --- | --- |
| `README` | New thumbnail and local reproduction added in this PR; verify exact served revision after merge |
| `a11oy` | Privacy/retention, limitations, and local reproduction |
| `anatomy` | Privacy/retention, limitations, and local reproduction |
| `cosmos` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `david-leads` | Privacy/retention, limitations, and local reproduction |
| `energy-attest-holo` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `energy-attested-runs` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `governed-agent-bench` | Short description, thumbnail, source, privacy, limitations, and local reproduction |
| `governed-norm-holo` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `governed-receipt-verifier` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `guardrail-receipt` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `hatun-mcp` | Thumbnail, privacy/retention, and limitations |
| `holographic` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `immune` | Thumbnail, privacy/retention, and limitations |
| `killinchu` | Privacy/retention and consolidated limitations |
| `lambda-gate-holo` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `llm-router-live` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `receipt-chain-live` | Thumbnail, limitations, and local reproduction |
| `sda` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `szl-blocked-live` | Thumbnail, source, privacy/retention, limitations, and local reproduction |
| `szl-estate-live` | Privacy/retention, limitations, and local reproduction |
| `szl-forge-lab` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `szl-govsign-live` | Thumbnail, source, privacy/retention, limitations, and local reproduction |
| `szl-kernels-live` | Thumbnail, privacy/retention, and local reproduction |
| `szl-model-inference-lab` | Thumbnail and privacy/retention |
| `szl-provctl-live` | Thumbnail, privacy/retention, limitations, and local reproduction |
| `yarqa` | Thumbnail, privacy/retention, and limitations |

## Implemented in this front-door wave

- Replaced the brittle SVG presentation with a 116 KB WebP and a
  failure-tolerant layered composition. The artwork remains an enhancement;
  hierarchy, background, and actions remain legible if it does not paint.
- Added commit-relative GitHub-profile asset routing and a byte-identical Space
  copy published by the exact-source Hugging Face manifest.
- Added Open Graph metadata tied to the same managed asset.
- Organized the truth-rich GitHub organization profile around one mission,
  three audience paths, two product boundaries, current-state sources, and
  explicit evidence language.
- Added a Hugging Face thumbnail and a local reproduction command.
- Updated the publication contract and local verifier to validate WebP format,
  file size, byte equality, metadata limits, truth markers, accessibility
  contracts, references, and manifest inclusion.

## Protected rollout

1. Merge this front-door change normally after independent review and required
   checks.
2. Verify the Hugging Face `deployment.json` reports the merged Git revision and
   the new WebP hash before calling the front door upgraded.
3. Run P0 audits independently for `szl-holdings.github.io`, `a11oy`,
   `a11oy-net`, `docs-site`, and `killinchu`.
4. Apply card-contract templates to the three canonical model families, then
   high-use datasets, then public Spaces.
5. Move long-tail visual shells into shared, versioned brand components only
   after each repository passes its own tests and ownership review.

No force merge, self-approval, protected-branch bypass, evidence promotion, or
estate-wide completion claim is authorized by this audit.
