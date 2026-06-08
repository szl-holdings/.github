# Templates

  Shared templates for every repository in the [SZL Holdings](https://github.com/szl-holdings) organization. New repositories should bootstrap from these to maintain a consistent presentation across the org.

  | Template | Purpose |
  |---|---|
  | [`README.md`](./README.md) | Default repository README structure (placeholders in `{{ }}`) |
  | [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Contribution policy for source-available proprietary repos |
  | [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) | Contributor Covenant 2.1, with SZL contact channel |
  | [`SECURITY.md`](./SECURITY.md) | Vulnerability reporting policy, CVSS triage SLAs |

  ## How to use

  1. Copy the template into a new repository.
  2. Replace every `{{PLACEHOLDER}}` token with the repo-specific value.
  3. Confirm the CI badge URL matches the repository's actual workflow file name (`ci.yml` by default).
  4. Open a PR and tag a maintainer for review.

  The audit history of org-wide template rollouts lives in the platform repo at `docs/audits/github-org.md`.

  ---

  (c) 2024–2026 SZL Holdings, LLC.
  