#!/usr/bin/env python3
"""Create a one-commit GitHub-signed branch that addresses PR #330 review.

The source PR remains read-only. Exactly two unused imports and one dead initial
assignment are removed from ``ci_health_digest.py``. The one unit test that
previously instantiated the imported type through that implementation module is
updated to instantiate it from its owning HTTP module. All other source bytes
are copied from the reviewed PR head. Candidate modules and tests execute before
the signed commit is created.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPOSITORY = "szl-holdings/.github"
SOURCE_PR = 330
SOURCE_HEAD = "7e1b59748b58bf7093b1b36dc9036ffbb03c7d10"
SOURCE_BASE = "7d6a15026edab70ca99f059897dc3bdeee10f6df"
TARGET_PATH = ".github/scripts/ci_health_digest.py"
TEST_PATH = ".github/scripts/test_ci_health_digest.py"
ALLOWED_DIFF_PATHS = {TARGET_PATH, TEST_PATH}
BRANCH = f"fix/ci-health-digest-review-fixed-{SOURCE_HEAD[:12]}"
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/ci-health-digest-review-fixed-signed.json",
    )
)


class ReviewFixError(RuntimeError):
    """Raised when the bounded review-fix envelope is violated."""


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
        raise ReviewFixError(
            f"GitHub API failed ({process.returncode}): {error or parsed}"
        )
    return process.returncode, parsed, error


def get(path: str) -> Any:
    return api(["--method", "GET", path])[1]


def write(method: str, path: str, body: dict[str, Any]) -> Any:
    return api(["--method", method, path, "--input", "-"], payload=body)[1]


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
        raise ReviewFixError(f"could not read branch: {error or payload}")
    sha = str(((payload or {}).get("object") or {}).get("sha") or "")
    if len(sha) != 40:
        raise ReviewFixError("branch ref lacks an immutable SHA")
    return sha


def verify_source_pr() -> None:
    value = get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}")
    if not isinstance(value, dict):
        raise ReviewFixError("source PR response is not an object")
    head = value.get("head") or {}
    base = value.get("base") or {}
    if value.get("state") != "open" or value.get("draft") is True:
        raise ReviewFixError("source PR must remain open and ready")
    if ((head.get("repo") or {}).get("full_name")) != REPOSITORY:
        raise ReviewFixError("source PR is not a same-repository branch")
    if str(head.get("sha") or "").lower() != SOURCE_HEAD:
        raise ReviewFixError("source PR head moved")
    if str(base.get("sha") or "").lower() != SOURCE_BASE:
        raise ReviewFixError("source PR base moved")


def source_files() -> tuple[dict[str, bytes], list[str]]:
    values = get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}/files?per_page=100")
    if not isinstance(values, list) or not values or len(values) > 100:
        raise ReviewFixError("source PR file inventory is outside the bounded envelope")
    files: dict[str, bytes] = {}
    removed: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            raise ReviewFixError("source PR contains a malformed file entry")
        status = str(item.get("status") or "")
        path = str(item.get("filename") or "")
        previous = str(item.get("previous_filename") or "")
        if not path:
            raise ReviewFixError("source file entry has no path")
        if status == "removed":
            removed.append(path)
            continue
        if status == "renamed":
            if not previous:
                raise ReviewFixError(f"renamed path {path} lacks previous path")
            removed.append(previous)
        if status not in {"added", "modified", "changed", "copied", "renamed"}:
            raise ReviewFixError(f"unsupported status {status!r} for {path}")
        blob_sha = str(item.get("sha") or "")
        if len(blob_sha) != 40:
            raise ReviewFixError(f"source file {path} lacks a blob SHA")
        blob = get(f"repos/{REPOSITORY}/git/blobs/{blob_sha}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64":
            raise ReviewFixError(f"source file {path} did not return base64")
        encoded = "".join(str(blob.get("content") or "").split())
        try:
            files[path] = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ReviewFixError(f"source file {path} is not valid base64") from exc
    missing = sorted(ALLOWED_DIFF_PATHS - set(files))
    if missing:
        raise ReviewFixError(f"source PR lacks required review-fix paths: {missing}")
    return files, sorted(set(removed))


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise ReviewFixError(
            f"expected exactly one {label} marker, observed {text.count(old)}"
        )
    return text.replace(old, new, 1)


def apply_review_fixes(files: dict[str, bytes]) -> dict[str, Any]:
    try:
        implementation = files[TARGET_PATH].decode("utf-8")
        tests = files[TEST_PATH].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewFixError("review-fix source is not UTF-8") from exc

    source_hashes = {
        path: hashlib.sha256(files[path]).hexdigest()
        for path in sorted(ALLOWED_DIFF_PATHS)
    }
    for marker in ("    ReaderSelection,\n", "    list_repositories,\n"):
        implementation = replace_once(
            implementation,
            marker,
            "",
            label=f"unused import {marker.strip()}",
        )
    dead = "    exit_code = 2\n"
    if implementation.count(dead) != 2:
        raise ReviewFixError(
            "expected one dead initialization and one live failure assignment"
        )
    implementation = implementation.replace(dead, "", 1)
    if implementation.count(dead) != 1:
        raise ReviewFixError("review fix removed the live failure assignment")

    tests = replace_once(
        tests,
        "        selected = chd.ReaderSelection(\n",
        "        selected = http.ReaderSelection(\n",
        label="ReaderSelection ownership test",
    )
    files[TARGET_PATH] = implementation.encode("utf-8")
    files[TEST_PATH] = tests.encode("utf-8")
    return {
        "removed_unused_imports": ["ReaderSelection", "list_repositories"],
        "removed_dead_initialization": True,
        "updated_type_owner_reference": "chd.ReaderSelection -> http.ReaderSelection",
        "source_sha256": source_hashes,
        "corrected_sha256": {
            path: hashlib.sha256(files[path]).hexdigest()
            for path in sorted(ALLOWED_DIFF_PATHS)
        },
    }


def run_candidate_tests(files: dict[str, bytes]) -> dict[str, Any]:
    root = Path("/tmp/ci-health-digest-review-candidate")
    if root.exists():
        subprocess.run(["rm", "-rf", str(root)], check=True)
    for path, content in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    scripts = root / ".github/scripts"
    compile_paths = [
        scripts / "ci_health_digest.py",
        scripts / "ci_health_digest_http.py",
        scripts / "ci_health_digest_sweep.py",
        scripts / "test_ci_health_digest.py",
    ]
    compile_process = subprocess.run(
        ["python", "-m", "py_compile", *map(str, compile_paths)],
        capture_output=True,
        text=True,
        check=False,
    )
    if compile_process.returncode:
        raise ReviewFixError(
            f"candidate compilation failed: {compile_process.stderr[:2000]}"
        )
    test_process = subprocess.run(
        ["python", str(scripts / "test_ci_health_digest.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if test_process.returncode:
        raise ReviewFixError(
            f"candidate tests failed: {(test_process.stderr or test_process.stdout)[:3000]}"
        )
    output = test_process.stderr or test_process.stdout
    if "Ran 13 tests" not in output or "OK" not in output:
        raise ReviewFixError("candidate test runner did not prove all 13 tests")
    return {
        "python_compile": "passed",
        "unit_tests": "passed",
        "test_count": 13,
        "test_output_tail": output[-1000:],
    }


def commit_tree(sha: str) -> str:
    value = get(f"repos/{REPOSITORY}/git/commits/{sha}")
    tree = str(((value or {}).get("tree") or {}).get("sha") or "")
    if len(tree) != 40:
        raise ReviewFixError(f"commit {sha} lacks an immutable tree")
    return tree


def commit_receipt(sha: str) -> dict[str, Any]:
    value = get(f"repos/{REPOSITORY}/commits/{sha}")
    verification = ((value or {}).get("commit") or {}).get("verification") or {}
    parents = [
        str(item.get("sha") or "")
        for item in (value or {}).get("parents") or []
        if isinstance(item, dict)
    ]
    return {
        "verified": verification.get("verified"),
        "reason": verification.get("reason"),
        "verified_at": verification.get("verified_at"),
        "parents": parents,
    }


def create_signed_commit(files: dict[str, bytes], removed: list[str]) -> str:
    additions = [
        {
            "path": path,
            "contents": base64.b64encode(content).decode("ascii"),
        }
        for path, content in sorted(files.items())
    ]
    file_changes: dict[str, Any] = {"additions": additions}
    add_paths = set(files)
    deletions = [{"path": path} for path in removed if path not in add_paths]
    if deletions:
        file_changes["deletions"] = deletions
    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) { commit { oid } ref { name } }
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
                        "branchName": BRANCH,
                    },
                    "expectedHeadOid": SOURCE_BASE,
                    "message": {
                        "headline": "fix(ci): make organization health digest fail closed",
                        "body": (
                            "Addresses both actionable review threads from PR #330 "
                            "and updates the dependent test to use the owning type.\n\n"
                            f"Source-PR: #{SOURCE_PR}\n"
                            f"Source-Head: {SOURCE_HEAD}\n\n"
                            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                        ),
                    },
                    "fileChanges": file_changes,
                }
            },
        },
    )[1]
    errors = (response or {}).get("errors") if isinstance(response, dict) else None
    if errors:
        raise ReviewFixError(f"createCommitOnBranch returned errors: {errors}")
    created = ((response or {}).get("data") or {}).get("createCommitOnBranch") or {}
    sha = str(((created.get("commit") or {}).get("oid")) or "")
    if len(sha) != 40:
        raise ReviewFixError("createCommitOnBranch returned no immutable commit")
    return sha


def compare_source_candidate(candidate: str) -> list[dict[str, Any]]:
    value = get(f"repos/{REPOSITORY}/compare/{SOURCE_HEAD}...{candidate}")
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, list):
        raise ReviewFixError("source/candidate comparison has no file inventory")
    compact = [
        {
            "filename": item.get("filename"),
            "status": item.get("status"),
            "additions": item.get("additions"),
            "deletions": item.get("deletions"),
        }
        for item in files
        if isinstance(item, dict)
    ]
    observed = {str(item.get("filename")) for item in compact}
    if observed != ALLOWED_DIFF_PATHS:
        raise ReviewFixError(
            f"source/candidate diff escaped the reviewed paths: {compact}"
        )
    return sorted(compact, key=lambda item: str(item.get("filename")))


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": "szl.signed-review-fix/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "source_pr": SOURCE_PR,
        "source_head": SOURCE_HEAD,
        "source_base": SOURCE_BASE,
        "replacement_branch": BRANCH,
        "status": "FAILED_CLOSED",
        "boundaries": [
            "The source pull request and branch are read-only.",
            "Only two unused imports, one dead initialization, and the dependent type-owner test reference may change.",
            "Candidate compilation and all 13 unit tests must pass before commit creation.",
            "The replacement must be GitHub-signed with the exact protected-main parent.",
            "The source/candidate comparison must contain exactly the two reviewed Python paths.",
            "No rule, protection, review, status, check result, secret, or protected ref is changed.",
        ],
    }
    try:
        verify_source_pr()
        files, removed = source_files()
        fix_receipt = apply_review_fixes(files)
        tests = run_candidate_tests(files)
        existing = ref_sha(BRANCH)
        if existing is None:
            write(
                "POST",
                f"repos/{REPOSITORY}/git/refs",
                {"ref": f"refs/heads/{BRANCH}", "sha": SOURCE_BASE},
            )
            existing = SOURCE_BASE
        if existing == SOURCE_BASE:
            candidate = create_signed_commit(files, removed)
            reused = False
        else:
            candidate = existing
            reused = True
        signature = commit_receipt(candidate)
        if signature["verified"] is not True:
            raise ReviewFixError(f"candidate signature is not verified: {signature}")
        if signature["parents"] != [SOURCE_BASE]:
            raise ReviewFixError(f"candidate parent mismatch: {signature['parents']}")
        comparison = compare_source_candidate(candidate)
        report.update(
            {
                "status": "SIGNED_REVIEW_FIX_VERIFIED",
                "replacement_commit": candidate,
                "replacement_tree": commit_tree(candidate),
                "source_tree": commit_tree(SOURCE_HEAD),
                "signature": signature,
                "review_fix": fix_receipt,
                "candidate_tests": tests,
                "source_candidate_diff": comparison,
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
