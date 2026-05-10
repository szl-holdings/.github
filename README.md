<!-- Repo-level README for szl-holdings/.github -->

# `szl-holdings/.github`

> Org-wide governance, reusable workflows, templates, and security policy for [SZL Holdings](https://github.com/szl-holdings).

<p>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/szl-holdings/.github"><img alt="OpenSSF Scorecard" src="https://api.securityscorecards.dev/projects/github.com/szl-holdings/.github/badge"></a>
  <a href="./LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-01696F?style=flat-square"></a>
  <a href="./SECURITY.md"><img alt="Security policy" src="https://img.shields.io/badge/security-policy-1B474D?style=flat-square&logo=github&logoColor=white"></a>
  <a href="./CODE_OF_CONDUCT.md"><img alt="Contributor Covenant 2.1" src="https://img.shields.io/badge/conduct-Contributor%20Covenant%202.1-C8B26A?style=flat-square"></a>
  <img alt="Workflows SHA-pinned" src="https://img.shields.io/badge/workflows-SHA--pinned-2DA44E?style=flat-square">
</p>

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

<sub>© 2026 SZL Holdings — [`szlholdings.com`](https://szlholdings.com) · ORCID [`0009-0001-0110-4173`](https://orcid.org/0009-0001-0110-4173)</sub>
