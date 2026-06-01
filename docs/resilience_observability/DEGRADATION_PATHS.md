# DEGRADATION_PATHS — Honest Graceful Degradation per Failure Mode

**Layer:** PURIQ v12 → `resilience_observability/`
**Author:** Yachay (SZL reliability agent), under CTO authority
**Date:** 2026-06-01
**Doctrine:** v12 (= v11 + PURIQ). v11 LOCKED numbers preserved verbatim:
**749 declarations / 14 unique axioms / 163 tracked sorries**, 13-axis `yuyay_v3`,
replay-hash `bacf54434f1a3bf2d758b27a62d5fd580ca4c8d3b180693573eeebcaea631fc5`.
SLSA **L1 (honest)**; Khipu signature is **DSSE PLACEHOLDER** until Sigstore lands.

> **Zero-Bandaid Law.** Every degradation path below is *honest*: it tells the user
> the truth about what is reduced, never fakes a healthy response, and emits a Khipu
> receipt for the degradation event (Doctrine v12 §5). "Graceful" means *the empire
> keeps the part of its promise it can still keep, and says clearly which part it cannot.*

---

## 0 — The degradation contract (load-bearing rule)

Every degraded response carries three honest signals so neither a human nor a sibling
organ is fooled into trusting reduced output as full output:

1. **`x-szl-degraded: true`** response header + a `degraded` block in the JSON body
   naming the failure mode and the fallback tier actually served.
2. **A degradation badge** on every HTML surface (a small banner, never hidden) reading
   e.g. *"DEGRADED — vector search unavailable, serving keyword fallback."*
3. **A Khipu receipt** (`schema: szl.degradation.receipt/v1`) appended to the canonical
   Khipu DAG via RUWAY (the only authorized writer, v11 §4), so the event is auditable.

Degradation **never** raises the Puriq utility `U(a∣x)` of an action: a degraded organ
factor stays in `[0,1]` (the `puriq_organ_factor_preserves_envelope` contract), so a
degraded path can only ever *lower* selection confidence, never inflate it.

```jsonc
// szl.degradation.receipt/v1  (appended to canonical Khipu DAG)
{
  "schema": "szl.degradation.receipt/v1",
  "event_id": "deg-2026-06-01T18:22:04Z-a11oy-router-rl",
  "flagship": "a11oy",
  "failure_mode": "llm_all_providers_rate_limited",
  "detected_at": "2026-06-01T18:22:04Z",
  "fallback_tier_served": "T0_cache",
  "user_visible": true,            // badge + header shown
  "honest_error_returned": false,  // true only when no fallback could serve
  "circuit": "llm_router",         // matches CIRCUIT_BREAKER_LAYER.md breaker name
  "breaker_state": "OPEN",
  "traceparent": "00-<32hex>-<16hex>-01",
  "doctrine": "v12",
  "dsse": { "sig": "PLACEHOLDER — Sigstore CI not wired", "keyid": "PENDING" }
}
```

---

## 1 — Failure-mode → degradation table (master)

| # | Failure mode | Affected flagship(s) | Degradation served | Honest signal | Khipu event |
|---|---|---|---|---|---|
| D1 | **HF Space down** (build/OOM/restart) | any Space | static fallback page + cached last-known-good JSON | banner: "Space restarting; showing cached snapshot from `<ts>`" | `space_down` |
| D2 | **LLM router — all providers rate-limited** | a11oy `/v1/router`, every flagship that calls it | T0 cache hit → T1 small local model → honest error | `degraded.tier` field | `llm_all_providers_rate_limited` |
| D3 | **HfApi push failing** | ship pipeline | local queue + exponential-backoff retry + alarm | ship log line + page | `hfapi_push_failed` |
| D4 | **Vector DB unavailable** | a11oy/amaru/sentra/vessels RAG | keyword (BM25/substring) fallback + badge | `degraded.search=keyword` | `vectordb_unavailable` |
| D5 | **WebSocket disconnect** | rosie nervous, killinchu twin | buffered events + Khipu replay on reconnect | client reconnect badge | `ws_disconnect` |
| D6 | **GPS spoof on drone** | killinchu edge | INS-only mode + halt + RTL | twin alarm glyph | `gps_spoof_detected` |
| D7 | **Starlink jammed** | killinchu edge | mesh LTE → encrypted store-and-forward → sneakernet | link badge | `starlink_jammed` |
| D8 | **Khipu DAG corruption** | vessels/a11oy canonical DAG | repair from `snapshots/` 30-day backups | integrity alarm | `khipu_corruption` |
| D9 | **Token leak** | org-wide secrets | automated rotation + incident receipt + customer notice | status-page incident | `token_leak` |

The detailed runbook for each follows.

---

## D1 — HF Space down → static fallback + cached last-known-good

**Detection.** External Prometheus blackbox probe hits `GET /api/<space>/healthz`
every 15 s. Two consecutive non-200 (or HF stage `BUILDING`/`APP_STARTING`/`RUNTIME_ERROR`
read from `HfApi.get_space_runtime`) flips the Space's health to `DOWN`.

**Degradation.**
- The **public status page** and any sibling that proxies the Space serve a *static
  fallback page* (committed at `static/_fallback/<space>.html` in each Space repo) that
  renders the **cached last-known-good** snapshot. The snapshot is the last successful
  `healthz` + key read-views, cached by the observability collector (see
  `OBSERVABILITY_DASHBOARD.md`) and mirrored to S3 (`BACKUP_AND_RECOVERY.md`).
- The fallback page shows: the Space name, the **timestamp** of the cached snapshot,
  a clear *"This Space is restarting — data below is a cached snapshot, not live"* banner,
  and a link to the status page.
- Because HF static Spaces (README, anatomy-3d, uds-demo) are docker-or-static and can
  themselves restart, the fallback HTML is **fully self-contained** (no runtime calls).

**Honesty.** We never serve a stale snapshot *as if* live. The cached-at timestamp is
mandatory and prominent. If no snapshot exists yet, the page says so plainly.

**Recovery.** When `healthz` returns 200 for 3 consecutive probes, health flips to `UP`,
the fallback banner disappears, and a `space_recovered` Khipu receipt is appended.

---

## D2 — LLM router: all providers rate-limited → T0 cache / T1 small / honest error

The a11oy `/v1/router` is the only LLM brain for every flagship (killinchu, amaru,
sentra, rosie all call it). Its action space `𝒜` is the license-typed candidate set
(GREEN MIT/Apache spine, AMBER Llama-class, RED API-only) per the open-LLM unification
note in `puriq/brainstorm/PONDER.md`.

**Cascade (in order):**

1. **T0 — semantic cache hit.** If the request embedding matches a cached prompt within
   the similarity floor, return the cached completion, flagged `degraded.tier=T0_cache`
   with the cache age. This is the *fastest honest answer* and is preferred over a live
   call when all providers are saturated.
2. **T1 — small local model.** If no cache hit, route to the smallest GREEN self-host
   model that is *not* rate-limited (the router removes rate-limited candidates from `𝒜`
   *before* the argmax, so the `exp(-β·HUKLLA)` factor is enforced at generation time).
   Response flagged `degraded.tier=T1_small`, with a note that a smaller model answered.
3. **Honest error.** If T0 misses *and* every model in `𝒜` is rate-limited, return a
   **structured honest error** — never a hallucinated fill:
   ```json
   { "error": "all_llm_providers_rate_limited",
     "retry_after_s": 30,
     "degraded": true,
     "tried": ["T0_cache_miss","T1_small_rate_limited","..."],
     "honest": "No model could answer within budget. This is a real error, not a guess." }
   ```

**Gate interaction.** A degraded T0/T1 answer still passes through the 13-axis Yuyay
gate. If the smaller model's output cannot clear the conjunctive AND floors, the router
returns the honest error rather than shipping an ungated emission (Doctrine v12 §5:
`Yuyay₁₃(a)=0 ⇒ U=0`).

**Khipu.** Every degraded route emits `llm_all_providers_rate_limited` with `tier_served`
and the `license_class` of the model that answered (GREEN/AMBER/RED), preserving the
sovereign-GREEN-only invariant.

---

## D3 — HfApi push failing → queue + exponential backoff + alarm

All HF changes go through **HfApi** (`create_commit` / `upload_file`), **NEVER** GitHub
Actions `secrets.HF_TOKEN` (HARD RULE). When a push fails (network, 5xx, rate-limit, lock):

**Degradation.**
- The commit operation set is **persisted to a durable local queue** (`ship_queue/<space>/<uuid>.json`
  containing the `CommitOperationAdd` paths + message + target repo).
- A retry worker drains the queue with **exponential backoff + full jitter**:
  `delay = min(cap, base * 2^attempt) * U(0,1)`, `base=2s`, `cap=300s`, max 8 attempts
  over ~25 min, then it parks the item in `ship_queue/_dead/` and **alarms**.
- The push is **idempotent**: re-pushing the same content set is a no-op commit (HF
  returns the same tree), so retries cannot duplicate or corrupt history.

**Alarm.** A dead-letter (max attempts exhausted) fires a SEV-3 page (see
`INCIDENT_RESPONSE_RUNBOOK.md`) and writes a status-page internal note (not public).

**Khipu.** `hfapi_push_failed` receipt on each exhausted item, with attempt count and the
last HF error string (honest — the real error, not a sanitized one).

---

## D4 — Vector DB unavailable → keyword search + degradation badge

The per-organ RAG (a11oy gate, amaru cortex, sentra immune, vessels receipt, rosie all)
runs over a vector index (the PONDER note pins the substrate per organ — pgvector for the
ACID ledger, Qdrant for filtered-NN, graph store for Khipu reachability).

**Degradation.**
- On vector-DB unavailability (connection refused / timeout / health fail), RAG falls
  back to **keyword search**: BM25 if a Lucene/Tantivy index is present, else
  case-insensitive substring ranking over the same chunk corpus (the chunks are stored
  alongside embeddings, so the text is always available).
- Every `/v1/rag` response gains `degraded: true, degraded.search: "keyword"` and the
  HTML surface shows a **degradation badge**.
- `similarity` scores are **omitted** (not faked) in keyword mode; results carry a
  `match: "keyword"` field instead, so a consumer never mistakes lexical overlap for
  semantic similarity.

**Honesty.** Keyword fallback is explicitly *worse* recall on paraphrase queries; the
badge says so. We do not silently return lexical hits dressed as semantic ones.

**Khipu.** `vectordb_unavailable` receipt per affected query batch (sampled, not per
query, to avoid DAG flooding — one receipt per breaker OPEN transition + a count).

---

## D5 — WebSocket disconnect → buffered events + Khipu replay on reconnect

Rosie's nervous-system live stream and the killinchu 3D twin push events over WebSocket.

**Degradation.**
- **Server side:** on client disconnect, events are not dropped — they are appended to a
  **per-client ring buffer** keyed by the last acknowledged event sequence number. The
  buffer is bounded (e.g. last 1000 events / 5 min) and is honest about overflow: if the
  buffer wraps, the reconnect response includes `"buffer_overflow": true, "gap_from_seq": N`.
- **Client side:** the twin/Rosie panel shows a *"reconnecting…"* badge and switches to
  cached-last-frame rendering; it never freezes silently.
- **On reconnect:** the client sends its last-seen sequence; the server **replays** the
  buffered events in order. Because every state-changing event is also a **Khipu receipt**,
  the authoritative replay source is the **Khipu DAG itself** — the client requests the
  receipts since its last verified DAG node and reconciles by Merkle proof of inclusion
  (the same reconciliation killinchu edge drones use). This makes replay *provably complete*
  for governed events, not best-effort.

**Khipu.** `ws_disconnect` and `ws_reconnect_replay` receipts; the replay receipt records
`replayed_count` and whether a buffer gap was bridged from the DAG.

---

## D6 — GPS spoof on drone → INS-only mode + halt + RTL

This is a **killinchu edge** safety-critical path. Detection draws on the C-UAS /
tamper-detection work (`killinchu/twin/TAMPER_HACK_DETECTION.md`,
`killinchu/cuas/MAVLINK_REMOTEID_DEEPDIVE.md`).

**Detection (any of):**
- GPS/INS innovation residual exceeds threshold (EKF rejects GPS as inconsistent with
  inertial dead-reckoning) — the standard, real PX4/ArduPilot spoof tell.
- Sudden position jump / impossible velocity, or CN0 anomaly (too-strong, too-uniform
  signal characteristic of a spoofer).
- Loss of RAIM / multi-constellation disagreement.

**Degradation (staged, conservative):**
1. **INS-only mode.** The flight controller stops trusting GPS and navigates on the
   inertial measurement unit (dead reckoning) + any non-spoofable aids (barometric
   altitude, optical flow, visual-inertial odometry if fitted).
2. **Halt.** `P(x,t)` selection is constrained: under a fired spoof tripwire, the geofence
   factor and the HUKLLA halt dominate (Egyptian-doubling compound-risk bound), so the
   argmax selects **loiter/hold** — the drone stops advancing the mission.
3. **RTL (Return-To-Launch).** If INS confidence degrades below the safe-flight floor,
   the controller commands RTL on the last *trusted* (pre-spoof) home fix, flying the
   inertial path home. RTL is the documented, conservative default.

**Honesty.** We do **not** claim spoof-proof navigation. INS drifts; the doc states the
drift envelope and the time-to-RTL budget honestly. The degradation is *halt-biased*: a
spoofed drone holds or comes home, it never pushes mission under uncertain position.

**Khipu.** `gps_spoof_detected` receipt written to the **local** edge Khipu chain (SQLite
+ SD append log) immediately — it reconciles to the canonical DAG on reconnect by Merkle
proof. The receipt records the detector that fired and the action taken (INS/halt/RTL).

---

## D7 — Starlink jammed → mesh LTE → encrypted store-and-forward → sneakernet

Per `killinchu/satellites/STARLINK_HONEST_TRUTH.md`, Starlink is our **own backhaul radio**
(comms), never a tracking sensor. When the link is jammed/lost:

**Degradation cascade:**
1. **Mesh LTE.** Fail over to a mesh-LTE bearer (peer drones / ground relay nodes carry
   traffic for each other). The edge anatomy already runs fully local, so loss of backhaul
   does not stop governance — it only delays reconciliation.
2. **Encrypted store-and-forward.** If no bearer is reachable, the edge node buffers all
   telemetry, video keyframes, and **Khipu receipts** to its local encrypted store
   (content-addressed; the local Khipu chain is the source of truth). Nothing is lost.
3. **Sneakernet pickup.** As a last resort, the encrypted store is physically retrieved
   (SD/USB) and ingested at a connected node; reconciliation is by **Merkle proof of
   inclusion** into the canonical DAG — exactly the disconnected-edge reconcile path the
   killinchu architecture is built around.

**Honesty.** This is the real failure ordering for contested-RF operations. We do not
pretend the link is up; the twin shows the bearer actually in use (Starlink / mesh-LTE /
store-and-forward) and the reconciliation backlog depth.

**Khipu.** `starlink_jammed` receipt (local), `link_failover` with the bearer chosen,
`reconcile_complete` when the backlog drains into the canonical DAG.

---

## D8 — Khipu DAG corruption → repair from snapshots/ 30-day backups

The canonical Khipu DAG is the empire's audit spine. Corruption = any node whose stored
`digest` ≠ recomputed `sha256(payload ‖ parents)`, or a broken parent link.

**Detection.** A continuous integrity verifier walks the DAG tail and recomputes digests;
the observability dashboard tracks **DAG integrity** as a first-class panel. A mismatch
fires a **SEV-1** (the audit spine is sacred).

**Degradation / repair:**
1. **Freeze writes** to the affected segment (RUWAY refuses new appends past the corrupt
   node until repaired — better an honest write-stall than a forked chain).
2. **Repair from `snapshots/`.** The DAG is snapshotted to `snapshots/` on a rolling
   schedule with **30-day hot backups** (see `BACKUP_AND_RECOVERY.md`). The verifier
   finds the most recent snapshot whose root digest is internally consistent and replays
   forward, re-validating each node by hash.
3. **Re-link & resume.** Nodes that fail re-validation are quarantined (not deleted —
   honesty), and writes resume from the last good root.

**Honesty.** Because `Khipu_i(a)` verifies the **hash chain** (signatures are DSSE
PLACEHOLDER), repair is a hash-chain re-derivation, not a signature re-attestation. We do
not claim cryptographic non-repudiation we have not wired. INV-3
(`puriq_khipu_integrity`) guarantees any action whose receipt cannot re-validate has
utility `0` — a corrupt-provenance action can never be selected.

**Khipu.** `khipu_corruption` (with the corrupt node index + recomputed-vs-stored digests)
and `khipu_repair_complete` (snapshot used, nodes quarantined, new root).

---

## D9 — Token leak → automated rotation + Khipu receipt + customer notification

Tokens in scope: HF_TOKEN, GITHUB_TOKEN, ZENODO_TOKEN, AI provider keys, and (when wired)
COSIGN signing material.

**Detection.** Secret-scanning (GitHub push protection + scheduled scan), anomalous-use
alerts, or manual report. Any positive triggers the leak path.

**Degradation / response (automated where safe):**
1. **Revoke & rotate.** The leaked credential is **revoked immediately** at the provider,
   a new one is minted, and dependent systems are updated. HF/GitHub support programmatic
   rotation; for AI providers, rotation is provider-API or console (documented in the
   runbook with the exact action). During rotation, affected pushes degrade to the **D3
   queue** (no data loss).
2. **Khipu incident receipt.** A `token_leak` receipt records *that* a leak occurred,
   *which class* of secret, detection source, and the rotation outcome — **without ever
   recording the secret value** (the receipt stores a salted hash prefix at most, for
   correlation, never the token).
3. **Customer notification.** If the leak could plausibly affect customer data or service,
   a notice is issued through the **status page** + direct channel within the contractual
   window. Internal-only secrets (CI tokens with no customer-data scope) get an internal
   incident record but no customer notice — the status-page filter (see
   `STATUS_PAGE_FEED.md`) decides this, honestly and without over-disclosure of internals.

**Honesty.** We do not bury a leak. We rotate first (stop the bleeding), receipt it
(auditable), and notify proportionally to real customer impact. No theatrical
over-notification, no silent cover-up.

**Khipu.** `token_leak` (detection + class) and `token_rotation_complete` (provider,
new-key-id fingerprint, downstream systems updated).

---

## 2 — Cross-cutting invariants (apply to all paths)

- **Every degradation lowers, never raises, trust.** Degraded organ factors stay in `[0,1]`.
- **Every degradation is receipted.** No silent fallback.
- **Every degradation is visible.** Header + badge + (if customer-affecting) status page.
- **Honest error is a valid terminal state.** When nothing can serve, we return a real
  error with `retry_after`, never a fabricated success.
- **v11 LOCKED numbers and the 13-axis gate are untouched** by any degradation path
  (ADDITIVE only).

---

*Cited internal sources:*
`killinchu/architecture/KILLINCHU_FULL_STACK_ARCHITECTURE.md`,
`killinchu/satellites/STARLINK_HONEST_TRUTH.md`,
`killinchu/twin/TAMPER_HACK_DETECTION.md`,
`wires_def_ship/szl_wire.py` (Khipu DAG + traceparent),
`puriq/doctrine/PURIQ_DOCTRINE_v12.md`, `puriq/brainstorm/PONDER.md`.

— Yachay (SZL reliability agent), under CTO authority — Doctrine v12, additive over v11 LOCKED.
