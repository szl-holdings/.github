#!/usr/bin/env python3
"""Bind privileged FORGE-9 consumers to one exact workflow-run PR subject."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class SourceRunIdentityError(ValueError):
    """Raised when a workflow run cannot be bound to one exact PR subject."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceRunIdentityError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SourceRunIdentityError(f"{label} must be an array")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceRunIdentityError(f"{label} must be a positive integer")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceRunIdentityError(f"{label} must be a non-empty string")
    return value


def _sha(value: Any, label: str) -> str:
    text = _string(value, label)
    if not SHA_PATTERN.fullmatch(text):
        raise SourceRunIdentityError(f"{label} must be an exact 40-character SHA")
    return text


def _repo_id(value: Any, label: str) -> int:
    return _integer(_mapping(value, label).get("id"), f"{label}.id")


def _base_is_allowed(ref: str, exact: Iterable[str], prefixes: Iterable[str]) -> bool:
    return ref in set(exact) or any(ref.startswith(prefix) for prefix in prefixes)


def bind_source_run(
    run: dict[str, Any],
    *,
    expected_run_id: int,
    expected_repository: str,
    expected_head_sha: str,
    allowed_bases: Iterable[str],
    allowed_base_prefixes: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the sole exact PR association for a pull_request workflow run."""

    run = _mapping(run, "workflow run")
    expected_run_id = _integer(expected_run_id, "expected run id")
    expected_repository = _string(expected_repository, "expected repository")
    expected_head_sha = _sha(expected_head_sha, "expected head SHA")

    if _integer(run.get("id"), "workflow run.id") != expected_run_id:
        raise SourceRunIdentityError("workflow run id does not match SOURCE_GATE_RUN_ID")
    if run.get("event") != "pull_request":
        raise SourceRunIdentityError("workflow run event is not pull_request")
    if _sha(run.get("head_sha"), "workflow run.head_sha") != expected_head_sha:
        raise SourceRunIdentityError("workflow run head SHA does not match the event")

    repository = _mapping(run.get("repository"), "workflow run.repository")
    repository_id = _integer(repository.get("id"), "workflow run.repository.id")
    if repository.get("full_name") != expected_repository:
        raise SourceRunIdentityError("workflow run repository identity does not match")

    head_repository = _mapping(
        run.get("head_repository"), "workflow run.head_repository"
    )
    if _integer(head_repository.get("id"), "workflow run.head_repository.id") != (
        repository_id
    ) or head_repository.get("full_name") != expected_repository:
        raise SourceRunIdentityError("workflow run came from a different head repository")

    associations = _list(run.get("pull_requests"), "workflow run.pull_requests")
    if len(associations) != 1:
        raise SourceRunIdentityError(
            "workflow run must identify exactly one pull request association"
        )
    association = _mapping(associations[0], "workflow run.pull_requests[0]")
    association_id = _integer(association.get("id"), "source pull request.id")
    number = _integer(association.get("number"), "source pull request.number")

    head = _mapping(association.get("head"), "source pull request.head")
    head_repo_id = _repo_id(head.get("repo"), "source pull request.head.repo")
    head_sha = _sha(head.get("sha"), "source pull request.head.sha")
    head_ref = _string(head.get("ref"), "source pull request.head.ref")
    if head_repo_id != repository_id or head_sha != expected_head_sha:
        raise SourceRunIdentityError(
            "source pull request head repository or SHA does not match the run"
        )

    base = _mapping(association.get("base"), "source pull request.base")
    base_repo_id = _repo_id(base.get("repo"), "source pull request.base.repo")
    base_ref = _string(base.get("ref"), "source pull request.base.ref")
    base_sha = _sha(base.get("sha"), "source pull request.base.sha")
    if base_repo_id != repository_id:
        raise SourceRunIdentityError("source pull request base repository does not match")
    if not _base_is_allowed(base_ref, allowed_bases, allowed_base_prefixes):
        raise SourceRunIdentityError(f"source pull request base {base_ref!r} is not allowed")

    return {
        "schema": "szl.forge9-source-run-binding/v1",
        "source_gate_run_id": expected_run_id,
        "event": "pull_request",
        "repository_id": repository_id,
        "repository_full_name": expected_repository,
        "pull_request_id": association_id,
        "pull_request_number": number,
        "head_repository_id": head_repo_id,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "base_repository_id": base_repo_id,
        "base_ref": base_ref,
        "base_sha": base_sha,
    }


def verify_pull_request(binding: dict[str, Any], pull_request: dict[str, Any]) -> None:
    """Require a current REST PR document to match an immutable run binding."""

    binding = _mapping(binding, "source-run binding")
    pull_request = _mapping(pull_request, "pull request")
    repository = _string(
        binding.get("repository_full_name"), "source-run binding.repository_full_name"
    )
    repository_id = _integer(
        binding.get("repository_id"), "source-run binding.repository_id"
    )

    if _integer(pull_request.get("id"), "pull request.id") != _integer(
        binding.get("pull_request_id"), "source-run binding.pull_request_id"
    ):
        raise SourceRunIdentityError("current pull request id does not match the run")
    if _integer(pull_request.get("number"), "pull request.number") != _integer(
        binding.get("pull_request_number"), "source-run binding.pull_request_number"
    ):
        raise SourceRunIdentityError("current pull request number does not match the run")
    if pull_request.get("state") != "open":
        raise SourceRunIdentityError("current pull request is not open")
    if not isinstance(pull_request.get("draft"), bool):
        raise SourceRunIdentityError("current pull request draft state is invalid")

    head = _mapping(pull_request.get("head"), "pull request.head")
    head_repo = _mapping(head.get("repo"), "pull request.head.repo")
    if (
        _integer(head_repo.get("id"), "pull request.head.repo.id") != repository_id
        or head_repo.get("full_name") != repository
        or _sha(head.get("sha"), "pull request.head.sha") != binding.get("head_sha")
        or _string(head.get("ref"), "pull request.head.ref") != binding.get("head_ref")
    ):
        raise SourceRunIdentityError("current pull request head identity does not match")

    base = _mapping(pull_request.get("base"), "pull request.base")
    base_repo = _mapping(base.get("repo"), "pull request.base.repo")
    if (
        _integer(base_repo.get("id"), "pull request.base.repo.id") != repository_id
        or base_repo.get("full_name") != repository
        or _string(base.get("ref"), "pull request.base.ref") != binding.get("base_ref")
        or _sha(base.get("sha"), "pull request.base.sha") != binding.get("base_sha")
    ):
        raise SourceRunIdentityError("current pull request base identity does not match")


def _workflow_runs(payload: Any) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    runs: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        page = _mapping(page, f"workflow-runs page {page_number}")
        for run in _list(page.get("workflow_runs"), "workflow_runs"):
            runs.append(_mapping(run, "workflow run"))
    return runs


def latest_matching_run_id(payload: Any, binding: dict[str, Any]) -> int:
    """Return the newest gate run with the exact same PR association."""

    binding = _mapping(binding, "source-run binding")
    expected = {
        key: binding.get(key)
        for key in (
            "repository_id",
            "repository_full_name",
            "pull_request_id",
            "pull_request_number",
            "head_repository_id",
            "head_ref",
            "head_sha",
            "base_repository_id",
            "base_ref",
            "base_sha",
        )
    }
    candidates: list[int] = []
    for run in _workflow_runs(payload):
        run_id = run.get("id")
        if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
            continue
        try:
            candidate = bind_source_run(
                run,
                expected_run_id=run_id,
                expected_repository=_string(
                    binding.get("repository_full_name"),
                    "source-run binding.repository_full_name",
                ),
                expected_head_sha=_sha(
                    binding.get("head_sha"), "source-run binding.head_sha"
                ),
                allowed_bases=(_string(binding.get("base_ref"), "binding.base_ref"),),
            )
        except SourceRunIdentityError:
            continue
        if all(candidate.get(key) == value for key, value in expected.items()):
            candidates.append(run_id)
    if not candidates:
        raise SourceRunIdentityError(
            "no workflow run has the exact bound pull request association"
        )
    return max(candidates)


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    bind = commands.add_parser("bind")
    bind.add_argument("--run-file", required=True)
    bind.add_argument("--expected-run-id", required=True, type=int)
    bind.add_argument("--expected-repository", required=True)
    bind.add_argument("--expected-head-sha", required=True)
    bind.add_argument("--allowed-base", action="append", default=[])
    bind.add_argument("--allowed-base-prefix", action="append", default=[])
    bind.add_argument("--output", required=True)

    verify = commands.add_parser("verify-pr")
    verify.add_argument("--binding-file", required=True)
    verify.add_argument("--pull-request-file", required=True)

    latest = commands.add_parser("latest")
    latest.add_argument("--runs-file", required=True)
    latest.add_argument("--binding-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "bind":
            binding = bind_source_run(
                _read_json(args.run_file),
                expected_run_id=args.expected_run_id,
                expected_repository=args.expected_repository,
                expected_head_sha=args.expected_head_sha,
                allowed_bases=args.allowed_base,
                allowed_base_prefixes=args.allowed_base_prefix,
            )
            _write_json(args.output, binding)
            return 0
        if args.command == "verify-pr":
            verify_pull_request(
                _read_json(args.binding_file), _read_json(args.pull_request_file)
            )
            return 0
        if args.command == "latest":
            print(
                latest_matching_run_id(
                    _read_json(args.runs_file), _read_json(args.binding_file)
                )
            )
            return 0
    except (OSError, json.JSONDecodeError, SourceRunIdentityError) as exc:
        print(f"source-run identity error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
