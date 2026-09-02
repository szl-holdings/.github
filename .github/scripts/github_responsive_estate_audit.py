#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory every SZL Holdings GitHub repository and audit UI screen coverage.

The audit is source-bound and fail-closed about inventory completeness. It does
not pretend that libraries, APIs, research repositories, or archived projects
need a browser layout. Repositories are classified first; only UI-bearing
repositories are evaluated against the phone-to-ultrawide source contract.

The script deliberately emits *source evidence*, not a claim that every live
runtime is healthy. Runtime/browser verification remains the responsibility of
``SZL Public Experience v3`` and repository-native deployment checks.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from ci_health_digest_http import (
    ApiError,
    DigestError,
    ReaderSelectionError,
    request_json,
    select_reader,
)

ORG = "szl-holdings"
SCHEMA = "szl.github-responsive-estate/v1"
MAX_WORKERS = 8
MAX_FILES_PER_REPOSITORY = 16
MAX_BYTES_PER_REPOSITORY = 4_000_000
MAX_BLOB_BYTES = 2_500_000

CONTROL_PLANE_NAMES = {
    ".github",
    "szl-doctrine",
    "szl-org-health",
    "szl-estate-os",
    "evidence-doctrine",
}
PRIORITY_PUBLIC_REPOSITORIES = {
    "a11oy",
    "a11oy-net",
    "anatomy",
    "killinchu",
    "szl-holdings.github.io",
}
SKIP_PATH_PARTS = {
    ".git",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "archive",
    "archives",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "third_party",
    "vendor",
    "vendors",
}
TEXT_SUFFIXES = {
    ".css",
    ".htm",
    ".html",
    ".js",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".scss",
    ".ts",
    ".tsx",
    ".vue",
}
UI_PATH_PATTERNS = (
    re.compile(r"(^|/)(index|landing|home|page|layout|app|main)\.(html?|jsx?|tsx?|vue)$", re.I),
    re.compile(r"(^|/)(style|styles|global|globals|app|main|index)\.(css|scss)$", re.I),
    re.compile(r"(^|/)(vite|next|nuxt|astro|svelte)\.config\.", re.I),
    re.compile(r"(^|/)(public|static|pages|web|frontend|client|ui)(/|$)", re.I),
)
AUTOMATION_TERMS = (
    "playwright",
    "lighthouse",
    "accessibility",
    "responsive",
    "public-experience",
    "axe",
    "a11y",
    "e2e",
    "visual-regression",
)


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int
    type: str


@dataclass(frozen=True)
class SourceSignals:
    viewport: bool
    responsive_layout: bool
    overflow_containment: bool
    reduced_motion: bool
    contrast_modes: bool
    touch_targets: bool
    safe_area: bool
    dynamic_viewport: bool
    zoom_reflow: bool
    local_wide_scroll: bool
    public_experience_v3: bool
    automated_browser_audit: bool


@dataclass(frozen=True)
class RepositoryResult:
    repository: str
    visibility: str
    archived: bool
    default_branch: str | None
    classification: str
    interface_scope: str
    homepage: str | None
    has_pages: bool
    tree_complete: bool
    tree_entries: int
    sampled_files: tuple[str, ...]
    skipped_large_files: tuple[str, ...]
    sampled_bytes: int
    signals: SourceSignals
    status: str
    priority: str
    blocking: bool
    missing: tuple[str, ...]
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


class AuditError(RuntimeError):
    """Raised when repository source evidence cannot be evaluated safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_path(path: str) -> str:
    return path.strip().strip("/")


def _is_excluded(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    return bool(parts & SKIP_PATH_PARTS)


def _is_text_candidate(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_SUFFIXES and not _is_excluded(path)


def _is_ui_path(path: str) -> bool:
    normalized = path.lower()
    if normalized in {"index.html", "cname"}:
        return True
    return any(pattern.search(path) for pattern in UI_PATH_PATTERNS)


def _is_automation_path(path: str) -> bool:
    lower = path.lower()
    return any(term in lower for term in AUTOMATION_TERMS)


def _priority(path: str) -> tuple[int, int, str]:
    lower = path.lower()
    exact = {
        "index.html": 0,
        "public/index.html": 1,
        "static/index.html": 2,
        "src/app.tsx": 3,
        "src/app.jsx": 3,
        "src/main.tsx": 4,
        "src/main.jsx": 4,
        "src/index.css": 5,
        "src/app.css": 5,
        "style.css": 5,
        "styles.css": 5,
        "app.py": 6,
        "serve.py": 6,
        "server.py": 6,
    }
    if lower in exact:
        return exact[lower], len(Path(path).parts), path
    suffix = Path(path).suffix.lower()
    if suffix in {".html", ".htm"}:
        rank = 10
    elif suffix in {".css", ".scss"}:
        rank = 20
    elif suffix in {".tsx", ".jsx", ".vue"}:
        rank = 30
    elif suffix in {".js", ".mjs", ".ts"}:
        rank = 40
    elif suffix == ".py":
        rank = 50
    else:
        rank = 60
    return rank, len(Path(path).parts), path


def select_source_entries(entries: Sequence[TreeEntry]) -> tuple[TreeEntry, ...]:
    candidates = [
        item
        for item in entries
        if item.type == "blob" and _is_text_candidate(item.path) and _is_ui_path(item.path)
    ]
    candidates.sort(key=lambda item: _priority(item.path))
    selected: list[TreeEntry] = []
    budget = 0
    for item in candidates:
        if len(selected) >= MAX_FILES_PER_REPOSITORY:
            break
        if item.size > MAX_BLOB_BYTES:
            continue
        if budget + item.size > MAX_BYTES_PER_REPOSITORY and selected:
            continue
        selected.append(item)
        budget += item.size
    return tuple(selected)


def _decode_blob(payload: Mapping[str, Any], *, repository: str, path: str) -> str:
    if payload.get("encoding") != "base64":
        raise AuditError(f"{repository}/{path} blob is not base64 encoded")
    raw = str(payload.get("content") or "").replace("\n", "")
    try:
        value = base64.b64decode(raw, validate=True)
        return value.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditError(f"{repository}/{path} is not valid UTF-8 text") from exc


def read_blob(token: str, repository: str, entry: TreeEntry) -> str:
    _, payload = request_json(
        token,
        f"https://api.github.com/repos/{ORG}/{quote(repository)}/git/blobs/{entry.sha}",
        operation=f"read responsive source {repository}/{entry.path}",
    )
    if not isinstance(payload, dict):
        raise AuditError(f"{repository}/{entry.path} blob payload is malformed")
    return _decode_blob(payload, repository=repository, path=entry.path)


def fetch_tree(
    token: str, repository: str, default_branch: str
) -> tuple[tuple[TreeEntry, ...], bool]:
    _, payload = request_json(
        token,
        (
            f"https://api.github.com/repos/{ORG}/{quote(repository)}/git/trees/"
            f"{quote(default_branch, safe='')}?recursive=1"
        ),
        operation=f"read recursive tree for {repository}@{default_branch}",
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
        raise AuditError(f"recursive tree for {repository} is malformed")
    values: list[TreeEntry] = []
    seen: set[str] = set()
    for item in payload["tree"]:
        if not isinstance(item, dict):
            raise AuditError(f"recursive tree for {repository} contains malformed entry")
        path = _clean_path(str(item.get("path") or ""))
        sha = str(item.get("sha") or "")
        kind = str(item.get("type") or "")
        size_raw = item.get("size") or 0
        try:
            size = int(size_raw)
        except (TypeError, ValueError) as exc:
            raise AuditError(f"tree entry {repository}/{path} has invalid size") from exc
        if not path or path in seen:
            raise AuditError(f"tree for {repository} has missing/duplicate path {path!r}")
        seen.add(path)
        if kind == "blob" and len(sha) != 40:
            raise AuditError(f"blob {repository}/{path} lacks immutable SHA")
        values.append(TreeEntry(path=path, sha=sha, size=size, type=kind))
    return tuple(values), not bool(payload.get("truncated"))


def _contains(text: str, *patterns: str) -> bool:
    lower = text.lower()
    return any(pattern.lower() in lower for pattern in patterns)


def detect_signals(paths: Sequence[str], texts: Sequence[str]) -> SourceSignals:
    joined = "\n".join(texts)
    lower = joined.lower()
    path_lower = "\n".join(paths).lower()
    viewport = bool(
        re.search(r"<meta\s+[^>]*name=[\"']viewport[\"']", lower)
        or re.search(r"export\s+const\s+viewport\b", lower)
        or "viewport-fit=cover" in lower
    )
    responsive_layout = _contains(
        joined,
        "@media",
        "clamp(",
        "minmax(",
        "container-type:",
        "grid-template-columns",
        "flex-wrap:",
        "szl public experience v3",
    )
    overflow_containment = bool(
        re.search(r"overflow-x\s*:\s*(auto|clip|hidden|scroll)", lower)
        or "max-width: 100%" in lower
        or "max-width:100%" in lower
        or "min-width: 0" in lower
        or "min-width:0" in lower
    )
    reduced_motion = "prefers-reduced-motion" in lower
    contrast_modes = "forced-colors" in lower or "prefers-contrast" in lower
    touch_targets = bool(
        re.search(r"min-(height|width)\s*:\s*(44|45|46|47|48)px", lower)
        or "--touch-target" in lower
        or "--tap-target" in lower
        or "44px" in lower and _contains(joined, "button", "[role=\"button\"]", "a[href]")
    )
    safe_area = "safe-area-inset" in lower
    dynamic_viewport = bool(re.search(r"\b\d*(dvh|svh|lvh)\b", lower))
    zoom_reflow = _contains(
        joined,
        "overflow-wrap:",
        "word-break:",
        "min-width: 0",
        "min-width:0",
        "flex-wrap:",
        "max-width: 100%",
        "max-width:100%",
    )
    local_wide_scroll = bool(
        re.search(r"(table|pre|code|\.table|\.code)[^{]{0,80}\{[^}]*overflow-x\s*:\s*auto", lower, re.S)
        or "overflow-x:auto" in lower
        or "overflow-x: auto" in lower
    )
    public_experience_v3 = (
        "szl public experience v3" in lower
        or "__szl_public_experience_v3__" in lower
        or "szl-space-hologram" in path_lower
    )
    automated_browser_audit = any(_is_automation_path(path) for path in paths)
    return SourceSignals(
        viewport=viewport,
        responsive_layout=responsive_layout,
        overflow_containment=overflow_containment,
        reduced_motion=reduced_motion,
        contrast_modes=contrast_modes,
        touch_targets=touch_targets,
        safe_area=safe_area,
        dynamic_viewport=dynamic_viewport,
        zoom_reflow=zoom_reflow,
        local_wide_scroll=local_wide_scroll,
        public_experience_v3=public_experience_v3,
        automated_browser_audit=automated_browser_audit,
    )


def _path_set(entries: Sequence[TreeEntry]) -> set[str]:
    return {item.path.lower() for item in entries}


def _has_any(paths: Iterable[str], expressions: Sequence[re.Pattern[str]]) -> bool:
    return any(any(pattern.search(path) for pattern in expressions) for path in paths)


def classify_repository(
    metadata: Mapping[str, Any], entries: Sequence[TreeEntry], sampled_text: str
) -> tuple[str, str]:
    name = str(metadata.get("name") or "")
    if metadata.get("archived"):
        return "ARCHIVED", "none"
    paths = _path_set(entries)
    lower_text = sampled_text.lower()
    has_ui_paths = _has_any(paths, UI_PATH_PATTERNS) or "index.html" in paths
    python_ui = any(path.endswith(("app.py", "serve.py", "server.py")) for path in paths) and any(
        token in lower_text for token in ("gradio", "streamlit", "htmlresponse", "staticfiles", "jinja2")
    )
    has_pages = bool(metadata.get("has_pages")) or "cname" in paths
    if name in CONTROL_PLANE_NAMES:
        return "CONTROL_PLANE", "none"
    if has_ui_paths or python_ui or has_pages:
        visibility = str(metadata.get("visibility") or ("private" if metadata.get("private") else "public"))
        return ("PRIVATE_WEB" if visibility == "private" else "PUBLIC_WEB"), "web_ui"
    if any(path.endswith((".tex", ".lean")) for path in paths) or any(
        token in name.lower() for token in ("paper", "proof", "research", "ouroboros")
    ):
        return "RESEARCH", "none"
    if any(path.endswith(("openapi.yaml", "openapi.yml", "openapi.json")) for path in paths) or (
        "dockerfile" in paths
        and any(path.endswith(("api.py", "server.py", "main.py")) for path in paths)
    ):
        return "API_SERVICE", "api_only"
    if any(
        path in paths
        for path in (
            "package.json",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "cargo.toml",
            "go.mod",
        )
    ) or any(path.startswith(("src/", "lib/", "packages/")) for path in paths):
        return "LIBRARY", "none"
    if any(path.startswith("docs/") for path in paths) or "readme.md" in paths:
        return "DOCS", "none"
    return "UNKNOWN", "unknown"


def _priority_for(metadata: Mapping[str, Any], classification: str) -> str:
    name = str(metadata.get("name") or "")
    homepage = str(metadata.get("homepage") or "").lower()
    if name in PRIORITY_PUBLIC_REPOSITORIES or any(
        host in homepage for host in ("a-11-oy.com", "a11oy.net")
    ):
        return "P0"
    if classification == "PUBLIC_WEB":
        return "P1"
    if classification == "PRIVATE_WEB":
        return "P2"
    return "N/A"


def evaluate_status(
    *,
    classification: str,
    tree_complete: bool,
    selected: Sequence[TreeEntry],
    signals: SourceSignals,
) -> tuple[str, bool, tuple[str, ...], tuple[str, ...]]:
    if classification not in {"PUBLIC_WEB", "PRIVATE_WEB"}:
        return "NOT_APPLICABLE", False, (), ()
    limitations: list[str] = []
    if not tree_complete:
        limitations.append("recursive Git tree was truncated")
    if not selected:
        limitations.append("no bounded UTF-8 UI source could be sampled")
    required = {
        "viewport": signals.viewport,
        "responsive_layout": signals.responsive_layout,
        "overflow_containment": signals.overflow_containment,
        "reduced_motion": signals.reduced_motion,
    }
    missing = [name for name, present in required.items() if not present]
    if limitations:
        return (
            "EVIDENCE_INCOMPLETE",
            classification == "PUBLIC_WEB",
            tuple(missing),
            tuple(limitations),
        )
    if missing:
        return (
            "ACTION_REQUIRED",
            classification == "PUBLIC_WEB",
            tuple(missing),
            (),
        )
    if not signals.automated_browser_audit:
        return "SOURCE_READY_AUDIT_GAP", False, ("automated_browser_audit",), ()
    return "SOURCE_READY", False, (), ()


def audit_repository(token: str, metadata: Mapping[str, Any]) -> RepositoryResult:
    name = str(metadata.get("name") or "").strip()
    full_name = str(metadata.get("full_name") or f"{ORG}/{name}").strip()
    default_branch = str(metadata.get("default_branch") or "").strip() or None
    if not name or full_name != f"{ORG}/{name}":
        raise AuditError(f"repository identity is malformed: {full_name!r}")
    visibility = str(
        metadata.get("visibility") or ("private" if metadata.get("private") else "public")
    )
    homepage = str(metadata.get("homepage") or "").strip() or None
    if metadata.get("archived"):
        empty = SourceSignals(*([False] * 12))
        return RepositoryResult(
            repository=full_name,
            visibility=visibility,
            archived=True,
            default_branch=default_branch,
            classification="ARCHIVED",
            interface_scope="none",
            homepage=homepage,
            has_pages=bool(metadata.get("has_pages")),
            tree_complete=True,
            tree_entries=0,
            sampled_files=(),
            skipped_large_files=(),
            sampled_bytes=0,
            signals=empty,
            status="NOT_APPLICABLE",
            priority="N/A",
            blocking=False,
            missing=(),
            evidence=("repository metadata: archived=true",),
            limitations=(),
        )
    if not default_branch:
        raise AuditError(f"active repository {full_name} has no default branch")

    entries, tree_complete = fetch_tree(token, name, default_branch)
    selected = select_source_entries(entries)
    skipped_large = tuple(
        item.path
        for item in entries
        if item.type == "blob"
        and _is_text_candidate(item.path)
        and _is_ui_path(item.path)
        and item.size > MAX_BLOB_BYTES
    )
    texts: list[str] = []
    read_paths: list[str] = []
    sampled_bytes = 0
    limitations: list[str] = []
    for entry in selected:
        try:
            texts.append(read_blob(token, name, entry))
            read_paths.append(entry.path)
            sampled_bytes += entry.size
        except (ApiError, AuditError, DigestError) as exc:
            limitations.append(f"{entry.path}: {type(exc).__name__}")

    all_paths = tuple(item.path for item in entries)
    signals = detect_signals((*all_paths, *read_paths), texts)
    classification, scope = classify_repository(metadata, entries, "\n".join(texts))
    status, blocking, missing, status_limitations = evaluate_status(
        classification=classification,
        tree_complete=tree_complete,
        selected=tuple(item for item in selected if item.path in read_paths),
        signals=signals,
    )
    limitations.extend(status_limitations)
    evidence: list[str] = []
    if signals.public_experience_v3:
        evidence.append("SZL Public Experience v3 source marker")
    if signals.automated_browser_audit:
        evidence.append("repository-native responsive/browser automation path")
    if metadata.get("has_pages"):
        evidence.append("GitHub Pages enabled")
    if homepage:
        evidence.append(f"homepage={homepage}")
    if skipped_large:
        limitations.append(f"{len(skipped_large)} UI source file(s) exceeded bounded blob size")
        if status == "SOURCE_READY":
            status = "SOURCE_READY_SAMPLED"

    return RepositoryResult(
        repository=full_name,
        visibility=visibility,
        archived=False,
        default_branch=default_branch,
        classification=classification,
        interface_scope=scope,
        homepage=homepage,
        has_pages=bool(metadata.get("has_pages")),
        tree_complete=tree_complete,
        tree_entries=len(entries),
        sampled_files=tuple(read_paths),
        skipped_large_files=skipped_large,
        sampled_bytes=sampled_bytes,
        signals=signals,
        status=status,
        priority=_priority_for(metadata, classification),
        blocking=blocking,
        missing=missing,
        evidence=tuple(evidence),
        limitations=tuple(sorted(set(limitations))),
    )


def summarize(results: Sequence[RepositoryResult]) -> dict[str, Any]:
    return {
        "repositories": len(results),
        "active": sum(not item.archived for item in results),
        "archived": sum(item.archived for item in results),
        "ui_bearing": sum(item.interface_scope == "web_ui" for item in results),
        "source_ready": sum(item.status in {"SOURCE_READY", "SOURCE_READY_SAMPLED"} for item in results),
        "audit_gap": sum(item.status == "SOURCE_READY_AUDIT_GAP" for item in results),
        "action_required": sum(item.status == "ACTION_REQUIRED" for item in results),
        "evidence_incomplete": sum(item.status == "EVIDENCE_INCOMPLETE" for item in results),
        "blocking": sum(item.blocking for item in results),
        "classifications": dict(sorted(Counter(item.classification for item in results).items())),
        "statuses": dict(sorted(Counter(item.status for item in results).items())),
    }


def report_payload(
    *,
    reader_mode: str,
    reader_credential: str,
    reader_attempts: Sequence[Mapping[str, Any]],
    results: Sequence[RepositoryResult],
    errors: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda item: (item.priority, item.repository))
    summary = summarize(ordered)
    complete = not errors and summary["repositories"] > 0
    status = "PASS" if complete and summary["blocking"] == 0 else "FAIL"
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "organization": ORG,
        "status": status,
        "inventory_complete": complete,
        "reader": {
            "mode": reader_mode,
            "credential_name": reader_credential,
            "attempts": [dict(item) for item in reader_attempts],
            "credential_value_recorded": False,
        },
        "summary": summary,
        "errors": list(errors),
        "repositories": [
            {
                **asdict(item),
                "signals": asdict(item.signals),
            }
            for item in ordered
        ],
        "boundaries": [
            "This is source and repository classification evidence, not a live-runtime health claim.",
            "Libraries, APIs, research, control-plane, docs-only, and archived repositories are not forced to implement a browser layout.",
            "UI-bearing repositories are sampled under bounded file/byte limits and retain explicit limitations.",
            "No repository, branch, setting, deployment, DNS record, Hugging Face asset, or secret is mutated by this audit.",
            "Runtime phone-to-ultrawide proof remains the responsibility of SZL Public Experience v3 and repository-native deployment checks.",
        ],
    }


def markdown_report(payload: Mapping[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# GitHub responsive estate audit",
        "",
        f"- Status: **{payload['status']}**",
        f"- Inventory complete: **{str(payload['inventory_complete']).lower()}**",
        f"- Repositories: **{summary['repositories']}** ({summary['active']} active / {summary['archived']} archived)",
        f"- UI-bearing: **{summary['ui_bearing']}**",
        f"- Source ready: **{summary['source_ready']}**",
        f"- Source-ready but missing browser automation: **{summary['audit_gap']}**",
        f"- Action required: **{summary['action_required']}**",
        f"- Evidence incomplete: **{summary['evidence_incomplete']}**",
        f"- Release-blocking public UI findings: **{summary['blocking']}**",
        "",
        "## Action queue",
        "",
        "| Priority | Repository | Class | Status | Missing / limitation |",
        "|---|---|---|---|---|",
    ]
    action_rows = [
        item
        for item in payload["repositories"]
        if item["status"] not in {"SOURCE_READY", "SOURCE_READY_SAMPLED", "NOT_APPLICABLE"}
    ]
    if not action_rows:
        lines.append("| — | — | — | — | No open responsive source findings |")
    else:
        for item in action_rows:
            detail = ", ".join(item["missing"] or item["limitations"] or ["review required"])
            detail = detail.replace("|", "\\|")[:240]
            lines.append(
                f"| {item['priority']} | `{item['repository']}` | {item['classification']} | "
                f"{item['status']} | {detail} |"
            )
    lines.extend(
        [
            "",
            "## Classification ledger",
            "",
            "| Repository | Visibility | Classification | UI scope | Status |",
            "|---|---|---|---|---|",
        ]
    )
    for item in payload["repositories"]:
        lines.append(
            f"| `{item['repository']}` | {item['visibility']} | {item['classification']} | "
            f"{item['interface_scope']} | {item['status']} |"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            *[f"- {value}" for value in payload["boundaries"]],
            "",
        ]
    )
    return "\n".join(lines)


def execute(output: Path, markdown: Path) -> int:
    try:
        reader = select_reader()
    except ReaderSelectionError as exc:
        payload = {
            "schema": SCHEMA,
            "generated_at": utc_now(),
            "organization": ORG,
            "status": "FAIL",
            "inventory_complete": False,
            "reader": {
                "mode": None,
                "credential_name": None,
                "attempts": [dict(item) for item in exc.attempts],
                "credential_value_recorded": False,
            },
            "summary": {
                "repositories": 0,
                "active": 0,
                "archived": 0,
                "ui_bearing": 0,
                "source_ready": 0,
                "audit_gap": 0,
                "action_required": 0,
                "evidence_incomplete": 0,
                "blocking": 1,
                "classifications": {},
                "statuses": {},
            },
            "errors": [{"repository": ORG, "error": type(exc).__name__}],
            "repositories": [],
            "boundaries": [
                "No credential value is recorded.",
                "UNKNOWN inventory is never converted to PASS.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown.write_text(markdown_report(payload), encoding="utf-8")
        return 2

    results: list[RepositoryResult] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(audit_repository, reader.token, repository): repository
            for repository in reader.repositories
        }
        for future in as_completed(futures):
            repository = futures[future]
            name = str(repository.get("full_name") or repository.get("name") or "UNKNOWN")
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - report class only, never secrets
                errors.append({"repository": name, "error": type(exc).__name__})

    payload = report_payload(
        reader_mode=reader.mode,
        reader_credential=reader.credential_name,
        reader_attempts=reader.attempts,
        results=results,
        errors=errors,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(markdown_report(payload), encoding="utf-8")
    return 0 if payload["status"] == "PASS" else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/github-responsive-estate.json"))
    parser.add_argument("--markdown", type=Path, default=Path("reports/github-responsive-estate.md"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return execute(args.output, args.markdown)


if __name__ == "__main__":
    raise SystemExit(main())
