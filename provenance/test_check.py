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
            "### Rights evidence", "Rights:",
        ):
            with self.subTest(content=content):
                event = self.event()
                event["pull_request"]["body"] = BODY.replace(
                    "I own this change or have the right to contribute every included component.",
                    content,
                )
                report = check.evaluate(self.policy, event)
                self.assertIn("pr_body_evidence", report["failed"])

    def test_bare_rollback_template_label_is_not_evidence(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace(
            "Revert the squash merge commit on .github.", "Rollback:"
        )
        report = check.evaluate(self.policy, event)
        self.assertFalse(report["evidence_sections"]["Rollback"])
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

    def test_html_comment_literal_inside_fence_preserves_later_sections(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace(
            "python3 provenance/test_check.py",
            "```sh\nrg '<!--' .github/pull_request_template.md\n```",
        )
        report = check.evaluate(self.policy, event)
        self.assertTrue(report["pass"], report["failed"])

    def test_raw_html_code_blocks_cannot_supply_required_headings(self) -> None:
        for tag in ("pre", "code", "PRE", "CoDe"):
            with self.subTest(tag=tag):
                event = self.event()
                event["pull_request"]["body"] = f"<{tag}>\n{BODY}\n</{tag}>"
                report = check.evaluate(self.policy, event)
                self.assertIn("pr_body_headings", report["failed"])
                self.assertIn("pr_body_evidence", report["failed"])

    def test_inline_raw_html_code_is_ignored_without_hiding_visible_sections(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = "<code>## Fake\ntext</code>\n" + BODY
        report = check.evaluate(self.policy, event)
        self.assertTrue(report["pass"], report["failed"])
        self.assertNotIn("Fake", report["headings"])

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

    def with_rights(self, content: str) -> dict:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace(
            "I own this change or have the right to contribute every included component.", content,
        )
        return check.evaluate(self.policy, event)

    def test_markup_only_and_whitespace_entities_are_not_evidence(self) -> None:
        for content in (
            "<br>", "<span></span>", '<a title="ownership confirmed"></a>',
            "&nbsp;", "&#160;", "&#x20;", "&amp;", "<span>&nbsp;</span>",
            '<input value="ownership confirmed">', "<hr>",
            '<span title="quoted > ownership confirmed">&nbsp;</span>',
            '<span title="quoted >\nattribute evidence"> </span>',
        ):
            with self.subTest(content=content):
                self.assertFalse(self.with_rights(content)["evidence_sections"]["Rights"])

    def test_visible_inline_html_text_remains_evidence(self) -> None:
        self.assertTrue(self.with_rights("<strong>I own this change.</strong>")["pass"])
        self.assertFalse(self.with_rights("<em>TODO</em>")["evidence_sections"]["Rights"])

    def test_inline_comment_looking_code_preserves_sections(self) -> None:
        for content in (
            "Executed `rg '<!--' policy.md` locally.",
            "Executed ``printf '`<!--`'`` locally.",
            "Verified `<code>` is rendered literally.",
        ):
            with self.subTest(content=content):
                event = self.event()
                event["pull_request"]["body"] = BODY.replace("python3 provenance/test_check.py", content)
                report = check.evaluate(self.policy, event)
                self.assertTrue(report["pass"], report["failed"])

    def test_literal_markup_is_retained_inside_code_evidence(self) -> None:
        for content in ("`<br>`", "`&nbsp;`", "```html\n<span></span>\n```", "~~~html\n<!-- literal command -->\n~~~"):
            with self.subTest(content=content):
                self.assertTrue(self.with_rights(content)["evidence_sections"]["Rights"])

    def test_empty_fence_info_string_is_not_evidence(self) -> None:
        self.assertFalse(self.with_rights("```ownership\n``` ")["evidence_sections"]["Rights"])

    def test_raw_html_blocks_do_not_supply_headings(self) -> None:
        for tag in ("script", "style", "textarea", "div", "table", "section", "details"):
            with self.subTest(tag=tag):
                event = self.event()
                event["pull_request"]["body"] = f'<{tag} data-note=">">\n{BODY}\n</{tag}>'
                report = check.evaluate(self.policy, event)
                self.assertIn("pr_body_headings", report["failed"])

    def test_blank_lines_do_not_expose_headings_in_opaque_container(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = "<div hidden>\n\n" + BODY + "\n\n</div>"
        self.assertIn("pr_body_headings", check.evaluate(self.policy, event)["failed"])

    def test_raw_html_declarations_do_not_supply_headings(self) -> None:
        for opening, closing in (("<![CDATA[", "]]>") , ("<?instruction", "?>"), ('<!DOCTYPE note "', '">')):
            with self.subTest(opening=opening):
                event = self.event()
                event["pull_request"]["body"] = opening + "\n" + BODY + "\n" + closing
                self.assertIn("pr_body_headings", check.evaluate(self.policy, event)["failed"])

    def test_multiline_quoted_tag_attributes_cannot_supply_headings(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = '<div data-note="quoted >\n' + BODY + '\n">\n</div>'
        self.assertIn("pr_body_headings", check.evaluate(self.policy, event)["failed"])

    def test_closed_html_regions_preserve_later_real_sections(self) -> None:
        for prefix in (
            '<div data-note=">">\n## Rights\nignored\n</div>\n',
            '<table>\n<tr><td title="</table>">ignored</td></tr>\n</table>\n',
            '<!-- `not code`\n## Rights\n-->\n',
            '<![CDATA[\n## Rights\n]]>\n',
            '<div>\n<div>\n</div>\n## Rights\n</div>\n',
        ):
            with self.subTest(prefix=prefix):
                event = self.event()
                event["pull_request"]["body"] = prefix + BODY
                report = check.evaluate(self.policy, event)
                self.assertTrue(report["pass"], report["failed"])

    def test_special_raw_tag_names_use_exact_boundaries(self) -> None:
        for tag in ("code-sample", "pre-view", "script-example", "style-note"):
            with self.subTest(tag=tag):
                event = self.event()
                event["pull_request"]["body"] = f"<{tag}>\nignored\n</{tag}>\n\n" + BODY
                report = check.evaluate(self.policy, event)
                self.assertTrue(report["pass"], report["failed"])

    def test_tag_removal_cannot_create_an_atx_heading(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace("## Rights", "<span></span>## Rights")
        self.assertIn("pr_body_headings", check.evaluate(self.policy, event)["failed"])

    def test_valid_closing_hashes_are_normalized(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY
        for name in check.HEADINGS:
            event["pull_request"]["body"] = event["pull_request"]["body"].replace("## " + name + "\n", "## " + name + " ### \t\n")
        report = check.evaluate(self.policy, event)
        self.assertTrue(report["pass"], report["failed"])

    def test_duplicate_closing_hash_heading_remains_ambiguous(self) -> None:
        for heading in ("## Rights ###", "## Rights ## \t", "  ## Rights #"):
            with self.subTest(heading=heading):
                event = self.event()
                event["pull_request"]["body"] = BODY + "\n" + heading + "\nAnother reason.\n"
                report = check.evaluate(self.policy, event)
                self.assertFalse(report["evidence_sections"]["Rights"])

    def test_unseparated_hashes_do_not_become_closing_hashes(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY.replace("## Rights\n", "## Rights###\n")
        self.assertFalse(check.evaluate(self.policy, event)["headings"]["Rights"])

    def test_long_heading_whitespace_is_not_repeatedly_backtracked(self) -> None:
        # Near the body bound, the former lazy capture / trailing-whitespace
        # regex pair took quadratic time. Keep this a semantic, untimed test.
        padding = " " * 200000
        name = "Rights" + padding + "x"
        self.assertEqual(check.evidence_sections("## " + name + "\nEvidence."), {name: ["Evidence.\n"]})
        self.assertEqual(check.evidence_sections("## Rights" + padding + "###\nEvidence."), {"Rights": ["Evidence.\n"]})

    def test_multiline_raw_closing_tag_preserves_following_sections(self) -> None:
        for tag in ("pre", "code", "script", "style", "textarea"):
            with self.subTest(tag=tag):
                event = self.event()
                event["pull_request"]["body"] = f"<{tag}>\nignored\n</{tag}\n>\n" + BODY
                report = check.evaluate(self.policy, event)
                self.assertTrue(report["pass"], report["failed"])

    def test_body_bound_fails_closed_without_changing_advisory_authority(self) -> None:
        event = self.event()
        event["pull_request"]["body"] = BODY + " " * check.MAX_BODY_CHARS
        report = check.evaluate(self.policy, event)
        self.assertIn("pr_body_headings", report["failed"])
        self.assertIn("pr_body_evidence", report["failed"])
        self.assertEqual(report["enforcement"], "advisory")
        self.assertEqual(report["schema"], "szl.provenance-check/v1")


if __name__ == "__main__":
    unittest.main()
