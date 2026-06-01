# RESILIENCE_BUDGET — SLOs + Error Budgets + Burn-Rate Alarms

**Layer:** PURIQ v12 → `resilience_observability/`
**Author:** Yachay (SZL reliability agent), under CTO authority
**Date:** 2026-06-01
**Doctrine:** v12 (= v11 + PURIQ). v11 LOCKED numbers preserved. SLSA L1 (honest); Khipu
sig DSSE PLACEHOLDER.

> Service Level Objectives per flagship, the error budget each SLO implies, and the
> multi-window burn-rate alarms that page before the budget is gone. Honest math: an SLO
> is a promise we can keep, an error budget is permission to fail that much and no more.

---

## 1 — SLO targets (locked for this layer)

| Flagship | SLO (30-day availability) | Rationale | Class |
|---|---|---|---|
| **a11oy** | **99.9%** | orchestrator + LLM router — every flagship depends on it | critical |
| **amaru** | **99.5%** | cortex/memory — degradable (cache, keyword fallback) | standard |
| **sentra** | **99.5%** | immune/policy — degradable but gating-critical | standard |
| **killinchu** | **99.9%** | real-time / safety-critical drone ops | critical (real-time) |
| **rosie** | **99.5%** | companion/nervous — degradable (buffer + replay) | standard |

Supporting services (not in the task's named set, tracked for completeness):
**vessels** 99.5% (receipt ingest — degradable via local buffer + reconcile),
**lean-kernel** 99.0% (proof endpoint — non-customer-critical),
**anatomy-3d / uds-demo** 99.0% (static showcase).

**SLI definition (what counts as "good"):** a request is *good* if it returns a non-5xx
within its endpoint's latency objective **OR** returns a clearly-flagged honest degraded
response (`degraded:true`). A fabricated success is **not** good. An honest error counts as
*bad for availability* but *good for honesty* — we never trade truth for an SLO number.

For **killinchu (real-time)**, the SLI also includes a **safety availability** clause: the
safety system (halt/RTL on spoof/jam, D6/D7) must be available **100%** — a safety hold
firing is *expected behaviour*, not an SLO miss; a safety system that *fails to halt* is a
SEV-1 and is excluded from the standard availability budget (it is a hard-stop, not a
budgeted error).

---

## 2 — Error budget per SLO (30-day window)

Error budget = `(1 − SLO) × window`. Over a 30-day month (43,200 min):

| Flagship | SLO | Allowed downtime / 30d | Allowed bad-request fraction |
|---|---|---|---|
| a11oy | 99.9% | **~43.2 min** | 0.1% |
| killinchu | 99.9% | **~43.2 min** | 0.1% |
| amaru | 99.5% | **~216 min (3.6 h)** | 0.5% |
| sentra | 99.5% | **~216 min (3.6 h)** | 0.5% |
| rosie | 99.5% | **~216 min (3.6 h)** | 0.5% |

**Budget policy:**
- While budget remains → ship features, run chaos (chaos spends budget deliberately — it
  is budgeted under the experiment abort guard, `CHAOS_ENGINEERING_PLAN.md`).
- Budget exhausted → **feature freeze** on that flagship; reliability work only until the
  budget recovers in the rolling window. This is the SRE bargain, applied honestly.

---

## 3 — Multi-window, multi-burn-rate alarms

A burn rate of `1×` consumes the entire 30-day budget in exactly 30 days. Faster burn =
sooner page. We use the standard two-window pairs (fast + slow) to page on real burn while
suppressing flutter (Google SRE workbook method).

| Burn rate | Budget consumed | Long window / short window | Severity | Meaning |
|---|---|---|---|---|
| **14.4×** | 2% of budget in 1h | 1h / 5m | **SEV-2** page | budget gone in ~2 days at this rate |
| **6×** | 5% in 6h | 6h / 30m | **SEV-3** page | budget gone in ~5 days |
| **3×** | 10% in 24h | 24h / 2h | SEV-3 ticket | budget gone in ~10 days |
| **1×** | baseline | 72h | SEV-4 info | on track to exactly meet SLO |

A burn-rate alarm fires only when **both** the long and short windows exceed the threshold
— the short window confirms the burn is *current* (not a stale spike), the long window
confirms it is *sustained*. This avoids paging on a 30-second blip while still catching a
real fast burn within minutes.

### Prometheus alarm sketch (a11oy, 14.4× fast burn)
```yaml
# error budget burn — a11oy fast burn (page SEV-2)
- alert: A11oyErrorBudgetFastBurn
  expr: |
    (
      (1 - (sum(rate(szl_requests_total{flagship="a11oy",status!~"5.."}[1h]))
            / sum(rate(szl_requests_total{flagship="a11oy"}[1h])))) > (14.4 * 0.001)
    )
    and
    (
      (1 - (sum(rate(szl_requests_total{flagship="a11oy",status!~"5.."}[5m]))
            / sum(rate(szl_requests_total{flagship="a11oy"}[5m])))) > (14.4 * 0.001)
    )
  for: 2m
  labels: { severity: "sev2", flagship: "a11oy" }
  annotations:
    summary: "a11oy burning error budget at >14.4x (1h+5m windows)"
    runbook: "INCIDENT_RESPONSE_RUNBOOK.md"
```
`0.001` is the a11oy budget fraction (1 − 0.999). For amaru/sentra/rosie substitute
`0.005`. killinchu uses `0.001` plus the separate safety-availability hard-stop rule.

---

## 4 — Latency objectives (per-endpoint, feeds the SLI)

| Endpoint | Objective (p99) | Notes |
|---|---|---|
| `/api/<space>/healthz` | < 300 ms | probe path |
| a11oy `/v1/router` (full tier) | < 8 s | LLM inference; T1/T0 fallback faster |
| `/v1/rag` | < 1.5 s | vector; keyword fallback faster |
| `/v1/brain/multi-jack` | < 5 s | fan-out |
| `/v1/lean-verify` | < 2 s | recompute Λ |
| `/v1/receipts/ingest` | < 500 ms | Khipu append |
| killinchu edge decision `P(x,t)` | < 250 ms | real-time; runs local, no cloud |

A request exceeding its p99 objective counts against the latency SLI even if it returns
200 — slow-but-successful is still a partial budget burn for latency-sensitive endpoints.

---

## 5 — Budget dashboard + governance

- A Grafana panel per flagship shows: budget remaining (%), current burn rate, projected
  exhaustion date. Driven by the same `szl_requests_total` series as the alarms.
- **Monthly review:** budgets reset on the rolling 30-day window; the resilience review
  reads the prior period's consumption + any feature freezes triggered.
- **Chaos accounting:** budget intentionally spent by chaos experiments is tagged
  `chaos:true` and reported separately, so a deliberate chaos burn is not confused with a
  real-incident burn.
- Every budget-policy action (freeze imposed / lifted) emits a Khipu
  `szl.budget_action.receipt/v1` receipt — auditable, like everything else.

```jsonc
// szl.budget_action.receipt/v1
{
  "schema": "szl.budget_action.receipt/v1",
  "flagship": "amaru",
  "action": "feature_freeze_imposed",   // imposed | lifted
  "reason": "30d error budget exhausted (consumed 100%)",
  "budget_remaining_pct": 0.0,
  "window": "30d",
  "at": "2026-06-01T18:40:00Z",
  "doctrine": "v12",
  "dsse": { "sig": "PLACEHOLDER — Sigstore CI not wired", "keyid": "PENDING" }
}
```

---

## 6 — Honesty notes (Zero-Bandaid)

- SLO numbers are **targets**, measured against live `szl_up`/`szl_requests_total`; the
  dashboard shows actual vs target. We do not retroactively claim a met SLO.
- **Honest errors count against availability** — we never inflate the SLI by dressing an
  error as a success. Truth beats the number.
- killinchu **safety availability is 100% and is not budgeted** — a safety hold is correct
  behaviour; a safety failure is SEV-1, not a budget line.
- All burn-rate math is the standard multi-window method; the thresholds above are the
  conventional 14.4×/6×/3× pairs, applied to each flagship's real budget fraction.
- v11 LOCKED numbers untouched; this layer is ADDITIVE.

---

*Cited internal sources:* `OBSERVABILITY_DASHBOARD.md` (`szl_requests_total`, `szl_up`),
`INCIDENT_RESPONSE_RUNBOOK.md` (severity → paging), `CHAOS_ENGINEERING_PLAN.md` (budgeted
chaos burn), `DEGRADATION_PATHS.md` (honest degraded responses counted in the SLI),
`killinchu/architecture/KILLINCHU_FULL_STACK_ARCHITECTURE.md` (edge real-time `P(x,t)`).

— Yachay (SZL reliability agent), under CTO authority — Doctrine v12, additive over v11 LOCKED.
