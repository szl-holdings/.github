#!/usr/bin/env python3
"""Open source-native Adaptive Theatre v3 PRs for current SZLHOLDINGS Spaces.

The controller is fail-closed:
- only current public Hugging Face Spaces are considered;
- only a GitHub repository with an existing reviewed SZL holographic/flow host
  asset is mutated;
- each repository keeps its own visual identity and product architecture;
- no Hugging Face file, hardware, secret, variable, model, or dataset is written;
- no branch protection is changed and no pull request is merged here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"
GITHUB_ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
BRANCH = "design/adaptive-theatre-v3"
MARKER = "szl:space-adaptive-v3"
JS_MARKER = "data-szl-space-adaptive-v3-loader"

CSS_HOST_NAMES = {
    "szl-holo-v2.css",
    "szl-hologram-v2.css",
    "szl-holo-proof-v2.css",
    "szl-flow.css",
    "szl-flow-proof.css",
}
JS_HOST_NAMES = {
    "szl-holo-v2.js",
    "szl-hologram-v2.js",
    "szl-holo-proof-v2.js",
    "szl-flow.js",
    "szl-flow-proof.js",
}
EXCLUDED_PARTS = {".git", "node_modules", "vendor", "dist", "build", ".next", "coverage", "fixtures", "archive", "archives"}
SOURCE_OVERRIDES: dict[str, str | None] = {
    "a11oy": "a11oy",
    "holographic": "a11oy",
    "killinchu": "killinchu",
    "immune": "immune",
    "szl-khipu": "szl-khipu",
    "szl-atelier": "szl-atelier",
    "governed-receipt-verifier": "governed-receipt-spec",
    "lyte-lattice": "lyte-lattice",
    "gdw-frontier": "gdw-frontier",
    "anatomy": None,
}


class RolloutError(RuntimeError):
    pass


def request_json(url: str, *, token: str = "", method: str = "GET", payload: Any | None = None) -> Any:
    body = None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "SZL-HF-Adaptive-Theatre/3.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
            return json.loads(data.decode("utf-8")) if data else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")[:2000]
        raise RolloutError(f"HTTP {exc.code} for {url}: {text}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RolloutError(f"request failed for {url}: {exc}") from exc


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-80:])
        raise RolloutError(f"command failed ({command[0]} exit {completed.returncode}):\n{tail}")
    return completed


def current_spaces() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"author": HF_ORG, "limit": 100, "full": "true"})
    data = request_json(f"{HF_API}/spaces?{query}")
    rows = data if isinstance(data, list) else data.get("items", [])
    result = []
    for row in rows:
        repo_id = str(row.get("id") or "")
        slug = repo_id.split("/", 1)[-1].strip()
        if slug:
            result.append(
                {
                    "id": repo_id or f"{HF_ORG}/{slug}",
                    "slug": slug,
                    "stage": (row.get("runtime") or {}).get("stage") or row.get("stage"),
                    "sdk": row.get("sdk") or (row.get("cardData") or {}).get("sdk"),
                    "sha": row.get("sha"),
                    "card": row.get("cardData") or {},
                }
            )
    return sorted(result, key=lambda item: item["slug"].lower())


def github_repositories(token: str) -> dict[str, dict[str, Any]]:
    repos: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        rows = request_json(f"{GITHUB_API}/orgs/{GITHUB_ORG}/repos?per_page=100&page={page}", token=token)
        if not rows:
            break
        for row in rows:
            repos[str(row["name"]).lower()] = row
        if len(rows) < 100:
            break
        page += 1
    return repos


def github_name_from_card(card: dict[str, Any]) -> str | None:
    for key in ("source_repo", "source-repo", "repository", "repo", "github", "homepage"):
        value = card.get(key)
        if not isinstance(value, str):
            continue
        match = re.search(r"github\.com/szl-holdings/([A-Za-z0-9_.-]+)", value)
        if match:
            return match.group(1)
        if value.startswith("szl-holdings/"):
            return value.split("/", 1)[1]
    return None


def source_repo(space: dict[str, Any], repos: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
    slug = space["slug"]
    if slug in SOURCE_OVERRIDES:
        candidate = SOURCE_OVERRIDES[slug]
        if candidate is None:
            return None, "intentional-fold"
        if candidate.lower() in repos:
            return repos[candidate.lower()]["name"], "override"
    card_name = github_name_from_card(space["card"])
    if card_name and card_name.lower() in repos:
        return repos[card_name.lower()]["name"], "card"
    if slug.lower() in repos:
        return repos[slug.lower()]["name"], "exact-slug"
    normalized = slug.lower().replace("_", "-")
    if normalized in repos:
        return repos[normalized]["name"], "normalized-slug"
    return None, "unmapped"


def eligible(path: Path, root: Path) -> bool:
    return path.is_file() and not (set(path.relative_to(root).parts) & EXCLUDED_PARTS)


def host_assets(root: Path) -> tuple[list[Path], list[Path]]:
    css = [path for path in root.rglob("*.css") if eligible(path, root) and path.name in CSS_HOST_NAMES]
    js = [path for path in root.rglob("*.js") if eligible(path, root) and path.name in JS_HOST_NAMES]
    return sorted(css), sorted(js)


def insert_css_import(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    statement = '@import url("./szl-space-adaptive-v3.css"); /* szl:space-adaptive-v3 */\n'
    if text.count(MARKER) > 1:
        raise RolloutError(f"duplicate CSS marker in {path}")
    if MARKER in text:
        return
    if text.startswith("@charset"):
        end = text.find(";") + 1
        text = text[:end] + "\n" + statement + text[end:].lstrip("\n")
    else:
        text = statement + text
    path.write_text(text, encoding="utf-8", newline="\n")


def insert_js_loader(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(JS_MARKER) > 1:
        raise RolloutError(f"duplicate JS marker in {path}")
    if JS_MARKER in text:
        return
    loader = r'''
;(function () {
  "use strict";
  if (window.__SZL_SPACE_ADAPTIVE_V3_LOADER__) return;
  window.__SZL_SPACE_ADAPTIVE_V3_LOADER__ = true;
  if (document.querySelector("script[data-szl-space-adaptive-v3-loader]")) return;
  var owner = document.currentScript;
  var script = document.createElement("script");
  script.src = owner && owner.src
    ? new URL("./szl-space-adaptive-v3.js", owner.src).href
    : "./szl-space-adaptive-v3.js";
  script.defer = true;
  script.dataset.szlSpaceAdaptiveV3Loader = "true";
  document.head.appendChild(script);
}());
'''.strip()
    path.write_text(text.rstrip() + "\n\n" + loader + "\n", encoding="utf-8", newline="\n")


def install_assets(repo_root: Path, css_source: Path, js_source: Path) -> dict[str, Any]:
    css_hosts, js_hosts = host_assets(repo_root)
    if not css_hosts and not js_hosts:
        raise RolloutError("NO_REVIEWED_HOLOGRAPHIC_HOST")
    installed: list[str] = []
    for host in css_hosts:
        target = host.parent / "szl-space-adaptive-v3.css"
        shutil.copyfile(css_source, target)
        insert_css_import(host)
        installed.extend([target.relative_to(repo_root).as_posix(), host.relative_to(repo_root).as_posix()])
    for host in js_hosts:
        target = host.parent / "szl-space-adaptive-v3.js"
        shutil.copyfile(js_source, target)
        insert_js_loader(host)
        installed.extend([target.relative_to(repo_root).as_posix(), host.relative_to(repo_root).as_posix()])
    for path in {item.parent / "szl-space-adaptive-v3.js" for item in js_hosts} | set(js_hosts):
        run(["node", "--check", str(path)], cwd=repo_root)
    for path in {item.parent / "szl-space-adaptive-v3.css" for item in css_hosts} | set(css_hosts):
        text = path.read_text(encoding="utf-8")
        if text.count("{") != text.count("}"):
            raise RolloutError(f"unbalanced CSS: {path.relative_to(repo_root)}")
    run(["git", "diff", "--check"], cwd=repo_root)
    return {"css_hosts": [p.relative_to(repo_root).as_posix() for p in css_hosts], "js_hosts": [p.relative_to(repo_root).as_posix() for p in js_hosts], "installed": sorted(set(installed))}


def existing_pr(token: str, repo: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"state": "open", "head": f"{GITHUB_ORG}:{BRANCH}", "base": "main", "per_page": 20})
    rows = request_json(f"{GITHUB_API}/repos/{GITHUB_ORG}/{repo}/pulls?{query}", token=token)
    return rows[0] if rows else None


def process_repo(repo: str, spaces: list[dict[str, Any]], token: str, css_source: Path, js_source: Path, workspace: Path, apply: bool) -> dict[str, Any]:
    row: dict[str, Any] = {"repository": f"{GITHUB_ORG}/{repo}", "spaces": [space["id"] for space in spaces], "status": "BLOCKED"}
    metadata = request_json(f"{GITHUB_API}/repos/{GITHUB_ORG}/{repo}", token=token)
    if metadata.get("archived"):
        row.update(status="SKIPPED_ARCHIVED")
        return row
    default = metadata.get("default_branch") or "main"
    row["default_branch"] = default
    checkout = workspace / repo
    env = dict(os.environ, GH_TOKEN=token, GIT_TERMINAL_PROMPT="0")
    run(["gh", "repo", "clone", f"{GITHUB_ORG}/{repo}", str(checkout), "--", "--depth=1", "--branch", default], env=env)
    run(["git", "config", "user.name", "SZL Adaptive Theatre Controller"], cwd=checkout)
    run(["git", "config", "user.email", "stephenlutar2@gmail.com"], cwd=checkout)
    run(["git", "checkout", "-B", BRANCH], cwd=checkout)
    try:
        changes = install_assets(checkout, css_source, js_source)
    except RolloutError as exc:
        row.update(status="UNAVAILABLE", error=str(exc))
        return row
    row["changes"] = changes
    diff = run(["git", "status", "--porcelain"], cwd=checkout).stdout.strip()
    if not diff:
        row.update(status="ALREADY_CURRENT")
        return row
    if not apply:
        row.update(status="WOULD_OPEN_PR")
        return row
    run(["git", "add", "-A"], cwd=checkout)
    run(["git", "commit", "-s", "-m", "feat(frontend): adopt Adaptive Theatre v3"], cwd=checkout)
    run(["git", "push", "--force-with-lease", "origin", f"HEAD:{BRANCH}"], cwd=checkout, env=env)
    present = existing_pr(token, repo)
    if present:
        row.update(status="PR_UPDATED", pr_number=present["number"], pr_url=present["html_url"])
        return row
    body = "\n".join(
        [
            "## Adaptive Theatre v3",
            "",
            "Adds the shared responsive geometry and viewport controller through this application's existing reviewed SZL holographic/flow host assets.",
            "",
            "The application keeps its own palette, motif, copy, workflow, and business logic. The shared layer supplies 320px mobile through 1920px theatre composition, 44/48px controls, safe areas, responsive tables/code/media, keyboard focus, reduced motion, forced colors, low-resource behavior, and print handling.",
            "",
            "No model, dataset, receipt, API, secret, hardware, branch-protection, or Hugging Face setting is changed. No runtime CDN, analytics, cookies, storage, or fabricated telemetry is introduced.",
            "",
            "Spaces: " + ", ".join(row["spaces"]),
            "",
            "Generated by `szl.hf-adaptive-theatre-rollout/v3`.",
            "",
            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
        ]
    )
    pr = request_json(
        f"{GITHUB_API}/repos/{GITHUB_ORG}/{repo}/pulls",
        token=token,
        method="POST",
        payload={"title": "feat(frontend): adopt Adaptive Theatre v3", "head": BRANCH, "base": default, "body": body, "maintainer_can_modify": True},
    )
    row.update(status="PR_OPENED", pr_number=pr["number"], pr_url=pr["html_url"])
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--css", type=Path, required=True)
    parser.add_argument("--js", type=Path, required=True)
    args = parser.parse_args()

    token = (os.environ.get("ORG_ADMIN_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    report: dict[str, Any] = {"schema": "szl.hf-adaptive-theatre-rollout/v3", "apply": args.apply, "token_recorded": False, "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows": []}
    if not token:
        report.update(status="UNAVAILABLE", error="No cross-repository GitHub token is configured.")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2

    spaces = current_spaces()
    repos = github_repositories(token)
    grouped: dict[str, list[dict[str, Any]]] = {}
    unmapped: list[dict[str, Any]] = []
    for space in spaces:
        repo, method = source_repo(space, repos)
        space["mapping_method"] = method
        if repo:
            grouped.setdefault(repo, []).append(space)
        else:
            unmapped.append(space)

    with tempfile.TemporaryDirectory(prefix="szl-adaptive-v3-") as tmp:
        workspace = Path(tmp)
        for repo, repo_spaces in sorted(grouped.items()):
            if repo == "a11oy":
                report["rows"].append({"repository": f"{GITHUB_ORG}/{repo}", "spaces": [s["id"] for s in repo_spaces], "status": "DOMAIN_ROLLOUT_SEPARATE"})
                continue
            try:
                report["rows"].append(process_repo(repo, repo_spaces, token, args.css, args.js, workspace, args.apply))
            except Exception as exc:  # preserve other repositories; report exact failure
                report["rows"].append({"repository": f"{GITHUB_ORG}/{repo}", "spaces": [s["id"] for s in repo_spaces], "status": "FAILED", "error": str(exc)[:4000]})

    for space in unmapped:
        report["rows"].append({"repository": None, "spaces": [space["id"]], "status": "UNMAPPED", "reason": space["mapping_method"], "stage": space.get("stage"), "sdk": space.get("sdk")})

    counts: dict[str, int] = {}
    for row in report["rows"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report["summary"] = {"spaces": len(spaces), "mapped_repositories": len(grouped), "status_counts": counts}
    blocking = [row for row in report["rows"] if row["status"] in {"FAILED"}]
    report["status"] = "FAILED" if blocking else "COMPLETE"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
