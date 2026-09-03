# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from .config import (
    GITHUB_TOKEN_NAMES, HF_TOKEN_NAMES, PAYLOAD_SHA256, SCHEMA,
)
from .controls import (
    converge_repository_metadata, converge_vessels_card,
    dispatch_controls, review_private_spaces,
)
from .net import GitHub, redact
from .verify import markdown_summary, terminal_status, verify_public_estate, write_json


def token_from_environment(names: Iterable[str]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return None, None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute the automatable remainder of the 2026-09-03 SZL frontier payload."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dispatch-controls", action="store_true")
    parser.add_argument("--enforce-ready", action="store_true")
    args = parser.parse_args(argv)

    gh_token, gh_source = token_from_environment(GITHUB_TOKEN_NAMES)
    hf_token, hf_source = token_from_environment(HF_TOKEN_NAMES)
    github = GitHub(gh_token, apply=args.apply)
    report = {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "payload_sha256": PAYLOAD_SHA256,
        "apply": args.apply,
        "dispatch_controls_requested": args.dispatch_controls,
        "token_values_recorded": False,
        "github_token_available": bool(gh_token),
        "github_token_source_name": gh_source,
        "hf_token_available": bool(hf_token),
        "hf_token_source_name": hf_source,
        "private_space_visibility_mutated": False,
        "branch_protection_mutated": False,
        "secrets_mutated": False,
        "cloudflare_mutated_by_this_controller": False,
        "nemo_signature_attempted": False,
        "nemo_queue_mutated": False,
        "nemo": {
            "issues": [
                "szl-holdings/szl-gpu-bridge#93",
                "szl-holdings/szl-gpu-bridge#20",
            ],
            "state": "EXPIRED_AWAITING_ENGINE_SIGNATURE",
            "next_action": (
                "regenerate a fresh reviewed jobspec through the repository controller, "
                "then run the enrolled owner-key signing ceremony"
            ),
            "automated_here": False,
        },
    }
    report["repository_metadata"] = converge_repository_metadata(github)
    report["vessels_card"] = converge_vessels_card(hf_token, apply=args.apply)
    report["private_spaces"] = review_private_spaces(hf_token)
    report["workflow_controls"] = dispatch_controls(
        github, enabled=args.dispatch_controls
    )
    report["public_estate"] = verify_public_estate(github)
    report["status"] = terminal_status(report)
    summary = markdown_summary(report)
    report["summary_sha256"] = hashlib.sha256(summary.encode()).hexdigest()

    write_json(args.report, report)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary + "\n")
    print(json.dumps(redact(report), indent=2, sort_keys=True))

    if report["status"] == "BLOCKED_AUTOMATABLE":
        return 2
    if args.enforce_ready and not report["public_estate"]["ready"]:
        return 1
    return 0
