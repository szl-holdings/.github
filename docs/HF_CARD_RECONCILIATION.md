# Hugging Face card reconciliation

The `hf-card-reconcile` workflow updates only the fields and optional card bodies
declared in `.github/config/hf_card_expectations.json`. The current targets are
`SZLHOLDINGS/yarqa` and `SZLHOLDINGS/szl-constellation`. Both cards were
hand-edited on the Hub by the owner, who chose to keep those edits. No asset
declares a `body_file`, so neither body can be replaced. Constellation's
estate-count prose is owner content outside this lane.

## Governance section

Each card must carry the `stamp_heading` (`## Governance`) and the markers that
`has_stamp()` checks: the Hub repository id, the GitHub source link, the doctrine
labels `MEASURED / REPORTED / UNKNOWN / UNAVAILABLE`, `UNSIGNED_HONEST`, and
`DSSE`. When a marker is missing:

| Card state | Plan result |
| --- | --- |
| No `## Governance` heading | Appends the full stamp block (`body+=governance_stamp`) |
| Exactly one heading | Inserts only the missing marker lines at the end of that section (`governance_stamp~=completed_missing_markers`) |
| More than one heading | Fails closed; the row is `UNAVAILABLE` and nothing is written |
| Section ends in an unclosed code fence or holds a possible setext heading | Fails closed |

A section ends at the next heading of the same or higher level, or at the end of
the file. Headings inside fenced code are ignored. The inserted lines join a
trailing bullet list directly and otherwise follow one blank line. Every other
byte is preserved, including CRLF or LF line endings and a missing final
newline. The duplicate-heading check runs even when every marker is present, so
a duplicated section is never reported as current. Each completion row lists
the inserted lines in `governance_markers_added`.

## Credentials

Plans read the public cards anonymously and never receive a credential or an
OIDC permission. Only apply authenticates. The `auth` dispatch input selects how.

### `auth=oidc` (default): Trusted Publishers, no stored Hub secret

The workflow has three jobs. `governance/hf-card-contract` runs the regression
tests and validates the expectation file. `governance/hf-card-reconcile` makes
the anonymous plan. `governance/hf-card-reconcile-apply` runs only when
`apply=true`. It is the only job with `id-token: write`, alongside
`contents: read` and `actions: read`, which it needs to fetch the reviewed plan.

The apply step runs `hf auth token` once for each selected target, with
`HF_OIDC_RESOURCE` set to that target's resource. The `hf` CLI comes from the
hash-locked `requirements/hf-publisher.lock` (`huggingface-hub==1.19.0`). Each
returned token must be exactly one `hf_…` line. The step masks it and keeps it
in its own process environment as `HF_OIDC_TOKEN_<RESOURCE>`. Minting and
applying happen in the same step, so no token passes through `GITHUB_ENV`, a
step output, a file, or an artifact.

| Space | `HF_OIDC_RESOURCE` | Variable read by the reconciler |
| --- | --- | --- |
| `SZLHOLDINGS/yarqa` | `spaces/SZLHOLDINGS/yarqa` | `HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_YARQA` |
| `SZLHOLDINGS/szl-constellation` | `spaces/SZLHOLDINGS/szl-constellation` | `HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_SZL_CONSTELLATION` |

The resource follows the expectation `kind`: `spaces/<ns>/<name>` for a Space,
`datasets/<ns>/<name>` for a dataset, and `<ns>/<name>` for a model. To see
the list for any selection, run
`python -I -P .github/scripts/hf_card_reconcile.py --list-oidc-targets --only …`.
It makes no network requests and writes no receipt.

Each exchanged token works for one Hub repository and expires after 60
minutes. The reconciler uses each token only for its own target: the write
check, card reads, the commit, and readback. Apply fails closed, with no Hub
request, if any selected target has no token, has a malformed token, or two
targets would share one variable name. When an exchange fails, the step logs
the Hub error with `hf_…` and JWT-shaped values redacted, marks the apply as
failed, and still runs the reconciler so that it records a failure receipt
naming the missing target and resource. Long-lived secrets are not passed to
this mode, and a failed exchange never falls back to one.

#### Configure the Trusted Publishers (owner action, once per Space)

On each Space, open **Settings → Trusted Publishers** and add a publisher
with provider **GitHub Actions** and these claims. The Hub compares claims
exactly (no prefix or regex matching), and managing publishers needs the
**Write** role on the Space.

| Space settings page | `repository` | `branch` | `workflow` |
| --- | --- | --- | --- |
| `https://huggingface.co/spaces/SZLHOLDINGS/yarqa/settings` | `szl-holdings/.github` | `main` | `hf-card-reconcile.yml` |
| `https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation/settings` | `szl-holdings/.github` | `main` | `hf-card-reconcile.yml` |

Leave every other claim unset. A publisher that does not match fails the
exchange with an `invalid_grant` error and a Hub request ID.

#### Identity preflight in OIDC mode

An exchanged token acts as a synthetic `[OIDC]` Hub user, so the owner and
organization-role check used in token mode does not apply. Before any read or
write, apply calls `GET /api/<kind>/<ns>/<name>/auth-check/write` with each
target's token (`/api/spaces/…` for these two Spaces). This is the endpoint behind `huggingface_hub`'s documented
`auth_check(..., write=True)`. Any result other than HTTP 200 fails the whole
apply before any card is read or written. The `/api/whoami-v2` response for
the same token is recorded as `REPORTED` context: HTTP status, `name`, `type`,
and token role. It never gates a write. How the Hub answers whoami-v2 for an
OIDC token is `UNKNOWN` until the first apply receipt records it.

The receipt's `auth` block holds `mode: "oidc"` and each target's `repo_id` and
`resource`. It never holds a token value, and `token_recorded` is always
`false`.

### `auth=token`: long-lived secret, unchanged behaviour

`auth=token` selects the first nonempty repository secret, in this order:
`HF_CARD_WRITE_TOKEN`, `HF_ORG_TOKEN`, `HF_ORG_TOKEN1`, `HF_TOKEN`, then
`HF_WRITE_TOKEN`. That one token is used for every target. An invalid credential
is a failure, not permission to try broader credentials. The whoami-v2
preflight still requires owner `betterwithage` with an eligible `SZLHOLDINGS`
role. If you use this mode, prefer a fine-grained `betterwithage` token limited
to these two Spaces, stored as `HF_CARD_WRITE_TOKEN`. Do not narrow or replace a
shared organization credential for this lane. The receipt records
`mode: "token"` and the name of the selected secret, never its value. The
secrets reach the apply step only when `auth=token`.

In either mode, a passing preflight does not prove the write happened. Inspect
the apply status and independently read back each live README.

## Plan, review, and apply

Dispatch the plan from `main`. It is anonymous, and the `auth` input has no
effect on it:

```text
gh workflow run hf-card-reconcile.yml --repo szl-holdings/.github --ref main \
  -f only=SZLHOLDINGS/yarqa,SZLHOLDINGS/szl-constellation \
  -f apply=false -f allow_body_replace=false
```

No asset declares a `body_file`, so `allow_body_replace=true` would change
nothing. Keep it `false`: the plan receipt then records
`body_replace_allowed: false`, and an apply bound to that plan cannot replace a
body. Front-matter reconciliation and governance marker completion do not depend
on this setting.

Find the plan run and download its receipt:

```text
gh run list --repo szl-holdings/.github --workflow hf-card-reconcile.yml \
  --event workflow_dispatch --limit 1 \
  --json databaseId,attempt,headSha,status,conclusion,url
gh run download RUN_ID --repo szl-holdings/.github \
  --name hf-card-reconcile-RUN_ID-ATTEMPT
```

Inspect `hf-card-reconcile.json`. Require both rows to be `MEASURED`. Review the
retained `new_text`, changes, before/after SHA256, Hub revisions, source
revision, and configuration/body hashes. The receipt remains `UNSIGNED_HONEST`.

For an accepted plan, and once both Trusted Publishers above exist, dispatch
the apply with the same targets and body setting:

```text
gh workflow run hf-card-reconcile.yml --repo szl-holdings/.github --ref main \
  -f only=SZLHOLDINGS/yarqa,SZLHOLDINGS/szl-constellation \
  -f apply=true -f allow_body_replace=false \
  -f plan_run_id=RUN_ID -f plan_run_attempt=ATTEMPT -f auth=oidc
```

`plan_run_attempt` defaults to `1`. The apply's `auth` does not need to match
anything in the plan: the plan binding covers source, configuration, targets,
and card bytes, not credentials.

The apply job requires a successful manual plan from this workflow on the exact
current `main` revision. It downloads that run attempt's artifact; rerunning the
plan cannot silently select a newer attempt. The reconciler checks that source,
configuration, selected assets, Hub revisions, and proposed card bytes still
match before any write. If anything has changed, review a fresh plan instead of
overriding the check.

The Hub commit includes `parentCommit` to reject concurrent changes. Mutating
requests are not automatically retried. Only an explicit direct-write HTTP 403
allows one attempt to open a Hub pull request. HTTP 401 is terminal.

Inspect any returned Hub PR and its exact diff before merging it. A created PR
is not live-main publication. Check existing open Hub PRs before retrying an
ambiguous or interrupted write to avoid duplicates.

## Completion evidence

Retain the plan/apply artifacts, exact GitHub source SHA, run URLs, Hub commit or
PR URLs, and anonymous live card readbacks. Compare the readback bytes with each
plan's `after_sha256`; verify each body remains unchanged apart from the
inserted governance marker lines and that each card still has exactly one
`## Governance` heading. An unchanged card produces a no-op without a new
commit. With `auth=oidc`, the Hub attributes the commit to a synthetic `[OIDC]`
user rather than `betterwithage`; keep the apply receipt's `auth` and
`identity` blocks with the evidence.

`MEASURED_SUCCESS` requires live-main readback for both cards. Authentication or
write failures remain failures even when plan generation or artifact upload
succeeds. This lane does not certify Space runtime behavior or estate readiness.

## Local regression tests

```text
python -I -P .github/scripts/test_hf_card_reconcile.py
```

The same tests run in the regular Tests workflow and in the
`governance/hf-card-contract` job, which both the plan and apply jobs need.
