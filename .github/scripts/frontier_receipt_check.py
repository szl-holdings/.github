#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate and stage one minimized public operator receipt; never promote a PR.

A schema match is not a security audit, inventory census, or queue qualification.
The CLI independently rechecks public repository metadata with the repository
credential, then stages the exact validated bytes for the existing uploader.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

MAX_BYTES = 2 * 1024 * 1024
MAX_REPOSITORIES = 256
SHA = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"szl-holdings/[A-Za-z0-9_.-]{1,100}")
LABELS = frozenset({"estate:p0", "estate:runtime-drift", "estate:blocked-external",
    "estate:code-actionable", "estate:execution-ledger", "estate:roadmap", "estate:backlog"})
BLOCKERS = frozenset({"draft", "external-fork", "non-default-base", "mergeability-not-clean",
    "no-check-evidence", "failed-checks", "active-checks", "changes-requested",
    "unresolved-review-threads", "OTHER_REVIEW_BLOCKER"})
ERROR_CODES = frozenset({"SIGNATURE_UNVERIFIED", "AUTHORIZATION_NOT_SELECTED",
    "AUTHORIZATION_EXPIRED_OR_FUTURE", "AUTHORIZATION_EXPIRED_AT_WRITE", "PROTECTION_DRIFT",
    "CONTROLLER_SOURCE_UNAVAILABLE", "TARGET_BASE_MOVED", "REQUIRED_CHECK_APP_UNVERIFIED",
    "REVIEW_HOLD", "REVIEW_LABEL_HOLD", "REPORT_OWNERSHIP_MISMATCH", "REPORT_CREDENTIAL_UNAVAILABLE",
    "API_AUTHENTICATION_DENIED", "API_ACCESS_DENIED", "API_RESOURCE_UNAVAILABLE", "API_RATE_LIMITED",
    "API_TRANSPORT_UNAVAILABLE", "OPERATOR_PRECONDITION_OR_OBSERVATION_FAILED"})
PROMOTIONS = frozenset({"NOT_REQUESTED", "ALREADY_QUEUED_EXACT_HEAD", "QUEUED_EXACT_HEAD_OBSERVED",
    "QUEUE_WRITE_ATTEMPTED_READBACK_REQUIRED", "QUEUE_WRITE_OUTCOME_UNKNOWN"})
UNCERTAIN = frozenset({"QUEUE_WRITE_ATTEMPTED_READBACK_REQUIRED", "QUEUE_WRITE_OUTCOME_UNKNOWN"})
COVERAGE = {"scope": "public-search-visible-only", "complete_organization": False,
    "private_repositories": "NOT_OBSERVED", "security_alerts": "NOT_OBSERVED", "atomic_snapshot": False}
TOP = frozenset({"schema", "status", "mode", "organization", "started_at", "finished_at",
    "token_value_recorded", "coverage", "source_revision", "pull_requests", "issues", "promotion",
    "command_center", "error_code", "summary"})
SUMMARY = frozenset({"observed_pull_requests", "observed_issues", "merged_pull_requests",
    "closed_exact_duplicates", "changed_issue_labels", "pull_request_errors", "issue_errors",
    "observation_failed", "classification_counts"})


class ReceiptError(ValueError):
    """Fixed diagnostic only; never interpolate receipt values or exception text."""


def require(condition: bool) -> None:
    if not condition:
        raise ReceiptError("PUBLIC_RECEIPT_NOT_VERIFIED")


def exact_keys(value: Any, keys: set[str] | frozenset[str]) -> None:
    require(type(value) is dict and set(value) == keys)


def count(value: Any, *, positive: bool = False) -> None:
    require(type(value) is int and int(positive) <= value <= 1_000_000_000)


def utc(value: Any) -> datetime:
    require(type(value) is str and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value) is not None)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ReceiptError("PUBLIC_RECEIPT_NOT_VERIFIED") from None


def decode(raw: bytes) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            require(key not in result)
            result[key] = value
        return result
    def nonfinite(_value: str) -> None:
        raise ReceiptError("PUBLIC_RECEIPT_NOT_VERIFIED")
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        raise ReceiptError("PUBLIC_RECEIPT_NOT_VERIFIED") from None
    require(type(value) is dict)
    return value


def validate(raw: bytes, expected_sha: str, *, now: datetime) -> tuple[dict[str, Any], list[str]]:
    """Validate the existing producer's exact bounded public projection."""
    require(type(expected_sha) is str and SHA.fullmatch(expected_sha) is not None)
    require(now.tzinfo is not None and now.utcoffset() == timedelta(0))
    value = decode(raw)
    exact_keys(value, TOP)
    require(value["schema"] == "szl.frontier-issue-operator/v1")
    require(value["organization"] == "szl-holdings" and value["source_revision"] == expected_sha)
    require(value["token_value_recorded"] is False)
    exact_keys(value["coverage"], set(COVERAGE))
    for key, expected in COVERAGE.items():
        require(type(value["coverage"][key]) is type(expected) and value["coverage"][key] == expected)
    require(value["mode"] in ("PUBLIC_OBSERVATION", "EXACT_QUEUE"))
    require(value["status"] in ("OBSERVATION_COMPLETE", "PARTIAL_FAILURE", "BLOCKED_MANAGED_PREREQUISITE"))
    start, finish = utc(value["started_at"]), utc(value["finished_at"])
    require(start <= finish <= now + timedelta(seconds=60))
    require(now - finish <= timedelta(hours=1) and finish - start <= timedelta(minutes=35))
    require(value["error_code"] is None or (type(value["error_code"]) is str and value["error_code"] in ERROR_CODES))
    require(value["command_center"] in ("NOT_REQUESTED", "NOT_VERIFIED", "PUBLIC_BODY_READBACK_VERIFIED"))
    promotion = value["promotion"]
    require(type(promotion) is dict and type(promotion.get("state")) is str)
    require(promotion["state"] in PROMOTIONS)
    permitted = {"state", "send"} if "send" in promotion else {"state"}
    exact_keys(promotion, permitted)
    if "send" in promotion:
        require(promotion["state"] == "QUEUE_WRITE_OUTCOME_UNKNOWN" and promotion["send"] in ("ERROR", "ACKNOWLEDGED"))
    if value["mode"] == "PUBLIC_OBSERVATION":
        require(promotion == {"state": "NOT_REQUESTED"})
    repositories: set[str] = set()
    for field, limit in (("pull_requests", 300), ("issues", 1000)):
        rows = value[field]
        require(type(rows) is list and len(rows) <= limit)
        seen: set[tuple[str, int]] = set()
        for row in rows:
            keys = {"repository", "number", "action", "url"}
            keys |= {"head_sha", "blockers", "checks"} if field == "pull_requests" else {"classification", "possible_duplicate_of"}
            exact_keys(row, keys)
            repo = row["repository"]
            require(type(repo) is str and REPOSITORY.fullmatch(repo) is not None and repo.split("/")[1] not in (".", ".."))
            count(row["number"], positive=True)
            identity = (repo, row["number"])
            require(identity not in seen)
            seen.add(identity)
            repositories.add(repo)
            route = "pull" if field == "pull_requests" else "issues"
            require(row["url"] == f"https://github.com/{repo}/{route}/{row['number']}")
            if field == "pull_requests":
                require(row["action"] in ("REVIEW_CANDIDATE", "BLOCKED", "ERROR", "READ_ONLY_ARCHIVED"))
                require(row["head_sha"] is None or (type(row["head_sha"]) is str and SHA.fullmatch(row["head_sha"]) is not None))
                blockers = row["blockers"]
                require(type(blockers) is list and all(type(x) is str and x in BLOCKERS for x in blockers))
                require(len(blockers) == len(set(blockers)))
                exact_keys(row["checks"], {"passed", "failed", "active"})
                for n in row["checks"].values():
                    count(n)
            else:
                require(row["action"] in ("DUPLICATE_CANDIDATE", "CLASSIFICATION_PROPOSED", "ERROR", "READ_ONLY_ARCHIVED"))
                require(type(row["classification"]) is str and row["classification"] in LABELS)
                duplicate = row["possible_duplicate_of"]
                if duplicate is not None:
                    count(duplicate, positive=True)
                    require(duplicate != row["number"])
    require(len(repositories) <= MAX_REPOSITORIES)
    summary = value["summary"]
    exact_keys(summary, SUMMARY)
    for key in SUMMARY - {"observation_failed", "classification_counts"}:
        count(summary[key])
    require(type(summary["observation_failed"]) is bool)
    for key in ("merged_pull_requests", "closed_exact_duplicates", "changed_issue_labels"):
        require(summary[key] == 0)
    for field, number, errors in (("pull_requests", "observed_pull_requests", "pull_request_errors"),
                                  ("issues", "observed_issues", "issue_errors")):
        require(summary[number] == len(value[field]))
        # Failed visibility can intentionally withhold a row while retaining its error.
        require(summary[errors] >= sum(row["action"] == "ERROR" for row in value[field]))
    classes = summary["classification_counts"]
    require(type(classes) is dict and all(key in LABELS for key in classes))
    for n in classes.values():
        count(n, positive=True)
    require(classes == dict(Counter(row["classification"] for row in value["issues"])))
    failed = bool(summary["pull_request_errors"] or summary["issue_errors"] or summary["observation_failed"]
                  or promotion["state"] in UNCERTAIN)
    if value["status"] == "OBSERVATION_COMPLETE":
        require(not failed and value["error_code"] is None and value["command_center"] != "NOT_VERIFIED")
    else:
        require(failed)
    if value["status"] == "BLOCKED_MANAGED_PREREQUISITE":
        require(value["mode"] == "EXACT_QUEUE" and summary["observation_failed"] and not repositories)
    return value, sorted(repositories)


def stage(input_path: Path, output_directory: Path, expected_sha: str,
          metadata_reader: Callable[[str], Any], *, now: datetime) -> dict[str, Any]:
    """Read once, validate first, recheck visibility, then exclusively stage bytes.

    No raw error or item identity is printed. No existing evidence is overwritten.
    A trusted hosted runner is assumed; this is not hostile-process isolation or
    an atomic visibility snapshot across all repositories.
    """
    require(not os.path.lexists(output_directory))
    for path in (input_path, *input_path.parents, *output_directory.parents):
        require(not path.is_symlink())
    before = input_path.stat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES)
    def identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    with input_path.open("rb") as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before))
        raw = stream.read(MAX_BYTES + 1)
        require(identity(os.fstat(stream.fileno())) == identity(before))
    require(identity(input_path.stat()) == identity(before) and not input_path.is_symlink())
    value, repositories = validate(raw, expected_sha, now=now)
    for repo in repositories:
        metadata = metadata_reader(repo)
        require(type(metadata) is dict and metadata.get("full_name") == repo
                and metadata.get("private") is False and metadata.get("visibility") == "public"
                and type(metadata.get("archived")) is bool
                and type(metadata.get("id")) is int and metadata["id"] > 0)
    output_directory.mkdir(mode=0o700, exist_ok=False)
    with (output_directory / "frontier-issue-operator.json").open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    (output_directory / "frontier-issue-operator.json").chmod(0o400)
    return {"schema": "szl.frontier-receipt-validation/v1", "state": "PUBLIC_PROJECTION_STAGED",
        "source_revision": expected_sha, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        "repository_metadata_reads": len(repositories), "operator_status": value["status"],
        "operational_qualification": False, "complete_organization": False}


def main() -> int:
    try:
        root = Path(__file__).resolve().parents[2]
        expected = os.environ.get("GITHUB_SHA", "")
        temporary = os.environ.get("RUNNER_TEMP", "")
        require(bool(temporary) and Path(temporary).is_absolute())
        # Reuse the existing canonical read transport, never a second publisher.
        spec = importlib.util.spec_from_file_location("frontier_receipt_source", Path(__file__).with_name("frontier_issue_operator.py"))
        require(spec is not None and spec.loader is not None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        reader = module.GitHub(os.environ.get("GITHUB_TOKEN", ""), apply=False)
        result = stage(root / "frontier-issue-operator.json", Path(temporary) / "frontier-verified-receipt",
                       expected, reader.repository, now=datetime.now(timezone.utc))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Do not reflect attacker-controlled paths, JSON keys, URLs, or provider text.
        print('{"state":"PUBLIC_RECEIPT_NOT_VERIFIED","upload_authorized":false}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
