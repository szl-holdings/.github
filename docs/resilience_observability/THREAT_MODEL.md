# THREAT_MODEL — STRIDE per Flagship

**Layer:** PURIQ v12 → `resilience_observability/`
**Author:** Yachay (SZL reliability agent), under CTO authority
**Date:** 2026-06-01
**Doctrine:** v12 (= v11 + PURIQ). v11 LOCKED numbers preserved (749/14/163, 13-axis
`yuyay_v3`, replay-hash `bacf5443…631fc5`). SLSA L1 (honest); Khipu sig DSSE PLACEHOLDER.
**Method:** STRIDE (Spoofing, Tampering, Repudiation, Information disclosure, Denial of
service, Elevation of privilege), mapped to existing organs.

> A STRIDE threat model for every flagship, with each mitigation mapped to an **organ we
> actually have** — Sentra (immune/policy), HUKLLA (tripwires T01–T10), Khipu (receipt
> DAG), SLSA (build provenance, L1 honest), Sigstore (signing — DSSE PLACEHOLDER until
> wired). Where a mitigation is not yet wired, it is marked honestly, not claimed.

---

## 0 — Organ → mitigation legend

| Organ | Role as a control |
|---|---|
| **Sentra** | immune/policy gate — verdicts, signature checks, MB guard (18 SLOC, 6 sigs + 1 MB guard) |
| **HUKLLA** | 10 tripwires T01–T10; T10 = absorbing STOP; soft-then-hard halt via `exp(−β·HUKLLA)` |
| **Khipu** | append-only Merkle receipt DAG (RUWAY = only writer); hash-chain integrity |
| **Yuyay** | 13-axis conjunctive gate; `Yuyay₁₃=0 ⇒ U=0` (no compensation) |
| **SLSA** | build provenance — **L1 (honest)**; "L3" is BANNED |
| **Sigstore** | artifact signing — **DSSE PLACEHOLDER** (not wired into CI yet) |
| **Breakers** | circuit breakers (`CIRCUIT_BREAKER_LAYER.md`) — DoS containment |

**Cross-cutting controls (apply to all flagships):**
- Every state-changing action is **Khipu-receipted** (Repudiation defense).
- Every action passes the **13-axis Yuyay gate** (admission control).
- Every external call is **breaker-wrapped** (DoS containment + degradation).
- HF changes via **HfApi token** only — **never** GitHub Actions `secrets.HF_TOKEN`
  (reduces secret-exposure surface).

---

## 1 — a11oy (orchestrator / LLM router / gate)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** Spoofing | forged request impersonating an organ or operator | Wire-D traceparent + per-Space `x-szl-space`; Sentra verdict on inbound; (future) mTLS between Spaces | mTLS NOT wired (HF Spaces are public HTTPS) — honest gap |
| **T** Tampering | altered router decision / poisoned prompt to bypass gate | Yuyay 13-axis conjunctive gate (no compensation); HUKLLA T-checks; router removes HUKLLA-tripped models from `𝒜` before argmax | live (in-process) |
| **R** Repudiation | "the router never made that call" | Khipu gate-decision receipt per decision (Wire F) | live; sig PLACEHOLDER (hash-chain only) |
| **I** Info disclosure | leak of provider names / prompts / keys | status-page filter (`STATUS_PAGE_FEED.md`) hides providers; secrets in manager, not code; license_class receipted not exposed | live |
| **D** DoS | provider exhaustion / request flood collapses router | per-provider breakers + D2 fallback (T0/T1/honest-error); rate limits | live |
| **E** EoP | low-trust action selected as if high-trust | `P(x,t)` = Λ·Yuyay·exp(−βHUKLLA)·∏Khipu; degraded factor ∈ [0,1] cannot inflate utility | live (Lean obligations sorry-tagged) |

## 2 — amaru (cortex / memory)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | forged cortex event injected via Wire E | event carries source/sink + traceparent; Sentra verdict; in-memory bus is process-local | live; no external broker (honest) |
| **T** | memory poisoning of RAG corpus | Khipu provenance on ingested chunks; Yuyay gate on writes; vector store integrity check | partial — corpus provenance receipts planned |
| **R** | denial of a stored memory | Khipu receipt on memory writes | live; sig PLACEHOLDER |
| **I** | leak of stored cortex contents | access via gated endpoints; status filter hides internals | live |
| **D** | cortex-subscribe SSE flood | `ws_stream`/SSE bounded ring buffer; breaker | live (bounded buffer) |
| **E** | unauthorized cortex write | RUWAY-only write path; Yuyay gate | live |

## 3 — sentra (immune / policy)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | spoofed verdict source | Sentra signature checks (6 sigs); traceparent | live |
| **T** | tampered policy bundle | Sentra MB guard + signature verify; SLSA provenance (L1) | L1 honest; Sigstore signing PLACEHOLDER |
| **R** | "no verdict was issued" | Khipu verdict receipt | live; sig PLACEHOLDER |
| **I** | leak of policy internals | filter hides tripwire mechanics from public | live |
| **D** | verdict-endpoint flood | breaker + bounded compute | live |
| **E** | bypassing the immune gate | Yuyay conjunctive AND + HUKLLA; gate cannot be skipped (U=0 if ungated) | live (obligations sorry-tagged) |

## 4 — vessels (receipt / Khipu DAG)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | forged receipt ingested | ingest validates required fields; traceparent; (future) DSSE sig | sig PLACEHOLDER |
| **T** | **Khipu DAG tampering** (the crown jewel) | Merkle hash chain — any altered node breaks `sha256(payload‖parents)`; integrity verifier (Row 5 dashboard); D8 repair from snapshots | live (hash-chain); INV-3 makes tampered node → U=0 |
| **R** | repudiation of an action | the DAG *is* the non-repudiation record (append-only, RUWAY-only) | live; hash-chain (sig PLACEHOLDER) |
| **I** | leak of receipt contents / digests | digests never published (status filter); ledger behind gated endpoint | live |
| **D** | ingest flood bloats DAG | rate-limited ingest; sampled degradation receipts; breaker | live |
| **E** | non-RUWAY writer appends | RUWAY is the **only** authorized writer (v11 §4) | live by design |

## 5 — rosie (nervous / companion / WS)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | spoofed brain-jack (Wire G) | socket status + traceparent; Sentra verdict on jack | live |
| **T** | tampered live event stream | Khipu replay on reconnect (D5) is authoritative; buffered events verified against DAG | live |
| **R** | denial of a companion action | Khipu receipt | live; sig PLACEHOLDER |
| **I** | leak via WS to wrong client | per-client buffer keyed by ack seq; gated | live |
| **D** | WS connection exhaustion | bounded buffers + reconnect backoff + breaker | live |
| **E** | privilege via companion to control plane | companion is read/advise; state changes go through a11oy gate | live by design |

## 6 — killinchu (drone edge) — the highest-stakes flagship

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | **GPS spoofing** | INS innovation residual + RAIM + CN0 detection → INS-only + halt + RTL (D6); HUKLLA spoof tripwire | live in SITL; honest about INS drift |
| **S** | RemoteID / MAVLink identity spoof | MAVLink/RemoteID validation (`killinchu/cuas/MAVLINK_REMOTEID_DEEPDIVE.md`); Sentra verdict | per cuas analysis |
| **T** | firmware / OTA tamper | secure OTA + tamper detection (`killinchu/twin/SECURE_OTA.md`, `TAMPER_HACK_DETECTION.md`); SLSA L1 | L1 honest; signing PLACEHOLDER |
| **T** | local Khipu chain tamper at edge | content-addressed local chain; Merkle reconcile to canonical DAG (broken chain rejected) | live (hash-chain) |
| **R** | "the drone never did X" | local Khipu receipts reconcile by Merkle proof on reconnect | live |
| **I** | telemetry/video interception over backhaul | encrypted store-and-forward (D7); contested-RF assumption baked in | live (encryption at rest/transit) |
| **D** | **RF jam** of Starlink/LTE | mesh-LTE → store-and-forward → sneakernet (D7); edge runs fully local (no cloud dependency) | live by design |
| **E** | hijack of flight control | `P(x,t)` geofence factor G(a) + `‖u‖≤u_max` MAVLink clamp; 2-person Yuyay-gated state-changing ops | live (obligations sorry-tagged) |

## 7 — lean-kernel + anatomy-3d / uds-demo (static + proof)

| STRIDE | Threat | Mitigation (organ) | Honest status |
|---|---|---|---|
| **S** | spoofed proof result | lean-kernel reports its actual build (`repo_sha`, toolchain); dashboard shows LOCKED vs live | live (honest drift surfaced) |
| **T** | tampered proof corpus | git history + tagged `c7c0ba17`; re-clone restore (R-Lean) | live |
| **R** | denial of a verify result | verify responses are deterministic + recomputable (`/api/lean/verify`) | live |
| **I** | n/a (proofs are public) | — | n/a |
| **D** | verify-endpoint flood | breaker + cached build result | live |
| **E** | claiming "SLSA L3" / proven-when-sorry | **BANNED**; honesty rules enforce L1 + sorry-tagging | live by doctrine |

---

## 8 — Top risks + priority mitigations (honest triage)

| Rank | Risk | Why top | Mitigation priority |
|---|---|---|---|
| 1 | **Khipu DAG tampering / corruption** | it is the audit spine; INV-3 ties all agency to it | hash-chain (live) + D8 repair + **wire Sigstore signing** (currently PLACEHOLDER) |
| 2 | **GPS spoof / flight-control hijack (killinchu)** | human-safety + physical harm | D6 INS/halt/RTL (live SITL) + 2-person gate + hardware redundancy |
| 3 | **Secret/token leak** | broad blast radius | secrets manager + scanning + D9 rotation + HfApi-only (never CI secret) |
| 4 | **All-LLM DoS** | customer-facing | per-provider breakers + D2 fallback (live) |
| 5 | **Spoofing between Spaces** | no mTLS yet | **honest gap** — wire mTLS / signed inter-Space tokens |

**Honest gaps stated plainly:** (a) inter-Space **mTLS is not wired** (HF Spaces are
public HTTPS endpoints); (b) **Sigstore signing is PLACEHOLDER** (DSSE), so non-repudiation
is hash-chain not cryptographic-signature; (c) SLSA is **L1**. These are the next security
investments; we do not claim them done.

---

*Cited internal sources:* `puriq/doctrine/PURIQ_DOCTRINE_v12.md` (organs, LOCKED numbers,
honesty rules), `wires_def_ship/szl_wire.py` (Khipu DAG, traceparent, RUWAY),
`killinchu/cuas/MAVLINK_REMOTEID_DEEPDIVE.md`, `killinchu/twin/{SECURE_OTA,TAMPER_HACK_DETECTION}.md`,
`killinchu/satellites/STARLINK_HONEST_TRUTH.md`, `DEGRADATION_PATHS.md`,
`CIRCUIT_BREAKER_LAYER.md`, `STATUS_PAGE_FEED.md`.

— Yachay (SZL reliability agent), under CTO authority — Doctrine v12, additive over v11 LOCKED.
