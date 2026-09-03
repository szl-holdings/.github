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
SPEC = importlib.util.spec_from_file_location("public_estate_convergence", MODULE_PATH)
assert SPEC and SPEC.loader
convergence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = convergence
SPEC.loader.exec_module(convergence)


def test_two_canonical_origins_have_source_native_visual_contracts() -> None:
    assert [row.name for row in convergence.CONTRACTS] == ["a-11-oy.com", "a11oy.net"]
    product, proof = convergence.CONTRACTS
    assert product.spectral_asset.endswith("/assets/szl-responsive-apex-v3.css")
    assert product.controller_asset.endswith("/assets/szl-responsive-apex-v3.js")
    assert product.advisory_health.endswith("/origin-status.json")
    assert product.repair == "PRODUCT_PAGES_BUILD"
    assert proof.spectral_asset.endswith("/assets/szl-spectral-proof-v2.css")
    assert proof.controller_asset.endswith("/scripts/szl-flow-proof.js")
    assert proof.repair == "A11OY_NET_PAGES_BUILD"


def test_product_root_requires_both_published_responsive_assets() -> None:
    product = convergence.CONTRACTS[0]
    assert product.root_literals == (
        "/assets/szl-responsive-apex-v3.css",
        "/assets/szl-responsive-apex-v3.js",
    )
    assert "SZL Apex Responsive Experience v3" in product.spectral_literals
    assert "__SZL_APEX_RESPONSIVE_V3__" in product.controller_literals


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


def test_product_repair_requests_the_actual_front_door_pages_build() -> None:
    contract = convergence.CONTRACTS[0]
    with mock.patch.object(convergence, "github_action", return_value=201) as action:
        receipt = convergence.request_repair(contract, "secret")
    action.assert_called_once_with(
        "POST",
        "/repos/szl-holdings/szl-holdings.github.io/pages/builds",
        "secret",
    )
    assert receipt["source_mutation"] is False
    assert receipt["action"] == "PRODUCT_PAGES_BUILD"


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


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"public-estate convergence contract: PASS ({len(tests)} tests)")
