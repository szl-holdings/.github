# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .config import PROBES
from .net import GitHub, probe, redact


def verify_public_estate(api: GitHub) -> dict[str, Any]:
    rows = [probe(contract) for contract in PROBES]
    expected_sha = None
    sha_error = None
    try:
        expected_sha = api.main_sha("szl-holdings/a11oy")
    except Exception as exc:
        sha_error = str(redact(str(exc)))
    build = next(row for row in rows if row["name"] == "a11oy-space-build-info")
    observed_sha = (build.get("contract_evidence") or {}).get("source_revision")
    revision_matches = bool(expected_sha and observed_sha == expected_sha)
    build["expected_source_revision"] = expected_sha
    build["source_revision_matches"] = revision_matches
    if not revision_matches:
        build["verified"] = False
    critical = [row for row in rows if row["critical"]]
    return {
        "expected_a11oy_main_sha": expected_sha,
        "expected_sha_error": sha_error,
        "observed_runtime_sha": observed_sha,
        "revision_matches": revision_matches,
        "checks": rows,
        "critical_verified": sum(1 for row in critical if row["verified"]),
        "critical_total": len(critical),
        "advisory_verified": sum(1 for row in rows if not row["critical"] and row["verified"]),
        "advisory_total": sum(1 for row in rows if not row["critical"]),
        "ready": bool(critical) and all(row["verified"] for row in critical),
    }


def terminal_status(report: Mapping[str, Any]) -> str:
    metadata = report.get("repository_metadata") or []
    card = report.get("vessels_card") or {}
    dispatches = report.get("workflow_controls") or []
    public = report.get("public_estate") or {}
    hard_block = any(row.get("state") == "BLOCKED" for row in metadata)
    hard_block = hard_block or card.get("state") in {
        "BLOCKED_SOURCE", "BLOCKED_NO_WRITE_TOKEN", "BLOCKED_WRITE", "READBACK_MISMATCH",
    }
    hard_block = hard_block or any(row.get("state") == "BLOCKED" for row in dispatches)
    metadata_ok = bool(metadata) and all(row.get("verified") for row in metadata)
    if hard_block:
        return "BLOCKED_AUTOMATABLE"
    if metadata_ok and card.get("verified") is True and public.get("ready") is True:
        return "AUTOMATED_FRONTIER_COMPLETE_OWNER_SIGNATURE_REMAINS"
    if any(row.get("state") == "DISPATCHED" for row in dispatches):
        return "CONVERGENCE_DISPATCHED"
    return "NOT_YET_CONVERGED"


def markdown_summary(report: Mapping[str, Any]) -> str:
    public, card = report["public_estate"], report["vessels_card"]
    lines = [
        "<!-- SZL-FRONTIER-PAYLOAD-CONVERGENCE-V1 -->",
        "## Frontier payload convergence receipt",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: **{report['status']}**",
        f"- Mode: `{'APPLY' if report['apply'] else 'DRY_RUN'}`",
        f"- Uploaded payload SHA-256: `{report['payload_sha256']}`",
        f"- Public critical checks: `{public['critical_verified']}/{public['critical_total']}`",
        f"- A11oy source parity: `{public['revision_matches']}`",
        f"- Vessels card: `{card.get('state')}` / verified `{card.get('verified')}`",
        "",
        "### Repository metadata",
    ]
    for row in report["repository_metadata"]:
        lines.append(
            f"- `{row['repository']}` — `{row.get('state')}`; verified `{row.get('verified')}`"
        )
    lines += ["", "### Existing control rails"]
    for row in report["workflow_controls"]:
        lines.append(f"- `{row['repository']}` / `{row['workflow']}` — `{row.get('state')}`")
    lines += [
        "",
        "### Guarded external boundary",
        "",
        "- The five named private Spaces were not made public. Each remains held for build and claims review.",
        "- Nemo-v3 reviewed jobspecs remain expired; no signature or queue authorization was attempted.",
        "- The owner must regenerate a fresh reviewed spec through the repository controller and complete the enrolled-key ceremony.",
        "- No token value is present in this receipt.",
        "",
    ]
    return "\n".join(lines)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(dict(value)), indent=2, sort_keys=True) + "\n")
