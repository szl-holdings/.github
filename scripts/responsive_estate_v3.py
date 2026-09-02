#!/usr/bin/env python3
"""Plan, apply, and optionally merge the SZL Space Responsive v3 rollout.

The controller is source-first. It inventories every public SZLHOLDINGS Space,
resolves its GitHub source using the committed A11oy source map, Space README
links, and exact-name fallbacks, then patches only repositories that already
carry the reviewed SZL holographic stylesheet. It never guesses an arbitrary
application entrypoint and never writes directly to Hugging Face.
"""
from __future__ import annotations

import argparse
import base64
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
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"
SOURCE_MAP_URL = "https://raw.githubusercontent.com/szl-holdings/a11oy/main/docs/huggingface-space-source-map-v1.json"
ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "szl-space-responsive-v3.css"
BRANCH_PREFIX = "design/responsive-experience-v3"
MARKER = "szl-space-responsive-v3"
HOST_NAMES = (
    "szl-holo-v2.css",
    "szl-hologram-v2.css",
    "szl-space-holo-v2.css",
    "szl-spectral-v2.css",
    "szl-holo-proof-v2.css",
)
EXCLUDED_REPOS = {".github", "a11oy", "a11oy-net", "szl-holdings.github.io"}
PASSING = {"success", "neutral", "skipped"}
FAILING = {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"}


class RolloutError(RuntimeError):
    pass


@dataclass
class Space:
    slug: str
    repo_id: str
    sdk: str | None = None
    stage: str | None = None
    sha: str | None = None
    source_repo: str | None = None
    source_method: str | None = None


@dataclass
class RepoPlan:
    repo: str
    spaces: list[str] = field(default_factory=list)
    default_branch: str | None = None
    base_sha: str | None = None
    host_path: str | None = None
    responsive_path: str | None = None
    status: str = "PLANNED"
    detail: str | None = None
    branch: str | None = None
    head_sha: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    merged: bool = False
    merge_sha: str | None = None


class Http:
    def __init__(self, token: str | None = None) -> None:
        self.token = (token or "").strip()

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: Any | None = None,
        accept: str = "application/vnd.github+json",
        timeout: int = 45,
        allow_404: bool = False,
    ) -> tuple[int, bytes, dict[str, str]]:
        headers = {
            "Accept": accept,
            "User-Agent": "szl-responsive-estate-v3/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            data = exc.read()
            if allow_404 and exc.code == 404:
                return exc.code, data, {k.lower(): v for k, v in exc.headers.items()}
            message = data.decode("utf-8", "replace")[:4000]
            raise RolloutError(f"{method} {url} -> HTTP {exc.code}: {message}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RolloutError(f"{method} {url} failed: {exc}") from exc

    def json(self, method: str, url: str, **kwargs: Any) -> Any:
        status, body, _ = self.request(method, url, **kwargs)
        if status == 404 and kwargs.get("allow_404"):
            return None
        try:
            return json.loads(body.decode("utf-8")) if body else None
        except json.JSONDecodeError as exc:
            raise RolloutError(f"non-JSON response from {url}") from exc


def get_json_public(url: str) -> Any:
    return Http().json("GET", url)


def get_text_public(url: str, *, allow_404: bool = False) -> str | None:
    status, body, _ = Http().request("GET", url, accept="text/plain", allow_404=allow_404)
    if status == 404:
        return None
    return body.decode("utf-8", "replace")


def inventory_spaces() -> list[Space]:
    query = urllib.parse.urlencode({"author": HF_ORG, "limit": 100, "full": "true"})
    payload = get_json_public(f"{HF_API}/spaces?{query}")
    if not isinstance(payload, list):
        raise RolloutError("Hugging Face public Space inventory was not a list")
    rows: list[Space] = []
    for item in payload:
        repo_id = str(item.get("id") or "")
        if "/" not in repo_id:
            continue
        slug = repo_id.split("/", 1)[1]
        runtime = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
        rows.append(
            Space(
                slug=slug,
                repo_id=repo_id,
                sdk=item.get("sdk"),
                stage=runtime.get("stage"),
                sha=item.get("sha"),
            )
        )
    return sorted(rows, key=lambda row: row.slug.lower())


def strings_in(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings_in(child)


def source_map_pairs() -> dict[str, str]:
    try:
        payload = get_json_public(SOURCE_MAP_URL)
    except RolloutError:
        return {}
    pairs: dict[str, str] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            values = list(strings_in(value))
            spaces: set[str] = set()
            repos: set[str] = set()
            for text in values:
                for match in re.finditer(r"(?:SZLHOLDINGS/|huggingface\.co/spaces/SZLHOLDINGS/)([A-Za-z0-9._-]+)", text, re.I):
                    spaces.add(match.group(1))
                for match in re.finditer(r"(?:github\.com/)?szl-holdings/([A-Za-z0-9._-]+)", text, re.I):
                    repos.add(match.group(1))
            if len(spaces) == 1 and len(repos) == 1:
                pairs[next(iter(spaces)).lower()] = next(iter(repos))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return pairs


def github_repo_exists(http: Http, repo: str) -> bool:
    value = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{repo}", allow_404=True)
    return isinstance(value, dict)


def source_from_space_readme(space: Space) -> str | None:
    url = f"https://huggingface.co/spaces/{urllib.parse.quote(space.repo_id, safe='/')}/resolve/main/README.md"
    try:
        text = get_text_public(url, allow_404=True)
    except RolloutError:
        return None
    if not text:
        return None
    matches = re.findall(r"(?:https?://)?github\.com/szl-holdings/([A-Za-z0-9._-]+)", text, re.I)
    unique = {match.rstrip("./") for match in matches}
    return next(iter(unique)) if len(unique) == 1 else None


def resolve_sources(spaces: list[Space], http: Http) -> None:
    committed = source_map_pairs()
    existence_cache: dict[str, bool] = {}

    def exists(repo: str) -> bool:
        if repo not in existence_cache:
            existence_cache[repo] = github_repo_exists(http, repo)
        return existence_cache[repo]

    for space in spaces:
        mapped = committed.get(space.slug.lower())
        if mapped and exists(mapped):
            space.source_repo = mapped
            space.source_method = "committed-source-map"
            continue
        readme = source_from_space_readme(space)
        if readme and exists(readme):
            space.source_repo = readme
            space.source_method = "space-readme"
            continue
        candidates = [
            space.slug,
            space.slug.lower(),
            space.slug.replace("_", "-"),
            space.slug.lower().replace("_", "-"),
        ]
        for candidate in dict.fromkeys(candidates):
            if exists(candidate):
                space.source_repo = candidate
                space.source_method = "exact-name"
                break


def repo_details(http: Http, repo: str) -> dict[str, Any]:
    value = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{repo}")
    if not isinstance(value, dict):
        raise RolloutError(f"repository metadata unavailable for {repo}")
    return value


def recursive_tree(http: Http, repo: str, sha: str) -> list[dict[str, Any]]:
    value = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{repo}/git/trees/{sha}?recursive=1")
    if not isinstance(value, dict) or not isinstance(value.get("tree"), list):
        raise RolloutError(f"recursive tree unavailable for {repo}@{sha}")
    if value.get("truncated"):
        raise RolloutError(f"recursive tree is truncated for {repo}; refusing an incomplete patch")
    return value["tree"]


def fetch_blob_text(http: Http, repo: str, blob_sha: str) -> str:
    value = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{repo}/git/blobs/{blob_sha}")
    if not isinstance(value, dict) or value.get("encoding") != "base64":
        raise RolloutError(f"blob {blob_sha} in {repo} is not base64 text")
    return base64.b64decode(str(value.get("content") or "")).decode("utf-8")


def pick_host(tree: list[dict[str, Any]]) -> tuple[str, str] | None:
    candidates: list[tuple[int, str, str]] = []
    priority = {name: index for index, name in enumerate(HOST_NAMES)}
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        name = PurePosixPath(path).name
        if name in priority:
            candidates.append((priority[name], path.count("/"), path))
    if not candidates:
        return None
    _, _, path = sorted(candidates)[0]
    blob_sha = next(str(item["sha"]) for item in tree if item.get("path") == path)
    return path, blob_sha


def create_blob(http: Http, repo: str, content: str) -> str:
    value = http.json(
        "POST",
        f"{GITHUB_API}/repos/{ORG}/{repo}/git/blobs",
        payload={"content": content, "encoding": "utf-8"},
    )
    return str(value["sha"])


def create_commit_for_plan(http: Http, plan: RepoPlan, asset: str, run_id: str) -> None:
    assert plan.default_branch and plan.base_sha and plan.host_path
    tree = recursive_tree(http, plan.repo, plan.base_sha)
    host_item = next(item for item in tree if item.get("path") == plan.host_path)
    host = fetch_blob_text(http, plan.repo, str(host_item["sha"]))
    import_line = f'@import url("./szl-responsive-v3.css"); /* {MARKER} */'
    host_lines = [line for line in host.splitlines() if MARKER not in line]
    updated_host = import_line + "\n" + "\n".join(host_lines).lstrip("\n")
    if not updated_host.endswith("\n"):
        updated_host += "\n"

    directory = str(PurePosixPath(plan.host_path).parent)
    responsive_path = "szl-responsive-v3.css" if directory == "." else f"{directory}/szl-responsive-v3.css"
    plan.responsive_path = responsive_path
    contract_path = ".szl/responsive-experience-v3.json"
    contract = {
        "schema": "szl.space-responsive-experience/v3",
        "source_repository": f"{ORG}/{plan.repo}",
        "spaces": sorted(plan.spaces),
        "host_stylesheet": plan.host_path,
        "responsive_stylesheet": responsive_path,
        "viewports": [[320, 568], [375, 812], [430, 932], [812, 375], [768, 1024], [1440, 900], [1920, 1080], [2560, 1440], [3440, 1440]],
        "requirements": {
            "horizontal_overflow_px": 0,
            "minimum_touch_target_px": 44,
            "minimum_touch_target_coarse_px": 48,
            "keyboard_focus_visible": True,
            "safe_area_aware": True,
            "reduced_motion": True,
            "increased_contrast": True,
            "forced_colors": True,
            "print_mode": True,
            "external_runtime_dependencies": 0,
        },
        "controller_run": run_id,
    }
    blobs = {
        plan.host_path: create_blob(http, plan.repo, updated_host),
        responsive_path: create_blob(http, plan.repo, asset),
        contract_path: create_blob(http, plan.repo, json.dumps(contract, indent=2, sort_keys=True) + "\n"),
    }
    entries = [{"path": path, "mode": "100644", "type": "blob", "sha": sha} for path, sha in blobs.items()]
    new_tree = http.json(
        "POST",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/git/trees",
        payload={"base_tree": plan.base_sha, "tree": entries},
    )
    message = (
        "feat(frontend): adopt SZL responsive experience v3\n\n"
        "Add the local mobile-to-theatre layout contract and bind it through the existing "
        "SZL holographic stylesheet without replacing the application-specific visual identity.\n\n"
        "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
    )
    commit = http.json(
        "POST",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/git/commits",
        payload={"message": message, "tree": new_tree["sha"], "parents": [plan.base_sha]},
    )
    plan.head_sha = str(commit["sha"])
    branch_suffix = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-") or str(int(time.time()))
    plan.branch = f"{BRANCH_PREFIX}-{branch_suffix}"
    http.json(
        "POST",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/git/refs",
        payload={"ref": f"refs/heads/{plan.branch}", "sha": plan.head_sha},
    )


def open_pr(http: Http, plan: RepoPlan) -> None:
    assert plan.branch and plan.head_sha and plan.host_path and plan.responsive_path
    body = f"""## Outcome

Adopt the organization-wide SZL Responsive Experience v3 contract for the Hugging Face Space source repository **without flattening this application into a generic template**.

### Spaces

{chr(10).join(f'- `{space}`' for space in sorted(plan.spaces))}

### Exact source patch

- add local `{plan.responsive_path}`;
- bind it once through existing `{plan.host_path}`;
- add `.szl/responsive-experience-v3.json` with the exact viewport and accessibility contract.

### Contract

- 320px compact phone, modern and large phone, phone landscape, tablet, desktop, Full HD, 2560px theatre, and 3440px ultrawide;
- zero horizontal overflow;
- 44px minimum controls and 48px on coarse pointers;
- visible keyboard focus, safe areas, reduced motion, increased contrast, forced colors, and print;
- responsive tables, code, media, dialogs, Gradio, and Streamlit layouts;
- local CSS only; no analytics, cookies, storage, CDN, external font, runtime fetch, or claimed telemetry.

### Boundary

The Space keeps its own palette, motif, information architecture, routes, business logic, and deployment workflow. No model, dataset, receipt, signer, policy, secret, visibility, hardware, or branch-protection setting changes.

Generated by `szl.responsive-estate/v3`.
"""
    value = http.json(
        "POST",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/pulls",
        payload={
            "title": "feat(frontend): adopt SZL responsive experience v3",
            "head": plan.branch,
            "base": plan.default_branch,
            "body": body,
            "maintainer_can_modify": True,
            "draft": False,
        },
    )
    plan.pr_number = int(value["number"])
    plan.pr_url = str(value.get("html_url") or "")
    plan.status = "PR_OPEN"


def check_state(http: Http, plan: RepoPlan) -> tuple[str, str]:
    assert plan.head_sha and plan.pr_number
    pr = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{plan.repo}/pulls/{plan.pr_number}")
    if pr.get("merged"):
        return "MERGED", "already merged"
    if pr.get("mergeable") is False:
        return "BLOCKED", str(pr.get("mergeable_state") or "not mergeable")

    check_runs = http.json(
        "GET",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/commits/{plan.head_sha}/check-runs?per_page=100",
    )
    rows = check_runs.get("check_runs") if isinstance(check_runs, dict) else []
    pending = [row for row in rows if row.get("status") != "completed"]
    failed = [row for row in rows if row.get("status") == "completed" and row.get("conclusion") not in PASSING]
    if failed:
        return "FAILED", ", ".join(f"{row.get('name')}={row.get('conclusion')}" for row in failed)
    if pending:
        return "PENDING", ", ".join(str(row.get("name")) for row in pending)

    statuses = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{plan.repo}/commits/{plan.head_sha}/status")
    state = str((statuses or {}).get("state") or "pending")
    if state == "failure" or state == "error":
        return "FAILED", f"combined commit status={state}"
    if state == "pending" and rows:
        return "PENDING", "combined commit status pending"
    return "GREEN", f"{len(rows)} completed check run(s), combined status={state}"


def merge_pr(http: Http, plan: RepoPlan) -> None:
    assert plan.pr_number and plan.head_sha
    value = http.json(
        "PUT",
        f"{GITHUB_API}/repos/{ORG}/{plan.repo}/pulls/{plan.pr_number}/merge",
        payload={
            "commit_title": "feat(frontend): adopt SZL responsive experience v3",
            "commit_message": (
                "Merge the local mobile-to-theatre contract through the existing Space-specific "
                "holographic stylesheet.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
            ),
            "sha": plan.head_sha,
            "merge_method": "squash",
        },
    )
    if not value.get("merged"):
        raise RolloutError(f"merge rejected for {plan.repo}#{plan.pr_number}: {value.get('message')}")
    plan.merged = True
    plan.merge_sha = str(value.get("sha") or "")
    plan.status = "MERGED"


def merge_green(http: Http, plans: list[RepoPlan], wait_seconds: int) -> None:
    active = [plan for plan in plans if plan.pr_number and not plan.merged]
    deadline = time.monotonic() + max(0, wait_seconds)
    first_seen: dict[str, float] = {plan.repo: time.monotonic() for plan in active}
    while active:
        next_active: list[RepoPlan] = []
        for plan in active:
            try:
                state, detail = check_state(http, plan)
                plan.detail = detail
                if state == "MERGED":
                    plan.merged = True
                    plan.status = "MERGED"
                elif state == "GREEN":
                    merge_pr(http, plan)
                elif state == "FAILED":
                    plan.status = "CHECKS_FAILED"
                elif state == "BLOCKED":
                    plan.status = "MERGE_BLOCKED"
                else:
                    plan.status = "CHECKS_PENDING"
                    next_active.append(plan)
            except RolloutError as exc:
                plan.status = "MERGE_ERROR"
                plan.detail = str(exc)
        active = next_active
        if not active or time.monotonic() >= deadline:
            break
        time.sleep(20)
    for plan in active:
        plan.status = "CHECKS_PENDING"
        plan.detail = f"checks did not complete within {wait_seconds}s"


def build_plans(spaces: list[Space], http: Http) -> list[RepoPlan]:
    grouped: dict[str, RepoPlan] = {}
    for space in spaces:
        if not space.source_repo or space.source_repo in EXCLUDED_REPOS:
            continue
        plan = grouped.setdefault(space.source_repo, RepoPlan(repo=space.source_repo))
        plan.spaces.append(space.repo_id)

    plans = list(grouped.values())
    for plan in plans:
        try:
            details = repo_details(http, plan.repo)
            if details.get("archived"):
                plan.status = "SKIPPED_ARCHIVED"
                continue
            plan.default_branch = str(details.get("default_branch") or "main")
            ref = http.json("GET", f"{GITHUB_API}/repos/{ORG}/{plan.repo}/git/ref/heads/{urllib.parse.quote(plan.default_branch, safe='')}")
            plan.base_sha = str(ref["object"]["sha"])
            tree = recursive_tree(http, plan.repo, plan.base_sha)
            picked = pick_host(tree)
            if not picked:
                plan.status = "NO_REVIEWED_HOLOGRAPHIC_HOST"
                plan.detail = "No known SZL holographic stylesheet exists; refusing a blind entrypoint edit."
                continue
            plan.host_path = picked[0]
            plan.status = "READY"
        except RolloutError as exc:
            plan.status = "PLAN_ERROR"
            plan.detail = str(exc)
    return sorted(plans, key=lambda plan: plan.repo.lower())


def serialize(spaces: list[Space], plans: list[RepoPlan], mode: str) -> dict[str, Any]:
    return {
        "schema": "szl.responsive-estate/v3",
        "mode": mode,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hf_space_count": len(spaces),
        "mapped_space_count": sum(1 for space in spaces if space.source_repo),
        "spaces": [space.__dict__ for space in spaces],
        "repositories": [plan.__dict__ for plan in plans],
        "summary": {
            status: sum(1 for plan in plans if plan.status == status)
            for status in sorted({plan.status for plan in plans})
        },
    }


def write_outputs(payload: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# SZL Responsive Estate v3",
        "",
        f"- Mode: `{payload['mode']}`",
        f"- Observed: `{payload['observed_at']}`",
        f"- Public Spaces: **{payload['hf_space_count']}**",
        f"- Source-mapped Spaces: **{payload['mapped_space_count']}**",
        "",
        "## Repository rollout",
        "",
        "| Repository | Spaces | Host | Status | Detail |",
        "|---|---:|---|---|---|",
    ]
    for plan in payload["repositories"]:
        spaces = "<br>".join(plan.get("spaces") or [])
        detail = (plan.get("detail") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{plan['repo']}` | {len(plan.get('spaces') or [])} | "
            f"`{plan.get('host_path') or 'UNAVAILABLE'}` | `{plan['status']}` | {detail} |"
        )
    lines.extend(["", "## Unmapped Spaces", ""])
    unmapped = [space for space in payload["spaces"] if not space.get("source_repo")]
    if unmapped:
        lines.extend(f"- `{space['repo_id']}` — source repository UNAVAILABLE" for space in unmapped)
    else:
        lines.append("None.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def token_from_env() -> str:
    return (
        os.environ.get("ESTATE_GITHUB_TOKEN")
        or os.environ.get("SZL_GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "apply"), default="plan")
    parser.add_argument("--merge-green", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=2100)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()

    token = token_from_env()
    if not token:
        raise SystemExit("ESTATE_GITHUB_TOKEN is required even for rate-limited repository planning")
    http = Http(token)
    spaces = inventory_spaces()
    resolve_sources(spaces, http)
    plans = build_plans(spaces, http)

    if args.mode == "apply":
        asset = ASSET_PATH.read_text(encoding="utf-8")
        run_id = os.environ.get("GITHUB_RUN_ID") or str(int(time.time()))
        for plan in plans:
            if plan.status != "READY":
                continue
            try:
                create_commit_for_plan(http, plan, asset, run_id)
                open_pr(http, plan)
            except RolloutError as exc:
                plan.status = "APPLY_ERROR"
                plan.detail = str(exc)
        if args.merge_green:
            merge_green(http, plans, args.wait_seconds)

    payload = serialize(spaces, plans, args.mode.upper())
    write_outputs(payload, args.json_out, args.markdown_out)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))

    hard_failures = {"PLAN_ERROR", "APPLY_ERROR", "CHECKS_FAILED", "MERGE_BLOCKED", "MERGE_ERROR"}
    if any(plan.status in hard_failures for plan in plans):
        return 1
    if args.mode == "apply" and args.merge_green and any(plan.status == "CHECKS_PENDING" for plan in plans):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
