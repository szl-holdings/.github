#!/usr/bin/env python3
# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
#
# gen_fixtures.py — generate scenario fixtures with REAL DSSE HMAC-SHA-256
# signatures that match the PRODUCTION szl-receipts contract exactly.
#
# Source of truth (verified against deployed code, NOT invented):
#   - Pepr policy:   szl-uds-deployment/pepr/policies/szl-receipt-on-deploy.ts
#   - Server verify: szl-uds-deployment/charts/szl-receipts/templates/configmap.yaml
#   - CLI verify:    szl-uds-deployment/scripts/verify_receipts.sh
#
# Signing (production form — NO PAE wrapper):
#   key   = base64decode(SZL_HMAC_KEY)
#   sig   = base64( HMAC-SHA-256(key, base64decode(payload)) )
#   verify: HMAC-SHA-256(key, payload_bytes) == base64decode(sig)
#
# Demo key (published, demo-only):
#   SZL_HMAC_KEY = "c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg=="
#               = base64("szl-dev-demo-key-2026-warhacker")
#   keyid        = "szl-dev-hmac-sha256-2026"
#
# Receipt payload (_type https://szlholdings.com/receipt/v1) fields:
#   subject, specHash, timestamp, admissionOp, resourceVersion
#
# HONEST SCOPE: only vessels ships a real signed Zarf package + GHCR image.
# a11oy/amaru/sentra/rosie ship SBOMs only at uds-v0.3.0 (no images yet), so
# they are NOT live cluster pods. The moving parts here are:
#   vessels workload + Pepr szl-receipts policy + DSSE receipt + cosign/HMAC verify.

import base64
import hashlib
import hmac
import json
import os

SZL_HMAC_KEY_B64 = "c3psLWRldi1kZW1vLWtleS0yMDI2LXdhcmhhY2tlcg=="  # demo only
KEY_BYTES = base64.b64decode(SZL_HMAC_KEY_B64)
KEY_ID = "szl-dev-hmac-sha256-2026"
PAYLOAD_TYPE = "application/vnd.szl.receipt.v1+json"
RECEIPT_TYPE = "https://szlholdings.com/receipt/v1"

HERE = os.path.dirname(os.path.abspath(__file__))


def build_dsse(payload_dict):
    """DSSE envelope matching szl-receipt-on-deploy.ts exactly.

    payload bytes = JSON.stringify(payload)  (no key sorting in production)
    sig           = base64( HMAC-SHA-256(KEY_BYTES, payload_bytes) )
    """
    payload_bytes = json.dumps(payload_dict).encode()
    payload_b64 = base64.b64encode(payload_bytes).decode()
    sig = base64.b64encode(
        hmac.new(KEY_BYTES, payload_bytes, hashlib.sha256).digest()
    ).decode()
    return {
        "payload": payload_b64,
        "payloadType": PAYLOAD_TYPE,
        "signatures": [{"keyid": KEY_ID, "sig": sig}],
    }


def server_receipt(envelope):
    """Wrap an envelope the way the receipts server stores it: {id, timestamp,
    envelope, valid}. id = sha256(JSON.stringify(envelope)) (per Pepr policy)."""
    rid = hashlib.sha256(json.dumps(envelope).encode()).hexdigest()
    payload = json.loads(base64.b64decode(envelope["payload"]))
    # server _verify_dsse: HMAC(key, payload_bytes) == base64decode(sig)
    expected = hmac.new(
        KEY_BYTES, base64.b64decode(envelope["payload"]), hashlib.sha256
    ).digest()
    actual = base64.b64decode(envelope["signatures"][0]["sig"])
    valid = hmac.compare_digest(expected, actual)
    return {
        "id": rid,
        "timestamp": payload["timestamp"],
        "envelope": envelope,
        "valid": valid,
    }


def spec_hash(spec):
    """sha256 of stable-sorted spec JSON (matches Pepr sha256() helper)."""
    serialized = json.dumps(spec, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


# ── The "drone loses contact" workload spec ───────────────────────────────────
# uav-7 has lost its C2 link. An operator deploys the recovery-controller
# workload that proposes redirecting the drone. Pepr receipt-traces the admission.
DRONE_DEPLOY_SPEC = {
    "replicas": 1,
    "selector": {"matchLabels": {"app": "uav7-recovery-controller"}},
    "template": {
        "metadata": {
            "labels": {"app": "uav7-recovery-controller"},
            "annotations": {
                "szl.io/scenario": "drone-loses-contact",
                "szl.io/proposed-action": "redirect_to_unauthorized_zone",
                "szl.io/drone-id": "uav-7",
                "szl.io/lat": "32.7",
                "szl.io/lon": "-117.1",
            },
        },
        "spec": {
            "containers": [
                {
                    "name": "controller",
                    "image": "docker.io/library/busybox:1.36",
                    "command": ["sh", "-c", "echo uav-7 recovery; sleep 3600"],
                }
            ]
        },
    },
}


def build_accepted():
    """A valid, signed receipt for the admitted recovery-controller workload."""
    payload = {
        "_type": RECEIPT_TYPE,
        "subject": "szl-demo-workload/Deployment/uav7-recovery-controller",
        "specHash": spec_hash(DRONE_DEPLOY_SPEC),
        "timestamp": "2026-06-17T18:42:07Z",
        "admissionOp": "CREATE",
        "resourceVersion": "10427",
    }
    return server_receipt(build_dsse(payload))


def build_chain():
    """A 3-receipt feed as the server would return it: namespace, the drone
    recovery Deployment, and the companion Job. This is the real 'chain' — one
    DSSE receipt per admitted workload, watched cluster-wide by one Pepr policy.
    """
    ns_payload = {
        "_type": RECEIPT_TYPE,
        "subject": "szl-demo-workload/Deployment/szl-demo-agent",
        "specHash": spec_hash({"replicas": 1, "template": {"spec": {}}}),
        "timestamp": "2026-06-17T18:42:05Z",
        "admissionOp": "CREATE",
        "resourceVersion": "10401",
    }
    deploy_payload = {
        "_type": RECEIPT_TYPE,
        "subject": "szl-demo-workload/Deployment/uav7-recovery-controller",
        "specHash": spec_hash(DRONE_DEPLOY_SPEC),
        "timestamp": "2026-06-17T18:42:07Z",
        "admissionOp": "CREATE",
        "resourceVersion": "10427",
    }
    job_payload = {
        "_type": RECEIPT_TYPE,
        "subject": "szl-demo-workload/Job/uav7-telemetry-flush",
        "specHash": spec_hash({"template": {"spec": {"restartPolicy": "Never"}}}),
        "timestamp": "2026-06-17T18:42:09Z",
        "admissionOp": "CREATE",
        "resourceVersion": "10433",
    }
    receipts = [
        server_receipt(build_dsse(ns_payload)),
        server_receipt(build_dsse(deploy_payload)),
        server_receipt(build_dsse(job_payload)),
    ]
    return {
        "source": "GET /receipts (szl-receipts-server)",
        "algorithm": "DSSE HMAC-SHA-256 (demo mode); Ed25519 + cosign in production",
        "keyid": KEY_ID,
        "policy": "szl-receipt-policy (Pepr) — cluster-wide on Deployment + Job admission",
        "receipts": receipts,
    }


def build_tampered():
    """Take a valid signed receipt, then MUTATE the decoded payload (change the
    specHash, as an attacker hiding a modified workload) WITHOUT re-signing.
    HMAC(key, new_payload) != stored sig => server marks valid=false,
    verify_receipts.sh prints UNVERIFIED, cosign verify fails.
    """
    original_payload = {
        "_type": RECEIPT_TYPE,
        "subject": "szl-demo-workload/Deployment/uav7-recovery-controller",
        "specHash": spec_hash(DRONE_DEPLOY_SPEC),
        "timestamp": "2026-06-17T18:42:07Z",
        "admissionOp": "CREATE",
        "resourceVersion": "10427",
    }
    env = build_dsse(original_payload)

    # Attacker swaps the workload spec but keeps the old signature.
    tampered_payload = dict(original_payload)
    tampered_payload["specHash"] = "deadbeef" * 8  # 64 hex chars, bogus
    tampered_payload["admissionOp"] = "UPDATE"
    env_tampered = dict(env)
    env_tampered["payload"] = base64.b64encode(
        json.dumps(tampered_payload).encode()
    ).decode()
    # signatures left untouched (stale)

    rec = server_receipt(env_tampered)  # recomputes valid -> should be False
    rec["_tamper_note"] = (
        "payload specHash mutated after signing; signature is over the ORIGINAL "
        "payload bytes and will not verify"
    )
    rec["_expected_verify_result"] = "UNVERIFIED — HMAC mismatch on tampered payload"
    return rec


def main():
    outputs = {
        "receipt_accepted.json": build_accepted(),
        "receipt_chain.json": build_chain(),
        "tampered_receipt.json": build_tampered(),
        "demo_workload.json": {
            "note": "JSON mirror of scripts/demo_workload.yaml recovery spec, "
            "for offline fixture mode. Live demo applies the YAML via kubectl.",
            "namespace": "szl-demo-workload",
            "deployment": "uav7-recovery-controller",
            "spec": DRONE_DEPLOY_SPEC,
        },
    }
    for name, obj in outputs.items():
        path = os.path.join(HERE, name)
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
