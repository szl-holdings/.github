#!/usr/bin/env python3
"""Create and optionally merge guarded Holographic Space Fabric v2 PRs.

The controller discovers public SZLHOLDINGS Spaces, resolves their canonical
GitHub source repositories, selects a high-confidence frontend adapter, and
opens one reviewable pull request per source repository. It never writes to a
default branch, force-pushes, changes protection, logs credentials, or claims a
Space is live before deployment evidence exists.
"""
from __future__ import annotations

import argparse
import ast
import base64
import concurrent.futures
import hashlib
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

API = "https://api.github.com"
HF_API = "https://huggingface.co/api/spaces"
SCHEMA = "szl.holographic-space-rollout/v2"
BRANCH = "design/szl-holographic-v2"
MARKER = 'data-szl-space-holo-v2="true"'
STYLE_MARKER = 'data-szl-space-holo-v2="style"'
SCRIPT_MARKER = 'data-szl-space-holo-v2="script"'
ASSETS_ROOT = Path("design/holographic-v2")
LOCAL_SOURCE_MAP = Path("design/responsive-v3/flagship-space-sources.json")
MONOREPO_STATIC_ROOTS = {
    "sentra": "artifacts/sentra",
    "vessels": "artifacts/vessels",
}
STATIC_INDEXES = (
    "index.html",
    "app/static/index.html",
    "static/index.html",
    "public/index.html",
    "site/index.html",
    "web/index.html",
    "frontend/index.html",
    "space/index.html",
    "templates/index.html",
    "docs/index.html",
)
NEXT_LAYOUTS = (
    "app/layout.tsx",
    "app/layout.jsx",
    "app/layout.js",
    "app/layout.ts",
    "src/app/layout.tsx",
    "src/app/layout.jsx",
    "src/app/layout.js",
    "src/app/layout.ts",
    "pages/_document.tsx",
    "pages/_document.jsx",
    "pages/_document.js",
    "pages/_document.ts",
    "src/pages/_document.tsx",
    "src/pages/_document.jsx",
    "src/pages/_document.js",
    "src/pages/_document.ts",
)
PYTHON_ENTRIES = (
    "app.py",
    "main.py",
    "space/app.py",
    "src/app.py",
    "demo/app.py",
    "web/app.py",
)
EXCLUDED_REPOS = {".github", "a11oy", "a11oy-net"}
ALLOWED_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}


class RolloutError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class Space:
    slug: str
    sdk: str | None
    stage: str | None
    url: str


@dataclass(frozen=True)
class Change:
    path: str
    content: str


@dataclass
class Plan:
    repository: str
    default_branch: str
    spaces: list[Space]
    mapping_score: int
    mapping_reason: str
    adapter: str | None = None
    entrypoint: str | None = None
    changes: list[Change] = field(default_factory=list)
    status: str = "planned"
    branch: str | None = None
    pull_number: int | None = None
    pull_request: str | None = None
    merge_commit: str | None = None
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "default_branch": self.default_branch,
            "spaces": [space.__dict__ for space in self.spaces],
            "mapping_score": self.mapping_score,
            "mapping_reason": self.mapping_reason,
            "adapter": self.adapter,
            "entrypoint": self.entrypoint,
            "change_paths": [change.path for change in self.changes],
            "status": self.status,
            "branch": self.branch,
            "pull_number": self.pull_number,
            "pull_request": self.pull_request,
            "merge_commit": self.merge_commit,
            "error": self.error,
        }


class GitHub:
    def __init__(self, token: str | None, *, retries: int = 4) -> None:
        self.token = token or ""
        self.retries = max(1, retries)

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | Sequence[Any] | None = None,
        *,
        expected: Iterable[int] = (200,),
    ) -> Any:
        url = path if path.startswith("http") else f"{API}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-holographic-space-rollout-v2",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        expected_set = set(expected)
        for attempt in range(1, self.retries + 1):
            request = urllib.request.Request(url, data=body, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
                    if response.status not in expected_set:
                        raise RolloutError("UNEXPECTED_STATUS", f"{method} {url} returned {response.status}")
                    return json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", "replace")[:8000]
                try:
                    detail: Any = json.loads(raw)
                except json.JSONDecodeError:
                    detail = raw
                if exc.code in {403, 429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(_retry_delay(exc.headers, attempt))
                    continue
                raise RolloutError(
                    "GITHUB_HTTP_ERROR",
                    f"GitHub returned {exc.code} for {method} {url}",
                    details={"status": exc.code, "response": detail},
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 15))
                    continue
                raise RolloutError("GITHUB_TRANSPORT_ERROR", str(exc)) from exc
        raise AssertionError("unreachable")

    def paged(self, path: str) -> list[Any]:
        values: list[Any] = []
        page = 1
        separator = "&" if "?" in path else "?"
        while True:
            batch = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RolloutError("INVALID_RESPONSE", f"Expected a list from {path}")
            values.extend(batch)
            if len(batch) < 100:
                return values
            page += 1
            if page > 20:
                raise RolloutError("PAGINATION_LIMIT", path)

    def repositories(self, org: str) -> list[dict[str, Any]]:
        return self.paged(f"/orgs/{quote(org)}/repos?type=all&sort=full_name")

    def tree(self, full_name: str, ref: str) -> list[dict[str, Any]]:
        owner, repo = full_name.split("/", 1)
        commit = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/commits/{quote(ref)}")
        tree_sha = ((commit or {}).get("commit") or {}).get("tree", {}).get("sha")
        if not tree_sha:
            raise RolloutError("TREE_SHA_MISSING", f"Could not resolve {full_name}@{ref}")
        tree = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise RolloutError("TREE_TRUNCATED", full_name)
        return [item for item in tree.get("tree", []) if item.get("type") == "blob"]

    def file(self, full_name: str, path: str, ref: str) -> tuple[str, str]:
        owner, repo = full_name.split("/", 1)
        query = urllib.parse.urlencode({"ref": ref})
        value = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote_path(path)}?{query}")
        if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
            raise RolloutError("UNSUPPORTED_CONTENT", f"Expected base64 content for {full_name}:{path}")
        return base64.b64decode(value["content"].replace("\n", "")).decode("utf-8"), str(value["sha"])

    def optional_file(self, full_name: str, path: str, ref: str) -> tuple[str, str] | None:
        try:
            return self.file(full_name, path, ref)
        except RolloutError as exc:
            if exc.details.get("status") == 404:
                return None
            raise

    def ref_sha(self, full_name: str, branch: str) -> str:
        owner, repo = full_name.split("/", 1)
        value = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/git/ref/heads/{quote(branch)}")
        sha = (value.get("object") or {}).get("sha")
        if not sha:
            raise RolloutError("REF_SHA_MISSING", f"Could not resolve {full_name}:{branch}")
        return str(sha)

    def ref_exists(self, full_name: str, branch: str) -> bool:
        try:
            self.ref_sha(full_name, branch)
            return True
        except RolloutError as exc:
            if exc.details.get("status") == 404:
                return False
            raise

    def create_branch(self, full_name: str, branch: str, sha: str) -> None:
        owner, repo = full_name.split("/", 1)
        self.request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
            expected=(201,),
        )

    def existing_sha(self, full_name: str, path: str, ref: str) -> str | None:
        value = self.optional_file(full_name, path, ref)
        return value[1] if value else None

    def write_file(self, full_name: str, branch: str, change: Change, message: str) -> None:
        owner, repo = full_name.split("/", 1)
        payload: dict[str, Any] = {
            "message": message,
            "branch": branch,
            "content": base64.b64encode(change.content.encode("utf-8")).decode("ascii"),
        }
        sha = self.existing_sha(full_name, change.path, branch)
        if sha:
            payload["sha"] = sha
        self.request(
            "PUT",
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote_path(change.path)}",
            payload,
            expected=(200, 201),
        )

    def open_pull(self, full_name: str, org: str, branch: str) -> dict[str, Any] | None:
        owner, repo = full_name.split("/", 1)
        query = urllib.parse.urlencode({"state": "open", "head": f"{org}:{branch}", "per_page": 20})
        values = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/pulls?{query}")
        return values[0] if values else None

    def create_pull(self, full_name: str, branch: str, base: str, title: str, body: str) -> dict[str, Any]:
        owner, repo = full_name.split("/", 1)
        return self.request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/pulls",
            {"head": branch, "base": base, "title": title, "body": body, "maintainer_can_modify": True},
            expected=(201,),
        )

    def pull(self, full_name: str, number: int) -> dict[str, Any]:
        owner, repo = full_name.split("/", 1)
        return self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/pulls/{number}")

    def checks(self, full_name: str, sha: str) -> list[dict[str, Any]]:
        owner, repo = full_name.split("/", 1)
        value = self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/commits/{sha}/check-runs?per_page=100")
        return list(value.get("check_runs") or [])

    def status(self, full_name: str, sha: str) -> dict[str, Any]:
        owner, repo = full_name.split("/", 1)
        return self.request("GET", f"/repos/{quote(owner)}/{quote(repo)}/commits/{sha}/status")

    def merge(self, full_name: str, number: int, sha: str, title: str) -> dict[str, Any]:
        owner, repo = full_name.split("/", 1)
        return self.request(
            "PUT",
            f"/repos/{quote(owner)}/{quote(repo)}/pulls/{number}/merge",
            {
                "sha": sha,
                "merge_method": "squash",
                "commit_title": title,
                "commit_message": (
                    "Apply the local SZL Holographic Space Fabric v2 while preserving the "
                    "application's product-specific information architecture and behavior.\n\n"
                    "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                ),
            },
            expected=(200, 405, 409),
        )


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def quote_path(value: str) -> str:
    return urllib.parse.quote(value, safe="/")


def retry_get(url: str, *, attempts: int = 4) -> Any:
    headers = {"User-Agent": "szl-holographic-space-rollout-v2", "Accept": "application/json"}
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == attempts:
                raise RolloutError("PUBLIC_API_FAILED", f"Could not read {url}: {exc}") from exc
            time.sleep(min(2**attempt, 12))
    raise AssertionError("unreachable")


def _retry_delay(headers: Mapping[str, str], attempt: int) -> int:
    retry_after = headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return min(max(int(retry_after), 1), 60)
    reset = headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        return min(max(int(reset) - int(time.time()) + 1, 1), 60)
    return min(2**attempt, 20)


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def simplified(value: str) -> str:
    result = normalize(value)
    for prefix in ("szl-holdings-", "szlholdings-", "szl-", "a11oy-"):
        if result.startswith(prefix):
            result = result[len(prefix) :]
    return result


def list_spaces() -> list[Space]:
    query = urllib.parse.urlencode({"author": "SZLHOLDINGS", "limit": 100, "full": "true"})
    values = retry_get(f"{HF_API}?{query}")
    if not isinstance(values, list):
        raise RolloutError("HF_RESPONSE_INVALID", "Hugging Face Spaces response was not a list")
    spaces: list[Space] = []
    for value in values:
        identity = str(value.get("id") or value.get("name") or "")
        slug = identity.split("/", 1)[-1]
        if not slug:
            continue
        card = value.get("cardData") or {}
        runtime = value.get("runtime") or {}
        spaces.append(
            Space(
                slug=slug,
                sdk=str(card.get("sdk") or value.get("sdk") or "") or None,
                stage=str(runtime.get("stage") or value.get("stage") or "") or None,
                url=f"https://huggingface.co/spaces/SZLHOLDINGS/{slug}",
            )
        )
    return sorted(spaces, key=lambda item: item.slug.lower())


def _canonical_repo(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?:github\.com/)?(szl-holdings/[A-Za-z0-9_.-]+)", value)
    return match.group(1).removesuffix(".git") if match else None


def _space_slug(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return normalize(value.split("/", 1)[-1])


def _local_source_map() -> dict[str, str]:
    if not LOCAL_SOURCE_MAP.is_file():
        return {}
    payload = json.loads(LOCAL_SOURCE_MAP.read_text(encoding="utf-8"))
    if payload.get("schema") != "szl.public-space-source-map/v1":
        raise RolloutError("LOCAL_SOURCE_MAP_SCHEMA_INVALID", str(payload.get("schema")))
    values = payload.get("sources")
    if not isinstance(values, list):
        raise RolloutError("LOCAL_SOURCE_MAP_INVALID", "sources must be a list")
    found: dict[str, str] = {}
    for item in values:
        if not isinstance(item, dict):
            raise RolloutError("LOCAL_SOURCE_MAP_INVALID", "source entries must be objects")
        slug = _space_slug(item.get("space"))
        repo = _canonical_repo(item.get("repo"))
        if not slug or not repo:
            raise RolloutError("LOCAL_SOURCE_MAP_INVALID", json.dumps(item, sort_keys=True))
        if slug in found and found[slug] != repo:
            raise RolloutError("LOCAL_SOURCE_MAP_CONFLICT", slug)
        found[slug] = repo
    return found


def source_map() -> dict[str, str]:
    # The protected local map is authoritative. Provider and a11oy
    # metadata may fill gaps, but can never silently override it.
    found = _local_source_map()
    url = "https://raw.githubusercontent.com/szl-holdings/a11oy/main/docs/huggingface-space-source-map-v1.json"
    try:
        payload = retry_get(url)
    except RolloutError:
        return found
    slug_keys = ("space", "space_id", "hf_space", "slug", "huggingface_space", "id")
    repo_keys = ("source_repo", "repository", "github_repo", "source_repository", "repo", "full_name")

    def direct_repo(value: Mapping[str, Any]) -> str | None:
        for key in repo_keys:
            repo = _canonical_repo(value.get(key))
            if repo:
                return repo
        mapping = value.get("source_mapping")
        if isinstance(mapping, dict):
            canonical = mapping.get("canonical")
            if isinstance(canonical, dict):
                repo = _canonical_repo(canonical.get("full_name") or canonical.get("repository"))
                if repo:
                    return repo
            repo = _canonical_repo(mapping.get("full_name") or mapping.get("repository"))
            if repo:
                return repo
        source = value.get("source")
        if isinstance(source, dict):
            repo = _canonical_repo(source.get("full_name") or source.get("repository") or source.get("repo"))
            if repo:
                return repo
        return None

    def direct_slug(value: Mapping[str, Any]) -> str | None:
        for key in slug_keys:
            candidate = value.get(key)
            if isinstance(candidate, dict):
                candidate = candidate.get("id") or candidate.get("slug") or candidate.get("name")
            slug = _space_slug(candidate)
            if slug and (key != "id" or str(candidate).lower().startswith("szlholdings/")):
                return slug
        return None

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            slug = direct_slug(value)
            repo = direct_repo(value)
            if slug and repo and slug not in found:
                found[slug] = repo
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found

def mapping_score(space: Space, repo: Mapping[str, Any], explicit: Mapping[str, str]) -> tuple[int, str]:
    full_name = str(repo.get("full_name") or "")
    name = str(repo.get("name") or "")
    homepage = str(repo.get("homepage") or "").lower()
    description = str(repo.get("description") or "").lower()
    topics = {normalize(str(item)) for item in repo.get("topics") or []}
    slug = normalize(space.slug)
    if explicit.get(slug) == full_name:
        return 1000, "canonical source map"
    score = 0
    reasons: list[str] = []
    if normalize(name) == slug:
        score += 180
        reasons.append("exact repository/Space slug")
    if simplified(name) == simplified(space.slug):
        score += 100
        reasons.append("normalized repository/Space slug")
    hf_path = f"/spaces/szlholdings/{space.slug.lower()}"
    if hf_path in homepage or space.slug.lower() + ".hf.space" in homepage:
        score += 220
        reasons.append("repository homepage names Space")
    if space.slug.lower() in description:
        score += 35
        reasons.append("description names Space")
    if topics & {"huggingface", "hugging-face", "hf-space", "space", "gradio", "streamlit"}:
        score += 30
        reasons.append("Space frontend topic")
    return score, ", ".join(reasons) or "no confident mapping signal"


def group_mappings(spaces: list[Space], repos: list[dict[str, Any]], explicit: Mapping[str, str]) -> tuple[dict[str, tuple[list[Space], int, str]], list[dict[str, Any]]]:
    active = [repo for repo in repos if not repo.get("archived") and not repo.get("disabled") and not repo.get("fork") and repo.get("name") not in EXCLUDED_REPOS]
    grouped: dict[str, tuple[list[Space], int, str]] = {}
    unmapped: list[dict[str, Any]] = []
    for space in spaces:
        ranked = sorted(((*mapping_score(space, repo, explicit), repo) for repo in active), key=lambda row: row[0], reverse=True)
        if not ranked or ranked[0][0] < 100:
            unmapped.append({"slug": space.slug, "sdk": space.sdk, "stage": space.stage, "reason": "no source repository reached confidence 100"})
            continue
        best_score, best_reason, best_repo = ranked[0]
        if len(ranked) > 1 and best_score < 1000 and best_score - ranked[1][0] < 30:
            unmapped.append({"slug": space.slug, "sdk": space.sdk, "stage": space.stage, "reason": "ambiguous source repository mapping"})
            continue
        full_name = str(best_repo["full_name"])
        current = grouped.get(full_name)
        if current:
            current[0].append(space)
            grouped[full_name] = (current[0], max(current[1], best_score), current[2] + "; " + best_reason)
        else:
            grouped[full_name] = ([space], best_score, best_reason)
    return grouped, unmapped


def insert_before(text: str, token: str, addition: str) -> str:
    index = text.lower().rfind(token.lower())
    if index < 0:
        raise RolloutError("INJECTION_POINT_MISSING", token)
    return text[:index] + addition + text[index:]


def adapt_static(content: str, css_href: str, js_href: str, slug: str) -> str:
    if STYLE_MARKER in content and SCRIPT_MARKER in content:
        return content
    if "</head>" not in content.lower() or "</body>" not in content.lower():
        raise RolloutError("STATIC_SHAPE_UNSUPPORTED", "closing head/body tags are required")
    identity = f'  <meta name="szl-space-slug" content="{slug}" {MARKER} />\n'
    style = f'  <link rel="stylesheet" href="{css_href}" {STYLE_MARKER} />\n'
    script = f'  <script src="{js_href}" defer {SCRIPT_MARKER}></script>\n'
    output = content
    if STYLE_MARKER not in output:
        output = insert_before(output, "</head>", identity + style)
    if SCRIPT_MARKER not in output:
        output = insert_before(output, "</body>", script)
    return output


def adapt_next(content: str, slug: str) -> str:
    if STYLE_MARKER in content and SCRIPT_MARKER in content:
        return content
    style = f'        <link rel="stylesheet" href="/szl-space-hologram.css" {STYLE_MARKER} />\n'
    script = f'        <script src="/szl-space-hologram.js" data-szl-space-slug="{slug}" defer {SCRIPT_MARKER}></script>\n'
    output = content
    if STYLE_MARKER not in output:
        if "</head>" in output.lower():
            output = insert_before(output, "</head>", style)
        else:
            match = re.search(r"<body(?:\s|>)", output, re.IGNORECASE)
            if not match:
                raise RolloutError("NEXT_SHAPE_UNSUPPORTED", "layout has no head or body")
            output = output[: match.start()] + "<head>\n" + style + "      </head>\n      " + output[match.start() :]
    if SCRIPT_MARKER not in output:
        if "</body>" not in output.lower():
            raise RolloutError("NEXT_SHAPE_UNSUPPORTED", "layout has no closing body")
        output = insert_before(output, "</body>", script)
    return output


def line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def node_span(node: ast.AST, offsets: list[int]) -> tuple[int, int]:
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        raise RolloutError("PYTHON_POSITION_MISSING", type(node).__name__)
    return offsets[int(node.lineno) - 1] + int(node.col_offset), offsets[int(node.end_lineno) - 1] + int(node.end_col_offset)


def python_import_offset(module: ast.Module, text: str) -> int:
    body = list(module.body)
    line = 0
    index = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        line = int(getattr(body[0], "end_lineno", body[0].lineno))
        index = 1
    while index < len(body) and isinstance(body[index], ast.ImportFrom) and body[index].module == "__future__":
        line = int(getattr(body[index], "end_lineno", body[index].lineno))
        index += 1
    return sum(len(value) for value in text.splitlines(keepends=True)[:line])


def first_ui_call(module: ast.Module, names: set[str]) -> ast.Call | None:
    calls: list[ast.Call] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in names:
            calls.append(node)
    return min(calls, key=lambda item: (item.lineno, item.col_offset)) if calls else None


def adapt_gradio(content: str) -> str:
    marker = "# SZL Holographic Space Fabric v2"
    if marker in content:
        return content
    try:
        module = ast.parse(content)
    except SyntaxError as exc:
        raise RolloutError("PYTHON_PARSE_FAILED", str(exc)) from exc
    call = first_ui_call(module, {"Blocks", "Interface"})
    if call is None:
        raise RolloutError("GRADIO_CALL_MISSING", "no gr.Blocks or gr.Interface call was found")
    offsets = line_offsets(content)
    edits: list[tuple[int, int, str]] = []
    present = {keyword.arg: keyword for keyword in call.keywords if keyword.arg in {"css", "head"}}
    for name, merger in (("css", "merge_hologram_css"), ("head", "merge_hologram_head")):
        keyword = present.get(name)
        if keyword is not None:
            start, end = node_span(keyword.value, offsets)
            edits.append((start, end, f"{merger}({content[start:end]})"))
    missing = [name for name in ("css", "head") if name not in present]
    if missing:
        _, end = node_span(call, offsets)
        close = end - 1
        if content[close] != ")":
            raise RolloutError("GRADIO_CALL_SHAPE", "call does not end with a parenthesis")
        start, _ = node_span(call, offsets)
        inside = content[start:close]
        comma = "" if inside.rstrip().endswith("(") else (" " if inside.rstrip().endswith(",") else ", ")
        values = {"css": "A11OY_HOLO_CSS", "head": "A11OY_HOLO_HEAD"}
        edits.append((close, close, comma + ", ".join(f"{name}={values[name]}" for name in missing)))
    output = content
    for start, end, replacement in sorted(edits, reverse=True):
        output = output[:start] + replacement + output[end:]
    import_at = python_import_offset(module, content)
    addition = "\n# SZL Holographic Space Fabric v2\nfrom szl_hologram_assets import A11OY_HOLO_CSS, A11OY_HOLO_HEAD, merge_hologram_css, merge_hologram_head\n"
    output = output[:import_at] + addition + output[import_at:]
    compile(output, "app.py", "exec")
    return output


def gradio_helper() -> str:
    return '''"""Local assets for SZL Holographic Space Fabric v2."""\nfrom pathlib import Path\n\n_ROOT = Path(__file__).resolve().parent\nA11OY_HOLO_CSS = (_ROOT / "szl-space-hologram.css").read_text(encoding="utf-8")\n_script = (_ROOT / "szl-space-hologram.js").read_text(encoding="utf-8")\nA11OY_HOLO_HEAD = '<script data-szl-space-holo-v2="inline">' + _script.replace("</script>", "<\\/script>") + "</script>"\n\ndef merge_hologram_css(value):\n    return f"{value or ''}\\n{A11OY_HOLO_CSS}"\n\ndef merge_hologram_head(value):\n    return f"{value or ''}\\n{A11OY_HOLO_HEAD}"\n'''


def adapt_streamlit(content: str, slug: str) -> str:
    marker = "# SZL Holographic Space Fabric v2"
    if marker in content:
        return content
    try:
        module = ast.parse(content)
    except SyntaxError as exc:
        raise RolloutError("PYTHON_PARSE_FAILED", str(exc)) from exc
    import_at = python_import_offset(module, content)
    addition = "\n# SZL Holographic Space Fabric v2\nfrom szl_hologram_streamlit import render_szl_hologram\n"
    output = content[:import_at] + addition + content[import_at:]
    try:
        patched = ast.parse(output)
    except SyntaxError as exc:
        raise RolloutError("STREAMLIT_IMPORT_FAILED", str(exc)) from exc
    offsets = line_offsets(output)
    calls = [node for node in ast.walk(patched) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "set_page_config"]
    if calls:
        _, insert_at = node_span(min(calls, key=lambda item: item.lineno), offsets)
    else:
        insert_at = python_import_offset(patched, output)
    output = output[:insert_at] + f"\nrender_szl_hologram({slug!r})\n" + output[insert_at:]
    compile(output, "app.py", "exec")
    return output


def streamlit_helper() -> str:
    return '''"""CSS-only Streamlit adapter for SZL Holographic Space Fabric v2."""\nfrom __future__ import annotations\n\nimport hashlib\nimport html\nfrom pathlib import Path\nimport streamlit as st\n\n_ROOT = Path(__file__).resolve().parent\n_CSS = (_ROOT / "szl-space-hologram.css").read_text(encoding="utf-8")\n_PALETTES = [\n    ("#07131a", "#102633", "#f2fbff", "#9ab4c2", "#64dcff", "#a88bff"),\n    ("#130a10", "#291522", "#fff6fb", "#c2a2b3", "#ff7bc3", "#ffb56b"),\n    ("#07140d", "#12281a", "#f5fff7", "#9db8a4", "#72efa0", "#5ad6ff"),\n    ("#130e06", "#2a1d0e", "#fffaf0", "#c2b297", "#ffc66d", "#ff7d73"),\n    ("#090a18", "#171932", "#f6f6ff", "#a6a8c4", "#878cff", "#54e4d7"),\n]\n_MOTIFS = ("command-grid", "signal-aurora", "bathymetric-radar", "parcel-topography", "threat-lattice", "case-lines", "editorial-orbit", "graph-mesh", "build-circuit", "recursive-weave", "agent-swarm", "cell-membrane", "checksum-ledger")\n\ndef render_szl_hologram(slug: str) -> None:\n    seed = int.from_bytes(hashlib.sha256(slug.encode("utf-8")).digest()[:4], "big")\n    background, surface, foreground, muted, accent, accent2 = _PALETTES[seed % len(_PALETTES)]\n    motif = _MOTIFS[(seed >> 8) % len(_MOTIFS)]\n    label = " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part)\n    variables = f":root{{--szl-space-bg:{background};--szl-space-surface:{surface};--szl-space-fg:{foreground};--szl-space-muted:{muted};--szl-space-accent:{accent};--szl-space-accent-2:{accent2};}}"\n    markup = f"""<style>{_CSS}{variables}</style><div id="szl-space-holo-v2-ambient" aria-hidden="true"><span class="szl-space-field"></span><span class="szl-space-orbit"></span><span class="szl-space-beam"></span><span class="szl-space-scan"></span><span class="szl-space-nodes"></span></div><nav style="position:relative;z-index:2147483000;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;margin:0 0 12px;border:1px solid var(--szl-space-line);border-radius:14px;background:color-mix(in srgb,var(--szl-space-bg) 88%,transparent);backdrop-filter:blur(16px)" aria-label="SZL ecosystem"><strong>{html.escape(label)}</strong><span style="display:flex;gap:10px;flex-wrap:wrap"><a href="https://a-11-oy.com">Command</a><a href="https://a11oy.net">Proof</a><a href="https://huggingface.co/SZLHOLDINGS">Spaces</a><a href="https://github.com/szl-holdings">Source</a></span></nav><script>document.documentElement.dataset.szlSpaceHoloV2='true';document.documentElement.dataset.szlSpaceMotif={motif!r};document.documentElement.dataset.szlSpaceSlug={slug!r};</script>"""\n    st.markdown(markup, unsafe_allow_html=True)\n'''


def read_assets(root: Path) -> tuple[str, str, str]:
    css = (root / "szl-space-hologram.css").read_text(encoding="utf-8")
    javascript = (root / "szl-space-hologram.js").read_text(encoding="utf-8")
    registry = (root / "theme-registry.json").read_text(encoding="utf-8")
    parsed = json.loads(registry)
    if parsed.get("schema") != "szl.holographic-space-theme-registry/v2":
        raise RolloutError("REGISTRY_SCHEMA_INVALID", "unsupported registry")
    for prohibited in ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage", "document.cookie"):
        if prohibited in javascript:
            raise RolloutError("CLIENT_BEHAVIOR_PROHIBITED", prohibited)
    for required in ("prefers-reduced-motion", "prefers-contrast", "forced-colors", "@media print"):
        if required not in css:
            raise RolloutError("ACCESSIBILITY_CONTRACT_MISSING", required)
    return css, javascript, registry


def plan_repository(github: GitHub, repo: Mapping[str, Any], spaces: list[Space], score: int, reason: str, css: str, javascript: str) -> Plan:
    full_name = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    plan = Plan(full_name, default_branch, spaces, score, reason)
    blobs = github.tree(full_name, default_branch)
    paths = {str(item.get("path")) for item in blobs}
    primary_slug = spaces[0].slug

    if full_name == "szl-holdings/platform":
        changes: list[Change] = []
        entrypoints: list[str] = []
        for space in spaces:
            root = MONOREPO_STATIC_ROOTS.get(normalize(space.slug))
            if not root:
                continue
            index_path = f"{root}/index.html"
            package_path = f"{root}/package.json"
            public_prefix = f"{root}/public/"
            if index_path not in paths or package_path not in paths or not any(path.startswith(public_prefix) for path in paths):
                plan.status = "report-only"
                plan.error = {
                    "code": "MONOREPO_FRONTEND_SHAPE_INVALID",
                    "message": f"{space.slug} is mapped to {root}, but its Vite index/package/public shape is incomplete.",
                }
                return plan
            content, _ = github.file(full_name, index_path, default_branch)
            patched = adapt_static(
                content,
                "/szl-space-hologram.css",
                "/szl-space-hologram.js",
                space.slug,
            )
            css_path = f"{root}/public/szl-space-hologram.css"
            js_path = f"{root}/public/szl-space-hologram.js"
            entrypoints.append(index_path)
            if patched != content:
                changes.extend(
                    [
                        Change(css_path, css),
                        Change(js_path, javascript),
                        Change(index_path, patched),
                    ]
                )
            elif css_path not in paths or js_path not in paths:
                plan.status = "report-only"
                plan.error = {
                    "code": "MONOREPO_ASSET_BINDING_INCOMPLETE",
                    "message": f"{space.slug} declares Holo markers without both public assets.",
                }
                return plan
        if entrypoints:
            plan.adapter = "monorepo-static"
            plan.entrypoint = ", ".join(entrypoints)
            if changes:
                deduped = {change.path: change for change in changes}
                plan.changes = list(deduped.values())
            else:
                plan.status = "already-integrated"
            return plan

    for path in NEXT_LAYOUTS:
        if path in paths:
            content, _ = github.file(full_name, path, default_branch)
            patched = adapt_next(content, primary_slug)
            if patched == content:
                plan.status = "already-integrated"
                return plan
            plan.adapter = "next"
            plan.entrypoint = path
            plan.changes = [
                Change("public/szl-space-hologram.css", css),
                Change("public/szl-space-hologram.js", javascript),
                Change(path, patched),
            ]
            return plan

    for path in STATIC_INDEXES:
        if path in paths:
            content, _ = github.file(full_name, path, default_branch)
            is_vite_root = path == "index.html" and "package.json" in paths and any(value.startswith("public/") for value in paths)
            if is_vite_root:
                css_path = "public/szl-space-hologram.css"
                js_path = "public/szl-space-hologram.js"
                css_href = "/szl-space-hologram.css"
                js_href = "/szl-space-hologram.js"
            else:
                parent = str(Path(path).parent).replace(".", "").strip("/")
                prefix = f"{parent}/" if parent else ""
                css_path = prefix + "szl-space-hologram.css"
                js_path = prefix + "szl-space-hologram.js"
                css_href = "./szl-space-hologram.css"
                js_href = "./szl-space-hologram.js"
            patched = adapt_static(content, css_href, js_href, primary_slug)
            if patched == content:
                plan.status = "already-integrated"
                return plan
            plan.adapter = "static"
            plan.entrypoint = path
            plan.changes = [Change(css_path, css), Change(js_path, javascript), Change(path, patched)]
            return plan

    for path in PYTHON_ENTRIES:
        if path not in paths:
            continue
        content, _ = github.file(full_name, path, default_branch)
        lower = content.lower()
        parent = str(Path(path).parent).replace(".", "").strip("/")
        prefix = f"{parent}/" if parent else ""
        if "gradio" in lower or "gr." in content:
            patched = adapt_gradio(content)
            if patched == content:
                plan.status = "already-integrated"
                return plan
            plan.adapter = "gradio"
            plan.entrypoint = path
            plan.changes = [
                Change(prefix + "szl-space-hologram.css", css),
                Change(prefix + "szl-space-hologram.js", javascript),
                Change(prefix + "szl_hologram_assets.py", gradio_helper()),
                Change(path, patched),
            ]
            return plan
        if "streamlit" in lower or re.search(r"\bst\.", content):
            patched = adapt_streamlit(content, primary_slug)
            if patched == content:
                plan.status = "already-integrated"
                return plan
            plan.adapter = "streamlit"
            plan.entrypoint = path
            plan.changes = [
                Change(prefix + "szl-space-hologram.css", css),
                Change(prefix + "szl_hologram_streamlit.py", streamlit_helper()),
                Change(path, patched),
            ]
            return plan

    plan.status = "report-only"
    plan.error = {
        "code": "NO_HIGH_CONFIDENCE_ADAPTER",
        "message": "Space source was mapped, but no safe static, Next.js, Gradio, or Streamlit entrypoint matched.",
    }
    return plan


def pr_body(plan: Plan, digest: str) -> str:
    spaces = "\n".join(f"- [{space.slug}]({space.url}) — SDK `{space.sdk or 'unknown'}`, runtime `{space.stage or 'unknown'}`" for space in plan.spaces)
    files = "\n".join(f"- `{change.path}`" for change in plan.changes)
    return f"""## SZL Holographic Space Fabric v2

This source repository is receiving the shared SZL navigation, accessibility,
and spatial rendering mechanics while retaining its own product information
architecture, workflows, copy, data, and application behavior.

### Spaces served by this source

{spaces}

### Identity

- adapter: `{plan.adapter}`
- entrypoint: `{plan.entrypoint}`
- source mapping: `{plan.mapping_reason}`
- asset digest: `{digest}`
- visual identity: derived from the public Space slug; curated for named SZL
  products and deterministic for every other slug, so deployments never
  reshuffle identity.

### Files

{files}

### Contract

- local assets only; no CDN, analytics, runtime fetch, cookies, or storage;
- shared Command → Proof → Spaces → Source flow;
- unique geometry and palette per Space rather than one cloned skin;
- keyboard focus, mobile navigation, reduced motion, high contrast, forced
  colors, low-power mode, visibility pausing, and print behavior;
- no direct default-branch write, force push, protection change, secret output,
  or deployment claim.

This PR must pass the repository's own checks. The central controller only
squash-merges through the normal API after all reported checks complete green;
repositories without checks remain open for explicit review.

Generated by `{SCHEMA}`.
"""


def apply_plan(github: GitHub, org: str, plan: Plan, digest: str) -> None:
    if plan.status != "planned":
        return
    open_pull = github.open_pull(plan.repository, org, BRANCH)
    exists = github.ref_exists(plan.repository, BRANCH)
    if exists and not open_pull:
        raise RolloutError("STALE_REVIEW_BRANCH", f"{plan.repository}:{BRANCH} exists without an open PR")
    if not exists:
        github.create_branch(plan.repository, BRANCH, github.ref_sha(plan.repository, plan.default_branch))
    for index, change in enumerate(plan.changes, start=1):
        github.write_file(
            plan.repository,
            BRANCH,
            change,
            (
                f"feat(frontend): apply SZL holographic fabric v2 ({index}/{len(plan.changes)})\n\n"
                "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
            ),
        )
    pull = open_pull or github.create_pull(
        plan.repository,
        BRANCH,
        plan.default_branch,
        "feat(frontend): join SZL Holographic Space Fabric v2",
        pr_body(plan, digest),
    )
    plan.status = "pr-updated" if open_pull else "pr-created"
    plan.branch = BRANCH
    plan.pull_number = int(pull["number"])
    plan.pull_request = str(pull["html_url"])


def wait_and_merge(github: GitHub, plan: Plan, wait_seconds: int) -> None:
    if not plan.pull_number:
        return
    started = time.monotonic()
    first_checks_at: float | None = None
    while time.monotonic() - started < wait_seconds:
        pull = github.pull(plan.repository, plan.pull_number)
        if pull.get("merged"):
            plan.status = "merged"
            plan.merge_commit = str(pull.get("merge_commit_sha") or "") or None
            return
        if pull.get("state") != "open":
            plan.status = "closed-unmerged"
            return
        sha = str((pull.get("head") or {}).get("sha") or "")
        if not sha:
            raise RolloutError("PULL_HEAD_MISSING", plan.repository)
        checks = github.checks(plan.repository, sha)
        if checks and first_checks_at is None:
            first_checks_at = time.monotonic()
        failed = [row for row in checks if row.get("status") == "completed" and row.get("conclusion") not in ALLOWED_CHECK_CONCLUSIONS]
        if failed:
            plan.status = "checks-failed"
            plan.error = {
                "code": "CHECKS_FAILED",
                "message": "One or more repository checks failed.",
                "details": [{"name": row.get("name"), "conclusion": row.get("conclusion"), "url": row.get("html_url")} for row in failed],
            }
            return
        pending = [row for row in checks if row.get("status") != "completed"]
        legacy = github.status(plan.repository, sha)
        if any(row.get("state") in {"error", "failure"} for row in legacy.get("statuses", [])):
            plan.status = "checks-failed"
            plan.error = {"code": "LEGACY_STATUS_FAILED", "message": "A legacy commit status failed."}
            return
        if checks and not pending and legacy.get("state") != "pending":
            result = github.merge(
                plan.repository,
                plan.pull_number,
                sha,
                f"feat(frontend): join SZL Holographic Space Fabric v2 (#{plan.pull_number})",
            )
            if result.get("merged"):
                plan.status = "merged"
                plan.merge_commit = str(result.get("sha") or "") or None
            else:
                plan.status = "merge-blocked"
                plan.error = {"code": "MERGE_REJECTED", "message": str(result.get("message") or "GitHub rejected merge")}
            return
        if not checks and time.monotonic() - started > min(180, wait_seconds):
            plan.status = "review-required-no-checks"
            return
        time.sleep(15)
    plan.status = "checks-pending"


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="szl-holdings")
    parser.add_argument("--assets-root", type=Path, default=ASSETS_ROOT)
    parser.add_argument("--report", type=Path, default=Path("reports/holographic-space-rollout-v2.json"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--merge-green", action="store_true")
    parser.add_argument("--merge-wait-seconds", type=int, default=1800)
    parser.add_argument("--max-repos", type=int, default=100)
    parser.add_argument("--repo-filter", default="")
    parser.add_argument("--token-env", default="SZL_GITHUB_TOKEN")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get(args.token_env, "")
    if args.apply and not token:
        raise RolloutError("WRITE_TOKEN_MISSING", f"Apply mode requires {args.token_env}")
    css, javascript, registry = read_assets(args.assets_root)
    digest = hashlib.sha256((css + "\0" + javascript + "\0" + registry).encode("utf-8")).hexdigest()
    github = GitHub(token)
    spaces = list_spaces()
    repositories = github.repositories(args.org)
    explicit = source_map()
    grouped, unmapped = group_mappings(spaces, repositories, explicit)
    repo_by_name = {str(repo["full_name"]): repo for repo in repositories}
    pattern = re.compile(args.repo_filter, re.IGNORECASE) if args.repo_filter else None
    plans: list[Plan] = []

    for full_name, (mapped_spaces, score, reason) in sorted(grouped.items()):
        if pattern and not pattern.search(full_name):
            continue
        if len(plans) >= max(1, args.max_repos):
            break
        try:
            plans.append(plan_repository(github, repo_by_name[full_name], mapped_spaces, score, reason, css, javascript))
        except RolloutError as exc:
            plans.append(
                Plan(
                    repository=full_name,
                    default_branch=str(repo_by_name[full_name].get("default_branch") or "main"),
                    spaces=mapped_spaces,
                    mapping_score=score,
                    mapping_reason=reason,
                    status="blocked",
                    error=exc.as_dict(),
                )
            )

    if args.apply:
        for plan in plans:
            try:
                apply_plan(github, args.org, plan, digest)
            except RolloutError as exc:
                plan.status = "blocked"
                plan.error = exc.as_dict()

    if args.apply and args.merge_green:
        mergeable = [plan for plan in plans if plan.pull_number]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, max(1, len(mergeable)))) as pool:
            futures = {pool.submit(wait_and_merge, github, plan, max(60, args.merge_wait_seconds)): plan for plan in mergeable}
            for future, plan in [(future, futures[future]) for future in concurrent.futures.as_completed(futures)]:
                try:
                    future.result()
                except RolloutError as exc:
                    plan.status = "blocked"
                    plan.error = exc.as_dict()
                except Exception as exc:  # defensive isolation per repository
                    plan.status = "blocked"
                    plan.error = {"code": "UNEXPECTED_ERROR", "message": str(exc)}

    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "organization": args.org,
        "mode": "apply" if args.apply else "dry-run",
        "merge_green": bool(args.merge_green),
        "asset_digest": digest,
        "branch": BRANCH,
        "summary": {
            "github_repositories": len(repositories),
            "public_spaces": len(spaces),
            "source_repositories_mapped": len(grouped),
            "source_repositories_planned": len(plans),
            "unmapped_spaces": len(unmapped),
            **counts,
        },
        "unmapped_spaces": unmapped,
        "repositories": [plan.as_dict() for plan in plans],
        "secrets_recorded": False,
        "default_branch_writes": False,
        "force_pushes": False,
        "protection_changes": False,
        "direct_huggingface_writes": False,
    }
    write_report(args.report, report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print(json.dumps({"status": "blocked", "error": exc.as_dict()}, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
