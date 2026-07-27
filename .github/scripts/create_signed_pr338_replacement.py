#!/usr/bin/env python3
"""Configure the proven exact-tree normalizer for fully green PR #338."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import create_signed_pr333_replacement as core

core.SOURCE_PR = 338
core.SOURCE_HEAD = "3d3db81922ddced7bb087482a91a57bc1ac9548f"
core.SOURCE_BASE = "5c991c4b0430e227db02d9e752e15152a1e2027b"
core.TARGET_BRANCH = "chore/retire-replit-receipt-lane-v1-signed-3d3db81922dd"
core.REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/pr338-signed-tree-normalization.json",
    )
)


def create_signed_commit(
    additions: dict[str, bytes],
    deletions: list[str],
) -> str:
    """Create the PR #338 exact-tree commit through GitHub GraphQL."""
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
                        "headline": "chore(replit): retire decommissioned receipt discovery",
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
