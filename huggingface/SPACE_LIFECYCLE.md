# Hugging Face Space lifecycle authority

**Status:** protected source policy. A source merge is not a provider mutation,
and a provider `RUNNING` stage is not end-to-end product proof.

## Historical authenticated policy authority

The policy is bound to the supported-API inventory at protected `.github/main`:

- Workflow run: `33352706604`
- Source: `ab1e0669b4ac5715e4e26fdbb529db70e6affc33`
- Artifact: `hf-official-estate-inventory-33352706604` (`9744148627`)
- Artifact digest:
  `sha256:baac9ac6941a491887d3f28bf6533e2f61000b8722fb2e10dfcdae1b59a2a435`
- Generated: `2026-08-31T03:06:21.407337+00:00`
- Authenticated role: SZLHOLDINGS organization admin
- Counts: 44 models, 37 datasets, 46 Spaces, 14 Kernels, 18 collections,
  and 6 buckets

This fixed policy is based on the August 31 inventory; it is not a current
estate census and does not admit every Space that may exist today. Deleted
targets fail provider reads, and new targets require a separate policy review.
The lifecycle hardening does not refresh the inventory or change visibility.

The immutable inventory enumerated 46 existing Spaces and all 46 were public
and enabled. A later bounded runtime census observed 27 `RUNNING` and 19
`PAUSED`. Every running static Space served its correct
`<subdomain>.static.hf.space/index.html` origin. That is reachability evidence,
not proof of every user flow.

## Policy decision

`.github/data/hf-space-lifecycle-policy.json` fixes the exact 46-Space
inventory as public. New repositories do not match a wildcard and require a new
protected policy revision with content, privacy, license, and source review.

The desired runtime stage is `RUNNING` for every admitted Space. This first
controller reports runtime drift but cannot repair it. At the August 31 census,
the following 19 public Spaces were paused:

- `a11oy-factory`
- `ayllu`
- `counsel`
- `evidence-studio`
- `experiments`
- `governed-agent-bench`
- `holographic`
- `immune-lattice`
- `khipu-lab`
- `lyte-services`
- `nexus`
- `second-brain`
- `szl-command-lab`
- `szl-experiments`
- `szl-khipu`
- `szl-model-inference-lab`
- `szl-real-estate`
- `szl-sovereign-os`
- `terra-assurance`

Restarting those Spaces requires a separate, reviewed runtime controller with
hardware/cost limits, one-target locking, build-log evidence, health probes,
and source/runtime identity checks. A blanket restart is not encoded here.

## What this controller can do

`HF Space Lifecycle Reconcile` is manual, protected-main-only, serialized on
`hf-provider-mutation-szlholdings`, and gated by the GitHub `production`
environment. GitHub concurrency only serializes participating workflows in
this repository; it is not an organization-wide or provider-side lock.
Only the controller step receives the fixed `HF_ORG_TOKEN`
secret. Without logging identity or token material, it verifies user identity
and an unambiguous SZLHOLDINGS admin role, then performs a separate,
non-mutating `HfApi.auth_check(..., repo_type="space", write=True)` against the
one exact selected Space. The reported access-token role is informational and
is never accepted as proof of target write authority.

Its only possible provider write is:

```python
HfApi.update_repo_settings(
    repo_id="one/exact-policy-target",
    repo_type="space",
    private=False,
)
```

An operator must obtain all of the following from a fresh plan for an apply:

1. Exact 64-hex policy digest.
2. Exact observed visibility.
3. Exact observed runtime stage.
4. Exact 40-hex Hub revision.
5. The precise `private-to-public` transition.

The controller checks provider state and protected-main identity, then reads
provider state again immediately before attempting the write. Any change in
Space identity, visibility, revision, runtime stage, or SDK between those two
reads blocks the write. It attempts at most one call, retries authenticated
reads only, and verifies that
visibility changed while revision, runtime stage, and SDK did not. If the call
may have escaped but readback cannot prove the result, the receipt is
`UNKNOWN_AFTER_ATTEMPT` and the job fails. It must not be retried blindly.

These checks are optimistic, not atomic compare-and-set (CAS). The supported
visibility API does not accept an expected revision or other atomic state
precondition, so a competing writer can still act between the final read and
the write. Expected values supplied by an operator are not a signed plan
receipt, and the controller does not check plan age or consume a receipt once.
Matching readback proves the observed state, not sole authorship of the change.
Coordinate all competing writers before applying; this patch does not provide
provider-wide serialization or replay protection.

Malformed dispatch values fail with a receipt and exit code 2 before provider
access. Actions passes its event-file path to the controller; it does not bind
raw inputs into step environments or commands that the runner prints.
Receipts and CLI errors exclude invalid input values. Artifact names
use only the GitHub run ID and attempt, so invalid targets or transitions are
not copied into workflow outputs or artifact names.

The controller cannot:

- make a Space private;
- archive, create, delete, rename, or upload a repository;
- pause, restart, or change hardware;
- change storage, variables, or secrets;
- touch models, datasets, Kernels, collections, buckets, jobs, or organization
  membership.

## Why PR #529 is not the lifecycle path

PR #529's dispatch-only archive workflow is green but unsigned and is not safe
to merge as an operator. It can log an `archived` readback without asserting
that the state became true, can leave some failed reads green, selects the first
token that answers `whoami` without proving SZLHOLDINGS manage authority, has a
two-target partial-write group, and has no exact-policy digest, expected-state
checks, production environment, protected-main recheck, or immutable receipt.

It also implements an older consolidation snapshot that conflicts with the
August 31 authenticated snapshot in which all 46 Spaces were public. It must be closed as
superseded, not dispatched or merged.

## Private datasets and buckets remain gated

Space visibility does not authorize publication of other Hub assets. The
current private set includes operational state, identity-bearing registries,
bundled Git history, training receipts, and unlicensed buckets. Those assets
remain private until per-asset admission proves consent, provenance, license
compatibility, and secret/PII absence. In particular:

- Keep `legacy-archive`, `szl-evidence`, `szl-training-receipts`, and
  `vault-artifacts` private.
- Keep all five private buckets private; the evidence bucket contains databases
  and archives, while the payload bucket requires payload-by-payload review.
- `thesis-formula-index` and `yuyay-v3-axis-labels-v1` are candidates only;
  publication still requires final content/provenance admission.

"Nothing private" is therefore an objective subject to data-safety admission,
not permission to expose operational databases, payloads, identities, or
third-party material.

## Operator sequence

1. Merge this source through signed, protected CI and the merge queue.
2. Confirm no other Hub mutation workflow is active.
3. Approve one `production` environment plan for one exact target.
4. Read its artifact and copy the policy hash and three exact provider fields.
5. If a publication transition is actually planned, launch one apply with those
   exact values.
6. Treat only `VERIFIED` as a completed visibility transition. Preserve
   `UNKNOWN_AFTER_ATTEMPT`, `BLOCKED_PRECONDITION`, and `CONCURRENT_DRIFT` as
   failures requiring investigation.

## Origins and proof boundaries

- `https://a-11-oy.com` is the application origin.
- `https://a11oy.net` is the static proof registry, not an application backend.
- `https://huggingface.co/SZLHOLDINGS` is the artifact and Space provider.
- `https://github.com/szl-holdings` is canonical source and governance.

Exact source equality, deployed revision, served-byte checks, API health, and
critical user journeys are separate release gates. A public card, HTTP 200, or
provider `RUNNING` flag cannot substitute for them.
