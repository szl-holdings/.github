# Frontier public read-only effect declaration proposal

Status: **PROPOSAL — no operational activation or owner acceptance is recorded here.**

This separate policy change binds the read-only repair initially frozen as
`24df38d1671da5fdef280471915f1acb53d05746` (tree
`217bcf58f5d938fd829bc973684798dcd9e4e8c4`). Its protected base is
`b352ab29bb9a19c0754c5d8f5bf56cd62ccf7a2e`. The source repair and this
trust-root proposal are separate commits. The closure below includes the later
two-line correction distinguishing verifier credential isolation from checkout
read access; executable behavior is unchanged.

## Exact reviewed execution closure

| Source | SHA-256 |
| --- | --- |
| `.github/scripts/frontier_payload/config.py` | `d9d2605f8bf324ca6f4e3f9c103f2710dc3c38ef02f317661ad96f5ac98d80ff` |
| `.github/scripts/frontier_payload_readonly.py` | `71cdcd83a487c9ab8612edae6fae9747a5065c8551b5c89d6308bf7e519c92f9` |
| `.github/scripts/test_frontier_payload_readonly.py` | `de4021b4730594340634c46521414f048ef22dbb9c3e7feb2dfcfc16f7e814f9` |
| `.github/workflows/frontier-payload-convergence.yml` | `ee3b068f18ef04451c8839427cdacda79947891f3459cce2f2ea28894ed82308` |

The workflow executes only these fixed entrypoints:

```text
python -I -P -m py_compile .github/scripts/frontier_payload_readonly.py .github/scripts/frontier_payload/config.py .github/scripts/test_frontier_payload_readonly.py
python -I -P .github/scripts/test_frontier_payload_readonly.py
python -I -P .github/scripts/frontier_payload_readonly.py --report /tmp/szl-frontier-payload-convergence-v1.json --summary /tmp/szl-frontier-payload-convergence-v1.md
```

The helper loads the pure configuration by exact file path. It never imports
the operational package initializer, controller, provider SDK, or mutation helpers.
The test fixture uses synthetic transports and native local timers; it does not
perform the public observations. The separately reviewed legacy fixture
`tests/test_frontier_payload_convergence.py` has SHA-256
`1646b895eee2569eac66d15210bd664c9e4ffec5e239f016acf938b434f933a4`.
Its obsolete workflow assertion was updated to the repaired read-only contract;
the legacy operational tests are retained and run offline separately. This file
is not invoked by the read-only workflow or included in its execution closure.

## Authority and bounded effects

- All workflow and job permissions are `contents: read`; credential references
  are empty, and checkout does not persist credentials.
- Both dispatch write inputs default to false. Either explicit true value fails
  before checkout, setup, or observation. The helper rejects write flags itself.
- Public observation runs only outside PR/merge-group events, on protected main,
  after offline contracts. An executable preflight verifies the ref and exact
  checked-out commit against `GITHUB_REF` and `GITHUB_SHA`.
- Existing action pins, action classifications, and checker grammar are unchanged.
- Two checkout, two Python setup, and two runner guard invocation sites are
  declared. The sole declared external-write site is one archived artifact upload
  to `frontier-payload-readonly-verification`, with no overwrite or deletion.
- Artifact paths are exactly the two fixed report files above, with 90-day
  retention and missing-file failure. GitHub scopes the literal artifact name
  to its workflow run. It is bounded run evidence, not durable attestation.
- The report is at most 65,536 bytes; the summary is at most 16,384 bytes. Network
  error text and bodies are not included. Public bodies contribute only hashes,
  lengths, literal-match results, and validated nonzero full source revisions.

The four policy counters count recognized source invocation sites. They do not
claim exact HTTP packet counts or a formal proof of third-party action internals.
The helper performs at most 14 anonymous GET invocations against the following
exact resources, with no redirects, retries, implicit proxy authority, provider
credentials, private-space requests, provider writes, dispatches, or messages:

| Public GET resource |
| --- |
| `https://a-11-oy.com/controller` |
| `https://a-11-oy.com/eu-ai-act` |
| `https://a-11-oy.com/spectral` |
| `https://a11oy.net/` |
| `https://api.github.com/repos/szl-holdings/a11oy/commits/main` |
| `https://api.github.com/repos/szl-holdings/david-leads` |
| `https://api.github.com/repos/szl-holdings/szl-atelier` |
| `https://gdw.a-11-oy.com/healthz` |
| `https://huggingface.co/spaces/SZLHOLDINGS/vessels/raw/main/README.md` |
| `https://raw.githubusercontent.com/szl-holdings/killinchu/main/docs/hf-cards/SZLHOLDINGS-vessels.README.md` |
| `https://szlholdings-a11oy.hf.space/api/build-info` |
| `https://szlholdings-a11oy.hf.space/api/livez` |
| `https://szlholdings-a11oy.hf.space/eu-ai-act` |
| `https://szlholdings-killinchu.hf.space/` |

Every public read has a 2,000,000-byte response limit, a native wall-clock timer
of at most 30 seconds, and the remaining monotonic 600-second aggregate deadline.
The workflow also retains its 25-minute job timeout. The static analyzer does
not extract GET effects; the explicit read resources and these bounds are
reviewed source behavior, supported by the network-free boundary tests.

`READ_ONLY_VERIFIED` requires both metadata rows, byte-identical valid Vessels
cards, exact A11oy main/runtime parity, and all nine public probes. The report
preserves eight critical probes and one advisory probe as separate counts, but
even advisory failure prevents overall success. Otherwise the helper emits
`NOT_YET_CONVERGED` and exits 1. Its schema is
`szl.frontier-payload-readonly/v1`; it makes no operational convergence claim.
Operational effects remain `HELD`, private Spaces remain `UNOBSERVED`, and
credentials are neither observed nor used. Available-token fields are false
with `credential_availability_observed: false`; they are not an environment census.

## Static review and decision boundary

The declaration pins all four exact source files and the complete 69-entry
`CODE@path:line` eligible unknown set. Source hash drift, unknown-set drift,
unclassified actions, credential or permission expansion, wildcard resources,
and excess mutation budgets retain their existing denials. No checker, default,
allowlist grammar, validity window, other declaration, or protected controller
is changed. The declaration expires with the existing policy on 2026-11-30.

The unknowns are bounded source-review requirements for Python imports and
dynamic test instrumentation, the anonymous urllib call, shell composition,
workflow environments, and known action inputs. Their complete identities are
in the policy entry; this document is not a substitute for those exact pins.

A policy edit is a trust-root transition. The complete candidate must produce
`REVIEW_REQUIRED`, never self-certify `ALLOW`; ordinary workflow analyses must
still bind without denial. This is a proposed source review, not an owner
attestation or independent human approval. The explicitly delegated operator
must retain the exact-head decision receipt, inspect terminal protected checks,
record the required exact-head owner decision, and use the normal protected
merge. A missing or DENY receipt cannot be accepted.

No public observations, provider mutations, credentials, native workflow runs,
GitHub messages, remote writes, or merges were performed to prepare this proposal.

Rollback is a reviewed protected revert of this declaration and source repair;
do not restore mutation-enabled defaults, write permissions, credential ingress,
or the malformed jobs from the earlier source. Any newer source requires fresh
exact pins and a new trust-root decision.
