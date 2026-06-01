# ONCALL.md — SZL Holdings Operational On-Call

**Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17**
**Updated:** 2026-06-02

---

## Current On-Call

**Primary:** Founder — Stephen Lutar
**Contact:** stephenlutar2@gmail.com
**GitHub:** [@stephenlutar2](https://github.com/stephenlutar2)

There is currently one on-call engineer. As the team grows, this document will be updated to reflect a rotation.

---

## Escalation Path

```
1. Incident detected (alert, user report, automated healthz failure)
         ↓
2. Primary oncall: stephenlutar2@gmail.com
         ↓ (if no response within SLA)
3. Automated escalation via rosie's Chaski endpoint:
   POST https://SZLHOLDINGS-rosie.hf.space/api/rosie/v2/chaski/escalate
   Body: { "severity": "P1|P2|P3", "summary": "...", "ts": "ISO8601" }
   → Returns a signed escalation receipt (Wire D DSSE envelope)
```

---

## Response SLA

| Severity | Hours | Description |
|---|---|---|
| P1 — All flagships down | 4h business hours / 24h off-hours | Full service outage |
| P2 — Single flagship down | 4h business hours / 24h off-hours | Partial degradation |
| P3 — Non-critical | Next business day | UI issues, minor bugs |

**Honest caveat:** This is a pre-Series-A, founder-operated organization. Off-hours response may exceed 24h for P2/P3 incidents. P1 incidents will be addressed as quickly as possible regardless of time.

Business hours: Monday–Friday, 09:00–18:00 US Eastern.

---

## Status Page

Link to status page: [SZLHOLDINGS/status](https://github.com/szl-holdings/status) — pending deployment. Will publish HF Space availability and Λ-score history once live.

---

## Runbooks

Per-flagship operational runbooks are in [`platform/docs/runbooks/`](https://github.com/szl-holdings/platform/tree/main/docs/runbooks/):

- [`a11oy.md`](https://github.com/szl-holdings/platform/blob/main/docs/runbooks/a11oy.md) — Governance layer
- [`amaru.md`](https://github.com/szl-holdings/platform/blob/main/docs/runbooks/amaru.md) — Cortex memory
- [`sentra.md`](https://github.com/szl-holdings/platform/blob/main/docs/runbooks/sentra.md) — Immune system
- [`rosie.md`](https://github.com/szl-holdings/platform/blob/main/docs/runbooks/rosie.md) — Aide / operator console
- [`killinchu.md`](https://github.com/szl-holdings/platform/blob/main/docs/runbooks/killinchu.md) — Defense / counter-UAS

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
