#!/usr/bin/env python3
"""Publish the SZL Hugging Face organization front door from protected main.

The original publisher is environment-gated. This central publisher uses the
same exact-source manifest and readback implementation while authorizing only
an ordinary push of the protected ``szl-holdings/.github`` main branch. It is
intended for the repository-scoped Hugging Face credential already used by the
central Space publishers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import hf_space_visibility as visibility  # noqa: E402
import hf_static_space_deploy as deploy  # noqa: E402

SCHEMA = "szl.hf-org-card-autopublish/v1"
SOURCE_REPOSITORY = "szl-holdings/.github"
TARGET_REPOSITORY = "SZLHOLDINGS/README"
WORKFLOW_PATH = ".github/workflows/hf-org-card-autopublish.yml"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class AuthorityError(RuntimeError):
    """Raised when provider-write authority is not exact and server owned."""


def assert_authority(source_sha: str, environ: dict[str, str]) -> None:
    """Accept only the first protected-main push attempt of this workflow."""

    if not SHA40.fullmatch(source_sha):
        raise AuthorityError("source revision must be an exact lowercase Git SHA")
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
    if not environ.get("GITHUB_TOKEN"):
        mismatches.append("GITHUB_TOKEN")
    if not environ.get("HF_TOKEN"):
        mismatches.append("HF_TOKEN")
    if mismatches:
        raise AuthorityError(
            "provider publication authority mismatch: "
            + ", ".join(sorted(set(mismatches)))
        )


def publish_org_card(
    *,
    repo_root: Path,
    manifest_path: Path,
    source_sha: str,
    wait_seconds: int,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Restore public visibility, publish exact bytes, and verify readback."""

    env = dict(os.environ if environ is None else environ)
    assert_authority(source_sha, env)
    deploy.assert_local_source(repo_root, source_sha)

    contract, files = deploy.load_contract(repo_root, manifest_path)
    target = contract.get("target", {})
    if (
        contract.get("source_repository") != SOURCE_REPOSITORY
        or target.get("repo_id") != TARGET_REPOSITORY
        or target.get("repo_type") != "space"
    ):
        raise AuthorityError("manifest escaped the fixed organization-card target")

    deployment = deploy.build_deployment(
        contract,
        files,
        source_sha,
        deploy.utc_now(),
    )
    token = env["HF_TOKEN"]
    github_token = env["GITHUB_TOKEN"]

    visibility_before = visibility.ensure_public_space(
        TARGET_REPOSITORY,
        token,
        wait_seconds=min(wait_seconds, 180),
    )
    publication = deploy.publish(
        contract,
        files,
        deployment,
        token,
        github_token,
        wait_seconds,
    )
    visibility_after = visibility.ensure_public_space(
        TARGET_REPOSITORY,
        token,
        wait_seconds=min(wait_seconds, 180),
        check_only=True,
    )
    if publication.get("state") != "VERIFIED":
        raise RuntimeError("publication returned without a VERIFIED state")
    if not visibility_after.unauthenticated_readable:
        raise RuntimeError("published organization card is not anonymously readable")

    return {
        "schema": SCHEMA,
        "state": "VERIFIED",
        "source_revision": source_sha,
        "target": TARGET_REPOSITORY,
        "file_count": len(files) + 1,
        "visibility_before": asdict(visibility_before),
        "publication": publication,
        "visibility_after": asdict(visibility_after),
    }


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = (
        json.dumps(
            deploy.sanitize_report(report),
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument(
        "--manifest",
        type=Path,
        default=Path("huggingface/org-card.manifest.json"),
    )
    result.add_argument("--source-sha", required=True)
    result.add_argument("--wait-seconds", type=int, default=600)
    result.add_argument("--report", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "FAILED",
        "source_revision": args.source_sha,
    }
    try:
        repo_root = args.repo_root.resolve()
        manifest = (
            args.manifest.resolve()
            if args.manifest.is_absolute()
            else (repo_root / args.manifest).resolve()
        )
        report = publish_org_card(
            repo_root=repo_root,
            manifest_path=manifest,
            source_sha=args.source_sha,
            wait_seconds=args.wait_seconds,
        )
        write_report(args.report, report)
        return 0
    except deploy.PublicationVerificationError as exc:
        report.update(exc.result)
        report["error"] = deploy.describe_exception(exc)
    except Exception as exc:
        report["error"] = deploy.describe_exception(exc)
    write_report(args.report, report)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
