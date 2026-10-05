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

    def test_head_requires_lowercase_hexadecimal_string(self) -> None:
        for head in ("z" * 40, "A" * 40, "a" * 39, "a" * 41, "a" * 40 + "\n", 10**39, None):
            with self.subTest(head=head):
                event = self.event()
                event["pull_request"]["head"]["sha"] = head
                report = check.evaluate(self.policy, event)
                self.assertFalse(report["pass"])
                self.assertIn("exact_head_sha", report["failed"])

    def test_declared_app_bot_is_admitted(self) -> None:
        for slug in self.policy["allowed_app_slugs"]:
            with self.subTest(slug=slug):
                report = check.evaluate(
                    self.policy, self.event(sender={"login": slug + "[bot]", "type": "Bot"})
                )
                self.assertTrue(report["pass"], report["failed"])

    def test_unapproved_and_mistyped_bots_fail(self) -> None:
        for sender in (
            {"login": "unapproved[bot]", "type": "Bot"},
            {"login": "github-actions[bot]", "type": "Bot"},
            {"login": "dependabot[bot]", "type": "User"},
            {"login": "dependabot[bot]"},
            {"login": "dependabot", "type": "Bot"},
            {"login": ["dependabot[bot]"], "type": "Bot"},
        ):
            with self.subTest(sender=sender):
                report = check.evaluate(self.policy, self.event(sender=sender))
                self.assertFalse(report["pass"])
                self.assertIn("allowed_actor", report["failed"])

    def test_bot_admission_tracks_policy_without_implicit_publishers(self) -> None:
        self.policy["allowed_app_slugs"] = []
        report = check.evaluate(
            self.policy, self.event(sender={"login": "dependabot[bot]", "type": "Bot"})
        )
        self.assertIn("allowed_actor", report["failed"])

    def test_each_evidence_section_requires_content(self) -> None:
        for name in check.HEADINGS:
            with self.subTest(heading=name):
                event = self.event()
                event["pull_request"]["body"] = "\n\n".join(
                    f"## {heading}\n" + ("" if heading == name else "Concrete evidence statement.")
                    for heading in check.HEADINGS
                )
                report = check.evaluate(self.policy, event)
                self.assertTrue(report["checks"]["pr_body_headings"])
                self.assertIn("pr_body_evidence", report["failed"])
                self.assertFalse(report["evidence_sections"][name])

    def test_placeholders_and_hidden_comments_are_not_evidence(self) -> None:
        for content in (
            " ", "TODO", "**TBD**", "- [ ] Pending", "N/A", "None.", "Not run",
            "---", "...", "- [x]", "<!-- I own the contribution. -->", "<!-- unclosed comment",
            "### Rights evidence",
        ):
            with self.subTest(content=content):
                event = self.event()
                event["pull_request"]["body"] = BODY.replace(
                    "I own this change or have the right to contribute every included component.",
                    content,
                )
                report = check.evaluate(self.policy, event)
                self.assertIn("pr_body_evidence", report["failed"])

    def test_fenced_and_commented_headings_are_not_sections(self) -> None:
        for body in (
            "```markdown\n" + BODY + "\n```",
            "~~~\n" + BODY + "\n~~~",
            "<!--\n" + BODY + "\n-->",
            "```markdown\n```not-a-closing-fence\n" + BODY + "\n```",
        ):
            with self.subTest(body=body[:15]):
                event = self.event()
                event["pull_request"]["body"] = body
                report = check.evaluate(self.policy, event)
                self.assertIn("pr_body_headings", report["failed"])
                self.assertIn("pr_body_evidence", report["failed"])

    def test_duplicate_required_sections_are_ambiguous(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY + "\n## Rights\nAnother attestation.\n"
        report = check.evaluate(self.policy, event)
        self.assertIn("pr_body_evidence", report["failed"])
        self.assertFalse(report["evidence_sections"]["Rights"])

    def test_code_evidence_and_explained_unavailability_are_allowed(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace(
            "python3 provenance/test_check.py", "```sh\npython3 provenance/test_check.py\n```"
        ).replace(
            "No secrets. Policy JSON only. Advisory workflow.",
            "Not run: hosted security checks remain pending on this exact candidate.",
        )
        report = check.evaluate(self.policy, event)
        self.assertTrue(report["pass"], report["failed"])

    def test_non_text_body_fails_evidence_checks(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = [BODY]
        report = check.evaluate(self.policy, event)
        self.assertIn("pr_body_headings", report["failed"])
        self.assertIn("pr_body_evidence", report["failed"])

    def test_empty_sections_unknown_bot_and_nonhex_head_fail_together(self) -> None:
        event = self.event(sender={"login": "unapproved[bot]", "type": "Bot"})
        event["pull_request"]["head"]["sha"] = "z" * 40
        event["pull_request"]["body"] = "\n\n".join("## " + name for name in check.HEADINGS)
        report = check.evaluate(self.policy, event)
        self.assertEqual(set(report["failed"]), {"exact_head_sha", "allowed_actor", "pr_body_evidence"})
        self.assertEqual(report["enforcement"], "advisory")
        self.assertFalse(report["pass"])


if __name__ == "__main__":
    unittest.main()
