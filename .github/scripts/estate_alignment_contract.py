#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate that product, source, artifact, and proof surfaces move as one."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
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
    "SZLHOLDINGS/ayllu",
    "SZLHOLDINGS/counsel",
    "SZLHOLDINGS/david-leads",
    "SZLHOLDINGS/finance",
    "SZLHOLDINGS/killinchu",
    "SZLHOLDINGS/lyte",
    "SZLHOLDINGS/sentra",
    "SZLHOLDINGS/szl-command-lab",
    "SZLHOLDINGS/szl-constellation",
    "SZLHOLDINGS/szl-frontier",
    "SZLHOLDINGS/szl-model-inference-lab",
    "SZLHOLDINGS/terra",
    "SZLHOLDINGS/vertical-services",
}
EXPECTED_INVENTORY_ONLY_SPACES = {"SZLHOLDINGS/yarqa"}
# Anonymous membership observation, separate from the historical fleet policy.
EXPECTED_PUBLIC_SPACE_IDS = {
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/a11oy-factory",
    "SZLHOLDINGS/agents-studio",
    "SZLHOLDINGS/anatomy",
    "SZLHOLDINGS/ayllu",
    "SZLHOLDINGS/counsel",
    "SZLHOLDINGS/counsel-assurance",
    "SZLHOLDINGS/curation-atlas",
    "SZLHOLDINGS/david-leads",
    "SZLHOLDINGS/estate-gardener",
    "SZLHOLDINGS/estate-holo",
    "SZLHOLDINGS/eternal-auditor",
    "SZLHOLDINGS/finance",
    "SZLHOLDINGS/foundation-confirmation-v2",
    "SZLHOLDINGS/frontier-console",
    "SZLHOLDINGS/frontier-showcase",
    "SZLHOLDINGS/gdw-frontier",
    "SZLHOLDINGS/governed-agent-bench",
    "SZLHOLDINGS/governed-receipt-verifier",
    "SZLHOLDINGS/holographic-unify",
    "SZLHOLDINGS/khipu-hologram",
    "SZLHOLDINGS/khipu-playground",
    "SZLHOLDINGS/khipu-proof-loom",
    "SZLHOLDINGS/khipu-yachay",
    "SZLHOLDINGS/killinchu",
    "SZLHOLDINGS/living-anatomy",
    "SZLHOLDINGS/llm-router-live",
    "SZLHOLDINGS/lyte",
    "SZLHOLDINGS/measured-honesty-census",
    "SZLHOLDINGS/newton-trust-upgrade",
    "SZLHOLDINGS/nexus",
    "SZLHOLDINGS/oac-system-health-lab",
    "SZLHOLDINGS/prove-it",
    "SZLHOLDINGS/puriq-markets",
    "SZLHOLDINGS/sentra",
    "SZLHOLDINGS/szl-atelier",
    "SZLHOLDINGS/szl-bench-suite",
    "SZLHOLDINGS/szl-brand-campaign",
    "SZLHOLDINGS/szl-chief-engineer",
    "SZLHOLDINGS/szl-command-center",
    "SZLHOLDINGS/szl-command-lab",
    "SZLHOLDINGS/szl-constellation",
    "SZLHOLDINGS/szl-cram-demo",
    "SZLHOLDINGS/szl-cyber-shield",
    "SZLHOLDINGS/szl-dream-architect",
    "SZLHOLDINGS/szl-energy-hologram",
    "SZLHOLDINGS/szl-energy-ledger",
    "SZLHOLDINGS/szl-forge-lab",
    "SZLHOLDINGS/szl-foundation-confirmation",
    "SZLHOLDINGS/szl-frontier",
    "SZLHOLDINGS/szl-frontier-deck",
    "SZLHOLDINGS/szl-infra-warden",
    "SZLHOLDINGS/szl-khipu",
    "SZLHOLDINGS/szl-marketing",
    "SZLHOLDINGS/szl-marketing-1-1",
    "SZLHOLDINGS/szl-model-inference-lab",
    "SZLHOLDINGS/szl-muhu-frontier",
    "SZLHOLDINGS/szl-provenance-pitch",
    "SZLHOLDINGS/szl-receipt-constellation",
    "SZLHOLDINGS/szl-receipts-chain",
    "SZLHOLDINGS/szl-research-council",
    "SZLHOLDINGS/szl-router-control",
    "SZLHOLDINGS/szl-science-gate-studio",
    "SZLHOLDINGS/szl-second-brain",
    "SZLHOLDINGS/szl-seismic-review",
    "SZLHOLDINGS/szl-typesafe-triage",
    "SZLHOLDINGS/szlholdings-si",
    "SZLHOLDINGS/terra",
    "SZLHOLDINGS/terra-assurance",
    "SZLHOLDINGS/the-grid",
    "SZLHOLDINGS/training-ledger-explorer",
    "SZLHOLDINGS/truth-router",
    "SZLHOLDINGS/vertical-services",
    "SZLHOLDINGS/wink-observatory",
    "SZLHOLDINGS/yarqa",
}
PUBLIC_SPACE_OBSERVED_AT = "2026-11-26T05:58:09.411368Z"
PUBLIC_SPACE_CLAIM_BOUNDARY = (
    "Anonymous public Space membership only; not fleet policy, ownership, "
    "publication eligibility, or runtime qualification."
)
PUBLIC_SPACE_POLICY_CONFLICTS = [{'repo_id': 'SZLHOLDINGS/llm-router-live',
  'github_declaration': 'KEEP',
  'a11oy_declaration': 'FOLD',
  'github_source': 'https://github.com/szl-holdings/.github/blob/3ed8a867fa4c5f63f1fbdc25f80891982613855c/docs/CANONICAL_FLEET.md',
  'a11oy_source': 'https://github.com/szl-holdings/a11oy/blob/18f169dde881055a8993192d2fd1aff99ebcc592/docs/generated/github-org-public-estate.md'},
 {'repo_id': 'SZLHOLDINGS/szl-atelier',
  'github_declaration': 'KEEP',
  'a11oy_declaration': 'FOLD',
  'github_source': 'https://github.com/szl-holdings/.github/blob/3ed8a867fa4c5f63f1fbdc25f80891982613855c/docs/CANONICAL_FLEET.md',
  'a11oy_source': 'https://github.com/szl-holdings/a11oy/blob/18f169dde881055a8993192d2fd1aff99ebcc592/docs/generated/github-org-public-estate.md'}]
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
HF_PAGE_SIZE = 100
HF_MAX_PAGES = 8
HF_PAGE_MAX_BYTES = 4_000_000
USER_AGENT = "SZL-Estate-Alignment/1.0"
PRODUCT_PATH = "docs/strategy/living-command-fabric.v1.json"
RUNTIME_BINDING_PATHS = ("/api/build-info", "/deployment.json")
ORG_CARD_SPACE_ID = "SZLHOLDINGS/README"
ORG_CARD_RUNTIME_ORIGIN = "https://szlholdings-readme.static.hf.space"
ORG_CARD_DEPLOYMENT_SOURCE = "szl-holdings/.github"
ORG_CARD_BINDING_PATHS = ("/deployment.json",)
RUNTIME_OBSERVATIONS = 2
MAX_RUNTIME_WORKERS = 8
SOURCE_REVISION_KEYS = (
    "observed_source_revision",
    "source_revision",
    "git_sha",
    "revision",
)


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


def validate_public_space_observation(observation: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(observation, dict):
        return ["public Space membership observation must be an object"]
    expected_keys = {
        "schema", "evidence_class", "observed_at", "scope", "author", "policy_authority",
        "excluded_control_surface", "public_space_count", "spaces", "policy_alignment",
        "policy_conflicts", "claim_boundary",
    }
    require(set(observation) == expected_keys, "public Space observation fields mismatch", failures)
    expected = {
        "schema": "szl.public-space-membership-observation/v1",
        "evidence_class": "MEASURED",
        "observed_at": PUBLIC_SPACE_OBSERVED_AT,
        "scope": "anonymous-public-author-list",
        "author": "SZLHOLDINGS",
        "excluded_control_surface": ORG_CARD_SPACE_ID,
        "policy_alignment": "UNKNOWN",
        "policy_conflicts": PUBLIC_SPACE_POLICY_CONFLICTS,
        "claim_boundary": PUBLIC_SPACE_CLAIM_BOUNDARY,
    }
    for key, value in expected.items():
        require(observation.get(key) == value, f"public Space observation {key} mismatch", failures)
    require(observation.get("policy_authority") is False, "public Space observation must not be publication policy", failures)
    rows = observation.get("spaces")
    if not isinstance(rows, list):
        return failures + ["public Space observations must be an array"]
    ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"repo_id", "revision"}:
            failures.append("public Space row must contain only repo_id and revision")
            continue
        repo_id = row.get("repo_id")
        if not isinstance(repo_id, str) or re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9._-]*", repo_id) is None:
            failures.append("public Space observation requires an exact SZLHOLDINGS ID")
        else:
            ids.append(repo_id)
        revision = row.get("revision")
        require(isinstance(revision, str) and SHA40.fullmatch(revision) is not None, "public Space observation requires an immutable Hub revision", failures)
    require(ids == sorted(ids) and len(ids) == len(set(ids)), "public Space observation IDs must be unique and sorted", failures)
    require(ORG_CARD_SPACE_ID not in ids, "README must remain outside public Space author membership", failures)
    require(set(ids) == EXPECTED_PUBLIC_SPACE_IDS, "public Space observation exact ID set mismatch", failures)
    require(type(observation.get("public_space_count")) is int and observation["public_space_count"] == len(rows) == len(EXPECTED_PUBLIC_SPACE_IDS), "public Space observation count mismatch", failures)
    return failures


def validate_live_public_space_membership(
    spaces: Any, observation: Any
) -> tuple[list[str], set[str]]:
    failures = validate_public_space_observation(observation)
    if failures:
        return failures, set()
    if not isinstance(spaces, list):
        return ["live public Space membership must be an array"], set()
    ids: list[str] = []
    for row in spaces:
        repo_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(repo_id, str) or re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9._-]*", repo_id) is None:
            failures.append("live public Space membership requires an exact SZLHOLDINGS ID")
        else:
            ids.append(repo_id)
    require(len(ids) == len(set(ids)), "live public Space membership contains duplicate IDs", failures)
    listed_ids = set(ids) - {ORG_CARD_SPACE_ID}
    expected_ids = {row["repo_id"] for row in observation["spaces"]}
    require(listed_ids == expected_ids, f"public Space inventory drift: missing={sorted(expected_ids - listed_ids)} unexpected={sorted(listed_ids - expected_ids)}", failures)
    require(len(listed_ids) == observation["public_space_count"], f"public Space count drift: {len(listed_ids)}", failures)
    return failures, listed_ids


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
        require(snapshot.get("policy_authority") is False, "Hub inventory must not be publication policy", failures)
        require(snapshot.get("governed_keep_list") == "docs/CANONICAL_FLEET.md", "governed keep-list authority mismatch", failures)
        require(snapshot.get("observed_at_scope") == "Portfolio and inventory-only Space membership; model and dataset counts have separate observation times.", "Hub observation scope mismatch", failures)
        require(
            snapshot.get("claim_boundary")
            == "Public Hub inventory evidence only; not availability, operational readiness, or publication policy.",
            "Hub inventory claim boundary mismatch",
            failures,
        )
        rows = snapshot.get("portfolio_spaces")
        require(isinstance(rows, list), "portfolio_spaces must be an array", failures)
        if isinstance(rows, list):
            ids = [row.get("repo_id") if isinstance(row, dict) else None for row in rows]
            require(set(ids) == EXPECTED_PORTFOLIO_SPACES, "portfolio Space set mismatch", failures)
            require(len(ids) == len(set(ids)) == 14, "portfolio Spaces must contain 14 unique IDs", failures)
            require(all(isinstance(row, dict) and row.get("class") in ALLOWED_SPACE_CLASSES for row in rows), "unknown portfolio Space class", failures)
            require(all(isinstance(row, dict) and str(row.get("canonical_source", "")).startswith("szl-holdings/") for row in rows), "every Space requires canonical GitHub source", failures)
            require(all(isinstance(row, dict) and str(row.get("deployment_source", "")).startswith("szl-holdings/") for row in rows), "every Space requires canonical deployment source", failures)
        inventory_only = snapshot.get("inventory_only_spaces")
        require(isinstance(inventory_only, list), "inventory_only_spaces must be an array", failures)
        if isinstance(inventory_only, list):
            inventory_ids = [row.get("repo_id") if isinstance(row, dict) else None for row in inventory_only]
            require(set(inventory_ids) == EXPECTED_INVENTORY_ONLY_SPACES, "inventory-only Space set mismatch", failures)
            require(len(inventory_ids) == len(set(inventory_ids)) == 1, "inventory-only Spaces must contain one unique ID", failures)
            require(all(isinstance(row, dict) and row.get("class") == "inventory_only" for row in inventory_only), "inventory-only class mismatch", failures)
            require(all(isinstance(row, dict) and row.get("governed_keep") is False for row in inventory_only), "inventory-only Space cannot be a keeper", failures)
            require(all(isinstance(row, dict) and row.get("disposition") == "FOLD" for row in inventory_only), "inventory-only disposition must be FOLD", failures)
            require(all(isinstance(row, dict) and str(row.get("canonical_source", "")).startswith("szl-holdings/") for row in inventory_only), "inventory-only Space requires canonical GitHub source", failures)
        require(snapshot.get("portfolio_space_count") == 14, "portfolio_space_count must be 14", failures)
        require(snapshot.get("public_space_count") == 15, "public_space_count must be 15", failures)
        require(snapshot.get("public_space_count") == snapshot.get("portfolio_space_count") + len(inventory_only or []), "public Space decomposition mismatch", failures)
        require(snapshot.get("model_count") == 69, "model_count must be 69", failures)
        require(snapshot.get("model_count_observed_at") == "2026-11-26T05:58:09Z", "model count observation time mismatch", failures)
        require(snapshot.get("dataset_count") == 174, "dataset_count must be 174", failures)
        require(snapshot.get("dataset_count_observed_at") == "2026-11-26T05:58:09Z", "dataset count observation time mismatch", failures)
        require(snapshot.get("organization_card_space_excluded_from_portfolio_count") == ORG_CARD_SPACE_ID, "README control-surface exclusion missing", failures)

    failures.extend(validate_public_space_observation(contract.get("public_space_membership_observation")))

    org_card = contract.get("organization_card_control_surface")
    require(isinstance(org_card, dict), "organization_card_control_surface must be an object", failures)
    if isinstance(org_card, dict):
        require(org_card.get("repo_id") == ORG_CARD_SPACE_ID, "organization-card repo_id mismatch", failures)
        require(org_card.get("class") == "organization_card_control_surface", "organization-card class mismatch", failures)
        require(org_card.get("deployment_source") == ORG_CARD_DEPLOYMENT_SOURCE, "organization-card deployment source mismatch", failures)
        require(org_card.get("runtime_origin") == ORG_CARD_RUNTIME_ORIGIN, "organization-card runtime origin mismatch", failures)
        require(org_card.get("binding_paths") == list(ORG_CARD_BINDING_PATHS), "organization-card binding path mismatch", failures)
        require(org_card.get("portfolio_member") is False, "organization-card must remain outside the portfolio count", failures)
        require(
            org_card.get("claim_boundary")
            == "Source-bound organization front door; excluded from the 14 portfolio-Space count.",
            "organization-card claim boundary mismatch",
            failures,
        )

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
    for marker in ("16 portfolio Spaces", "1 inventory-only Space", "45 models", "34 datasets"):
        require(marker.casefold() in profile.casefold(), f"GitHub profile missing {marker}", failures)
        require(marker.casefold() in hf_readme.casefold(), f"Hugging Face README missing {marker}", failures)
    for label, text in documents.items():
        require(
            "not availability, operational readiness, or publication policy"
            in " ".join(text.casefold().split()),
            f"{label} missing Hub inventory claim boundary",
            failures,
        )
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
    required_origin: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                final_url = str(response.geturl())
                if required_origin and url_origin(final_url) != url_origin(required_origin):
                    raise AlignmentError(
                        f"cross-origin redirect rejected: {url} -> {final_url}"
                    )
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise AlignmentError(f"response exceeds {max_bytes} bytes: {url}")
                return payload
        except urllib.error.HTTPError as exc:
            final_url = str(exc.geturl())
            if required_origin and url_origin(final_url) != url_origin(required_origin):
                raise AlignmentError(
                    f"cross-origin redirect rejected: {url} -> {final_url}"
                ) from exc
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


def source_repository(value: Any) -> str:
    repository = str(value or "").split(":", 1)[0]
    if re.fullmatch(r"szl-holdings/[A-Za-z0-9_.-]+", repository) is None:
        raise AlignmentError(f"invalid canonical source repository: {value!r}")
    return repository


def runtime_origin(repo_id: Any) -> str:
    value = str(repo_id or "")
    if re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9._-]*", value) is None:
        raise AlignmentError(f"invalid portfolio Space id: {repo_id!r}")
    return "https://" + re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-") + ".hf.space"


def url_origin(value: str) -> tuple[str, str, int | None]:
    """Return a normalized network origin, rejecting ambiguous URLs."""

    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AlignmentError(f"invalid network origin: {value!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise AlignmentError(f"invalid network origin: {value!r}") from exc
    if port == (443 if parsed.scheme.lower() == "https" else 80):
        port = None
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def cache_busted_runtime_url(origin: str, path: str, ordinal: int) -> str:
    parsed = urllib.parse.urlsplit(origin + path)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("cache_bust", f"{time.time_ns()}-{os.getpid()}-{ordinal}"))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), "")
    )


def source_revision(payload: Any) -> str | None:
    """Return one exact Git source revision from a bounded runtime receipt."""

    if not isinstance(payload, Mapping):
        return None
    candidates = [payload.get(key) for key in SOURCE_REVISION_KEYS]
    for name in ("build", "source", "deployment", "runtime"):
        nested = payload.get(name)
        if isinstance(nested, Mapping):
            candidates.extend(nested.get(key) for key in SOURCE_REVISION_KEYS)
    revisions = {
        str(candidate).strip().lower()
        for candidate in candidates
        if isinstance(candidate, str) and SHA40.fullmatch(candidate.strip().lower())
    }
    if len(revisions) > 1:
        raise AlignmentError("runtime binding reports conflicting source revisions")
    return next(iter(revisions), None)


def reported_source_repository(payload: Any) -> str | None:
    """Distinguish absent identity from an explicit invalid or conflicting claim.

    Origin inference is allowed only when no repository field was supplied.
    Check every supported envelope; a valid sibling cannot hide an invalid one.
    Do not reflect untrusted field values into retained errors or receipts.
    """
    if not isinstance(payload, Mapping):
        return None
    envelopes = [payload]
    for name in ("build", "source", "deployment", "runtime"):
        nested = payload.get(name)
        if isinstance(nested, Mapping):
            envelopes.append(nested)
    repositories: set[str] = set()
    for envelope in envelopes:
        for key in ("source_repository", "repository"):
            if key not in envelope:
                continue
            candidate = envelope[key]
            if not isinstance(candidate, str) or re.fullmatch(
                r"szl-holdings/[A-Za-z0-9_.-]+(?::[A-Za-z0-9_./-]+)?",
                candidate,
            ) is None:
                raise AlignmentError("runtime binding reports invalid source repository")
            repositories.add(source_repository(candidate))
    if len(repositories) > 1:
        raise AlignmentError("runtime binding reports conflicting source repositories")
    return next(iter(repositories), None)


def runtime_source_binding(
    row: Mapping[str, Any],
    expected_revision: str,
    *,
    fetch: Callable[..., bytes] = fetch_bytes,
) -> dict[str, Any]:
    """Fail closed unless a Space exposes its exact canonical Git revision."""

    repo_id = str(row.get("repo_id") or "")
    repository = source_repository(row.get("deployment_source"))
    expected = str(expected_revision or "").lower()
    if SHA40.fullmatch(expected) is None:
        raise AlignmentError(f"invalid expected source revision for {repo_id}: {expected!r}")
    if repo_id == ORG_CARD_SPACE_ID:
        configured_origin = str(row.get("runtime_origin") or "")
        if configured_origin != ORG_CARD_RUNTIME_ORIGIN:
            raise AlignmentError(
                f"organization-card runtime origin mismatch: {configured_origin!r}"
            )
        configured_paths = row.get("binding_paths")
        if configured_paths != list(ORG_CARD_BINDING_PATHS):
            raise AlignmentError(
                f"organization-card binding paths mismatch: {configured_paths!r}"
            )
        origin = ORG_CARD_RUNTIME_ORIGIN
        binding_paths = ORG_CARD_BINDING_PATHS
    else:
        if row.get("runtime_origin") is not None or row.get("binding_paths") is not None:
            raise AlignmentError(
                f"custom runtime binding is reserved for {ORG_CARD_SPACE_ID}"
            )
        origin = runtime_origin(repo_id)
        binding_paths = RUNTIME_BINDING_PATHS
    attempts: list[dict[str, Any]] = []
    for path in binding_paths:
        observations: list[dict[str, Any]] = []
        for ordinal in range(1, RUNTIME_OBSERVATIONS + 1):
            url = cache_busted_runtime_url(origin, path, ordinal)
            try:
                payload = load_json_bytes(
                    fetch(url, attempts=2, required_origin=origin),
                    label=url,
                )
                observed = source_revision(payload)
                observed_repository = reported_source_repository(payload)
            except AlignmentError as exc:
                observations.append({"ordinal": ordinal, "url": url, "error": str(exc)})
                attempts.append(
                    {
                        "path": path,
                        "observation_count": RUNTIME_OBSERVATIONS,
                        "stable": False,
                        "complete": False,
                        "matched": False,
                        "observations": observations,
                    }
                )
                return {
                    "repo_id": repo_id,
                    "canonical_source": repository,
                    "expected_revision": expected,
                    "binding_path": path,
                    "observed_revision": None,
                    "observed_source": None,
                    "matched": False,
                    "attempts": attempts,
                }
            except Exception as exc:
                observations.append(
                    {"ordinal": ordinal, "url": url, "error": type(exc).__name__}
                )
            else:
                observations.append(
                    {
                        "ordinal": ordinal,
                        "url": url,
                        "observed_revision": observed,
                        "observed_source": observed_repository,
                    }
                )

        successful = [row for row in observations if "error" not in row]
        identities = {
            (row.get("observed_revision"), row.get("observed_source"))
            for row in successful
        }
        stable = len(successful) == RUNTIME_OBSERVATIONS and len(identities) == 1
        observed, observed_repository = (
            next(iter(identities)) if stable else (None, None)
        )
        complete = observed is not None
        # The runtime origin and deployment_source are already contract-bound.
        # An explicit repository field strengthens that evidence, but absence of the
        # redundant field must not invalidate a stable exact-SHA witness. A conflicting
        # explicit repository still fails closed.
        source_compatible = observed_repository in (None, repository)
        source_evidence = (
            "reported"
            if observed_repository == repository
            else "contract-bound-origin"
            if observed_repository is None
            else "conflicting"
        )
        attempt = {
            "path": path,
            "observation_count": RUNTIME_OBSERVATIONS,
            "stable": stable,
            "complete": complete,
            "observed_revision": observed,
            "observed_source": observed_repository,
            "source_evidence": source_evidence,
            "matched": (
                stable
                and complete
                and observed == expected
                and source_compatible
            ),
            "observations": observations,
        }
        attempts.append(attempt)

        if stable and complete:
            return {
                "repo_id": repo_id,
                "canonical_source": repository,
                "expected_revision": expected,
                "binding_path": path,
                "observed_revision": observed,
                "observed_source": observed_repository,
                "source_evidence": source_evidence,
                "matched": attempt["matched"],
                "attempts": attempts,
            }
        if successful and not stable:
            return {
                "repo_id": repo_id,
                "canonical_source": repository,
                "expected_revision": expected,
                "binding_path": path,
                "observed_revision": None,
                "observed_source": None,
                "matched": False,
                "attempts": attempts,
            }
    return {
        "repo_id": repo_id,
        "canonical_source": repository,
        "expected_revision": expected,
        "binding_path": None,
        "observed_revision": None,
        "observed_source": None,
        "matched": False,
        "attempts": attempts,
    }


def canonical_repositories(contract: Mapping[str, Any]) -> set[str]:
    repositories = {"szl-holdings/a11oy", "szl-holdings/.github"}
    taxonomy = contract["taxonomy"]
    snapshot = contract["huggingface_inventory_snapshot"]
    rows = list(taxonomy["commercial_flagships"]) + list(taxonomy["public_domain_bodies"]) + list(snapshot["portfolio_spaces"])
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("source", "service_source", "canonical_source", "deployment_source"):
            value = str(row.get(key) or "")
            if value.startswith("szl-holdings/"):
                repositories.add(source_repository(value))
    return repositories


class HFListing(list):
    """Completed public listing, with bounded-read coverage attached."""

    def __init__(self, rows: list[dict[str, Any]], *, pages: int) -> None:
        super().__init__(rows)
        self.pages = pages
        self.complete = True
        self.observed_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    def __eq__(self, other: object) -> bool:
        payload_equal = list.__eq__(self, other)
        if payload_equal is NotImplemented:
            return NotImplemented
        if not payload_equal or not isinstance(other, HFListing):
            return payload_equal
        return (self.pages, self.complete, self.observed_at) == (
            other.pages, other.complete, other.observed_at
        )

    def __ne__(self, other: object) -> bool:
        equal = self.__eq__(other)
        return NotImplemented if equal is NotImplemented else not equal


def validate_hf_page_url(url: str, kind: str, *, next_page: bool) -> None:
    """Only follow the Hub's exact author-scoped cursor URL, never arbitrary links."""
    if kind not in {"models", "datasets", "spaces"}:
        raise AlignmentError(f"unsupported Hugging Face inventory kind: {kind}")
    parts = urllib.parse.urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "huggingface.co"
        or parts.path != f"/api/{kind}"
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        raise AlignmentError(f"Hugging Face {kind} pagination URL outside approved endpoint")
    try:
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise AlignmentError(f"Hugging Face {kind} pagination query malformed") from exc
    expected = {"author", "limit", "full"} | ({"cursor"} if next_page else set())
    if (
        set(query) != expected
        or any(len(values) != 1 for values in query.values())
        or query.get("author") != ["SZLHOLDINGS"]
        or query.get("limit") != [str(HF_PAGE_SIZE)]
        or query.get("full") != ["true"]
        or (next_page and not query.get("cursor", [""])[0])
    ):
        raise AlignmentError(f"Hugging Face {kind} pagination changed the author or request scope")


def next_hf_page(link_header: str | None, kind: str) -> str | None:
    """Read the provider-supplied Link rel=next; do not synthesize cursors."""
    if link_header is None:
        return None
    if not isinstance(link_header, str) or not link_header.strip():
        raise AlignmentError(f"Hugging Face {kind} pagination Link is malformed")
    next_urls: list[str] = []
    for item in link_header.split(","):
        match = re.fullmatch(r"\s*<([^<>]+)>\s*(.*)\s*", item)
        if match is None or not match.group(2).strip().startswith(";"):
            raise AlignmentError(f"Hugging Face {kind} pagination Link is malformed")
        attributes: dict[str, str] = {}
        for parameter in match.group(2).strip().split(";")[1:]:
            name, separator, raw = parameter.strip().partition("=")
            if not separator or not name or not raw.strip():
                raise AlignmentError(f"Hugging Face {kind} pagination Link has malformed attributes")
            name = name.strip().lower()
            value = raw.strip().strip('"').lower()
            if name in attributes:
                raise AlignmentError(f"Hugging Face {kind} pagination Link has duplicate attributes")
            attributes[name] = value
        if "next" in attributes.get("rel", "").split():
            next_urls.append(match.group(1))
    if len(next_urls) > 1:
        raise AlignmentError(f"Hugging Face {kind} pagination has multiple next links")
    if not next_urls:
        return None
    validate_hf_page_url(next_urls[0], kind, next_page=True)
    return next_urls[0]


def fetch_hf_page(
    url: str,
    *,
    attempts: int = 3,
    max_bytes: int = HF_PAGE_MAX_BYTES,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bytes, str | None]:
    """Read one anonymous, bounded page including its pagination header."""
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                # Never follow a redirect that silently changes inventory scope.
                if str(response.geturl()) != url:
                    raise AlignmentError("Hugging Face inventory pagination redirect rejected")
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise AlignmentError("Hugging Face inventory page exceeds byte budget")
                return payload, response.headers.get("Link")
        except urllib.error.HTTPError as exc:
            if str(exc.geturl()) != url:
                raise AlignmentError("Hugging Face inventory pagination error redirect rejected") from exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise
            sleep(retry_delay(exc, float(2**attempt)))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 == attempts:
                raise
            sleep(float(2**attempt))
    raise AlignmentError("unreachable Hugging Face inventory retry state")


def list_hf(kind: str) -> HFListing:
    """Return only complete, author-verified public inventory under a rate budget."""
    url = f"{HF_API}/{kind}?author=SZLHOLDINGS&limit={HF_PAGE_SIZE}&full=true"
    seen_pages: set[str] = set()
    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for page_index in range(HF_MAX_PAGES):
        validate_hf_page_url(url, kind, next_page=page_index > 0)
        if url in seen_pages:
            raise AlignmentError(f"Hugging Face {kind} pagination repeated a cursor")
        seen_pages.add(url)
        payload, link = fetch_hf_page(url)
        try:
            page = json.loads(
                payload,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AlignmentError(f"Hugging Face {kind} page is not strict JSON") from exc
        if not isinstance(page, list):
            raise AlignmentError(f"Hugging Face {kind} endpoint did not return an array")
        if len(page) > HF_PAGE_SIZE:
            raise AlignmentError(f"Hugging Face {kind} returned oversized page")
        for row in page:
            if not isinstance(row, dict):
                raise AlignmentError(f"Hugging Face {kind} endpoint returned a malformed row")
            repo_id = row.get("id")
            if not isinstance(repo_id, str) or re.fullmatch(
                r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9._-]*", repo_id
            ) is None:
                raise AlignmentError(f"Hugging Face {kind} returned non-author or invalid ID")
            if repo_id in seen_ids:
                raise AlignmentError(f"Hugging Face {kind} pagination duplicated an ID")
            seen_ids.add(repo_id)
            rows.append(row)
        next_url = next_hf_page(link, kind)
        if next_url is None:
            # An exactly full page without provider continuation cannot prove
            # the author listing was complete. Preserve UNAVAILABLE, not green.
            if len(page) == HF_PAGE_SIZE:
                raise AlignmentError(f"Hugging Face {kind} full terminal page lacks completion proof")
            return HFListing(rows, pages=page_index + 1)
        if not page:
            raise AlignmentError(f"Hugging Face {kind} pagination advertised an empty next page")
        if next_url in seen_pages:
            raise AlignmentError(f"Hugging Face {kind} pagination repeated a cursor")
        url = next_url
    raise AlignmentError(f"Hugging Face {kind} inventory exceeded {HF_MAX_PAGES}-page budget")


def validate_live(contract: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    unavailable: list[str] = []
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
    repository_revisions: dict[str, str] = {}
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
            repository_revisions[repository] = github_main_sha(repository, token)
        except Exception as exc:
            unavailable.append(f"canonical repository unavailable: {repository}: {type(exc).__name__}")

    models = list_hf("models")
    datasets = list_hf("datasets")
    spaces = list_hf("spaces")
    for kind, listing in (("models", models), ("datasets", datasets), ("spaces", spaces)):
        if (
            not isinstance(listing, HFListing)
            or listing.complete is not True
            or not (1 <= listing.pages <= HF_MAX_PAGES)
        ):
            raise AlignmentError(f"Hugging Face {kind} inventory coverage unavailable")
    snapshot = contract["huggingface_inventory_snapshot"]
    expected_portfolio = {row["repo_id"] for row in snapshot["portfolio_spaces"]}
    expected_inventory_only = {row["repo_id"] for row in snapshot["inventory_only_spaces"]}
    membership = contract["public_space_membership_observation"]
    membership_failures, listed_space_ids = validate_live_public_space_membership(spaces, membership)
    failures.extend(membership_failures)
    expected_public = {row["repo_id"] for row in membership["spaces"]}
    portfolio_ids = listed_space_ids & expected_portfolio
    inventory_only_ids = listed_space_ids & expected_inventory_only
    require(portfolio_ids == expected_portfolio, f"public portfolio Space drift: missing={sorted(expected_portfolio - portfolio_ids)} unexpected={sorted(portfolio_ids - expected_portfolio)}", failures)
    require(inventory_only_ids == expected_inventory_only, f"inventory-only Space drift: missing={sorted(expected_inventory_only - inventory_only_ids)} unexpected={sorted(inventory_only_ids - expected_inventory_only)}", failures)
    require(len(models) == snapshot["model_count"], f"model count drift: {len(models)}", failures)
    require(len(datasets) == snapshot["dataset_count"], f"dataset count drift: {len(datasets)}", failures)

    # The static README control surface is intentionally outside the portfolio
    # count and is not guaranteed to appear in the author-filtered bulk Space
    # listing. Prove its existence directly instead of turning a Hub listing
    # quirk into a false source-alignment failure.
    try:
        org_card_detail = load_json_bytes(
            fetch_bytes(f"{HF_API}/spaces/{ORG_CARD_SPACE_ID}"),
            label="Hugging Face organization-card Space",
        )
    except Exception as exc:
        org_card_present = False
        unavailable.append(
            "Hugging Face organization-card Space unavailable: "
            f"{type(exc).__name__}"
        )
    else:
        org_card_present = str(org_card_detail.get("id") or "") == ORG_CARD_SPACE_ID
        require(
            org_card_present,
            "Hugging Face organization-card Space identity mismatch",
            failures,
        )

    runtime_rows = list(
        contract["huggingface_inventory_snapshot"]["portfolio_spaces"]
    )

    def read_runtime_binding(
        indexed_row: tuple[int, Mapping[str, Any]],
    ) -> tuple[int, dict[str, Any] | None, str | None, str]:
        index, row = indexed_row
        repository = source_repository(row["deployment_source"])
        expected_revision = repository_revisions.get(repository)
        if expected_revision is None:
            return (
                index, None,
                f"runtime source authority unavailable for {row['repo_id']}: {repository}",
                "UNAVAILABLE",
            )
        observation = runtime_source_binding(row, expected_revision)
        failure = None
        verdict = "ALIGNED"
        if observation["matched"] is not True:
            if observation.get("observed_revision") is None:
                verdict = "UNAVAILABLE"
                failure = f"runtime source identity unavailable for {row['repo_id']}"
            else:
                verdict = "DIVERGENT"
                failure = (
                    f"runtime source revision drift for {row['repo_id']}: "
                    f"expected {repository}@{expected_revision}, observed "
                    f"{observation.get('observed_source')}@{observation['observed_revision']}"
                )
        return index, observation, failure, verdict

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(MAX_RUNTIME_WORKERS, max(1, len(runtime_rows)))
    ) as pool:
        runtime_results = list(
            pool.map(read_runtime_binding, enumerate(runtime_rows))
        )

    runtime_bindings: list[dict[str, Any]] = []
    for _, observation, failure, verdict in sorted(runtime_results):
        if observation is not None:
            runtime_bindings.append(observation)
        if failure is not None:
            (unavailable if verdict == "UNAVAILABLE" else failures).append(failure)

    org_card_binding: dict[str, Any] | None = None
    org_card = contract.get("organization_card_control_surface")
    if not isinstance(org_card, Mapping):
        unavailable.append("organization-card source contract unavailable")
    else:
        org_card_repository = source_repository(org_card.get("deployment_source"))
        org_card_revision = repository_revisions.get(org_card_repository)
        if org_card_revision is None:
            unavailable.append(
                f"organization-card source authority unavailable: {org_card_repository}"
            )
        else:
            try:
                org_card_binding = runtime_source_binding(org_card, org_card_revision)
            except Exception as exc:
                unavailable.append(
                    "organization-card source binding unavailable: "
                    f"{type(exc).__name__}"
                )
            else:
                if org_card_binding.get("matched") is not True:
                    if org_card_binding.get("observed_revision") is None:
                        unavailable.append("organization-card runtime source identity unavailable")
                    else:
                        failures.append(
                            "organization-card source revision drift: "
                            f"expected {org_card_repository}@{org_card_revision}, observed "
                            f"{org_card_binding.get('observed_source')}@"
                            f"{org_card_binding.get('observed_revision')}"
                        )

    return failures, {
        "unavailable": unavailable,
        "a11oy_contract_revision": a11oy_sha,
        "canonical_repositories": repository_observations,
        "runtime_source_bindings": runtime_bindings,
        "organization_card_source_binding": org_card_binding,
        "huggingface": {
            "models": len(models),
            "datasets": len(datasets),
            "inventory_coverage": {
                kind: {
                    "pages": getattr(listing, "pages", None),
                    "complete": getattr(listing, "complete", False),
                    "observed_at": getattr(listing, "observed_at", None),
                    "observed_count": len(listing),
                }
                for kind, listing in (
                    ("models", models), ("datasets", datasets), ("spaces", spaces)
                )
            },
            "spaces_including_org_card": len(
                listed_space_ids | ({ORG_CARD_SPACE_ID} if org_card_present else set())
            ),
            "public_listed_spaces": len(listed_space_ids),
            "public_space_membership_observation": {
                "observed_at": membership["observed_at"],
                "scope": membership["scope"],
                "expected_space_ids": sorted(expected_public),
                "listed_space_ids": sorted(listed_space_ids),
                "policy_authority": False,
                "policy_alignment": membership["policy_alignment"],
                "policy_conflicts": membership["policy_conflicts"],
            },
            "portfolio_spaces": len(portfolio_ids),
            "portfolio_space_ids": sorted(portfolio_ids),
            "inventory_only_spaces": len(inventory_only_ids),
            "inventory_only_space_ids": sorted(inventory_only_ids),
        },
    }


def checked_out_revision(root: Path) -> str:
    """Read the actual checkout, not a PR event's synthetic GITHUB_SHA.

    This only reads local Git metadata. It neither fetches nor changes refs.
    A missing or invalid checkout identity is not replaced with an environment
    value that could describe a different source tree.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise AlignmentError("checked-out Git source identity unavailable") from None
    revision = result.stdout.strip()
    if SHA40.fullmatch(revision) is None:
        raise AlignmentError("checked-out Git source identity is not an exact commit")
    return revision


def build_receipt(root: Path, *, live: bool) -> dict[str, Any]:
    contract_path = root / "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json"
    contract = load_json(contract_path)
    failures = validate_contract(contract)
    failures.extend(validate_documents(root, contract))
    unavailable: list[str] = []
    try:
        checkout_revision = checked_out_revision(root)
    except AlignmentError as exc:
        checkout_revision = "UNAVAILABLE"
        unavailable.append(str(exc))
    live_observation: dict[str, Any] | None = None
    if live:
        try:
            live_failures, live_observation = validate_live(contract)
            failures.extend(live_failures)
            unavailable.extend(live_observation.get("unavailable", []))
        except Exception as exc:
            unavailable.append(f"live alignment evidence unavailable: {type(exc).__name__}: {exc}")
    # Incomplete coverage takes precedence; verified divergence remains in failures.
    state = "UNAVAILABLE" if unavailable else "DIVERGENT" if failures else "ALIGNED"
    receipt = {
        "schema": "szl.estate-alignment-receipt/v1",
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "state": state,
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "source_revision": checkout_revision,
        "live_requested": live,
        "live_observation": live_observation,
        "failures": failures,
        "unavailable": unavailable,
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
