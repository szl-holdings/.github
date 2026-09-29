#!/usr/bin/env python3
"""Lint a Hugging Face card (README.md) against the SZL card contract.

Checks, all fail closed:

1. The card has YAML front matter that parses to a mapping.
2. The front matter satisfies hf-card/schema.json for the card type
   (model, dataset, space or kernel).
3. Decision D10: a card may print the MEASURED label, or a benchmark-style
   number, only next to a link to a committed receipt or test in its source
   repository. "Next to" means the same claim unit: one table row, one list
   item, one paragraph or one heading. A receipt link is a commit-pinned
   GitHub URL, https://github.com/szl-holdings/<repo>/blob/<40-hex sha>/<path>
   (tree/ and raw.githubusercontent.com forms are accepted). When the front
   matter names szl.source_repo, the link must point into that repository.
4. model-index results must carry source.url set to such a receipt link.

A label legend such as "MEASURED / REPORTED / UNKNOWN / UNAVAILABLE" lists the
vocabulary and is not a claim. Fenced code blocks and HTML comments are
ignored. Nothing here contacts the network.

Exit codes: 0 clean, 1 findings, 2 usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CARD_TYPES = ("model", "dataset", "space", "kernel")
TYPE_MARKER = re.compile(r"<!--\s*hf-card:\s*type=(model|dataset|space|kernel)\b")

# A legend enumerates the vocabulary ("MEASURED / REPORTED / MODELED / UNKNOWN"):
# three or more upper-case labels joined by "/", ",", "·", "or" or "and"
# (optionally in `code` or **bold**). It states what the labels are, not that
# any one of them applies, so it is not a claim.
_CAPS = r"[`*]*\b[A-Z][A-Z_]{2,}\b[`*]*"
_JOIN = r"\s*(?:[/,·]\s*(?:(?:or|and)\s+)?|(?:or|and)\s+)"
LEGEND = re.compile(rf"{_CAPS}(?:{_JOIN}{_CAPS}){{2,}}")
MEASURED = re.compile(r"\bMEASURED\b")

_NUM = r"(?<![\w.])\d+(?:[.,]\d+)?"
BENCH_UNIT = re.compile(
    _NUM
    + r"\s?(?:%|‰|ms|µs|us|ns|tok/s|tokens/s|tokens/sec|it/s|samples/s|req/s|qps|"
    r"GB/s|MB/s|TFLOPS|GFLOPS|TOPS)(?![\w/])"
)
BENCH_SPEEDUP = re.compile(_NUM + r"\s?[x×](?![\w])(?!\s*\d)")  # "2.3x", not "3290 x 128"
NEGATED = re.compile(r"(?i)\b(?:never|not|no|without)\s+(?:\S+\s+)?$")
# A metric name followed closely by a value: "accuracy: 0.93", "F1 = 91.2",
# "| MMLU | 71.3 |", "pass@1 of 67". Prose such as "16-bit precision" is not
# matched because the value must follow the metric name.
BENCH_METRIC = re.compile(
    r"(?i)\b(?:accuracy|f1(?:-score)?|precision|recall|auroc|auc|bleu|rouge(?:-[l12])?|"
    r"exact[ _-]match|pass@\d+|perplexity|latency|throughput|speed-?up|p50|p90|p95|p99|"
    r"mmlu|gsm8k|humaneval|hellaswag|truthfulqa|win[ -]rate|wer|cer|ndcg|mrr)\b"
    r"\**[\s:=(|\-–]{0,6}(?:(?:of|is|at|was|=)\s+)?\**" + _NUM
)

RECEIPT = re.compile(
    r"^https://(?:github\.com/szl-holdings/(?P<repo>[A-Za-z0-9._-]+)/(?:blob|tree)/"
    r"(?P<sha>[0-9a-f]{40})/(?P<path>[^\s?#]+)"
    r"|raw\.githubusercontent\.com/szl-holdings/(?P<rrepo>[A-Za-z0-9._-]+)/"
    r"(?P<rsha>[0-9a-f]{40})/(?P<rpath>[^\s?#]+))(?:\?[^\s#]*)?(?:#[^\s]*)?$"
)
INLINE_LINK = re.compile(r"\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
BARE_URL = re.compile(r"(?<![(<\w])https?://[^\s)<>\]|]+")
REF_USE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]|\[([^\]]+)\](?![\[(:])")
REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s+.*)?$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
HTML_TAG = re.compile(r"<[A-Za-z/][^>]*>")
HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.I)


class CardError(Exception):
    """The card cannot be evaluated (usage or parse error, exit 2)."""


class SchemaError(Exception):
    """schema.json uses a keyword this validator does not implement."""


@dataclass
class Finding:
    rule: str
    message: str
    line: int | None = None

    def render(self, path: str) -> str:
        where = f"{path}:{self.line}" if self.line else path
        return f"{where}: {self.rule}: {self.message}"


@dataclass
class Report:
    path: str
    card_type: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "type": self.card_type,
            "ok": self.ok,
            "findings": [f.__dict__ for f in self.findings],
        }


# --------------------------------------------------------------------------
# Front matter


def split_front_matter(text: str) -> tuple[dict[str, Any], str, int]:
    """Return (metadata, body, body_start_line). Raises CardError."""
    text = text.lstrip("﻿")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise CardError("card has no YAML front matter (first line must be ---)")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = "".join(lines[1:index])
            try:
                data = yaml.safe_load(raw) if raw.strip() else None
            except yaml.YAMLError as exc:
                raise CardError(f"front matter is not valid YAML: {exc}") from None
            if not isinstance(data, dict):
                raise CardError("front matter must be a YAML mapping")
            return data, "".join(lines[index + 1 :]), index + 2
    raise CardError("front matter is not closed by a second --- line")


# --------------------------------------------------------------------------
# JSON Schema subset validator (fails closed on unknown keywords)

_ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "$defs", "default", "examples"}
_KEYWORDS = _ANNOTATIONS | {
    "type", "required", "properties", "additionalProperties", "items", "minItems", "maxItems",
    "uniqueItems", "enum", "const", "pattern", "minLength", "maxLength", "minimum", "maximum",
    "allOf", "anyOf", "not", "if", "then", "$ref",
}


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    _audit_schema(schema, "#")
    return schema


def _audit_schema(node: Any, where: str) -> None:
    if isinstance(node, dict):
        unknown = set(node) - _KEYWORDS
        # Keys under properties/$defs are names, not keywords.
        if unknown and not where.endswith(("/properties", "/$defs")):
            raise SchemaError(f"{where}: unsupported schema keyword(s) {sorted(unknown)}")
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    _audit_schema(sub, f"{where}/{key}/{name}")
            elif key in ("items", "not", "if", "then", "additionalProperties") and isinstance(value, dict):
                _audit_schema(value, f"{where}/{key}")
            elif key in ("allOf", "anyOf"):
                for i, sub in enumerate(value):
                    _audit_schema(sub, f"{where}/{key}/{i}")


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "") -> list[str]:
    """Return a list of human-readable violations (empty when valid)."""
    errors: list[str] = []
    here = path or "(front matter)"
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise SchemaError(f"unsupported $ref {ref!r}")
        errors += validate(value, root["$defs"][ref.split("/")[-1]], root, path)
    if "type" in schema:
        wanted = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](value) for t in wanted):
            return errors + [f"{here}: expected {'/'.join(wanted)}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{here}: must be {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{here}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{here}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{here}: longer than {schema['maxLength']} characters ({len(value)})")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{here}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{here}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{here}: above maximum {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{here}: needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{here}: allows at most {schema['maxItems']} item(s)")
        if schema.get("uniqueItems"):
            seen = [json.dumps(item, sort_keys=True, default=str) for item in value]
            if len(seen) != len(set(seen)):
                errors.append(f"{here}: items must be unique")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{here}: missing required key {key!r}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, root, f"{path}.{key}" if path else key)
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(props)):
                errors.append(f"{here}: unexpected key {key!r}")
    for sub in schema.get("allOf", []):
        errors += validate(value, sub, root, path)
    if "anyOf" in schema and not any(not validate(value, sub, root, path) for sub in schema["anyOf"]):
        errors.append(f"{here}: matches none of the allowed forms")
    if "not" in schema and not validate(value, schema["not"], root, path):
        errors.append(f"{here}: matches a forbidden form")
    if "if" in schema and not validate(value, schema["if"], root, path):
        errors += validate(value, schema.get("then", {}), root, path)
    return errors


def validate_front_matter(meta: dict[str, Any], card_type: str, schema: dict[str, Any] | None = None) -> list[str]:
    if card_type not in CARD_TYPES:
        raise CardError(f"unknown card type {card_type!r}; expected one of {CARD_TYPES}")
    schema = schema or load_schema()
    return validate(meta, schema["$defs"][card_type], schema)


# --------------------------------------------------------------------------
# Claim units and receipt links


@dataclass
class Unit:
    line: int
    text: str


def iter_units(body: str, first_line: int = 1) -> Iterator[Unit]:
    """Split a markdown body into claim units, skipping code fences."""
    body = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), body)
    fence: str | None = None
    current: list[str] = []
    start = first_line

    def flush() -> Iterator[Unit]:
        nonlocal current
        if current and any(part.strip() for part in current):
            yield Unit(start, "\n".join(current))
        current = []

    for offset, raw in enumerate(body.splitlines()):
        number = first_line + offset
        line = re.sub(r"^\s{0,3}(?:>\s?)+", "", raw)
        opener = FENCE.match(line)
        if fence is not None:
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence):
                fence = None
            continue
        if opener:
            yield from flush()
            fence = opener.group(1)
            continue
        if not line.strip():
            yield from flush()
            continue
        stripped = line.lstrip()
        if stripped.startswith("|") or HEADING.match(line) or LIST_ITEM.match(line):
            yield from flush()
            start = number
            current = [line]
            if stripped.startswith("|") or HEADING.match(line):
                yield from flush()
            continue
        if not current:
            start = number
        current.append(line)
    yield from flush()


def reference_definitions(body: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    fence: str | None = None
    for raw in body.splitlines():
        opener = FENCE.match(raw)
        if fence is not None:
            if opener and opener.group(1)[0] == fence[0]:
                fence = None
            continue
        if opener:
            fence = opener.group(1)
            continue
        match = REF_DEF.match(raw)
        if match:
            refs[match.group(1).strip().lower()] = match.group(2)
    return refs


def unit_urls(text: str, refs: dict[str, str]) -> list[str]:
    urls = [m.group(1) for m in INLINE_LINK.finditer(text)]
    urls += [m.group(1) for m in AUTOLINK.finditer(text)]
    urls += [m.group(1) for m in HREF.finditer(text)]
    scrubbed = HTML_TAG.sub(" ", AUTOLINK.sub(" ", INLINE_LINK.sub(" ", text)))
    urls += [m.group(0).rstrip(".,;:'\"") for m in BARE_URL.finditer(scrubbed)]
    for m in REF_USE.finditer(text):
        label = (m.group(2) or m.group(1) or m.group(3) or "").strip().lower()
        if label in refs:
            urls.append(refs[label])
    return urls


def receipt_repo(url: str) -> str | None:
    """Return the repository name for a commit-pinned receipt URL, else None."""
    match = RECEIPT.match(url)
    if not match:
        return None
    return (match.group("repo") or match.group("rrepo")).lower()


def _receipt_problem(urls: Iterable[str], source_repo: str | None) -> str | None:
    """None when the unit carries a valid receipt link, else why not."""
    urls = list(urls)
    pinned = [(u, receipt_repo(u)) for u in urls]
    good = [u for u, repo in pinned if repo and (source_repo is None or repo == source_repo)]
    if good:
        return None
    wrong_repo = [u for u, repo in pinned if repo and source_repo is not None and repo != source_repo]
    if wrong_repo:
        return f"receipt link points outside the source repo szl-holdings/{source_repo}: {wrong_repo[0]}"
    unpinned = [u for u in urls if "github.com/szl-holdings/" in u]
    if unpinned:
        return f"receipt link is not pinned to a 40-hex commit: {unpinned[0]}"
    return "no commit-pinned receipt link in the same row, list item or paragraph"


def _claims_in(text: str) -> list[str]:
    reasons: list[str] = []
    # HTML tags are layout (width="100%"), not prose; their hrefs still count
    # as links (see unit_urls). "never 100%" negates rather than claims.
    text = HTML_TAG.sub(" ", text)
    if _is_measured_claim(text):
        reasons.append("MEASURED label")
    for pattern in (BENCH_UNIT, BENCH_SPEEDUP, BENCH_METRIC):
        hit = next((m for m in pattern.finditer(text) if not NEGATED.search(text[: m.start()])), None)
        if hit:
            reasons.append(f"benchmark number {hit.group(0).strip()!r}")
            break
    return reasons


def source_repo_name(meta: dict[str, Any]) -> str | None:
    szl = meta.get("szl")
    if isinstance(szl, dict) and isinstance(szl.get("source_repo"), str):
        return szl["source_repo"].split("/", 1)[-1].lower()
    return None


def lint_claims(meta: dict[str, Any], body: str, first_line: int = 1) -> list[Finding]:
    findings: list[Finding] = []
    source_repo = source_repo_name(meta)
    refs = reference_definitions(body)
    for unit in iter_units(body, first_line):
        if REF_DEF.match(unit.text) and "\n" not in unit.text:
            continue
        reasons = _claims_in(unit.text)
        if not reasons:
            continue
        problem = _receipt_problem(unit_urls(unit.text, refs), source_repo)
        if problem:
            snippet = " ".join(unit.text.split())[:100]
            findings.append(Finding("D10", f"{' and '.join(reasons)} without a receipt: {problem}. Text: {snippet!r}", unit.line))
    findings += _lint_front_matter_claims(meta, source_repo)
    return findings


def _walk_strings(
    value: Any, path: str, siblings: tuple[str, ...] = ()
) -> Iterator[tuple[str, str, tuple[str, ...]]]:
    """Yield (path, string, sibling strings). One mapping is one claim unit, so a
    MEASURED value is satisfied by a receipt URL in any string of the same mapping."""
    if isinstance(value, str):
        yield path, value, siblings
    elif isinstance(value, dict):
        strings = tuple(v for v in value.values() if isinstance(v, str))
        for key, sub in value.items():
            yield from _walk_strings(sub, f"{path}.{key}" if path else str(key), strings)
    elif isinstance(value, list):
        strings = tuple(v for v in value if isinstance(v, str))
        for i, sub in enumerate(value):
            yield from _walk_strings(sub, f"{path}[{i}]", strings)


def _is_measured_claim(text: str) -> bool:
    legend = [m.span() for m in LEGEND.finditer(text)]
    return any(not any(a <= m.start() < b for a, b in legend) for m in MEASURED.finditer(text))


def _lint_front_matter_claims(meta: dict[str, Any], source_repo: str | None) -> list[Finding]:
    findings: list[Finding] = []
    for path, text, siblings in _walk_strings({k: v for k, v in meta.items() if k != "model-index"}, ""):
        if _is_measured_claim(text):
            urls = [u for s in (text, *siblings) for u in BARE_URL.findall(s)]
            problem = _receipt_problem(urls, source_repo)
            if problem:
                findings.append(Finding("D10", f"front matter {path} carries a MEASURED label without a receipt: {problem}"))
    for i, entry in enumerate(meta.get("model-index") or []):
        results = entry.get("results") if isinstance(entry, dict) else None
        for j, result in enumerate(results or []):
            source = result.get("source") if isinstance(result, dict) else None
            url = source.get("url") if isinstance(source, dict) else None
            problem = _receipt_problem([url] if isinstance(url, str) else [], source_repo)
            if problem:
                findings.append(Finding("D10", f"model-index[{i}].results[{j}] has metrics without a receipt source.url: {problem}"))
    return findings


# --------------------------------------------------------------------------
# Entry points


def detect_type(text: str) -> str | None:
    match = TYPE_MARKER.search(text)
    return match.group(1) if match else None


def lint_text(text: str, card_type: str | None, path: str = "README.md", schema: dict[str, Any] | None = None) -> Report:
    card_type = card_type or detect_type(text)
    if card_type is None:
        raise CardError("card type unknown: pass --type or render the card with render.py")
    meta, body, first_line = split_front_matter(text)
    report = Report(path, card_type)
    for error in validate_front_matter(meta, card_type, schema):
        report.findings.append(Finding("schema", error))
    report.findings += lint_claims(meta, body, first_line)
    return report


def lint_file(path: Path, card_type: str | None = None) -> Report:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CardError(f"cannot read {path}: {exc}") from None
    return lint_text(text, card_type, str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cards", nargs="+", type=Path, help="README.md files to lint")
    parser.add_argument("--type", choices=CARD_TYPES, help="card type (default: the hf-card marker in the card)")
    parser.add_argument("--json", type=Path, help="write a JSON report here")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    reports: list[Report] = []
    try:
        for card in args.cards:
            reports.append(lint_file(card, args.type))
    except (CardError, SchemaError) as exc:
        print(f"hf-card lint: {exc}", file=sys.stderr)
        return 2
    for report in reports:
        for finding in report.findings:
            print(finding.render(report.path))
        print(f"{report.path}: {'OK' if report.ok else f'{len(report.findings)} finding(s)'} ({report.card_type})")
    if args.json:
        args.json.write_text(json.dumps([r.as_dict() for r in reports], indent=2) + "\n", encoding="utf-8")
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
