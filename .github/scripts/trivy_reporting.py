#!/usr/bin/env python3
"""Report fresh Trivy SARIF availability without fabricating scan results."""

import json
import os
from pathlib import Path
import sys


REPORT = Path("trivy-results.sarif")


def availability(outcome: str) -> tuple[bool, str]:
    if outcome != "success":
        return False, "scanner did not complete successfully"
    if REPORT.is_symlink() or not REPORT.is_file():
        return False, "scanner result file is missing"
    try:
        payload = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "scanner result is unreadable or invalid JSON"
    if not isinstance(payload, dict) or payload.get("version") != "2.1.0" or not isinstance(payload.get("runs"), list):
        return False, "scanner result has no SARIF 2.1.0 run envelope"
    return True, "fresh result from the successful scanner"


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "report"}:
        raise SystemExit("usage: trivy_reporting.py prepare|report")
    if sys.argv[1] == "prepare":
        REPORT.unlink(missing_ok=True)
        return 0

    available, reason = availability(os.environ.get("TRIVY_SCAN_OUTCOME", ""))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"available={str(available).lower()}\n")
    status = "available" if available else "unavailable"
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(f"Trivy SARIF report: **{status}** — {reason}.\n\n")
        summary.write("The separate CRITICAL/HIGH scan remains the authoritative failure gate.\n")
    if not available:
        print(f"::warning::Trivy SARIF unavailable: {reason}. No result will be uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
