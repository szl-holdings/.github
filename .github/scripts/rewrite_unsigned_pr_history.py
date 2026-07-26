#!/usr/bin/env python3
"""Replace exact unsigned PR histories with GitHub-signed snapshot commits.

This recovery is intentionally narrow:

* only same-repository PR branches declared in ``TARGETS_JSON`` are eligible;
* the current PR head and base must equal the declared immutable SHAs;
* a temporary branch is created from the declared base;
* GitHub GraphQL ``createCommitOnBranch`` creates one GitHub-signed commit;
* the signed commit tree must equal the original PR head tree byte-for-byte;
* the signature must be valid and reported as signed by GitHub;
* all targets are prepared and verified before any PR branch is replaced;
* each original ref is rechecked immediately before its guarded force update.

No branch-protection, ruleset, check, review, secret, or status setting is changed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "szl.signed-pr-history-recovery/v1"
SIGNED_OFF_BY = "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
SUPPORTED_FILE_STATUSES = {
    "added",
    "modified",
    "removed",
    "renamed",
    "copied",
    "changed",
}


class RecoveryError(RuntimeError):
    """Raised when a fail-closed recovery invariant is not satisfied."""


@dataclass(frozen=True)
class Target:
    number: int
    expected_head_sha: str
    expected_base_sha: str
    headline: str


@dataclass
class PreparedTarget:
    target: Target
    head_branch: str
    old_tree_sha: str
    additions: list[dict[str, str]]
    deletions: list[dict[str, str]]
    changed_paths: list[str]
    temp_branch: str
    signed_commit_sha: str | None = None
    signed_tree_sha: str | None = None
    signature: dict[str, Any] | None = None
    updated: bool = False


def _run_gh(
    arguments: list[str],
    *,
    payload: dict[str, Any] | None = None,
) -> Any:
    command = ["gh", "api", *arguments]
    process = subprocess.run(
        command,
        input=(json.dumps(payload) if payload is not None else None),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RecoveryError(
            f"GitHub API command failed ({process.returncode}): "
            f"{' '.join(command[:4])}; {detail[:2000]}"
        )
    output = process.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RecoveryError(
            f"GitHub API returned non-JSON output: {output[:1000]}"
        ) from exc


def _rest_get(path: str) -> Any:
    return _run_gh(["--method", "GET", path])


def _rest_write(method: str, path: str, payload: dict[str, Any]) -> Any:
    return _run_gh(
        ["--method", method, path, "--input", "-"],
        payload=payload,
    )


def _rest_delete(path: str) -> None:
    _run_gh(["--method", "DELETE", path])


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    result = _run_gh(
        ["graphql", "--input", "-"],
        payload={"query": query, "variables": variables},
    )
    if not isinstance(result, dict):
        raise RecoveryError("GraphQL response is not an object")
    errors = result.get("errors")
    if errors:
        raise RecoveryError(
            "GraphQL mutation failed: "
            + json.dumps(errors, sort_keys=True)[:3000]
        )
    return result


def _load_targets() -> list[Target]:
    raw = os.environ.get("TARGETS_JSON")
    if not raw:
        raise RecoveryError("TARGETS_JSON is required")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecoveryError("TARGETS_JSON is not valid JSON") from exc
    if not isinstance(values, list) or not values:
        raise RecoveryError("TARGETS_JSON must contain a non-empty list")

    targets: list[Target] = []
    seen_numbers: set[int] = set()
    for value in values:
        if not isinstance(value, dict):
            raise RecoveryError("each target must be an object")
        target = Target(
            number=int(value["number"]),
            expected_head_sha=str(value["expected_head_sha"]).lower(),
            expected_base_sha=str(value["expected_base_sha"]).lower(),
            headline=str(value["headline"]).strip(),
        )
        if target.number in seen_numbers:
            raise RecoveryError(f"duplicate target PR #{target.number}")
        if len(target.expected_head_sha) != 40 or len(target.expected_base_sha) != 40:
            raise RecoveryError(
                f"target PR #{target.number} must use full immutable SHAs"
            )
        if not target.headline or len(target.headline) > 100:
            raise RecoveryError(
                f"target PR #{target.number} headline must be 1-100 characters"
            )
        seen_numbers.add(target.number)
        targets.append(target)
    return targets


def _ref_path(branch: str) -> str:
    # GitHub's Git refs endpoint expects the complete ``heads/...`` ref path.
    return urllib.parse.quote(f"heads/{branch}", safe="/")


def _delete_temp_branch(repository: str, branch: str) -> None:
    try:
        _rest_delete(f"repos/{repository}/git/refs/{_ref_path(branch)}")
    except RecoveryError as exc:
        print(f"warning: failed to delete temporary branch {branch}: {exc}")


def _prepare_target(
    repository: str,
    target: Target,
    *,
    run_id: str,
) -> PreparedTarget:
    pr = _rest_get(f"repos/{repository}/pulls/{target.number}")
    if not isinstance(pr, dict):
        raise RecoveryError(f"PR #{target.number} response is not an object")
    if pr.get("state") != "open" or pr.get("draft") is True:
        raise RecoveryError(f"PR #{target.number} must be open and ready")

    head = pr.get("head") or {}
    base = pr.get("base") or {}
    head_sha = str(head.get("sha") or "").lower()
    base_sha = str(base.get("sha") or "").lower()
    head_repo = ((head.get("repo") or {}).get("full_name"))
    head_branch = str(head.get("ref") or "")
    if head_repo != repository:
        raise RecoveryError(
            f"PR #{target.number} head must be in {repository}, observed {head_repo}"
        )
    if head_sha != target.expected_head_sha:
        raise RecoveryError(
            f"PR #{target.number} head moved: expected "
            f"{target.expected_head_sha}, observed {head_sha}"
        )
    if base_sha != target.expected_base_sha:
        raise RecoveryError(
            f"PR #{target.number} base moved: expected "
            f"{target.expected_base_sha}, observed {base_sha}"
        )
    if not head_branch:
        raise RecoveryError(f"PR #{target.number} has no head branch")

    old_commit = _rest_get(f"repos/{repository}/git/commits/{head_sha}")
    old_tree_sha = str(((old_commit or {}).get("tree") or {}).get("sha") or "")
    if len(old_tree_sha) != 40:
        raise RecoveryError(f"PR #{target.number} old tree SHA is unavailable")

    changed_count = int(pr.get("changed_files") or 0)
    if changed_count > 100:
        raise RecoveryError(
            f"PR #{target.number} has {changed_count} files; bounded recovery supports 100"
        )
    files = _rest_get(
        f"repos/{repository}/pulls/{target.number}/files?per_page=100"
    )
    if not isinstance(files, list) or len(files) != changed_count:
        raise RecoveryError(
            f"PR #{target.number} file inventory mismatch: "
            f"expected {changed_count}, observed "
            f"{len(files) if isinstance(files, list) else 'non-list'}"
        )

    additions_by_path: dict[str, dict[str, str]] = {}
    deletions: set[str] = set()
    changed_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise RecoveryError(f"PR #{target.number} has a malformed file entry")
        status = str(item.get("status") or "")
        filename = str(item.get("filename") or "")
        if status not in SUPPORTED_FILE_STATUSES or not filename:
            raise RecoveryError(
                f"PR #{target.number} has unsupported file status: "
                f"{status!r} for {filename!r}"
            )
        changed_paths.add(filename)

        if status == "removed":
            deletions.add(filename)
            continue
        if status == "renamed":
            previous = str(item.get("previous_filename") or "")
            if not previous:
                raise RecoveryError(
                    f"PR #{target.number} renamed file lacks previous_filename"
                )
            deletions.add(previous)
            changed_paths.add(previous)

        blob_sha = str(item.get("sha") or "")
        if len(blob_sha) != 40:
            raise RecoveryError(
                f"PR #{target.number} file {filename} lacks an immutable blob SHA"
            )
        blob = _rest_get(f"repos/{repository}/git/blobs/{blob_sha}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64":
            raise RecoveryError(
                f"PR #{target.number} file {filename} did not return base64 bytes"
            )
        contents = "".join(str(blob.get("content") or "").split())
        if not contents:
            # Base64 for a zero-byte file is legitimately empty.
            if int(blob.get("size") or -1) != 0:
                raise RecoveryError(
                    f"PR #{target.number} file {filename} has empty blob content"
                )
        additions_by_path[filename] = {
            "path": filename,
            "contents": contents,
        }

    # A path recreated by the PR is an addition, not a final deletion.
    deletions.difference_update(additions_by_path)
    temp_branch = f"recovery/signed-pr-{target.number}-{run_id}"
    return PreparedTarget(
        target=target,
        head_branch=head_branch,
        old_tree_sha=old_tree_sha,
        additions=[additions_by_path[path] for path in sorted(additions_by_path)],
        deletions=[{"path": path} for path in sorted(deletions)],
        changed_paths=sorted(changed_paths),
        temp_branch=temp_branch,
    )


def _create_signed_snapshot(
    repository: str,
    prepared: PreparedTarget,
) -> None:
    target = prepared.target
    _rest_write(
        "POST",
        f"repos/{repository}/git/refs",
        {
            "ref": f"refs/heads/{prepared.temp_branch}",
            "sha": target.expected_base_sha,
        },
    )

    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit {
          oid
          url
          tree { oid }
          parents(first: 2) { nodes { oid } }
          signature {
            isValid
            state
            wasSignedByGitHub
            signer { login }
          }
        }
        ref { name }
      }
    }
    """
    body = (
        "Controlled required-signatures recovery.\n\n"
        f"PR: #{target.number}\n"
        f"Original head: {target.expected_head_sha}\n"
        f"Original tree: {prepared.old_tree_sha}\n"
        "The temporary commit is verified for exact tree parity and a valid "
        "GitHub signature before the PR branch ref is replaced.\n\n"
        f"{SIGNED_OFF_BY}"
    )
    file_changes: dict[str, Any] = {}
    if prepared.additions:
        file_changes["additions"] = prepared.additions
    if prepared.deletions:
        file_changes["deletions"] = prepared.deletions
    result = _graphql(
        mutation,
        {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": repository,
                    "branchName": prepared.temp_branch,
                },
                "expectedHeadOid": target.expected_base_sha,
                "message": {
                    "headline": target.headline,
                    "body": body,
                },
                "fileChanges": file_changes,
            }
        },
    )
    payload = ((result.get("data") or {}).get("createCommitOnBranch") or {})
    commit = payload.get("commit") or {}
    commit_sha = str(commit.get("oid") or "").lower()
    tree_sha = str((commit.get("tree") or {}).get("oid") or "").lower()
    signature = commit.get("signature") or {}
    parents = [
        str(item.get("oid") or "").lower()
        for item in ((commit.get("parents") or {}).get("nodes") or [])
        if isinstance(item, dict)
    ]

    if len(commit_sha) != 40:
        raise RecoveryError(f"PR #{target.number} signed commit SHA is unavailable")
    if parents != [target.expected_base_sha]:
        raise RecoveryError(
            f"PR #{target.number} signed commit parent mismatch: {parents}"
        )
    if tree_sha != prepared.old_tree_sha:
        raise RecoveryError(
            f"PR #{target.number} tree mismatch: original {prepared.old_tree_sha}, "
            f"signed {tree_sha}"
        )
    if (
        signature.get("isValid") is not True
        or str(signature.get("state") or "").upper() != "VALID"
        or signature.get("wasSignedByGitHub") is not True
    ):
        raise RecoveryError(
            f"PR #{target.number} commit is not validly GitHub-signed: "
            f"{json.dumps(signature, sort_keys=True)}"
        )

    prepared.signed_commit_sha = commit_sha
    prepared.signed_tree_sha = tree_sha
    prepared.signature = signature


def _recheck_all_targets(repository: str, prepared: list[PreparedTarget]) -> None:
    for item in prepared:
        pr = _rest_get(f"repos/{repository}/pulls/{item.target.number}")
        observed = str(((pr or {}).get("head") or {}).get("sha") or "").lower()
        base = str(((pr or {}).get("base") or {}).get("sha") or "").lower()
        if observed != item.target.expected_head_sha:
            raise RecoveryError(
                f"PR #{item.target.number} moved before ref replacement: "
                f"expected {item.target.expected_head_sha}, observed {observed}"
            )
        if base != item.target.expected_base_sha:
            raise RecoveryError(
                f"PR #{item.target.number} base moved before ref replacement: "
                f"expected {item.target.expected_base_sha}, observed {base}"
            )


def _replace_ref(repository: str, prepared: PreparedTarget) -> None:
    if not prepared.signed_commit_sha:
        raise RecoveryError(
            f"PR #{prepared.target.number} has no verified signed commit"
        )
    _rest_write(
        "PATCH",
        f"repos/{repository}/git/refs/{_ref_path(prepared.head_branch)}",
        {"sha": prepared.signed_commit_sha, "force": True},
    )

    # PR synchronization is eventually consistent. Bound the wait and require
    # the exact signed SHA rather than accepting any branch movement.
    observed = ""
    for _ in range(15):
        pr = _rest_get(f"repos/{repository}/pulls/{prepared.target.number}")
        observed = str(((pr or {}).get("head") or {}).get("sha") or "").lower()
        if observed == prepared.signed_commit_sha:
            break
        time.sleep(2)
    if observed != prepared.signed_commit_sha:
        raise RecoveryError(
            f"PR #{prepared.target.number} did not synchronize to signed SHA "
            f"{prepared.signed_commit_sha}; observed {observed}"
        )

    commit = _rest_get(
        f"repos/{repository}/commits/{prepared.signed_commit_sha}"
    )
    verification = ((commit or {}).get("commit") or {}).get("verification") or {}
    if verification.get("verified") is not True:
        raise RecoveryError(
            f"PR #{prepared.target.number} REST verification is not valid: "
            f"{json.dumps(verification, sort_keys=True)}"
        )
    prepared.updated = True


def _public_record(item: PreparedTarget) -> dict[str, Any]:
    return {
        "pull_request": item.target.number,
        "old_head_sha": item.target.expected_head_sha,
        "base_sha": item.target.expected_base_sha,
        "head_branch": item.head_branch,
        "old_tree_sha": item.old_tree_sha,
        "signed_commit_sha": item.signed_commit_sha,
        "signed_tree_sha": item.signed_tree_sha,
        "signature": item.signature,
        "tree_parity": item.signed_tree_sha == item.old_tree_sha,
        "changed_paths": item.changed_paths,
        "updated": item.updated,
    }


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise RecoveryError(
            f"recovery is locked to szl-holdings/.github, observed {repository!r}"
        )
    if not os.environ.get("GH_TOKEN"):
        raise RecoveryError("GH_TOKEN is required")

    targets = _load_targets()
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "local")
    report_path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/signed-pr-history-recovery.json",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    prepared: list[PreparedTarget] = []
    error: str | None = None

    try:
        # Complete every read-only preflight before creating temporary refs.
        prepared = [
            _prepare_target(repository, target, run_id=run_id)
            for target in targets
        ]

        # Prepare and cryptographically verify every replacement before moving
        # any target PR branch.
        for item in prepared:
            _create_signed_snapshot(repository, item)
        _recheck_all_targets(repository, prepared)

        # Replace only exact heads. The active required-signatures rule remains
        # unchanged and will re-evaluate the new one-commit histories.
        for item in prepared:
            _replace_ref(repository, item)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)
    finally:
        for item in prepared:
            _delete_temp_branch(repository, item.temp_branch)
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation": os.environ.get("GITHUB_SHA"),
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
            "repository": repository,
            "status": "COMPLETED" if error is None else "FAILED_CLOSED",
            "error": error,
            "targets": [_public_record(item) for item in prepared],
            "boundaries": [
                "No secret value is recorded in this report.",
                "The active required-signatures rule is not changed or bypassed.",
                "Every replacement commit is created by GitHub, signature-valid, and tree-identical to the original PR head before ref replacement.",
                "Every target head and base is rechecked against immutable expected SHAs before any ref replacement.",
            ],
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if error is None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
