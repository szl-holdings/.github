# SZL Production Readiness System v5

Fail-closed, externally read-only auditor and intended-policy contract.

```bash
python tools/production/szl_production_auditor_v5.py \
  --profile tools/production/szl_production_readiness_profile_v5.json \
  --validate-only

python -m unittest -v tools/production/test_szl_production_auditor_v5.py
```

Full audit from a workspace of checkouts:

```bash
python tools/production/szl_production_auditor_v5.py \
  --profile tools/production/szl_production_readiness_profile_v5.json \
  --workspace "$WORKSPACE" \
  --out production-readiness-output \
  --execute-tools
```

Public-only inventory: this repository is public, so the profile, the tiers CSV
and the snapshot list public repositories only. `validate_profile` rejects any
`repositories` entry whose `visibility` is not `public`, and the live inventory
drift check compares the profile with public repositories only.

Truth boundary: this packet performs no merge, deployment, Hub mutation, ruleset
edit, DNS change, model training, or production certification. Missing evidence
is UNKNOWN or FAIL, never PASS.

`VERIFIED_PRODUCTION_READY` is allowed only when every blocking G00–G16 gate is
PASS with live enforcement, attested artifacts, ring promotion of the same
digest, tested rollback, and runtime readback.
