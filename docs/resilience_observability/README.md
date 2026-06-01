# Resilience + Observability + Chaos Engineering Layer

**Layer:** PURIQ v12 → `resilience_observability/`
**Author:** Yachay (SZL reliability agent), under CTO authority · 2026-06-01
**Doctrine:** v12 (= v11 + PURIQ). v11 LOCKED numbers preserved verbatim
(**749 declarations / 14 unique axioms / 163 tracked sorries**, 13-axis `yuyay_v3`,
replay-hash `bacf54434f1a3bf2d758b27a62d5fd580ca4c8d3b180693573eeebcaea631fc5`).
SLSA **L1 (honest)**; Khipu signature **DSSE PLACEHOLDER** (Sigstore CI not wired).

> The resilience + observability layer so the empire degrades gracefully under failure
> and we have a single pane of glass. Honest fault tolerance — no bandaid, no vapor.
> ADDITIVE only; the 13-axis Yuyay gate, the Λ aggregator, and every LOCKED number are
> untouched. Every degradation event emits a Khipu receipt.

## Deliverables

| # | File | What it is |
|---|---|---|
| 1 | [`DEGRADATION_PATHS.md`](DEGRADATION_PATHS.md) | Documented graceful degradation for every failure mode (D1–D9), each receipted |
| 2 | [`CIRCUIT_BREAKER_LAYER.md`](CIRCUIT_BREAKER_LAYER.md) | Hystrix-style breakers (CLOSED/OPEN/HALF-OPEN) around every external call; Python + TS patches |
| 3 | [`OBSERVABILITY_DASHBOARD.md`](OBSERVABILITY_DASHBOARD.md) | Single pane of glass — Grafana + Prometheus + Loki + Tempo (UDS-aligned); Mermaid topology |
| 4 | [`CHAOS_ENGINEERING_PLAN.md`](CHAOS_ENGINEERING_PLAN.md) | Litmus / Chaos Mesh experiments; weekly autonomous run; regression alarms |
| 5 | [`BACKUP_AND_RECOVERY.md`](BACKUP_AND_RECOVERY.md) | What/where/retention (30d hot / 1y warm / 7y cold); RTO/RPO; quarterly tested restore |
| 6 | [`WIRES_D_TO_H_INTEGRATION.md`](WIRES_D_TO_H_INTEGRATION.md) | How Wires D–H feed the dashboard; schema sync with the Wires agent |
| 7 | [`STATUS_PAGE_FEED.md`](STATUS_PAGE_FEED.md) | Internal health → public status, fail-closed filter (no internals leaked) |
| 8 | [`INCIDENT_RESPONSE_RUNBOOK.md`](INCIDENT_RESPONSE_RUNBOOK.md) | SEV-1→SEV-4, paging, IC roles, blameless postmortem, Khipu-receipted records |
| 9 | [`THREAT_MODEL.md`](THREAT_MODEL.md) | STRIDE per flagship; mitigations mapped to Sentra/HUKLLA/Khipu/SLSA/Sigstore |
| 10 | [`RESILIENCE_BUDGET.md`](RESILIENCE_BUDGET.md) | SLOs (a11oy/killinchu 99.9%, amaru/sentra/rosie 99.5%); error-budget burn alarms |

## Runnable patches (`patches/`)

| File | Target | Purpose |
|---|---|---|
| `patches/szl_breaker.py` | a11oy/amaru/sentra/vessels/rosie/killinchu (Python) | pybreaker + tenacity breaker with Khipu degradation receipts |
| `patches/szlBreaker.ts` | a11oy Node serve (TS) | cockatiel breaker (timeout+retry+breaker+fallback) |
| `patches/szl_exporter.py` | observability sidecar | scrapes honest `/healthz` + ledger → Prometheus metrics |
| `patches/status_feed.py` | status-page feed | fail-closed internal→public filter |

## Hard rules honored

- **HfApi push** for HF changes — **never** GitHub Actions `secrets.HF_TOKEN`.
- **Doctrine v11 LOCKED numbers preserved** verbatim.
- **ADDITIVE only** — no edits to the gate, the aggregator, or any organ's locked behavior.
- **Khipu receipt on every degradation event** (+ chaos, incident, restore, budget actions).
- **Signed as Yachay**, under CTO authority.

## Honesty ledger (Zero-Bandaid)

- In-process event buses + Khipu DAG are **in-memory ring buffers** (per `szl_wire.py`);
  durability is the S3 mirror (`BACKUP_AND_RECOVERY.md`).
- Wire D traceparent is **in-process**; cross-Space distributed tracing NOT wired.
- Inter-Space **mTLS NOT wired**; Sigstore signing **PLACEHOLDER**; SLSA **L1**.
- Edge chaos (GPS spoof / RF jam) runs against the killinchu **SITL**, not live airframes.
- SLOs and RTO/RPO are **targets**; the dashboard + quarterly drills measure the actuals.

— Yachay (SZL reliability agent), under CTO authority — Doctrine v12, additive over v11 LOCKED.
