#!/usr/bin/env python3
"""Advisory szl/provenance gate. Records identifiers and SHAs, never secrets."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "szl.solo-maintainer-provenance/v1"
HEADINGS = [
    "Origin",
    "Rights",
    "Agents and tools",
    "Tests",
    "Security",
    "Rollback",
    "Known limits",
]


def load_policy(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise SystemExit("policy schema mismatch")
    if data.get("credential_value_recorded") is not False:
        raise SystemExit("policy must forbid credential recording")
    return data


def _strip_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Remove HTML comments from one non-fenced line, retaining visible text."""
    visible = ""
    rest = line
    while rest:
        if in_comment:
            end = rest.find("-->")
            if end < 0:
                return visible, True
            rest = rest[end + 3 :]
            in_comment = False
            continue
        start = rest.find("<!--")
        if start < 0:
            visible += rest
            break
        visible += rest[:start]
        rest = rest[start + 4 :]
        in_comment = True
    return visible, in_comment


def _strip_raw_html_code(line: str, raw_code: str) -> tuple[str, str]:
    """Remove raw HTML pre/code regions whose Markdown is rendered literally."""
    visible = ""
    rest = line
    while rest:
        if raw_code:
            closing = re.search(rf"</{raw_code}\s*>", rest, flags=re.IGNORECASE)
            if not closing:
                return visible, raw_code
            rest = rest[closing.end() :]
            raw_code = ""
            continue
        opening = re.search(r"<(pre|code)\b[^>]*>", rest, flags=re.IGNORECASE)
        if not opening:
            visible += rest
            break
        visible += rest[: opening.start()]
        raw_code = opening[1].lower()
        rest = rest[opening.end() :]
    return visible, raw_code


def evidence_sections(body: str) -> dict[str, list[str]]:
    """Extract visible sections without treating code examples as headings."""
    sections: dict[str, list[str]] = {}
    if not isinstance(body, str):
        return sections
    current: list[str] | None = None
    fence = ""
    html_comment = False
    raw_code = ""
    for source_line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", source_line)
        if fence:
            if (
                marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                and not source_line[marker.end():].strip()
            ):
                fence = ""
            elif current is not None:
                current[-1] += source_line + "\n"
            continue

        line, html_comment = _strip_html_comments(source_line, html_comment)
        line, raw_code = _strip_raw_html_code(line, raw_code)
        if raw_code and not line:
            continue
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            fence = marker[1]
            continue
        heading = re.match(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$", line)
        if heading:
            if len(heading[1]) <= 2:
                name = heading[2]
                current = sections.setdefault(name, []) if len(heading[1]) == 2 else None
                if current is not None:
                    current.append("")
            continue
        if current is not None:
            current[-1] += line + "\n"
    return sections


def substantive_section(contents: list[str]) -> bool:
    """Require non-placeholder content, not proof that an attestation is true."""
    if len(contents) != 1:
        return False
    for line in contents[0].splitlines():
        line = re.sub(r"^\s*(?:[-+*]\s*)?\[[ xX]\]\s*", "", line)
        text = re.sub(r"^[\s>*_`~\-+\[\]]+|[\s*_`~]+$", "", line).strip()
        if not re.search(r"[A-Za-z0-9]", text):
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9 _./-]{0,80}:", text):
            continue
        if not re.fullmatch(
            r"(?:todo|tbd|pending|none|n/?a|not applicable|not run|unknown|unavailable|blocked)[.!]*",
            text,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def evaluate(policy: dict, event: dict) -> dict:
    pr = event.get("pull_request") or {}
    repo = event.get("repository") or {}
    sender = event.get("sender") or {}
    body = pr.get("body") or ""
    head = (pr.get("head") or {}).get("sha")
    base_ref = (pr.get("base") or {}).get("ref")
    default_branch = repo.get("default_branch") or "main"
    owner = ((pr.get("head") or {}).get("repo") or {}).get("full_name", "")
    actor = sender.get("login") or ""
    sections = evidence_sections(body)
    headings = {name: name in sections for name in HEADINGS}
    evidence = {name: substantive_section(sections.get(name, [])) for name in HEADINGS}
    internal = owner.startswith(f"{policy['organization']}/")
    allowed_humans = set(policy.get("allowed_human_actors") or [])
    allowed_bots = {f"{slug}[bot]" for slug in policy.get("allowed_app_slugs") or []}
    actor_ok = isinstance(actor, str) and (
        actor in allowed_humans
        or (sender.get("type") == "Bot" and actor in allowed_bots)
    )
    checks = {
        "exact_head_sha": isinstance(head, str) and re.fullmatch(r"[0-9a-f]{40}", head) is not None,
        "internal_head_repository": internal,
        "allowed_actor": actor_ok,
        "protected_base": base_ref == default_branch,
        "pr_body_headings": all(headings.values()),
        "pr_body_evidence": all(evidence.values()),
        "not_direct_default_branch_push": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "schema": "szl.provenance-check/v1",
        "enforcement": policy.get("enforcement", "advisory"),
        "required_check": policy.get("required_check"),
        "head_sha": head,
        "base_ref": base_ref,
        "head_repository": owner,
        "actor": actor,
        "headings": headings,
        "evidence_sections": evidence,
        "checks": checks,
        "failed": failed,
        "pass": not failed,
        "credential_value_recorded": False,
        "known_limits": [
            "advisory until added as a required check",
            "does not verify GitHub merge provenance after merge",
            "head syntax is checked; current provider head and branch protection are not reauthorized",
            "App bot logins must match declared policy; App identity is not resolved from the Apps API",
            "non-placeholder evidence text is required; its truth is not independently verified",
        ],
    }


def main(argv: list[str]) -> int:
    policy_path = Path(argv[1] if len(argv) > 1 else "provenance/solo-maintainer-policy.v1.json")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH") or (argv[2] if len(argv) > 2 else ""))
    policy = load_policy(policy_path)
    if not event_path or not event_path.exists():
        print(json.dumps({"schema": "szl.provenance-check/v1", "pass": False, "failed": ["missing_event"]}, indent=2))
        return 1
    event = json.loads(event_path.read_text(encoding="utf-8"))
    report = evaluate(policy, event)
    print(json.dumps(report, indent=2))
    if report["enforcement"] == "advisory":
        return 0 if report["pass"] else 2
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
