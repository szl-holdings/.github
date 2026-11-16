# SZL estate lifecycle map

Census completed: `2026-11-16T22:56:04.967948+00:00`.

Repository inventory observed: `2026-11-16T22:54:43.793864+00:00`, through
authenticated GitHub organization repository API reads with pagination exhausted
(100 + 65 records): **165 repositories**.

This map distinguishes observed repository state from recorded migration plans.
Archiving preserves source, release, citation, and provenance history; it is
not deletion and does not mean the artifact was unimportant.

## Observed estate

| State | Count | Policy |
|---|---:|---|
| Public repositories | 137 | Open by default after license, secret, dependency, and release-history review |
| Private repositories | 28 | Retained only for lead data, fundraising material, or security operations |
| Archived repositories | 29 | Public and read-only; retained for reproducibility and provenance |
| Active repositories | 136 | Product, proof, documentation, or shared infrastructure |

### Inventory reconciliation

The enumerated counts supersede the 2026-08-01 snapshot and correct this change's
earlier 162-repository calculation. The organization metadata reports
`public_repos=137` and `owned_private_repos=28`, consistent with the 165 enumerated
repositories. The separately reported `total_private_repos=25` quota field does
not represent the enumerated owned-private count and must not be used to derive
this inventory.

Visibility and archive state were observed read-only; this update changes no
repository settings. No private repository names are published here. These are
dated observations, not a claim that every repository is operational or that
every migration is complete.

Observed archived public repositories:

`a-11-oy.github.io`, `cosmos`, `counsel`, `developers`, `docs-site`,
`energy-attest-holo`, `evidence-typed-formula-governance`,
`fail-closed-governed-ai-services`, `governed-inference-meter`,
`governed-norm-holo`, `immune-lattice`, `khipu-lab`, `khipu-pages`,
`lambda-gate-holo`, `lean-kernel`, `ouroboros`, `receipt-chain-live`,
`szl-cookbook`, `szl-experiments`, `szl-fleet-overlay`, `szl-formula-ledger`,
`szl-governed-norm`, `szl-kernels-live`, `szl-otel-mesh`,
`szl-organ-integrity`, `szl-provctl-live`, `szl-telemetry`,
`szl-uds-deployment`, and `warhacker-demo`.

[`szl-substrate`](https://github.com/szl-holdings/szl-substrate) remains an active,
independently versioned public shared package used by a11oy and killinchu.

## Recorded canonical mappings

The seven mappings below are retained from the earlier lifecycle plan. Their
source states reflect the dated inventory above; their destinations and
retention reasons are historical records, not fresh verification that each
migration completed. In particular, `docs-site` is now archived, so its paths
remain historical references pending an active documentation destination.
`uds-bundles` is active and must not be described as currently archived.

| Repository | Observed state | Recorded destination | Retention reason |
|---|---|---|---|
| [`developers`](https://github.com/szl-holdings/developers) | Archived | [`docs-site/docs/developers`](https://github.com/szl-holdings/docs-site/tree/main/docs/developers) | Developer documentation history |
| [`evidence-typed-formula-governance`](https://github.com/szl-holdings/evidence-typed-formula-governance) | Archived | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) and [`szl-papers`](https://github.com/szl-holdings/szl-papers) | Final DOI reproduction package; immutable research record |
| [`fail-closed-governed-ai-services`](https://github.com/szl-holdings/fail-closed-governed-ai-services) | Archived | [`a11oy`](https://github.com/szl-holdings/a11oy) and [`platform`](https://github.com/szl-holdings/platform) | Final DOI reproduction package; implementation destination recorded in the lifecycle plan |
| [`szl-otel-mesh`](https://github.com/szl-holdings/szl-otel-mesh) | Archived | [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Superseded mesh implementation; DOI and history retained |
| [`szl-uds-deployment`](https://github.com/szl-holdings/szl-uds-deployment) | Archived | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | UDS deployment-family source and release evidence |
| [`uds-bundles`](https://github.com/szl-holdings/uds-bundles) | Active | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Signed bundle manifests and provenance |
| [`warhacker-demo`](https://github.com/szl-holdings/warhacker-demo) | Archived | [`a11oy`](https://github.com/szl-holdings/a11oy) and [`killinchu`](https://github.com/szl-holdings/killinchu) | Concluded demonstration retained as a historical record |

## Recorded consolidation requirements

The earlier plan called all five sources below active. Four are archived in the
current dated inventory; `szl-trust` remains active. The requirements remain
follow-up items whose completion has not been verified by this inventory.
An archive flag alone does not prove that executable surfaces, publisher
ownership, credentials, or provenance were transferred successfully.

| Repository | Observed state | Recorded destination | Migration requirement to verify |
|---|---|---|---|
| [`governed-inference-meter`](https://github.com/szl-holdings/governed-inference-meter) | Archived | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest) | Verify successor ownership of the HF publisher and drift guard, scoped credentials, Model-versus-Kernel ownership, and a successor-owned publish |
| [`szl-fleet-overlay`](https://github.com/szl-holdings/szl-fleet-overlay) | Archived | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Verify migration of the UDS Operator packages, Helm chart, Zarf bundle, release path, and their provenance |
| [`szl-cookbook`](https://github.com/szl-holdings/szl-cookbook) | Archived | [`docs-site/docs/cookbook/recipes`](https://github.com/szl-holdings/docs-site/tree/main/docs/cookbook/recipes) for presentation | Verify migration of runnable TypeScript, Lean, payloads, operator tooling, workflows, the Pages carousel, and inbound A11oy references; the recorded docs-site destination is also archived |
| [`szl-governed-norm`](https://github.com/szl-holdings/szl-governed-norm) | Archived | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Verify the later non-finite receipt-digest hardening and compatibility namespace, and reconcile Forge, Model, Kernel, and registry revision pins |
| [`szl-trust`](https://github.com/szl-holdings/szl-trust) | Active | [`docs-site/docs/trust`](https://github.com/szl-holdings/docs-site/tree/main/docs/trust) | Before archive, migrate the offline verifier, tests, and scoped CC-BY license/notice; reconcile the archived documentation destination and verify an active canonical docs site |

## Lifecycle rules

1. Do not unarchive a repository merely because it contains important work.
   Frozen DOI packages, signed release artifacts, and concluded demonstrations
   are more trustworthy when their historical state remains read-only.
2. Consolidate maintained documentation and implementation into the named
   canonical repository, while keeping provenance links back to the archive.
3. Unarchive only when active maintenance must resume and no canonical active
   destination can accept the change.
4. Never move secrets, customer or lead data, fundraising material, or
   security-operational data into a public repository.
5. Every visibility change requires a license check, secret scan, dependency
   review, and a successful default-branch test history.
