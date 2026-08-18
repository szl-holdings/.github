#!/usr/bin/env python3
"""Publish one signed qillqaq Secrets-read permission repair.

Temporary controller: it patches the reviewed GitHub App manifest, the exact
FORGE-9 permission invariant, and the existing permission regression. It writes
only those three files to a clean branch rooted at protected main.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = os.environ["REPOSITORY"]
TARGET_BRANCH = os.environ["TARGET_BRANCH"]
EXPECTED_PARENT = os.environ["EXPECTED_PARENT"]
TOKEN = os.environ["GITHUB_TOKEN"]
MANIFEST_PATH = ROOT / ".governance/github-app-manifest.json"
VERIFIER_PATH = ROOT / ".github/scripts/verify_forge9_governance.py"
DRIFT_TEST_PATH = ROOT / ".github/scripts/test_code_security_drift.py"

OLD_EXPECTED = '''    expected = {
        "actions": "read",
        "administration": "read",
        "checks": "read",
        "commit_statuses": "write",
        "contents": "read",
        "metadata": "read",
        "organization_administration": "read",
        "pull_requests": "write",
    }
'''
NEW_EXPECTED = '''    expected = {
        "actions": "read",
        "administration": "read",
        "checks": "read",
        "commit_statuses": "write",
        "contents": "read",
        "metadata": "read",
        "organization_administration": "read",
        "organization_secrets": "read",
        "pull_requests": "write",
        "secrets": "read",
    }
'''
OLD_TEST = '''        self.assertEqual(permissions["organization_administration"], "read")
        self.assertEqual(permissions["administration"], "read")
'''
NEW_TEST = '''        self.assertEqual(permissions["organization_administration"], "read")
        self.assertEqual(permissions["organization_secrets"], "read")
        self.assertEqual(permissions["administration"], "read")
        self.assertEqual(permissions["secrets"], "read")
'''
BOT_SIGNOFF = (
    "Signed-off-by: github-actions[bot] "
    "<41898282+github-actions[bot]@users.noreply.github.com>"
)


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def request(url: str, *, data: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        method="POST" if data is not None else "GET",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-qillqaq-secrets-permission-materializer/2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:4000]
        raise SystemExit(f"GitHub HTTP {exc.code}: {body}") from exc


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    permissions = manifest.get("default_permissions")
    if not isinstance(permissions, dict):
        raise SystemExit("GitHub App manifest permissions are missing")
    if "secrets" in permissions or "organization_secrets" in permissions:
        raise SystemExit("Secrets permissions already exist; controller is stale")
    permissions["organization_secrets"] = "read"
    permissions["secrets"] = "read"
    manifest["default_permissions"] = dict(sorted(permissions.items()))
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    verifier = VERIFIER_PATH.read_text(encoding="utf-8")
    if verifier.count(OLD_EXPECTED) != 1:
        raise SystemExit("FORGE-9 expected-permission block changed")
    VERIFIER_PATH.write_text(
        verifier.replace(OLD_EXPECTED, NEW_EXPECTED, 1), encoding="utf-8"
    )

    drift_test = DRIFT_TEST_PATH.read_text(encoding="utf-8")
    if drift_test.count(OLD_TEST) != 1:
        raise SystemExit("code-security App-permission regression changed")
    DRIFT_TEST_PATH.write_text(
        drift_test.replace(OLD_TEST, NEW_TEST, 1), encoding="utf-8"
    )

    run(
        "python",
        "-m",
        "py_compile",
        str(VERIFIER_PATH),
        str(DRIFT_TEST_PATH),
    )
    run("python", str(VERIFIER_PATH))
    run("python", str(DRIFT_TEST_PATH))
    run("python", ".github/scripts/test_secret_health.py")
    run("git", "diff", "--check")

    paths = [
        ".github/scripts/test_code_security_drift.py",
        ".github/scripts/verify_forge9_governance.py",
        ".governance/github-app-manifest.json",
    ]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only"], cwd=ROOT, text=True
    ).splitlines()
    if sorted(changed) != sorted(paths):
        raise SystemExit(f"unexpected changed paths: {changed}")

    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) { commit { oid url } }
    }
    """
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": REPOSITORY,
                "branchName": TARGET_BRANCH,
            },
            "message": {
                "headline": "fix(app): grant qillqaq secret-name read",
                "body": BOT_SIGNOFF,
            },
            "expectedHeadOid": EXPECTED_PARENT,
            "fileChanges": {
                "additions": [
                    {
                        "path": path,
                        "contents": base64.b64encode((ROOT / path).read_bytes()).decode(
                            "ascii"
                        ),
                    }
                    for path in paths
                ]
            },
        }
    }
    payload = request(
        "https://api.github.com/graphql",
        data={"query": mutation, "variables": variables},
    )
    if payload.get("errors"):
        raise SystemExit(json.dumps(payload["errors"], indent=2))
    commit = payload["data"]["createCommitOnBranch"]["commit"]
    sha = commit["oid"]
    commit_payload = request(f"https://api.github.com/repos/{REPOSITORY}/commits/{sha}")
    verification = commit_payload["commit"]["verification"]
    author = commit_payload["commit"]["author"]
    if verification.get("verified") is not True or verification.get("reason") != "valid":
        raise SystemExit(f"target commit is not GitHub-verified: {verification}")
    if author != {
        "name": "github-actions[bot]",
        "email": "41898282+github-actions[bot]@users.noreply.github.com",
        "date": author.get("date"),
    }:
        raise SystemExit(f"unexpected signed commit author: {author}")
    if BOT_SIGNOFF not in commit_payload["commit"]["message"]:
        raise SystemExit("signed commit does not carry its exact author DCO identity")

    receipt = {
        "schema": "szl.qillqaq-secrets-permission-materialization/v2",
        "expected_parent": EXPECTED_PARENT,
        "target_branch": TARGET_BRANCH,
        "commit": commit,
        "verification": {
            "verified": verification.get("verified"),
            "reason": verification.get("reason"),
        },
        "dco_identity": BOT_SIGNOFF,
        "permissions_added": {
            "repository.secrets": "read",
            "organization.organization_secrets": "read",
        },
        "changed_paths": paths,
        "secret_value_requested": False,
        "secret_value_recorded": False,
        "diagnostic_controller_included": False,
    }
    (ROOT / "qillqaq-secrets-permission-materialization.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
