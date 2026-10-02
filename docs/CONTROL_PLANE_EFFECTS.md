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

The policy admits only its explicitly declared workflows, including the
reviewed front-door scope described below. A change to an undeclared workflow or
an unbound executable/configuration path is denied by this gate until its
effect contract is reviewed and added. The workflow is not a required branch
protection context merely because this file is present.

## What the gate evaluates

For each selected workflow, the gate binds observed behavior to an explicit
declaration:

- event triggers and GitHub token permissions;
- referenced credential names, never credential values;
- exact SHA-pinned actions with reviewed effect classifications;
- local executable dependencies covered by exact content digests;
- literal local Hugging Face JSON `--manifest` arguments, including their
  publication target;
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
fan-out, unsupported runners or shells, and unbounded checkout targets are not
modeled execution boundaries and cannot be waived with an exact-byte review.
A literal checkout repository override binds the actual repository resource.
Credential expressions are inspected after YAML decoding; receipts record
only referenced credential names, including fallback and bracket forms.

Known action input keys must be ASCII identifiers and are normalized with
the runner's case-insensitive semantics; normalization collisions are denied.
Explicit authentication inputs must resolve wholly to named secret or
`GITHUB_TOKEN` references; literal, dynamic, or unbound fallback authority
is denied without recording its value. Artifact names bind the
actual literal destination. A fixed literal prefix followed by exactly
`-${{ github.run_id }}`, `-${{ github.run_id }}-${{ github.run_attempt }}`, or
`-${{ github.sha }}` binds a distinct exact `artifact-template` resource key
containing both the prefix and the suffix type. This models the provider-owned
numeric/hex suffix; it does not admit arbitrary dynamic names or wildcard
matching. The original `control-plane-effect-${{ github.run_id }}` contract
retains its existing run-scoped resource key. Other dynamic names, non-archived uploads,
overwriting/deleting artifacts, Python cache writes, and checkout options
that fetch unmodeled resources are denied. A checkout cannot substitute
foreign repository or unbounded revision bytes for pinned local dependencies.
Explicit `github.sha` is accepted only when events or an exact event condition
exclude pull requests: a PR's `github.sha` names a synthetic merge commit rather
than the head whose dependencies the gate binds. The existing exact
PR/merge-group/event SHA fallback remains supported.
A direct PR head SHA requires the exact PR-event condition on its job or step.
The one admitted step-output resolver is matched against its complete canonical
shell body and environment bindings: it accepts same-repository PR heads,
rejects fork PRs instead of falling back to their synthetic merge revision,
requires same-repository `main` for workflow-run heads, and validates a 40-hex
result before writing its output. It must precede its consumer, have a unique
step ID, run unconditionally without ignored failures, be consumed only under
default or explicit `success()` gating, and have no inherited
environment or preceding arbitrary executable code. Modified or other output
resolvers remain denied. These source selectors describe event revisions; they
do not independently prove a live provider's event payload or release state.

Run blocks may interpolate only provider-owned `github.sha`, `github.run_id`,
`github.run_attempt`, or that validated hex resolver output. All remaining
shell/Python analysis, exact-byte review, effect declarations, and mutation
budgets still apply; allowing an inert value does not prove the surrounding
program safe. User-controlled strings, fallback expressions, missing resolvers,
and malformed expressions remain denied. Unknown
external actions, unresolved local actions or dependencies, and reusable
workflows cannot be accepted by reviewing only the caller's bytes.
Executable control hints come from run blocks, not workflow names or labels.

Owner-reviewed unknowns remain available only for eligible bounded source
constructs. Acceptance requires exact file digests and the complete observed
unknown set; the receipt records whether that review was applied. This cannot
waive invalid YAML, unresolved authority or execution boundaries, or fan-out.

## Front-door workflow admission

The front-door declarations bind organization-card content writes to
`huggingface:space:SZLHOLDINGS/README:contents` and visibility changes to
`huggingface:space:SZLHOLDINGS/README:settings`. The central wrapper enforces
this target directly; the production publisher's literal manifest is also
included in the reviewed file digests. Changing its target invalidates that
review. Both real publishers use the same `hf-org-card-main` concurrency group
for publication with cancellation disabled. The receipt preserves the shared
resource conflict for review; it does not infer authorization or provider
compare-and-set behavior from the concurrency group.

The estate and router validators invoke the same deployment helper only in
materialization mode. Static dependency analysis still inventories the helper's
SDK write site, so their declarations conservatively name that same manifest
target and retain the conflict. This is an inventory of potential source
effects, not a claim that validation published anything.

The `tests.yml` declaration binds its seven observed SDK sites to the exact
`runner:test-double:huggingface-client` fixture resource. This key describes
local fake/mock API instances, not a Hugging Face repository or deployment.
The reviewed test source supplies `FakeApi` for source-variable writes,
replaces `huggingface_hub.HfApi` for restart tests, and passes `mock.Mock`
instances to commit tests. Production CLI entries in that workflow are compile
and help checks; it supplies no Hugging Face secret or publication command.
The declaration pins the workflow, test modules, and referenced production
modules and retains all seven conservative `external-write` site counts.
This fixture binding must not be generalized to another workflow or changed
test harness without a fresh source and policy review.

## Trust-root bootstrap boundary

The policy, checker, checker tests, and enforcing workflow form a trust root.
A candidate change to any of them cannot honestly certify itself. Such a
change is a bootstrap or trust-root transition and cannot produce `ALLOW`.
An eligible transition produces `REVIEW_REQUIRED`; a hard violation remains
`DENY`. Bundling a denied ordinary workflow with a trust-root edit does not
downgrade that denial.

`REVIEW_REQUIRED` is a truthful stop for independent human review. The reviewer
must inspect the complete trust-root diff, exact digests, workflow permissions,
action pins, test evidence, and protected-branch result before accepting the
new root. The check result is supporting evidence; it is not an independent
approval of code that executed from the candidate revision.

After a reviewed trust root is present on the protected base, ordinary workflow
changes are evaluated against the policy blob from that base. Changing a
workflow's source digest requires changing the policy and therefore another
trust-root review. Later trust-root changes repeat the same bootstrap process.

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
| `DENY` | `2` | Policy violations or analysis failures block the change. |
| `REVIEW_REQUIRED` | `3` | A trust-root transition needs independent review. |

Any missing receipt, malformed receipt, unknown exit code, or disagreement
between the receipt and process exit fails the workflow. `REVIEW_REQUIRED`
completes the reporting step so reviewers can inspect its artifact; the
receipt's decision remains `REVIEW_REQUIRED`. Acceptance depends on normal
protected-branch review and merge rules.

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
- a substitute for branch protection, independent review, or runtime witness.

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
5. Renew validity only through a protected, independently reviewed change.

Expired intent, a weakened default, broader resource matching, or an unreviewed
trust expansion must remain denied.
