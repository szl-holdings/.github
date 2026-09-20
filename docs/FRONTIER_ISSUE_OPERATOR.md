# Public estate observation and exact-head queue admission

This is the existing Frontier issue operator's successor, not another estate
controller. It addresses the legacy operator's public-report and promotion
boundaries under the existing organization execution issue #694.

## What runs automatically

The existing two-hour schedule observes public search-visible pull requests and
issues. The current query is explicitly public-only. A complete search page set
is not a complete organization inventory and is never presented as one. Private
repositories and security alerts remain `NOT_OBSERVED`.

Public output is a positive projection of independently checked repository
visibility, public item numbers, exact source IDs, fixed state codes and counts.
Titles, bodies, review identities, check names, arbitrary URLs and provider error
messages never enter this projection. Visibility is checked again before output.
A visibility change after publication cannot retroactively erase public history.

The scheduled workflow may replace only the body of the existing machine-owned
`.github#585`, using the repository token, after checking its exact number,
author, title, open state and machine marker. It cannot create, reopen or close
an issue, alter labels, replace another issue, or post arbitrary comments.
This narrow reporting write is separate from queue admission.

Classification is advisory. Identical title/body bytes produce a duplicate
candidate pointing to the oldest issue number in the same repository. Case,
whitespace and delimiters are significant. Nothing closes automatically.

The API client refuses noncanonical origins, redirects, ambient proxies,
oversized responses, duplicate JSON keys, incomplete pages and ungranted
mutation operations. The old immediate-merge endpoint is absent. Obsolete merge,
closure and label-replacement methods explicitly refuse calls.

## Solo-maintainer promotion

No second maintainer is manufactured and no approval is impersonated. Existing
provider review requirements remain in force; zero required approvals are valid
when that is the actual protected policy. This adapter supports only an active
public repository with a protected default branch, an enforced squash merge
queue, strict required checks, resolved review threads, deletion/force-push
protection and required main-branch signatures. The adapter additionally requires
an observed verified signature on the exact candidate head. It does not change
ordinary GitHub merge policies or claim unsigned Git Database API commits are
signed. A qualified signing path is an operational prerequisite for this adapter.

`config/estate-pr-authorizations.json` ships with an empty `authorizations` list.
The existing workflow does not edit it. To authorize one candidate, admit a
normal source PR containing one exact record with these fields:

| Field | Meaning |
| --- | --- |
| `id` | Unique lowercase slug, at most 64 characters |
| `repository` | Exact public `szl-holdings/name`; no glob or fork |
| `pr_number` | Positive integer, never a Boolean |
| `head_sha` | The reviewed 40-character candidate commit |
| `base_sha` | The exact protected target default-branch commit |
| `not_before` | UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `expires_at` | Exclusive UTC expiry, at most 24 hours after `not_before` |
| `rules_sha256` | `rules_digest()` of the complete effective branch-rule list |

The top-level schema is `szl.estate-pr-authorizations/v1`. Duplicate IDs or target
PRs, extra fields, mutable references and malformed dates are refused. The rules
fingerprint includes inherited effective rules. A rule collection at the bounded
page limit is unavailable, not an empty or partial success. Classic-only
protection configurations are not promoted by this adapter.

After protected admission, use the existing **Frontier issue operator** manual
workflow on `main`, with `apply=true`, the exact `authorization_id`, and
`acknowledgement=ENQUEUE_EXACT_REVIEWED_HEAD`. Input values are read from the
runner's bounded event file; they are not expanded into shell code, echoed into
step environment variables, or used as secret storage.

The adapter verifies its live first-attempt workflow identity, current protected
controller source, exact policy-file Git blob, grant lifetime, target head/base,
effective-rules digest, public/archive state, hold labels, signature, all observed
checks/statuses, required check integration IDs, reviews and unresolved threads.
It repeats the source/grant and target preflights before one queue request.
Unknown required-check application identity cannot be inferred from a legacy
status's username. Required skipped/neutral checks are not successful tests.

The only PR mutation is GitHub `enqueuePullRequest`, with `expectedHeadOid` and
`jump=false`. No immediate merge, administrator bypass, auto-merge fallback,
force push, review dismissal, rule edit or queue jumping is supported.
A previously observed matching entry is a no-op. The queue receipt binds the
entry's nested pull-request identity, not an assumed merge-group commit SHA.

A pre-send receipt is atomically written before the one possible mutation.
Transport ambiguity causes readback, never an automatic resend. A queue entry
observed at the exact head is not a completed merge, signed-main receipt,
deployment or runtime qualification. If the entry cannot be reconciled, the
result stays `QUEUE_WRITE_OUTCOME_UNKNOWN` and the process exits nonzero.
Even a very fast provider merge requires independent later merge verification.
Re-running an apply attempt is refused; inspect existing state before a fresh
manual dispatch. Source, base or rules movement invalidates the original grant.

## Credentials and process isolation

Dependency installation and all tests run in the credential-free validation job.
The operational job starts on a different hosted runner, checks out the exact
protected source and executes only the standard-library operator. It receives
organization credentials only in that execution step. No test/dependency artifact
is executed by the operational job.

The existing `ORG_REPO_WORKFLOW_TOKEN` / `SZL_GITHUB_TOKEN` aliases remain usable;
organization-admin aliases are no longer automatic defaults. Missing permissions
remain a managed prerequisite. This change neither rotates credentials nor proves
their provider scopes. Prefer an appropriately scoped short-lived GitHub App;
that provisioning remains separate. `SZL_REPORT_TOKEN` is the repository token
and is used only for the fixed public report.

The trusted runner environment and admitted source are the execution boundary;
this is not a new remote-attestation or federated identity implementation. The
API is not atomic. Repository/ruleset restrictions continue to protect the queue
while the operator records only what it actually observed.

## Local qualification

Run from the repository root, without provider credentials:

```bash
python -m pytest -q tests/test_frontier_issue_operator.py tests/test_frontier_issue_operator_safety.py tests/test_frontier_issue_operator_authority.py
python -O -m pytest -q tests/test_frontier_issue_operator.py tests/test_frontier_issue_operator_safety.py tests/test_frontier_issue_operator_authority.py
python -m py_compile .github/scripts/frontier_issue_operator.py
git diff --check
```

Fixtures block networking. They prove parser, effect-boundary, projection,
preflight and readback behavior, not live credential or provider qualification.
The current schema retains its name but uses explicit `PUBLIC_OBSERVATION` /
`EXACT_QUEUE` modes and `OBSERVATION_COMPLETE` / `PARTIAL_FAILURE` dispositions.
Consumers must not equate any of these with an organization-wide all-clear.
Selected failures have fixed diagnostic codes; unknown exceptions are never
reflected into reports. No queue grant is populated merely to turn CI green.

## Admission and incident limits

The earlier public command-center body was corrected separately. Historical
issue revisions and prior artifacts were not erased, and the legacy scheduled
operator remains capable of overwriting that correction until this successor is
normally admitted. Do not claim durable live remediation from a draft PR.

Keep #740 draft until exact-head hosted qualification and review are complete.
The #741 card dependency remains intact. Existing Hugging Face publisher holds,
private-alert coverage, every-file estate auditing, model training, local-device
execution and product-domain deployment remain separate obligations. No provider
release workflow, secret store, model weight, public effector or DNS setting is
changed by this repair. Revert only through a reviewed source PR and retain
historical evidence; do not silently restore the unsafe legacy mutation policy.

Primary API references:

- <https://docs.github.com/en/graphql/reference/pulls#enqueuepullrequestinput>
- <https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch>
- <https://docs.github.com/en/actions/reference/security/secure-use>
