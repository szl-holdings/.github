#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free tests for the owner deployment review bridge."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github" / "scripts" / "owner_deployment_review_bridge.py"
SPEC = importlib.util.spec_from_file_location("owner_deployment_review_bridge", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SHA = "79a8f2add42913b0831260574145437efe56af4a"
RUN_ID = 34069683698
ENV_ID = 18757132984


def command(**overrides):
    value = {
        "schema": MODULE.SCHEMA,
        "repository": MODULE.REPOSITORY,
        "workflow_run_id": RUN_ID,
        "environment_id": ENV_ID,
        "environment_name": MODULE.ENVIRONMENT,
        "head_sha": SHA,
        "workflow_path": MODULE.WORKFLOW_PATH,
        "decision": "approved",
        "reason": "Execute the reviewed four-source archive restoration wave.",
    }
    value.update(overrides)
    return value


def issue_event(**issue_overrides):
    issue = {
        "number": 999,
        "state": "open",
        "title": MODULE.TITLE,
        "body": "Approval follows.\n```json\n"
        + json.dumps(command(), sort_keys=True)
        + "\n```\n",
        "user": {"login": MODULE.OWNER},
    }
    issue.update(issue_overrides)
    return {"action": "opened", "issue": issue}


class ParsingContracts(unittest.TestCase):
    def test_exact_command_is_accepted(self):
        parsed = MODULE.parse_command(
            "```json\n" + json.dumps(command()) + "\n```"
        )
        self.assertEqual(parsed["workflow_run_id"], RUN_ID)

    def test_missing_fence_is_rejected(self):
        with self.assertRaisesRegex(MODULE.ReviewError, "fenced json"):
            MODULE.parse_command(json.dumps(command()))

    def test_multiple_fences_are_rejected(self):
        block = "```json\n" + json.dumps(command()) + "\n```"
        with self.assertRaisesRegex(MODULE.ReviewError, "exactly one"):
            MODULE.parse_command(block + "\n" + block)

    def test_duplicate_json_key_is_rejected(self):
        body = '```json\n{"schema":"a","schema":"b"}\n```'
        with self.assertRaisesRegex(MODULE.ReviewError, "duplicate JSON key"):
            MODULE.parse_command(body)

    def test_extra_key_is_rejected(self):
        value = command(extra="forbidden")
        with self.assertRaisesRegex(MODULE.ReviewError, "keys mismatch"):
            MODULE.parse_command("```json\n" + json.dumps(value) + "\n```")

    def test_wrong_workflow_is_rejected(self):
        value = command(workflow_path=".github/workflows/other.yml")
        with self.assertRaisesRegex(MODULE.ReviewError, "workflow_path"):
            MODULE.parse_command("```json\n" + json.dumps(value) + "\n```")

    def test_wrong_environment_is_rejected(self):
        value = command(environment_name="staging")
        with self.assertRaisesRegex(MODULE.ReviewError, "environment_name"):
            MODULE.parse_command("```json\n" + json.dumps(value) + "\n```")

    def test_non_lowercase_sha_is_rejected(self):
        value = command(head_sha=SHA.upper())
        with self.assertRaisesRegex(MODULE.ReviewError, "lowercase"):
            MODULE.parse_command("```json\n" + json.dumps(value) + "\n```")

    def test_credential_shape_is_rejected(self):
        value = command(reason="Approve with github_pat_" + "x" * 40)
        with self.assertRaisesRegex(MODULE.ReviewError, "credential-shaped"):
            MODULE.parse_command("```json\n" + json.dumps(value) + "\n```")

    def test_wrong_issue_author_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(
                json.dumps(issue_event(user={"login": "someone-else"})),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.ReviewError, "exact estate owner"):
                MODULE.load_event(path)


class FakeClient:
    def __init__(self, *, branch_sha=SHA, current_user_can_approve=True):
        self.branch_sha = branch_sha
        self.current_user_can_approve = current_user_can_approve
        self.approved = False
        self.posts = []
        self.completed = False

    def get(self, path):
        if path.endswith("/branches/main"):
            return {"commit": {"sha": self.branch_sha}}
        if path.endswith("/pending_deployments"):
            if self.approved or self.completed:
                return []
            return [
                {
                    "environment": {
                        "id": ENV_ID,
                        "name": MODULE.ENVIRONMENT,
                    },
                    "current_user_can_approve": self.current_user_can_approve,
                }
            ]
        if path.endswith(str(RUN_ID)):
            if self.completed:
                return {
                    "head_branch": "main",
                    "head_sha": SHA,
                    "path": MODULE.WORKFLOW_PATH,
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                }
            return {
                "head_branch": "main",
                "head_sha": SHA,
                "path": MODULE.WORKFLOW_PATH,
                "event": "push",
                "status": "in_progress" if self.approved else "waiting",
                "conclusion": None,
            }
        raise AssertionError(path)

    def post(self, path, payload):
        self.posts.append((path, payload))
        self.approved = True
        return {"status": "approved"}


class ProviderContracts(unittest.TestCase):
    def test_exact_pending_deployment_is_approved_and_read_back(self):
        client = FakeClient()
        report = MODULE.review(command(), client)
        self.assertEqual(report["status"], "APPROVED_READBACK_VERIFIED")
        self.assertTrue(report["mutated"])
        self.assertEqual(len(client.posts), 1)
        self.assertEqual(client.posts[0][1]["environment_ids"], [ENV_ID])
        self.assertEqual(client.posts[0][1]["state"], "approved")
        self.assertNotIn(command()["reason"], json.dumps(report))

    def test_protected_main_drift_blocks_review(self):
        client = FakeClient(branch_sha="0" * 40)
        with self.assertRaisesRegex(MODULE.ReviewError, "protected main moved"):
            MODULE.review(command(), client)
        self.assertEqual(client.posts, [])

    def test_provider_cannot_approve_blocks_review(self):
        client = FakeClient(current_user_can_approve=False)
        with self.assertRaisesRegex(MODULE.ReviewError, "cannot approve"):
            MODULE.review(command(), client)
        self.assertEqual(client.posts, [])

    def test_successfully_completed_run_is_idempotent(self):
        client = FakeClient()
        client.completed = True
        report = MODULE.review(command(), client)
        self.assertEqual(report["status"], "ALREADY_COMPLETED")
        self.assertFalse(report["mutated"])
        self.assertEqual(client.posts, [])

    def test_report_rejects_token_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MODULE.ReviewError, "credential-shaped"):
                MODULE.write_report(
                    Path(directory) / "receipt.json",
                    {"value": "ghp_" + "x" * 30},
                )


if __name__ == "__main__":
    unittest.main()
