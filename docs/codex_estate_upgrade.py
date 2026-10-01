#!/usr/bin/env python3
"""
szl_codex_upgrade_payload.py

Fail-closed Codex operator for the SZL Holdings estate upgrade.

Does:
  - emit per-keeper work orders as JSON
  - print the mechanical production gate (defaults HOLD)
  - refuse forbidden actions
  - write a compact plan Codex can execute as draft PRs

Does not:
  - merge, deploy, publish, sign, mint repos, load quarantined joblib
  - claim PRODUCTION_AUTHORIZED, 180 theorems, or Λ uniqueness
  - contact GitHub/HF unless --live is passed (optional inventory only)

Usage:
    python szl_codex_upgrade_payload.py --emit
    python szl_codex_upgrade_payload.py --gate
    python szl_codex_upgrade_payload.py --refuse merge_pr_marked_do_not_merge
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "codex_work_orders"

LOCKED_EIGHT = ("F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22")
FORMULA_REGISTRY_N = 21
CONJECTURE_1 = "OPEN"
PRODUCTION = "HOLD"

KEEP = [
    "szl-holdings/a11oy",
    "szl-holdings/killinchu",
    "szl-holdings/david-leads",
    "szl-holdings/anatomy",
    "szl-holdings/immune",
    "szl-holdings/szl-real-estate",
    "szl-holdings/szl-atelier",
    "szl-holdings/szl-router",
]

KERNELS = [
    "szl-holdings/szl-formulas",
    "szl-holdings/szl-lambda-gate",
    "szl-holdings/szl-kernels",
    "szl-holdings/szl-receipt",
    "szl-holdings/lutar-lean",
    "szl-holdings/szl-frontier",
]

BENCHES = [
    "szl-holdings/frontier-bench",
    "szl-holdings/retrieval-bench",
]

PROOF = [
    "szl-holdings/a11oy-net",
    "szl-holdings/szl-holdings.github.io",
    "szl-holdings/.github",
]

FORBIDDEN = {
    "bypass_authentication",
    "extract_secrets",
    "scrape_private_data",
    "scrape_paywalled_content",
    "bypass_robots_or_terms",
    "download_gated_weights_without_permission",
    "rehost_model_artifacts_without_distribution_rights",
    "claim_license_without_verification",
    "fabricate_hardware_receipts",
    "fabricate_benchmark_results",
    "fabricate_independent_review",
    "weaken_required_checks",
    "bypass_branch_protection",
    "merge_pr_marked_do_not_merge",
    "deploy_without_explicit_approval",
    "publish_without_explicit_approval",
    "claim_production_without_measured_evidence",
    "claim_number_one_without_comparative_benchmark_evidence",
    "mint_public_repo_or_space",
    "revive_archived_hologram",
    "close_conjecture_1",
    "claim_180_theorems",
    "load_quarantined_joblib",
    "archive_keep_fleet_repo",
}

REQUIRED_PRODUCTION = [
    "qualified_receipt",
    "target_environment",
    "deployment_receipt",
    "monitoring_receipt",
    "rollback_plan",
    "explicit_release_approval",
    "post_deploy_verification",
]

WORK_ORDERS = [
    {
        "id": "E1",
        "repo": "szl-holdings/a11oy",
        "lane": "frontend+backend",
        "title": "Shared KANCHAY tokens, honest chips, operator panel",
        "do": [
            "Bind existing product CSS; 44px targets; no overflow; reduced-motion",
            "Show 21 formulas + locked-8 + Conjecture 1 OPEN",
            "ELECTRE / Choquet as separate operators, not Λ replacements",
        ],
        "do_not": ["claim production", "load joblib", "merge main"],
    },
    {
        "id": "E2",
        "repo": "szl-holdings/a11oy-net",
        "lane": "frontend",
        "title": "Proof-site language + token sync",
        "do": ["Proof language only", "No runtime-health claims"],
        "do_not": ["clone Command Center"],
    },
    {
        "id": "E3",
        "repo": "szl-holdings/szl-holdings.github.io",
        "lane": "frontend",
        "title": "Holdings door token sync",
        "do": ["Pointers to console/verify", "KANCHAY already in-tree"],
        "do_not": ["imitate product health"],
    },
    {
        "id": "E4",
        "repo": "szl-holdings/szl-formulas",
        "lane": "backend",
        "title": "ELECTRE + Choquet + Sugeno + A2 degree-1 tests",
        "do": [
            "Keep 21-name registry",
            "Add electre_iii_credibility, choquet_discrete, choquet_2additive, sugeno",
            "Test Λ(c·x)=c·Λ(x) and reject c^n",
        ],
        "do_not": ["change locked-8", "un-quarantine joblib", "claim uniqueness"],
    },
    {
        "id": "E5",
        "repo": "szl-holdings/szl-lambda-gate",
        "lane": "backend",
        "title": "Document operator stack order",
        "do": ["evidence → ELECTRE → Λ zero-kill → Choquet advisory"],
        "do_not": ["close Conjecture 1"],
    },
    {
        "id": "E6",
        "repo": "szl-holdings/szl-frontier",
        "lane": "backend",
        "title": "Sibling aggregators module only",
        "do": ["python/szl_frontier/aggregators.py if needed"],
        "do_not": ["rewrite engine.py admissions plane as Choquet"],
    },
    {
        "id": "E7",
        "repo": "szl-holdings/killinchu",
        "lane": "frontend",
        "title": "Adapter FE + synthetic disclaimer",
        "do": ["44px, overflow, chips", "no public effector"],
        "do_not": ["copy a11oy shell"],
    },
    {
        "id": "E8",
        "repo": "szl-holdings/szl-router",
        "lane": "frontend+backend",
        "title": "Receipt visibility + BLOCKED states",
        "do": ["per-answer receipt", "bounded fallback"],
        "do_not": ["print credentials or private hosts"],
    },
    {
        "id": "E9",
        "repo": "szl-holdings/frontier-bench",
        "lane": "backend",
        "title": "Public scoreboard honesty",
        "do": ["unconfigured engine = BLOCKED"],
        "do_not": ["fabricate TTFT"],
    },
    {
        "id": "E10",
        "repo": "szl-holdings/szl-receipt",
        "lane": "backend",
        "title": "UNSIGNED vs signed distinction",
        "do": ["never coerce missing sig"],
        "do_not": ["claim production from a chain"],
    },
    {
        "id": "E11",
        "repo": "szl-holdings/.github",
        "lane": "ci",
        "title": "Pin frontend verifier to full SHA",
        "do": ["callers must not float @main"],
        "do_not": ["give the action write permissions"],
    },
    {
        "id": "E12",
        "repo": "szl-holdings/.github",
        "lane": "inventory",
        "title": "Regenerate GH↔HF alignment from live APIs",
        "do": ["list drift", "label MEASURED-at-time"],
        "do_not": ["invent missing cards"],
    },
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refuse(action: str) -> dict:
    if action in FORBIDDEN:
        return {
            "allowed": False,
            "action": action,
            "reason": "Forbidden by estate fail-closed policy.",
        }
    return {"allowed": True, "action": action, "reason": "Not on the forbidden list; still HOLD for production."}


def production_gate(evidence_kinds: list[str], explicit_release_approval: bool) -> dict:
    if not explicit_release_approval:
        return {
            "decision": PRODUCTION,
            "reason": "No explicit release approval.",
            "missing": REQUIRED_PRODUCTION,
        }
    have = set(evidence_kinds)
    missing = [k for k in REQUIRED_PRODUCTION if k not in have]
    if missing:
        return {
            "decision": PRODUCTION,
            "reason": "Production evidence incomplete.",
            "missing": missing,
        }
    return {
        "decision": "READY_FOR_SEPARATE_DEPLOYMENT_CONFIRMATION",
        "reason": "Record complete. Deploy remains a distinct owner action.",
        "missing": [],
    }


def doctrine() -> dict:
    return {
        "lambda_uniqueness": CONJECTURE_1,
        "locked_eight": list(LOCKED_EIGHT),
        "formula_registry_n": FORMULA_REGISTRY_N,
        "wave_cards_are_theorems": False,
        "production": PRODUCTION,
        "trust_ceiling": 0.97,
        "joblib_default": "QUARANTINED",
        "stack": [
            "evidence_validity",
            "electre_discordance",
            "lambda_zero_kill_advisory",
            "choquet_sugeno_advisory",
        ],
        "origins": {
            "product": "https://a-11-oy.com",
            "proof": "https://a11oy.net",
            "holdings": "https://holdings.a-11-oy.com",
            "github": "https://github.com/szl-holdings",
            "hub": "https://huggingface.co/SZLHOLDINGS",
        },
    }


def emit(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": "szl-codex-upgrade/1",
        "generated_at": now(),
        "doctrine": doctrine(),
        "keep_fleet": KEEP,
        "kernels": KERNELS,
        "benches": BENCHES,
        "proof": PROOF,
        "work_orders": WORK_ORDERS,
        "forbidden": sorted(FORBIDDEN),
        "gate": production_gate([], False),
        "codex_start": [
            "Read CODEX_ESTATE_UPGRADE.md",
            "Pick one work order",
            "Branch from main; draft PR only",
            "Smallest diff; fail-closed tests",
            "PR body: Conjecture 1 OPEN, locked-8 frozen, PRODUCTION HOLD",
            "Stop for owner review",
        ],
    }
    (out / "bundle.json").write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    for wo in WORK_ORDERS:
        (out / f"{wo['id']}.json").write_text(json.dumps(wo, indent=2) + "\n", encoding="utf-8")
    (out / "HOLD.txt").write_text(
        "PRODUCTION_AUTHORIZED = HOLD\n"
        "Λ uniqueness = Conjecture 1 OPEN\n"
        "locked-8 frozen\n"
        "21 formulas SOFTWARE\n"
        "~180 wave cards are not theorems\n",
        encoding="utf-8",
    )
    return bundle


def main() -> None:
    p = argparse.ArgumentParser(description="SZL Codex upgrade operator (fail-closed)")
    p.add_argument("--emit", action="store_true", help="Write work-order JSON under codex_work_orders/")
    p.add_argument("--gate", action="store_true", help="Print production gate")
    p.add_argument("--refuse", metavar="ACTION", help="Test a forbidden action")
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()

    if args.refuse:
        print(json.dumps(refuse(args.refuse), indent=2))
        return
    if args.gate:
        print(json.dumps(production_gate([], False), indent=2))
        return
    bundle = emit(Path(args.out))
    print(
        json.dumps(
            {
                "wrote": str(Path(args.out)),
                "orders": len(bundle["work_orders"]),
                "production": bundle["gate"]["decision"],
                "conjecture_1": CONJECTURE_1,
                "locked_eight_n": len(LOCKED_EIGHT),
                "formulas": FORMULA_REGISTRY_N,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
