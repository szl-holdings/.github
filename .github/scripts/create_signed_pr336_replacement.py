#!/usr/bin/env python3
"""Configure the proven exact-tree normalizer for fully green PR #336."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import create_signed_pr333_replacement as core

core.SOURCE_PR = 336
core.SOURCE_HEAD = "94cd5f7c14151dbd42f7b0d5e62470136bd3cb44"
core.SOURCE_BASE = "fa4b719adf5bdfcc970b2b32d49c35871b1b3fe9"
core.TARGET_BRANCH = "fix/ci-health-github-managed-dynamic-v1-signed-94cd5f7c1415"
core.REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/pr336-signed-tree-normalization.json",
    )
)


def create_signed_commit(
    additions: dict[str, bytes],
    deletions: list[str],
) -> str:
    """Create the PR #336 exact-tree commit through GitHub GraphQL."""
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
    response = core.api(
        ["graphql", "--input", "-"],
        payload={
            "query": mutation,
            "variables": {
                "input": {
                    "branch": {
                        "repositoryNameWithOwner": core.REPOSITORY,
                        "branchName": core.TARGET_BRANCH,
                    },
                    "expectedHeadOid": core.SOURCE_BASE,
                    "message": {
                        "headline": "fix(ci): isolate GitHub-managed dynamic workflow evidence",
                        "body": (
                            f"Tree-identical signed normalization of PR #{core.SOURCE_PR}.\n\n"
                            f"Source-Head: {core.SOURCE_HEAD}\n"
                            f"Source-Base: {core.SOURCE_BASE}\n\n"
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
        raise core.NormalizationError(
            f"createCommitOnBranch returned errors: {json.dumps(errors, sort_keys=True)}"
        )
    created = ((response or {}).get("data") or {}).get(
        "createCommitOnBranch"
    ) or {}
    return core.require_sha(
        (created.get("commit") or {}).get("oid"),
        "created commit",
    )


core.create_signed_commit = create_signed_commit


if __name__ == "__main__":
    raise SystemExit(core.main())
