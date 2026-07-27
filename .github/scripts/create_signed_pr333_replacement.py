#!/usr/bin/env python3
"""Create one GitHub-signed, exact-tree replacement for PR #333.

This controller changes no source bytes. It reads the immutable PR file set,
reconstructs that exact tree on one branch whose parent is the exact protected
main base, creates the commit through GitHub's ``createCommitOnBranch``
mutation, and verifies tree parity, parentage, and GitHub signature.

It never merges, enqueues, publishes statuses, edits checks or reviews, changes
rulesets or protections, or reads or records a credential value.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPOSITORY = "szl-holdings/.github"
SOURCE_PR = 333
SOURCE_HEAD = "ba8d7537960a730d6b2ff78853cfd0ab1254fa61"
SOURCE_BASE = "8b5a09fa05cc98768b4d6004db52972b91b160b3"
TARGET_BRANCH = "fix/ci-health-default-branch-evidence-v1-signed-ba8d7537960a"
REPORT_SCHEMA = "szl.signed-tree-normalization/v1"
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/pr333-signed-tree-normalization.json",
    )
)


class NormalizationError(RuntimeError):
    """Raised when an immutable source or signed-result invariant fails."""


def api(
    arguments: list[str],
    *,
    payload: dict[str, Any] | None = None,
    allow_failure: bool = False,
) -> tuple[int, Any, str]:
    process = subprocess.run(
        ["gh", "api", *arguments],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    raw = process.stdout.strip()
    try:
        parsed: Any = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw[:3000]
    error = process.stderr.strip()[:3000]
    if process.returncode and not allow_failure:
        raise NormalizationError(
            f"GitHub API failed ({process.returncode}): {error or parsed}"
        )
    return process.returncode, parsed, error


def get(path: str) -> Any:
    return api(["--method", "GET", path])[1]


def write(method: str, path: str, body: dict[str, Any]) -> Any:
    return api(
        ["--method", method, path, "--input", "-"],
        payload=body,
    )[1]


def require_sha(value: object, label: str) -> str:
    sha = str(value or "").lower()
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise NormalizationError(f"{label} is not an immutable SHA: {sha!r}")
    return sha


def source_pr() -> dict[str, Any]:
    value = get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}")
    if not isinstance(value, dict):
        raise NormalizationError("source PR response is not an object")
    head = value.get("head") or {}
    base = value.get("base") or {}
    if value.get("state") != "open" or value.get("draft") is True:
        raise NormalizationError("source PR must remain open and non-draft")
    if ((head.get("repo") or {}).get("full_name")) != REPOSITORY:
        raise NormalizationError("source PR is not a same-repository branch")
    if require_sha(head.get("sha"), "source PR head") != SOURCE_HEAD:
        raise NormalizationError("source PR head moved")
    if require_sha(base.get("sha"), "source PR base") != SOURCE_BASE:
        raise NormalizationError("source PR base moved")
    if base.get("ref") != "main":
        raise NormalizationError("source PR no longer targets main")
    return value


def commit_tree(sha: str) -> str:
    value = get(f"repos/{REPOSITORY}/git/commits/{sha}")
    if not isinstance(value, dict):
        raise NormalizationError(f"commit {sha} response is not an object")
    return require_sha((value.get("tree") or {}).get("sha"), f"tree for {sha}")


def source_file_changes() -> tuple[dict[str, bytes], list[str], list[dict[str, Any]]]:
    values = get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}/files?per_page=100")
    if not isinstance(values, list) or not values or len(values) > 100:
        raise NormalizationError("source PR file inventory is outside the bounded envelope")
    additions: dict[str, bytes] = {}
    deletions: list[str] = []
    inventory: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            raise NormalizationError("source PR contains a malformed file entry")
        path = str(item.get("filename") or "")
        status = str(item.get("status") or "")
        previous = str(item.get("previous_filename") or "")
        if not path or path in seen:
            raise NormalizationError(f"invalid or duplicate source path: {path!r}")
        seen.add(path)
        if path.startswith("/") or ".." in path.split("/"):
            raise NormalizationError(f"unsafe source path: {path!r}")
        if status == "removed":
            deletions.append(path)
            inventory.append({"path": path, "status": status})
            continue
        if status == "renamed":
            if not previous:
                raise NormalizationError(f"renamed path {path!r} lacks previous path")
            deletions.append(previous)
        if status not in {"added", "modified", "changed", "copied", "renamed"}:
            raise NormalizationError(f"unsupported status {status!r} for {path}")
        blob_sha = require_sha(item.get("sha"), f"blob for {path}")
        blob = get(f"repos/{REPOSITORY}/git/blobs/{blob_sha}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64":
            raise NormalizationError(f"source file {path} did not return base64")
        encoded = "".join(str(blob.get("content") or "").split())
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise NormalizationError(f"source file {path} is not valid base64") from exc
        additions[path] = content
        inventory.append(
            {
                "path": path,
                "status": status,
                "blob_sha": blob_sha,
                "size": len(content),
            }
        )
    if set(additions) & set(deletions):
        raise NormalizationError("a path is both added and deleted")
    return additions, sorted(set(deletions)), inventory


def ref_sha(branch: str) -> str | None:
    encoded = quote(f"heads/{branch}", safe="/")
    code, payload, error = api(
        ["--method", "GET", f"repos/{REPOSITORY}/git/ref/{encoded}"],
        allow_failure=True,
    )
    if code:
        text = f"{error} {payload}".lower()
        if "404" in text or "not found" in text:
            return None
        raise NormalizationError(f"could not read target branch: {error or payload}")
    return require_sha(((payload or {}).get("object") or {}).get("sha"), "target branch head")


def ensure_target_branch() -> str:
    observed = ref_sha(TARGET_BRANCH)
    if observed is None:
        value = write(
            "POST",
            f"repos/{REPOSITORY}/git/refs",
            {"ref": f"refs/heads/{TARGET_BRANCH}", "sha": SOURCE_BASE},
        )
        observed = require_sha(((value or {}).get("object") or {}).get("sha"), "created branch head")
    if observed != SOURCE_BASE:
        return observed
    return observed


def create_signed_commit(additions: dict[str, bytes], deletions: list[str]) -> str:
    file_changes: dict[str, Any] = {
        "additions": [
            {
                "path": path,
                "contents": base64.b64encode(content).decode("ascii"),
            }
            for path, content in sorted(additions.items())
        ]
    }
    if deletions:
        file_changes["deletions"] = [{"path": path} for path in deletions]
    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid }
        ref { name }
      }
    }
    """
    response = api(
        ["graphql", "--input", "-"],
        payload={
            "query": mutation,
            "variables": {
                "input": {
                    "branch": {
                        "repositoryNameWithOwner": REPOSITORY,
                        "branchName": TARGET_BRANCH,
                    },
                    "expectedHeadOid": SOURCE_BASE,
                    "message": {
                        "headline": "fix(ci): bind organization health to protected default branches",
                        "body": (
                            f"Tree-identical signed normalization of PR #{SOURCE_PR}.\n\n"
                            f"Source-Head: {SOURCE_HEAD}\n"
                            f"Source-Base: {SOURCE_BASE}\n\n"
                            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                        ),
                    },
                    "fileChanges": file_changes,
                }
            },
        },
    )[1]
    errors = response.get("errors") if isinstance(response, dict) else None
    if errors:
        raise NormalizationError(f"createCommitOnBranch returned errors: {errors}")
    created = ((response or {}).get("data") or {}).get("createCommitOnBranch") or {}
    return require_sha((created.get("commit") or {}).get("oid"), "created commit")


def commit_receipt(sha: str) -> dict[str, Any]:
    value = get(f"repos/{REPOSITORY}/commits/{sha}")
    if not isinstance(value, dict):
        raise NormalizationError("candidate commit response is not an object")
    verification = ((value.get("commit") or {}).get("verification") or {})
    parents = [
        require_sha(item.get("sha"), "candidate parent")
        for item in value.get("parents") or []
        if isinstance(item, dict)
    ]
    return {
        "sha": sha,
        "tree": commit_tree(sha),
        "parents": parents,
        "verified": verification.get("verified"),
        "reason": verification.get("reason"),
        "verified_at": verification.get("verified_at"),
        "author": ((value.get("commit") or {}).get("author") or {}).get("name"),
        "committer": ((value.get("commit") or {}).get("committer") or {}).get("name"),
    }


def verify_candidate(sha: str, expected_tree: str) -> dict[str, Any]:
    receipt = commit_receipt(sha)
    if receipt["tree"] != expected_tree:
        raise NormalizationError(
            f"tree mismatch: source={expected_tree}; candidate={receipt['tree']}"
        )
    if receipt["parents"] != [SOURCE_BASE]:
        raise NormalizationError(
            f"candidate parent mismatch: {receipt['parents']}"
        )
    if receipt["verified"] is not True or receipt["reason"] != "valid":
        raise NormalizationError(
            f"candidate signature is not valid: {receipt['verified']}/{receipt['reason']}"
        )
    if ref_sha(TARGET_BRANCH) != sha:
        raise NormalizationError("target branch does not point at the candidate")
    return receipt


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "source_pr": SOURCE_PR,
        "source_head": SOURCE_HEAD,
        "source_base": SOURCE_BASE,
        "target_branch": TARGET_BRANCH,
        "status": "FAILED_CLOSED",
        "credential_value_recorded": False,
        "boundaries": [
            "The source PR and source branch are read-only.",
            "The candidate must have exact source-tree parity and exact protected-main parentage.",
            "Only GitHub createCommitOnBranch may create the replacement commit.",
            "No merge, queue, status, check, review, ruleset, protection, secret, or deployment mutation occurs.",
        ],
    }
    error: str | None = None
    try:
        source_pr()
        expected_tree = commit_tree(SOURCE_HEAD)
        additions, deletions, inventory = source_file_changes()
        report["source_tree"] = expected_tree
        report["file_inventory"] = inventory
        report["deletions"] = deletions
        branch_head = ensure_target_branch()
        candidate = branch_head
        if branch_head == SOURCE_BASE:
            candidate = create_signed_commit(additions, deletions)
            report["created"] = True
        else:
            report["created"] = False
        report["candidate"] = verify_candidate(candidate, expected_tree)
        report["status"] = "SIGNED_TREE_IDENTICAL"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        report["error"] = error
        print(error, file=sys.stderr)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
