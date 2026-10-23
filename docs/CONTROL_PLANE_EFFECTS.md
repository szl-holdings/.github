# Control-Plane Effect Bill of Materials

The Control-Plane Effect Bill of Materials (CP-eBOM) records the statically
observable effects of a changed GitHub Actions workflow. It answers a narrow
but important review question: which declared control-plane resources could
this source attempt to read or change?

The gate is deterministic and network-free. It reads exact Git objects for a
base commit and a head commit, applies a strict effect policy, and emits a
canonical JSON receipt. The analyzer does not contact GitHub, Hugging Face, a
cloud provider, or any product runtime. It does not request or record secret
values.

The policy covers only its explicitly declared workflows; other estate
workflows have not all been migrated. A change to an undeclared workflow or an
unbound executable/configuration path is denied by this gate until its effect
contract is examined and added. The workflow is not a required branch
protection context merely because this file is present.

## What the gate evaluates

For each selected workflow, the gate binds observed behavior to an explicit
declaration:

- event triggers and GitHub token permissions;
- referenced credential names, never credential values;
- exact SHA-pinned actions with reviewed effect classifications;
- local executable dependencies covered by exact content digests;
- known external mutation sinks and exact resource keys;
- per-effect call budgets and a total external-write budget;
- concurrency, protected-ref, exact-revision, expected-before, and readback
  controls; and
- effects recognized in the head, with a bounded comparison to the merge
  base. The current delta parser does not prove the complete effect set of
  arbitrary shell, Python, or JavaScript programs.

Unknown actions, dynamic execution, unresolved local dependencies, wildcard
resources, undeclared effects, digest mismatches, expired intent, and resource
conflicts are recorded as unknown or denied. A missing declaration is never
interpreted as read-only. Textual control indicators are review hints; they
do not prove a provider compare-and-set, readback, or protected-ref behavior.

Only a small exact shell no-op grammar can contribute to an automatic
`ALLOW`. Other shell commands and all analyzed Python or JavaScript source
produce an unknown/review result even when the analyzer recognizes a likely
mutation sink. Those sink recognizers enrich the inventory; they do not prove
the absence of other effects. Exact SHA-pinned reviewed Actions have explicit
effect classifications.

Workflow structure is decoded with the admitted PyYAML 6.0.3 parser, not
matched as text. String-preserving scalar decoding keeps the GitHub `on` key
intact and recognizes quoted, spaced, escaped, and flow-style keys and values.
Duplicate keys, aliases, anchors, explicit tags, directives, multiple
documents, and inputs exceeding the size, event-count, or nesting limits are
denied. A missing or different parser version also fails closed. The enforcing
workflow installs one exact Python 3.12 Linux wheel URL with its SHA-256;
local execution requires the same parser version.
The enforcing workflow uses Python's isolated mode for installation,
self-tests, analysis, and receipt handling so repository-local modules or
Python environment overrides cannot shadow the admitted parser or libraries.

Permissions are read from workflow and job mappings, including `write-all`.
Unresolved inherited token authority is denied. Containers, services, matrix
fan-out, unsupported runners or shells, and dynamic checkout targets are not
modeled execution boundaries and cannot be waived with an exact-byte review.
A literal checkout repository override binds the actual repository resource.
Credential expressions are inspected after YAML decoding; receipts record
only referenced credential names, including fallback and bracket forms.

Known action input keys must be ASCII identifiers and are normalized with
the runner's case-insensitive semantics; normalization collisions are denied.
Explicit authentication inputs must resolve wholly to named secret or
`GITHUB_TOKEN` references; literal, dynamic, or unbound fallback authority
is denied without recording its value. Artifact names bind the
actual literal destination. Only the enforcing workflow's exact
`control-plane-effect-${{ github.run_id }}` template maps to its declared
run-scoped artifact namespace. The alignment workflow alone also admits its two
exact `estate-alignment-{local,live}-${{ github.run_id }}-${{ github.run_attempt }}`
templates, each bound to its distinct declared artifact namespace. Those fixed
platform identifiers preserve separate retry receipts without overwrite/delete
authority; arbitrary expressions and use from other workflow paths remain denied.
Other dynamic names, non-archived uploads,
overwriting/deleting artifacts, Python cache writes, and checkout options
that fetch unmodeled resources are denied. A checkout cannot substitute
foreign repository or revision bytes for pinned local dependencies. Unknown
external actions, unresolved local actions or dependencies, and reusable
workflows cannot be accepted by reviewing only the caller's bytes.
Executable control hints come from run blocks, not workflow names or labels.

Code-scanning uploads have one narrow shape. `actions/download-artifact` at
exactly `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` (v8.0.1) is a read of an
artifact uploaded by the same run, accepted only with a literal `name` and no
other input; a token, run id, repository, pattern, id list, or path is denied.
`github/codeql-action/upload-sarif` at exactly
`2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2` (v4.38.2) is an external write to
that repository's code-scanning category, accepted only with a literal
traversal-free `.sarif` file and a literal `category`; a token, ref, sha,
checkout path, matrix, or wait input is denied. Any other `:write` grant still
produces `GITHUB_WRITE_PERMISSION_PRESENT`. The only exemption is
`security-events: write` when it is the workflow's single write grant and the
job holding it has exactly `contents: read` plus `security-events: write`,
exactly two steps (that download, then that upload), a `needs` job that
uploads the same literal artifact name with a reviewed upload-artifact pin,
and no token or secret reference in the job or the workflow `env`. The bound
receipt then lists the grant under `scoped_write_permissions`. Container and
Dockerfile actions, such as `rhysd/actionlint`, stay unclassified because a
commit SHA does not pin the image bytes they build and run.

Owner-reviewed unknowns remain available only for eligible bounded source
constructs. Acceptance requires exact file digests and the complete observed
unknown set; the receipt records whether that review was applied. This cannot
waive invalid YAML, unresolved authority or execution boundaries, or fan-out.

## Bounded canonical A11oy publisher

The new version of `reusable-hf-deploy.yml` has one additional admitted
invocation graph, not generic reusable-workflow or dynamic-checkout support.
Before caller source or HF credentials are used, an isolated Python validator
at an exact checker-pinned digest requires the canonical A11oy repository,
main event SHA, exact target, runtime identity and default-branch-tip guard.
Its publication interface is intentionally incompatible with arbitrary callers;
consumers at prior immutable revisions are unchanged. Both the validator and
the complete shell/Python/lock closure remain part of the exact source review.

The paired `job.workflow_repository` / `job.workflow_sha` checkout is accepted
only at `tools/` in this graph, with depth 1 and credentials disabled. Only the
four explicitly named executable/lock paths map from that workspace to their
immutable `.github` source blobs. The sole caller checkout is literal
`szl-holdings/a11oy` at `github.sha` under `caller/`. Caller bytes are publisher
data; the tools interpreter uses `-I -P` and literal tools executable paths.
Any other checkout resource, path, ref, credential or execution boundary still
denies. Hash-locked `requirements/hf-publisher.lock` is included explicitly.

The exact local `reusable-hf-deploy-source-witness.yml` invocation is separately
modeled. It supplies literal boolean `contract-only: true`, the declared
permission interface and one named token mapping. Its exact callee and validator
are checked too. Only the two read-only tools checkouts, pure invocation check
and pinned source-comparison block are reachable; every mutating job is guarded
off. Caller bytes alone cannot approve a different callee or enable publication.

The signer is an isolated job with exactly a same-run artifact download and
`actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8`.
That wrapper's reviewed transitive is
`actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d`. The sole admitted input
is literal `subject-path: hf-runtime-binding.json`. The classified sites are
GitHub OIDC issuance, public Sigstore Fulcio certificate issuance, Rekor append,
GitHub attestation upload, and a local bundle write. Registry push and artifact
metadata storage are excluded because their enabling inputs are not admitted.
Only this exact job may hold `id-token: write` and `attestations: write`; extra
steps, env, credentials, subjects, selectors or write grants deny. The local
contract-only caller delegates that interface but reaches no signing job.

Runtime binding and publication-input artifact names include both `run_id` and
`run_attempt`; downloads admit no alternate run, repository, token or path.
Both publication input files must exist before upload and after download. Public
smoke coverage uses two explicit Python 3.11/3.12 jobs and distinct attempt-scoped
artifacts; arbitrary matrix fan-out remains unsupported. Normal and optimized
Python regressions are retained in each job.

The declaration includes optional pruning as an external deletion effect on
the fixed A11oy COPY-derived file set, preserving protected-file exclusions;
it does not grant repository deletion. Budgets count statically observed
invocation/source sites, not HTTP packets, commit batches, retries or proof of
runtime call counts. SDK-shaped sites in offline regression fixtures retain
explicit credentialless test-harness resources rather than production targets.
Publication, source-variable update, optional restart, telemetry, artifacts and
attestation effects are all separately visible. This source model establishes
neither live authorization nor deployment, runtime readiness, complete image
identity, hardware provenance, or independent witness authority.

Upstream action sources reviewed for these classifications:
[wrapper action.yml](https://github.com/actions/attest-build-provenance/blob/4d101475d8b20a2381f78447822ac1eab6504dd8/action.yml),
[attest main.ts](https://github.com/actions/attest/blob/508db95dd578ae2727ebd6217d5ba78e4fbda05d/src/main.ts),
[attest.ts](https://github.com/actions/attest/blob/508db95dd578ae2727ebd6217d5ba78e4fbda05d/src/attest.ts).

## Bounded seismic publisher

`reusable-hf-deploy-seismic.yml` is a separate workflow for the exact
`szl-holdings/szl-seismic-review` caller and
`SZLHOLDINGS/szl-seismic-review` Space. Its invocation job checks the
immutable called-workflow revision, main-branch event SHA, target, Dockerfile,
source-revision inputs, smoke paths and default-branch-tip requirement before
the publication job can receive an HF token. The caller checkout is a literal
repository at `github.sha`; publisher tools come from `job.workflow_sha` at
`tools/`. The publisher keeps the established Space writer lock and uses
`ubuntu-24.04` with the existing hash-locked Python 3.12.10 client closure.

Publication derives its file set from Dockerfile COPY sources and writes
`SOURCE_REVISION` inside that set. It checks the exact main tip before the HF
commit, binds the non-secret `SZL_SOURCE_REVISION` variable, checks Space bytes
and smoke routes, then verifies `/api/build-info` reports the source revision.
The local source witness uses the literal `contract-only: true` branch; no HF
publication job is reachable from that branch. The effect declaration binds
the workflow, validator, tool closure, reviewed unknowns and target resources
to exact source digests. It grants no authority to another caller or Space.

These checks report source and observed runtime state for a particular run.
They do not certify seismic science, independent model quality, external
authorization or future availability. A failed or incomplete run remains
failed or incomplete. Rollback is a protected change to the seismic caller's
immutable reusable-workflow pin, followed by normal exact-head checks and a
new authorized publisher run; the existing A11oy publisher is unaffected.

## Trust-root bootstrap boundary

The policy, checker, checker tests, and enforcing workflow form a trust root.
A candidate change to any of them cannot honestly certify itself. Such a
change is a bootstrap or trust-root transition and cannot produce `ALLOW`.
An eligible transition produces `REVIEW_REQUIRED`; a hard violation remains
`DENY`. Bundling a denied ordinary workflow with a trust-root edit does not
downgrade that denial.

`REVIEW_REQUIRED` is a truthful stop for a trust-root decision, not an `ALLOW`
or an approval. SZL operates as a sole-owner build; do not invent an
independent human reviewer. For a trust-root transition, the owner or an
explicitly delegated operator must record a solo-owner attestation on the
exact PR head before requesting a normal protected merge. The record must name
the acting operator and state whether any independent human review occurred.
It must identify the base and head commits, the retained CP-eBOM decision
digest, the complete trust-root diff and exact source digests, workflow
permissions and action pins, terminal exact-head required checks, observed
unknowns and limits, and a rollback path. The acting operator must inspect
the evidence and state why the change is acceptable despite the non-`ALLOW`
receipt. A missing or `DENY` receipt is not eligible. This attestation is
accountable owner acceptance, not a GitHub self-approval or a claim of
independent review. Verify the commit signature when required by effective
branch rules, and read back the protected merge and receipt afterward. Any
approval requirement in effective branch rules still applies; do not bypass
it. A trust-root edit cannot downgrade an ordinary workflow's hard `DENY`.

After an owner-attested trust root is present on the protected base, ordinary
workflow changes are evaluated against the policy blob from that base.
Changing a workflow's source digest requires changing the policy and
therefore another trust-root decision. Later trust-root changes repeat the
same bootstrap process.

## Receipt and result semantics

The canonical receipt contains the exact analyzed revisions, merge base, tree
identities, raw-diff digest, changed Git modes and blob digests, policy and
checker identities, workflow analyses, effect deltas, conflicts, reason codes,
and a bounded claim. Stable ordering and canonical JSON make equivalent
analysis inputs produce equivalent receipt bytes. The decision digest binds the
canonical receipt fields other than the decision digest itself.

The workflow recognizes these verdict and process-exit pairs:

| Verdict | Exit | Workflow meaning |
| --- | ---: | --- |
| `ALLOW` | `0` | No unresolved effect in the declared scope. |
| `DENY` | `2` | A policy violation, unknown effect, or analysis failure blocks the change. |
| `REVIEW_REQUIRED` | `3` | A trust-root transition needs an explicit owner decision and protected checks; it is not `ALLOW`. |

Any missing receipt, malformed receipt, unknown exit code, or disagreement
between the receipt and process exit fails the workflow. `REVIEW_REQUIRED`
stays the receipt verdict. The required effect check passes that verdict only
when the release-admission verifier accepts one unedited owner decision for
the pull-request head. A missing, edited, stale-head, or wrong-owner decision
fails the check. A merge-group run uses that same pull-request head, and the
group's base, tree, and raw diff must be the ones the owner accepted. `ALLOW`
does not need an owner decision. `DENY` fails even when an owner decision is
present. The check does not relabel the receipt `ALLOW`. Direct push has no
owner-decision subject, so `REVIEW_REQUIRED` fails closed there.

The uploaded Actions artifact is run-scoped evidence with limited retention.
It is not an immutable attestation. Durable release evidence must bind the
protected merge commit to its hosted check result and retained receipt through
the repository's normal release-governance process.

## Claim limits

An `ALLOW` receipt supports only the claim
`VERIFIED_STATIC_EFFECT_BOUNDARY`. That claim applies to the analyzer's bounded,
reviewed grammar and the exact Git objects named in the receipt. It is not:

- a proof about arbitrary programs or obfuscated code;
- evidence that any provider call ran or succeeded;
- evidence that a deployment or runtime is healthy;
- authorization to use a secret or mutate a provider; or
- a substitute for branch protection, any review required by effective rules,
  or runtime witness.

The receipt explicitly states that no provider calls were performed and no
secret values were requested or recorded.

## Policy lifecycle

The policy is deny-by-default and time-bounded. Its workflow source digest,
trusted-transitive digests, action classifications, resource keys, budgets,
and required controls are reviewed together.

Before policy expiry:

1. Recompute every digest from the exact proposed Git blobs.
2. Review all analyzer and action-classification changes as trust-root changes.
3. Run adversarial self-tests and the gate at the exact candidate head.
4. Preserve least-privilege permissions and immutable action pins.
5. Renew validity only through a protected, owner-attested transition with
   terminal required checks and any review demanded by effective branch rules.

Expired intent, a weakened default, broader resource matching, or an unreviewed
trust expansion must remain denied.
