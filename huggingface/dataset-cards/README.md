# Dataset card source-admission proposal

This directory proposes `szl-holdings/.github` as the canonical **card source**
for two existing public Hugging Face datasets. Authority remains pending
protected owner merge. Provider effects are disabled, and publication has not
been attempted. This proposal does not adopt the dataset run publisher, signing
key, scientific claims, or artifact provenance as verified authority.

| Dataset | Exact observed Hub revision | Only proposed card change |
|---|---|---|
| `SZLHOLDINGS/test-results` | `4d5de7b588460f56fc67437b11617c339a69d8c8` | Select `harness_runs.jsonl` as `default/train`. |
| `SZLHOLDINGS/SZLHOLDINGS` | `7a6cce17710bf47b9e5a64e0b1be43d1276733ef` | Disable the viewer with `viewer: false`. |

Both anonymous viewer split reads failed on a companion promotion-audit JSON
field containing string and boolean values. Selecting the actual run JSONL
keeps the test-results audit out of row inference. Its two rows parsed locally
with `dsse` and `run` columns; no signatures or scientific assertions were
verified. The organization-profile repository declares metadata-only use and
has no row payload, so the proposal disables its viewer without inventing data.

The candidate cards preserve every original byte except the stated front-matter
insertion. Their historical prose is retained source material, not a fresh
measurement by this proposal. Card licensing remains the original declared
Apache-2.0; no new dataset rights, chain of title, consent, privacy review,
training suitability, deployment, or readiness claim is introduced.

The adjacent `admission.json` records immutable before hashes and every
non-README Git blob identity: fourteen files for test-results and six for the
organization profile. Signed runs, evidence, audit, public key, license,
provenance, status, and legacy metadata are outside the proposed write set.
The source directory contains only the two candidate cards and this admission
record; it does not copy or transform those retained provider artifacts.

## Local checks

From a clean checkout of this proposal with Git line-ending translation
disabled (`core.autocrlf=false`). These byte checks use the canonical LF Git
blobs. A Windows checkout that translates them to CRLF must report drift;
that is a failed check, not a reason to rehash the immutable card anchors.
For a fresh clone, set the option at creation rather than rewriting an active
checkout:

```sh
git clone --config core.autocrlf=false https://github.com/szl-holdings/.github.git
```

Select the reviewed proposal revision, then run:

```sh
python -I -B .github/scripts/hf_dataset_card_admission.py
python -I -B .github/scripts/test_hf_dataset_card_admission.py
```

The validator reads only the local manifest and candidate cards. It verifies
exact dataset identities, immutable revisions, strict field types, bounded
regular-file paths, candidate hashes, the allowed insertion, restored baseline
hashes, and complete retained manifests against fixed snapshot anchors.
Adjacent rehashing cannot make a dropped artifact or extra prose pass.
Exit 0 means those local source checks passed. Exit 2 is `BLOCKED` with
`DATASET_CARD_ADMISSION_INVALID`. It makes no network request, reads no
credentials, executes no dataset code, and creates no output files.

The dedicated `hf-dataset-card-admission.yml` workflow runs this suite normally
and with Python assertions disabled, then validates the actual two-card source
proposal. It uses the existing SHA-pinned checkout and Python setup actions,
read-only repository permission, no persisted checkout credentials, no explicit
secrets and a five-minute job limit. It does not upload artifacts or contact
Hugging Face. Hosted execution must be read back at the final proposal head;
local test success alone does not establish it.

The proposed new declaration in `control_plane_effect_policy.json` binds the
exact workflow and two helper byte hashes, the actual analyzer unknown set,
one repository checkout and one Python setup, with zero external writes.
Existing declarations and deny-by-default controls are preserved. This changes
a policy trust root: the full gate returns `REVIEW_REQUIRED` and still requires
protected owner review. A matching per-workflow static analysis is not owner
approval, provider authority, or a proof of arbitrary program behavior.

No live card expectation, credential binding or uploader is changed. The
existing card reconciler supports three scalar
fields and optional body/stamp changes; it does not implement either proposed
viewer operation. Adding these targets to it is outside this source admission.

The path checks assume a cooperative local filesystem. They refuse ordinary
links and reparse points but do not establish a race-safe sandbox. Immutable
Git blob identities establish the declared preservation set; this validator
does not independently fetch the provider or verify DSSE signatures.

## Separate publication gate

Protected owner merge can admit the reviewed card source. A later, separately
reviewed publisher must bind that exact source revision and the exact current
Hub parent, permit only `README.md`, preserve every retained blob, and obtain
provider authorization. It must then read back the new immutable Hub revision,
full non-README manifest, test-results splits and bounded rows, and the disabled
organization-profile viewer. A source merge or local check is not publication,
host registration, scientific qualification, or runtime readiness.
