#!/usr/bin/env python3
"""Rebuild blocked PR trees as single GitHub-signed commits.

The source pull requests are read-only. Each recovery branch starts at the exact
current default-branch commit, receives one ``createCommitOnBranch`` GraphQL
commit, and is accepted only when GitHub reports a verified signature and the
new commit tree is byte-identical to the source PR head tree.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "szl-holdings/.github")
REPORT_PATH = Path(
    os.environ.get("REPORT_PATH", "reports/signed-pr-recovery.json")
)
TARGETS = (
    {
        "source_pr": 322,
        "branch_prefix": "fix/hf-release-evidence-chain-signed",
        "headline": "fix(hf): serialize publication readiness and estate evidence",
        "body": (
            "Rebuilds the exact reviewed tree from PR #322 as one GitHub-signed "
            "commit so the active required-signatures rule remains enforced.\n\n"
            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
        ),
    },
    {
        "source_pr": 323,
        "branch_prefix": "fix/code-security-drift-app-auth-signed",
        "headline": "fix(security): replace stale drift PAT with qillqaq app auth",
        "body": (
            "Rebuilds the exact reviewed tree from PR #323 as one GitHub-signed "
            "commit so the active required-signatures rule remains enforced.\n\n"
            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
        ),
    },
)
GRAPHQL_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid url }
    ref { name target { oid } }
  }
}
"""


class RecoveryError(RuntimeError):
    """A fail-closed recovery invariant was not satisfied."""


def _run(command: list[str], *, stdin: dict[str, Any] | None = None) -> Any:
    process = subprocess.run(
        command,
        input=json.dumps(stdin) if stdin is not None else None,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RecoveryError(
            f"command failed ({process.returncode}): {' '.join(command)}: "
            f"{detail[:2000]}"
        )
    text = process.stdout.strip()
    return json.loads(text) if text else None


def rest(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    command = ["gh", "api", "--method", method, path]
    if body is not None:
        command.extend(["--input", "-"])
    return _run(command, stdin=body)


def graphql(query: str, variables: dict[str, Any]) -> Any:
    return _run(
        ["gh", "api", "graphql", "--input", "-"],
        stdin={"query": query, "variables": variables},
    )


def paginated_pr_files(number: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = rest(
            "GET",
            f"repos/{REPOSITORY}/pulls/{number}/files?per_page=100&page={page}",
        )
        if not isinstance(batch, list):
            raise RecoveryError(f"PR #{number} files response is not a list")
        files.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return files
        page += 1


def current_main_sha() -> str:
    ref = rest("GET", f"repos/{REPOSITORY}/git/ref/heads/main")
    sha = str(((ref or {}).get("object") or {}).get("sha") or "")
    if len(sha) != 40:
        raise RecoveryError(f"main ref lacks an immutable SHA: {sha!r}")
    return sha


def get_ref_sha(branch: str) -> str | None:
    encoded = quote(branch, safe="/")
    process = subprocess.run(
        ["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/git/ref/heads/{encoded}"],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ,
    )
    if process.returncode != 0:
        if "HTTP 404" in process.stderr or '"status":"404"' in process.stdout:
            return None
        detail = process.stderr.strip() or process.stdout.strip()
        raise RecoveryError(f"could not read branch {branch}: {detail[:1000]}")
    payload = json.loads(process.stdout)
    sha = str(((payload or {}).get("object") or {}).get("sha") or "")
    if len(sha) != 40:
        raise RecoveryError(f"branch {branch} lacks an immutable SHA")
    return sha


def create_ref(branch: str, sha: str) -> None:
    rest(
        "POST",
        f"repos/{REPOSITORY}/git/refs",
        {"ref": f"refs/heads/{branch}", "sha": sha},
    )


def file_content(path: str, ref: str) -> str:
    encoded_path = quote(path, safe="/")
    encoded_ref = quote(ref, safe="")
    payload = rest(
        "GET",
        f"repos/{REPOSITORY}/contents/{encoded_path}?ref={encoded_ref}",
    )
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise RecoveryError(f"{path}@{ref} is not a regular file")
    if payload.get("encoding") != "base64" or not payload.get("content"):
        raise RecoveryError(f"{path}@{ref} lacks inline base64 content")
    return "".join(str(payload["content"]).splitlines())


def build_file_changes(
    source_pr: int,
    source_sha: str,
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    additions: dict[str, str] = {}
    deletions: set[str] = set()
    inventory = paginated_pr_files(source_pr)
    for item in inventory:
        status = str(item.get("status") or "")
        path = str(item.get("filename") or "")
        previous = str(item.get("previous_filename") or "")
        if not path:
            raise RecoveryError(f"PR #{source_pr} contains a file without a path")
        if status == "removed":
            deletions.add(path)
        elif status == "renamed":
            if not previous:
                raise RecoveryError(f"renamed path {path} has no previous_filename")
            deletions.add(previous)
            additions[path] = file_content(path, source_sha)
        elif status in {"added", "modified", "changed", "copied"}:
            additions[path] = file_content(path, source_sha)
        else:
            raise RecoveryError(
                f"unsupported PR file status for {path}: {status!r}"
            )

    overlap = set(additions).intersection(deletions)
    if overlap:
        raise RecoveryError(f"paths appear in both additions and deletions: {sorted(overlap)}")
    if not additions and not deletions:
        raise RecoveryError(f"PR #{source_pr} has no file changes")
    changes = {
        "additions": [
            {"path": path, "contents": contents}
            for path, contents in sorted(additions.items())
        ],
        "deletions": [{"path": path} for path in sorted(deletions)],
    }
    return changes, inventory


def commit_tree(sha: str) -> str:
    payload = rest("GET", f"repos/{REPOSITORY}/git/commits/{sha}")
    tree = str(((payload or {}).get("tree") or {}).get("sha") or "")
    if len(tree) != 40:
        raise RecoveryError(f"commit {sha} lacks a tree SHA")
    return tree


def commit_verification(sha: str) -> dict[str, Any]:
    payload = rest("GET", f"repos/{REPOSITORY}/commits/{sha}")
    verification = ((payload or {}).get("commit") or {}).get("verification") or {}
    return {
        "verified": verification.get("verified"),
        "reason": verification.get("reason"),
        "verified_at": verification.get("verified_at"),
    }


def recover(target: dict[str, Any], base_sha: str) -> dict[str, Any]:
    number = int(target["source_pr"])
    source = rest("GET", f"repos/{REPOSITORY}/pulls/{number}")
    if not isinstance(source, dict) or source.get("state") != "open":
        raise RecoveryError(f"source PR #{number} is not open")
    source_sha = str(((source.get("head") or {}).get("sha")) or "")
    source_base = str(((source.get("base") or {}).get("sha")) or "")
    if len(source_sha) != 40 or len(source_base) != 40:
        raise RecoveryError(f"source PR #{number} lacks immutable head/base SHAs")
    if source_base != base_sha:
        raise RecoveryError(
            f"source PR #{number} base moved: source={source_base}; main={base_sha}"
        )

    branch = f"{target['branch_prefix']}-{source_sha[:12]}"
    existing = get_ref_sha(branch)
    if existing is None:
        create_ref(branch, base_sha)
        existing = base_sha
    if existing != base_sha:
        candidate_sha = existing
        reused = True
        file_inventory: list[dict[str, Any]] = []
    else:
        changes, file_inventory = build_file_changes(number, source_sha)
        mutation_input = {
            "branch": {
                "repositoryNameWithOwner": REPOSITORY,
                "refName": f"refs/heads/{branch}",
            },
            "expectedHeadOid": base_sha,
            "message": {
                "headline": str(target["headline"]),
                "body": (
                    f"{target['body']}\n\n"
                    f"Source-PR: #{number}\n"
                    f"Source-Head: {source_sha}"
                ),
            },
            "fileChanges": changes,
        }
        response = graphql(GRAPHQL_MUTATION, {"input": mutation_input})
        errors = (response or {}).get("errors")
        if errors:
            raise RecoveryError(f"createCommitOnBranch failed: {errors}")
        created = ((response or {}).get("data") or {}).get("createCommitOnBranch") or {}
        candidate_sha = str(((created.get("commit") or {}).get("oid")) or "")
        if len(candidate_sha) != 40:
            raise RecoveryError(f"createCommitOnBranch returned no commit for PR #{number}")
        reused = False

    verification = commit_verification(candidate_sha)
    if verification.get("verified") is not True:
        raise RecoveryError(
            f"recovery commit {candidate_sha} is not verified: {verification}"
        )
    source_tree = commit_tree(source_sha)
    candidate_tree = commit_tree(candidate_sha)
    if source_tree != candidate_tree:
        raise RecoveryError(
            f"tree mismatch for PR #{number}: source={source_tree}; "
            f"recovery={candidate_tree}"
        )
    return {
        "source_pr": number,
        "source_head": source_sha,
        "source_base": source_base,
        "source_tree": source_tree,
        "recovery_branch": branch,
        "recovery_commit": candidate_sha,
        "recovery_tree": candidate_tree,
        "verification": verification,
        "tree_byte_parity": True,
        "reused_existing_branch": reused,
        "changed_file_count": len(file_inventory) if file_inventory else None,
    }


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": "szl.signed-pr-recovery/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": REPOSITORY,
        "status": "NOT_VERIFIED",
        "recoveries": [],
        "boundaries": [
            "No ruleset, required check, review rule, or signature requirement is changed.",
            "Source PRs are read-only and remain open until signed replacements are independently green.",
            "Each replacement starts at the exact current main SHA and contains one GitHub-signed commit.",
            "A recovery is accepted only when GitHub verifies the signature and the source/recovery tree SHAs match.",
            "No custom secret is read or emitted; only the ephemeral workflow token is used.",
        ],
    }
    try:
        base_sha = current_main_sha()
        report["main_sha"] = base_sha
        report["recoveries"] = [recover(target, base_sha) for target in TARGETS]
        report["status"] = "RECOVERED_VERIFIED"
    except Exception as exc:  # noqa: BLE001
        report["fatal"] = f"{type(exc).__name__}: {exc}"
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
