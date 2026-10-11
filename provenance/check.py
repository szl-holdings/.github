#!/usr/bin/env python3
"""Advisory szl/provenance gate. Records identifiers and SHAs, never secrets."""
from __future__ import annotations

import html
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


MAX_BODY_CHARS = 262144
_RAW_TAGS = {"pre", "code", "script", "style", "textarea"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_BLOCK_TAGS = set("address article aside base basefont blockquote body caption center col colgroup dd details dialog dir div dl dt fieldset figcaption figure footer form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu menuitem nav noframes ol optgroup option p param search section summary table tbody td tfoot th thead title tr track ul".split())
_TAG_START = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)(?=[\t />]|$)")
_ATX = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")


def _code_pairs(line: str) -> dict[int, tuple[int, int]]:
    """Next equal-length backtick run, computed once rather than rescanning."""
    following: dict[int, re.Match] = {}
    pairs = {}
    for run in reversed(list(re.finditer(r"`+", line))):
        width = len(run[0])
        close = following.get(width)
        if close is not None:
            pairs[run.start()] = (close.end(), width)
        following[width] = run
    return pairs


class _MarkdownLines:
    """Bounded evidence subset, not a general Markdown renderer or sanitizer.

    Supports top-level ATX headings, fenced code, and balanced single-line code
    spans. Literal code is never fed to HTML processing. Comments, declarations,
    CDATA, raw-text tags and HTML containers are excluded; containers remain
    opaque through their matching close, including blank lines (conservative
    compared with Markdown renderers). Unclosed HTML stays opaque to EOF. Other
    inline HTML tags contribute no attribute/markup text; visible prose survives.
    Multiline code spans, Setext/list-nested headings and renderer-specific HTML
    extensions are not evidence-section syntax. Entire input is bounded above.
    """

    def __init__(self) -> None:
        self.fence = ""
        self.comment = False
        self.declaration_end = ""
        self.opaque: list[str] = []
        self.pending: tuple[str, bool, bool] | None = None
        self.quote = ""

    def _tag(self, name: str, closing: bool, block_start: bool, tail: str, self_closing: bool) -> None:
        if closing:
            if self.opaque and self.opaque[-1] == name:
                self.opaque.pop()
            return
        if name in _VOID_TAGS:
            return
        if self.opaque:
            if name in _RAW_TAGS | _BLOCK_TAGS or name == self.opaque[-1]:
                self.opaque.append(name)
        elif name in _RAW_TAGS | _BLOCK_TAGS or (block_start and not tail.strip() and not self_closing):
            self.opaque.append(name)

    def _angle_end(self, line: str, start: int) -> int | None:
        for index in range(start, len(line)):
            char = line[index]
            if self.quote:
                if char == self.quote:
                    self.quote = ""
            elif char in "\"'":
                self.quote = char
            elif char == ">":
                return index + 1
        return None

    def _prose(self, line: str) -> str:
        output = []
        pairs = _code_pairs(line)
        index = 0
        while index < len(line):
            if self.comment:
                end = line.find("-->", index)
                if end < 0:
                    break
                self.comment = False
                index = end + 3
                continue
            if self.declaration_end:
                end = line.find(self.declaration_end, index)
                if end < 0:
                    break
                index = end + len(self.declaration_end)
                self.declaration_end = ""
                continue
            if self.pending is not None:
                end = self._angle_end(line, index)
                if end is None:
                    break
                name, closing, block_start = self.pending
                self.pending = None
                if name:
                    self._tag(name, closing, block_start, line[end:], line[index:end].rstrip().endswith("/>"))
                index = end
                continue
            if self.opaque and self.opaque[-1] in _RAW_TAGS:
                tag_name = self.opaque[-1]
                end = re.compile(r"</" + tag_name + r"[ \t]*>", re.IGNORECASE).search(line, index)
                if end is None:
                    if re.compile(r"</" + tag_name + r"[ \t]*$", re.IGNORECASE).search(line, index):
                        self.pending = (tag_name, True, False)
                    break
                self.opaque.pop()
                index = end.end()
                continue
            if line.startswith("<!--", index):
                self.comment = True
                index += 4
                continue
            if line.startswith("<![CDATA[", index) or line.startswith("<?", index):
                self.declaration_end = "]]>" if line.startswith("<![CDATA[", index) else "?>"
                index += 9 if self.declaration_end == "]]>" else 2
                continue
            if re.match(r"<![A-Za-z]", line[index:index + 3]):
                self.pending = ("", False, False)
                index += 2
                continue
            tag = _TAG_START.match(line, index)
            if tag:
                self.pending = (tag[2].lower(), bool(tag[1]), index <= 3 and not line[:index].strip())
                index = tag.end()
                continue
            if not self.opaque:
                if line[index] == "\\" and index + 1 < len(line):
                    output.append(line[index:index + 2])
                    index += 2
                    continue
                if index in pairs:
                    end, _ = pairs[index]
                    output.append(line[index:end])
                    index = end
                    continue
                output.append(line[index])
            index += 1
        return "".join(output)

    def lines(self, body: str):
        for source in body.splitlines():
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})", source)
            if self.fence:
                if (marker and marker[1][0] == self.fence[0]
                        and len(marker[1]) >= len(self.fence) and not source[marker.end():].strip()):
                    self.fence = ""
                    yield "fence", source
                else:
                    yield "literal", source
                continue
            in_html = bool(self.comment or self.declaration_end or self.pending is not None or self.opaque)
            if not in_html and marker and not (marker[1][0] == "`" and "`" in source[marker.end():]):
                self.fence = marker[1]
                yield "fence", source
                continue
            heading = not in_html and _ATX.match(source) is not None
            yield "heading" if heading else "prose", self._prose(source)


def _display_text(line: str) -> str:
    """Decode entities only in prose, after tags/comments were removed."""
    output = []
    pairs = _code_pairs(line)
    index = start = 0
    while index < len(line):
        if line[index] == "\\" and index + 1 < len(line):
            index += 2
            continue
        if index in pairs:
            end, width = pairs[index]
            output.append(html.unescape(line[start:index]))
            output.append(line[index + width:end - width])
            index = start = end
        else:
            index += 1
    output.append(html.unescape(line[start:]))
    return "".join(output)


def evidence_sections(body: str) -> dict[str, list[str]]:
    """Extract visible sections without treating code examples as headings."""
    sections: dict[str, list[str]] = {}
    if not isinstance(body, str) or len(body) > MAX_BODY_CHARS:
        return sections
    current: list[str] | None = None
    for kind, line in _MarkdownLines().lines(body):
        heading = _ATX.match(line) if kind == "heading" else None
        if heading:
            if len(heading[1]) <= 2:
                # Avoid ambiguous whitespace regexes on an untrusted PR body.
                name = heading[2].rstrip(" \t")
                if name.endswith("#"):
                    before_hashes = name.rstrip("#")
                    if before_hashes and before_hashes[-1] in " \t":
                        name = before_hashes.rstrip(" \t")
                name = name.strip()
                current = sections.setdefault(name, []) if len(heading[1]) == 2 else None
                if current is not None:
                    current.append("")
            continue
        if current is not None:
            current[-1] += line + "\n"
    return sections


def substantive_section(contents: list[str]) -> bool:
    """Require non-placeholder content, not proof that an attestation is true."""
    if len(contents) != 1 or not isinstance(contents[0], str) or len(contents[0]) > MAX_BODY_CHARS:
        return False
    for kind, line in _MarkdownLines().lines(contents[0]):
        if kind in {"fence", "heading"}:
            continue
        line = line if kind == "literal" else _display_text(line)
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
