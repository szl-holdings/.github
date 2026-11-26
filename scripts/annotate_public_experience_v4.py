"""Project the measured responsive browser report into the v4 evidence schema.

The browser probe measures geometry and runtime reachability. The remaining v4
content, accessibility, developer, and diligence criteria stay UNAVAILABLE
until a dedicated probe measures them. This script never turns missing evidence
into PASS and never grants release authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


V4_SCHEMA = "szl.public-experience-v4-runtime/v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def criterion(status: str, evidence: str) -> dict[str, str]:
    return {"status": status, "evidence": evidence}


def build_report(source: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    surface_count = source.get("surfaceCount")
    pass_count = source.get("passCount")
    fail_count = source.get("failCount")
    if not all(isinstance(value, int) and value >= 0 for value in (surface_count, pass_count, fail_count)):
        raise ValueError("normalized report counts are invalid")
    if surface_count == 0 or pass_count + fail_count != surface_count:
        raise ValueError("normalized report counts are inconsistent")

    geometry_status = "PASS" if fail_count == 0 else "FAIL"
    criteria = {
        "responsive_viewports": criterion(geometry_status, "normalized v3.1 browser measurements"),
        "runtime_reachability": criterion(geometry_status, "normalized v3.1 browser and page-error measurements"),
        "accessibility_semantics": criterion("UNAVAILABLE", "no v4 semantic/accessibility probe is wired"),
        "first_time_user_clarity": criterion("UNAVAILABLE", "no v4 content probe is wired"),
        "developer_experience": criterion("UNAVAILABLE", "no v4 source/version-link probe is wired"),
        "investor_diligence_clarity": criterion("UNAVAILABLE", "no v4 claim-evidence probe is wired"),
    }
    return {
        "schema": V4_SCHEMA,
        "measurementBasis": "v3.1 browser geometry and runtime probe projected onto the v4 release checklist",
        "observedAt": source.get("observedAt"),
        "projectedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "surfaceCount": surface_count,
        "passCount": pass_count,
        "failCount": fail_count,
        "criteria": criteria,
        "status": "FAIL" if fail_count else "INCOMPLETE",
        "disposition": "HOLD",
        "sourceReportSha256": source_sha256,
        "authority": {
            "sourceRollout": False,
            "merge": False,
            "providerMutation": False,
            "automaticPromotion": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(source, sha256_file(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": V4_SCHEMA, "status": report["status"], "disposition": "HOLD"}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


