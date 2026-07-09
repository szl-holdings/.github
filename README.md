> **SZL Holdings** · Doctrine v11 · Λ = Conjecture 1 (advisory, never "green"/theorem) · canonical [a-11-oy.com](https://a-11-oy.com)

<div align="center">

# 🧬 .github

<!-- CII Best Practices badge (founder-action required): register at https://bestpractices.coreinfrastructure.org/ then add the live badge here. -->

**org doctrine**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20434276.svg)](https://doi.org/10.5281/zenodo.20434276) [![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-a6ce39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173) [![Doctrine](https://img.shields.io/badge/Doctrine-v11-3b82f6?style=flat-square)](https://github.com/szl-holdings/.github/blob/main/doctrine/DOCTRINE_V11.md) [![SLSA](https://img.shields.io/badge/SLSA-L1_honest-22c55e?style=flat-square)](https://slsa.dev/spec/v1.0/levels)

[Hugging Face](https://huggingface.co/SZLHOLDINGS) · [Demo](https://szlholdings-readme.static.hf.space/) · [GitHub Org](https://github.com/szl-holdings)

`receipts.in ≡ receipts.out`

</div>

---
<!-- Repo-level README for szl-holdings/.github -->

# `szl-holdings/.github`
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-0B1F3A.svg?style=flat-square&logo=apache&logoColor=00D4FF)](https://www.apache.org/licenses/LICENSE-2.0)
[![GHAS Code Security](https://img.shields.io/badge/GHAS-Code_Security-2DA44E.svg?style=flat-square&logo=github)](https://github.com/szl-holdings/.github/security/code-scanning)
[![Secret Protection](https://img.shields.io/badge/GHAS-Secret_Protection-2DA44E.svg?style=flat-square&logo=github)](https://github.com/szl-holdings/.github/security/secret-scanning)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20434276.svg)](https://doi.org/10.5281/zenodo.20434276)
[![SLSA: enabled](https://img.shields.io/badge/SLSA-enabled-0B1F3A.svg?style=flat-square&logoColor=00D4FF)](https://slsa.dev/spec/v1.0/levels)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-A6CE39.svg?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173)

> Org-wide governance, reusable workflows, templates, and security policy for [SZL Holdings](https://github.com/szl-holdings).


---

## What lives here

| Path | Purpose |
|---|---|
| [`profile/README.md`](./profile/README.md) | Org profile shown at <https://github.com/szl-holdings> |
| [`.github/ISSUE_TEMPLATE/`](./.github/ISSUE_TEMPLATE/) | Default issue templates cascaded to every repo without its own |
| [`.github/PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md) | Default PR template |
| [`.github/workflows/`](./.github/workflows/) | **21 reusable workflows** — see [`WORKFLOWS.md`](./WORKFLOWS.md) |
| [`.github/dependabot.yml`](./.github/dependabot.yml) | Weekly dependency updates for this repo |
| [`.github/CODEOWNERS`](./.github/CODEOWNERS) | Org-default ownership |
| [`templates/`](./templates/) | Copy-paste templates for product repos (`README`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`) |
| [`security.txt`](./security.txt) | RFC 9116 disclosure record (canonical copy; deploy under `/.well-known/security.txt`) |
| [`SECURITY.md`](./SECURITY.md) · [`CONTRIBUTING.md`](./CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) · [`SUPPORT.md`](./SUPPORT.md) | Org-default community docs |
| [`CITATION.cff`](./CITATION.cff) | Citation metadata |
| [`assets/social/`](./assets/social/) | 1280×640 social-preview banners ready for upload via Settings → General → Social preview |

## Reusable workflows

Twenty-one SHA-pinned, harden-runner-protected workflows that every product repo can call:

```yaml
jobs:
  codeql:
    uses: szl-holdings/.github/.github/workflows/reusable-codeql.yml@<commit-sha>
```

**CI & release**

| Workflow | What it does |
|---|---|
| `reusable-node-ci.yml` | Node lint + typecheck + test + build matrix |
| `reusable-docs-ci.yml` | Markdown lint + link-check for docs repos |
| `reusable-release-please.yml` | Conventional-commits release automation |
| `reusable-dco.yml` | Developer Certificate of Origin sign-off check |

**Security & supply chain**

| Workflow | What it does |
|---|---|
| `reusable-codeql.yml` | CodeQL static analysis (JS, TS, Python) |
| `reusable-dependency-review.yml` | Block PRs that introduce vulnerable or non-permissive deps |
| `reusable-trivy.yml` | Trivy filesystem vulnerability scan |
| `reusable-gitleaks.yml` | Gitleaks secret scanning on every PR / push |
| `reusable-secret-scan.yml` | TruffleHog verified committed-secret scan |
| `reusable-sbom.yml` | CycloneDX + SPDX SBOM per release |
| `reusable-scorecard.yml` | OpenSSF Scorecard re-run + badge publish |
| `reusable-workflow-lint.yml` | `actionlint` + `zizmor` lint on all workflows |
| `pin-check-reusable.yml` | Enforce 40-char SHA pinning on third-party Actions |

**Deploy & drift**

| Workflow | What it does |
|---|---|
| `reusable-hf-deploy.yml` | GitHub → Hugging Face Space deployer (Dockerfile-derived file set) |
| `reusable-hf-module-drift-check.yml` | Detect drift between a repo's source and its live HF Space |
| `reusable-anatomy-map-drift.yml` | Guard the shared SZL Anatomy map across its surfaces |
| `reusable-bundle-ref-check.yml` | Verify UDS bundle `repository`/`ref` point at published GHCR tags |
| `reusable-lockfile-registry-check.yml` | Reject lockfiles pinned to sandbox-internal registries |

**Doctrine honesty guards**

| Workflow | What it does |
|---|---|
| `reusable-overclaim-guard.yml` | Doctrine overclaim guard (Λ / Conjecture-1 claims) |
| `reusable-energy-provenance-guard.yml` | Energy-provenance honesty guard (measured-or-`UNAVAILABLE`) |
| `reusable-receipt-shape-guard.yml` | Receipt-shape honesty guard for committed attestation data |

All Actions are SHA-pinned and wrapped with [`step-security/harden-runner`](https://github.com/step-security/harden-runner) using a deny-by-default egress policy. See [`WORKFLOWS.md`](./WORKFLOWS.md) for inputs, secrets, and per-workflow examples.

## Security posture

- Private vulnerability reporting: [security policy](https://github.com/szl-holdings/.github/security/policy)
- Email: `security@szlholdings.com`
- Canonical RFC 9116 record: [`security.txt`](./security.txt)
- Org-wide: branch protection rulesets, signed-commit enforcement, CODEOWNERS, OpenSSF Scorecard
- Live status: 0 open Dependabot · 0 open secret-scanning · 0 open CodeQL

## Tooling for contributors

- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`, `refactor:`, `test:`)
- Squash-merge into `main`; release automation handled by `release-please`
- All PRs run reusable security suite before merge

## License

[Apache-2.0](./LICENSE) for this repo. Product repos under SZL Holdings may use different licenses — see each repo's `LICENSE`.

---

<sub>© 2026 SZL Holdings — [`github.com/szl-holdings`](https://github.com/szl-holdings) · ORCID [`0009-0001-0110-4173`](https://orcid.org/0009-0001-0110-4173)</sub>

---

## Founder guides (baby-simple, copy-paste)

Two step-by-step Word guides for getting the SZL ecosystem running from zero — hardware to buy, tools to install, accounts to create, secrets to set, and how to sign, build, deploy and test the UDS bundles.

| Guide | What it covers | File |
|---|---|---|
| **Environment Setup Guide** | What to buy (3 hardware options), what to install (with links + one command each), accounts, secret keys, and a 10-step first-time setup | [`docs/SZL_ENVIRONMENT_SETUP_GUIDE.docx`](./docs/SZL_ENVIRONMENT_SETUP_GUIDE.docx) |
| **UDS Run Guide** | Sign the 5 unsigned bundles, build Zarf packages, spin up k3d, deploy, verify, cleanup, the 90-second Warhacker demo script, and the founder action queue | [`docs/SZL_UDS_RUN_GUIDE.docx`](./docs/SZL_UDS_RUN_GUIDE.docx) |

Mirrored on Hugging Face: [`SZLHOLDINGS/doctrine-v11`](https://huggingface.co/datasets/SZLHOLDINGS/doctrine-v11) under `founder-guides/`.

---

## Related repositories in the SZL substrate

The SZL substrate repos cross-link reciprocally. Two live products (a11oy + killinchu) sit on one signed substrate.

- [`a11oy`](https://github.com/szl-holdings/a11oy) — command platform; signed-receipt substrate with built-in reasoning, policy & operator capabilities (TypeScript packages, MCP server)
- [`killinchu`](https://github.com/szl-holdings/killinchu) — drones & vessels field tool; counter-UAS + maritime picture; DSSE receipt per engagement
- [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) — Lean 4 + Mathlib proofs of the Λ aggregator (749 decl / 14 axioms / 163 sorries; 8 formulas proven {F1,F4,F7,F11,F12,F18,F19,F22}, Λ = Conjecture 1)
- [`szl-papers`](https://github.com/szl-holdings/szl-papers) — DOI-pinned thesis lineage (v1 → v23)
- [`ouroboros`](https://github.com/szl-holdings/ouroboros) — bounded-recursion runtime
- [`platform`](https://github.com/szl-holdings/platform) — composing monorepo for the substrate runtime
- [`uds-mesh`](https://github.com/szl-holdings/uds-mesh) — UDS span schemas + governance receipts
- [`uds-bundles`](https://github.com/szl-holdings/uds-bundles) · [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) — signed, airgap-deployable mesh bundle
- [`hatun-mcp`](https://github.com/szl-holdings/hatun-mcp) — doctrine-aware Model Context Protocol server
- [`vsp-otel`](https://github.com/szl-holdings/vsp-otel) — OpenTelemetry exporter for Λ-axis spans
- [`developers`](https://github.com/szl-holdings/developers) · [`docs-site`](https://github.com/szl-holdings/docs-site) · [`szl-cookbook`](https://github.com/szl-holdings/szl-cookbook) — build-on-SZL hub, docs & recipes
- [`szl-trust`](https://github.com/szl-holdings/szl-trust) — public proof portal · [`khipu-consensus`](https://github.com/szl-holdings/khipu-consensus) — BFT witnessing

Org page: [github.com/szl-holdings](https://github.com/szl-holdings) · Doctrine v11 · 14 unique axioms · 749 declarations · 163 sorries · DOI [`10.5281/zenodo.20434276`](https://doi.org/10.5281/zenodo.20434276)

## SZL Holdings

![SZL Holdings](./branding/szl-avatar-animated.gif)

*The SZL Holdings animated mark (400×400, 16fps loop). Signed Yachay.*

