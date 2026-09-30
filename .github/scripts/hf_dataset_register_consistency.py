#!/usr/bin/env python3
"""Compare a pinned dataset register with captured governance metadata offline.

This checks consistency of a supplied szl.dataset-collection-evidence-audit/v1
snapshot. It neither authenticates the audit nor approves rights/training.
It reads no credentials, dataset payloads, remote services or model weights.
Exit 0: matched restrictive metadata; 1: conflict; 2: unknown/invalid input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

SCHEMA = "szl.dataset-collection-evidence-audit/v1"
REGISTER_ID = "SZLHOLDINGS/model-bom"
REGISTER_PATH = "DATASET_LICENSE_REGISTER.csv"
HEADER = ("dataset_id", "license", "training_eligibility", "source_datasets",
          "downloads_30d", "last_modified", "notes")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
REPO_ID = re.compile(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
ELIGIBLE = {"ELIGIBLE", "ELIGIBLE-WITH-ATTRIBUTION"}
RESTRICTIVE = {"BANNED", "HELD-COUNSEL", "BLOCKED", "HELD", "RESTRICTED",
               "REVIEW-REQUIRED", "NOT-ELIGIBLE", "NOT-EVALUATED"}
CATALOG_ONLY = {"SZLHOLDINGS/killinchu-osint-corpus",
                "SZLHOLDINGS/oac-clinical-transport-observability-synthetic"}
DOCUMENT_SCHEMAS = {
    "szl.hf-status/v1": ("training_suitability",),
    "szl.hf-license-candidate-status/v1": ("claims", "training_suitability"),
    "szl.hf-provenance/v1": ("dataset_artifact_provenance", "training_suitability", "state"),
    "szl.hf-license-candidate-provenance/v1": ("evidence_boundaries", "training_suitability"),
}


class SnapshotError(ValueError):
    """Invalid or inconsistent revision-bound metadata input."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def _state(value: object) -> str:
    return value.strip().upper().replace("_", "-") if isinstance(value, str) else "UNKNOWN"


def _revision(value: object, label: str) -> str:
    _require(isinstance(value, str) and bool(HEX40.fullmatch(value)),
             f"{label}: full immutable 40-character revision required")
    return value


def _envelope(envelope: object, repo_id: str, revision: str, path: str) -> None:
    _require(isinstance(envelope, dict), f"{repo_id}/{path}: evidence envelope required")
    _require(envelope.get("http_status") == 200 and envelope.get("error") is None
             and envelope.get("truncated") is False, f"{repo_id}/{path}: incomplete evidence")
    _require(envelope.get("server_revision") == revision,
             f"{repo_id}/{path}: captured/server revision mismatch")
    _require(envelope.get("url") == f"https://huggingface.co/datasets/{repo_id}/raw/{revision}/{path}",
             f"{repo_id}/{path}: exact immutable raw URL required")
    digest = envelope.get("content_sha256")
    _require(isinstance(digest, str) and bool(HEX64.fullmatch(digest)),
             f"{repo_id}/{path}: SHA-256 evidence required")


def _register(snapshot: dict, assets: dict) -> tuple[dict, str]:
    register = snapshot.get("license_register")
    _require(isinstance(register, dict) and register.get("id") == REGISTER_ID,
             "model-bom register descriptor required")
    revision = _revision(register.get("revision"), "register")
    _require(REGISTER_ID in assets and assets[REGISTER_ID]["revision"] == revision,
             "register dataset and descriptor revisions must agree")
    contract = assets[REGISTER_ID].get("provenance", {}).get("contracts", {}).get(REGISTER_PATH)
    _require(isinstance(contract, dict), "raw register contract required")
    _envelope(contract.get("evidence"), REGISTER_ID, revision, REGISTER_PATH)
    _require(register.get("source_url") == contract["evidence"]["url"], "register source URL drift")
    content = contract.get("content")
    _require(isinstance(content, str), "register content must be captured CSV text")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _require(digest == contract["evidence"]["content_sha256"], "register CSV digest mismatch")
    reader = csv.DictReader(io.StringIO(content))
    _require(tuple(reader.fieldnames or ()) == HEADER, "unexpected dataset register header")
    rows = {}
    for row in reader:
        _require(None not in row and all(isinstance(v, str) for v in row.values()), "malformed CSV row")
        repo_id = row["dataset_id"].strip()
        _require(bool(REPO_ID.fullmatch(repo_id)) and ".." not in repo_id, "invalid register dataset ID")
        _require(repo_id not in rows, f"duplicate register dataset ID: {repo_id}")
        rows[repo_id] = row
    _require(type(register.get("observed_rows")) is int and register["observed_rows"] == len(rows),
             "register row count drift")
    return rows, digest


def _document_states(asset: dict) -> tuple[list[str], list[str]]:
    restrictions, observed = [], []
    contracts = asset.get("provenance", {}).get("contracts", {})
    _require(isinstance(contracts, dict), "governance contracts must be an object")
    for path in ("status.json", "provenance.json"):
        if path not in contracts:
            continue
        contract = contracts[path]
        _require(isinstance(contract, dict), "governance contract must be an object")
        _envelope(contract.get("evidence"), asset["id"], asset["revision"], path)
        content = contract.get("content")
        _require(isinstance(content, dict), "governance content must be an object")
        for identity in (content.get("repository_id"), content.get("subject", {}).get("repo_id"),
                         content.get("repository", {}).get("id")):
            _require(identity is None or identity == asset["id"], "governance repository identity drift")
        # These historical fields describe earlier publication/source states;
        # they are deliberately not compared to the captured file revision.
        pointer = DOCUMENT_SCHEMAS.get(content.get("schema"))
        if pointer is None:
            observed.append("UNKNOWN")
            continue
        value = content
        for key in pointer:
            value = value.get(key) if isinstance(value, dict) else None
        state = _state(value)
        observed.append(state)
        if state in RESTRICTIVE:
            restrictions.append(state)
    return restrictions, observed


def _compare(asset: dict, row: dict | None) -> dict:
    repo_id = asset["id"]
    registry = _state(row["training_eligibility"]) if row else "UNKNOWN"
    result = {"id": repo_id, "revision": asset["revision"], "register_eligibility": registry,
              "license_consistency": "UNKNOWN", "training_comparison": "UNKNOWN",
              "training_disposition": "UNKNOWN", "training_allowed": None,
              "restrictions": [], "findings": [], "rights_clearance": "NOT_ESTABLISHED"}
    def finding(code: str) -> None:
        result["findings"].append({"code": code})
    if registry in RESTRICTIVE:
        result["restrictions"].append(registry)
        result["training_allowed"] = False
        result["training_disposition"] = registry
    if row is None:
        finding("MISSING_REGISTER_ROW")
    # Catalog-only entries retain IDs and registry restrictions without reading
    # their cards, governance documents, inventories, schemas or payloads.
    if repo_id in CATALOG_ONLY or asset.get("scope") == "catalog-only" or asset.get("exclusion_reason"):
        finding("CATALOG_ONLY_NOT_INSPECTED")
        return result
    _envelope(asset.get("card_evidence"), repo_id, asset["revision"], "README.md")
    metadata = asset.get("card_metadata")
    _require(isinstance(metadata, dict), f"{repo_id}: card metadata required")
    declared = metadata.get("license")
    if row and isinstance(declared, str) and declared.strip() and row["license"].strip():
        result["license_consistency"] = ("MATCHED_METADATA" if declared.strip().lower() == row["license"].strip().lower() else "CONFLICT")
        if result["license_consistency"] == "CONFLICT":
            finding("REGISTER_LICENSE_DECLARATION_MISMATCH")
    restrictions, observed = _document_states(asset)
    if metadata.get("training_eligible") is False:
        restrictions.append("BLOCKED")
    if "all-rights-reserved" in str(metadata.get("license_name", "")).lower():
        restrictions.append("RESTRICTED")
    excerpts = asset.get("card_claim_excerpts", [])
    _require(isinstance(excerpts, list), "card excerpts must be a list")
    for excerpt in excerpts:
        _require(isinstance(excerpt, dict) and isinstance(excerpt.get("text"), str)
                 and type(excerpt.get("line")) is int and excerpt["line"] > 0, "invalid card excerpt")
        text = excerpt["text"].lower()
        # Excerpts can quote another dataset's restrictions or a historical
        # register. Do not reclassify this asset from unstructured prose.
        # Missing machine-readable clearance remains UNKNOWN regardless.
        if "packaging" in text and ("source documents" in text or "original rights" in text):
            finding("PACKAGING_LICENSE_NOT_SOURCE_CLEARANCE")
        if "rights" in text and "not_evaluated" in text:
            finding("RIGHTS_REVIEW_NOT_EVALUATED")
    result["restrictions"] = sorted(set(result["restrictions"] + restrictions))
    if result["restrictions"]:
        result["training_allowed"] = False
        result["training_disposition"] = next(x for x in ("BANNED", "HELD-COUNSEL", "BLOCKED", "HELD", "RESTRICTED", "REVIEW-REQUIRED", "NOT-ELIGIBLE", "NOT-EVALUATED") if x in result["restrictions"])
    # Missing row remains UNKNOWN even when a separate restriction is observed.
    if row is None:
        result["training_disposition"] = "UNKNOWN"
    elif registry in ELIGIBLE:
        result["training_comparison"] = "CONFLICT"
        finding("ELIGIBILITY_CONFLICT_RESTRICTION" if result["restrictions"] else "ELIGIBILITY_UNSUBSTANTIATED")
        if not result["restrictions"]:
            result["training_disposition"] = "UNKNOWN"
    elif registry in RESTRICTIVE:
        result["training_comparison"] = "MATCHED_METADATA"
    else:
        finding("UNKNOWN_REGISTER_DISPOSITION")
    result["observed_training_states"] = observed or ["UNKNOWN"]
    return result


def check_snapshot(snapshot: dict) -> dict:
    _require(isinstance(snapshot, dict) and snapshot.get("schema") == SCHEMA, "unsupported audit metadata schema")
    datasets = snapshot.get("datasets")
    _require(isinstance(datasets, list) and 0 < len(datasets) <= 1000, "bounded dataset metadata inventory required")
    assets = {}
    for asset in datasets:
        _require(isinstance(asset, dict) and asset.get("asset_type") == "dataset", "dataset identity required")
        repo_id = asset.get("id")
        _require(isinstance(repo_id, str) and bool(REPO_ID.fullmatch(repo_id)) and ".." not in repo_id, "invalid dataset ID")
        _require(repo_id not in assets, f"duplicate observed dataset ID: {repo_id}")
        _revision(asset.get("revision"), repo_id)
        assets[repo_id] = asset
    coverage = snapshot.get("coverage")
    _require(isinstance(coverage, dict) and type(coverage.get("public_datasets_listed")) is int
             and coverage["public_datasets_listed"] == len(assets), "captured public inventory count drift")
    rows, digest = _register(snapshot, assets)
    compared = [_compare(asset, rows.get(repo_id)) for repo_id, asset in sorted(assets.items())]
    for repo_id in sorted(rows.keys() - assets.keys()):
        compared.append({"id": repo_id, "revision": None, "register_eligibility": _state(rows[repo_id]["training_eligibility"]),
                         "license_consistency": "UNKNOWN", "training_comparison": "UNKNOWN",
                         "training_disposition": "UNKNOWN", "training_allowed": False if _state(rows[repo_id]["training_eligibility"]) in RESTRICTIVE else None,
                         "restrictions": [], "findings": [{"code": "NOT_IN_CAPTURED_PUBLIC_INVENTORY"}],
                         "rights_clearance": "NOT_ESTABLISHED"})
    conflicts = sum("CONFLICT" in (x["license_consistency"], x["training_comparison"]) for x in compared)
    unknowns = sum("UNKNOWN" in (x["license_consistency"], x["training_comparison"]) for x in compared)
    state = "CONFLICT" if conflicts else "UNKNOWN" if unknowns else "MATCHED_METADATA"
    assert all(x["training_allowed"] in (False, None) for x in compared)
    return {"schema": "szl.dataset-register-consistency/v1", "state": state,
            "register_revision": snapshot["license_register"]["revision"], "register_csv_sha256": digest,
            "assets": compared, "counts": {"inventory": len(assets), "register_rows": len(rows),
                                          "conflicting_assets": conflicts, "unknown_assets": unknowns,
                                          "missing_register_rows": len(assets.keys() - rows.keys())},
            "legal_approval": False, "training_approval": False, "rights_changed": False,
            "hub_requests": False, "generator": "UNKNOWN_NOT_IDENTIFIED",
            "content_claim_fidelity": "INHERITED_FROM_SUPPLIED_AUDIT_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED",
            "limits": ["Checks a captured exact-revision metadata snapshot, not current Hub heads or legal rights.",
                       "CSV bytes are digest checked; normalized governance contents and card excerpts inherit audit fidelity.",
                       "License declaration equality does not establish source-data clearance or training permission.",
                       "Historical publication parent/source fields are preserved; no generator or byte-parity attestation is invented."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.report:
            _require(args.report.resolve() != args.snapshot.resolve(), "report must not overwrite input snapshot")
            _require(not args.report.exists(), "report must be a new file; preserve previous evidence")
        _require(args.snapshot.stat().st_size <= 4 * 1024 * 1024, "metadata snapshot exceeds 4 MiB bound")
        report = check_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8-sig")))
        exit_code = {"MATCHED_METADATA": 0, "CONFLICT": 1, "UNKNOWN": 2}[report["state"]]
    except (SnapshotError, OSError, UnicodeError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        report = {"state": "INVALID_METADATA_INPUT", "error": str(exc), "legal_approval": False,
                  "training_approval": False, "rights_changed": False, "hub_requests": False}
        print(json.dumps(report, sort_keys=True))
        return 2
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError as exc:
            print(json.dumps({"state": "REPORT_WRITE_FAILED", "error": str(exc)}))
            return 2
    else:
        print(text, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
