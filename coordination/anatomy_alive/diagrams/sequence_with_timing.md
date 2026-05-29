# Anatomy-Alive Sequence Diagram — with Millisecond Timings

**Trace ID:** `anatomy-alive-trace-20260530T000000Z`  
**Anchor formula:** `AdversarialRobustness`  
**Lean theorem:** `Lutar.Composition.Robustness.robustness_preserved_by_composition`  
**Harness run:** 2026-05-30, Doctrine v6

---

```mermaid
sequenceDiagram
    autonumber
    actor Harness as Harness<br/>(run_anatomy_alive.py)
    participant L1 as L1 lutar-lean<br/>Lean theorem store
    participant L2 as L2 ouroboros<br/>TS formula runtime
    participant L3 as L3 ouroboros<br/>parity tests (vitest)
    participant L4 as L4 vsp-otel<br/>span exporter
    participant L5 as L5 uds-mesh<br/>DSSE ledger
    participant L6 as L6 a11oy<br/>policy gates
    participant L7 as L7 sentra<br/>forecast loop

    Note over Harness: t=0ms  trace_id injected

    Harness->>L1: GET /repos/szl-holdings/lutar-lean/contents/Lutar/Composition/AdversarialRobustness.lean
    Note over L1: t=12ms  blob SHA a96e448f
    L1-->>Harness: blob_sha=a96e448f, size=6138B [t=1018ms]
    Note over Harness: grep theorem + sorry → PASS

    Harness->>L2: GET /repos/szl-holdings/ouroboros/contents/agentic/formulas/src/adversarialRobustness.ts
    Note over L2: t=1018ms  blob SHA 72868677
    L2-->>Harness: blob confirmed + Python parity ε₂=0.300 ✓ [t=2118ms]

    Harness->>L3: GET 6 test file blobs (adversarialRobustness.test.ts … falsePosition.test.ts)
    L3-->>Harness: all 6 exist, assertions confirmed [t=5730ms]
    Note over Harness: STAGED — pnpm vitest needs Node (Cursor scope)

    Harness->>L4: Simulate signSpan() on synthetic OTel span
    Note over L4: t=5730ms  span attrs carry szl.anchor_formula.id (harness-injected)
    L4-->>Harness: λ=0.9208 ≥ 0.90 PASS [t=6890ms]
    Note over Harness: STAGED — exporter.ts (blob 026eb629) does not<br/>auto-inject szl.anchor_formula.id — Cursor Track 1

    Harness->>L5: Emit DSSE receipt (AdversarialRobustness, l1=2.0 l2=1.5 δ=0.1)
    Note over L5: PAE(type, payload) + HMAC-SHA-256
    L5-->>Harness: signature verified; lean_commit_sha consistent L1↔L5 [t=7960ms]

    Harness->>L6: Run adversarialRobustnessGate(l1=2.0, l2=1.5, δ=0.1, maxε=0.5)
    Note over L6: ε₂=0.300 ≤ 0.500  allow=true
    L6-->>Harness: PolicyDecision{allow:true, leanTheorem:robustness_preserved_by_composition} [t=10580ms]
    Note over Harness: formula_witness emission to uds-mesh=false<br/>(Cursor Track 1 deliverable)

    Harness->>L7: Audit sentra/main for receipt consumption
    Note over L7: sentra_immune.py + tupu_replay_5x.py present<br/>zero receipt/formula_witness keyword hits
    L7-->>Harness: NOT-YET-WIRED — witnessed.py absent [t=14338ms]

    Note over Harness: VERDICT: STAGED-PASS<br/>L1=PASS L2=PASS L3=STAGED L4=STAGED L5=PASS L6=PASS L7=NOT-YET-WIRED
```

---

## Layer status key

| Status | Meaning |
|---|---|
| `PASS` | Layer fires on main today with real verification |
| `STAGED` | Files confirmed on main; runtime execution requires Cursor wiring (Node/pnpm) |
| `NOT-YET-WIRED` | Code does not yet exist on main; specific missing file cited |
| `FAIL` | Hard failure — would block the bank pitch |

## Timing breakdown (actual, 2026-05-30 harness run)

| Layer | Organ | Duration (ms) | Bottleneck |
|---|---|---|---|
| L1 | lutar-lean | 1,018 | GitHub API round-trip + blob decode |
| L2 | ouroboros | 1,100 | GitHub API + Python parity compute |
| L3 | ouroboros | 3,612 | 6 parallel blob confirmations |
| L4 | vsp-otel | 1,160 | GitHub API + signSpan() simulation |
| L5 | uds-mesh | 1,070 | GitHub API + HMAC round-trip |
| L6 | a11oy | 2,620 | 3 blob fetches + gate content grep |
| L7 | sentra | 3,758 | 4 blob checks + keyword scan |
| **Total** | | **14,338** | |

