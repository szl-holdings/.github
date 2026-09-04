#!/usr/bin/env python3
"""Remove the exact legacy files blocking the SZL Hugging Face org-card publish.

This is intentionally a separate, one-purpose migration rather than relaxing
the canonical publisher's deletion-closed manifest. The files remain in the
Hugging Face Git history; only their current-branch entries are removed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

TARGET_REPOSITORY = "SZLHOLDINGS/README"
SOURCE_REPOSITORY = "szl-holdings/.github"
WORKFLOW_PATH = ".github/workflows/hf-org-card-autopublish.yml"
SCHEMA = "szl.hf-org-card-legacy-cleanup/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(
    r"(?:hf_[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._~+/-]+=*|"
    r"gh[oprsu]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})",
    re.I,
)
LEGACY_PATHS = (
    "GOVERNANCE.md",
    "MODELS.txt",
    "SEVEN_SPACES.md",
    "SPACE_PROVENANCE_FRONTIER.json",
    "seven-spaces.yaml",
)


class CleanupError(RuntimeError):
    """Raised when cleanup authority or provider readback is incomplete."""


@dataclass(frozen=True)
class CleanupReport:
    schema: str
    state: str
    target: str
    source_revision: str
    deleted_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    before_head: str
    after_head: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"


def redact(value: str) -> str:
    return TOKEN_RE.sub("[REDACTED]", value)


def assert_authority(source_sha: str, environ: dict[str, str]) -> None:
    """Accept only the first protected-main push attempt of the central workflow."""

    if not SHA40.fullmatch(source_sha):
        raise CleanupError("source revision must be an exact lowercase Git SHA")
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_REPOSITORY": SOURCE_REPOSITORY,
        "GITHUB_SHA": source_sha,
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": (
            f"{SOURCE_REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
        ),
    }
    mismatches = sorted(
        name for name, wanted in expected.items() if environ.get(name) != wanted
    )
    if not environ.get("HF_TOKEN"):
        mismatches.append("HF_TOKEN")
    if mismatches:
        raise CleanupError(
            "cleanup authority mismatch: " + ", ".join(sorted(set(mismatches)))
        )


def cleanup_legacy_paths(
    *,
    source_sha: str,
    token: str,
    environ: dict[str, str] | None = None,
    wait_seconds: int = 120,
    api_factory: Callable[..., Any] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> CleanupReport:
    """Delete only the reviewed legacy paths and prove the exact result."""

    env = dict(os.environ if environ is None else environ)
    assert_authority(source_sha, env)
    if token != env.get("HF_TOKEN"):
        raise CleanupError("explicit token does not match the authorized environment")
    if not 1 <= wait_seconds <= 600:
        raise CleanupError("wait_seconds must be between 1 and 600")

    if api_factory is None:
        try:
            from huggingface_hub import CommitOperationDelete, HfApi
        except ImportError as exc:
            raise CleanupError("huggingface_hub is required") from exc
    else:
        CommitOperationDelete = None  # type: ignore[assignment,misc]
        HfApi = api_factory  # type: ignore[assignment,misc]

    api = HfApi(token=token)
    before = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
    before_head = str(getattr(before, "sha", ""))
    if not SHA40.fullmatch(before_head):
        raise CleanupError("Hugging Face returned an invalid pre-cleanup head")

    remote_files = set(api.list_repo_files(repo_id=TARGET_REPOSITORY, repo_type="space"))
    present = tuple(path for path in LEGACY_PATHS if path in remote_files)
    missing = tuple(path for path in LEGACY_PATHS if path not in remote_files)
    if not present:
        return CleanupReport(
            schema=SCHEMA,
            state="ALREADY_CLEAN",
            target=TARGET_REPOSITORY,
            source_revision=source_sha,
            deleted_paths=(),
            missing_paths=missing,
            before_head=before_head,
            after_head=before_head,
        )

    if api_factory is None:
        operations = [CommitOperationDelete(path_in_repo=path) for path in present]
    else:
        operations = [path for path in present]
    commit = api.create_commit(
        repo_id=TARGET_REPOSITORY,
        repo_type="space",
        operations=operations,
        commit_message="chore: retire legacy organization-card collateral",
        parent_commit=before_head,
    )
    commit_oid = str(getattr(commit, "oid", ""))
    if not SHA40.fullmatch(commit_oid):
        raise CleanupError("Hugging Face returned an invalid cleanup commit OID")

    deadline = time.monotonic() + wait_seconds
    last_head = ""
    last_files: set[str] = set()
    while time.monotonic() < deadline:
        info = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
        last_head = str(getattr(info, "sha", ""))
        last_files = set(
            api.list_repo_files(
                repo_id=TARGET_REPOSITORY,
                repo_type="space",
                revision=commit_oid,
            )
        )
        if last_head == commit_oid and not (set(LEGACY_PATHS) & last_files):
            return CleanupReport(
                schema=SCHEMA,
                state="VERIFIED",
                target=TARGET_REPOSITORY,
                source_revision=source_sha,
                deleted_paths=present,
                missing_paths=missing,
                before_head=before_head,
                after_head=commit_oid,
            )
        sleeper(3)

    remaining = sorted(set(LEGACY_PATHS) & last_files)
    raise CleanupError(
        "cleanup readback did not converge "
        f"(head_matches={last_head == commit_oid}, remaining={remaining})"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-sha", required=True)
    result.add_argument("--wait-seconds", type=int, default=120)
    result.add_argument("--report", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = cleanup_legacy_paths(
            source_sha=args.source_sha,
            token=os.environ.get("HF_TOKEN", ""),
            wait_seconds=args.wait_seconds,
        )
        payload = report.to_json()
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload, encoding="utf-8", newline="\n")
        print(payload, end="")
        return 0
    except Exception as exc:
        payload = json.dumps(
            {
                "schema": SCHEMA,
                "state": "FAILED",
                "source_revision": args.source_sha,
                "error": redact(f"{type(exc).__name__}: {exc}"),
            },
            sort_keys=True,
            indent=2,
        ) + "\n"
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload, encoding="utf-8", newline="\n")
        print(payload, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
