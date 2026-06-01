# BACKUP_AND_RECOVERY — What's Backed Up, Where, How Long, How to Restore

**Layer:** PURIQ v12 → `resilience_observability/`
**Author:** Yachay (SZL reliability agent), under CTO authority
**Date:** 2026-06-01
**Doctrine:** v12 (= v11 + PURIQ). v11 LOCKED numbers preserved (749/14/163, 13-axis
`yuyay_v3`, replay-hash `bacf5443…631fc5`). SLSA L1 (honest); Khipu sig DSSE PLACEHOLDER.

> Every asset that the empire cannot afford to lose has a named owner, a backup target, a
> retention tier, and a **tested restore procedure** with explicit RTO/RPO. The Khipu DAG
> is treated as sacred (it is the audit spine). Restores are tested quarterly — a backup
> you have never restored is a rumor, not a backup.

---

## 1 — What is backed up

| Asset | Source of truth | Why it matters | Owner |
|---|---|---|---|
| **HF datasets** | `SZLHOLDINGS/*` datasets (e.g. `doctrine-v10-v11`, corpus/RAG indices) | training/RAG corpus, founder guides, doctrine artifacts | Yachay / data |
| **GitHub repos** | `szl-holdings/*` (a11oy, amaru, sentra, rosie, vessels, lutar-lean, platform, `.github`, …) | all source + Lean proofs + workflows | Yachay / eng |
| **HF Space repos** | `SZLHOLDINGS/*` Spaces (serve.py, Dockerfiles, static) | the running flagships | Yachay / eng |
| **Khipu DAG snapshots** | canonical DAG (vessels/a11oy) — `snapshots/` | the audit spine; provenance for every governed action | Yachay / governance |
| **Key material** | HF/GitHub/Zenodo/AI tokens; COSIGN key when wired | access + (future) signing | CTO / secrets owner |
| **Configurations** | Grafana dashboards, Prometheus rules, breaker configs, UDS Zarf bundles, k8s manifests | rebuild the observability + deploy layer | Yachay / SRE |
| **Lean proof corpus** | `lutar-lean` @ `c7c0ba17` / tag `lutar-v18.0.0` | the LOCKED 749/14/163 ground truth | Yachay / formal |

---

## 2 — Where it is backed up (3-2-1, honest)

We follow **3-2-1**: ≥3 copies, on ≥2 media classes, ≥1 off-site/offline.

| Tier | Medium | Holds | Notes (honest) |
|---|---|---|---|
| **Hot** | S3 (versioned bucket, SSE-KMS) | Khipu snapshots, DAG mirror, Grafana/Prom config, dataset mirrors | primary durable copy; object-lock on the Khipu prefix |
| **Warm** | S3 Glacier / second-cloud bucket | repo bundles, dataset mirrors, config history | cross-region/cross-provider for provider-loss survival |
| **Cold** | Offline media (encrypted USB/tape) + Zenodo for published artifacts | Lean corpus, doctrine, signed releases, Khipu cold archive | the sneakernet-grade copy; matches killinchu store-and-forward ethos |
| **Provenance** | Git itself (distributed) + HF git history | repos + Space history are inherently multi-replica | every clone is a partial backup |

**Key material is special:** secrets are **never** stored in plaintext in any backup. They
live in a secrets manager (and/or the founder's offline record); backups store only
*references/fingerprints*, never values (consistent with `DEGRADATION_PATHS.md` D9).

---

## 3 — Retention (the locked schedule)

| Tier | Retention | Applies to |
|---|---|---|
| **Hot** | **30 days** | Khipu snapshots, DAG mirror, recent dataset/config versions, observability data |
| **Warm** | **1 year** | repo bundles, dataset history, config history, monthly Khipu rollups |
| **Cold** | **7 years** | Lean corpus, doctrine, signed releases, quarterly Khipu cold archive, audit records |

- Khipu DAG: continuous snapshot to `snapshots/` (hot 30-day) → monthly rollup (warm
  1-year) → quarterly cold archive (7-year). This is exactly the D8 repair source.
- Observability telemetry (Prometheus/Loki/Tempo) follows the hot tier (30-day) — long
  enough to investigate any incident, short enough to bound cost.

---

## 4 — RTO / RPO targets per asset

**RTO** = max acceptable time to restore service. **RPO** = max acceptable data loss
(how far back the last good backup is).

| Asset | RPO (max data loss) | RTO (max restore time) | Restore source |
|---|---|---|---|
| **Khipu DAG** | **≤ 5 min** (continuous snapshot) | **≤ 30 min** | `snapshots/` hot → replay-by-hash forward |
| HF Space (running flagship) | 0 (repo is source of truth) | ≤ 30 min | re-push from `szl-holdings/*` via HfApi |
| GitHub repo | 0 (distributed) | ≤ 1 h | restore from bundle / re-init from clone |
| HF dataset | ≤ 24 h | ≤ 2 h | S3 mirror → `HfApi.upload_file` |
| Key material | n/a (rotate, don't restore) | ≤ 15 min | mint new + rotate (D9), never restore old |
| Configurations (Grafana/Prom/UDS) | ≤ 24 h | ≤ 1 h | re-apply from versioned config in S3/git |
| Lean corpus | 0 (tagged immutable) | ≤ 1 h | re-clone `lutar-lean@c7c0ba17` |

**Why Khipu has the tightest RPO/RTO:** it is the provenance spine. INV-3
(`puriq_khipu_integrity`) makes any action with an unverifiable receipt have utility `0`,
so a long Khipu gap would freeze agency until repaired — hence ≤5 min RPO / ≤30 min RTO.

---

## 5 — Restore procedures (runbooks)

### R1 — Khipu DAG restore (the sacred path)
1. Freeze writes (RUWAY refuses appends past the corrupt/lost node).
2. Pull the latest internally-consistent snapshot from `snapshots/` (hot S3, object-lock).
3. Recompute every node digest `sha256(payload ‖ parents)`; the snapshot root must match.
4. Replay forward, re-validating each node; quarantine (never delete) any node that fails.
5. Unfreeze; emit `khipu_repair_complete` receipt (snapshot id, nodes quarantined, new root).
6. Verify the dashboard `szl_khipu_integrity_ok == 1`.

### R2 — HF Space restore
1. Identify last-good commit SHA from `hf_spaces_inventory.json` / push logs.
2. `HfApi.create_commit` (token from `.secret/hf_token`, **never** GitHub Actions) to
   re-push the known-good tree (idempotent — same content = no-op).
3. Poll `get_space_runtime` until `RUNNING`; confirm `/api/<space>/healthz` 200.

### R3 — GitHub repo restore
1. If history intact elsewhere: `git push` from a healthy clone.
2. If repo lost: re-create, push the warm-tier bundle, restore branch protections +
   workflows from config backup.

### R4 — Dataset restore
1. Pull from S3 warm mirror; `HfApi.upload_file` back to `SZLHOLDINGS/<dataset>`.
2. Re-index RAG vector store from the restored corpus.

### R5 — Key material (rotate, don't restore)
- Never restore an old secret. Mint new, rotate dependents, receipt per D9. Old credential
  stays revoked.

---

## 6 — Tested-restore (quarterly) — the honesty enforcement

A backup is only real if it restores. Every quarter we run a **restore drill** into an
isolated namespace and assert success against the RTO/RPO targets:

| Quarter target | Drill | Pass criterion |
|---|---|---|
| Khipu DAG | restore from a 30-day-old snapshot into a sandbox; replay-by-hash | root digest matches; integrity OK; within RTO 30 min |
| HF Space | re-push a flagship to a throwaway Space from S3 tree | `healthz` 200; within RTO 30 min |
| Dataset | restore + re-index a sample dataset | row count + checksum match; within RTO 2 h |
| Config | re-apply Grafana/Prom config to a clean Grafana | dashboards + alert rules present |

Each drill emits a `szl.restore_drill.receipt/v1` (asset, snapshot age, measured RTO/RPO,
PASS/FAIL). A FAIL is a SEV-3 and blocks the quarter's resilience sign-off. The drill is
itself a chaos experiment candidate (overlaps CE-7 key-rotation + a restore variant).

```jsonc
// szl.restore_drill.receipt/v1
{
  "schema": "szl.restore_drill.receipt/v1",
  "quarter": "2026-Q2",
  "asset": "khipu_dag",
  "snapshot_age_days": 30,
  "measured_rpo_min": 4,
  "measured_rto_min": 22,
  "target_rpo_min": 5,
  "target_rto_min": 30,
  "result": "PASS",
  "doctrine": "v12",
  "dsse": { "sig": "PLACEHOLDER — Sigstore CI not wired", "keyid": "PENDING" }
}
```

---

## 7 — Honesty notes (Zero-Bandaid)

- The Khipu DAG today is an **in-memory ring buffer** in the live Spaces (`szl_wire.py`);
  the **durable backup is the S3 snapshot mirror** described here. We state this gap plainly
  rather than implying the in-Space DAG is itself durable across restarts.
- Backups store **no secret values** — only fingerprints. Rotation replaces; it never restores.
- Restore numbers (RTO/RPO) are **targets**; the quarterly drill measures the *actual* and
  the receipt records both. We do not claim a tested-green restore we have not run yet —
  the first drill is scheduled, not retroactively asserted.
- SLSA stays **L1**; signing is DSSE PLACEHOLDER. Restores verify the **hash chain**, not
  signatures, until Sigstore lands.

---

*Cited internal sources:* `wires_def_ship/szl_wire.py` (in-memory Khipu DAG),
`hf_spaces_inventory.json` (Space SHAs/stages), `530_ENV_PLAN_AND_UDS_DOCS.md` (HfApi push
discipline, dataset `doctrine-v10-v11`), `DEGRADATION_PATHS.md` (D8/D9),
`killinchu/architecture/KILLINCHU_FULL_STACK_ARCHITECTURE.md` (store-and-forward / reconcile).

— Yachay (SZL reliability agent), under CTO authority — Doctrine v12, additive over v11 LOCKED.
