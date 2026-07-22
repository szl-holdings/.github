#!/usr/bin/env python3
"""Update exact pull-request branches to their exact protected base revisions.

The manifest pins repository, PR number, current head SHA, target branch, and base
SHA. Every target is preflighted before any write. The GitHub update-branch API
performs a normal base merge into the PR branch; this script never force-pushes,
rewrites commits, changes protection, or merges the pull request itself.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GateError(RuntimeError):
    pass


def request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "szl-exact-pr-branch-update/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:5000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "szl.exact-pr-branch-update/v1":
        raise GateError("unexpected manifest schema")
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise GateError("manifest has no targets")
    seen: set[tuple[str, int]] = set()
    for target in targets:
        key = (str(target["repository"]), int(target["pull_request"]))
        if key in seen:
            raise GateError(f"duplicate target: {key}")
        seen.add(key)
        for field in ("expected_head_sha", "expected_base_sha"):
            value = str(target[field])
            if len(value) != 40:
                raise GateError(f"{key} has invalid {field}")
            int(value, 16)
    return data


def pr_path(repository: str, number: int) -> str:
    owner, repo = repository.split("/", 1)
    return (
        f"/repos/{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo, safe='')}/pulls/{number}"
    )


def preflight(token: str, target: dict[str, Any]) -> dict[str, Any]:
    repository = str(target["repository"])
    number = int(target["pull_request"])
    expected_head = str(target["expected_head_sha"])
    expected_base_branch = str(target["expected_base_branch"])
    expected_base = str(target["expected_base_sha"])
    pr = request(token, "GET", pr_path(repository, number))
    if pr.get("state") != "open" or pr.get("draft"):
        raise GateError(f"{repository}#{number} is not an open non-draft PR")
    actual_head = str((pr.get("head") or {}).get("sha") or "")
    actual_base_branch = str((pr.get("base") or {}).get("ref") or "")
    actual_base = str((pr.get("base") or {}).get("sha") or "")
    if actual_head != expected_head:
        raise GateError(f"{repository}#{number} head moved: expected {expected_head}, got {actual_head}")
    if actual_base_branch != expected_base_branch:
        raise GateError(
            f"{repository}#{number} targets {actual_base_branch!r}, expected {expected_base_branch!r}"
        )
    if actual_base != expected_base:
        raise GateError(f"{repository}#{number} base moved: expected {expected_base}, got {actual_base}")
    if pr.get("mergeable") is False:
        raise GateError(f"{repository}#{number} is not mergeable")
    return {
        "repository": repository,
        "pull_request": number,
        "head_before": actual_head,
        "base_branch": actual_base_branch,
        "base_sha": actual_base,
        "purpose": target.get("purpose"),
    }


def update(token: str, target: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    repository = before["repository"]
    number = before["pull_request"]
    endpoint = pr_path(repository, number) + "/update-branch"
    response = request(
        token,
        "PUT",
        endpoint,
        {"expected_head_sha": before["head_before"]},
    )
    deadline = time.monotonic() + 90
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        time.sleep(3)
        last = request(token, "GET", pr_path(repository, number))
        head_after = str((last.get("head") or {}).get("sha") or "")
        base_after = str((last.get("base") or {}).get("sha") or "")
        if head_after and head_after != before["head_before"]:
            if base_after != before["base_sha"]:
                raise GateError(
                    f"{repository}#{number} base changed during update: {before['base_sha']} -> {base_after}"
                )
            return {
                **before,
                "head_after": head_after,
                "update_response": response,
                "state_after": last.get("state"),
                "mergeable_after": last.get("mergeable"),
            }
    raise GateError(
        f"{repository}#{number} head did not advance after update-branch; last={last!r}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema": "szl.exact-pr-branch-update-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "identity": None,
        "targets": [],
        "errors": [],
        "ok": False,
    }
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        report["identity"] = request(token, "GET", "/user").get("login")
        manifest = load_manifest(args.manifest)
        prepared = [preflight(token, target) for target in manifest["targets"]]
        report["targets"] = prepared
        if args.execute:
            report["targets"] = [
                update(token, target, before)
                for target, before in zip(manifest["targets"], prepared, strict=True)
            ]
        report["ok"] = True
        code = 0
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        code = 1
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
