# Hub treatment — SZLHOLDINGS

Captured: `2026-08-29T14:18:27Z`  
Evidence class: **REPORTED**  
Source: public browse of https://huggingface.co/SZLHOLDINGS plus https://huggingface.co/api/spaces?author=SZLHOLDINGS  
Hub session: **AVAILABLE** (no 429). Pin/unpin was **not** executed.

This sandbox cannot pin or unpin. Those mutations require Hub admin with `HF_TOKEN`. Do not treat this file as a Hub write. Do not create a new Space.

---

## Org counts (public UI)

| Tab | Count | Notes |
|-----|------:|-------|
| Spaces | 42 | UI. API enumerated **41** public Space ids. Delta of 1 is UNKNOWN. |
| Models | 42 | UI and models listing agree. |
| Datasets | 28 | UI and datasets listing agree. |
| Kernels | 14 | UI. |
| Collections | 13 | UI. |

Counts are listing metadata, not quality.

---

## Pin list (public front of Hub catalog)

Pin these five. They are the catalog front door.

| Space | Observed now | Treatment |
|-------|--------------|-----------|
| `SZLHOLDINGS/a11oy` | Running, **pinned** | PIN — keep. Flagship Command Center. |
| `SZLHOLDINGS/killinchu` | Running, **pinned**, 2 likes | PIN — keep. Public vertical. Synthetic reference only. |
| `SZLHOLDINGS/immune` | Running, **not pinned** | PIN — currently missing from the front. Defense matrix, not the lattice HUD. |
| `SZLHOLDINGS/szl-atelier` | Running, **pinned** | PIN — keep. Walk Hub model cards. Not weights. |
| `SZLHOLDINGS/holographic` | Running, **not pinned** | PIN — currently missing from the front. Atlas / estate hologram that *is* the catalog face. |

Recommended pin set (doctrine):

```
SZLHOLDINGS/a11oy
SZLHOLDINGS/killinchu
SZLHOLDINGS/immune
SZLHOLDINGS/szl-atelier
SZLHOLDINGS/holographic
```

---

## Unpin list

HF org homepage currently pins five Spaces. Two of those slots are labs.

| Space | Observed now | Treatment |
|-------|--------------|-----------|
| `SZLHOLDINGS/cosmos` | Running, **pinned** | **UNPIN (must).** Lab Three.js map. Runtime mirror. Not catalog front. After unpin: LAB, keep running. |
| `SZLHOLDINGS/szl-khipu` (card: SZL KHIPU) | Running, **pinned** | UNPIN. Lab occupying a pin slot. Kernel is the model/kernel, not this Space. After unpin: LAB, keep running. |

No other currently-pinned lab was observed on the org homepage.

---

## Factory

`SZLHOLDINGS/a11oy-factory`

- **RUNNING · unpinned · not a second flagship**
- Org listing showed Starting, then the Space page showed Running. Treat as RUNNING.
- Not in the pin list. Do not promote it to a second flagship.
- Keep running, unpinned.

---

## Warhacker

`SZLHOLDINGS/warhacker` — **NOT LISTED (correct)**

- Absent from org homepage.
- Absent from the 41 public Space ids returned by the Hub API.
- Site search did not surface a SZLHOLDINGS Warhacker Space.
- Direct URL https://huggingface.co/spaces/SZLHOLDINGS/warhacker returned **401**, not a public card. Same 401 pattern as other missing slugs (`puriq-live`, `khipu`, `szl-holdings`).
- Archive lives on GitHub (`warhacker-demo`, a11oy release `v1.0.0`, 2026-06-03). Do not pin it. Do not mint a Warhacker Space.

---

## Mutation boundary

Pin/unpin requires Hub admin / `HF_TOKEN`. This sandbox cannot do it.

Do **not**:

- Create a new Space.
- Upgrade Hub cards that are already Running unless the card lies (`a11oy`, `killinchu`, `szl-atelier`, `cosmos`, `szl-khipu`).
- Treat this REPORTED recapture as a Hub write or as production certification.

---

## Four journeys

Operate / Build / Research / Verify are **routes into cards**, not a fifth website.

The public origins stay three:

1. Product — https://a-11-oy.com
2. Proof — https://a11oy.net
3. Artifact registry — https://huggingface.co/SZLHOLDINGS

Journeys select a card (Command Center, vertical, lab hologram, verifier). They are not a new origin, not a fourth/fifth site, and not a reason to mint another Space.

---

## Classification of every Space found

### PIN — catalog front (5)

| Id | Runtime | Now | Action |
|----|---------|-----|--------|
| `SZLHOLDINGS/a11oy` | docker · Running | pinned | keep PIN |
| `SZLHOLDINGS/killinchu` | docker · Running | pinned | keep PIN |
| `SZLHOLDINGS/immune` | docker · Running | unpinned | PIN |
| `SZLHOLDINGS/szl-atelier` | static · Running | pinned | keep PIN |
| `SZLHOLDINGS/holographic` | docker · Running | unpinned | PIN |

### UNPIN — currently pinned labs (2)

| Id | Runtime | Now | Action |
|----|---------|-----|--------|
| `SZLHOLDINGS/cosmos` | docker · Running | pinned | **UNPIN (must)** then LAB |
| `SZLHOLDINGS/szl-khipu` | docker · Running | pinned | UNPIN then LAB |

### LAB — keep running, unpinned

Named labs from doctrine, plus the rest of the public runtime that is not catalog front.

| Id | Runtime | Now | Note |
|----|---------|-----|------|
| `SZLHOLDINGS/szl-command-lab` | docker · Running | unpinned | command-lab. Holographic body. Not flagship. |
| `SZLHOLDINGS/khipu-lab` | docker · Running | unpinned | Lab hologram. `szl-khipu` is the kernel. |
| `SZLHOLDINGS/szl-khipu` | docker · Running | **pinned (wrong)** | After unpin: LAB. |
| `SZLHOLDINGS/cosmos` | docker · Running | **pinned (wrong)** | After unpin: LAB. |
| `SZLHOLDINGS/a11oy-factory` | docker · Running | unpinned | **RUNNING unpinned. Not a second flagship.** |
| `SZLHOLDINGS/immune-lattice` | docker · Running | unpinned | COP HUD. Sibling of `immune`, not the pin. |
| `SZLHOLDINGS/nexus` | docker · Running | unpinned | Incubator. Analog CRT. Not product. |
| `SZLHOLDINGS/ayllu` | docker · Running | unpinned | Eleven-seat council. Experimental. |
| `SZLHOLDINGS/counsel` | docker · Running | unpinned | Legal vertical revival. Not flagship. |
| `SZLHOLDINGS/experiments` | docker · Running | unpinned | Experimental. |
| `SZLHOLDINGS/szl-experiments` | docker · Running | unpinned | Experimental. |
| `SZLHOLDINGS/second-brain` | docker · Running | unpinned | Handles-only retrieval hologram. |
| `SZLHOLDINGS/anatomy` | docker · Running | unpinned | Living anatomy map. |
| `SZLHOLDINGS/yarqa` | docker · Running | unpinned | Plug-flow CFD demo. |
| `SZLHOLDINGS/llm-router-live` | docker · Running | unpinned | Router status. Product marks STALE / NOT_MEASURED. |
| `SZLHOLDINGS/hatun-mcp` | docker | unpinned | Lab. |
| `SZLHOLDINGS/sda` | docker · Running | unpinned | Domain-awareness demo. |
| `SZLHOLDINGS/david-leads` | docker | unpinned | Insurance intelligence demo. |
| `SZLHOLDINGS/szl-real-estate` | docker · Running | unpinned | Public-records underwriting. Not MLS. |
| `SZLHOLDINGS/szl-sovereign-os` | docker · Running | unpinned | Operator kernel hologram. |
| `SZLHOLDINGS/szl-estate-live` | static · Running | unpinned | Khipu Loom / estate search. |
| `SZLHOLDINGS/szl-forge-lab` | static · Running | unpinned | Forge evidence console. |
| `SZLHOLDINGS/szl-model-inference-lab` | docker | unpinned | Bounded inference lab. |
| `SZLHOLDINGS/szl-quant-live` | static · Running | unpinned | Paper-only quant ledger. |
| `SZLHOLDINGS/governed-agent-bench` | gradio | unpinned | Bench surface. |
| `SZLHOLDINGS/energy-attested-runs` | static | unpinned | Verify-it-yourself. |
| `SZLHOLDINGS/governed-receipt-verifier` | static | unpinned | In-browser verifier. |
| `SZLHOLDINGS/guardrail-receipt` | static | unpinned | Guardrail receipt demo. |
| `SZLHOLDINGS/governed-norm-holo` | static | unpinned | Kernel hologram. |
| `SZLHOLDINGS/lambda-gate-holo` | static | unpinned | Λ hologram. Conjecture 1. |
| `SZLHOLDINGS/energy-attest-holo` | static | unpinned | Energy hologram. |
| `SZLHOLDINGS/receipt-chain-live` | static | unpinned | Receipt chain. |
| `SZLHOLDINGS/szl-provctl-live` | static · Running | unpinned | Provenance DAG. |
| `SZLHOLDINGS/szl-kernels-live` | static | unpinned | Kernel ops console. |
| `SZLHOLDINGS/szl-govsign-live` | static · Running | unpinned | DSSE sign demo. |
| `SZLHOLDINGS/szl-blocked-live` | static · Running | unpinned | Honest BLOCKED demo. |

Keep labs as labs. Do not pin them. Do not pause them from this recapture.

### ARCHIVE / not listed

| Name | Finding |
|------|---------|
| Warhacker | **NOT LISTED (correct).** Must not be a Space. |

### UNKNOWN

| Item | Why |
|------|-----|
| Space count 42 (UI) vs 41 (API) | One public id not in the API dump. Not Warhacker. Not a reason to create a Space. |
| Direct missing slugs (`warhacker`, `khipu`, `puriq-live`, `szl-holdings`) | HTTP 401, not a public card. Do not infer a private Warhacker Space from 401. |
| Private Spaces | Not readable without `HF_TOKEN`. |

---

## Observed org pin strip (as of capture)

Pinned on https://huggingface.co/SZLHOLDINGS, in the order shown:

1. SZL KHIPU — `szl-khipu` — **unpin (lab)**
2. SZL Cosmos — `cosmos` — **unpin (must)**
3. a11oy — Command Center — `a11oy` — keep
4. SZL Atelier — `szl-atelier` — keep
5. killinchu — Andean Drone Intelligence — `killinchu` — keep

Target pin strip after Hub admin acts:

1. `a11oy`
2. `killinchu`
3. `immune`
4. `szl-atelier`
5. `holographic`

---

## Models / datasets (listing only)

REPORTED. Not a quality claim.

- Models: 42. Includes `SZL-Khipu-1.5B`, `SZL-Forge-1.5B-ReceiptAgent`, `SZL-Khipu-1.5B-GGUF`, nano silhouettes, kernel cards.
- Datasets: 28. Includes `killinchu-osint-corpus`, `szl-lake`, `a11oy-verifiable-corpus`, `governed-agent-bench`.

---

## Close

Evidence class remains **REPORTED**. This file is a treatment order for a Hub admin, not a mutation.

- Pin: a11oy, killinchu, immune, szl-atelier, holographic
- Unpin: cosmos (must), szl-khipu (lab on the pin strip)
- Factory: RUNNING unpinned, not a second flagship
- Warhacker: NOT LISTED (correct)
- Do not create a new Space
- Four journeys are routes into cards, not a fifth website
