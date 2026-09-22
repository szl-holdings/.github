#!/usr/bin/env python3
"""Offline negative controls for every public CI-digest output channel."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci_health_digest_public import PublicationError, public_digest


@dataclass
class Row:
    repository: str
    workflow: str = "fixture"
    provenance: str = "protected_default_branch"
    conclusion: str = "failure"
    run_id: int | None = 12
    run_attempt: int | None = 1
    run_number: int | None = 3
    event: str | None = "push"
    url: str | None = "https://attacker.invalid/leak"


def repo(name="public-fixture", private=False):
    return dict(name=name, full_name=f"szl-holdings/{name}", private=private,
                visibility="private" if private else "public", default_branch="main", archived=False)


def coverage(n):
    return dict(organization_repositories=n, active_repositories=n,
                archived_repositories=0, queried_active_repositories=n, active_workflows=n)


def classify(name, workflow, **kwargs):
    return ("INTENTIONAL" if workflow == "intentional" else "ACTIONABLE", "fixture note")


class PublicProjectionTests(unittest.TestCase):
    def render(self, entries, reds, reader=None):
        return public_digest(reds, entries, coverage=coverage(len(entries)),
                             authentication_mode="fixture", classify=classify,
                             visibility_reader=reader or repo)

    def test_private_names_workflows_and_urls_never_enter_view(self):
        private = repo("private-canary-91", True)
        view = self.render([repo(), private], {"public-fixture": [Row("public-fixture")],
            "private-canary-91": [Row("private-canary-91", "private-workflow-canary")]})
        output = view.body + json.dumps(view.red_runs)
        for secret in ("private-canary-91", "private-workflow-canary", "attacker.invalid"):
            self.assertNotIn(secret, output)
        self.assertEqual(view.red_total, 2)
        self.assertEqual(view.restricted_red_total, 1)
        self.assertEqual(view.dispositions["ACTIONABLE"], 2)

    def test_private_only_red_is_not_all_clear(self):
        view = self.render([repo("secret-fixture", True)], {"secret-fixture": [Row("secret-fixture")]})
        self.assertEqual(view.red_total, 1)
        self.assertEqual(view.red_runs, {})
        self.assertNotIn("No red latest", view.body)
        self.assertIn("**1 red workflow(s)**", view.body)

    def test_hidden_classification_is_preserved(self):
        view = self.render([repo("secret-fixture", True)], {"secret-fixture": [Row("secret-fixture", "intentional")]})
        self.assertEqual(view.dispositions["INTENTIONAL"], 1)
        self.assertEqual(view.dispositions["ACTIONABLE"], 0)
        self.assertEqual(view.red_total, 1)

    def test_public_to_private_change_withholds_detail(self):
        view = self.render([repo()], {"public-fixture": [Row("public-fixture")]}, lambda n: repo(n, True))
        self.assertEqual(view.restricted_red_total, 1)
        self.assertNotIn("public-fixture", view.body)

    def test_private_to_public_is_not_new_publication_permission(self):
        with patch(__name__ + ".repo", wraps=repo) as observed:
            view = self.render([repo("secret-fixture", True)], {"secret-fixture": [Row("secret-fixture")]},
                               lambda n: self.fail("private inventory must never be promoted by a later read"))
        self.assertEqual(view.restricted_red_total, 1)

    def test_visibility_failure_is_terminal_without_provider_message(self):
        def reader(name):
            raise PublicationError("fixture provider failure")
        with self.assertRaises(PublicationError):
            self.render([repo()], {"public-fixture": [Row("public-fixture")]}, reader)

    def test_missing_visibility_never_publishes(self):
        for field in ("private", "visibility", "full_name"):
            item = repo(); item.pop(field)
            with self.subTest(field=field), self.assertRaises(PublicationError):
                self.render([item], {"public-fixture": [Row("public-fixture")]})

    def test_truthy_private_is_not_boolean_visibility(self):
        for value in (0, 1, "false", "true", None):
            item = repo(); item["private"] = value
            with self.subTest(value=value), self.assertRaises(PublicationError):
                self.render([item], {})

    def test_inconsistent_visibility_fails_closed(self):
        item = repo(); item["visibility"] = "private"
        with self.assertRaises(PublicationError): self.render([item], {})

    def test_internal_visibility_is_hidden(self):
        item = repo("internal-fixture", True); item["visibility"] = "internal"
        view = self.render([item], {"internal-fixture": [Row("internal-fixture")]})
        self.assertEqual(view.restricted_red_total, 1)

    def test_duplicate_casefold_identity_fails_closed(self):
        with self.assertRaises(PublicationError): self.render([repo("A"), repo("a")], {})

    def test_unknown_red_repository_fails_closed(self):
        with self.assertRaises(PublicationError): self.render([repo()], {"unlisted": [Row("unlisted")]})

    def test_mismatched_row_identity_fails_closed(self):
        with self.assertRaises(PublicationError): self.render([repo()], {"public-fixture": [Row("other")]})

    def test_visibility_read_identity_mismatch_fails_closed(self):
        with self.assertRaises(PublicationError):
            self.render([repo()], {"public-fixture": [Row("public-fixture")]}, lambda n: repo("other"))

    def test_recreated_repository_id_fails_closed(self):
        item = repo(); item["id"] = 1
        def reader(n):
            value = repo(n); value["id"] = 2; return value
        with self.assertRaises(PublicationError): self.render([item], {"public-fixture": [Row("public-fixture")]}, reader)

    def test_protection_claim_is_not_inferred_from_lane_name(self):
        view = self.render([repo()], {"public-fixture": [Row("public-fixture")]})
        self.assertIn("NOT VERIFIED", view.body)
        self.assertEqual(view.red_runs["public-fixture"][0]["provenance"], "default_branch_protection_unverified")
        self.assertNotIn("protected_default_branch", view.body + json.dumps(view.red_runs))

    def test_dynamic_lane_remains_distinct(self):
        row = Row("public-fixture", provenance="github_managed_dynamic")
        view = self.render([repo()], {"public-fixture": [row]})
        self.assertEqual(view.red_runs["public-fixture"][0]["provenance"], "github_managed_dynamic")

    def test_unknown_lane_and_boolean_run_id_fail_closed(self):
        for row in (Row("public-fixture", provenance="invented"), Row("public-fixture", run_id=True)):
            with self.assertRaises(PublicationError): self.render([repo()], {"public-fixture": [row]})

    def test_markdown_is_escaped_and_link_is_canonical(self):
        row = Row("public-fixture", "<script>\n`|evil")
        view = self.render([repo()], {"public-fixture": [row]})
        self.assertNotIn("<script>", view.body)
        self.assertIn("https://github.com/szl-holdings/public-fixture/actions/runs/12", view.body)
        self.assertNotIn("attacker.invalid", view.body)

    def test_inventory_coverage_cannot_be_silently_reduced(self):
        with self.assertRaises(PublicationError):
            public_digest({}, [repo()], coverage=coverage(2), authentication_mode="fixture",
                          classify=classify, visibility_reader=repo)


class PublicPublisherIntegrationTests(unittest.TestCase):
    def test_all_output_channels_omit_private_detail_and_issue_remains_open(self):
        import ci_health_digest as chd
        from ci_health_digest_http import ReaderSelection
        private = repo("private-integration-canary", True)
        selected = ReaderSelection("github_app", "fixture", "token-canary", (private,), ())
        reds = {private["name"]: (Row(private["name"], "workflow-integration-canary"),)}
        written = []
        with tempfile.TemporaryDirectory() as d:
            report_path, summary_path = Path(d)/"report.json", Path(d)/"summary.md"
            def issue(body, *, red_total):
                written.append(body)
                self.assertEqual(red_total, 1)
                return dict(number=158, state="open")
            stdout = io.StringIO()
            with patch.object(chd, "select_reader", return_value=selected), \
                 patch.object(chd, "sweep", return_value=(reds, coverage(1))), \
                 patch.object(chd, "upsert_issue", side_effect=issue), \
                 patch.object(chd, "maybe_notify", return_value={"attempted": False}), \
                 patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}), redirect_stdout(stdout):
                code = chd.main(["--report", str(report_path)])
            output = report_path.read_text() + summary_path.read_text() + stdout.getvalue() + "".join(written)
            report = json.loads(report_path.read_text())
        self.assertEqual(code, 0)
        for canary in (private["name"], "workflow-integration-canary", "token-canary", "attacker.invalid"):
            self.assertNotIn(canary, output)
        self.assertEqual(report["summary"]["red_total"], 1)
        self.assertEqual(report["red_runs"], {})
        self.assertEqual(report["publication"]["restricted_red_total"], 1)
        self.assertEqual(report["issue"]["state"], "open")


if __name__ == "__main__":
    unittest.main(verbosity=2)
