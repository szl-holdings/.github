#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate that product, source, artifact, and proof surfaces move as one."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

SCHEMA = "szl.estate-alignment/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
LOCKED_EIGHT = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]
EXPECTED_FLAGSHIPS = ["a11oy", "killinchu", "forge"]
EXPECTED_BODIES = ["terra", "killinchu", "counsel", "finance", "lyte"]
EXPECTED_ENGINES = ["sentra", "lyte", "killinchu", "finance", "terra", "counsel"]
EXPECTED_FOLDS = {
    "aegis": "killinchu",
    "sentra": "killinchu",
    "immune": "killinchu",
    "vessels": "killinchu",
}
EXPECTED_FORBIDDEN_PRODUCTS = {"nexus", *EXPECTED_FOLDS}
EXPECTED_PORTFOLIO_SPACES = {
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/killinchu",
    "SZLHOLDINGS/immune",
    "SZLHOLDINGS/immune-lattice",
    "SZLHOLDINGS/terra",
    "SZLHOLDINGS/sentra",
    "SZLHOLDINGS/counsel",
    "SZLHOLDINGS/finance",
    "SZLHOLDINGS/lyte",
    "SZLHOLDINGS/vertical-services",
    "SZLHOLDINGS/szl-command-lab",
    "SZLHOLDINGS/david-leads",
    "SZLHOLDINGS/szl-constellation",
    "SZLHOLDINGS/szl-frontier",
    "SZLHOLDINGS/szl-model-inference-lab",
    "SZLHOLDINGS/ayllu",
}
ALLOWED_SPACE_CLASSES = {
    "commercial_flagship_runtime",
    "killinchu_capability_channel",
    "public_domain_body_runtime",
    "internal_engine_surface",
    "shared_internal_engine_runtime",
    "estate_atlas",
    "reference_workflow",
    "lab_surface",
    "research_surface",
    "forge_inference_surface",
    "incubation_lab",
}
GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"
USER_AGENT = "SZL-Estate-Alignment/1.0"
PRODUCT_PATH = "docs/strategy/living-command-fabric.v1.json"


class AlignmentError(RuntimeError):
    """Raised when alignment evidence is malformed or unavailable."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AlignmentError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    raise AlignmentError(f"non-finite JSON value: {value}")


def load_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AlignmentError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AlignmentError(f"{label} must contain an object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    return load_json_bytes(path.read_bytes(), label=str(path))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def exact_slugs(rows: Any, label: str, expected: list[str], failures: list[str]) -> None:
    require(isinstance(rows, list), f"{label} must be an array", failures)
    if not isinstance(rows, list):
        return
    observed = [row.get("slug") if isinstance(row, dict) else None for row in rows]
    require(observed == expected, f"{label} slugs must be {expected}; observed {observed}", failures)
    require(len(observed) == len(set(observed)), f"{label} contains duplicate slugs", failures)


def validate_contract(contract: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    require(contract.get("schema") == SCHEMA, f"schema must be {SCHEMA}", failures)
    authority = contract.get("authority")
    require(isinstance(authority, dict), "authority must be an object", failures)
    if isinstance(authority, dict):
        expected_authority = {
            "product_origin": "https://a-11-oy.com",
            "proof_origin": "https://a11oy.net",
            "canonical_source_organization": "https://github.com/szl-holdings",
            "artifact_registry": "https://huggingface.co/SZLHOLDINGS",
            "huggingface_front_door": "SZLHOLDINGS/README",
        }
        for key, expected in expected_authority.items():
            require(authority.get(key) == expected, f"{key} must be {expected}", failures)

    taxonomy = contract.get("taxonomy")
    require(isinstance(taxonomy, dict), "taxonomy must be an object", failures)
    if isinstance(taxonomy, dict):
        flagships = taxonomy.get("commercial_flagships")
        bodies = taxonomy.get("public_domain_bodies")
        exact_slugs(flagships, "commercial_flagships", EXPECTED_FLAGSHIPS, failures)
        exact_slugs(bodies, "public_domain_bodies", EXPECTED_BODIES, failures)
        require(taxonomy.get("commercial_flagship_count") == 3, "commercial flagship count mismatch", failures)
        require(taxonomy.get("public_domain_body_count") == 5, "public body count mismatch", failures)
        require(taxonomy.get("internal_engine_count") == 6, "internal engine count mismatch", failures)
        require(taxonomy.get("internal_engines") == EXPECTED_ENGINES, "internal engine set mismatch", failures)
        require(taxonomy.get("folded_capabilities") == EXPECTED_FOLDS, "folded capability map mismatch", failures)
        if isinstance(flagships, list):
            flagship_slugs = {row.get("slug") for row in flagships if isinstance(row, dict)}
            require(not (set(EXPECTED_FOLDS) & flagship_slugs), "folded capability promoted to flagship", failures)

    snapshot = contract.get("huggingface_inventory_snapshot")
    require(isinstance(snapshot, dict), "huggingface_inventory_snapshot must be an object", failures)
    if isinstance(snapshot, dict):
        rows = snapshot.get("portfolio_spaces")
        require(isinstance(rows, list), "portfolio_spaces must be an array", failures)
        if isinstance(rows, list):
            ids = [row.get("repo_id") if isinstance(row, dict) else None for row in rows]
            require(set(ids) == EXPECTED_PORTFOLIO_SPACES, "portfolio Space set mismatch", failures)
            require(len(ids) == len(set(ids)) == 16, "portfolio Spaces must contain 16 unique IDs", failures)
            require(all(isinstance(row, dict) and row.get("class") in ALLOWED_SPACE_CLASSES for row in rows), "unknown portfolio Space class", failures)
            require(all(isinstance(row, dict) and str(row.get("canonical_source", "")).startswith("szl-holdings/") for row in rows), "every Space requires canonical GitHub source", failures)
        require(snapshot.get("portfolio_space_count") == 16, "portfolio_space_count must be 16", failures)
        require(snapshot.get("model_count") == 44, "model_count must be 44", failures)
        require(snapshot.get("dataset_count") == 33, "dataset_count must be 33", failures)
        require(snapshot.get("organization_card_space_excluded_from_portfolio_count") == "SZLHOLDINGS/README", "README control-surface exclusion missing", failures)

    movement = contract.get("movement_contract")
    require(isinstance(movement, dict), "movement_contract must be an object", failures)
    if isinstance(movement, dict):
        for key in (
            "github_is_source_authority",
            "huggingface_is_generated_artifact_registry",
            "a11oy_net_is_proof_not_product",
            "one_canonical_writer_per_huggingface_target",
            "source_revision_required_for_runtime_claims",
            "human_authority_required",
        ):
            require(movement.get(key) is True, f"{key} must be true", failures)
        require(movement.get("public_effectors_enabled") is False, "public effectors must be disabled", failures)
        require(movement.get("lambda_status") == "CONJECTURE_1_ADVISORY", "Lambda status mismatch", failures)
        require(movement.get("locked_formula_ids") == LOCKED_EIGHT, "locked formula IDs mismatch", failures)
        require(set(movement.get("forbidden_public_products") or []) == EXPECTED_FORBIDDEN_PRODUCTS, "forbidden public-product set mismatch", failures)
    return failures


def validate_documents(root: Path, contract: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    profile = (root / "profile/README.md").read_text(encoding="utf-8")
    hf_readme = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
    hf_index = (root / "huggingface/org-card/index.html").read_text(encoding="utf-8")
    manifest = load_json(root / "huggingface/org-card.manifest.json")
    documents = {
        "GitHub profile": profile,
        "Hugging Face README": hf_readme,
        "Hugging Face index": hf_index,
    }
    for label, text in documents.items():
        for marker in ("Three commercial flagships", "Five public domain bodies", "Six internal engines"):
            require(marker.casefold() in text.casefold(), f"{label} missing {marker!r}", failures)
        for name in ("A11oy", "Killinchu", "Forge", "Terra", "PRISM Counsel", "PURIQ Finance", "LYTE"):
            require(name.casefold() in text.casefold(), f"{label} missing {name}", failures)
    for marker in ("16 portfolio Spaces", "44 models", "33 datasets"):
        require(marker.casefold() in profile.casefold(), f"GitHub profile missing {marker}", failures)
        require(marker.casefold() in hf_readme.casefold(), f"Hugging Face README missing {marker}", failures)
    require('data-szl-surface="company-front-door"' in hf_index, "Hugging Face homepage smoke marker missing", failures)
    require('data-szl-estate-alignment="1.0.0"' in hf_index, "Hugging Face homepage alignment marker missing", failures)
    files = manifest.get("files") or []
    mapping = {row.get("source"): row.get("destination") for row in files if isinstance(row, dict)}
    require(mapping.get("docs/ESTATE_ALIGNMENT_CONTRACT_V1.json") == "estate-alignment.json", "manifest does not publish alignment contract", failures)
    markers = ((manifest.get("runtime_transforms") or {}).get("README.md") or {}).get("required_markers") or []
    for marker in ("Three commercial flagships", "Five public domain bodies", "Six internal engines"):
        require(marker in markers, f"rendered README gate missing {marker}", failures)
    return failures


def normalize_product_source(value: str) -> str:
    return value.replace(
        "szl-holdings/a11oy/verticals/counsel",
        "szl-holdings/a11oy:verticals/counsel",
    )


def validate_product_contract(product: Mapping[str, Any], local: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    taxonomy = local["taxonomy"]
    observed_bodies = [row.get("slug") for row in product.get("verticals", []) if isinstance(row, dict)]
    require(observed_bodies == EXPECTED_BODIES, f"A11oy body taxonomy drift: {observed_bodies}", failures)
    public_taxonomy = product.get("public_product_taxonomy") or {}
    require(public_taxonomy.get("public_domain_bodies") == EXPECTED_BODIES, "A11oy public body set drift", failures)
    require(public_taxonomy.get("internal_engines") == EXPECTED_ENGINES, "A11oy internal engine set drift", failures)
    require(public_taxonomy.get("folded_into_killinchu") == list(EXPECTED_FOLDS), "A11oy folded capability set drift", failures)
    require(((product.get("authorities") or {}).get("lean_kernel") or {}).get("locked_proven_ids") == LOCKED_EIGHT, "A11oy locked formula set drift", failures)
    estate = product.get("estate") or {}
    require(estate.get("product_surface") == local["authority"]["product_origin"], "A11oy product origin drift", failures)
    require(estate.get("proof_surface") == local["authority"]["proof_origin"], "A11oy proof origin drift", failures)
    require(estate.get("artifact_organization") == "SZLHOLDINGS", "A11oy artifact organization drift", failures)
    local_sources = {row["slug"]: row["source"] for row in taxonomy["public_domain_bodies"]}
    for row in product.get("verticals", []):
        if not isinstance(row, dict) or row.get("slug") not in local_sources:
            continue
        observed = normalize_product_source(str(row.get("canonical_source") or ""))
        require(observed == local_sources[row["slug"]], f"A11oy canonical source drift for {row['slug']}: {observed}", failures)
    return failures


def retry_delay(error: urllib.error.HTTPError, fallback: float) -> float:
    raw = error.headers.get("Retry-After") if error.headers else None
    if raw:
        try:
            return min(max(float(raw), fallback), 60.0)
        except (TypeError, ValueError):
            pass
    return fallback


def fetch_bytes(
    url: str,
    *,
    token: str | None = None,
    attempts: int = 5,
    max_bytes: int = 4_000_000,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise AlignmentError(f"response exceeds {max_bytes} bytes: {url}")
                return payload
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise
            sleep(retry_delay(exc, float(2**attempt)))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 == attempts:
                raise
            sleep(float(2**attempt))
    raise AlignmentError("unreachable retry state")


def github_main_sha(repository: str, token: str | None) -> str:
    value = load_json_bytes(
        fetch_bytes(f"{GITHUB_API}/repos/{repository}/branches/main", token=token),
        label=f"{repository} main",
    )
    sha = str((value.get("commit") or {}).get("sha") or "").lower()
    if not SHA40.fullmatch(sha):
        raise AlignmentError(f"{repository} main did not resolve to exact SHA")
    return sha


def canonical_repositories(contract: Mapping[str, Any]) -> set[str]:
    repositories = {"szl-holdings/a11oy", "szl-holdings/.github"}
    taxonomy = contract["taxonomy"]
    snapshot = contract["huggingface_inventory_snapshot"]
    rows = list(taxonomy["commercial_flagships"]) + list(taxonomy["public_domain_bodies"]) + list(snapshot["portfolio_spaces"])
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("source", "service_source", "canonical_source"):
            value = str(row.get(key) or "")
            if value.startswith("szl-holdings/"):
                repositories.add(value.split(":", 1)[0])
    return repositories


def list_hf(kind: str) -> list[dict[str, Any]]:
    value = json.loads(
        fetch_bytes(f"https://huggingface.co/api/{kind}?author=SZLHOLDINGS&limit=100&full=true")
    )
    if not isinstance(value, list):
        raise AlignmentError(f"Hugging Face {kind} endpoint did not return an array")
    return [row for row in value if isinstance(row, dict)]


def validate_live(contract: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    a11oy_sha = github_main_sha("szl-holdings/a11oy", token)
    product = load_json_bytes(
        fetch_bytes(
            f"https://raw.githubusercontent.com/szl-holdings/a11oy/{a11oy_sha}/{PRODUCT_PATH}"
        ),
        label="A11oy living-command contract",
    )
    failures.extend(validate_product_contract(product, contract))

    repository_observations: list[dict[str, Any]] = []
    for repository in sorted(canonical_repositories(contract)):
        try:
            value = load_json_bytes(
                fetch_bytes(f"{GITHUB_API}/repos/{repository}", token=token),
                label=repository,
            )
            repository_observations.append(
                {
                    "repository": repository,
                    "archived": value.get("archived"),
                    "visibility": value.get("visibility"),
                    "default_branch": value.get("default_branch"),
                }
            )
            require(value.get("archived") is False, f"canonical repository is archived: {repository}", failures)
        except Exception as exc:
            failures.append(f"canonical repository unavailable: {repository}: {type(exc).__name__}")

    models = list_hf("models")
    datasets = list_hf("datasets")
    spaces = list_hf("spaces")
    space_ids = {str(row.get("id") or "") for row in spaces}
    portfolio_ids = space_ids - {"SZLHOLDINGS/README"}
    expected = {row["repo_id"] for row in contract["huggingface_inventory_snapshot"]["portfolio_spaces"]}
    require(portfolio_ids == expected, f"public portfolio Space drift: missing={sorted(expected - portfolio_ids)} unexpected={sorted(portfolio_ids - expected)}", failures)
    require(len(models) == contract["huggingface_inventory_snapshot"]["model_count"], f"model count drift: {len(models)}", failures)
    require(len(datasets) == contract["huggingface_inventory_snapshot"]["dataset_count"], f"dataset count drift: {len(datasets)}", failures)
    require("SZLHOLDINGS/README" in space_ids, "Hugging Face organization-card Space missing", failures)
    return failures, {
        "a11oy_contract_revision": a11oy_sha,
        "canonical_repositories": repository_observations,
        "huggingface": {
            "models": len(models),
            "datasets": len(datasets),
            "spaces_including_org_card": len(space_ids),
            "portfolio_spaces": len(portfolio_ids),
            "portfolio_space_ids": sorted(portfolio_ids),
        },
    }


def build_receipt(root: Path, *, live: bool) -> dict[str, Any]:
    contract_path = root / "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json"
    contract = load_json(contract_path)
    failures = validate_contract(contract)
    failures.extend(validate_documents(root, contract))
    live_observation: dict[str, Any] | None = None
    if live:
        try:
            live_failures, live_observation = validate_live(contract)
            failures.extend(live_failures)
        except Exception as exc:
            failures.append(f"live alignment evidence unavailable: {type(exc).__name__}: {exc}")
    receipt = {
        "schema": "szl.estate-alignment-receipt/v1",
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "state": "ALIGNED" if not failures else "DIVERGENT",
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "source_revision": os.getenv("GITHUB_SHA", "UNAVAILABLE"),
        "live_requested": live,
        "live_observation": live_observation,
        "failures": failures,
        "authority": {
            "provider_writes": False,
            "secret_values_recorded": False,
            "public_effectors_enabled": False,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("estate-alignment-receipt.json"))
    args = parser.parse_args()
    receipt = build_receipt(args.repo_root.resolve(), live=args.live)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "failure_count": len(receipt["failures"]),
                "receipt_sha256": receipt["receipt_sha256"],
            },
            indent=2,
        )
    )
    return 0 if receipt["state"] == "ALIGNED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
