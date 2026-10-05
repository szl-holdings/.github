# Metricool offline contract: effect review

Evidence class: DECLARED source-review record. This is not an approval, a
provider permission, an independent-human review, or a deployment receipt.

## Review and authority boundary

The scoped change adds an offline governance contract, its synthetic regression
suite and a GitHub Actions workflow. The acting reviewer is the Codex
`github_security_readonly` subagent working under the owner-delegated root
operator. No independent human review occurred. The operator must still inspect
the complete final diff, the exact-head hosted checks and the retained effect
receipt before making the separate solo-owner attestation described in
[Control-Plane Effects](CONTROL_PLANE_EFFECTS.md).

The effect policy is a trust root. Adding a declaration is a trust-root change,
not a way for this candidate to certify itself. The required outcome for an
otherwise eligible candidate is `REVIEW_REQUIRED`, never a self-issued `ALLOW`.
A hard denial, missing receipt, incomplete source binding, or failed required
check remains a blocker. Existing declarations, expiry, deny defaults, effect
classifier and checker tests must remain unchanged.

## Execution reviewed

The workflow checks out this repository with a full event SHA expression and
`persist-credentials: false`, sets up Python 3.12, installs the exact hash-locked
schema libraries, compares the checked-out commit with the event SHA before
installing, and runs the config validator and synthetic tests. Before installing
or validating, the workflow rejects symlinks or SHA-256 mismatches on the four
fixed config, schema and dependency-lock input paths listed below. Its token permissions are only
`contents: read`. There are no explicit secret expressions, credential inputs,
artifact uploads, repository writes, PR mutations, publisher calls, deployment
operations, service containers, matrices or reusable-workflow dispatches.

Checkout reads this repository once. Setup Python has one recognized local
toolchain-install effect. The allowed external-write budget is zero. Pip can
read the package index and wheel files and install into the ephemeral runner;
this is not a network-free installation. `--require-hashes`, wheel-only
installation, isolated pip configuration and disabled pip cache constrain the
dependency operation. The current lock names six libraries. Hash equality does
not prove package safety, and Python's toolchain patch version and runner image
are not content-addressed by this change.

The validator reads fixed repository config/schema paths and bounded caller
input, checks consistency, and prints a redacted result. Even positive results
always report `allowed_to_publish: false` and zero provider writes. Schema
validation uses explicit local date-time/HTTPS format checkers and the reviewed
schemas have only local references. No inference, training, provider SDK, HTTP
client or credential request is introduced. The branded account identifiers in
tests are synthetic. Tests write and remove only their own temporary fixtures,
spawn the same interpreter on the known local CLI, and exercise deny paths.

This source review is narrower than an arbitrary-Python proof. Dynamic imports,
test subprocess calls, pip installation, shell commands, action inputs and the
step-scoped expected-SHA environment still require exact-byte review because
the static analyzer cannot prove their full behavior. An observed boolean
control hint is not provider compare-and-set or independent authorization.

## Exact source bindings

The base for this addition is
`fc71ae973a0f31b8e9ee793fc8545a354448d451`. The preceding local source candidate is
`9b6341eddbfb74be31cfd1b64426134d08d9bcf6`. The final candidate commit and hosted
decision digest are not yet assigned by this document. Digests below refer to
canonical Git/LF source bytes, not a Windows CRLF materialization.

The local integration preserves both the subsequent finite-number correction
`a343a9935140d6b0b08b655447caa04b69f4fa73` and reviewed remote config/document
source `fdcc7d24d296875fc40787a67512c87cfbcc68f6`. The remote `approvedChannels`,
required controls, update/evidence policies and operational states are retained.
A fixed `twitter` to `x` channel mapping leaves provider records and intent
identities unchanged; it grants no new provider alias or authority. The separate
implementation flags remain false. Local history integration is not a remote
writer handoff, branch publication, protected admission or provider deployment.

| Path | SHA-256 | Enforcement |
| --- | --- | --- |
| `.github/workflows/metricool-contract.yml` | `e070577e8ada1cabd541868fa459e6ed3a563b243a793096e52c4f02a5ee55fe` | Effect-policy source and reviewed-unknown pin |
| `.github/scripts/metricool_contract.py` | `04d1bb86ac925231972bd3742644db198683d66142f32486203fd7aaac417cf8` | Effect-policy reviewed-unknown pin |
| `.github/scripts/test_metricool_contract.py` | `1c3aadc57e940af02bb66dc157d390f742d25e531fd8d0617f07cd377e5f8f31` | Effect-policy reviewed-unknown pin |
| `config/metricool-control-plane.json` | `e4f6aa9f4741023738b85fd7217e6d79f724647c588379c9bfb7520794cb7a9c` | Pinned workflow checks bytes before installation/validation |
| `config/schemas/metricool-control-plane.schema.json` | `451b232a549ab7f04cc61d96a64f631dc4c5b1047cc091bb34bcb077587389f5` | Pinned workflow checks bytes before installation/validation |
| `schemas/metricool-publication-receipt.schema.json` | `cb9562c16c987e7a7448dfd49cc356419fd1b6df4fe2f771101d93ea5c3ca0b6` | Pinned workflow checks bytes before installation/validation |
| `requirements/metricool-contract.lock` | `6ff63ee80c5dab7249e3f7794b42ca1cb2a5a3bf2b989606e0c94d5955dcf606` | Pinned workflow checks bytes before installation/validation |
| `docs/METRICOOL_CONTROL_PLANE.md` | `8679370b01e1597ee573d88e36dbcd3c65823fc37d86f3f341ae36241d41c296` | Documentation-only review digest, not executable admission |

The static dependency grammar itself discovers the two Python files, not the
four other-root data inputs. Their coverage comes from the reviewed, pinned
workflow's explicit byte guard. No classifier change or fabricated dependency
coverage is asserted. Both Python invocations use isolated mode and explicit
file paths; the test invocation does not depend on discovery of an unpinned
test-directory prefix.

The action pins remain checkout
`3d3c42e5aac5ba805825da76410c181273ba90b1` and setup-python
`5fda3b95a4ea91299a34e894583c3862153e4b97`. The declaration requires the three
actual triggers, contents-read, no explicit secrets and concurrency. It does
not claim the analyzer recognized protected-ref, exact-SHA, expected-before
or readback controls: those hints are false in its actual output. The explicit
checkout/SHA comparison remains part of the exact-byte source review.

## Local binding preview

A network-free preview used the admitted PyYAML 6.0.3 and existing checker
functions `load_policy_bytes`, `analyze_workflow_source`, `analyze_dependency`
and `bind_declaration` over canonical working-tree bytes. This is not an
exact-commit repository receipt.

The Metricool declaration bound both recognized effect sites with one call
each, zero external writes and no per-workflow denial reason. Its complete
41-member eligible unknown set matched the source pins: two action-input
reviews, three synthetic-test subprocess sites, thirteen Python import sites,
three Python source reviews, eighteen shell-command locations, one shell
composition and one step environment. These unknowns were inspected in the
bounded source described above; they were not erased or generalized to future
source. Changing a byte or the unknown set invalidates this declaration.

The same preview evaluated all 25 declarations: none had per-workflow denial
reasons. It still reports the existing cross-workflow resource conflict on
`stepsecurity:monitor:szl-holdings/.github` between `recover-nexus-target.yml`
and `responsive-estate-v3.yml`. Neither declaration was modified. This report
does not waive or remove that conflict. The final repository verdict must
remain a trust-root review decision with all observed reasons retained.

After removing only the new Metricool declaration, parsed policy equality
against the base blob was true. Existing declaration semantics, trust maps,
defaults and validity dates remain unchanged. The historical LF policy digest
before finite-number hardening was
`58d1dc10897ee9268e87f53a9f630f68f378e67f2c72f11a326c3d46052d557a`.

## Required admission evidence

The final exact policy declaration must bind the workflow, local executable
dependencies and their complete observed eligible-unknown set. Input manifests
or supplemental hash tables must distinguish enforced pins from documentation
only. Do not call absent dependency coverage complete, accept unreviewable
unknowns, or modify the classifier merely to remove an inconvenient result.

Run parser validation, contract regressions, checker self-tests and exact Git
object analysis after the final commit is created. Record the resulting base,
head, retained decision digest, complete trust-root diff, action pins, observed
unknowns, limits and exact-head required-check conclusions in the separate
operator attestation. Do not invent that future digest in this review.

## Rollback

Use a normal protected PR to revert the Metricool workflow and its newly added
declaration together, preserving every pre-existing policy entry and default.
Retain the old effect receipt and PR history. Do not loosen controls, delete
external data, rewrite protected history, or disable gates. There is no new
provider writer or deployed service to roll back.
