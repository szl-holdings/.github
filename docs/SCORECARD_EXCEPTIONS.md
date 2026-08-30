# OpenSSF Scorecard — documented exceptions for `szl-holdings/.github`

This file records the Scorecard findings in this repository that are **not**
defects, with the evidence for that judgement. It exists so the alert list can
be dismissed with a written rationale instead of being silently ignored, and so
a future reviewer can re-derive the decision rather than trusting a dismissal
note.

Reviewed 2026-08-30 against the open code-scanning alert set for this
repository (2 critical, 4 high, 23 medium at time of review).

---

## 1. `DangerousWorkflowID` — `.github/workflows/dco.yml:42` and `:50` (critical ×2)

**What Scorecard flags.** The `Dangerous-Workflow` check reports the
combination of a `pull_request_target` trigger with a checkout of an
attacker-controlled ref (`ref: refs/pull/{N}/head` and
`ref: ${{ github.event.pull_request.base.sha }}`). In the general case that
pattern is a privilege-escalation sink, because `pull_request_target` runs with
the base repository's secrets and write-capable token while the checked-out tree
is contributor-controlled.

**Why it does not apply here.** The workflow was written specifically to defeat
that attack, and Scorecard's pattern match cannot observe the mitigations:

1. **The untrusted tree is never executed.** The PR head is checked out into an
   isolated `candidate/` path and is only ever read as *git history* — every
   `python` invocation in the workflow runs a script from `trusted/`, not from
   `candidate/`. See the `Run strict real-commit DCO self-tests`,
   `Validate exact pull-request commits from trusted base`,
   `Validate exact merge-group range` and `Validate exact protected push range`
   steps: all four execute
   `"$GITHUB_WORKSPACE/trusted/.github/scripts/..."`.

2. **The executed tree is pinned to the workflow's own revision.** The
   `trusted/` checkout uses `ref: ${{ github.workflow_sha }}` — the exact commit
   of the workflow file that GitHub decided to run — and the next step asserts
   the checkout actually landed there:

   ```
   test "$(git -C "$GITHUB_WORKSPACE/trusted" rev-parse HEAD)" = "$EXPECTED_TRUSTED_SHA"
   ```

   A contributor cannot substitute their own checker, because changing the
   checker in their PR changes `candidate/`, not `trusted/`.

3. **No credentials are exposed to any checkout.** Every one of the six
   `actions/checkout` invocations sets `persist-credentials: false`, so no
   `.git/config` in any path carries a usable token.

4. **The token is narrowly scoped.** After the change that accompanies this
   file, the workflow default is `contents: read` + `pull-requests: read`, and
   `statuses: write` is granted only to the two jobs that publish the commit
   status. There is no `contents: write`, no `id-token: write`, and no secret
   other than `github.token` is referenced.

5. **Every action is SHA-pinned** (`actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`).

**Disposition.** Dismiss both alerts as **false positive**, citing this section.
Do not "remediate" by rewriting the workflow: replacing
`pull_request_target` with `pull_request` would remove the ability to publish a
commit status on the PR head, which is the entire purpose of the native DCO
gate, and would weaken a control rather than strengthen it.

**Re-review trigger.** Re-open this decision if any future edit causes the
workflow to (a) execute a path under `candidate/`, (b) drop the
`EXPECTED_TRUSTED_SHA` assertion, (c) set `persist-credentials: true`, or
(d) add `contents: write`, `id-token: write`, or any repository secret.

---

## 2. `TokenPermissionsID` (high ×4)

| Alert | Status |
|---|---|
| `.github/workflows/notification-inbox-scheduler.yml:13` | **Fixed.** `actions: write` moved from the workflow default to the single `dispatch` job that needs it. |
| `.github/workflows/dco.yml:17` | **Fixed.** `statuses: write` moved from the workflow default to the two jobs that publish a status. |
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
