#!/usr/bin/env python3
"""Build the ntfy alert payload for the code-security-drift workflow.

Task #745 added an inline bash/jq step to ``code-security-drift.yml`` that, on a
scheduled run, pages the shared alert relay when the managed-security-config
drift check finds drift (exit 1) or could not complete (auth/API failure,
exit 2). That message-building logic — reading ``.errors[]`` from the committed
``code_security_report.json`` for the drift case, the generic could-not-complete
text for the failure case, and the ``\\n\\n`` separators (one of which a previous
revision silently stripped via command substitution) — lived only inside YAML
and was untested. A future edit could quietly produce an empty or malformed
alert and we'd only notice during a real incident.

This module extracts that logic into a testable unit so ``test_build_drift_alert.py``
can lock the contract network-free:

  exit 1 + readable report -> names the offending repo(s) + fix hint
  exit 2 / missing / unreadable report -> "COULD NOT COMPLETE" + grepped detail
  neither case drops its ``\\n\\n`` separators

The workflow calls this script and pipes the printed payload straight to curl,
so the only logic left in YAML is "run the check, capture the exit code, POST
the payload" — nothing that can silently malform the message.

Stdlib only (argparse/json/re); no third-party deps, no network.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

# Prefix shared with the other org guards' alerts; the relay flattens the
# Slack-compatible {"text": ...} payload to clean ntfy text.
PREFIX = "\U0001F6A8 [szl-holdings] "  # 🚨
CANONICAL_CONFIG = "252588"

# Kept verbatim so the alert wording does not silently drift from the YAML it
# replaced (and from the operator-facing docs that quote it).
_DRIFT_HEAD = (
    "Code-security config drift detected in szl-holdings "
    f"(config {CANONICAL_CONFIG}).\n\n"
)
_DRIFT_FIX = (
    f"\n\nFix: re-attach config {CANONICAL_CONFIG} "
    f"(POST .../configurations/{CANONICAL_CONFIG}/attach {{scope:all}}) or add a "
    "reasoned entry to .github/data/code_security_allowlist.json."
)


def _grep_error_detail(drift_output: str, *, max_lines: int = 5) -> str:
    """Mirror ``grep -iE 'error' | tail -n N | sed 's/^[[:space:]]*//'``.

    Returns the last ``max_lines`` matching lines, each left-stripped, joined by
    a single newline (no trailing newline — command substitution stripped it).
    """
    matched = [ln for ln in drift_output.splitlines() if re.search("error", ln, re.IGNORECASE)]
    matched = matched[-max_lines:]
    return "\n".join(ln.lstrip() for ln in matched)


def build_text(exit_code: int, report: Optional[dict], drift_output: str = "") -> str:
    """Build the alert body (without the shared 🚨 prefix).

    ``report`` is the parsed ``code_security_report.json`` (or ``None`` when the
    file is missing/unreadable). The drift wording is used ONLY when the check
    reported real drift (exit 1) AND a report is available; every other case —
    exit 2, or exit 1 with no usable report — uses the could-not-complete
    wording so coverage never *looks* confirmed when the check could not run.
    """
    if exit_code == 1 and report is not None:
        errors = report.get("errors") or []
        body = "\n".join(str(e) for e in errors)
        return _DRIFT_HEAD + body + _DRIFT_FIX

    text = (
        "Code-security drift check COULD NOT COMPLETE (auth/API failure, exit "
        f"{exit_code}). The org code-security endpoints need an org-admin "
        "SZL_GITHUB_TOKEN \u2014 coverage cannot be confirmed."
    )
    detail = _grep_error_detail(drift_output)
    if detail:
        # Explicit literal newlines — a previous revision built this with
        # ``${detail:+$(printf '\n\n')$detail}`` and command substitution
        # stripped the trailing newlines, gluing the detail onto the sentence.
        text = text + "\n\n" + detail
    return text


def build_payload(exit_code: int, report: Optional[dict], drift_output: str = "") -> dict:
    """The full Slack-compatible relay payload, prefix included."""
    return {"text": PREFIX + build_text(exit_code, report, drift_output)}


def _load_report(path: Optional[str], exit_code: int) -> Optional[dict]:
    """Load the report only when the drift branch needs it.

    A missing OR unparseable report on the exit-1 path falls through to the
    could-not-complete wording rather than emitting an empty/garbled drift
    alert (the failure mode this whole script exists to prevent).
    """
    if exit_code != 1 or not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _read_text(path: Optional[str]) -> str:
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exit-code", type=int, required=True,
                    help="The drift checker's exit code (0 clean / 1 drift / 2 failure).")
    ap.add_argument("--report", default=".github/data/code_security_report.json",
                    help="Path to the committed code_security_report.json.")
    ap.add_argument("--drift-output", default="",
                    help="Path to the captured checker stdout/stderr (for error detail).")
    ap.add_argument("--emit", choices=("payload", "text"), default="payload",
                    help="Emit the full JSON payload (default) or the bare text body.")
    args = ap.parse_args(argv)

    report = _load_report(args.report, args.exit_code)
    drift_output = _read_text(args.drift_output)

    if args.emit == "text":
        sys.stdout.write(build_text(args.exit_code, report, drift_output))
    else:
        json.dump(build_payload(args.exit_code, report, drift_output),
                  sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
