#!/usr/bin/env python3
"""Create guarded per-repository PRs for A11oy Holo-Constellation Space identity.

The controller inventories the current public SZLHOLDINGS Spaces, resolves their
GitHub source of truth, detects a supported frontend stack, and creates a normal
review branch and pull request. It never writes to a default branch, force
pushes, changes protection, or writes directly to Hugging Face.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"
SCHEMA = "szl.holographic-space-rollout/v2"
ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
BRANCH = "design/holographic-space-v2"
ASSET_REPO = "szl-holdings/a11oy"
ASSET_REF = "main"
ASSET_CSS = "console/assets/szl-holo-v2.css"
ASSET_JS = "console/assets/szl-holo-v2.js"
SOURCE_MAP = "docs/huggingface-space-source-map-v1.json"
STATIC_MARKER = "data-szl-holo-space-v2"
PYTHON_MARKER = "# SZL Holo Space v2"

STATIC_ENTRIES = (
    "index.html",
    "public/index.html",
    "site/index.html",
    "web/index.html",
    "frontend/index.html",
    "space/index.html",
    "docs/index.html",
)
NEXT_ENTRIES = (
    "app/layout.tsx", "app/layout.jsx", "app/layout.js", "app/layout.ts",
    "src/app/layout.tsx", "src/app/layout.jsx", "src/app/layout.js", "src/app/layout.ts",
    "pages/_document.tsx", "pages/_document.jsx", "pages/_document.js", "pages/_document.ts",
    "src/pages/_document.tsx", "src/pages/_document.jsx", "src/pages/_document.js", "src/pages/_document.ts",
)
PYTHON_ENTRIES = (
    "app.py", "main.py", "space/app.py", "src/app.py", "demo/app.py", "web/app.py",
    "Home.py", "streamlit_app.py",
)
ARCHETYPE_HINTS = {
    "lyte": ("lyte", "observability", "signal", "lattice"),
    "vessels": ("vessels", "maritime", "fleet", "voyage", "ais"),
    "terra": ("terra", "real-estate", "realestate", "property", "parcel"),
    "aegis": ("aegis", "security", "defense", "threat", "cyber"),
    "prism-counsel": ("prism", "counsel", "legal", "matter"),
    "carlota-jo": ("carlota", "advisory"),
    "nexus": ("nexus", "integration", "router", "bridge"),
    "factory": ("factory", "forge", "atelier", "builder"),
    "ouroboros": ("ouroboros", "research", "loop", "thesis"),
    "khipu": ("khipu", "kernel", "consensus", "receipt"),
    "killinchu": ("killinchu", "agent", "swarm", "orchestration"),
}
MOTIFS = {
    "lyte": "signal-aurora",
    "vessels": "bathymetric-radar",
    "terra": "topographic-parcels",
    "aegis": "threat-lattice",
    "prism-counsel": "case-facets",
    "carlota-jo": "editorial-orbit",
    "nexus": "connection-field",
    "factory": "assembly-circuit",
    "ouroboros": "recursive-ring",
    "khipu": "woven-proof",
    "killinchu": "agent-swarm",
}
FALLBACK_MOTIFS = tuple(MOTIFS.values()) + ("command-constellation",)
PALETTES = (
    ("#07131a", "#102633", "#f2fbff", "#9ab4c2", "#64dcff", "#a88bff"),
    ("#130a10", "#291522", "#fff6fb", "#c2a2b3", "#ff7bc3", "#ffb56b"),
    ("#07140d", "#12281a", "#f5fff7", "#9db8a4", "#72efa0", "#5ad6ff"),
    ("#130e06", "#2a1d0e", "#fffaf0", "#c2b297", "#ffc66d", "#ff7d73"),
    ("#090a18", "#171932", "#f6f6ff", "#a6a8c4", "#878cff", "#54e4d7"),
    ("#0f0715", "#24102f", "#fff6ff", "#bca6c5", "#d88cff", "#74c6ff"),
    ("#061315", "#10272b", "#f1feff", "#9bb9bb", "#50e3d4", "#b4ed70"),
    ("#140808", "#2d1414", "#fff6f4", "#c2a3a0", "#ff6c63", "#e9cf6f"),
    ("#0a1115", "#16242c", "#f5fbff", "#a3b2bb", "#83c7ff", "#8df0bd"),
    ("#111006", "#282512", "#fffef0", "#beb99b", "#e5f36b", "#e8a85f"),
    ("#0b0714", "#1c122c", "#faf6ff", "#aea2c0", "#b697ff", "#ff82ad"),
    ("#07120f", "#12251f", "#f2fff9", "#9db6aa", "#75e8b4", "#c1a0ff"),
)


class RolloutError(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class Change:
    path: str
    content: str


@dataclass
class Space:
    identifier: str
    slug: str
    sdk: str
    stage: str
    source_repo: str | None = None
    source_root: str = ""
    mapping: str = "unmapped"


@dataclass
class Plan:
    repository: str
    default_branch: str
    spaces: list[Space] = field(default_factory=list)
    adapter: str | None = None
    entrypoint: str | None = None
    changes: list[Change] = field(default_factory=list)
    status: str = "planned"
    branch: str | None = None
    pull_request: str | None = None
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "default_branch": self.default_branch,
            "spaces": [
                {
                    "identifier": item.identifier,
                    "slug": item.slug,
                    "sdk": item.sdk,
                    "stage": item.stage,
                    "source_root": item.source_root,
                    "mapping": item.mapping,
                }
                for item in self.spaces
            ],
            "adapter": self.adapter,
            "entrypoint": self.entrypoint,
            "change_paths": [item.path for item in self.changes],
            "status": self.status,
            "branch": self.branch,
            "pull_request": self.pull_request,
            "error": self.error,
        }


class HTTP:
    def __init__(self, token: str = "", retries: int = 4):
        self.token = token.strip()
        self.retries = max(1, retries)

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | Sequence[Any] | None = None,
        expected: Iterable[int] = (200,),
    ) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json" if url.startswith(GITHUB_API) else "application/json",
            "User-Agent": "szl-holographic-space-rollout/2.0",
        }
        if url.startswith(GITHUB_API):
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        expected_set = set(expected)
        for attempt in range(1, self.retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
                    if response.status not in expected_set:
                        raise RolloutError("HTTP_STATUS", f"{method} {url} returned {response.status}")
                    return json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", "replace")[:5000]
                try:
                    detail: Any = json.loads(raw)
                except json.JSONDecodeError:
                    detail = raw
                retryable = exc.code in {403, 429, 500, 502, 503, 504}
                if retryable and attempt < self.retries:
                    retry_after = exc.headers.get("Retry-After")
                    time.sleep(min(int(retry_after), 60) if retry_after and retry_after.isdigit() else min(2**attempt, 20))
                    continue
                raise RolloutError(
                    "HTTP_ERROR",
                    f"{method} {url} returned {exc.code}",
                    {"status": exc.code, "response": detail},
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 20))
                    continue
                raise RolloutError("TRANSPORT_ERROR", f"{method} {url} failed: {exc}") from exc
        raise AssertionError("unreachable")


class GitHub:
    def __init__(self, token: str):
        self.http = HTTP(token)

    def get(self, path: str) -> Any:
        return self.http.request("GET", GITHUB_API + path)

    def post(self, path: str, payload: Mapping[str, Any], expected: Iterable[int] = (201,)) -> Any:
        return self.http.request("POST", GITHUB_API + path, payload, expected)

    def put(self, path: str, payload: Mapping[str, Any], expected: Iterable[int] = (200, 201)) -> Any:
        return self.http.request("PUT", GITHUB_API + path, payload, expected)

    def paged(self, path: str) -> list[Any]:
        rows: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 21):
            batch = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RolloutError("INVALID_RESPONSE", f"Expected list from {path}")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise RolloutError("PAGINATION_LIMIT", f"Pagination exceeded safe bound for {path}")

    def repositories(self, organization: str) -> list[dict[str, Any]]:
        return self.paged(f"/orgs/{quote(organization)}/repos?type=all&sort=full_name")

    def content(self, repository: str, path: str, ref: str) -> tuple[str, str]:
        owner, name = repository.split("/", 1)
        encoded = urllib.parse.quote(path, safe="/")
        query = urllib.parse.urlencode({"ref": ref})
        value = self.get(f"/repos/{quote(owner)}/{quote(name)}/contents/{encoded}?{query}")
        if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
            raise RolloutError("UNSUPPORTED_CONTENT", f"Expected base64 content for {repository}:{path}")
        text = base64.b64decode(value["content"].replace("\n", "")).decode("utf-8")
        return text, str(value["sha"])

    def maybe_content(self, repository: str, path: str, ref: str) -> tuple[str, str] | None:
        try:
            return self.content(repository, path, ref)
        except RolloutError as exc:
            if exc.details.get("status") == 404:
                return None
            raise

    def tree(self, repository: str, ref: str) -> list[dict[str, Any]]:
        owner, name = repository.split("/", 1)
        commit = self.get(f"/repos/{quote(owner)}/{quote(name)}/commits/{urllib.parse.quote(ref, safe='')}")
        tree_sha = commit.get("commit", {}).get("tree", {}).get("sha")
        if not tree_sha:
            raise RolloutError("TREE_SHA_MISSING", f"Could not resolve tree for {repository}@{ref}")
        tree = self.get(f"/repos/{quote(owner)}/{quote(name)}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise RolloutError("TREE_TRUNCATED", f"Tree for {repository} is truncated")
        return [row for row in tree.get("tree", []) if row.get("type") == "blob"]

    def ref_sha(self, repository: str, branch: str) -> str:
        owner, name = repository.split("/", 1)
        value = self.get(f"/repos/{quote(owner)}/{quote(name)}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        sha = value.get("object", {}).get("sha")
        if not sha:
            raise RolloutError("REF_SHA_MISSING", f"Could not resolve {repository}:{branch}")
        return str(sha)

    def ref_exists(self, repository: str, branch: str) -> bool:
        try:
            self.ref_sha(repository, branch)
            return True
        except RolloutError as exc:
            if exc.details.get("status") == 404:
                return False
            raise

    def create_branch(self, repository: str, branch: str, sha: str) -> None:
        owner, name = repository.split("/", 1)
        self.post(f"/repos/{quote(owner)}/{quote(name)}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})

    def write_file(self, repository: str, branch: str, change: Change, message: str) -> None:
        owner, name = repository.split("/", 1)
        encoded = urllib.parse.quote(change.path, safe="/")
        current = self.maybe_content(repository, change.path, branch)
        payload: dict[str, Any] = {
            "branch": branch,
            "message": message,
            "content": base64.b64encode(change.content.encode("utf-8")).decode("ascii"),
        }
        if current:
            payload["sha"] = current[1]
        self.put(f"/repos/{quote(owner)}/{quote(name)}/contents/{encoded}", payload)

    def open_pr(self, repository: str, organization: str, branch: str) -> dict[str, Any] | None:
        owner, name = repository.split("/", 1)
        query = urllib.parse.urlencode({"state": "open", "head": f"{organization}:{branch}", "per_page": 20})
        rows = self.get(f"/repos/{quote(owner)}/{quote(name)}/pulls?{query}")
        return rows[0] if rows else None

    def create_pr(self, repository: str, branch: str, base: str, title: str, body: str) -> dict[str, Any]:
        owner, name = repository.split("/", 1)
        return self.post(
            f"/repos/{quote(owner)}/{quote(name)}/pulls",
            {"head": branch, "base": base, "title": title, "body": body, "maintainer_can_modify": True},
        )


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")[:96] or "a11oy-space"


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def fnv1a(value: str) -> int:
    result = 0x811C9DC5
    for character in value:
        result ^= ord(character)
        result = (result * 0x01000193) & 0xFFFFFFFF
    return result


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in slug(value).split("-") if part)


def archetype(space_slug: str) -> str | None:
    value = slug(space_slug)
    for name, hints in ARCHETYPE_HINTS.items():
        if any(hint in value for hint in hints):
            return name
    return None


def theme(space_slug: str) -> dict[str, Any]:
    seed = fnv1a(space_slug)
    kind = archetype(space_slug)
    return {
        "id": space_slug,
        "label": title_case(space_slug),
        "motif": MOTIFS.get(kind or "", FALLBACK_MOTIFS[(seed >> 8) % len(FALLBACK_MOTIFS)]),
        "palette": list(PALETTES[seed % len(PALETTES)]),
        "source": "space-specific",
        "archetype": kind or "independent",
    }


def asset_digest(css: str, javascript: str) -> str:
    digest = hashlib.sha256()
    digest.update(css.encode("utf-8"))
    digest.update(b"\0")
    digest.update(javascript.encode("utf-8"))
    return digest.hexdigest()


def unique_javascript(javascript: str, space_theme: Mapping[str, Any]) -> str:
    needle = "function resolveTheme() {"
    if needle not in javascript:
        raise RolloutError("ASSET_SHAPE_CHANGED", "Canonical JavaScript no longer exposes resolveTheme()")
    override = json.dumps(
        {
            "id": space_theme["id"],
            "label": space_theme["label"],
            "motif": space_theme["motif"],
            "palette": space_theme["palette"],
            "source": "space-specific",
        },
        separators=(",", ":"),
    )
    return javascript.replace(needle, needle + f"\n    return {override};", 1)


def add_html_attribute(source: str, space_slug: str) -> str:
    match = re.search(r"<html(?P<attrs>[^>]*)>", source, flags=re.IGNORECASE)
    if match is None:
        raise RolloutError("HTML_SHAPE_UNSUPPORTED", "Document has no html element")
    if STATIC_MARKER in match.group(0):
        return source
    replacement = f'<html{match.group("attrs")} {STATIC_MARKER}="{html.escape(space_slug, quote=True)}">'
    return source[: match.start()] + replacement + source[match.end() :]


def insert_before(source: str, token: str, payload: str) -> str:
    offset = source.lower().rfind(token.lower())
    if offset < 0:
        raise RolloutError("INJECTION_POINT_MISSING", f"Missing {token}")
    return source[:offset] + payload + source[offset:]


def adapt_static(source: str, space_slug: str, css_href: str, js_href: str) -> str:
    if f'{STATIC_MARKER}="{space_slug}"' in source and "szl-holo-v2.css" in source and "szl-holo-v2.js" in source:
        return source
    if "</head>" not in source.lower() or "</body>" not in source.lower():
        raise RolloutError("HTML_SHAPE_UNSUPPORTED", "Static document needs closing head and body tags")
    source = add_html_attribute(source, space_slug)
    if "szl-holo-v2.css" not in source:
        source = insert_before(source, "</head>", f'  <link rel="stylesheet" href="{css_href}" data-szl-holo-space-asset="style-v2" />\n')
    if "szl-holo-v2.js" not in source:
        source = insert_before(source, "</body>", f'  <script src="{js_href}" defer data-szl-holo-space-asset="script-v2"></script>\n')
    return source


def offsets(source: str) -> list[int]:
    values = [0]
    for match in re.finditer("\n", source):
        values.append(match.end())
    return values


def node_range(node: ast.AST, line_offsets: Sequence[int]) -> tuple[int, int]:
    return (
        line_offsets[node.lineno - 1] + node.col_offset,
        line_offsets[node.end_lineno - 1] + node.end_col_offset,
    )


def import_offset(source: str, module: ast.Module) -> int:
    body = list(module.body)
    index = 0
    line = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        line = int(body[0].end_lineno or body[0].lineno)
        index = 1
    while index < len(body) and isinstance(body[index], ast.ImportFrom) and body[index].module == "__future__":
        line = int(body[index].end_lineno or body[index].lineno)
        index += 1
    return sum(len(value) for value in source.splitlines(keepends=True)[:line])


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def compatible_expression(node: ast.AST) -> bool:
    return isinstance(node, (ast.Constant, ast.Name, ast.Attribute, ast.BinOp, ast.JoinedStr, ast.Call, ast.Subscript))


def adapt_gradio(source: str) -> str:
    if PYTHON_MARKER in source:
        return source
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise RolloutError("PYTHON_PARSE_FAILED", f"Could not parse Gradio source: {exc}") from exc
    calls = [node for node in ast.walk(module) if isinstance(node, ast.Call) and call_name(node) in {"Blocks", "Interface", "TabbedInterface"}]
    if not calls:
        raise RolloutError("GRADIO_CALL_MISSING", "No Gradio Blocks/Interface call was found")
    call = min(calls, key=lambda item: (item.lineno, item.col_offset))
    line_offsets = offsets(source)
    call_start, call_end = node_range(call, line_offsets)
    opening = source.find("(", call_start, call_end)
    closing = call_end - 1
    if opening < 0 or source[closing] != ")":
        raise RolloutError("GRADIO_CALL_SHAPE", "Could not locate Gradio call parentheses")
    operations: list[tuple[int, int, str]] = []
    existing = {item.arg: item for item in call.keywords if item.arg}
    for keyword, additive in (("css", "SZL_HOLO_CSS"), ("head", "SZL_HOLO_HEAD")):
        item = existing.get(keyword)
        if item is None:
            continue
        if not compatible_expression(item.value):
            raise RolloutError("GRADIO_CUSTOM_VALUE_UNSUPPORTED", f"Existing {keyword}= expression cannot be safely composed")
        start, end = node_range(item.value, line_offsets)
        segment = source[start:end]
        operations.append((start, end, f"({segment}) + {additive}"))
    missing = [(key, value) for key, value in (("css", "SZL_HOLO_CSS"), ("head", "SZL_HOLO_HEAD")) if key not in existing]
    if missing:
        inner = source[opening + 1 : closing].rstrip()
        prefix = "" if not inner or inner.endswith(",") else ", "
        payload = prefix + ", ".join(f"{key}={value}" for key, value in missing)
        operations.append((closing, closing, payload))
    for start, end, replacement in sorted(operations, reverse=True):
        source = source[:start] + replacement + source[end:]
    insertion = import_offset(source, ast.parse(source))
    import_line = f"\n{PYTHON_MARKER}\nfrom szl_holo_space_v2 import SZL_HOLO_CSS, SZL_HOLO_HEAD\n"
    return source[:insertion] + import_line + source[insertion:]


def adapt_streamlit(source: str) -> str:
    if PYTHON_MARKER in source:
        return source
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise RolloutError("PYTHON_PARSE_FAILED", f"Could not parse Streamlit source: {exc}") from exc
    line_offsets = offsets(source)
    insertion = import_offset(source, module)
    call_offset = insertion
    for node in module.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "set_page_config":
                _, call_offset = node_range(node, line_offsets)
                while call_offset < len(source) and source[call_offset] in "\r\n":
                    call_offset += 1
                break
    call = "\ninstall_streamlit_holo(st)\n"
    source = source[:call_offset] + call + source[call_offset:]
    import_line = f"\n{PYTHON_MARKER}\nfrom szl_holo_space_v2 import install_streamlit_holo\n"
    return source[:insertion] + import_line + source[insertion:]


def gradio_helper(css: str, javascript: str, space_theme: Mapping[str, Any]) -> str:
    js = unique_javascript(javascript, space_theme).replace("</script>", "<\\/script>")
    return (
        '"""First-party A11oy Holo-Constellation assets for this Space."""\n\n'
        + f"SZL_HOLO_CSS = {css!r}\n"
        + f"_SZL_HOLO_JS = {js!r}\n"
        + f"SZL_HOLO_HEAD = '<script data-szl-holo-space=\"{space_theme['id']}\">' + _SZL_HOLO_JS + '</script>'\n"
    )


def streamlit_helper(css: str, space_theme: Mapping[str, Any]) -> str:
    palette = space_theme["palette"]
    links = "".join(
        f'<a class="szl-holo-link" href="{href}" target="_top">{label}</a>'
        for label, href in (
            ("Command", "https://a-11-oy.com/"),
            ("Proof", "https://a11oy.net/record/"),
            ("Source", "https://github.com/szl-holdings"),
            ("Spaces", "https://huggingface.co/SZLHOLDINGS"),
        )
    )
    rail = (
        f'<div class="szl-holo-rail" data-szl-holo-space-v2="{space_theme["id"]}">'
        f'<div class="szl-holo-identity"><span class="szl-holo-mark"></span><span class="szl-holo-copy">'
        f'<span class="szl-holo-eyebrow">SZL · Holo-Constellation</span><span class="szl-holo-label">{html.escape(space_theme["label"])}</span>'
        f'</span></div><nav class="szl-holo-nav">{links}</nav></div>'
    )
    override = (
        f":root{{--szl-holo-bg:{palette[0]};--szl-holo-bg-deep:{palette[0]};--szl-holo-surface:{palette[1]};"
        f"--szl-holo-surface-2:{palette[1]};--szl-holo-ink:{palette[2]};--szl-holo-muted:{palette[3]};"
        f"--szl-holo-accent:{palette[4]};--szl-holo-accent-2:{palette[5]};}}"
        ".stApp{color:var(--szl-holo-ink);background:radial-gradient(circle at 84% 8%,color-mix(in srgb,var(--szl-holo-accent-2) 12%,transparent),transparent 28rem),linear-gradient(158deg,var(--szl-holo-bg),var(--szl-holo-surface));}"
        ".szl-holo-rail{position:relative;margin:-1rem -1rem 1.2rem;border:1px solid var(--szl-holo-line);border-radius:16px;}"
        "@media(max-width:760px){.szl-holo-nav{position:static;display:flex;overflow-x:auto}.szl-holo-link{flex:0 0 auto}}"
    )
    markup = f"<style>{css}{override}</style>{rail}"
    return (
        '"""First-party CSS-only A11oy Holo-Constellation adapter for Streamlit."""\n\n'
        + f"_SZL_HOLO_MARKUP = {markup!r}\n\n"
        + "def install_streamlit_holo(st):\n"
        + "    st.markdown(_SZL_HOLO_MARKUP, unsafe_allow_html=True)\n"
    )


def source_map_entries(value: Any) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(source_map_entries(item))
    elif isinstance(value, dict):
        strings = {str(key): str(item) for key, item in value.items() if isinstance(item, str)}
        space = next((item for key, item in strings.items() if key.lower() in {"space", "space_id", "hf_space", "huggingface_space", "slug"}), "")
        repo = next((item for key, item in strings.items() if key.lower() in {"source_repo", "repository", "github_repo", "source", "repo"}), "")
        root = next((item for key, item in strings.items() if key.lower() in {"source_root", "source_path", "subdir", "path", "directory"}), "")
        if not space:
            space = next((item for item in strings.values() if "SZLHOLDINGS/" in item or "huggingface.co/spaces/SZLHOLDINGS/" in item), "")
        if not repo:
            repo = next((item for item in strings.values() if "szl-holdings/" in item or "github.com/szl-holdings/" in item), "")
        if space and repo:
            space_slug = slug(space.rstrip("/").split("/")[-1])
            match = re.search(r"(?:github\.com/)?(szl-holdings/[A-Za-z0-9_.-]+)", repo)
            if match:
                rows.append((space_slug, match.group(1), root.strip("/")))
        for item in value.values():
            if isinstance(item, (dict, list)):
                rows.extend(source_map_entries(item))
    return rows


def list_spaces() -> list[Space]:
    url = HF_API + "/spaces?" + urllib.parse.urlencode({"author": HF_ORG, "limit": 100, "full": "true"})
    values = HTTP().request("GET", url)
    rows: list[Space] = []
    for item in values:
        identifier = str(item.get("id") or item.get("_id") or "")
        if not identifier:
            continue
        card = item.get("cardData") or {}
        runtime = item.get("runtime") or {}
        rows.append(
            Space(
                identifier=identifier,
                slug=slug(identifier.split("/")[-1]),
                sdk=str(item.get("sdk") or card.get("sdk") or "").lower(),
                stage=str(runtime.get("stage") or item.get("stage") or "unknown"),
            )
        )
    return rows


def resolve_sources(github: GitHub, spaces: list[Space], repositories: list[dict[str, Any]]) -> None:
    source_text, _ = github.content(ASSET_REPO, SOURCE_MAP, ASSET_REF)
    explicit = {space_slug: (repo, root) for space_slug, repo, root in source_map_entries(json.loads(source_text))}
    by_compact = {compact(item.get("name")): str(item.get("full_name")) for item in repositories if item.get("name")}
    for item in spaces:
        if item.slug in explicit:
            item.source_repo, item.source_root = explicit[item.slug]
            item.mapping = "source-map"
            continue
        exact = by_compact.get(compact(item.slug))
        if exact:
            item.source_repo = exact
            item.mapping = "exact-repository-name"


def roots_for(space: Space) -> list[str]:
    values = [space.source_root, f"spaces/{space.slug}", space.slug, "space", ""]
    seen: set[str] = set()
    roots: list[str] = []
    for value in values:
        cleaned = value.strip("/")
        if cleaned not in seen:
            seen.add(cleaned)
            roots.append(cleaned)
    return roots


def prefixed(root: str, path: str) -> str:
    return f"{root}/{path}" if root else path


def find_entry(paths: set[str], space: Space) -> tuple[str, str] | None:
    roots = roots_for(space)
    sdk = space.sdk
    ordered: list[tuple[str, Sequence[str]]]
    if sdk == "static":
        ordered = [("static-html", STATIC_ENTRIES), ("next-layout", NEXT_ENTRIES), ("python", PYTHON_ENTRIES)]
    elif sdk == "gradio":
        ordered = [("python", PYTHON_ENTRIES), ("static-html", STATIC_ENTRIES), ("next-layout", NEXT_ENTRIES)]
    elif sdk == "streamlit":
        ordered = [("python", PYTHON_ENTRIES), ("static-html", STATIC_ENTRIES), ("next-layout", NEXT_ENTRIES)]
    else:
        ordered = [("next-layout", NEXT_ENTRIES), ("static-html", STATIC_ENTRIES), ("python", PYTHON_ENTRIES)]
    for root in roots:
        for adapter, candidates in ordered:
            for candidate in candidates:
                full = prefixed(root, candidate)
                if full in paths:
                    return adapter, full
    return None


def plan_space(github: GitHub, repo: Mapping[str, Any], space: Space, css: str, javascript: str) -> Plan:
    repository = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    plan = Plan(repository=repository, default_branch=default_branch, spaces=[space])
    paths = {str(item.get("path")) for item in github.tree(repository, default_branch)}
    found = find_entry(paths, space)
    if not found:
        plan.status = "report-only"
        plan.error = {"code": "NO_SUPPORTED_ENTRYPOINT", "message": "No static, Next.js, Gradio, or Streamlit entrypoint matched."}
        return plan
    adapter, entry = found
    source, _ = github.content(repository, entry, default_branch)
    root = str(Path(entry).parent).replace(".", "").strip("/")
    space_theme = theme(space.slug)
    unique_js = unique_javascript(javascript, space_theme)

    if adapter == "static-html":
        asset_root = root
        css_path = prefixed(asset_root, "szl-holo-v2.css")
        js_path = prefixed(asset_root, "szl-holo-v2.js")
        patched = adapt_static(source, space.slug, "./szl-holo-v2.css", "./szl-holo-v2.js")
        plan.adapter = adapter
        plan.entrypoint = entry
        plan.changes = [Change(css_path, css), Change(js_path, unique_js), Change(entry, patched)]
        return plan

    if adapter == "next-layout":
        patched = adapt_static(source, space.slug, "/szl-holo-v2.css", "/szl-holo-v2.js")
        public_root = prefixed(space.source_root.strip("/"), "public") if space.source_root else "public"
        plan.adapter = adapter
        plan.entrypoint = entry
        plan.changes = [
            Change(prefixed(public_root, "szl-holo-v2.css"), css),
            Change(prefixed(public_root, "szl-holo-v2.js"), unique_js),
            Change(entry, patched),
        ]
        return plan

    lower = source.lower()
    if "streamlit" in lower or space.sdk == "streamlit" or re.search(r"\bst\.", source):
        patched = adapt_streamlit(source)
        plan.adapter = "streamlit-python"
        plan.entrypoint = entry
        plan.changes = [Change(prefixed(root, "szl_holo_space_v2.py"), streamlit_helper(css, space_theme)), Change(entry, patched)]
        return plan
    if "gradio" in lower or space.sdk == "gradio" or re.search(r"\bgr\.", source):
        patched = adapt_gradio(source)
        plan.adapter = "gradio-python"
        plan.entrypoint = entry
        plan.changes = [Change(prefixed(root, "szl_holo_space_v2.py"), gradio_helper(css, javascript, space_theme)), Change(entry, patched)]
        return plan

    plan.status = "report-only"
    plan.error = {"code": "PYTHON_FRAMEWORK_UNSUPPORTED", "message": "Python entrypoint did not expose a safe Gradio or Streamlit adapter."}
    return plan


def merge_plans(plans: list[Plan]) -> list[Plan]:
    grouped: dict[str, Plan] = {}
    for item in plans:
        current = grouped.get(item.repository)
        if current is None:
            grouped[item.repository] = item
            continue
        current.spaces.extend(item.spaces)
        if current.status != "planned" or item.status != "planned":
            current.status = "report-only"
            current.error = {
                "code": "MULTI_SPACE_REPOSITORY_REQUIRES_REVIEW",
                "message": "Multiple mapped Spaces in this repository did not resolve to one unambiguous automatic patch.",
            }
            current.changes = []
            continue
        existing_paths = {change.path for change in current.changes}
        collision = existing_paths.intersection(change.path for change in item.changes)
        if collision:
            current.status = "report-only"
            current.error = {"code": "CHANGE_PATH_COLLISION", "message": f"Multiple Spaces target the same files: {sorted(collision)}"}
            current.changes = []
            continue
        current.changes.extend(item.changes)
        current.adapter = "multi-space"
        current.entrypoint = ", ".join(filter(None, (current.entrypoint, item.entrypoint)))
    return sorted(grouped.values(), key=lambda item: item.repository)


def pr_body(plan: Plan, digest: str) -> str:
    spaces = "\n".join(
        f"- `{item.identifier}` — SDK `{item.sdk or 'unknown'}`, runtime stage `{item.stage}`, mapping `{item.mapping}`"
        for item in plan.spaces
    )
    files = "\n".join(f"- `{item.path}`" for item in plan.changes)
    return f"""## A11oy Holo-Constellation Space rollout

This source repository is receiving a first-party, Space-specific A11oy visual instrument while keeping its native product workflow and information architecture.

### Spaces

{spaces}

### Adapter

- adapter: `{plan.adapter}`
- entrypoint: `{plan.entrypoint}`
- canonical asset digest: `{digest}`
- review branch: `{BRANCH}`

### Files

{files}

### Experience contract

- unique deterministic palette and identity for each Space slug;
- domain-appropriate motif where the slug maps to Lyte, Vessels, Terra, Aegis, PRISM, Carlota Jo, Nexus, Factory, Ouroboros, KHIPU, or Killinchu;
- shared Command / Products / Proof / Source / Spaces navigation;
- local assets only; no analytics, cookies, browser storage, runtime fetch, CDN, or external font;
- keyboard focus, 44px controls, reduced motion, increased contrast, forced colors, mobile, and print behavior;
- decorative motion is not measured telemetry.

### Governance boundary

This pull request does not alter branch protection, default-branch policy, model weights, datasets, receipt truth, API behavior, secrets, or Hugging Face state directly. Existing CI and the canonical publisher remain the release authorities.

Generated by `{SCHEMA}`.
"""


def apply_plan(github: GitHub, plan: Plan, digest: str) -> None:
    if plan.status != "planned":
        return
    existing_pr = github.open_pr(plan.repository, ORG, BRANCH)
    if existing_pr:
        plan.status = "pr-open"
        plan.branch = BRANCH
        plan.pull_request = str(existing_pr.get("html_url"))
        return
    if github.ref_exists(plan.repository, BRANCH):
        raise RolloutError("BRANCH_EXISTS_WITHOUT_PR", f"{plan.repository}:{BRANCH} exists without an open pull request")
    github.create_branch(plan.repository, BRANCH, github.ref_sha(plan.repository, plan.default_branch))
    for index, change in enumerate(plan.changes, start=1):
        github.write_file(
            plan.repository,
            BRANCH,
            change,
            f"feat(frontend): apply Holo Space v2 ({index}/{len(plan.changes)})\n\nSigned-off-by: Stephen P. Lutar <stephenlutar2@gmail.com>",
        )
    pull = github.create_pr(
        plan.repository,
        BRANCH,
        plan.default_branch,
        "feat(frontend): join the A11oy Holo-Constellation v2",
        pr_body(plan, digest),
    )
    plan.status = "pr-created"
    plan.branch = BRANCH
    plan.pull_request = str(pull.get("html_url"))


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repo-filter", default="")
    parser.add_argument("--space-filter", default="")
    parser.add_argument("--max-repos", type=int, default=100)
    parser.add_argument("--report", type=Path, default=Path("reports/holographic-space-rollout-v2.json"))
    parser.add_argument("--token-env", default="GH_ORG_TOKEN")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get(args.token_env, "")
    if args.apply and not token:
        raise RolloutError("WRITE_TOKEN_MISSING", f"Apply mode requires {args.token_env}")
    github = GitHub(token)
    repositories = github.repositories(ORG)
    repository_by_name = {str(item["full_name"]): item for item in repositories}
    css, _ = github.content(ASSET_REPO, ASSET_CSS, ASSET_REF)
    javascript, _ = github.content(ASSET_REPO, ASSET_JS, ASSET_REF)
    digest = asset_digest(css, javascript)
    spaces = list_spaces()
    resolve_sources(github, spaces, repositories)
    repo_pattern = re.compile(args.repo_filter, re.IGNORECASE) if args.repo_filter else None
    space_pattern = re.compile(args.space_filter, re.IGNORECASE) if args.space_filter else None

    raw_plans: list[Plan] = []
    unmapped: list[dict[str, Any]] = []
    for space in spaces:
        if space_pattern and not space_pattern.search(space.identifier):
            continue
        if not space.source_repo:
            unmapped.append({"space": space.identifier, "sdk": space.sdk, "stage": space.stage, "status": "UNMAPPED_SOURCE"})
            continue
        if repo_pattern and not repo_pattern.search(space.source_repo):
            continue
        repo = repository_by_name.get(space.source_repo)
        if not repo or repo.get("archived") or repo.get("disabled") or repo.get("fork"):
            unmapped.append({"space": space.identifier, "source_repo": space.source_repo, "status": "SOURCE_UNAVAILABLE"})
            continue
        if space.source_repo in {f"{ORG}/.github", f"{ORG}/a11oy-net"}:
            continue
        try:
            raw_plans.append(plan_space(github, repo, space, css, javascript))
        except RolloutError as exc:
            raw_plans.append(
                Plan(
                    repository=space.source_repo,
                    default_branch=str(repo.get("default_branch") or "main"),
                    spaces=[space],
                    status="report-only",
                    error=exc.as_dict(),
                )
            )
    plans = merge_plans(raw_plans)[: max(1, args.max_repos)]
    write_failures = 0
    if args.apply:
        for plan in plans:
            try:
                apply_plan(github, plan, digest)
            except RolloutError as exc:
                plan.status = "blocked"
                plan.error = exc.as_dict()
                write_failures += 1

    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "apply" if args.apply else "dry-run",
        "organization": ORG,
        "hugging_face_organization": HF_ORG,
        "canonical_asset_source": {"repository": ASSET_REPO, "ref": ASSET_REF, "css": ASSET_CSS, "javascript": ASSET_JS, "digest": digest},
        "summary": {
            "spaces_discovered": len(spaces),
            "spaces_unmapped_or_unavailable": len(unmapped),
            "repositories_planned": len(plans),
            "write_failures": write_failures,
            **counts,
        },
        "repositories": [plan.as_dict() for plan in plans],
        "unmapped": unmapped,
        "secrets_recorded": False,
        "default_branch_writes": False,
        "force_pushes": False,
        "protection_changes": False,
        "direct_hugging_face_writes": False,
    }
    write_report(args.report, report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 2 if write_failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print(json.dumps({"status": "blocked", "error": exc.as_dict()}, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
