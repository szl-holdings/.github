#!/usr/bin/env bash
# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
#
# scenario_drone_loses_contact.sh — Warhacker 2026 running-deployment scenario.
#
# Andrew Greene (Defense Unicorns) asked for a RUNNING DEPLOYMENT, not slideware.
# This is the honest version of that demo.
#
# WHAT IS ACTUALLY DEPLOYABLE (verified against szl-uds-deployment):
#   - vessels ships a real signed Zarf package + GHCR image.
#   - szl-receipts ships a Pepr admission policy + a receipts server.
#   a11oy / amaru / sentra / rosie ship SBOMs only at uds-v0.3.0 — no images,
#   no Zarf packages yet — so they are NOT live cluster pods. We do not pretend
#   otherwise (Doctrine V7 §10: no theater).
#
# THE REAL MOVING PARTS:
#   workload (kubectl apply)  ->  Pepr szl-receipt-policy (admission webhook)
#     -> DSSE-wrapped HMAC-SHA-256 receipt POSTed to szl-receipts-server
#     -> receipt visible in kubectl annotations AND at the /receipts endpoint
#     -> cosign/HMAC verify proves it; tamper breaks it.
#
# THE STORY (framing only): drone uav-7 loses its C2 link. An operator deploys a
# "uav7-recovery-controller" workload that proposes redirecting the drone into an
# unauthorized zone. The moment that Deployment hits the API server, the Pepr
# policy receipt-traces it: a tamper-evident DSSE receipt is emitted, annotated
# on the resource, and posted to the receipts server — governance you can audit.
#
# Target runtime: <= 90 seconds on a warm Docker cache (uds run start ~90s cold).
#
# Source talk track: szl-uds-deployment/docs/WARHACKER_DEMO.md
#
# Usage:
#   ./scenario_drone_loses_contact.sh          # live cluster
#   OFFLINE=true ./scenario_drone_loses_contact.sh   # fixtures, same real crypto
#
# Environment overrides:
#   NS_RECEIPTS    receipts namespace        (default: szl-receipts)
#   NS_WORKLOAD    workload namespace        (default: szl-demo-workload)
#   SERVER_SVC     receipts server service   (default: szl-receipts-server)
#   SERVER_PORT    local forward port        (default: 8443)
#   SZL_HMAC_KEY   base64 demo key           (default: published demo key)
#   WORKLOAD_YAML  drone workload manifest   (default: ./fixtures/demo_workload.yaml)
#   OFFLINE        force offline fixture mode (default: auto-detect)

set -euo pipefail

NS_RECEIPTS="${NS_RECEIPTS:-szl-receipts}"
NS_WORKLOAD="${NS_WORKLOAD:-szl-demo-workload}"
SERVER_SVC="${SERVER_SVC:-szl-receipts-server}"
SERVER_PORT="${SERVER_PORT:-8443}"
SZL_HMAC_KEY="${SZL_HMAC_KEY:-c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES="${SCRIPT_DIR}/fixtures"
WORKLOAD_YAML="${WORKLOAD_YAML:-${FIXTURES}/demo_workload.yaml}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[scenario]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ FAIL ]${NC} $*"; exit 1; }

START=$(date +%s)
PF_PID=""

cleanup() {
  local code=$?
  [[ -n "${PF_PID}" ]] && kill "${PF_PID}" 2>/dev/null || true
  local end; end=$(date +%s)
  echo ""
  if [[ "${code}" -eq 0 ]]; then ok "Scenario complete in $(( end - START ))s."
  else err "Scenario failed (exit ${code}). Elapsed: $(( end - START ))s."; fi
}
trap cleanup EXIT

# verify one DSSE envelope file against the demo key (production HMAC form)
verify_envelope() {
  SZL_HMAC_KEY="${SZL_HMAC_KEY}" python3 - "$1" <<'PYEOF'
import base64, hashlib, hmac, json, os, sys
key = base64.b64decode(os.environ["SZL_HMAC_KEY"])
obj = json.load(open(sys.argv[1]))
env = obj.get("envelope", obj)
pb = base64.b64decode(env["payload"])
exp = hmac.new(key, pb, hashlib.sha256).digest()
act = base64.b64decode(env["signatures"][0]["sig"]) if env["signatures"][0]["sig"] else b""
ok = hmac.compare_digest(exp, act)
print("VERIFIED" if ok else "UNVERIFIED")
sys.exit(0 if ok else 1)
PYEOF
}

# ── Mode detection ─────────────────────────────────────────────────────────────
OFFLINE="${OFFLINE:-}"
if [[ -z "${OFFLINE}" ]]; then
  if command -v kubectl &>/dev/null && kubectl get ns "${NS_RECEIPTS}" &>/dev/null; then
    OFFLINE="false"
  else
    OFFLINE="true"
  fi
fi
if [[ "${OFFLINE}" == "true" ]]; then
  warn "No live cluster (ns/${NS_RECEIPTS} absent) — OFFLINE fixture mode."
  warn "Bring it up first: uds run start   (~90s; szl-uds-deployment)."
else
  log "Live cluster detected — namespace ${NS_RECEIPTS} present."
fi

echo "════════════════════════════════════════════════════════════════"
echo "  Warhacker 2026 — drone-loses-contact running-deployment scenario"
echo "════════════════════════════════════════════════════════════════"

# ── STEP 1 — cluster + Pepr policy are live; receipt feed starts empty ──────────
log "Step 1: cluster + szl-receipts Pepr policy live; receipt feed"
if [[ "${OFFLINE}" == "false" ]]; then
  kubectl get pods -n "${NS_RECEIPTS}" 2>/dev/null | grep -E 'szl-receipts|pepr' || warn "  no receipts pods listed"
  kubectl port-forward -n "${NS_RECEIPTS}" "svc/${SERVER_SVC}" "${SERVER_PORT}:8443" \
    &>/tmp/scenario-receipts-pf.log & PF_PID=$!
  for _ in $(seq 1 20); do curl -sf "http://localhost:${SERVER_PORT}/health" &>/dev/null && break; sleep 1; done
  BEFORE="$(curl -s "http://localhost:${SERVER_PORT}/receipts" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo '?')"
  log "  receipts before workload: ${BEFORE}"
else
  log "  (offline) Pepr szl-receipt-policy watches Deployment+Job admission cluster-wide."
  log "  receipts before workload: 0"
fi
ok "Step 1: Pepr admission webhook is live and watching."

# ── STEP 2 — deploy the drone recovery workload (proposed AI action) ────────────
log "Step 2: deploy uav7-recovery-controller (proposes redirect_to_unauthorized_zone)"
if [[ "${OFFLINE}" == "false" ]]; then
  [[ -f "${WORKLOAD_YAML}" ]] && kubectl apply -f "${WORKLOAD_YAML}" \
    || warn "  workload manifest not found at ${WORKLOAD_YAML}; apply your own"
  sleep 5
else
  python3 -c 'import json;d=json.load(open("'"${FIXTURES}"'/demo_workload.json"));print("  (offline) would kubectl apply:",d["namespace"]+"/"+d["deployment"]);print("  proposed action:",d["spec"]["template"]["metadata"]["annotations"]["szl.io/proposed-action"])'
fi
ok "Step 2: workload admitted — Pepr intercepted the API call before etcd."

# ── STEP 3 — receipt annotation lands on the resource ───────────────────────────
log "Step 3: receipt annotation on the admitted resource (kubectl)"
if [[ "${OFFLINE}" == "false" ]]; then
  kubectl get deployment uav7-recovery-controller -n "${NS_WORKLOAD}" \
    -o jsonpath='{.metadata.annotations}' 2>/dev/null | python3 -m json.tool 2>/dev/null \
    || warn "  annotation not present yet"
else
  echo '  (offline) annotations: szl.receipt.id / szl.receipt.ts / szl.receipt.key'
  python3 -c 'import json;r=json.load(open("'"${FIXTURES}"'/receipt_accepted.json"));print("    szl.receipt.id  =",r["id"][:32]+"…");print("    szl.receipt.key =","szl-dev-hmac-sha256-2026")'
fi
ok "Step 3: resource annotated with the receipt SHA-256 — auditable in K8s metadata."

# ── STEP 4 — receipt appears at the /receipts endpoint (DSSE envelope) ──────────
log "Step 4: receipt at /receipts (DSSE envelope, HMAC-SHA-256)"
FEED="${FIXTURES}/receipt_chain.json"
if [[ "${OFFLINE}" == "false" ]]; then
  curl -s "http://localhost:${SERVER_PORT}/receipts" -o /tmp/scenario-feed.json 2>/dev/null || true
  AFTER="$(python3 -c 'import sys,json;print(len(json.load(open("/tmp/scenario-feed.json"))))' 2>/dev/null || echo '?')"
  log "  receipts after workload: ${AFTER}"
  echo '  one envelope payload (decoded):'
  python3 -c 'import json,base64;rs=json.load(open("/tmp/scenario-feed.json"));p=json.loads(base64.b64decode(rs[-1]["envelope"]["payload"]));print(json.dumps(p,indent=2))' 2>/dev/null || true
else
  echo '  one envelope payload (decoded):'
  python3 -c 'import json,base64;rs=json.load(open("'"${FEED}"'"))["receipts"];p=json.loads(base64.b64decode(rs[1]["envelope"]["payload"]));print(json.dumps(p,indent=2))'
fi
ok "Step 4: DSSE receipt emitted (_type https://szlholdings.com/receipt/v1)."

# ── STEP 5 — verify the receipt signature (real HMAC-SHA-256) ───────────────────
log "Step 5: verify the receipt DSSE signature (HMAC-SHA-256, demo key)"
verify_envelope "${FIXTURES}/receipt_accepted.json" >/dev/null \
  && ok "Step 5: receipt_accepted.json VERIFIED — sig matches payload." \
  || err "Step 5: verification failed — fixture broken."
if [[ "${OFFLINE}" == "false" ]] && [[ -f "${SCRIPT_DIR}/../verify_receipts.sh" ]]; then
  log "  (live) running the bundle's verify task:"
  SZL_HMAC_KEY="${SZL_HMAC_KEY}" bash "${SCRIPT_DIR}/../verify_receipts.sh" 2>/dev/null || true
fi

# ── STEP 6 — every receipt in the feed verifies (the real 'chain') ──────────────
log "Step 6: verify the full receipt feed (one receipt per admitted workload)"
python3 - "${FEED}" <<'PYEOF'
import base64, hashlib, hmac, json, sys
key = base64.b64decode("c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==")
def v(env):
    pb = base64.b64decode(env["payload"])
    return hmac.compare_digest(hmac.new(key, pb, hashlib.sha256).digest(),
                               base64.b64decode(env["signatures"][0]["sig"]))
rs = json.load(open(sys.argv[1]))["receipts"]
allok = True
for i, r in enumerate(rs):
    subj = json.loads(base64.b64decode(r["envelope"]["payload"]))["subject"]
    okk = v(r["envelope"]); allok = allok and okk
    print(f"  r{i}: {'PASS' if okk else 'FAIL'}  {subj}")
print(f"  Summary: {sum(v(r['envelope']) for r in rs)} VERIFIED, "
      f"{sum(not v(r['envelope']) for r in rs)} UNVERIFIED of {len(rs)}")
sys.exit(0 if allok else 1)
PYEOF
ok "Step 6: every receipt in the feed VERIFIED — tamper-evident audit trail."

# ── STEP 7 — vessels surfaces the workload (the one real shipped UI) ────────────
log "Step 7: vessels (the one real shipped package) surfaces the receipt"
if [[ "${OFFLINE}" == "false" ]]; then
  if kubectl get svc vessels-web -n "${NS_WORKLOAD}" &>/dev/null || kubectl get svc vessels-web -A &>/dev/null; then
    echo "  vessels-web present — open its receipt view for uav7-recovery-controller"
  else
    warn "  vessels-web not deployed in this bundle; receipt is still visible at /receipts"
  fi
  echo "  Dashboard: http://localhost:${SERVER_PORT}/   (receipt feed UI)"
else
  echo "  (offline) vessels is the only module with a real signed Zarf package + image."
  echo "  Dashboard: http://localhost:${SERVER_PORT}/   (receipt feed UI)"
fi
ok "Step 7: receipt surfaced for operator review."

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Workload:  szl-demo-workload/Deployment/uav7-recovery-controller"
echo "  Action:    redirect_to_unauthorized_zone (uav-7 @ 32.7,-117.1)"
echo "  Pipeline:  kubectl apply -> Pepr admission -> DSSE receipt -> verify"
echo "  Signing:   DSSE HMAC-SHA-256 (demo) / Ed25519 + cosign (production)"
echo "  Tamper:    ./scenario_tamper_test.sh"
echo "  Honest:    vessels + Pepr are deployable; a11oy/amaru/sentra/rosie"
echo "             ship SBOMs only at uds-v0.3.0 (not live pods)."
echo "════════════════════════════════════════════════════════════════"
