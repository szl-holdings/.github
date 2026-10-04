# HF release dependency source and effect review

This change closes the actual five-workflow path dependency of the final-estate
v5 contract repair. It does not modify the effect checker or remove active
trigger/test dependencies to evade selection. The operational HF terminal and
Kernel v2 publisher remain unchanged.
This review does not establish the unchanged v2 workflow's enabled state or
global publisher exclusivity. It preserves the existing Kernel Git finalizer;
no additional publication path is introduced.

## Entrypoints and source owners

| Workflow | Executable boundary | External effects |
| --- | --- | --- |
| final-estate-reconciliation-v5 | Fixed v5 CLI, source checked before/after | Bounded GitHub/public GET/HEAD and one run artifact |
| final-estate-reconciliation-v5-pr | Source suites | One run artifact; no verifier CLI or explicit credentials |
| hf-release-readiness-terminal-pr | Fixed offline runner and source suites | One run artifact; socket/DNS/process effects denied before imports |
| hf-release-finalization | Existing canonical Git adapter with source checks | Existing two Kernel card/contract publications, two private dataset evidence uploads, one run artifact |
| hf-release-finalization-pr | Existing source, transport and upstream suites | Public protected-source acquisition and one run artifact; no publisher CLI or explicit credentials |

Repository-wide caller inspection found the operational workflow invokes only
hf_release_finalization_git.py. Its main installs KernelGitFinalizer as the
legacy CLI's Finalizer, retaining the retry layer. The base kernel and evidence
publisher implementations had no active production caller. They now raise
explicit unsupported-entrypoint errors. This removes dormant generic Kernel
upload and dataset-create implementations rather than granting them effects.
The base Lake verification and all its existing source projection, lineage,
index digest, direct predecessor, receipt count, and stable Viewer controls are
unchanged. The tests retain real data fixtures and no missing dependency stub.

The supported controller checkout binds the exact event head. The three fixed
public source owners are szl-lake, szl-energy-attest, and szl-lambda-gate. The
new helper observes each protected main, fetches that exact SHA with full
history, retains the three existing ancestry floors, checks the local HEAD,
and reads main again. It never fetches a caller-selected target. Git hooks,
ambient configuration, file/ext transport and credential helpers are disabled.
The same five upstream contract commands remain, with publisher credentials
removed from their child environment. Every checkout must remain clean.

Operational source verification additionally binds the actual local controller
HEAD and tracked script/workflow bytes, exact event SHA, canonical repository,
main ref, supported event, and current protected main. It runs before/after
source contracts, before/after each canonical Kernel publication, before/after
each of the two evidence uploads, and around the final CLI. A changed source
blocks acknowledgement; it cannot roll back a provider write that already
occurred. These repeated observations are not an atomic cross-repository lease.

## Preserved provider effects and credentials

The only active Kernel targets remain SZLHOLDINGS/governed-inference-meter and
SZLHOLDINGS/szl-governed-norm. The existing Git transport changes README.md and
contract.json, preserves the complete build tree, uses expected metadata
revision and immutable readback, and retains both selfchecks. No model, Space,
hardware, repository creation, visibility, or alternate publisher is added.

The two existing private SZLHOLDINGS/szl-evidence dataset destinations remain
release-finalization-v2/latest.json and the timestamped
release-finalization-v2/history/<timestamp>.json. The existing existence preflight is retained; it does not independently
attest current privacy. No creation or visibility mutation is allowed. The existing
HF_ORG_TOKEN/HF_ORG_TOKEN1 fallback and HF_TOKEN enter only the original
publication step. GITHUB_TOKEN has contents:read for exact protected-main GETs.
Public Git child processes and child source tests receive no such credential.
PR jobs use checkout's declared read access without persisting it and supply no
provider or GitHub token to test commands.

The finalizer's issues:write permission and automatic issue update step are
removed. The v5 consumer of issue 301 is replaced with digest/run/attempt/source
bound native artifact evidence; no material evidence dependency is silently
removed. The v5 report's own automatic issue writes are also removed. Existing
issues are left untouched, while the unchanged terminal keeps its issue 257
ownership. All existing operational trigger lanes and signed receipt checks
remain. This source work neither dispatches nor enables any workflow.

## Exact policy and bounded interpretation

Five declarations pin exact workflow bytes, transitive source hashes, action
pins, credentials, recognized effects, and every reviewed unknown identity.
Literal artifact names denote exact run-local resources, with unchanged paths
and 30/90-day retention. All seventeen existing declarations, global budgets,
policy dates, trust roots, default denials and checker bytes remain unchanged.

The static checker also sees an HTTP PATCH in the unchanged terminal helper
because the source tests inspect that file. The terminal PR runner denies
network/process effects before importing it; the finalizer workflow only lists
it as trigger/test source data and never executes it. Those sites are bound to
separate test/source-inventory resources, not to a GitHub issue capability.
Likewise, the finalizer PR's dataset upload site is reached only through
synthetic provider fixtures without credentials, while its operational binding
covers exactly the existing two dataset evidence writes. Dynamic Kernel Git
commands and third-party imports remain explicit, source-reviewed unknowns;
the declaration does not pretend the checker proves arbitrary Python behavior.

The two existing Kernel targets also appear as resource-only inventory entries
in the operational declaration. They add no effect, capability or grant, and
the checker does not enforce their dynamic Git behavior or include those
entries in conflict detection. The max_external_writes value of four is the
recognized-sink allowance, including the unexecuted terminal PATCH source
site. It is not an overall runtime write ceiling. The active outer call graph
contains up to two existing Kernel publish operations, two existing evidence
SDK upload invocations, and one artifact upload action. SDK/Git internal
requests, retries and wire effects are not bounded by that static site count.

The complete closure contains 13 files for each v5 workflow, 9 for terminal PR,
15 for operational finalization, and 12 for finalization PR. Source acquisition
uses bounded metadata bodies/timeouts, fixed Git commands with 180-second
process limits and five 300-second source commands. These limits do not prove
arbitrary transitive library termination; workflow timeouts remain the outer
bound. Native full finalizer tests are still required before admission.
