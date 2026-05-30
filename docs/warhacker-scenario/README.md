# Warhacker 2026 — drone-loses-contact running deployment

The honest "running deployment" Andrew Greene (Defense Unicorns) asked for at
Warhacker (June 16–19, San Diego). A workload admitted to a live k3d/UDS cluster
is automatically receipt-traced by the **szl-receipts Pepr admission policy**,
which emits a tamper-evident **DSSE HMAC-SHA-256** governance receipt that any
reviewer in the room can verify themselves.

```
kubectl apply (workload) → Pepr szl-receipt-policy → DSSE receipt
   → szl-receipts-server /receipts  +  K8s annotations  →  cosign/HMAC verify
```

## Honest scope (Doctrine V7 §10)

Verified against `szl-uds-deployment`: **vessels** ships a real signed Zarf
package + GHCR image, and **szl-receipts** ships a real Pepr policy + receipts
server. **a11oy / amaru / sentra / rosie ship SBOMs only at uds-v0.3.0** (no
images, no Zarf packages) — they are **not** live cluster pods, and this scenario
does not pretend they are. The moving parts are: **vessels workload + Pepr policy
+ DSSE receipt + cosign verify.**

## Quick start

```bash
# 1. Bring up the cluster + bundle (szl-uds-deployment, ~90s from scratch):
uds run start

# 2. Run the end-to-end scenario (≤90s on a warm cache):
./scenario_drone_loses_contact.sh

# 3. Show tamper-evidence — same primitives, shown failing:
./scenario_tamper_test.sh
```

No cluster handy? Both scripts fall back to **offline fixture mode** with the
same real DSSE crypto:

```bash
OFFLINE=true ./scenario_drone_loses_contact.sh
./scenario_tamper_test.sh        # always offline (pure crypto)
```

## What's here

| File | Purpose |
|------|---------|
| `scenario_drone_loses_contact.sh` | Single bash entry point: apply workload → Pepr receipt → verify. |
| `scenario_drone_loses_contact.md` | Narrated walkthrough + 16 verifiable proof points. |
| `scenario_tamper_test.sh` | Mutate receipt payload → HMAC verify fails → server flags valid=false. |
| `fixtures/demo_workload.yaml` | The uav-7 recovery workload that triggers receipt emission. |
| `fixtures/demo_workload.json` | JSON mirror of the workload spec (offline mode). |
| `fixtures/receipt_accepted.json` | A valid signed server receipt for the workload. |
| `fixtures/receipt_chain.json` | The `/receipts` feed — one DSSE receipt per admitted workload. |
| `fixtures/tampered_receipt.json` | Mutated payload with stale sig (verify must fail). |
| `fixtures/gen_fixtures.py` | Regenerates fixtures with real HMAC-SHA-256 sigs. |

## The story

Drone **uav-7** loses its C2 link near `32.7, -117.1`. An operator deploys the
**uav7-recovery-controller** workload, whose proposed action
(`redirect_to_unauthorized_zone`) is recorded in annotations. The Pepr admission
webhook receipt-traces the Deployment the instant it hits the API server. See
`scenario_drone_loses_contact.md` for the full narration and the 16 commands.

## Verify the crypto yourself

Signatures are **real** HMAC-SHA-256, matching the production receipt contract
in `szl-uds-deployment/pepr/policies/szl-receipt-on-deploy.ts`:

- `sig = base64( HMAC-SHA-256(key, payload_bytes) )` (plain HMAC, no PAE wrapper)
- `verify: HMAC-SHA-256(key, base64decode(payload)) == base64decode(sig)`
- demo key `SZL_HMAC_KEY = c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==`
  = base64(`szl-dev-demo-key-2026-warhacker`); keyid `szl-dev-hmac-sha256-2026`
- production: Ed25519 + cosign (DSSE format unchanged, only the key type)

```bash
python3 fixtures/gen_fixtures.py     # regenerate from scratch
./scenario_tamper_test.sh            # clean=VERIFIED, tampered=UNVERIFIED
```

This is the same path as the bundle's own `scripts/verify_receipts.sh` and the
server's `_verify_dsse()`.

## Scope

In-cluster scenario only. The UDS bundle / Zarf package build is owned by Gap 1
(`szl-uds-deployment`, `uds run start`). This scenario drives the deployed Pepr
policy + receipts server and does not rebuild the bundle. No module repos
touched — `.github/docs/` only.

---
*SZL Holdings · Apache-2.0 · UNCLASSIFIED//FOUO*
