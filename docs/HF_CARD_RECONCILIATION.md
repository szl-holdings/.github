# Hugging Face card reconciliation

The `hf-card-reconcile` workflow updates only the fields and optional card bodies
declared in `.github/config/hf_card_expectations.json`. The current targets are
`SZLHOLDINGS/yarqa` and `SZLHOLDINGS/szl-constellation`. Constellation's existing
body is preserved; its historical estate-count claim is outside this lane.

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
allow_body_replace=true
```

Enabling body replacement during a plan previews the declared Yarqa body without
writing anything. Using `false` produces a metadata-only plan and cannot later
authorize a body replacement.

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
plan's `after_sha256`; verify the constellation body remains unchanged apart from
the appended governance stamp. An unchanged card produces a no-op without a new
commit.

`MEASURED_SUCCESS` requires live-main readback for both cards. Authentication or
write failures remain failures even when plan generation or artifact upload
succeeds. This lane does not certify Space runtime behavior or estate readiness.

## Local regression tests

```text
python -I -P .github/scripts/test_hf_card_reconcile.py
```

The same tests run in the regular Tests workflow and before reconciliation.
