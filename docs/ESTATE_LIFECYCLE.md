# SZL estate lifecycle map

Status date: 2026-08-01

This map distinguishes active product surfaces from frozen public records.
Archiving preserves source, release, citation, and provenance history; it is
not deletion and does not mean the artifact was unimportant.

## Current estate

| State | Count | Policy |
|---|---:|---|
| Public repositories | 58 | Open by default after license, secret, dependency, and release-history review |
| Private repositories | 4 | Retained only for lead data, fundraising material, or security operations |
| Archived repositories | 7 | Public and read-only; retained for reproducibility and provenance |
| Active repositories | 55 | Product, proof, documentation, or shared infrastructure |

[`szl-substrate`](https://github.com/szl-holdings/szl-substrate) is the newest
public shared package. It remains an active, independently versioned boundary
used by a11oy and killinchu.

## Archived-to-canonical map

| Frozen public repository | Canonical active destination | Retention reason |
|---|---|---|
| [`developers`](https://github.com/szl-holdings/developers) | [`docs-site/docs/developers`](https://github.com/szl-holdings/docs-site/tree/main/docs/developers) | Developer documentation migrated; history retained |
| [`evidence-typed-formula-governance`](https://github.com/szl-holdings/evidence-typed-formula-governance) | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) and [`szl-papers`](https://github.com/szl-holdings/szl-papers) | Final DOI reproduction package; immutable research record |
| [`fail-closed-governed-ai-services`](https://github.com/szl-holdings/fail-closed-governed-ai-services) | [`a11oy`](https://github.com/szl-holdings/a11oy) and [`platform`](https://github.com/szl-holdings/platform) | Final DOI reproduction package; implementation continues in the active runtime |
| [`szl-fleet-overlay`](https://github.com/szl-holdings/szl-fleet-overlay) | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Frozen UDS deployment-family source and release evidence |
| [`szl-otel-mesh`](https://github.com/szl-holdings/szl-otel-mesh) | [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Explicitly superseded mesh implementation; DOI and history retained |
| [`szl-uds-deployment`](https://github.com/szl-holdings/szl-uds-deployment) | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Frozen UDS deployment-family source and release evidence |
| [`uds-bundles`](https://github.com/szl-holdings/uds-bundles) | [`a11oy`](https://github.com/szl-holdings/a11oy), [`killinchu`](https://github.com/szl-holdings/killinchu), and [`szl-mesh`](https://github.com/szl-holdings/szl-mesh) | Frozen signed bundle manifests and provenance |
| [`warhacker-demo`](https://github.com/szl-holdings/warhacker-demo) | [`a11oy`](https://github.com/szl-holdings/a11oy) and [`killinchu`](https://github.com/szl-holdings/killinchu) | Concluded demonstration retained as a historical record |

## Active consolidation candidates

These repositories remain active. A canonical destination is a migration
direction, not evidence that the source has already been archived.

| Active repository | Intended destination | Required before archive |
|---|---|---|
| [`governed-inference-meter`](https://github.com/szl-holdings/governed-inference-meter) | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest) | Transfer the only live HF publisher and drift guard, re-enter its scoped token at the destination, reconcile Model-versus-Kernel ownership, and prove a successor-owned publish |
| [`szl-cookbook`](https://github.com/szl-holdings/szl-cookbook) | [`docs-site/docs/cookbook/recipes`](https://github.com/szl-holdings/docs-site/tree/main/docs/cookbook/recipes) for presentation | Retain active while it owns runnable TypeScript, Lean, payloads, operator tooling, workflows, and the live Pages carousel; migrate those surfaces and inbound A11oy references before reconsidering archive |
| [`szl-governed-norm`](https://github.com/szl-holdings/szl-governed-norm) | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Fold the later non-finite receipt-digest hardening and compatibility namespace, then reconcile Forge, Model, Kernel, and registry revision pins |
| [`szl-trust`](https://github.com/szl-holdings/szl-trust) | [`docs-site/docs/trust`](https://github.com/szl-holdings/docs-site/tree/main/docs/trust) | Migrate the offline verifier, tests, and scoped CC-BY license/notice; correct migration claims and verify the canonical [docs site](https://holdings.a-11-oy.com/docs-site/) before archive |

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
