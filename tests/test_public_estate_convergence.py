#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for public-estate convergence."""
from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
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
    assert proof.root_stylesheet == "/assets/szl-flow-proof.css"


def test_product_root_tracks_the_live_a11oy_front_door() -> None:
    product = convergence.CONTRACTS[0]
    assert product.root_literals == (
        "TASK-FIRST ENTRY POINTS",
        "Choose the view that matches your job.",
    )
    assert "A11oy Holographic Operations" in product.spectral_literals
    assert '"organ":"a11oy"' in product.controller_literals
    assert '"status":"ok"' in product.health_literals


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


def pages_fixture():
    """A Pages transform whose imported CSS URL makes source/served bytes differ."""
    source_css = b'@import "/assets/szl/szl-tokens.css";\n/* proof flow */\n'
    served_css = b'@import "/assets/szl/szl-tokens.' + b'a' * 64 + b'.css";\n/* proof flow */\n'
    digest = hashlib.sha256(served_css).hexdigest()
    path = f"assets/szl-flow-proof.{digest}.css"
    root = ('<!doctype html><html><head><link rel="stylesheet" href="/' + path
            + '" data-szl-proof-flow-asset="style"></head><body>Proof</body></html>').encode()
    manifest = {
        "schema": "szl.frontend-asset-manifest/v1",
        "scope": "STATIC_FRONTEND_ASSET_DELIVERY_ONLY",
        "canonical_assets_preserved": True,
        "source_revision": "2" * 40,
        "documents": {"index.html": {"served_sha256": hashlib.sha256(root).hexdigest()}},
        "assets": {"assets/szl-flow-proof.css": {
            "source_path": "assets/szl-flow-proof.css",
            "source_sha256": hashlib.sha256(source_css).hexdigest(),
            "served_path": path, "served_sha256": digest,
        }},
    }
    witness = {
        "schema_version": "a11oy-static-source-witness/v1",
        "surface": "https://a11oy.net",
        "source_repository": "https://github.com/szl-holdings/a11oy-net",
        "source_revision": "2" * 40,
        "artifact_kind": "STATIC_GITHUB_PAGES",
        "artifact_binding": "EXACT_SOURCE_REVISION",
    }
    return root, manifest, witness, source_css, served_css


def pages_probe(fixture=None, *, response_change=None):
    root, manifest, witness, source_css, served_css = fixture or pages_fixture()
    origin = "https://a11oy.net/"
    path = "assets/szl-flow-proof." + hashlib.sha256(served_css).hexdigest() + ".css"
    bodies = {
        origin: (root, "text/html"),
        origin + "frontend-assets.json": (json.dumps(manifest).encode(), "application/json"),
        origin + ".well-known/szl-source.json": (json.dumps(witness).encode(), "application/json"),
        origin + "assets/szl-flow-proof.css": (source_css, "text/css"),
        origin + path: (served_css, "text/css"),
    }

    def request(method, url, **kwargs):
        assert method == "GET" and not kwargs, "no token or mutation is admitted"
        assert url in bodies, "unexpected URL was requested: " + url
        body, content_type = bodies[url]
        response = (200, body, {"Content-Type": content_type + "; charset=utf-8"}, url)
        return response_change(url, response) if response_change else response

    with mock.patch.object(convergence, "request", side_effect=request):
        return convergence.probe(origin, (), pages_stylesheet="/assets/szl-flow-proof.css")


def test_fingerprinted_pages_stylesheet_is_semantically_and_byte_bound() -> None:
    fixture = pages_fixture()
    assert b"/assets/szl-flow-proof.css" not in fixture[0]
    result = pages_probe(fixture)
    assert result["verified"] is True
    assert result["pages_stylesheet"]["served_sha256"] == hashlib.sha256(fixture[4]).hexdigest()
    assert result["pages_stylesheet"]["source_revision"] == "2" * 40
    assert result["pages_stylesheet"]["scope"] == "DEPLOYED_STATIC_ARTIFACT_ONLY"


def test_pages_link_must_be_real_unique_enabled_and_exact() -> None:
    initial = pages_fixture()
    root = initial[0]
    variants = (
        root.replace(b"<link ", b"<!-- <link ").replace(b"></head>", b"> --></head>"),
        root.replace(b"<link ", b"<script>var fake = '<link ").replace(b"></head>", b">';</script></head>"),
        root.replace(b'rel="stylesheet"', b'rel="preload"'),
        root.replace(b'href="/assets/', b'href="https://other.example/assets/'),
        root.replace(b'href="/assets/', b'href="wrong" href="/assets/'),
        root.replace(b'<link ', b'<link disabled '),
        root.replace(b'<link ', b'<link media="print" '),
        root.replace(b'<head>', b'<head><base href="https://other.example/">'),
        root.replace(b'</head>', root[root.index(b'<link '):root.index(b'</head>')] + b'</head>'),
    )
    for changed in variants:
        fixture = list(copy.deepcopy(initial))
        fixture[0] = changed
        fixture[1]["documents"]["index.html"]["served_sha256"] = hashlib.sha256(changed).hexdigest()
        assert pages_probe(fixture)["verified"] is False, changed


def test_pages_stylesheet_in_inert_or_foreign_content_is_not_loaded() -> None:
    initial = pages_fixture()
    for tag in ("template", "noscript", "textarea", "title", "iframe", "xmp",
                "noembed", "noframes", "plaintext", "svg", "math", "select"):
        root = initial[0].replace(b"<link ", ("<" + tag + "><link ").encode())
        root = root.replace(b"></head>", ("></" + tag + "></head>").encode())
        fixture = list(copy.deepcopy(initial))
        fixture[0] = root
        fixture[1]["documents"]["index.html"]["served_sha256"] = hashlib.sha256(root).hexdigest()
        assert pages_probe(fixture)["verified"] is False, tag
    for prefix in (b"<head><template></head><head>",
                   b"<head><template><noscript></template></head><head>",
                   b"<head><plaintext></plaintext></head><head>"):
        root = initial[0].replace(b"<head>", prefix)
        fixture = list(copy.deepcopy(initial))
        fixture[0] = root
        fixture[1]["documents"]["index.html"]["served_sha256"] = hashlib.sha256(root).hexdigest()
        assert pages_probe(fixture)["verified"] is False


def test_saturated_root_read_cannot_claim_a_complete_document() -> None:
    fixture = list(pages_fixture())
    fixture[0] += b" " * (2_000_000 - len(fixture[0]))
    fixture[1]["documents"]["index.html"]["served_sha256"] = hashlib.sha256(fixture[0]).hexdigest()
    result = pages_probe(fixture)
    assert result["bytes"] == 2_000_000
    assert result["verified"] is False


def test_pages_manifest_and_witness_must_agree_on_exact_artifact() -> None:
    mutations = (
        lambda m, w: m.update(schema="other"),
        lambda m, w: m.update(scope="RUNTIME_READY"),
        lambda m, w: m.update(canonical_assets_preserved=False),
        lambda m, w: m.update(source_revision="../main"),
        lambda m, w: w.update(source_revision="3" * 40),
        lambda m, w: w.update(source_repository="https://github.com/other/repo"),
        lambda m, w: w.update(artifact_binding="UNKNOWN"),
        lambda m, w: m["documents"]["index.html"].update(served_sha256="0" * 64),
        lambda m, w: m["assets"]["assets/szl-flow-proof.css"].update(served_path="../other.css"),
        lambda m, w: m["assets"]["assets/szl-flow-proof.css"].update(source_path="other.css"),
        lambda m, w: m["assets"]["assets/szl-flow-proof.css"].update(served_sha256="not-a-digest"),
        lambda m, w: m["assets"]["assets/szl-flow-proof.css"].update(source_sha256="0" * 64),
        lambda m, w: m.update(assets=[]),
        lambda m, w: m.update(documents=None),
    )
    for mutate in mutations:
        fixture = list(pages_fixture())
        mutate(fixture[1], fixture[2])
        assert pages_probe(fixture)["verified"] is False


def test_pages_transport_and_malformed_binding_fail_closed() -> None:
    for path in ("", "frontend-assets.json", ".well-known/szl-source.json", "assets/szl-flow-proof.css"):
        for failure in ("missing", "redirect", "type", "bytes"):
            def change(url, response):
                if url != "https://a11oy.net/" + path:
                    return response
                status, body, headers, final = response
                if failure == "missing": status = 404
                elif failure == "redirect": final = "https://other.example/"
                elif failure == "type": headers = {"Content-Type": "text/plain"}
                else: body = b"invalid"
                return status, body, headers, final
            assert pages_probe(response_change=change)["verified"] is False, (path, failure)
    for malformed in (b'[]', b'{"schema":"old","schema":"new"}', b'{"value":NaN}'):
        def change(url, response):
            return (200, malformed, response[2], url) if url.endswith("frontend-assets.json") else response
        assert pages_probe(response_change=change)["verified"] is False
    def corrupt_served_css(url, response):
        if "/assets/szl-flow-proof." in url and not url.endswith("/szl-flow-proof.css"):
            return (200, response[1] + b"corrupt", response[2], url)
        return response
    assert pages_probe(response_change=corrupt_served_css)["verified"] is False


def test_all_four_existing_origin_probes_remain_required() -> None:
    for contract in convergence.CONTRACTS:
        for failed in range(4):
            results = [{"verified": i != failed} for i in range(4)]
            with mock.patch.object(convergence, "probe", side_effect=results) as probe:
                assert convergence.probe_origin(contract)["operational"] is False
            assert probe.call_count == 4


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


def test_drift_issue_lookup_does_not_shell_split_the_title() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert '--search \\"$title in:title\\"' not in text
    assert 'select(.title == "[runtime] Canonical public-origin drift")' in text


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"public-estate convergence contract: PASS ({len(tests)} tests)")
