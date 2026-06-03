<div align="center">

# 🧬 .github

<!-- CII-BEST-PRACTICES-BADGE: PENDING — replace 'PENDING' with the project id once founder registers this repo at https://bestpractices.coreinfrastructure.org/ -->
[![CII Best Practices](https://bestpractices.coreinfrastructure.org/projects/PENDING/badge)](https://bestpractices.coreinfrastructure.org/)

**org doctrine**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20434276.svg)](https://doi.org/10.5281/zenodo.20434276) [![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-a6ce39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173) [![Doctrine](https://img.shields.io/badge/Doctrine-v11-3b82f6?style=flat-square)](https://github.com/szl-holdings/.github/blob/main/DOCTRINE_V11.md) [![SLSA](https://img.shields.io/badge/SLSA-L1_honest-22c55e?style=flat-square)](https://slsa.dev/spec/v1.0/levels)

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
| [`.github/workflows/`](./.github/workflows/) | **11 reusable workflows** — see [`WORKFLOWS.md`](./WORKFLOWS.md) |
| [`.github/dependabot.yml`](./.github/dependabot.yml) | Weekly dependency updates for this repo |
| [`.github/CODEOWNERS`](./.github/CODEOWNERS) | Org-default ownership |
| [`templates/`](./templates/) | Copy-paste templates for product repos (`README`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`) |
| [`security.txt`](./security.txt) | RFC 9116 disclosure record (canonical copy; deploy under `/.well-known/security.txt`) |
| [`SECURITY.md`](./SECURITY.md) · [`CONTRIBUTING.md`](./CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) · [`SUPPORT.md`](./SUPPORT.md) | Org-default community docs |
| [`CITATION.cff`](./CITATION.cff) | Citation metadata |
| [`assets/social/`](./assets/social/) | 1280×640 social-preview banners ready for upload via Settings → General → Social preview |

## Reusable workflows

Eleven SHA-pinned, harden-runner-protected workflows that every product repo can call:

```yaml
jobs:
  codeql:
    uses: szl-holdings/.github/.github/workflows/reusable-codeql.yml@<commit-sha>
```

| Workflow | What it does |
|---|---|
| `reusable-codeql.yml` | CodeQL static analysis (JS, TS, Python) |
| `reusable-dependency-review.yml` | Block PRs that introduce vulnerable deps |
| `reusable-trivy.yml` | Filesystem + container vuln scanning |
| `reusable-gitleaks.yml` | Secret scanning on every PR / push |
| `reusable-secret-scan.yml` | TruffleHog-style verified-secret scan |
| `reusable-sbom.yml` | CycloneDX SBOM per release |
| `reusable-scorecard.yml` | OpenSSF Scorecard re-run + badge publish |
| `reusable-workflow-lint.yml` | `actionlint` + zizmor lint on all workflows |
| `reusable-release-please.yml` | Conventional-commits release automation |
| `reusable-node-ci.yml` | Node lint + typecheck + test matrix |
| `reusable-docs-ci.yml` | Markdown lint + link-check for docs repos |

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

The 13 substrate repos cross-link reciprocally. This footer is maintained by GH Admin #1 (org-wide).

- [`a11oy`](https://github.com/szl-holdings/a11oy) — policy + receipt substrate (TypeScript packages, MCP server)
- [`amaru`](https://github.com/szl-holdings/amaru) — cortex memory + reasoner (FastAPI, 7-chakra runtime, DSSE receipts)
- [`rosie`](https://github.com/szl-holdings/rosie) — operator console + receipt stream UI
- [`sentra`](https://github.com/szl-holdings/sentra) — immune / red-team (egress inspector + tripwires, Wire B live)
- [`uds-mesh`](https://github.com/szl-holdings/uds-mesh) — UDS span schemas + governance receipts
- [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) — Lean 4 + Mathlib proofs of the Λ aggregator (749 decl / 14 axioms / 163 sorries)
- [`ouroboros`](https://github.com/szl-holdings/ouroboros) — bounded-recursion runtime
- [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) — DOI-pinned thesis substrate (v3 → v18)
- [`platform`](https://github.com/szl-holdings/platform) — composing monorepo for the substrate runtime
- [`szl-brand`](https://github.com/szl-holdings/szl-brand) — anatomy + visual doctrine (PDFs hosted in-repo)
- [`szl-cookbook`](https://github.com/szl-holdings/szl-cookbook) — governed-AI recipes
- [`agi-forecast`](https://github.com/szl-holdings/agi-forecast) — PAC-Bayes + Bekenstein governance-trajectory forecasts
- [`vsp-otel`](https://github.com/szl-holdings/vsp-otel) — OpenTelemetry exporter for Λ-axis spans

Org page: [github.com/szl-holdings](https://github.com/szl-holdings) · Doctrine v11 · 14 unique axioms · 749 declarations · 163 sorries · DOI [`10.5281/zenodo.20434276`](https://doi.org/10.5281/zenodo.20434276)

## SZL Holdings

![SZL Holdings](./branding/szl-avatar-animated.gif)

*Amaru — the Inca avatar of SZL Holdings. Animated mark (400×400, 16fps loop). Signed Yachay.*
