#!/usr/bin/env python3
"""Reconcile A11oy SDA contract probes with the byte-shared Killinchu surface.

This is a bounded source-control operation.  It does not deploy to Hugging Face,
change repository protections, approve a PR, or merge anything.  Every mutable
reference is checked against an immutable expected SHA before a write occurs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"


class ReconcileError(RuntimeError):
    pass


def request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    raw_payload = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=raw_payload,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-sda-shared-source-reconcile/1.0",
            **({"Content-Type": "application/json"} if raw_payload is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:3000]
        raise ReconcileError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ReconcileError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(body.decode("utf-8")) if body else None


def split_repo(repository: str) -> tuple[str, str]:
    owner, name = repository.split("/", 1)
    return owner, name


def repo_path(repository: str, suffix: str) -> str:
    owner, name = split_repo(repository)
    return f"/repos/{owner}/{name}/{suffix.lstrip('/')}"


def assert_admin(token: str, identity: str, repository: str) -> None:
    encoded = urllib.parse.quote(identity, safe="")
    data = request(token, "GET", repo_path(repository, f"collaborators/{encoded}/permission"))
    if data.get("permission") != "admin":
        raise ReconcileError(
            f"authenticated identity {identity!r} has {data.get('permission')!r}, not admin, on {repository}"
        )


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    if result.returncode != 0:
        tail = result.stdout[-5000:]
        raise ReconcileError(f"command failed ({' '.join(command)}):\n{tail}")
    return result.stdout


def clone_at(token: str, repository: str, ref: str, destination: Path) -> None:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    run(["gh", "repo", "clone", repository, str(destination), "--", "--filter=blob:none"], cwd=destination.parent, env=env)
    run(["git", "fetch", "--no-tags", "origin", ref], cwd=destination, env=env)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=destination, env=env)


def patch_static_sdks(text: str, slugs: list[str]) -> str:
    updated = text
    for slug in slugs:
        pattern = re.compile(
            rf'(^\s*\{{"name":\s*"{re.escape(slug)}"[^\n]*"sdk":\s*)"gradio"',
            re.MULTILINE,
        )
        updated, count = pattern.subn(r'\1"static"', updated, count=1)
        if count != 1:
            raise ReconcileError(f"expected exactly one stale gradio classification for {slug}, found {count}")
    for slug in slugs:
        expected = re.compile(
            rf'^\s*\{{"name":\s*"{re.escape(slug)}"[^\n]*"sdk":\s*"static"',
            re.MULTILINE,
        )
        if not expected.search(updated):
            raise ReconcileError(f"failed to establish static SDK classification for {slug}")
    required_markers = (
        "SPACE_API_CONTRACTS",
        '"/api/anatomy/v1/manifest"',
        '"/api/a11oy/v1/verify/receipt"',
        '"contract_state"',
    )
    missing = [marker for marker in required_markers if marker not in updated]
    if missing:
        raise ReconcileError(f"A11oy SDA shared source is missing required contract markers: {missing}")
    return updated


def content_metadata(token: str, repository: str, path: str, ref: str) -> dict[str, Any]:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    encoded_ref = urllib.parse.quote(ref, safe="")
    return request(token, "GET", repo_path(repository, f"contents/{encoded_path}?ref={encoded_ref}"))


def put_content(
    token: str,
    repository: str,
    path: str,
    branch: str,
    current_sha: str,
    content: str,
    message: str,
) -> str:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    result = request(
        token,
        "PUT",
        repo_path(repository, f"contents/{encoded_path}"),
        {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "sha": current_sha,
            "branch": branch,
        },
    )
    return result["commit"]["sha"]


def delete_content(
    token: str,
    repository: str,
    path: str,
    branch: str,
    current_sha: str,
    message: str,
) -> str:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    result = request(
        token,
        "DELETE",
        repo_path(repository, f"contents/{encoded_path}"),
        {"message": message, "sha": current_sha, "branch": branch},
    )
    return result["commit"]["sha"]


def ref_sha(token: str, repository: str, branch: str) -> str:
    encoded = urllib.parse.quote(f"heads/{branch}", safe="/")
    return request(token, "GET", repo_path(repository, f"git/ref/{encoded}"))["object"]["sha"]


def create_or_reset_branch(token: str, repository: str, branch: str, base_sha: str) -> None:
    encoded = urllib.parse.quote(f"heads/{branch}", safe="/")
    try:
        request(token, "GET", repo_path(repository, f"git/ref/{encoded}"))
    except ReconcileError as exc:
        if "HTTP 404" not in str(exc):
            raise
        request(
            token,
            "POST",
            repo_path(repository, "git/refs"),
            {"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        return
    request(
        token,
        "PATCH",
        repo_path(repository, f"git/refs/{encoded}"),
        {"sha": base_sha, "force": True},
    )


def update_pr_body(token: str, repository: str, number: int, body: str) -> None:
    request(token, "PATCH", repo_path(repository, f"pulls/{number}"), {"body": body})


def append_peer(body: str, peer_line: str) -> str:
    cleaned = re.sub(r"\n*Shared-source-peer:.*(?:\n|$)", "\n", body or "").rstrip()
    return cleaned + "\n\n" + peer_line + "\n"


def find_or_create_pr(
    token: str,
    repository: str,
    branch: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    owner, _ = split_repo(repository)
    query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{branch}", "base": "main"})
    existing = request(token, "GET", repo_path(repository, f"pulls?{query}"))
    if existing:
        pr = existing[0]
        request(
            token,
            "PATCH",
            repo_path(repository, f"pulls/{pr['number']}"),
            {"title": title, "body": body, "maintainer_can_modify": True},
        )
        return request(token, "GET", repo_path(repository, f"pulls/{pr['number']}"))
    return request(
        token,
        "POST",
        repo_path(repository, "pulls"),
        {
            "title": title,
            "body": body,
            "head": branch,
            "base": "main",
            "draft": False,
            "maintainer_can_modify": True,
        },
    )


def validate_tree(repo: Path, test_command: list[str]) -> None:
    run(["python", "-m", "py_compile", "szl_spaces_surface.py"], cwd=repo)
    run(test_command, cwd=repo)
    run(["git", "diff", "--check"], cwd=repo)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    if not token:
        raise ReconcileError("SZL_GITHUB_TOKEN is not configured")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("schema") != "szl.sda-shared-source-reconcile/v1":
        raise ReconcileError("unexpected manifest schema")

    report: dict[str, Any] = {
        "schema": "szl.sda-shared-source-reconcile-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "actions": [],
        "errors": [],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        identity = request(token, "GET", "/user")["login"]
        report["identity"] = identity
        a11oy = manifest["a11oy"]
        killinchu = manifest["killinchu"]
        for repository in (a11oy["repository"], killinchu["repository"]):
            assert_admin(token, identity, repository)

        a_pr = request(token, "GET", repo_path(a11oy["repository"], f"pulls/{a11oy['pull_request']}"))
        if a_pr.get("state") != "open" or a_pr.get("draft"):
            raise ReconcileError("A11oy #1028 is not an open non-draft PR")
        if a_pr["head"]["ref"] != a11oy["branch"] or a_pr["head"]["sha"] != a11oy["expected_head_sha"]:
            raise ReconcileError(
                f"A11oy PR head moved: expected {a11oy['branch']}@{a11oy['expected_head_sha']}, "
                f"got {a_pr['head']['ref']}@{a_pr['head']['sha']}"
            )
        if a_pr["base"]["ref"] != "main":
            raise ReconcileError("A11oy #1028 no longer targets main")

        current_k_main = ref_sha(token, killinchu["repository"], "main")
        if current_k_main != killinchu["expected_main_sha"]:
            raise ReconcileError(
                f"Killinchu main moved: expected {killinchu['expected_main_sha']}, got {current_k_main}"
            )

        with tempfile.TemporaryDirectory(prefix="szl-sda-reconcile-") as temp:
            root = Path(temp)
            a_checkout = root / "a11oy"
            k_checkout = root / "killinchu"
            clone_at(token, a11oy["repository"], a11oy["expected_head_sha"], a_checkout)
            shared = a_checkout / manifest["shared_path"]
            corrected = patch_static_sdks(shared.read_text(encoding="utf-8"), manifest["static_spaces"])
            shared.write_text(corrected, encoding="utf-8", newline="\n")
            temporary_workflow = a_checkout / a11oy["temporary_workflow"]
            if not temporary_workflow.exists():
                raise ReconcileError(f"temporary workflow is missing at expected head: {a11oy['temporary_workflow']}")
            temporary_workflow.unlink()
            validate_tree(
                a_checkout,
                ["python", "-m", "pytest", "-q", "tests/test_szl_spaces_inventory.py", "tests/test_demo_critical_routes.py"],
            )

            clone_at(token, killinchu["repository"], current_k_main, k_checkout)
            (k_checkout / manifest["shared_path"]).write_text(corrected, encoding="utf-8", newline="\n")
            validate_tree(k_checkout, ["python", "-m", "pytest", "-q", "tests/test_ecosystem_alignment.py"])

        a_shared_meta = content_metadata(token, a11oy["repository"], manifest["shared_path"], a11oy["branch"])
        put_content(
            token,
            a11oy["repository"],
            manifest["shared_path"],
            a11oy["branch"],
            a_shared_meta["sha"],
            corrected,
            "fix(spaces): preserve verified static SDK inventory\n\nKeep the exact SDA contract probes while retaining the three live static Space classifications already merged in #1027.\n\nSigned-off-by: Stephen Lutar <stephenlutar@gmail.com>",
        )
        temp_meta = content_metadata(token, a11oy["repository"], a11oy["temporary_workflow"], a11oy["branch"])
        delete_content(
            token,
            a11oy["repository"],
            a11oy["temporary_workflow"],
            a11oy["branch"],
            temp_meta["sha"],
            "ci: remove completed SDA branch repair workflow\n\nThe verified source correction is now committed; no branch-only workflow remains in the product diff.\n\nSigned-off-by: Stephen Lutar <stephenlutar@gmail.com>",
        )
        a_head = ref_sha(token, a11oy["repository"], a11oy["branch"])

        create_or_reset_branch(token, killinchu["repository"], killinchu["branch"], current_k_main)
        k_meta = content_metadata(token, killinchu["repository"], manifest["shared_path"], killinchu["branch"])
        put_content(
            token,
            killinchu["repository"],
            manifest["shared_path"],
            killinchu["branch"],
            k_meta["sha"],
            corrected,
            "fix(spaces): mirror exact SDA API contracts\n\nKeep the shared Space inventory and exact route-level health contracts byte-identical with A11oy.\n\nSigned-off-by: Stephen Lutar <stephenlutar@gmail.com>",
        )
        k_head = ref_sha(token, killinchu["repository"], killinchu["branch"])

        k_body = (
            "## Purpose\n\nMirror the byte-identical `szl_spaces_surface.py` from A11oy #1028 so both services "
            "enforce the same exact Anatomy and SDA route contracts while retaining the three verified static "
            "Space SDK classifications.\n\n## Verification\n\n- Python compilation passed.\n"
            "- `pytest -q tests/test_ecosystem_alignment.py` passed on the exact proposed file.\n"
            "- The shared file is byte-identical to the A11oy candidate.\n\n## Boundary\n\n"
            "No deployment, token, branch protection, signing policy, model, or kernel behavior is changed.\n\n"
            f"Shared-source-peer: {a11oy['repository']}#{a11oy['pull_request']}@{a_head}\n"
        )
        k_pr = find_or_create_pr(
            token,
            killinchu["repository"],
            killinchu["branch"],
            killinchu["pull_request_title"],
            k_body,
        )
        a_body = append_peer(
            a_pr.get("body") or "",
            f"Shared-source-peer: {killinchu['repository']}#{k_pr['number']}@{k_head}",
        )
        update_pr_body(token, a11oy["repository"], a11oy["pull_request"], a_body)

        report["actions"] = [
            {
                "repository": a11oy["repository"],
                "pull_request": a11oy["pull_request"],
                "head_sha": a_head,
                "status": "repaired",
                "temporary_workflow_removed": True,
            },
            {
                "repository": killinchu["repository"],
                "pull_request": k_pr["number"],
                "head_sha": k_head,
                "status": "companion-opened",
                "shared_blob_sha256": __import__("hashlib").sha256(corrected.encode("utf-8")).hexdigest(),
            },
        ]
        report["ok"] = True
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
