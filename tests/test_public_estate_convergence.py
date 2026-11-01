#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for public-estate convergence."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "public_estate_convergence.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "public-estate-convergence.yml"
SPEC = importlib.util.spec_from_file_location("public_estate_convergence", MODULE_PATH)
assert SPEC and SPEC.loader
convergence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = convergence
SPEC.loader.exec_module(convergence)


def test_two_canonical_origins_have_source_native_contracts() -> None:
    assert [row.name for row in convergence.CONTRACTS] == ["a-11-oy.com", "a11oy.net"]
    product, proof = convergence.CONTRACTS
    assert product.spectral_asset.endswith("/static/3d/holographic.html")
    assert product.controller_asset.endswith("/api/a11oy/v1/honest")
    assert product.advisory_health.endswith("/healthz")
    assert product.repair is None
    assert proof.spectral_asset.endswith("/assets/szl-spectral-proof-v2.css")
    assert proof.controller_asset.endswith("/scripts/szl-flow-proof.js")
    assert proof.repair == "A11OY_NET_PAGES_BUILD"


def test_product_root_tracks_the_live_a11oy_front_door() -> None:
    product = convergence.CONTRACTS[0]
    assert product.root_literals == (
        "TASK-FIRST ENTRY POINTS",
        "Choose the view that matches your job.",
    )
    assert "A11oy Holographic Operations" in product.spectral_literals
    assert '"organ":"a11oy"' in product.controller_literals
    assert '"status":"ok"' in product.health_literals


def test_proof_root_accepts_the_fingerprinted_stylesheet() -> None:
    proof = convergence.CONTRACTS[1]
    hashed = (
        '<link rel="stylesheet" href="/assets/szl-flow-proof.'
        'f6f4981719fabbc13fc209fce6af232f8ed53de73abea81a5ff12153b4cc2156.css" '
        'data-szl-proof-flow-asset="style" />'
    )
    with mock.patch.object(
        convergence,
        "request",
        return_value=(200, hashed.encode("utf-8"), {"Content-Type": "text/html"}, "https://a11oy.net/"),
    ):
        observed = convergence.probe(proof.root, proof.root_literals)
    assert observed["verified"] is True
    assert observed["required_literals"]["/assets/szl-flow-proof."] is True


def test_probe_requires_http_200_bytes_and_every_literal() -> None:
    with mock.patch.object(
        convergence,
        "request",
        return_value=(200, b"alpha beta", {"Content-Type": "text/plain"}, "https://example.test/"),
    ):
        assert convergence.probe("https://example.test/", ("alpha", "beta"))["verified"] is True
        assert convergence.probe("https://example.test/", ("alpha", "gamma"))["verified"] is False
    with mock.patch.object(
        convergence,
        "request",
        return_value=(404, b"alpha beta", {}, "https://example.test/"),
    ):
        assert convergence.probe("https://example.test/", ("alpha",))["verified"] is False


def test_product_has_no_misbound_pages_repair() -> None:
    product = convergence.CONTRACTS[0]
    assert product.repair is None
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "/repos/szl-holdings/szl-holdings.github.io/pages/builds" not in text


def test_proof_repair_requests_existing_pages_build_only() -> None:
    contract = convergence.CONTRACTS[1]
    with mock.patch.object(convergence, "github_action", return_value=201) as action:
        receipt = convergence.request_repair(contract, "secret")
    action.assert_called_once_with(
        "POST",
        "/repos/szl-holdings/a11oy-net/pages/builds",
        "secret",
    )
    assert receipt["source_mutation"] is False


def test_token_precedence_prefers_governed_pat() -> None:
    with mock.patch.dict(
        os.environ,
        {"GITHUB_TOKEN": "built-in", "SZL_GITHUB_TOKEN": "governed"},
        clear=True,
    ):
        assert convergence.token_from_environment() == ("governed", "SZL_GITHUB_TOKEN")


def test_source_contains_no_content_dns_cloudflare_or_hf_mutator() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "/contents/",
        "/git/refs",
        "/git/blobs",
        "/git/trees",
        "/git/commits",
        "cloudflare.com/client",
        "/dns_records",
        "hf-sync.yml/dispatches",
        "create_commit",
        "update_file",
        "delete_file",
    )
    for fragment in forbidden:
        assert fragment not in text


def test_exact_head_parity_readback() -> None:
    head = "9be0cdb392f5fba9225d7284813191578a14c766"
    match = convergence.parity_readback(head, head, head)
    assert match["state"] == "MATCH"
    assert match["source_mutation"] is False
    assert match["hf_mutation"] is False
    assert match["runtime_mutation"] is False
    drifted = convergence.parity_readback(head, head, "a" * 40)
    assert drifted["state"] == "DIVERGENT"
    assert convergence.parity_readback(head, "", head)["state"] == "NOT_SUPPLIED"


def test_signed_receipt_validation_fails_closed() -> None:
    payload = {"url": "https://a11oy.net/", "verified": True}
    digest = convergence.hashlib.sha256(convergence.canonical_payload(payload)).hexdigest()
    unsigned = convergence.proof_envelope(
        {
            "url": payload["url"],
            "http_status": 200,
            "bytes": 12,
            "verified": True,
            "required_literals": {},
        }
    )
    assert unsigned["signed"] is False
    assert unsigned["algorithm"] == "UNSIGNED"
    assert convergence.validate_signed_receipt(unsigned)["reason"] == "UNSIGNED"
    mismatched = {
        "payload": payload,
        "payload_sha256": "0" * 64,
        "algorithm": "ed25519",
        "signed": True,
        "signature": "ab" * 32,
    }
    assert convergence.validate_signed_receipt(mismatched)["reason"] == "PAYLOAD_HASH_MISMATCH"
    unbound = {
        "payload": payload,
        "payload_sha256": digest,
        "algorithm": "ed25519",
        "signed": True,
        "signature": "ab" * 32,
    }
    result = convergence.validate_signed_receipt(unbound)
    assert result["valid"] is False
    assert result["reason"] == "NO_PINNED_PUBLIC_KEY"


def test_rights_state_gate_blocks_undeclared_effects() -> None:
    product, proof = convergence.CONTRACTS
    assert convergence.rights_state(product) == "OBSERVE"
    assert convergence.rights_state(proof) == "REPAIR_DECLARED"
    blocked = convergence.OriginContract(
        name="blocked.example",
        root="https://blocked.example/",
        spectral_asset="https://blocked.example/a",
        controller_asset="https://blocked.example/b",
        root_literals=(),
        spectral_literals=(),
        controller_literals=(),
        advisory_health="https://blocked.example/health",
        health_literals=(),
        repair="UNDECLARED",
    )
    assert convergence.rights_state(blocked) == "BLOCKED"
    for right in ("publish", "merge", "train", "dns", "credentials", "billing", "security-settings"):
        assert convergence.rights_permit("OBSERVE", right) is False
        assert convergence.rights_permit("REPAIR_DECLARED", right) is False
        assert convergence.rights_permit("BLOCKED", right) is False
    assert convergence.rights_permit("OBSERVE", "read") is True
    assert convergence.rights_permit("REPAIR_DECLARED", "pages-build-request") is True
    assert convergence.rights_permit("OBSERVE", "pages-build-request") is False


def test_rollback_leaves_main_and_live_workloads_untouched() -> None:
    assert "Do not touch protected main" in convergence.ROLLBACK
    assert "close the PR" in convergence.ROLLBACK
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "source_mutation" in text
    assert convergence.proof_envelope(
        {"url": "https://a11oy.net/", "http_status": 200, "bytes": 1, "verified": False, "required_literals": {}}
    )["source_mutation"] is False


def test_drift_receipt_is_a_structured_log_without_an_issue_write() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert '--search \\"$title in:title\\"' not in text
    assert "gh issue" not in text
    assert "issues: write" not in text.lower()
    assert "contents: read" in text
    assert "/tmp/public-origin-drift.json" in text
    assert '"issue_write": False' in text
    receipt = text.split("Emit the public-origin drift receipt", 1)[1].split(
        "- name: Upload immutable convergence evidence", 1
    )[0]
    assert "set -euo pipefail" in receipt
    assert "set +e" not in receipt
    assert "exit 0" not in receipt


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"public-estate convergence contract: PASS ({len(tests)} tests)")
