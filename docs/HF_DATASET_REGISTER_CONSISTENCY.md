# Offline dataset register consistency

The SPDX checker compares license declarations. That does not compare a
dataset register's eligibility claim with training restrictions, upstream
rights, or missing inventory entries. The separate checker below reports those
metadata contradictions without assigning rights or approving training.

```sh
python .github/scripts/hf_dataset_register_consistency.py \
  --snapshot captured-dataset-audit.json \
  --report new-consistency-report.json
python .github/scripts/test_hf_dataset_register_consistency.py
```

The report path must be new. The input, historical register and other reports
are preserved. No credentials, HTTP requests, repository code, dataset rows,
model weights, clinical content or OSINT content are read or executed. Excluded
assets retain only inventory identity and existing register restrictions.

## Input and evidence boundaries

The input is a bounded `szl.dataset-collection-evidence-audit/v1` metadata
snapshot, or a projection retaining its required fields. It includes:

- The captured public dataset inventory and its count, with full immutable
  40-character revisions. This is captured public coverage, not private or
  present-day completeness.
- `license_register`: the `SZLHOLDINGS/model-bom` revision, source URL and count.
- The model-bom `provenance.contracts.DATASET_LICENSE_REGISTER.csv` envelope and
  captured CSV text. Its exact seven-column header and raw UTF-8 digest must
  agree with the capture.
- For inspected assets, card metadata/excerpts and `card_evidence`; selected
  `status.json` and `provenance.json` contracts use the same evidence envelope.

Every used envelope must identify an untruncated successful capture, matching
server revision, SHA-256 and exact immutable raw URL. The checker compares
these outer capture fields to the dataset revision. Historical `parent_sha`,
`subject.based_on_revision`, upstream revisions and attestation base revisions
legitimately describe earlier states and are preserved.

The raw CSV digest can be recomputed. Normalized governance JSON, extracted
card fields and excerpts inherit the supplied audit's fidelity: retaining a
raw-card digest does not cryptographically authenticate an excerpt. This tool
does not fetch current heads or independently attest the audit. Original
capture evidence must remain available to the reviewer.

## Comparison contract

License declaration and training-disposition comparisons are separate:

- `CONFLICT`: an eligibility claim contradicts explicit restrictions or lacks
  captured support; a register license also conflicts if its declaration
  differs from the captured card declaration.
- `MATCHED_METADATA`: compared declarations match, or a restrictive register
  disposition is retained. This is a metadata result, not legal clearance.
- `UNKNOWN`: coverage, a register row or a supported declaration is missing.
  Unknown is never a positive training result.

Exit codes are `0` for matched metadata, `1` for conflicts and `2` for unknown
or invalid input. A report may contain both conflicts and unknowns; these
counts are not disjoint. `training_allowed` is only `false` for an explicit
restriction or `null` for unresolved metadata. It is never `true`.

`BANNED`, `HELD-COUNSEL`, `BLOCKED`, `RESTRICTED` and `REVIEW-REQUIRED` are retained
as restrictions. The original register label remains visible even when a
separate current status is more restrictive. A published LICENSE or candidate
state `PUBLISHED` is not a training approval. Matching Apache packaging labels
does not clear upstream documents or quoted material.

The supported status/provenance adapters inspect their actual training fields:
the profile schemas use `training_suitability` and
`dataset_artifact_provenance.training_suitability.state`; license-publication
schemas use `claims.training_suitability` and
`evidence_boundaries.training_suitability`. Card `training_eligible: false` and
an explicit all-rights-reserved license name also retain restrictions.
Unstructured excerpts can quote other assets or history, so they supply only
scope diagnostics and never reclassify a dataset. Missing machine-readable
clearance remains unresolved. `production_ready: false` is not a substitute
for a training restriction.

## Source ownership and pending integration

The actual historical dataset-register generator/publisher is **UNKNOWN**.
The card-declared `szl_estate_audit` name is not an identified implementation.
Forge's local model-BOM v2 builder is a different tool and is unchanged. This
checker neither generates nor publishes a replacement register and preserves
historical source-of-record and byte-parity limitations.

The required `Tests` workflow runs this checker’s synthetic offline self-test.
It does not fetch current Hub state, publish a replacement register, establish
dataset rights, or replace review of the underlying captured audit. The source
checker makes no security policy, allowlist, rights, dataset or collection
changes.

The dated audit covered 34 public dataset IDs and a 30-row register. Three
eligible rows had explicit blocked training claims; four current IDs were
absent. Unsubstantiated eligibility and packaging scopes remain unresolved.
The responsible publisher must supply its implementation, exact source/input
revisions and retained output evidence before register publication is repaired.
