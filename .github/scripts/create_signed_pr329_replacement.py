#!/usr/bin/env python3
"""Create a tree-identical GitHub-signed replacement branch for PR #329.

The source pull request is read-only. A new branch starts at the exact protected
main commit and receives one GitHub-created commit through
``createCommitOnBranch``. The branch is accepted only when GitHub reports a
valid GitHub signature, one exact parent, and byte-identical source/candidate
trees. No source ref, protected ref, ruleset, check, status, review, or secret is
modified.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPOSITORY = "szl-holdings/.github"
SOURCE_PR = 329
EXPECTED_HEAD = "e3f4bc6fc37f8b17cb389b5fb639787a26b04839"
EXPECTED_BASE = "7d6a15026edab70ca99f059897dc3bdeee10f6df"
BRANCH = f"fix/ci-health-digest-verification-v2-signed-{EXPECTED_HEAD[:12]}"
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/ci-health-digest-signed-replacement.json",
    )
)


class RecoveryError(RuntimeError):
    """Raised when a signed-replacement invariant is not satisfied."""


def run(
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
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()[:3000]
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = stdout[:3000]
    if process.returncode and not allow_failure:
        raise RecoveryError(
            f"GitHub API failed ({process.returncode}): {stderr or parsed}"
        )
    return process.returncode, parsed, stderr


def rest_get(path: str) -> Any:
    return run(["--method", "GET", path])[1]


def rest_write(method: str, path: str, payload: dict[str, Any]) -> Any:
    return run(["--method", method, path, "--input", "-"], payload=payload)[1]


def get_ref(branch: str) -> str | None:
    encoded = quote(f"heads/{branch}", safe="/")
    code, payload, error = run(
        ["--method", "GET", f"repos/{REPOSITORY}/git/ref/{encoded}"],
        allow_failure=True,
    )
    if code:
        text = f"{error} {payload}".lower()
        if "404" in text or "not found" in text:
            return None
        raise RecoveryError(f"could not read replacement branch: {error or payload}")
    sha = str(((payload or {}).get("object") or {}).get("sha") or "")
    if len(sha) != 40:
        raise RecoveryError("replacement branch ref lacks an immutable SHA")
    return sha


def source_pr() -> dict[str, Any]:
    value = rest_get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}")
    if not isinstance(value, dict):
        raise RecoveryError("source PR response is not an object")
    head = value.get("head") or {}
    base = value.get("base") or {}
    if value.get("state") != "open" or value.get("draft") is True:
        raise RecoveryError("source PR must be open and ready")
    if ((head.get("repo") or {}).get("full_name")) != REPOSITORY:
        raise RecoveryError("source PR is not a same-repository branch")
    if str(head.get("sha") or "").lower() != EXPECTED_HEAD:
        raise RecoveryError("source PR head moved")
    if str(base.get("sha") or "").lower() != EXPECTED_BASE:
        raise RecoveryError("source PR base moved")
    return value


def source_files() -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    values = rest_get(
        f"repos/{REPOSITORY}/pulls/{SOURCE_PR}/files?per_page=100"
    )
    if not isinstance(values, list):
        raise RecoveryError("source PR file inventory is not a list")
    if not values or len(values) > 100:
        raise RecoveryError(
            f"source PR file count is outside the bounded envelope: {len(values)}"
        )
    additions: list[dict[str, str]] = []
    deletions: list[dict[str, str]] = []
    paths: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            raise RecoveryError("source PR contains a malformed file entry")
        status = str(item.get("status") or "")
        path = str(item.get("filename") or "")
        previous = str(item.get("previous_filename") or "")
        if not path:
            raise RecoveryError("source PR file entry has no path")
        paths.append(path)
        if status == "removed":
            deletions.append({"path": path})
            continue
        if status == "renamed":
            if not previous:
                raise RecoveryError(f"renamed file {path} lacks previous path")
            deletions.append({"path": previous})
        if status not in {"added", "modified", "changed", "copied", "renamed"}:
            raise RecoveryError(f"unsupported file status {status!r} for {path}")
        blob_sha = str(item.get("sha") or "")
        if len(blob_sha) != 40:
            raise RecoveryError(f"file {path} lacks an immutable blob SHA")
        blob = rest_get(f"repos/{REPOSITORY}/git/blobs/{blob_sha}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64":
            raise RecoveryError(f"file {path} did not return base64 bytes")
        contents = "".join(str(blob.get("content") or "").split())
        if not contents and int(blob.get("size") or -1) != 0:
            raise RecoveryError(f"file {path} returned empty non-zero blob content")
        additions.append({"path": path, "contents": contents})
    add_paths = {item["path"] for item in additions}
    deletions = [item for item in deletions if item["path"] not in add_paths]
    changes: dict[str, list[dict[str, str]]] = {}
    if additions:
        changes["additions"] = sorted(additions, key=lambda item: item["path"])
    if deletions:
        changes["deletions"] = sorted(deletions, key=lambda item: item["path"])
    return changes, sorted(set(paths))


def commit_tree(sha: str) -> str:
    value = rest_get(f"repos/{REPOSITORY}/git/commits/{sha}")
    tree = str(((value or {}).get("tree") or {}).get("sha") or "")
    if len(tree) != 40:
        raise RecoveryError(f"commit {sha} lacks an immutable tree")
    return tree


def commit_receipt(sha: str) -> dict[str, Any]:
    value = rest_get(f"repos/{REPOSITORY}/commits/{sha}")
    if not isinstance(value, dict):
        raise RecoveryError("candidate commit response is not an object")
    verification = ((value.get("commit") or {}).get("verification") or {})
    parents = [
        str(item.get("sha") or "")
        for item in value.get("parents") or []
        if isinstance(item, dict)
    ]
    return {
        "verified": verification.get("verified"),
        "reason": verification.get("reason"),
        "verified_at": verification.get("verified_at"),
        "parents": parents,
    }


def create_signed_commit(changes: dict[str, Any]) -> str:
    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid }
        ref { name target { oid } }
      }
    }
    """
    payload = {
        "query": mutation,
        "variables": {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": REPOSITORY,
                    "branchName": BRANCH,
                },
                "expectedHeadOid": EXPECTED_BASE,
                "message": {
                    "headline": "fix(ci): make organization health digest fail closed",
                    "body": (
                        "Tree-identical, GitHub-signed replacement for PR #329.\n\n"
                        f"Source-PR: #{SOURCE_PR}\n"
                        f"Source-Head: {EXPECTED_HEAD}\n\n"
                        "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                    ),
                },
                "fileChanges": changes,
            }
        },
    }
    response = run(["graphql", "--input", "-"], payload=payload)[1]
    errors = (response or {}).get("errors") if isinstance(response, dict) else None
    if errors:
        raise RecoveryError(f"createCommitOnBranch returned errors: {errors}")
    created = ((response or {}).get("data") or {}).get("createCommitOnBranch") or {}
    sha = str(((created.get("commit") or {}).get("oid")) or "")
    if len(sha) != 40:
        raise RecoveryError("createCommitOnBranch returned no immutable commit")
    return sha


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": "szl.signed-pr-replacement/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "source_pr": SOURCE_PR,
        "source_head": EXPECTED_HEAD,
        "source_base": EXPECTED_BASE,
        "replacement_branch": BRANCH,
        "status": "FAILED_CLOSED",
        "boundaries": [
            "The source pull request and source branch are read-only.",
            "No protected ref, rule, status, review, check result, or secret is changed.",
            "The replacement starts at the exact source base and contains one GitHub-created commit.",
            "A valid GitHub signature, one exact parent, and source/candidate tree parity are mandatory.",
        ],
    }
    try:
        source_pr()
        changes, paths = source_files()
        source_tree = commit_tree(EXPECTED_HEAD)
        existing = get_ref(BRANCH)
        if existing is None:
            rest_write(
                "POST",
                f"repos/{REPOSITORY}/git/refs",
                {"ref": f"refs/heads/{BRANCH}", "sha": EXPECTED_BASE},
            )
            existing = EXPECTED_BASE
        if existing == EXPECTED_BASE:
            candidate = create_signed_commit(changes)
            reused = False
        else:
            candidate = existing
            reused = True
        receipt = commit_receipt(candidate)
        candidate_tree = commit_tree(candidate)
        if receipt["verified"] is not True:
            raise RecoveryError(f"candidate signature is not verified: {receipt}")
        if receipt["parents"] != [EXPECTED_BASE]:
            raise RecoveryError(
                f"candidate parents are not the exact base: {receipt['parents']}"
            )
        if candidate_tree != source_tree:
            raise RecoveryError(
                f"tree mismatch: source={source_tree}; candidate={candidate_tree}"
            )
        report.update(
            {
                "status": "SIGNED_REPLACEMENT_VERIFIED",
                "changed_paths": paths,
                "source_tree": source_tree,
                "replacement_commit": candidate,
                "replacement_tree": candidate_tree,
                "signature": receipt,
                "tree_parity": True,
                "reused_existing_branch": reused,
            }
        )
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
