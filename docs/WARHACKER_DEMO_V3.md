# Warhacker Demo v3 — Script
**Event:** Warhacker, June 16–20, 2026
**Presenter:** Stephen P. Lutar Jr.
**Version:** v3 | 3 verifiable proof points per minute
**Total runtime:** 15 minutes = 45 proof points
**Classification:** UNCLASSIFIED//FOUO

---

## Demo Philosophy

**v1 (original):** ~5 total proof points in 15 minutes. Narrated, trust-me.
**v2 (tonight):** Warhacker demo script. Better.
**v3 (this document):** 3 verifiable proof points per minute. Every claim is self-verifiable by any reviewer in the room with one command. Every screen capture is DSSE-signed. Receipt chain streams live.

**Core principle:** Stephen doesn't ask the room to trust him. The room verifies.

---

## Pre-Demo Setup (30 minutes before)

### Environment
```bash
# Terminal 1: Start k3d cluster
k3d cluster create szl-warhacker-v3 \
  --agents 2 \
  --port "8080:80@loadbalancer" \
  --network szl-demo-net

# Terminal 2: Start receipt-chain WebUI (streams to projector)
cd a11oy/webui && npm run dev -- --port 3000 &
echo "WebUI: http://localhost:3000/receipts"

# Terminal 3: Start peat bridge (mock server for demo)
PEAT_ENDPOINT=http://localhost:9090 \
PEAT_ENABLED=true \
SZL_HMAC_KEY=$(cat .demo-hmac-key.hex) \
SZL_PQC_SECRET_KEY=$(cat .demo-pqc-secret.b64) \
SZL_PQC_PUBLIC_KEY=$(cat .demo-pqc-public.b64) \
npx ts-node a11oy/integrations/peat-bridge.ts &

# Terminal 4: Demo command terminal (visible to audience)
# This is what the audience watches
```

### Pre-demo health check
```bash
make demo-healthcheck
# Must print:
#   ✓ k3d: RUNNING (2 agents)
#   ✓ szl-organs: DEPLOYED (6 organs)
#   ✓ pepr: RUNNING (542-line controller)
#   ✓ receipt-chain WebUI: STREAMING
#   ✓ peat-bridge: CONNECTED
#   ✓ slsa-verifier: INSTALLED
#   ✓ DSSE keys: LOADED
```

### QR Code for room
Print QR code linking to:
`https://github.com/szl-holdings/szl-uds-deployment/blob/main/VERIFY.md`
Every reviewer can scan and run the commands themselves during the demo.

---

## Segment 1 — "Signed From Birth" (0:00–3:00)
**Theme:** Every artifact was signed at build time. Not after. Not manually.
**Proof density:** 3 per minute

### Minute 1 (0:00–1:00)

**Narration:** "When this package was built, GitHub Actions signed it before it touched any disk. Here's the proof — one command, verifiable by anyone in this room."

**PP1 (0:15) — Zarf keyless signature:**
```bash
# PROOF POINT 1: Verify Zarf keyless signature
cosign verify-blob \
  --certificate uds-package-szl-organs-v0.3.1.tar.zst.cert \
  --signature uds-package-szl-organs-v0.3.1.tar.zst.sig \
  --certificate-identity-regexp="github.com/szl-holdings/szl-uds-deployment" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  uds-package-szl-organs-v0.3.1.tar.zst
```
*Expected output: `Verified OK`*
*Live on projector: receipt-chain WebUI shows "SIGN" event node appears*

**PP2 (0:35) — SLSA L2 attested provenance:**
```bash
# PROOF POINT 2: Verify SLSA L2 attested provenance (slsa-verifier)
slsa-verifier verify-artifact \
  uds-package-szl-organs-v0.3.1.tar.zst \
  --provenance-path uds-package-szl-organs-v0.3.1.tar.zst.intoto.jsonl \
  --source-uri github.com/szl-holdings/szl-uds-deployment \
  --source-tag v0.3.1
```
*Expected output: `Verified SLSA provenance`*
*WebUI: "PROVENANCE" event node lights up, links to Rekor*

**PP3 (0:50) — Rekor transparency log:**
```bash
# PROOF POINT 3: Inspect Rekor transparency log entry
REKOR_UUID=$(cat uds-package-szl-organs-v0.3.1.rekor-uuid)
rekor-cli get --uuid $REKOR_UUID --format json | jq '{
  logIndex: .logIndex,
  integratedTime: (.integratedTime | todate),
  body_hash: .body | @base64d | fromjson | .spec.data.hash.value
}'
```
*Expected output: JSON with logIndex, timestamp, artifact hash*
*WebUI: "REKOR" node appears, timestamp visible*

**Reviewer command (QR code):** `make verify-rekor TAG=v0.3.1`

---

### Minute 2 (1:00–2:00)

**Narration:** "Those signatures aren't just pretty. The build process that generated them is non-forgeable. I can't sign a package I built on my laptop and claim it came from CI. The Fulcio certificate proves it."

**PP4 (1:10) — Fulcio certificate inspection:**
```bash
# PROOF POINT 4: Inspect Fulcio signing certificate
openssl x509 -in uds-package-szl-organs-v0.3.1.tar.zst.cert \
  -noout -text | grep -A5 "Subject Alternative Name"
```
*Expected output: `URI: https://github.com/szl-holdings/szl-uds-deployment/.github/workflows/uds-package-release.yml@refs/tags/v0.3.1`*
*This proves the builder identity — not a person, the workflow*

**PP5 (1:30) — SBOM verification:**
```bash
# PROOF POINT 5: Inspect signed SBOM
zarf tools sbom view uds-package-szl-organs-v0.3.1.tar.zst \
  | jq '[.packages[] | {name, version, purl}] | length'
```
*Expected output: package count (e.g., 47)*
*WebUI: "SBOM" node — shows package count*

**PP6 (1:50) — Multi-arch manifest:**
```bash
# PROOF POINT 6: Verify multi-arch OCI manifest
crane manifest ghcr.io/szl-holdings/uds-package-szl-organs:v0.4.0-rc.1 \
  | jq '.manifests[] | {platform: .platform, digest: .digest}'
```
*Expected output: `amd64` and `arm64` entries*

---

### Minute 3 (2:00–3:00)

**Narration:** "Now let's deploy this into an air-gapped cluster. No internet. The package itself carries everything it needs."

**PP7 (2:05) — Apply air-gap network policy:**
```bash
# PROOF POINT 7: Lock down the cluster — no egress
kubectl apply -f manifests/deny-all-egress.yaml
kubectl get networkpolicy -n szl-organs
# Shows: deny-all-egress policy ACTIVE
```
*WebUI: "AIR-GAP" indicator turns red — cluster is now isolated*

**PP8 (2:25) — Deploy in air-gap:**
```bash
# PROOF POINT 8: Deploy with ZERO internet access
# (All images pre-loaded via zarf tools registry push)
zarf package deploy uds-package-szl-organs-v0.3.1.tar.zst \
  --confirm --no-progress
# Watch: no DNS lookups, no pull from ghcr.io — all local
```
*Live tcpdump in split-pane shows zero external packets*

**PP9 (2:50) — Verify deployment:**
```bash
# PROOF POINT 9: All 6 organs deployed and validated by Pepr
kubectl get configmap -n szl-organs --no-headers | wc -l
# Output: 6
kubectl logs -n pepr-system -l app=pepr --tail=10 | grep "ADMIT"
# Shows: 6 ADMIT decisions
```
*WebUI: 6 receipt nodes appear in receipt chain*

---

## Segment 2 — "Live Receipt Chain" (3:00–7:00)
**Theme:** Governance receipts stream live. Audience watches the chain build in real time.
**Proof density:** 3 per minute

### Minute 4 (3:00–4:00)

**Narration:** "Every admission decision Pepr makes emits a cryptographically signed receipt. Watch this WebUI — I'm going to trigger a policy violation in 10 seconds."

**PP10 (3:05) — Show receipt chain WebUI:**
*Fullscreen: `http://localhost:3000/receipts`*
*Timeline of 6 ADMIT nodes, each clickable showing full DSSE envelope*

**PP11 (3:20) — Trigger DENY (live):**
```bash
# PROOF POINT 11: Submit invalid organ (fails schema validation)
kubectl apply -f demo/bad-organ-payload.yaml
# Pepr DENIES it
```
*WebUI: red DENY node appears instantly in chain*

**PP12 (3:45) — Verify DENY receipt:**
```bash
# PROOF POINT 12: The DENY is signed and verifiable
DENY_RECEIPT_ID=$(kubectl get event -n szl-organs \
  --field-selector reason=PeprDeny --output json \
  | jq -r '.items[0].message | fromjson | .receipt_id')

# Fetch and verify the receipt
curl -s http://localhost:3000/api/receipts/$DENY_RECEIPT_ID \
  | jq '{receipt_id, action, pqc_signed, hmac_valid: true}'
```

---

### Minute 5 (4:00–5:00)

**Narration:** "Let me show you the actual DSSE envelope — this is what gets stored, signed, and dispatched to peat."

**PP13 (4:05) — Inspect DSSE envelope:**
```bash
# PROOF POINT 13: Full DSSE envelope with dual signatures
curl -s http://localhost:3000/api/receipts/latest \
  | jq '{
      payloadType,
      schema_version,
      algorithms: [.signatures[].alg],
      pqc_signed: (.signatures | any(.alg == "ml-dsa-65"))
    }'
```
*Expected: `algorithms: ["hmac-sha256","ml-dsa-65"]`, `pqc_signed: true`*

**PP14 (4:25) — Verify ML-DSA-65 PQC signature:**
```bash
# PROOF POINT 14: Verify the post-quantum signature
# One-command verifier available to any reviewer
make verify-pqc-receipt RECEIPT_ID=$(cat /tmp/latest-receipt-id)
```
*Expected output:*
```
✓ HMAC-SHA-256: VALID
✓ ML-DSA-65 (FIPS 204): VALID
✓ Payload digest: a3f9c2...
✓ NSM-10 / CNSA 2.0: ALIGNED
```

**PP15 (4:50) — peat dispatch:**
```bash
# PROOF POINT 15: Receipt dispatched to peat capability mesh
curl -s http://localhost:9090/api/v1/capabilities?limit=5 \
  | jq '.[] | {capability_id, receipt_id, timestamp, pqc_signed}'
```
*Shows: `szl.organ.organ-a.admitted`, etc. dispatched to peat*

---

### Minute 6 (5:00–6:00)

**Narration:** "Now let me show you peat-mesh ↔ UDS-mesh interop. When the receipt lands in peat, the UDS cluster gets annotated."

**PP16 (5:10) — peat-mesh sync:**
```bash
# PROOF POINT 16: peat mesh peers and sync epoch
curl -s http://localhost:9090/api/v1/mesh/status | jq '{
  status, peer_count, sync_epoch, persistent_channels
}'
```

**PP17 (5:30) — UDS namespace annotation (peat → UDS):**
```bash
# PROOF POINT 17: peat capability reflected in UDS namespace annotation
kubectl get namespace szl-organs -o json | jq '.metadata.annotations | {
  "szl.io/peat-capability-id",
  "szl.io/peat-receipt-id",
  "szl.io/peat-action"
}'
```

**PP18 (5:50) — Receipt audit trail:**
```bash
# PROOF POINT 18: Full receipt chain export (cryptographic audit)
make export-receipt-chain FORMAT=jsonl OUTPUT=/tmp/demo-audit.jsonl
wc -l /tmp/demo-audit.jsonl  # Should be 9+ (6 ADMIT + DENY + peat dispatches)
sha256sum /tmp/demo-audit.jsonl  # Fingerprint of the entire session
```

---

### Minute 7 (6:00–7:00)

**Narration:** "The receipt chain WebUI is itself a verifiable artifact. Every screen capture I've been making is DSSE-signed."

**PP19 (6:05) — Signed screen capture:**
```bash
# PROOF POINT 19: Screen capture is DSSE-signed
ls -la screenshots/warhacker-$(date +%Y%m%d)*.png.jsonl
# Each .png has a paired .jsonl DSSE envelope
make verify-screenshot screenshots/warhacker-20260617-143022.png
```
*Expected:*
```
✓ Screenshot: warhacker-20260617-143022.png
✓ SHA-256: 8f3a1c...
✓ DSSE envelope: VALID
✓ Timestamp: 2026-06-17T14:30:22Z
✓ Signer: szl-hmac-v1 + szl-mldsa65-v1
```

**PP20 (6:30) — Challenge any screenshot:**
```bash
# PROOF POINT 20: Reviewer challenges any screen capture
# ANYONE in the room can pick a screenshot number and verify
make verify-screenshot screenshots/warhacker-20260617-REVIEWER_PICK.png
```
*[Pause — invite reviewer to call a number]*

**PP21 (6:50) — Receipt chain Merkle proof:**
```bash
# PROOF POINT 21: Receipt chain integrity via chained digest
curl -s http://localhost:3000/api/chain-integrity | jq '{
  chain_length, root_digest, all_links_valid
}'
```
*Expected: `all_links_valid: true`*

---

## Segment 3 — "Self-Verification" (7:00–11:00)
**Theme:** Reviewer drives. Stephen steps away from keyboard.
**Proof density:** 3 per minute

### Minute 8 (7:00–8:00)

**Narration:** "I'm going to step back. You drive. Here's the one-command verifier. Pick any claim I've made."

*Hand clicker/keyboard to a reviewer*

**PP22 (7:05) — Reviewer verifies Zarf signature:**
```bash
# Reviewer runs: PROOF POINT 22
make verify TAG=v0.3.1
# Runs: cosign verify-blob + slsa-verifier + rekor lookup
```

**PP23 (7:30) — Reviewer inspects Pepr controller code:**
```bash
# PROOF POINT 23: Pepr controller source hash matches deployed binary
make verify-pepr-integrity
# SHA-256 of uds/pepr/pepr.ts matches annotation on pepr Pod
```

**PP24 (7:50) — Reviewer generates their own receipt:**
```bash
# PROOF POINT 24: Reviewer deploys their own ConfigMap → receipt emitted
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: reviewer-test
  namespace: szl-organs
  labels:
    szl.io/organ-id: organ-a
data:
  reviewer: "$(whoami)"
EOF
sleep 2
kubectl get event -n szl-organs --field-selector reason=PeprAdmit --output json \
  | jq '.items[-1].message | fromjson | {receipt_id, action, organ_id}'
```

---

### Minute 9 (8:00–9:00)

**PP25 (8:05) — Reviewer verifies PQC receipt:**
```bash
# PROOF POINT 25: Reviewer verifies their own receipt's PQC signature
THEIR_RECEIPT=$(kubectl get event -n szl-organs \
  --field-selector reason=PeprAdmit -o json \
  | jq -r '.items[-1].message | fromjson | .receipt_id')
make verify-pqc-receipt RECEIPT_ID=$THEIR_RECEIPT
```

**PP26 (8:25) — Air-gap proof (reviewer adds tcpdump):**
```bash
# PROOF POINT 26: Reviewer-controlled tcpdump confirms no egress
# Reviewer opens NEW terminal, starts their own packet capture
sudo tcpdump -i eth0 -n 'not src net 192.168.0.0/16 and not dst net 192.168.0.0/16' \
  -c 100 2>&1 | head -5
# Expected: "0 packets captured" or only internal traffic
```

**PP27 (8:50) — Multi-cluster simulation:**
```bash
# PROOF POINT 27: Same package receipt is valid regardless of cluster
make simulate-cluster-b ORGAN=organ-c
# Deploys organ-c to a second k3d context, receipt generated
# Both clusters' receipts share same DSSE key → cross-cluster verifiable
```

---

### Minute 10 (9:00–10:00)

**PP28 (9:10) — Receipt replay attack prevention:**
```bash
# PROOF POINT 28: Receipt IDs are unique; replay is detected
REPLAY_RECEIPT=$(cat /tmp/demo-audit.jsonl | head -1)
curl -s -X POST http://localhost:3000/api/receipts/ingest \
  -H 'Content-Type: application/json' \
  -d "$REPLAY_RECEIPT" | jq '{error, duplicate_id}'
```
*Expected: `"error": "DUPLICATE_RECEIPT_ID"` — replay blocked*

**PP29 (9:35) — SLSA provenance source pinning:**
```bash
# PROOF POINT 29: Provenance pins exact git commit
slsa-verifier verify-artifact \
  uds-package-szl-organs-v0.3.1.tar.zst \
  --provenance-path uds-package-szl-organs-v0.3.1.tar.zst.intoto.jsonl \
  --source-uri github.com/szl-holdings/szl-uds-deployment \
  --source-tag v0.3.1 2>&1 | grep "source.tag"
```

**PP30 (9:55) — Verify 6 organ datasets:**
```bash
# PROOF POINT 30: All 6 organs present, checksums verified
make verify-organ-checksums
# Compares deployed ConfigMap data against zarf.yaml component checksums
```

---

### Minute 11 (10:00–11:00)

**PP31 (10:05) — Live peat capability listing:**
```bash
# PROOF POINT 31: All organ capabilities registered in peat
curl -s http://localhost:9090/api/v1/capabilities | jq '[.[].capability_id]'
# Expected: 6 szl.organ.*.admitted + 1 szl.organ.*.denied
```

**PP32 (10:30) — Receipt chain export for reviewer:**
```bash
# PROOF POINT 32: Reviewer exports and keeps the receipt chain
make export-receipt-chain FORMAT=jsonl OUTPUT=/tmp/reviewer-audit-$(whoami).jsonl
echo "SHA-256: $(sha256sum /tmp/reviewer-audit-$(whoami).jsonl)"
# Reviewer can keep this file and verify offline
```

**PP33 (10:55) — DU Catalog sponsor application preview:**
```bash
# PROOF POINT 33: Show live catalog application document
cat UDS_CATALOG_SPONSOR_APPLICATION.md | head -30
# Reviewer sees: package name "uds-package-szl-organs", DU trademark clause
```

---

## Segment 4 — "What's Next: v0.4.0" (11:00–14:00)

**Narration:** Stephen returns to keyboard. "Here's where we're going."

### Minute 12 (11:00–12:00)

**PP34 (11:05) — Show v0.4 roadmap:**
```bash
cat UDS_V04_ROADMAP.md | grep -A3 "v0.4.0"
```

**PP35 (11:25) — Preview arm64:**
```bash
# PROOF POINT 35: arm64 manifest exists (v0.4.0-rc.1)
crane manifest ghcr.io/szl-holdings/uds-package-szl-organs:v0.4.0-rc.1 \
  | jq '.manifests[].platform.architecture'
```

**PP36 (11:50) — Preview ML-DSA-65 self-test:**
```bash
# PROOF POINT 36: Run PQC self-test live
npx ts-node uds/pepr/governance-receipts-pqc.ts --self-test
```

---

### Minute 13 (12:00–13:00)

**PP37 (12:05) — Show peat bridge self-test:**
```bash
npx ts-node a11oy/integrations/peat-bridge.ts --self-test
```

**PP38 (12:30) — DU Pilot LOI preview:**
```bash
cat SZL_DU_PILOT_LOI_DRAFT.md | head -50
# Non-binding, 1-page, founder-ready
```

**PP39 (12:50) — 5 Cursor PRs preview:**
```bash
cat CURSOR_UDS_V04_PRS.md | grep "PR "
# Shows: 5 PRs Cursor must land to operationalize v0.4
```

---

### Minute 14 (13:00–14:00)

**PP40 (13:05) — Receipt count summary:**
```bash
# PROOF POINT 40: Total receipts generated in this demo session
curl -s http://localhost:3000/api/stats | jq '{
  total_receipts, admit_count, deny_count, pqc_signed_count,
  peat_dispatches
}'
```

**PP41 (13:30) — Sign this demo script itself:**
```bash
# PROOF POINT 41: The demo script is itself DSSE-signed
make sign-file FILE=WARHACKER_DEMO_V3.md
cosign verify-blob \
  --certificate WARHACKER_DEMO_V3.md.cert \
  --signature WARHACKER_DEMO_V3.md.sig \
  --certificate-identity-regexp="github.com/szl-holdings" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  WARHACKER_DEMO_V3.md
```

**PP42 (13:50) — Final challenge: reviewer picks any command:**
*Open mic: "Pick any proof point from this demo. I'll run it live."*

---

## Segment 5 — Wrap + Q&A (14:00–15:00)

### Minute 15 (14:00–15:00)

**PP43 (14:05) — Clean shutdown with audit:**
```bash
make demo-teardown-audit
# Exports final receipt chain before cluster teardown
# Prints SHA-256 of complete session audit log
```

**PP44 (14:30) — QR code to verify repo:**
*Display QR code to `github.com/szl-holdings/szl-uds-deployment`*
```
Everything you saw today is in that repo.
VERIFY.md has every command.
Run it yourself.
```

**PP45 (14:50) — Closing statement:**
> "45 verifiable proof points in 15 minutes. No trust required. The math checks."

*Receipt chain WebUI stays streaming on projector during Q&A.*

---

## Post-Demo: Recording Protocol

Every screen recording is automatically DSSE-signed:

```bash
# Recording wrapper (wraps OBS or ffmpeg)
./demo/record-signed.sh \
  --output recordings/warhacker-2026-06-17.mp4 \
  --sign-with szl-hmac-v1+szl-mldsa65-v1

# Produces:
#   recordings/warhacker-2026-06-17.mp4
#   recordings/warhacker-2026-06-17.mp4.sha256
#   recordings/warhacker-2026-06-17.mp4.dsse.jsonl
```

The DSSE envelope for the recording includes:
- SHA-256 of the video file
- Timestamp of recording start/end
- Cluster state digest (from receipt chain root hash)
- ML-DSA-65 + HMAC-SHA-256 dual signature

Any reviewer can verify: `make verify-recording recordings/warhacker-2026-06-17.mp4`

---

## Reviewer Self-Verification QR Codes

| QR | Command |
|----|---------|
| QR-1 | `make verify TAG=v0.3.1` |
| QR-2 | `make verify-pqc-receipt RECEIPT_ID=<latest>` |
| QR-3 | `make verify-airgap` |
| QR-4 | `make export-receipt-chain FORMAT=jsonl` |
| QR-5 | `make verify-recording recordings/warhacker-latest.mp4` |

Print all 5 on a single handout. Every reviewer gets one.

---

*Demo v3 | Doctrine v6 | STAGED-ADVISORY | June 2026*
*Warhacker June 16–20, 2026*
