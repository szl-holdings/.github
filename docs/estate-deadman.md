# Estate dead-man supervisor

The estate dead-man is an independent GitHub-hosted observer for the scheduled
control planes that keep the SZL public estate measured and recoverable.

It monitors three exact workflow definitions:

| Target | Expected cadence | Failure budget |
|---|---:|---:|
| `szl-org-health/autonomic-sre.yml` | 5 minutes | 30 minutes without a successful scheduled run |
| `szl-org-health/scheduled-estate-census.yml` | 6 hours | 8 hours without a successful scheduled run |
| `a11oy/public-estate-live-witness.yml` | 6 hours | 8 hours without a successful scheduled run |

The latest completed run has precedence. A recent green run cannot conceal a
newer red run. Active runs are accepted only inside their bounded duration and
only when backed by a fresh success or a newly installed workflow's first-run
grace period.

Completed runs must have a terminal update time at or after their creation time.
An impossible timestamp sequence is rejected before it can influence health.

A suspected failure is sampled twice, sixty seconds apart. Only the same target
failing both samples creates or refreshes the single `[ESTATE-DEADMAN]`
incident. Alternating or recovered samples are `INCONCLUSIVE`, fail the run,
and cannot create, refresh, or close an incident. A later wholly healthy cycle
closes the incident. Every confirmed-failure cycle refreshes the reserved issue;
there is no marker-controlled throttle that another workflow could replay to
suppress current evidence. Each accepted marker is structurally consistent
with an immutable provider-authenticated scheduled workflow attempt. It does
not claim causal authorship because same-repository workflows using the built-in
Actions identity can also write issues; every confirmed cycle overwrites the
reserved issue with current evidence.

The controller checks the protected branch revision again after incident
discovery and immediately before every create, comment, refresh, or close.
If the branch changes between a recovery comment and closing the issue, the
close is withheld and the receipt records the failed reconciliation.

Legacy incident records that predate run-bound markers are not trusted as
current incidents. An operator can preserve the original body and open state,
retitle the record outside the exact reserved title, and document the migration.
The next scheduled cycle creates current evidence under the reserved title if
failure is confirmed. Migration never supplies a synthetic run marker or claims
that the underlying outage recovered.

Each cycle writes a JSON receipt and a `.sha256` sidecar containing the SHA-256
of the exact emitted JSON file bytes. The receipt contains public
workflow identifiers, timestamps, conclusions, bounded age calculations, and
the incident action. Its `policy_sha256` binds the exact canonical-LF policy
source bytes, and duplicate JSON object keys are rejected. It contains no
credential value.

## Authority boundary

The supervisor mints the existing QILLQAQ GitHub App into a read-only token
restricted to `.github`, `szl-org-health`, and `a11oy`; that token can read
Actions and contents metadata only. The built-in `.github` job token is kept in
a separate client and can manage one incident issue only. Neither credential
can edit workflow definitions, branches, repository contents, deployments,
DNS, Hugging Face assets, models, products, or public effectors. The controller
accepts no caller-supplied repository, workflow, branch, or URL.

The private cross-repository App installation is an operational prerequisite,
not a source-level claim. The controller is not operationally proven until a
real provider-scheduled run reads all three repositories and emits a terminal
receipt. Missing App authority fails closed; there is no fallback to a broader
personal token or to the repository-scoped incident token.

## Independent failure domains

This control plane is independent from the workflows it observes, but it still
uses GitHub Actions and the GitHub API. It therefore detects disabled, stale,
stuck, and failed scheduled workflows across repositories, but it cannot report
a total GitHub control-plane outage while GitHub itself is unavailable.

The next resilience tier is an external dead-man hosted outside GitHub with the
same read-only policy and a separate notification path. Until that tier is
proven, the repository makes no claim of provider-independent availability.

## Reproduce the contract

```bash
python -m py_compile .github/scripts/estate_deadman.py tests/test_estate_deadman.py
python -m unittest discover -s tests -p 'test_estate_deadman.py' -v
python .github/scripts/estate_deadman.py \
  --offline-contract-only \
  --output reports/estate-deadman-contract.json
```
