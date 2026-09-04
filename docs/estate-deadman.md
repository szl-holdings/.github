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

A suspected failure is sampled twice, sixty seconds apart. Only a confirmed
failure creates or refreshes the single `[ESTATE-DEADMAN]` incident. Recovered
evidence closes that incident automatically. Refreshes are throttled to one per
hour so a provider outage cannot create an issue or notification storm.

Each cycle writes a JSON receipt and SHA-256 digest. The receipt contains public
workflow identifiers, timestamps, conclusions, bounded age calculations, and
the incident action. It contains no credential value.

## Authority boundary

The supervisor can read exact GitHub workflow and run metadata and can manage
one incident issue. It cannot edit workflow definitions, branches, repository
contents, deployments, DNS, Hugging Face assets, models, products, or public
effectors. It accepts no caller-supplied repository, workflow, branch, or URL.

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
