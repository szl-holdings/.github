# Private card publishing

The public push-triggered workflow keeps its existing public target set.
Private targets belong in a separate configuration stored outside this
repository, on a trusted POSIX runner. This change adds no private target,
model metadata, artifact details, or private card content to the repository.

The separate configuration uses the existing expectation schema. Mark each
private asset with the boolean field `private: true`. Omit license overrides
unless separately reviewed. Store any replacement body alongside the private
configuration. An unavailable target still fails the selected plan.

## Authenticated plan

Supply `HF_CARD_READ_TOKEN` through the private runner's credential mechanism.
Scope it to the intended target. Do not place credentials in commands or files
that will be published. Set `private_config`, `private_bodies`, and
`private_receipts` to the reviewed private paths before running:

```bash
set -euo pipefail
umask 077
export GITHUB_SHA="$(git rev-parse HEAD)"
python3 -I -P .github/scripts/hf_card_reconcile.py \
  --config "$private_config" --bodies-dir "$private_bodies" \
  --authenticated-plan --allow-body-replace \
  --out-json "$private_receipts/plan.json"
```

Review the exact before/after text, revision, and hashes locally. Receipts
include private content and must stay private. Files use mode 0600; their
parent directory must be private too. Authenticated plans and private-target
applies refuse execution in GitHub Actions to prevent public artifact uploads.
Default plans ignore inherited credentials and continue to read anonymously.

## Apply

After reviewing the exact plan, provision `HF_CARD_WRITE_TOKEN` scoped to the
target. Run from the same reviewed source revision:

```bash
python3 -I -P .github/scripts/hf_card_reconcile.py \
  --config "$private_config" --bodies-dir "$private_bodies" \
  --apply --auth token --allow-body-replace \
  --expected-plan "$private_receipts/plan.json" \
  --out-json "$private_receipts/apply.json"
```

The existing owner preflight, source/config/body hashes, target set, Hub
parent revision, and exact-byte readback remain mandatory. Read credentials
are never substituted for write credentials. Changed visibility fails closed;
the tool does not change visibility. A new main commit requires verified main
readback. A returned Hub pull request remains pending main readback. Inspect
an ambiguous write result before retrying. Card updates do not deploy models.
