# OpenSSF Scorecard — documented exceptions for `szl-holdings/.github`

This file records the Scorecard findings in this repository that are **not**
defects, with the evidence for that judgement. It exists so the alert list can
be dismissed with a written rationale instead of being silently ignored, and so
a future reviewer can re-derive the decision rather than trusting a dismissal
note.

Reviewed 2026-08-30 against the open code-scanning alert set for this
repository (2 critical, 4 high, 23 medium at time of review).

---

## 1. `DangerousWorkflowID` — native provenance workflow (resolved)

The earlier implementation combined `pull_request_target` with candidate and
trusted checkouts. Even though it attempted to keep the proposed tree as data,
that shape was unnecessarily difficult to audit and produced two critical
Scorecard findings.

The native workflow has been replaced. It now processes only GitHub event and
REST API metadata: there is no checkout, local action, candidate script, cache,
artifact, or repository secret. The protected pull-request jobs validate the
exact workflow source, live PR/base/head tuple, unique governed head, base
ancestry, and absence of proposed workflow edits before publishing the legacy
compatibility context. The merge-group job has read-only Contents permission;
only the protected pull-request and reconciliation jobs can write a status.

**Disposition.** The old false-positive exception is retired. Re-scan after the
replacement reaches the default branch and close the alerts as fixed when the
provider observes the new file.

**Residual provider limitation.** Ruleset `19755620` still identifies a status
by the historical context name and GitHub Actions App, not by one workflow
file. A distinct candidate workflow could otherwise imitate that name. The
protected pull-request path therefore rejects any `.github/workflows/**` edit;
workflow migrations require an explicit owner review and bypass of only the
obsolete compatibility context. Requiring a specific workflow or a distinct
App-owned status remains the complete fix once ruleset settings are editable.

**Re-review trigger.** Re-open this decision if the workflow gains any `uses:`,
checkout, candidate execution, repository secret, `contents: write`,
`id-token: write`, or status-write permission on the merge-group job.

---

## 2. `TokenPermissionsID` (high ×4)

| Alert | Status |
|---|---|
| `.github/workflows/notification-inbox-scheduler.yml:13` | **Fixed.** `actions: write` moved from the workflow default to the single `dispatch` job that needs it. |
| `.github/workflows/dco.yml` | **Fixed.** The workflow default and merge-group compatibility job use `permissions: {}`; `statuses: write` exists only on the protected PR and reconciliation jobs that publish the legacy context. |
| `.github/workflows/attest-and-approve.yml:22` | **Accepted.** The workflow default is already the minimum (`contents: read`). The remaining write scopes (`contents: write`, `id-token: write`, `pull-requests: write`) are declared at job level on the single `attest` job and are each load-bearing: `id-token: write` for OIDC-based attestation, `contents: write` to record the attestation, `pull-requests: write` to approve. Scorecard reports the top-level block's line number even when the write scope is job-scoped, so this alert cannot be cleared without removing the workflow's function. |
| `.github/workflows/hf-kernel-card-publish-v2.yml:28` | **Accepted.** Same shape: workflow default is `contents: read`; the `publish` job needs `actions: write` (to re-dispatch on transient Hub failure) and `issues: write` (to file the publish receipt). |

The general rule this repository follows, and which the two fixes above bring
these files into line with:

> The workflow-level `permissions:` block is read-only. Any write scope is
> declared on the individual job that exercises it, with a comment naming the
> step that requires it.

---

## Sources

- OpenSSF Scorecard checks reference, `Dangerous-Workflow` and `Token-Permissions`: <https://github.com/ossf/scorecard/blob/main/docs/checks.md>
- GitHub Actions permissions model and job-level scoping: <https://docs.github.com/actions/using-jobs/assigning-permissions-to-jobs>
- `pull_request_target` hazard and the recommended isolation pattern: <https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/>
