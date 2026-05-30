# Scenario — Drone Loses Contact (running-deployment, honest)

**Event:** Warhacker, June 16–19, 2026, San Diego
**Requested by:** Andrew Greene (Defense Unicorns) — "show me a running deployment"
**Runtime:** ≤ 90 seconds on a warm cache (`uds run start` ~90s cold)
**Classification:** UNCLASSIFIED//FOUO
**Signing:** DSSE HMAC-SHA-256 (demo mode) · Ed25519 + cosign (production)
**Source talk track:** `szl-uds-deployment/docs/WARHACKER_DEMO.md`

---

## Honest scope (Doctrine V7 §10 — no theater)

Verified against `szl-uds-deployment`: only **vessels** ships a real signed Zarf
package + GHCR image, and **szl-receipts** ships a real Pepr admission policy +
receipts server. **a11oy / amaru / sentra / rosie ship SBOMs only at uds-v0.3.0**
— no images, no Zarf packages yet — so they are **not** live cluster pods. This
scenario does not pretend otherwise. The moving parts are:

```
workload (kubectl apply) → Pepr szl-receipt-policy (admission webhook)
   → DSSE HMAC-SHA-256 receipt → szl-receipts-server /receipts
   → kubectl annotations + cosign/HMAC verify    (tamper breaks it)
```

## The story (framing)

Drone **uav-7** loses its C2 link near `32.7, -117.1`. An operator deploys a
**uav7-recovery-controller** workload whose proposed action
(`redirect_to_unauthorized_zone`) is recorded in resource annotations. The
instant that Deployment hits the API server, the Pepr policy intercepts it,
computes a SHA-256 of the spec, wraps it in a DSSE envelope, annotates the
resource, and POSTs the receipt to the server — a tamper-evident governance
trail any auditor can query.

---

## Run it

```bash
uds run start                          # bring up cluster + bundle (~90s)
./scenario_drone_loses_contact.sh      # live, ≤90s
# or, with no cluster, same real crypto on fixtures:
OFFLINE=true ./scenario_drone_loses_contact.sh
./scenario_tamper_test.sh
```

---

## The DSSE receipt format (production, verified)

From `szl-uds-deployment/pepr/policies/szl-receipt-on-deploy.ts` and the server's
`_verify_dsse()`:

- **payloadType:** `application/vnd.szl.receipt.v1+json`
- **payload `_type`:** `https://szlholdings.com/receipt/v1` with fields
  `subject`, `specHash`, `timestamp`, `admissionOp`, `resourceVersion`.
- **sig:** `base64( HMAC-SHA-256(key, payload_bytes) )` — plain HMAC over the
  raw payload bytes (no PAE wrapper).
- **verify:** `HMAC-SHA-256(key, base64decode(payload)) == base64decode(sig)`.
- **keyid:** `szl-dev-hmac-sha256-2026`.
- **demo key:** `SZL_HMAC_KEY = c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==`
  = base64(`szl-dev-demo-key-2026-warhacker`). Demo only; production is Ed25519.

---

## Verifiable proof points (1 per ~5 seconds)

`$NS` = `szl-receipts`, `$WL` = `szl-demo-workload`, `$KEY` = the demo key above.

### Cluster + policy live (PP1–PP3)

**PP1 (0:05) — the receipts stack is actually running:**
```bash
kubectl get pods -n szl-receipts
```
*Expected: `szl-receipts-server` and the Pepr `pepr-szl-receipt-policy` pods `Running`.*

**PP2 (0:10) — the dashboard is reachable and the feed starts empty:**
```bash
kubectl port-forward svc/szl-receipts-server 8443:8443 -n szl-receipts &
curl -s http://localhost:8443/health | python3 -m json.tool
curl -s http://localhost:8443/receipts | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),"receipts")'
```
*Expected: health ok; `0 receipts` (nothing deployed yet).*

**PP3 (0:15) — the Pepr policy is registered cluster-wide:**
```bash
kubectl get mutatingwebhookconfigurations | grep -i pepr
```
*Expected: the szl-receipt-policy mutating webhook is listed.*

### Deploy the drone workload (PP4–PP6)

**PP4 (0:20) — apply the recovery workload (proposed AI action):**
```bash
kubectl apply -f fixtures/demo_workload.yaml
```
*Expected: namespace + `uav7-recovery-controller` Deployment + `uav7-telemetry-flush` Job created.*

**PP5 (0:25) — a receipt fires within ~5s (feed count increments):**
```bash
sleep 5; curl -s http://localhost:8443/receipts | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),"receipts")'
```
*Expected: `2`–`3 receipts` (one per admitted Deployment/Job).*

**PP6 (0:30) — the receipt annotation is on the resource (before etcd):**
```bash
kubectl get deployment uav7-recovery-controller -n szl-demo-workload \
  -o jsonpath='{.metadata.annotations}' | python3 -m json.tool
```
*Expected: `szl.receipt.id`, `szl.receipt.ts`, `szl.receipt.key=szl-dev-hmac-sha256-2026`.*

### The DSSE envelope (PP7–PP9)

**PP7 (0:35) — read one receipt envelope from the server:**
```bash
curl -s http://localhost:8443/receipts | python3 -c 'import sys,json;print(json.dumps(json.load(sys.stdin)[-1]["envelope"],indent=2))'
```
*Expected: `{payload, payloadType: application/vnd.szl.receipt.v1+json, signatures:[{keyid,sig}]}`.*

**PP8 (0:40) — decode the payload (the governance claim):**
```bash
curl -s http://localhost:8443/receipts | python3 -c 'import sys,json,base64;e=json.load(sys.stdin)[-1]["envelope"];print(json.dumps(json.loads(base64.b64decode(e["payload"])),indent=2))'
```
*Expected: `_type https://szlholdings.com/receipt/v1`, `subject=.../uav7-recovery-controller`, `specHash`, `admissionOp=CREATE`.*

**PP9 (0:45) — the proposed action is captured in the workload annotations:**
```bash
kubectl get deployment uav7-recovery-controller -n szl-demo-workload \
  -o jsonpath='{.metadata.annotations.szl\.io/proposed-action}'
```
*Expected: `redirect_to_unauthorized_zone`.*

### Verify the signatures (PP10–PP13)

**PP10 (0:50) — verify one receipt's HMAC-SHA-256 signature by hand:**
```bash
python3 - fixtures/receipt_accepted.json <<'PY'
import base64,hashlib,hmac,json,sys
key=base64.b64decode("c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==")
e=json.load(open(sys.argv[1]))["envelope"]; pb=base64.b64decode(e["payload"])
exp=hmac.new(key,pb,hashlib.sha256).digest()
print("VERIFIED" if hmac.compare_digest(exp,base64.b64decode(e["signatures"][0]["sig"])) else "UNVERIFIED")
PY
```
*Expected: `VERIFIED`.*

**PP11 (0:55) — run the bundle's own verify task against the live feed:**
```bash
uds run demo:verify          # or: SZL_HMAC_KEY=$KEY bash scripts/verify_receipts.sh
```
*Expected: `Summary: N VERIFIED, 0 UNVERIFIED out of N receipts`.*

**PP12 (1:00) — every receipt in the feed verifies:**
```bash
python3 - fixtures/receipt_chain.json <<'PY'
import base64,hashlib,hmac,json,sys
key=base64.b64decode("c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==")
def v(e):
  pb=base64.b64decode(e["payload"])
  return hmac.compare_digest(hmac.new(key,pb,hashlib.sha256).digest(),base64.b64decode(e["signatures"][0]["sig"]))
rs=json.load(open(sys.argv[1]))["receipts"]
for i,r in enumerate(rs): print(f"r{i}:","VERIFIED" if v(r["envelope"]) else "UNVERIFIED")
PY
```
*Expected: all `VERIFIED`.*

**PP13 (1:05) — the server's stored `valid` flag agrees with local verify:**
```bash
curl -s http://localhost:8443/receipts | python3 -c 'import sys,json;rs=json.load(sys.stdin);print(sum(r["valid"] for r in rs),"valid of",len(rs))'
```
*Expected: all valid.*

### Tamper-evidence (PP14–PP16)

**PP14 (1:10) — the tampered receipt FAILS verification:**
```bash
python3 - fixtures/tampered_receipt.json <<'PY'
import base64,hashlib,hmac,json,sys
key=base64.b64decode("c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==")
e=json.load(open(sys.argv[1]))["envelope"]; pb=base64.b64decode(e["payload"])
exp=hmac.new(key,pb,hashlib.sha256).digest()
print("VERIFIED" if hmac.compare_digest(exp,base64.b64decode(e["signatures"][0]["sig"])) else "UNVERIFIED (tamper detected)")
PY
```
*Expected: `UNVERIFIED (tamper detected)`.*

**PP15 (1:15) — full tamper walkthrough:**
```bash
./scenario_tamper_test.sh
```
*Expected: clean=VERIFIED, tampered=UNVERIFIED — mutation always detectable.*

**PP16 (1:20) — package provenance (the one real signed Zarf package):**
```bash
cosign verify-blob \
  --bundle uds-package-vessels-*.tar.zst.cosign.bundle \
  --certificate-identity-regexp='github.com/szl-holdings/vessels' \
  --certificate-oidc-issuer='https://token.actions.githubusercontent.com' \
  uds-package-vessels-*.tar.zst
```
*Expected: `Verified OK`. (vessels is the only module with a signed Zarf package; Gap 1 owns it.)*

---

## What this proves

- A workload's admission is **receipt-traced** automatically, cluster-wide, by a
  single Pepr policy — no per-app instrumentation.
- The receipt is a **DSSE envelope** with a real HMAC-SHA-256 signature you can
  recompute with stdlib `hmac`.
- The decision is **auditable in two places** — K8s annotations and the
  `/receipts` endpoint — with no side channel.
- **Tamper-evidence is real:** mutating the receipt payload breaks the signature
  (`scenario_tamper_test.sh`), and the server flags it `valid=false`.
- It's **honest:** vessels + Pepr are the deployable pieces; the other four
  modules are SBOM-only at uds-v0.3.0 and are not presented as live pods.
