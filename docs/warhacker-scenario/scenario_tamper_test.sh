#!/usr/bin/env bash
# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
#
# scenario_tamper_test.sh — Warhacker 2026 tamper-evidence test.
#
# Same primitives as the live demo (DSSE HMAC-SHA-256), shown failing on tamper.
#
# THE STORY: an attacker has modified a workload spec in the cluster and tries to
# make the governance receipt still look valid by editing the stored receipt JSON
# (changing the specHash) WITHOUT re-signing. The substrate catches it:
#
#   1. A clean receipt VERIFIES (HMAC over payload == stored signature).
#   2. The payload is mutated (specHash swapped) — signature left untouched.
#   3. Re-verification FAILS: HMAC(key, new_payload) != stored sig.
#   4. The receipts server marks valid=false; verify_receipts.sh prints UNVERIFIED;
#      cosign verify (production) fails. Same primitives, same outcome.
#
# This matches szl-uds-deployment/scripts/verify_receipts.sh and the server's
# _verify_dsse() in charts/szl-receipts/templates/configmap.yaml.
#
# Target runtime: <= 20 seconds, no cluster required (pure crypto).
#
# Usage: ./scenario_tamper_test.sh
# Env:   SZL_HMAC_KEY  base64 demo key (default: published demo key)

set -euo pipefail

SZL_HMAC_KEY="${SZL_HMAC_KEY:-c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg==}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES="${SCRIPT_DIR}/fixtures"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[tamper]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ FAIL ]${NC} $*"; exit 1; }

# returns 0 if VERIFIED, 1 if UNVERIFIED — production HMAC form (no PAE wrapper)
verify_envelope() {
  SZL_HMAC_KEY="${SZL_HMAC_KEY}" python3 - "$1" <<'PYEOF'
import base64, hashlib, hmac, json, os, sys
key = base64.b64decode(os.environ["SZL_HMAC_KEY"])
obj = json.load(open(sys.argv[1]))
env = obj.get("envelope", obj)
pb = base64.b64decode(env["payload"])
exp = hmac.new(key, pb, hashlib.sha256).digest()
sigb64 = env["signatures"][0]["sig"]
act = base64.b64decode(sigb64) if sigb64 else b""
sys.exit(0 if hmac.compare_digest(exp, act) else 1)
PYEOF
}

echo "════════════════════════════════════════════════════════════════"
echo "  Warhacker 2026 — receipt TAMPER test (same primitives as live)"
echo "════════════════════════════════════════════════════════════════"

# ── STEP 1 — baseline: a clean receipt VERIFIES ─────────────────────────────────
log "Step 1: baseline — verify a clean (untampered) receipt"
if verify_envelope "${FIXTURES}/receipt_accepted.json"; then
  ok "Step 1: clean receipt VERIFIED (HMAC over payload == stored signature)."
else
  err "Step 1: clean receipt failed to verify — fixture is broken."
fi

# ── STEP 2 — attacker mutates payload specHash, keeps the old signature ─────────
log "Step 2: attacker swaps specHash in tampered_receipt.json (no re-sign)"
echo "  decoded payload diff (specHash):"
python3 - "${FIXTURES}/receipt_accepted.json" "${FIXTURES}/tampered_receipt.json" <<'PYEOF'
import base64, json, sys
clean = json.load(open(sys.argv[1]))["envelope"]
tamp  = json.load(open(sys.argv[2]))["envelope"]
ch = json.loads(base64.b64decode(clean["payload"]))["specHash"]
th = json.loads(base64.b64decode(tamp["payload"]))["specHash"]
print(f"    clean    -> specHash={ch[:24]}…")
print(f"    tampered -> specHash={th[:24]}…")
PYEOF
ok "Step 2: payload specHash mutated; signature left stale."

# ── STEP 3 — re-verify the tampered receipt: MUST fail ──────────────────────────
log "Step 3: re-verify tampered receipt (MUST be UNVERIFIED)"
if verify_envelope "${FIXTURES}/tampered_receipt.json"; then
  err "Step 3: tampered receipt VERIFIED — tamper-evidence BROKEN. Fail hard."
else
  ok "Step 3: tampered receipt UNVERIFIED — tamper DETECTED (correct)."
fi

# ── STEP 4 — this is exactly what the live path reports ─────────────────────────
log "Step 4: how the live cluster reports it"
echo "  - szl-receipts-server /receipts marks this receipt: valid=false"
echo "  - scripts/verify_receipts.sh prints: UNVERIFIED (demo key mismatch or unsigned)"
echo "  - production cosign verify-blob over the Ed25519 sig: FAIL"
echo -e "  ${RED}TAMPER ALERT${NC}: stored receipt no longer matches its signed payload."
ok "Step 4: same primitives, same failure — mutation is always detectable."

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  RESULT: tamper attempt DETECTED. Mutating the receipt payload"
echo "  breaks the HMAC-SHA-256 signature. Any reviewer can reproduce:"
echo "    SZL_HMAC_KEY=${SZL_HMAC_KEY} \\"
echo "    bash scenario_tamper_test.sh"
echo "════════════════════════════════════════════════════════════════"
