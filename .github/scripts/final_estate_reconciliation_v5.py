#!/usr/bin/env python3
"""Reconcile the active SZL public estate from immutable evidence and safe probes.

Replit Unified Control Hub is explicitly decommissioned from the active estate.
Its closed issue is verified as a scope decision; no Replit operational claim is
made. When invoked by the readiness workflow, a failed upstream conclusion is a
first-class fail-closed gate so stale issue evidence cannot be reused as green.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from final_estate_v5_core import (
    EVIDENCE_ISSUES,
    ORG,
    PROBES,
    REPLIT_DECOMMISSION_ISSUE,
    REPORT_MARKER,
    REPORT_SCHEMA,
    SHA40,
    Gate,
    GitHubClient,
)

from final_estate_v5_evidence import (
    evaluate_issue_gate,
    evaluate_release_revision_consistency,
    evaluate_replit_decommission,
)
from final_estate_v5_probes import (
    evaluate_a11oy_source,
    evaluate_open_public_prs,
    safe_probe,
)

MAX_REPORT_BYTES = 2 * 1024 * 1024


def evaluate_controller_source(client: GitHubClient) -> Gate:
    """Observe the checked-out event source and protected main; never a lease."""
    try:
        expected = os.environ.get("GITHUB_SHA", "")
        event = os.environ.get("GITHUB_EVENT_NAME", "")
        if (SHA40.fullmatch(expected) is None or expected == "0" * 40
                or os.environ.get("EVIDENCE_GENERATION") != expected
                or os.environ.get("GITHUB_REPOSITORY") != "szl-holdings/.github"
                or os.environ.get("GITHUB_REF") != "refs/heads/main"
                or event not in {"push", "workflow_run", "workflow_dispatch"}
                or (event == "workflow_run" and os.environ.get("UPSTREAM_WORKFLOW")
                    != "HF Release Readiness Terminal")):
            raise RuntimeError("CONTROLLER_EVENT_SOURCE_REJECTED")
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip()
        if actual != expected or client.controller_head() != expected:
            raise RuntimeError("CONTROLLER_SOURCE_MOVED_OR_MISMATCHED")
        return Gate("source:controller_protected_main", True,
                    "checked-out event source equals observed protected main",
                    {"repository": "szl-holdings/.github", "revision": expected,
                     "event": event, "atomic_lease": False})
    except Exception:
        return Gate("source:controller_protected_main", False,
                    "CONTROLLER_SOURCE_UNVERIFIED", {})


def evaluate_upstream_readiness() -> Gate:
    workflow = str(os.environ.get("UPSTREAM_WORKFLOW") or "").strip()
    conclusion = str(os.environ.get("UPSTREAM_CONCLUSION") or "").strip().lower()
    run_url = str(os.environ.get("UPSTREAM_RUN_URL") or "").strip()
    if not workflow:
        return Gate(
            "workflow:hf_release_readiness_terminal",
            True,
            "direct invocation; deterministic issue evidence remains authoritative",
            {
                "event": os.environ.get("GITHUB_EVENT_NAME") or "local",
                "workflow_run_bound": False,
            },
        )
    ok = conclusion == "success"
    return Gate(
        "workflow:hf_release_readiness_terminal",
        ok,
        f"workflow={workflow}; conclusion={conclusion or 'missing'}",
        {
            "workflow": workflow,
            "conclusion": conclusion or None,
            "run_url": run_url or None,
            "workflow_run_bound": True,
        },
    )


def evaluate(client: GitHubClient) -> dict[str, Any]:
    gates = [evaluate_controller_source(client), evaluate_upstream_readiness()]
    if gates[0].ok:
        gates.extend(
            evaluate_issue_gate(client, name, repo, number)
            for name, (repo, number) in EVIDENCE_ISSUES.items()
        )
        gates.append(evaluate_release_revision_consistency(client))
        gates.append(evaluate_replit_decommission(client))
        source_gate, source_sha = evaluate_a11oy_source(client)
        gates.append(source_gate)
        gates.extend(safe_probe(name, spec, source_sha) for name, spec in PROBES.items())
        gates.append(evaluate_open_public_prs(client))
        gates.append(evaluate_controller_source(client))
    operational = all(gate.ok for gate in gates)
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": ORG,
        "active_estate": [
            "GitHub protected source and evidence",
            "Hugging Face inventory, Lake, first-class Kernels, and canonical A11oy",
            "a-11-oy.com",
            "a11oy.net",
        ],
        "excluded_lanes": [
            {
                "name": "replit_unified_control_hub",
                "status": "DECOMMISSIONED_NOT_IN_ACTIVE_ESTATE",
                "evidence_issue": (
                    f"https://github.com/{REPLIT_DECOMMISSION_ISSUE[0]}"
                    f"/issues/{REPLIT_DECOMMISSION_ISSUE[1]}"
                ),
                "operational_claim": False,
            }
        ],
        "status": "OPERATIONAL_VERIFIED" if operational else "NOT_VERIFIED",
        "operational_verified": operational,
        "gates": [asdict(gate) for gate in gates],
        "summary": {
            "ok": sum(gate.ok for gate in gates),
            "error": sum(not gate.ok for gate in gates),
            "total": len(gates),
        },
        "boundaries": [
            "This verifier performs bounded GitHub evidence reads and public probes, then writes its local report and per-run artifact; it never updates issues.",
            "The checked-out event source must equal observed protected main before and after observations; these readbacks are not an atomic lease.",
            "A failed upstream HF Release Readiness Terminal workflow is an explicit fail-closed gate; stale evidence cannot substitute for a completed run.",
            "API routes may be GET-only; HEAD is required only for document/static surfaces whose contract declares it.",
            "It does not mutate any Hugging Face asset, deployment, visibility, hardware, model, dataset, kernel, collection, bucket, branch rule, training state, weight, qualification, or promotion state.",
            "Replit Unified Control Hub is decommissioned from the active estate and receives no operational claim.",
            "OPERATIONAL_VERIFIED requires every active gate to pass in the same run, including zero open pull requests in the public estate.",
            "This status does not claim SZL-Nemo v3 is trained or that the Brain is a fully trained neural model.",
        ],
    }


def issue_body(report: Mapping[str, Any], run_url: str | None) -> str:
    lines = [
        f"<!-- {REPORT_MARKER} -->",
        "# SZL Holdings active-estate reconciliation",
        "",
        f"- Status: **{report['status']}**",
        f"- Generated: `{report['generated_at']}`",
        "- Replit Unified Control Hub: **DECOMMISSIONED / NOT IN ACTIVE ESTATE**",
    ]
    if run_url:
        lines.append(f"- Run: {run_url}")
    lines.extend(["", "| Gate | Result | Detail |", "|---|---|---|"])
    for gate in report["gates"]:
        detail = str(gate["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{gate['name']}` | `{'PASS' if gate['ok'] else 'FAIL'}` | {detail} |"
        )
    lines.extend(
        ["", "```json", json.dumps(report, indent=2, sort_keys=True), "```", ""]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="reports/final-estate-reconciliation-v5.json",
    )
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    client = GitHubClient(token)
    report = evaluate(client)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise RuntimeError("REPORT_BUDGET_EXCEEDED")
    output.write_bytes(encoded)
    print(encoded.decode("utf-8"), end="")
    return 1 if args.enforce and not report["operational_verified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
