#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check

POLICY = Path(__file__).with_name("solo-maintainer-policy.v1.json")
BODY = """## Origin
Founder-authored / approved agent-assisted work.

## Rights
I own this change or have the right to contribute every included component.

## Agents and tools
Grok 4.6 terminal controller.

## Tests
python3 provenance/test_check.py

## Security
No secrets. Policy JSON only. Advisory workflow.

## Rollback
Revert the squash merge commit on .github.

## Known limits
Does not add szl/provenance as a required ruleset check.
"""


class ProvenanceCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = check.load_policy(POLICY)

    def event(self, **over) -> dict:
        payload = {
            "pull_request": {
                "body": BODY,
                "head": {
                    "sha": "a" * 40,
                    "repo": {"full_name": "szl-holdings/.github"},
                },
                "base": {"ref": "main"},
            },
            "repository": {"default_branch": "main"},
            "sender": {"login": "stephenlutar2-hash"},
        }
        payload.update(over)
        return payload

    def test_policy_forbids_credential_recording(self) -> None:
        self.assertIs(self.policy["credential_value_recorded"], False)

    def test_founder_internal_pr_passes(self) -> None:
        report = check.evaluate(self.policy, self.event())
        self.assertTrue(report["pass"], report["failed"])

    def test_missing_heading_fails(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace("## Rollback\nRevert the squash merge commit on .github.\n", "")
        report = check.evaluate(self.policy, event)
        self.assertFalse(report["pass"])
        self.assertIn("pr_body_headings", report["failed"])

    def test_http_success_is_not_modeled_as_live(self) -> None:
        report = check.evaluate(self.policy, self.event())
        self.assertNotIn("live", report)
        self.assertIn("advisory until added as a required check", report["known_limits"])

    def test_fork_head_fails_internal_mode(self) -> None:
        event = self.event()
        event["pull_request"]["head"]["repo"]["full_name"] = "other/.github"
        report = check.evaluate(self.policy, event)
        self.assertIn("internal_head_repository", report["failed"])


if __name__ == "__main__":
    unittest.main()
