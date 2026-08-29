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

Truth boundary: this packet performs no merge, deployment, Hub mutation, ruleset
edit, DNS change, model training, or production certification. Missing evidence
is UNKNOWN or FAIL, never PASS.

`VERIFIED_PRODUCTION_READY` is allowed only when every blocking G00–G16 gate is
PASS with live enforcement, attested artifacts, ring promotion of the same
digest, tested rollback, and runtime readback.
