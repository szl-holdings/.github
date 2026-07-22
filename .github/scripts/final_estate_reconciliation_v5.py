#!/usr/bin/env python3
"""Reconcile the active SZL public estate from immutable evidence and safe probes.

Replit Unified Control Hub is explicitly decommissioned from the active estate. Its
closed issue is verified as a scope decision; no Replit operational claim is made.
"""
from __future__ import annotations

import argparse
import json
import os
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


def evaluate(client: GitHubClient) -> dict[str, Any]:
    gates = [
        evaluate_issue_gate(client, name, repo, number)
        for name, (repo, number) in EVIDENCE_ISSUES.items()
    ]
    gates.append(evaluate_release_revision_consistency(client))
    gates.append(evaluate_replit_decommission(client))
    source_gate, source_sha = evaluate_a11oy_source(client)
    gates.append(source_gate)
    gates.extend(safe_probe(name, spec, source_sha) for name, spec in PROBES.items())
    gates.append(evaluate_open_public_prs(client))
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
            "This controller performs GitHub evidence reads, contract-aware public probes, and one deterministic issue update only.",
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
    lines.extend(["", "```json", json.dumps(report, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/final-estate-reconciliation-v5.json")
    parser.add_argument("--publish-issue", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubClient(token)
    report = evaluate(client)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.publish_issue:
        run_url = None
        if all(
            os.environ.get(key)
            for key in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
        ):
            run_url = (
                f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
                f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            )
        client.upsert_report_issue(issue_body(report, run_url), report["operational_verified"])
    return 1 if args.enforce and not report["operational_verified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
