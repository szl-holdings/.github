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

## Credential

Prefer a fine-grained `betterwithage` token with content read/write permission
limited to these two Space repositories, stored as the repository Actions secret
`HF_CARD_WRITE_TOKEN`. The existing fallback order remains `HF_ORG_TOKEN`,
`HF_ORG_TOKEN1`, `HF_TOKEN`, then `HF_WRITE_TOKEN`. The first nonempty secret wins;
an invalid credential is a failure, not permission to try broader credentials.
Do not narrow or replace a shared organization credential for this lane.

Plans read the public cards anonymously. Apply validates the credential identity
before attempting any write. A successful identity check is not write proof:
inspect the apply status and independently read back each live README.

## Plan, review, and apply

Dispatch from `main` using these inputs:

```text
only=SZLHOLDINGS/yarqa,SZLHOLDINGS/szl-constellation
apply=false
allow_body_replace=false
```

No asset declares a `body_file`, so `allow_body_replace=true` would change
nothing. Keep it `false`: the plan receipt then records
`body_replace_allowed: false`, and an apply bound to that plan cannot replace a
body. Front-matter reconciliation and governance marker completion do not depend
on this setting.

Download `hf-card-reconcile-RUN_ID-ATTEMPT`, and inspect
`hf-card-reconcile.json`. Require both rows to be `MEASURED`. Review the retained
`new_text`, changes, before/after SHA256, Hub revisions, source revision, and
configuration/body hashes. The receipt remains `UNSIGNED_HONEST`.

For an accepted plan, dispatch again with the same targets and body setting,
`apply=true`, `plan_run_id=RUN_ID`, and `plan_run_attempt=ATTEMPT` (default `1`).
The workflow requires a successful manual
plan from this workflow on the exact current `main` revision. It downloads that
run attempt's artifact; rerunning the plan cannot silently select a newer attempt.
The reconciler checks that source, configuration, selected assets,
Hub revisions, and proposed card bytes still match before any write. If anything
has changed, review a fresh plan instead of overriding the check.

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
commit.

`MEASURED_SUCCESS` requires live-main readback for both cards. Authentication or
write failures remain failures even when plan generation or artifact upload
succeeds. This lane does not certify Space runtime behavior or estate readiness.

## Local regression tests

```text
python -I -P .github/scripts/test_hf_card_reconcile.py
```

The same tests run in the regular Tests workflow and before reconciliation.
