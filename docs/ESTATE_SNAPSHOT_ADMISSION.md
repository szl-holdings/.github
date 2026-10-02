# Supplied estate snapshot admission

The network-free tool preserves distinct `license` metadata and `LICENSE`
file-existence fields and checks exact active membership of supplied CSVs.

```sh
python -I scripts/estate_snapshot_admission.py \
  --snapshot /path/to/estate-snapshot.csv \
  --consolidation /path/to/estate-consolidation.csv \
  --dependencies /path/to/dependency-matrix.csv \
  --output /path/to/estate-proposal.json
python -I .github/scripts/test_estate_snapshot_admission.py
```

Exit 0 means `VALIDATED_PROPOSAL`; exit 2 means `REJECTED` with a safe reason.
Existing outputs are never overwritten. UTF-8 CSV inputs have exact headers,
2 MiB/20,000-row/16 KiB-field limits, and strict membership/boolean/tier checks.
Duplicates, malformed rows and unknown dependency owners are rejected.
Empty specs are retained as unpinned. Pickles/programs are never loaded.

SHA-256 binds original bytes; output is deterministic. Specs and metadata skew
are preserved. Spec drift is not a solver conflict. Proposed entries cover
active repositories; archived repositories receive no proposed action.

Scope is `SUPPLIED_PUBLIC_SNAPSHOT`, trust `UNSIGNED_HONEST`; production and
automatic promotion are false. Source/Hub/parent/claims bindings stay null,
demos/license review `NOT_MEASURED`. File existence is not rights clearance.
Current/private inventory, secrets, CI, publication and runtime need separate
evidence. Tiers do not replace `estate/alignment.v1.json` authority.

The contract workflow runs synthetic tests with read-only repository access,
SHA-pinned Actions and exact event checkout. Its effect-policy binding is a
trust-root transition: `REVIEW_REQUIRED` until an exact-head sole-owner
attestation and normal protected-branch checks accept that root, as described
in [Control-Plane Effect Bill of Materials](CONTROL_PLANE_EFFECTS.md).
