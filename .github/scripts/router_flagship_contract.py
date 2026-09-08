#!/usr/bin/env python3
"""Validate the SZL Router flagship authority and presentation contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "szl.router-flagship/v1"
SOURCE = "szl-holdings/szl-router"
SPACE = "SZLHOLDINGS/llm-router-live"
PRODUCT = "https://a-11-oy.com/code"
PROOF = "https://a11oy.net"
ASSET = "profile/assets/hf-card-router.svg"
MANIFEST_DESTINATION = "assets/hf-card-router.svg"
TOKEN_RE = re.compile(r"(?:github_pat_|gh[pousr]_|hf_)[A-Za-z0-9_]{12,}")


class ContractError(RuntimeError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ContractError(f"non-finite JSON value: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def validate(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    policy_path = root / "governance/router-flagship-v1.json"
    policy = load_json(policy_path)
    require(policy.get("schema") == SCHEMA, f"schema must be {SCHEMA}", failures)
    require(policy.get("status") == "ACTIVE_SOURCE_OWNER", "router status must be ACTIVE_SOURCE_OWNER", failures)

    program = policy.get("program")
    require(isinstance(program, dict), "program must be an object", failures)
    if isinstance(program, dict):
        require(program.get("name") == "SZL Router", "program name mismatch", failures)
        require(program.get("class") == "INFERENCE_FLAGSHIP", "program class mismatch", failures)

    chain = policy.get("authority_chain")
    require(isinstance(chain, dict), "authority_chain must be an object", failures)
    if isinstance(chain, dict):
        source = chain.get("github_source")
        mirror = chain.get("hugging_face_mirror")
        product = chain.get("product_integration")
        proof = chain.get("proof_origin")
        require(isinstance(source, dict), "github_source must be an object", failures)
        require(isinstance(mirror, dict), "hugging_face_mirror must be an object", failures)
        require(isinstance(product, dict), "product_integration must be an object", failures)
        require(isinstance(proof, dict), "proof_origin must be an object", failures)
        if isinstance(source, dict):
            require(source.get("repository") == SOURCE, "GitHub source mismatch", failures)
            require(source.get("source_owner") is True, "GitHub source must own gateway", failures)
        if isinstance(mirror, dict):
            require(mirror.get("repo_id") == SPACE, "Hugging Face target mismatch", failures)
            require(mirror.get("visibility") == "public", "router Space must be public", failures)
            require(mirror.get("presentation") == "flagship", "router Space must be flagship presentation", failures)
            require(mirror.get("generated_only") is True, "Hub target must be generated only", failures)
            require(mirror.get("credential_bearing_gateway") is False, "public Space cannot be credential-bearing gateway", failures)
        if isinstance(product, dict):
            require(
                f"{product.get('origin', '')}{product.get('path', '')}" == PRODUCT,
                "A11oy integration path mismatch",
                failures,
            )
            require(product.get("replaces_gateway_source") is False, "A11oy cannot replace router source", failures)
        if isinstance(proof, dict):
            require(proof.get("origin") == PROOF, "proof origin mismatch", failures)

    publication = policy.get("publication")
    require(isinstance(publication, dict), "publication must be an object", failures)
    if isinstance(publication, dict):
        expected_true = (
            "exact_source_revision_required",
            "immutable_hugging_face_revision_required",
            "runtime_revision_match_required",
            "live_readiness_witness_required",
        )
        require(publication.get("single_writer_repository") == SOURCE, "single writer mismatch", failures)
        require(publication.get("target_creation_allowed") is False, "publisher may not create target", failures)
        require(publication.get("target_rename_allowed") is False, "publisher may not rename target", failures)
        for key in expected_true:
            require(publication.get(key) is True, f"{key} must be true", failures)

    boundary = policy.get("authority_boundary")
    require(isinstance(boundary, dict), "authority_boundary must be an object", failures)
    if isinstance(boundary, dict):
        require(boundary.get("model_proposes") is True, "model proposal boundary missing", failures)
        require(boundary.get("router_routes") is True, "router route role missing", failures)
        require(boundary.get("independent_policy_constrains") is True, "policy boundary missing", failures)
        require(boundary.get("human_binds_consequential_action") is True, "human bind missing", failures)
        require(boundary.get("router_can_self_authorize") is False, "router cannot self-authorize", failures)
        require(boundary.get("public_effectors_enabled") is False, "public effectors must be disabled", failures)
        require(boundary.get("lambda_status") == "CONJECTURE_1_ADVISORY", "Lambda status mismatch", failures)

    profile = (root / "profile/README.md").read_text(encoding="utf-8")
    hub_readme = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
    fleet = (root / "docs/CANONICAL_FLEET.md").read_text(encoding="utf-8")
    governance = (root / "huggingface/org-card/GOVERNANCE.md").read_text(encoding="utf-8")
    svg = (root / ASSET).read_text(encoding="utf-8")
    manifest = load_json(root / "huggingface/org-card.manifest.json")

    documents = {
        "GitHub profile": profile,
        "Hugging Face README": hub_readme,
        "canonical fleet": fleet,
        "Hub governance": governance,
    }
    for label, text in documents.items():
        for marker in ("SZL Router", SOURCE, SPACE, PRODUCT, PROOF):
            require(marker.casefold() in text.casefold(), f"{label} missing {marker}", failures)

    for label, text in {
        "GitHub profile": profile,
        "Hugging Face README": hub_readme,
    }.items():
        folded = normalized(text)
        require("one inference flagship: **szl router**" in folded, f"{label} missing inference flagship declaration", failures)
        require("three commercial flagships" in folded, f"{label} lost commercial flagship taxonomy", failures)
        require("five public domain bodies" in folded, f"{label} lost body taxonomy", failures)
        require("six internal engines" in folded, f"{label} lost engine taxonomy", failures)
        require("not availability, operational readiness, or publication policy" in folded, f"{label} lost inventory claim boundary", failures)

    require('<title id="title">SZL Router flagship</title>' in svg, "router SVG title missing", failures)
    require("INFERENCE FLAGSHIP" in svg, "router SVG flagship marker missing", failures)
    require(SOURCE in svg, "router SVG source marker missing", failures)
    require(SPACE in svg, "router SVG Space marker missing", failures)
    require("<script" not in svg.casefold(), "router SVG may not contain scripts", failures)

    files = manifest.get("files")
    require(isinstance(files, list), "org-card manifest files must be an array", failures)
    mapping = {
        row.get("source"): row.get("destination")
        for row in files or []
        if isinstance(row, dict)
    }
    require(mapping.get(ASSET) == MANIFEST_DESTINATION, "router asset is not published by org-card manifest", failures)
    markers = (
        ((manifest.get("runtime_transforms") or {}).get("README.md") or {}).get("required_markers")
        or []
    )
    for marker in ("Inference flagship", "SZL Router", "One inference flagship", "assets/hf-card-router.svg"):
        require(marker in markers, f"org-card rendered README gate missing {marker}", failures)

    aggregate = "\n".join((profile, hub_readme, fleet, governance, svg, policy_path.read_text(encoding="utf-8")))
    require(not TOKEN_RE.search(aggregate), "credential-shaped material detected", failures)

    payload = {
        "schema": "szl.router-flagship-validation/v1",
        "status": "PASS" if not failures else "FAIL",
        "source": SOURCE,
        "space": SPACE,
        "product": PRODUCT,
        "proof": PROOF,
        "asset_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        "failures": failures,
        "credential_values_recorded": False,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        result = validate(args.root.resolve())
    except (ContractError, OSError, UnicodeError) as exc:
        result = {
            "schema": "szl.router-flagship-validation/v1",
            "status": "FAIL",
            "failures": [str(exc)],
            "credential_values_recorded": False,
        }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
