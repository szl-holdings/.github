# SZL Doctrine v11

**Status:** ENACTED — 2026-06-13
**Supersedes:** Doctrine v7 (ENACTED 2026-05-30) and the interim v8–v10 working notes.
**Authority:** Founder — Stephen P. Lutar Jr.
**Attestation:** This document is the single source of truth for the eight estate gates G1–G8. It must itself pass the v11 grep gates (codename gate G5, overclaim gate G2/G7) on every clause.
**Audit basis:** SZL estate-elevation recon (a11oy + killinchu live surfaces, 2026-06-13), `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, and `team/AUDIT/elevate/DEV5_RECON.md`.

---

> The half-state — claiming more than is real — is the only unacceptable outcome.
> Every gate below traces to a specific observed failure or a specific verifiable estate fact. No gate is decorative.

---

## Part I — The Eight Estate Gates (G1–G8)

The gates are hard invariants. They are never relaxed for convenience, deadline, or aesthetics. Each gate states the rule, its rationale, and its enforcement.

---

### G1 — Locked-Proven Count is EXACTLY 8

**Rule:** The set of locked-proven formulas is EXACTLY the eight identifiers `{F1, F4, F7, F11, F12, F18, F19, F22}` at commit `c7c0ba17`. No artifact, endpoint, docstring, dashboard, or report may state the locked-proven count as 5, or as any value other than 8. The phrase "locked=5" (in any spacing or punctuation) is a hard violation. The authoritative live source is `GET /api/a11oy/v1/honest` (verified: `count=8`, ids `[F1,F4,F7,F11,F12,F18,F19,F22]`, commit `c7c0ba17`).

**Rationale:** Live `/api/a11oy/v1/honest` correctly reports 8, but `a11oy_devb_endpoints.py:28` (doc string) and `:60` (`"locked_proven":["F1","F11","F12","F18","F19"]` — only 5) carry a stale 5-element set. A 5/8 mismatch on a governance metric is a half-state: the dashboard claims one thing while the audited count is another.
Source: `team/AUDIT/elevate/DEV5_RECON.md`, G1 section; live endpoint `https://szlholdings-a11oy.hf.space/api/a11oy/v1/honest`.

**Enforcement:**
- CI grep gate: `locked[ _=:-]*5` (case-insensitive) anywhere outside an explicitly-quoted historical-diff block fails the gate.
- The estate KPI board (`/api/{ns}/v1/ecosystem/kpi-board`) asserts `locked.count == 8` and `set(locked.ids) == {F1,F4,F7,F11,F12,F18,F19,F22}`; any other value renders the board NON-OK.
- Fix concept handed to Dev1 for `a11oy_devb_endpoints.py`: replace both the `:28` doc and the `:60` list with the EXACTLY-8 set.

---

### G2 — Λ (Lambda) is Conjecture 1, never a bare "unique theorem"; trust never 100%

**Rule:** The uniqueness of Λ is **Conjecture 1** — machine-checked FALSE *as literally stated*. It may NOT be described as a proven "unique theorem". The only proven uniqueness result is **Theorem U** (Λ is unique modulo the audit-invariant). Any numeric trust / confidence / Λ value must be strictly less than 1.0 (`Λ < 1.0`); a value of `1.0` (100% trust) is a hard violation. Forbidden surface phrasings: "unique theorem", "tamper-proof", "100%", "fully verified", "guaranteed".

**Rationale:** `killinchu /api/killinchu/v1/gov/chapaq-verdict` proxies `a11oy /api/sentra/v1/verdict` which returns `lambda_value: 1.0`, asserting 100% trust — a half-state, because no audit chain is perfect. Live a11oy Λ is `0.91911` (`< 1.0`), which is honest and correct.
Source: `team/AUDIT/elevate/DEV5_RECON.md`, Λ-defect section; live `https://szlholdings-a11oy.hf.space/api/a11oy/v1/gov` (Λ=0.91911).

**Enforcement:**
- CI grep gate (overclaim sweep): `unique theorem`, `tamper.?proof`, bare `100%` trust, `fully verified` without an adjacent `Conjecture 1` / `Theorem U` qualifier fail the gate.
- The estate KPI board clamps any reported Λ to `< 1.0` and raises a `LAMBDA_OVERCLAIM` flag (e.g. flags the CHAPAQ verdict whose `lambda=1.0`) rather than silently passing it through.
- The `szl_label_engine.js` `auditText()` helper catches `100%`, `tamper-proof`, and `unique theorem` in any rendered string.

---

### G3 — Khipu is tamper-EVIDENT (Conjectures 2/3), never tamper-PROOF

**Rule:** Khipu BFT **safety is Conjecture 2** and **liveness is Conjecture 3**. The ledger is **tamper-evident**, never "tamper-proof". Receipts are **signed and verifiable**, never "immutable" or "unforgeable" in the absolute sense.

**Rationale:** A signed append-only receipt chain detects tampering; it does not physically prevent it. Stating "tamper-proof" overclaims the property and is a half-state.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G3.

**Enforcement:**
- CI grep gate: `tamper.?proof`, `immutable ledger`, `unforgeable` fail unless inside a quoted negative ("not tamper-proof, but tamper-evident").
- Khipu surfaces must label safety/liveness as `Conjecture 2` / `Conjecture 3`.

---

### G4 — SLSA is "L1 honest · L2 attested · L3 roadmap"; never bare L3 / FedRAMP / IronBank / CMMC / ATO

**Rule:** Supply-chain posture is stated EXACTLY as: **"L1 honest · L2 attested (.att emitted, not independently verified) · L3 roadmap"**. The following bare claims are hard violations anywhere in a user-visible surface: bare `SLSA L3` (without "roadmap"), `FedRAMP`, `IronBank`, `CMMC`, `ATO` (Authority To Operate). These imply certifications the estate does not hold.

**Rationale:** `.att` files are emitted but not independently verified; claiming bare L3 or any government certification is a half-state.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G4.

**Enforcement:**
- CI grep gate (overclaim sweep): `SLSA[ -]*L3` not immediately followed by `roadmap`, plus the literals `FedRAMP|IronBank|CMMC|\bATO\b`, fail the gate.
- The `szl_label_engine.js` `auditText()` helper flags bare `SLSA L3`, `FedRAMP`, `IronBank`, `CMMC`, `ATO`.

---

### G5 — Codenames are internal-only keys; user-visible strings read YACHAY / Operator / CHAPAQ

**Rule:** The codenames `amaru`, `rosie`, `sentra`, `jarvis` are acceptable ONLY as internal identifiers (JS object keys, `id`/`class`/`data-*` attributes, Python variable names, internal route segments). They MUST NOT appear in any **user-visible string**. The canonical user-visible mapping is: `amaru → YACHAY`, `rosie → Operator`, `sentra → CHAPAQ`, `jarvis → Operator`.

**Rationale:** Codenames leaking into rendered UI, titles, aria-labels, alt text, or placeholders break the public naming doctrine.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G5; live org-wide sweep (PASSED, 0 user-visible codenames).

**Enforcement:**
- GitHub Action `codename-gate.yml` (this gate) runs `codename_sweep.py`, which imports `szl_codename_gate.py`. The scanner strips `<script>`/`<style>`/tags and scans only visible text plus `title`/`aria-label`/`alt`/`placeholder` attributes; it explicitly ALLOWS `id`/`class`/`data-*` internal keys.
- Transient HTTP 000 from a live surface is a WARN, not a FAIL (intermittent HF behavior), but a confirmed visible-text match is a hard FAIL.
- Shared scanner (`szl_codename_gate.py`) and sweep (`codename_sweep.py`) are co-located in `.github/scripts/`.

---

### G6 — killinchu effectors are SIMULATED (human-on-loop); only sensing is LIVE

**Rule:** All killinchu effectors (vessel / submarine / drone control, weapons, maneuver) are **SIMULATED, human-on-loop**. There is **no live vessel or sub control**. Only **sensing** modalities may be labeled LIVE, and only when truly live: ADS-B, AIS, RemoteID, and OSINT feeds. Any effector surface must carry the `SIMULATED` badge.

**Rationale:** Claiming live kinetic control is both untrue and unsafe. Sensing feeds can be genuinely live; control cannot.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G6.

**Enforcement:**
- Effector responses and HTML render the `SIMULATED` badge from `szl_label_engine.js`.
- Sensing feeds render `LIVE` only when the upstream feed is confirmed reachable; otherwise `SAMPLE`/`CONNECT-READY`.
- CI grep gate: effector route handlers asserting `LIVE` control fail.

---

### G7 — Honest labels; 0 runtime CDN; Section 889 vendors EXACTLY 5; trust never 100%

**Rule:** (a) Every datum carries an honest provenance badge from the canonical set: `LIVE / SAMPLE / FORECAST / OSINT / MODELED / SIMULATED / CONNECT-READY / EXPERIMENTAL / HEURISTIC`. (b) **0 runtime CDN**: all 3D and JS libraries are vendored locally (under `static-vendor/` and `static/vendor3d/`); no `<script src="https://cdn...">` at runtime. (c) The Section 889 prohibited-vendor list is **EXACTLY 5** entries — never more, never fewer. (d) Trust/Λ is never 100% (restates G2's `Λ < 1.0`).

**Rationale:** Runtime CDN reintroduces a supply-chain and availability dependency the estate deliberately removed; an over- or under-sized 889 list misstates compliance scope.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G7; recon confirmed libs vendored under `static-vendor/` (three.min.js, globe.gl.min.js, echarts-gl.min.js, 3d-force-graph.min.js, d3.min.js) and `static/vendor3d/` (three.module.min.js, OrbitControls.js).

**Enforcement:**
- CI grep gate: `<script src="https?://` (runtime CDN) in served HTML fails.
- The ecosystem 3D surface (`/estate-organism`) loads three.js via a vendored fallback chain `/static/vendor3d/three.module.min.js → /static-vendor/three.min.js`, never a CDN.
- 889-vendor manifest check asserts list length `== 5`.
- The `szl_label_engine.js` SCHEMES registry is the single source of the 9 honest badges; unbadged data surfaces are flagged.

---

### G8 — The half-state is the only unacceptable outcome

**Rule:** Honest `SAMPLE` / `FORECAST` / `OSINT` / `MODELED` / `SIMULATED` labeling is always correct and always acceptable. The single unacceptable outcome is the **half-state**: claiming more than is real (faking `LIVE`, faking green, faking a proof, faking a certification). When in doubt, label down, never up. **G8 also forbids breaking what is already real**: do not regress a working, verified mechanism merely to satisfy a suggestion that conflicts with deployed reality.

**Rationale:** This is the estate's prime directive. Every other gate is an instance of it. The DSSE-scheme decision below is a direct application: the suggested Ed25519 switch was rejected because it would break the *real*, deployed ECDSA-P256 cosign interop.
Source: `team/AUDIT/elevate/ELEVATION_SPEC.md` §0, G8; `team/AUDIT/elevate/DEV5_RECON.md`, DSSE-scheme resolution.

**Enforcement:**
- Every additive surface is `try/except`-guarded so a failure degrades to honest "not wired" rather than a fake-success.
- Builders never fabricate `LIVE`; e.g. the cross-app ledger reports `PENDING` (honest) until the killinchu cosign secret is set, rather than faking a unified chain.
- Human and CI review reject any change that converts an honest down-label to an unsupported up-label.

---

## Part II — Resolved Estate Decisions (v11 binding)

### §A — Cosign / DSSE scheme is ECDSA-P256-SHA256 (single canonical scheme)

**Decision:** The one canonical signing scheme for the estate is **ECDSA-P256-SHA256** with key id `szlholdings-cosign`. This resolves the prior Ed25519 / ECDSA-P256 / HMAC drift.

**Rationale:** The deployed estate — `szl_dsse.py` (byte-identical across both apps, sha256 `d734fd066f215d65…`), the published `cosign.pub` (a P-256 EC key at `szl-holdings/.github/cosign.pub`), and every verify path — uses P-256. `a11oy_signing_key.py:16-17` explicitly states the key is "deliberately NOT Ed25519". Switching to Ed25519 (a task suggestion) would break cosign-CLI interop and the verified cross-app chain — a direct G8 violation. Doctrine therefore standardizes on the **real** scheme, ECDSA-P256.
Source: `team/AUDIT/elevate/DEV5_RECON.md`, DSSE-scheme resolution; `a11oy_signing_key.py:16-17`.

**Canonical framing (binding for all cross-app receipts):**
- `canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"))` (byte-stable; the JS `canonicalJSON` in `szl_receipt_cosign.js` byte-matches this).
- PAE (DSSE v1): `"DSSEv1" SP LEN(type) SP type SP LEN(body) SP body`.
- Envelopes are DSSE; a receipt verifies cross-app iff it verifies under the shared `szlholdings-cosign` P-256 key.

**Enforcement:** CI grep gate flags any new `Ed25519`/`HMAC` signing path in a receipt module without an explicit `[legacy-interop]` annotation. The estate ledger verifies envelopes under P-256 only.

### §B — Cross-app unified ledger requires the shared cosign secret

**Decision:** The cross-app unified ledger is the SAME cosign chain across both apps. a11oy's `POST /khipu/sign` signs under keyid `szlholdings-cosign`; killinchu currently signs under an ephemeral keyid (`088f370deba4b985`) because its Space secret is unset. Until `SZL_COSIGN_PRIVATE_PEM` (or `SZL_COSIGN_PRIVATE_KEY_PEM`) is set on the killinchu Space to the same key as a11oy, the ledger MUST report cross-app status `PENDING` (honest), never a faked unified chain.

**Rationale:** a11oy's canonical signature DOES verify on killinchu (confirmed), so the chain unifies the moment the secret is set — an operator action via HF settings. A key is NEVER committed to a repo.
Source: `team/AUDIT/elevate/DEV5_RECON.md`, cross-app cosign section.

**Enforcement:** The ecosystem ledger builder verifies the cross-app chain and reports `PENDING` until both apps sign under the shared keyid; it never fabricates `VERIFIED`.

### §C — OTLP / MELT is labeled honestly in-process

**Decision:** Telemetry (MELT — metrics, events, logs, traces) is computed **in-process** and is **not exported** to an external collector. It is labeled honestly in-process (as `organnervous` already does), rather than claiming an OTLP export pipeline that does not exist.

**Rationale:** No external collector is wired; claiming OTLP export would be a half-state.
Source: `team/AUDIT/elevate/DEV5_RECON.md`, OTLP/MELT section.

**Enforcement:** Anatomy/vitals surfaces label MELT as in-process; no surface claims an external OTLP exporter unless one is actually wired and reachable.

---

## Part III — Doctrine Meta-Rules

### Precedence

In any conflict between a clause of this doctrine and a standing CI configuration, workflow, suggestion, or PR template, this doctrine takes precedence. Configurations must be updated to match doctrine, not the reverse. Where a task suggestion conflicts with deployed reality (e.g. the Ed25519 suggestion), G8 governs: do not break what is real.

### Single Source of Truth

This file (`doctrine/DOCTRINE_V11.md` in the `szl-holdings/.github` repo) is the single canonical statement of gates G1–G8. The shared modules enforce it in code: `szl_label_engine.js` (badges + `auditText`), `szl_codename_gate.py` + `codename_sweep.py` (G5), `szl_receipt_cosign.js` + `szl_dsse.py` (§A), and the ecosystem KPI board (`/api/{ns}/v1/ecosystem/kpi-board`, G1/G2).

### Amendment Process

New or amended gates require: (a) a specific failure case or verifiable estate fact, (b) Founder approval, (c) a PR to the `.github` repo showing the exact diff to this document, and (d) at least one new enforcement mechanism (grep gate, CI check, or shared-module rule).

### Compliance Statement

This document was drafted to pass v11's own gates:
- G2/G7 overclaim grep: PASS — every "100%", "tamper-proof", "unique theorem", and bare "SLSA L3" appears only inside an explicitly-quoted prohibition.
- G5 codename grep: PASS — `amaru/rosie/sentra/jarvis` appear only inside explicit prohibition/mapping clauses, not as user-visible product strings.
- G1: PASS — the locked count is stated as EXACTLY 8 throughout; the only "5" appears inside a quoted description of the defect.

---

*Doctrine v11 | SZL | 2026-06-13 | Drafted by Dev5 (ecosystem foundation lane) under Doctrine v8–v10 working notes | Founder approval required before enactment | Single source of truth for gates G1–G8*
