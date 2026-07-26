#!/usr/bin/env python3
"""Verify the existing signed PR #330 review-fix branch without mutation."""
from __future__ import annotations

import base64
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
CANDIDATE_BRANCH = "fix/ci-health-digest-review-fixed-7e1b59748b58"
TARGET_PATH = ".github/scripts/ci_health_digest.py"
TEST_PATH = ".github/scripts/test_ci_health_digest.py"
ALLOWED_TREE_DIFFS = {TARGET_PATH, TEST_PATH}
PYTHON_PATHS = (
    TARGET_PATH,
    ".github/scripts/ci_health_digest_http.py",
    ".github/scripts/ci_health_digest_sweep.py",
    TEST_PATH,
)
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/ci-health-digest-review-fix-verification.json",
    )
)


class VerificationError(RuntimeError):
    """Raised when a signed review-fix invariant is not satisfied."""


def api(arguments: list[str]) -> Any:
    process = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if process.returncode:
        detail = process.stderr.strip() or process.stdout.strip()
        raise VerificationError(
            f"GitHub API failed ({process.returncode}): {detail[:3000]}"
        )
    raw = process.stdout.strip()
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise VerificationError("GitHub API returned non-JSON output") from exc


def get(path: str) -> Any:
    return api(["--method", "GET", path])


def branch_sha(branch: str) -> str:
    encoded = quote(f"heads/{branch}", safe="/")
    value = get(f"repos/{REPOSITORY}/git/ref/{encoded}")
    sha = str(((value or {}).get("object") or {}).get("sha") or "")
    if len(sha) != 40:
        raise VerificationError("candidate branch lacks an immutable head SHA")
    return sha


def commit_receipt(sha: str) -> dict[str, Any]:
    value = get(f"repos/{REPOSITORY}/commits/{sha}")
    if not isinstance(value, dict):
        raise VerificationError("candidate commit response is not an object")
    verification = ((value.get("commit") or {}).get("verification") or {})
    return {
        "verified": verification.get("verified"),
        "reason": verification.get("reason"),
        "verified_at": verification.get("verified_at"),
        "parents": [
            str(item.get("sha") or "")
            for item in value.get("parents") or []
            if isinstance(item, dict)
        ],
    }


def tree_sha(commit_sha: str) -> str:
    value = get(f"repos/{REPOSITORY}/git/commits/{commit_sha}")
    sha = str(((value or {}).get("tree") or {}).get("sha") or "")
    if len(sha) != 40:
        raise VerificationError(f"commit {commit_sha} lacks an immutable tree")
    return sha


def tree_map(commit_sha: str) -> tuple[str, dict[str, tuple[str, str, str]]]:
    root = tree_sha(commit_sha)
    value = get(f"repos/{REPOSITORY}/git/trees/{root}?recursive=1")
    if not isinstance(value, dict) or value.get("truncated") is True:
        raise VerificationError(f"tree inventory for {commit_sha} is unavailable or truncated")
    entries = value.get("tree")
    if not isinstance(entries, list):
        raise VerificationError(f"tree inventory for {commit_sha} is malformed")
    mapping: dict[str, tuple[str, str, str]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise VerificationError("tree inventory contains a malformed entry")
        path = str(item.get("path") or "")
        kind = str(item.get("type") or "")
        mode = str(item.get("mode") or "")
        sha = str(item.get("sha") or "")
        if not path or len(sha) != 40:
            raise VerificationError("tree inventory entry lacks a path or SHA")
        mapping[path] = (kind, mode, sha)
    return root, mapping


def blob_bytes(blob_sha: str) -> bytes:
    value = get(f"repos/{REPOSITORY}/git/blobs/{blob_sha}")
    if not isinstance(value, dict) or value.get("encoding") != "base64":
        raise VerificationError(f"blob {blob_sha} did not return base64 content")
    encoded = "".join(str(value.get("content") or "").split())
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise VerificationError(f"blob {blob_sha} contains invalid base64") from exc


def verify_source_pr() -> None:
    value = get(f"repos/{REPOSITORY}/pulls/{SOURCE_PR}")
    if not isinstance(value, dict):
        raise VerificationError("source PR response is not an object")
    head = value.get("head") or {}
    base = value.get("base") or {}
    if value.get("state") != "open" or value.get("draft") is True:
        raise VerificationError("source PR must remain open and ready")
    if str(head.get("sha") or "").lower() != SOURCE_HEAD:
        raise VerificationError("source PR head moved")
    if str(base.get("sha") or "").lower() != SOURCE_BASE:
        raise VerificationError("source PR base moved")


def direct_tree_diff(
    source: dict[str, tuple[str, str, str]],
    candidate: dict[str, tuple[str, str, str]],
) -> dict[str, dict[str, Any]]:
    differences: dict[str, dict[str, Any]] = {}
    for path in sorted(set(source) | set(candidate)):
        if source.get(path) == candidate.get(path):
            continue
        differences[path] = {
            "source": source.get(path),
            "candidate": candidate.get(path),
        }
    return differences


def verify_review_content(candidate_tree: dict[str, tuple[str, str, str]]) -> dict[str, Any]:
    files: dict[str, bytes] = {}
    for path in PYTHON_PATHS:
        entry = candidate_tree.get(path)
        if entry is None or entry[0] != "blob":
            raise VerificationError(f"candidate tree lacks Python file {path}")
        files[path] = blob_bytes(entry[2])
    try:
        implementation = files[TARGET_PATH].decode("utf-8")
        tests = files[TEST_PATH].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError("candidate Python files are not UTF-8") from exc

    if "    ReaderSelection,\n" in implementation:
        raise VerificationError("unused ReaderSelection import remains")
    if "    list_repositories,\n" in implementation:
        raise VerificationError("unused list_repositories import remains")
    if implementation.count("    exit_code = 2\n") != 1:
        raise VerificationError("candidate does not retain exactly one failure assignment")
    if tests.count("        selected = http.ReaderSelection(\n") != 1:
        raise VerificationError("dependent test does not use the owning HTTP type")
    if "        selected = chd.ReaderSelection(\n" in tests:
        raise VerificationError("dependent test still relies on the removed re-export")

    root = Path("/tmp/ci-health-digest-review-verification")
    if root.exists():
        subprocess.run(["rm", "-rf", str(root)], check=True)
    for path, content in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    scripts = root / ".github/scripts"
    compile_process = subprocess.run(
        [
            "python",
            "-m",
            "py_compile",
            *[str(root / path) for path in PYTHON_PATHS],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if compile_process.returncode:
        raise VerificationError(
            f"candidate compilation failed: {compile_process.stderr[:2000]}"
        )
    test_process = subprocess.run(
        ["python", str(scripts / "test_ci_health_digest.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = test_process.stderr or test_process.stdout
    if test_process.returncode or "Ran 13 tests" not in output or "OK" not in output:
        raise VerificationError(f"candidate tests failed: {output[:3000]}")
    return {
        "removed_unused_imports": ["ReaderSelection", "list_repositories"],
        "failure_assignment_count": 1,
        "dependent_test_type_owner": "http.ReaderSelection",
        "python_compile": "passed",
        "unit_tests": "passed",
        "test_count": 13,
        "test_output_tail": output[-1000:],
    }


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": "szl.signed-review-fix-verification/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "source_pr": SOURCE_PR,
        "source_head": SOURCE_HEAD,
        "source_base": SOURCE_BASE,
        "candidate_branch": CANDIDATE_BRANCH,
        "status": "FAILED_CLOSED",
        "boundaries": [
            "Read-only verification of an existing candidate branch.",
            "Direct tree-object comparison is used; sibling-commit three-dot comparison is not used.",
            "Exactly two reviewed Python paths may differ from the source PR tree.",
            "No branch, pull request, rule, status, check, review, or secret is mutated.",
        ],
    }
    try:
        verify_source_pr()
        candidate_sha = branch_sha(CANDIDATE_BRANCH)
        signature = commit_receipt(candidate_sha)
        if signature["verified"] is not True:
            raise VerificationError(f"candidate signature is not verified: {signature}")
        if signature["parents"] != [SOURCE_BASE]:
            raise VerificationError(f"candidate parent mismatch: {signature['parents']}")
        source_tree_sha, source_tree = tree_map(SOURCE_HEAD)
        candidate_tree_sha, candidate_tree = tree_map(candidate_sha)
        differences = direct_tree_diff(source_tree, candidate_tree)
        if set(differences) != ALLOWED_TREE_DIFFS:
            raise VerificationError(
                "direct source/candidate tree differences escaped the reviewed paths: "
                f"{sorted(differences)}"
            )
        content_receipt = verify_review_content(candidate_tree)
        report.update(
            {
                "status": "SIGNED_REVIEW_FIX_VERIFIED",
                "candidate_commit": candidate_sha,
                "signature": signature,
                "source_tree": source_tree_sha,
                "candidate_tree": candidate_tree_sha,
                "direct_tree_differences": differences,
                "review_fix": content_receipt,
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
