#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Roll out the reviewed SZL Frontier Design Kernel through protected pull requests.

The operator is intentionally bounded:

* GitHub remains authoritative; no target default branch is pushed directly.
* Target repositories and entry points are discovered from a reviewed registry.
* Assets are vendored at the exact organization-design source revision.
* Existing page content is preserved; only marker-delimited shell hooks are added.
* Every candidate is validated locally before a branch is pushed.
* A secret-free receipt records source, targets, files, tests, PRs, and blockers.

The script never changes domains, hosting allocation, billing, secrets, branch
protection, or runtime data. It does not print authentication material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
DEFAULT_ORG = "szl-holdings"
USER_AGENT = "szl-frontier-design-rollout/1.0"
TOKEN_KEYS = ("GH_ADMIN_TOKEN", "ORG_ADMIN_TOKEN", "GH_ORG_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
MAX_TREE_BYTES = 8 * 1024 * 1024
MAX_API_BYTES = 4 * 1024 * 1024

HEAD_START = "<!-- szl-frontier-design:head:v1 -->"
HEAD_END = "<!-- /szl-frontier-design:head:v1 -->"
BODY_START = "<!-- szl-frontier-design:body:v1 -->"
BODY_END = "<!-- /szl-frontier-design:body:v1 -->"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def token_from_environment() -> tuple[str | None, str | None]:
    for key in TOKEN_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value, key
    return None, None


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        command = " ".join(args[:3])
        detail = (completed.stderr or completed.stdout or "command failed").strip()[-1600:]
        raise RuntimeError(f"{command}: {detail}")
    return completed


class GitHubAPI:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_404: bool = False,
        limit: int = MAX_API_BYTES,
    ) -> tuple[int, Any]:
        url = path if path.startswith("https://") else API + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(limit + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(min(limit, 256 * 1024))
            status = int(exc.code)
            if status == 404 and allow_404:
                return status, None
            message = raw.decode("utf-8", "replace")[:1200]
            raise RuntimeError(f"GitHub {method} {path} returned HTTP {status}: {message}") from exc
        if len(raw) > limit:
            raise RuntimeError(f"GitHub response exceeded {limit} bytes: {path}")
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return status, raw.decode("utf-8", "replace")

    def repo(self, full_name: str) -> dict[str, Any] | None:
        status, payload = self.request("GET", f"/repos/{full_name}", allow_404=True)
        return payload if status == 200 and isinstance(payload, dict) else None

    def tree(self, full_name: str, ref: str) -> list[str]:
        encoded = urllib.parse.quote(ref, safe="")
        status, payload = self.request(
            "GET",
            f"/repos/{full_name}/git/trees/{encoded}?recursive=1",
            limit=MAX_TREE_BYTES,
        )
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"tree inventory unavailable for {full_name}@{ref}")
        if payload.get("truncated") is True:
            raise RuntimeError(f"tree inventory truncated for {full_name}@{ref}; refusing partial discovery")
        return sorted(
            str(item.get("path"))
            for item in payload.get("tree", [])
            if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
        )

    def open_pr(self, full_name: str, branch: str, base: str) -> dict[str, Any] | None:
        owner = full_name.split("/", 1)[0]
        query = urllib.parse.urlencode(
            {"state": "open", "head": f"{owner}:{branch}", "base": base, "per_page": 20}
        )
        _, payload = self.request("GET", f"/repos/{full_name}/pulls?{query}")
        if isinstance(payload, list) and payload:
            return payload[0] if isinstance(payload[0], dict) else None
        return None

    def create_pr(
        self,
        full_name: str,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        _, payload = self.request(
            "POST",
            f"/repos/{full_name}/pulls",
            {
                "title": title,
                "head": branch,
                "base": base,
                "body": body,
                "maintainer_can_modify": True,
                "draft": False,
            },
        )
        if not isinstance(payload, dict) or not payload.get("number"):
            raise RuntimeError(f"GitHub did not return a pull request for {full_name}")
        return payload

    def required_checks(self, full_name: str, branch: str) -> bool:
        try:
            status, payload = self.request(
                "GET", f"/repos/{full_name}/branches/{urllib.parse.quote(branch, safe='')}/protection",
                allow_404=True,
            )
        except RuntimeError:
            return False
        if status != 200 or not isinstance(payload, dict):
            return False
        checks = payload.get("required_status_checks")
        if not isinstance(checks, dict):
            return False
        return bool(checks.get("contexts") or checks.get("checks"))

    def enable_auto_merge(self, pull_request: dict[str, Any]) -> tuple[bool, str]:
        node_id = str(pull_request.get("node_id") or "")
        if not node_id:
            return False, "pull request node id unavailable"
        try:
            _, payload = self.request(
                "POST",
                "/graphql",
                {
                    "query": (
                        "mutation($id:ID!){enablePullRequestAutoMerge(input:{"
                        "pullRequestId:$id,mergeMethod:SQUASH}){pullRequest{number}}}"
                    ),
                    "variables": {"id": node_id},
                },
            )
        except RuntimeError as exc:
            return False, str(exc)[:500]
        if isinstance(payload, dict) and payload.get("errors"):
            return False, str(payload["errors"])[:500]
        return True, "enabled"


@dataclass(frozen=True)
class BrandTarget:
    brand: str
    repo: str
    default_branch: str
    entrypoints: tuple[str, ...]
    discovery: str


def excluded(path: str, excluded_directories: set[str]) -> bool:
    parts = Path(path).parts
    return any(part in excluded_directories for part in parts[:-1])


def dynamic_entrypoints(
    paths: Iterable[str],
    *,
    brand: str,
    excluded_directories: set[str],
    maximum: int,
) -> list[str]:
    scored: list[tuple[int, str]] = []
    for path in paths:
        lower = path.lower()
        if excluded(path, excluded_directories):
            continue
        suffix = Path(path).suffix.lower()
        if suffix not in {".html", ".htm", ".py"}:
            continue
        score = 0
        name = Path(path).name.lower()
        depth = len(Path(path).parts)
        if name in {"index.html", "index.htm"}:
            score += 80
        if name in {"app.py", "serve.py", "server.py"}:
            score += 35
        if brand in lower:
            score += 100
        if brand == "killinchu" and "elite" in lower:
            score += 75
        if brand == "hatun" and any(token in lower for token in ("wire", "mcp", "orchestrat")):
            score += 75
        if brand == "a11oy" and any(token in lower for token in ("console", "home", "landing")):
            score += 60
        if lower.startswith(("web/", "pages/", "templates/", "static/", "public/")):
            score += 20
        score -= depth * 3
        if score > 20:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return [path for _, path in scored[:maximum]]


def candidate_entrypoints(
    paths: list[str],
    config: dict[str, Any],
    *,
    brand: str,
    patch_policy: dict[str, Any],
    fallback: bool = False,
) -> list[str]:
    path_set = set(paths)
    exact = list(config.get("entrypoint_candidates") or [])
    if fallback:
        exact = list((config.get("fallback") or {}).get("entrypoint_candidates") or exact)
    exact += list(config.get("python_entrypoint_candidates") or [])
    selected = [path for path in exact if path in path_set]
    maximum = int(patch_policy.get("maximum_entrypoints_per_brand") or 3)
    if selected:
        return selected[:maximum]
    return dynamic_entrypoints(
        paths,
        brand=brand,
        excluded_directories=set(patch_policy.get("excluded_directories") or []),
        maximum=maximum,
    )


def resolve_targets(
    api: GitHubAPI,
    registry: dict[str, Any],
    *,
    organization: str,
) -> tuple[list[BrandTarget], list[dict[str, Any]]]:
    resolved: list[BrandTarget] = []
    blockers: list[dict[str, Any]] = []
    patch_policy = registry.get("patch_policy") or {}
    for brand, config_any in (registry.get("brands") or {}).items():
        config = config_any if isinstance(config_any, dict) else {}
        chosen: BrandTarget | None = None
        inspected: list[str] = []
        for full_name in config.get("repository_candidates") or []:
            if not str(full_name).startswith(organization + "/"):
                continue
            repo = api.repo(str(full_name))
            if repo is None or bool(repo.get("archived")):
                continue
            default = str(repo.get("default_branch") or "main")
            paths = api.tree(str(full_name), default)
            entries = candidate_entrypoints(
                paths, config, brand=brand, patch_policy=patch_policy
            )
            inspected.append(f"{full_name}:{len(entries)}")
            if entries:
                chosen = BrandTarget(
                    brand=brand,
                    repo=str(full_name),
                    default_branch=default,
                    entrypoints=tuple(entries),
                    discovery="dedicated-repository",
                )
                break
        if chosen is None:
            fallback = config.get("fallback") or {}
            fallback_repo = str(fallback.get("repository") or "")
            if fallback_repo.startswith(organization + "/"):
                repo = api.repo(fallback_repo)
                if repo is not None and not bool(repo.get("archived")):
                    default = str(repo.get("default_branch") or "main")
                    paths = api.tree(fallback_repo, default)
                    entries = candidate_entrypoints(
                        paths,
                        config,
                        brand=brand,
                        patch_policy=patch_policy,
                        fallback=True,
                    )
                    inspected.append(f"{fallback_repo}:fallback:{len(entries)}")
                    if entries:
                        chosen = BrandTarget(
                            brand=brand,
                            repo=fallback_repo,
                            default_branch=default,
                            entrypoints=tuple(entries),
                            discovery="registered-fallback",
                        )
        if chosen is None:
            blockers.append(
                {
                    "brand": brand,
                    "state": "BLOCKED",
                    "reason": "No non-archived registered repository contained a safe entry point.",
                    "inspected": inspected,
                }
            )
        else:
            resolved.append(chosen)
    return resolved, blockers


def strip_marker_block(text: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\s*", re.DOTALL)
    return pattern.sub("", text)


def patch_body_tag(text: str, brand: str) -> str:
    pattern = re.compile(r"<body\b(?P<attrs>[^>]*)>", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        raise ValueError("HTML body tag not found")
    attrs = match.group("attrs")
    attrs = re.sub(r"\sdata-szl-frontier\s*=\s*(['\"]).*?\1", "", attrs, flags=re.IGNORECASE)
    class_match = re.search(r"\sclass\s*=\s*(['\"])(.*?)\1", attrs, flags=re.IGNORECASE | re.DOTALL)
    if class_match:
        classes = class_match.group(2).split()
        if "szl-frontier" not in classes:
            classes.append("szl-frontier")
        replacement = f' class="{" ".join(classes)}"'
        attrs = attrs[: class_match.start()] + replacement + attrs[class_match.end() :]
    else:
        attrs += ' class="szl-frontier"'
    attrs += f' data-szl-frontier="{brand}"'
    replacement = "<body" + attrs + ">"
    return text[: match.start()] + replacement + text[match.end() :]


def patch_entry(text: str, *, brand: str, css_url: str, js_url: str) -> str:
    if "</head>" not in text.lower() or "</body>" not in text.lower():
        raise ValueError("entry point lacks closing head/body tags")
    text = strip_marker_block(text, HEAD_START, HEAD_END)
    text = strip_marker_block(text, BODY_START, BODY_END)
    text = patch_body_tag(text, brand)
    head_block = (
        f"\n{HEAD_START}\n"
        f'<link rel="stylesheet" href="{css_url}" data-szl-frontier-asset="css-v1">\n'
        f"{HEAD_END}\n"
    )
    body_block = (
        f"\n{BODY_START}\n"
        f'<script src="{js_url}" defer data-szl-frontier-asset="js-v1"></script>\n'
        f"{BODY_END}\n"
    )
    text = re.sub(r"</head>", head_block + "</head>", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"</body>", body_block + "</body>", text, count=1, flags=re.IGNORECASE)
    return text


def choose_asset_location(repo_root: Path, entrypoints: list[str]) -> tuple[Path, str]:
    if (repo_root / "static").is_dir():
        return Path("static/szl/frontier-v1"), "/static/szl/frontier-v1"
    if (repo_root / "public").is_dir():
        return Path("public/szl/frontier-v1"), "/szl/frontier-v1"
    if (repo_root / "assets").is_dir():
        return Path("assets/szl/frontier-v1"), "/assets/szl/frontier-v1"
    if (repo_root / "web" / "assets").is_dir() or all(path.startswith("web/") for path in entrypoints):
        return Path("web/assets/szl/frontier-v1"), "/assets/szl/frontier-v1"
    if any(path.endswith(".py") for path in entrypoints):
        raise RuntimeError(
            "Python-rendered entry selected but no static/public/assets root exists; refusing broken asset URLs"
        )
    return Path("assets/szl/frontier-v1"), "/assets/szl/frontier-v1"


def write_target_test(repo_root: Path, contract_path: Path) -> Path:
    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        test_path = tests_dir / "test_szl_frontier_design.py"
        root_expression = "Path(__file__).resolve().parents[1]"
    else:
        test_path = repo_root / "test_szl_frontier_design.py"
        root_expression = "Path(__file__).resolve().parent"
    relative_contract = contract_path.relative_to(repo_root).as_posix()
    test_path.write_text(
        f'''#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generated network-free contract test for SZL Frontier Design Kernel v1."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = {root_expression}
CONTRACT = ROOT / {relative_contract!r}
HEAD = "{HEAD_START}"
BODY = "{BODY_START}"


def contract_value(payload, key):
    return payload.get(key)


class FrontierDesignContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_source_is_exact_and_presentation_only(self) -> None:
        self.assertEqual(contract_value(self.contract, "schema"), "szl.frontier-design.installation/v1")
        self.assertRegex(contract_value(self.contract, "source_revision"), r"^[0-9a-f]{{40}}$")
        self.assertEqual(contract_value(self.contract, "authority"), "PRESENTATION_ONLY")
        self.assertFalse(bool(self.contract.get("direct_main_push")))

    def test_assets_match_reviewed_digests(self) -> None:
        for name, record in self.contract["assets"].items():
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), f"missing {{name}} asset: {{path}}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, record["sha256"])
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("@import url", text)
            self.assertNotIn("<script src=\"http", text)

    def test_each_entry_is_marker_bound_once(self) -> None:
        for record in self.contract["entrypoints"]:
            path = ROOT / record["path"]
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count(HEAD), 1, path)
            self.assertEqual(text.count(BODY), 1, path)
            self.assertIn(f'data-szl-frontier="{{record["brand"]}}"', text)
            self.assertIn("szl-frontier", text)
            self.assertIn(record["css_url"], text)
            self.assertIn(record["js_url"], text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
''',
        encoding="utf-8",
    )
    return test_path


def git_environment(token: str, temp_root: Path) -> dict[str, str]:
    askpass = temp_root / "git-askpass.sh"
    askpass.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
        "  *) printf '%s\\n' \"$SZL_GH_TOKEN\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    askpass.chmod(askpass.stat().st_mode | stat.S_IXUSR)
    env = os.environ.copy()
    env.update(
        {
            "GIT_ASKPASS": str(askpass),
            "GIT_TERMINAL_PROMPT": "0",
            "SZL_GH_TOKEN": token,
            "GIT_AUTHOR_NAME": "Stephen P. Lutar",
            "GIT_AUTHOR_EMAIL": "stephenlutar2@gmail.com",
            "GIT_COMMITTER_NAME": "Stephen P. Lutar",
            "GIT_COMMITTER_EMAIL": "stephenlutar2@gmail.com",
        }
    )
    return env


def grouped_targets(targets: list[BrandTarget]) -> dict[str, list[BrandTarget]]:
    grouped: dict[str, list[BrandTarget]] = {}
    for target in targets:
        grouped.setdefault(target.repo, []).append(target)
    return grouped


def install_repo(
    *,
    api: GitHubAPI,
    token: str,
    source_root: Path,
    source_revision: str,
    registry: dict[str, Any],
    repo: str,
    targets: list[BrandTarget],
    branch_prefix: str,
    apply: bool,
    work_root: Path,
) -> dict[str, Any]:
    default_branch = targets[0].default_branch
    if any(target.default_branch != default_branch for target in targets):
        raise RuntimeError(f"inconsistent default branches for grouped target {repo}")
    branch = f"{branch_prefix}-{source_revision[:12]}"
    existing = api.open_pr(repo, branch, default_branch)
    if existing is not None:
        return {
            "repository": repo,
            "brands": [target.brand for target in targets],
            "branch": branch,
            "state": "EXISTING_PR",
            "pull_request": {
                "number": existing.get("number"),
                "url": existing.get("html_url"),
            },
        }

    repo_root = work_root / repo.split("/", 1)[1]
    env = git_environment(token, work_root)
    run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-tags",
            "--branch",
            default_branch,
            f"https://github.com/{repo}.git",
            str(repo_root),
        ],
        env=env,
        timeout=300,
    )
    run(["git", "checkout", "-b", branch], cwd=repo_root, env=env)

    all_entries = sorted({path for target in targets for path in target.entrypoints})
    asset_relative, asset_url = choose_asset_location(repo_root, all_entries)
    asset_dir = repo_root / asset_relative
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_css = source_root / ".github" / "design" / "frontier-v1" / "szl-frontier.css"
    source_js = source_root / ".github" / "design" / "frontier-v1" / "szl-frontier.js"
    css_dest = asset_dir / "szl-frontier.css"
    js_dest = asset_dir / "szl-frontier.js"
    shutil.copyfile(source_css, css_dest)
    shutil.copyfile(source_js, js_dest)

    changed_entries: list[dict[str, Any]] = []
    modified_python: list[str] = []
    for target in sorted(targets, key=lambda item: item.brand):
        for entry in target.entrypoints:
            path = repo_root / entry
            if not path.is_file():
                raise RuntimeError(f"discovered entry disappeared after clone: {repo}:{entry}")
            original = path.read_text(encoding="utf-8")
            patched = patch_entry(
                original,
                brand=target.brand,
                css_url=asset_url + "/szl-frontier.css",
                js_url=asset_url + "/szl-frontier.js",
            )
            path.write_text(patched, encoding="utf-8")
            if path.suffix.lower() == ".py":
                modified_python.append(entry)
            changed_entries.append(
                {
                    "brand": target.brand,
                    "path": entry,
                    "discovery": target.discovery,
                    "css_url": asset_url + "/szl-frontier.css",
                    "js_url": asset_url + "/szl-frontier.js",
                }
            )

    contract_path = repo_root / "design" / "szl-frontier-contract.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema": "szl.frontier-design.installation/v1",
        "version": registry.get("version"),
        "source_repository": registry.get("source_repository"),
        "source_revision": source_revision,
        "repository": repo,
        "default_branch": default_branch,
        "brands": sorted(target.brand for target in targets),
        "entrypoints": changed_entries,
        "assets": {
            "css": {
                "path": css_dest.relative_to(repo_root).as_posix(),
                "sha256": sha256_bytes(css_dest.read_bytes()),
            },
            "javascript": {
                "path": js_dest.relative_to(repo_root).as_posix(),
                "sha256": sha256_bytes(js_dest.read_bytes()),
            },
        },
        "authority": "PRESENTATION_ONLY",
        "runtime_dependencies": [],
        "network_fetches": 0,
        "direct_main_push": False,
        "delete_existing_content": False,
        "generated_at": utc_now(),
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    contract_path.write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    test_path = write_target_test(repo_root, contract_path)

    validations: list[dict[str, Any]] = []
    for command in (
        [sys.executable, str(test_path.relative_to(repo_root))],
        ["git", "diff", "--check"],
    ):
        result = run(command, cwd=repo_root, env=env)
        validations.append(
            {
                "command": " ".join(command),
                "status": "PASS",
                "output": (result.stdout or result.stderr).strip()[-900:],
            }
        )
    if modified_python:
        command = [sys.executable, "-m", "py_compile", *modified_python]
        result = run(command, cwd=repo_root, env=env)
        validations.append(
            {
                "command": "python -m py_compile " + " ".join(modified_python),
                "status": "PASS",
                "output": (result.stdout or result.stderr).strip()[-900:],
            }
        )

    run(["git", "add", "--all"], cwd=repo_root, env=env)
    status = run(["git", "status", "--porcelain"], cwd=repo_root, env=env)
    if not status.stdout.strip():
        return {
            "repository": repo,
            "brands": [target.brand for target in targets],
            "branch": branch,
            "state": "ALREADY_ALIGNED",
            "validations": validations,
        }

    summary = ", ".join(sorted(target.brand for target in targets))
    run(
        [
            "git",
            "commit",
            "-m",
            f"feat(design): install SZL Frontier shell for {summary}",
            "-m",
            f"Source-bound to szl-holdings/.github@{source_revision}.",
            "-m",
            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
        ],
        cwd=repo_root,
        env=env,
    )
    commit_sha = run(["git", "rev-parse", "HEAD"], cwd=repo_root, env=env).stdout.strip()

    if not apply:
        return {
            "repository": repo,
            "brands": [target.brand for target in targets],
            "branch": branch,
            "candidate_commit": commit_sha,
            "state": "DRY_RUN_VALIDATED",
            "entrypoints": changed_entries,
            "assets": contract["assets"],
            "validations": validations,
        }

    run(["git", "push", "--set-upstream", "origin", branch], cwd=repo_root, env=env, timeout=300)
    title = "feat(design): install the SZL Frontier visual system v1"
    body = (
        "## Frontier design rollout\n\n"
        f"Installs the reviewed organization design kernel from `szl-holdings/.github@{source_revision}`.\n\n"
        f"**Brand adapters:** {summary}.\n\n"
        "### Contract\n\n"
        "- one shared spacing, typography, navigation, component, focus, and motion grammar;\n"
        "- distinct palette and spatial motif for each product;\n"
        "- progressive enhancement with zero runtime CDN or analytics dependency;\n"
        "- existing page content preserved; only marker-delimited hooks added;\n"
        "- mobile, reduced-motion, forced-colors, keyboard-focus, and print behavior included;\n"
        "- presentation authority only—no API, data, secret, domain, hardware, or billing mutation.\n\n"
        "### Changed entry points\n\n"
        + "\n".join(f"- `{row['path']}` → `{row['brand']}`" for row in changed_entries)
        + "\n\n### Verification\n\n"
        + "\n".join(f"- `{row['command']}`: **PASS**" for row in validations)
        + "\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
    )
    pull_request = api.create_pr(
        repo,
        branch=branch,
        base=default_branch,
        title=title,
        body=body,
    )
    auto_merge = {"enabled": False, "reason": "required checks not detected"}
    if api.required_checks(repo, default_branch):
        enabled, reason = api.enable_auto_merge(pull_request)
        auto_merge = {"enabled": enabled, "reason": reason}

    return {
        "repository": repo,
        "brands": [target.brand for target in targets],
        "default_branch": default_branch,
        "branch": branch,
        "candidate_commit": commit_sha,
        "state": "PR_OPEN",
        "entrypoints": changed_entries,
        "assets": contract["assets"],
        "validations": validations,
        "pull_request": {
            "number": pull_request.get("number"),
            "url": pull_request.get("html_url"),
            "node_id": pull_request.get("node_id"),
        },
        "auto_merge": auto_merge,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Push candidate branches and open PRs")
    parser.add_argument("--organization", default=DEFAULT_ORG)
    parser.add_argument("--branch-prefix", default="design/szl-frontier-v1")
    parser.add_argument("--receipt", type=Path, default=Path("frontier-design-rollout-receipt.json"))
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    design_root = source_root / ".github" / "design" / "frontier-v1"
    registry_path = design_root / "brands.json"
    css_path = design_root / "szl-frontier.css"
    js_path = design_root / "szl-frontier.js"
    for required in (registry_path, css_path, js_path):
        if not required.is_file():
            raise SystemExit(f"required design artifact missing: {required}")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source_revision = run(["git", "rev-parse", "HEAD"], cwd=source_root).stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise SystemExit("design source is not an exact Git revision")

    token, token_source = token_from_environment()
    receipt: dict[str, Any] = {
        "schema": "szl.frontier-design.rollout-receipt/v1",
        "generated_at": utc_now(),
        "apply": bool(args.apply),
        "organization": args.organization,
        "source": {
            "repository": registry.get("source_repository"),
            "revision": source_revision,
            "version": registry.get("version"),
            "css_sha256": sha256_bytes(css_path.read_bytes()),
            "javascript_sha256": sha256_bytes(js_path.read_bytes()),
            "registry_sha256": sha256_bytes(registry_path.read_bytes()),
        },
        "credential": {"present": bool(token), "source": token_source},
        "targets": [],
        "blockers": [],
        "status": "FAIL",
    }

    def persist() -> None:
        receipt["receipt_sha256"] = canonical_sha256(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    if args.apply and not token:
        receipt["blockers"].append(
            {
                "state": "BLOCKED",
                "reason": "No organization-scoped GitHub credential is available for cross-repository PR creation.",
            }
        )
        persist()
        return 2

    api = GitHubAPI(token)
    try:
        targets, blockers = resolve_targets(api, registry, organization=args.organization)
        receipt["blockers"].extend(blockers)
        if not targets:
            receipt["blockers"].append(
                {"state": "BLOCKED", "reason": "No registered design target resolved."}
            )
            persist()
            return 2

        if token is None:
            receipt["blockers"].append(
                {
                    "state": "BLOCKED",
                    "reason": "Repository discovery succeeded, but candidate validation requires authenticated cloning.",
                }
            )
            persist()
            return 2

        with tempfile.TemporaryDirectory(prefix="szl-frontier-rollout-") as temporary:
            work_root = Path(temporary)
            for repo, repo_targets in sorted(grouped_targets(targets).items()):
                try:
                    result = install_repo(
                        api=api,
                        token=token,
                        source_root=source_root,
                        source_revision=source_revision,
                        registry=registry,
                        repo=repo,
                        targets=repo_targets,
                        branch_prefix=args.branch_prefix,
                        apply=args.apply,
                        work_root=work_root,
                    )
                    receipt["targets"].append(result)
                except Exception as exc:
                    receipt["blockers"].append(
                        {
                            "repository": repo,
                            "brands": [target.brand for target in repo_targets],
                            "state": "BLOCKED",
                            "reason": f"{type(exc).__name__}: {exc}"[:1800],
                        }
                    )
    except Exception as exc:
        receipt["blockers"].append(
            {"state": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"[:1800]}
        )

    successful_states = {"PR_OPEN", "EXISTING_PR", "ALREADY_ALIGNED", "DRY_RUN_VALIDATED"}
    target_ok = bool(receipt["targets"]) and all(
        target.get("state") in successful_states for target in receipt["targets"]
    )
    receipt["status"] = "PASS" if target_ok and not receipt["blockers"] else "PARTIAL"
    receipt["completed_at"] = utc_now()
    persist()
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "source_revision": source_revision,
                "target_count": len(receipt["targets"]),
                "blocker_count": len(receipt["blockers"]),
                "receipt": str(args.receipt),
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
