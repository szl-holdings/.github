#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline workflow and source-context contracts. These never use real tokens."""
import contextlib
import io
import os
import sys
import tempfile
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml
import verify_hf_inventory_source as guard

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/hf-official-estate-inventory.yml"


class SourceContextTests(unittest.TestCase):
    def env(self):
        return {"GITHUB_REPOSITORY": "szl-holdings/.github", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true", "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40}

    def branch(self):
        return {"name": "main", "protected": True, "commit": {"sha": "a" * 40}}

    def test_protected_push_and_schedule(self):
        for event in ("push", "schedule"):
            env = self.env(); env["GITHUB_EVENT_NAME"] = event
            self.assertEqual(guard.verify_context(env, "a" * 40, self.branch()), "a" * 40)

    def test_dispatch_requires_explicit_true(self):
        env = self.env(); env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
        for value in ("", "false", "TRUE", "1"):
            env["HF_INVENTORY_PUBLISH_INPUT"] = value
            with self.subTest(value=value), self.assertRaisesRegex(guard.SourceBoundaryError, "EXPLICIT"):
                guard.verify_context(env, "a" * 40, self.branch())
        env["HF_INVENTORY_PUBLISH_INPUT"] = "true"
        self.assertEqual(guard.verify_context(env, "a" * 40, self.branch()), "a" * 40)

    def test_pull_request_and_target_events_rejected(self):
        for event in ("pull_request", "pull_request_target", "workflow_run", "merge_group", "repository_dispatch"):
            env = self.env(); env["GITHUB_EVENT_NAME"] = event
            with self.subTest(event=event), self.assertRaisesRegex(guard.SourceBoundaryError, "EVENT"):
                guard.verify_context(env, "a" * 40, self.branch())

    def test_source_ref_repository_and_protection_rejected(self):
        for field, value in (("GITHUB_REPOSITORY", "other/.github"), ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_REF_PROTECTED", "false"), ("GITHUB_REF_PROTECTED", "1"), ("GITHUB_SHA", "0" * 40), ("GITHUB_SHA", "a" * 39), ("GITHUB_SHA", "a" * 40 + "\n")):
            env = self.env(); env[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(guard.SourceBoundaryError):
                guard.verify_context(env, "a" * 40, self.branch())
        with self.assertRaises(guard.SourceBoundaryError):
            guard.verify_context(self.env(), "b" * 40, self.branch())

    def test_fresh_branch_identity_is_required(self):
        for branch in ({}, {"name": "main", "protected": 1, "commit": {"sha": "a" * 40}}, {"name": "main", "protected": True, "commit": {"sha": "b" * 40}}, {"name": "feature", "protected": True, "commit": {"sha": "a" * 40}}):
            with self.subTest(branch=branch), self.assertRaises(guard.SourceBoundaryError):
                guard.verify_context(self.env(), "a" * 40, branch)

    def test_redirects_and_header_injection_rejected(self):
        with self.assertRaises(guard.SourceBoundaryError):
            guard._NoRedirect().redirect_request(None, None, 302, "", {}, "https://outside.invalid")
        for token in ("", "x\r\ny"):
            with self.assertRaises(guard.SourceBoundaryError):
                guard.read_main(token)

    def test_invalid_context_never_requests_github(self):
        with patch.dict(guard.os.environ, self.env(), clear=True):
            guard.os.environ["GITHUB_EVENT_NAME"] = "pull_request"
            with patch.object(guard.subprocess, "check_output", return_value="a" * 40), patch.object(guard, "read_main") as request, patch("builtins.print"):
                self.assertEqual(guard.main(), 2)
                request.assert_not_called()


class WorkflowBoundaryTests(unittest.TestCase):
    def workflow(self):
        return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_verify_job_and_workflow_environment_have_no_credentials(self):
        workflow = self.workflow()
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertNotIn("secrets.", json.dumps(workflow.get("env", {})))
        self.assertNotIn("secrets.", json.dumps(workflow["jobs"]["verify"]))
        self.assertNotIn("GITHUB_ENV", json.dumps(workflow))
        self.assertNotIn("pull_request_target", workflow["on"])

    def test_privileged_job_is_separate_and_protected(self):
        job = self.workflow()["jobs"]["inventory"]
        self.assertEqual(job["needs"], "verify")
        self.assertNotIn("secrets.", json.dumps(job.get("env", {})))
        for condition in ("github.repository == 'szl-holdings/.github'", "github.ref == 'refs/heads/main'", "github.ref_protected == true", "github.event_name == 'push'", "github.event_name == 'schedule'", "github.event_name == 'workflow_dispatch'", "inputs.publish == true"):
            self.assertIn(condition, job["if"])
        self.assertNotIn("always()", job["if"])

    def test_secrets_exist_only_in_the_collector_step(self):
        job = self.workflow()["jobs"]["inventory"]
        steps = job["steps"]
        privileged = [step for step in steps if "secrets." in json.dumps(step)]
        self.assertEqual(len(privileged), 1)
        self.assertEqual(privileged[0]["id"], "estate")
        text = privileged[0]["run"]
        self.assertIn("verify_hf_inventory_source.py", text)
        self.assertIn('--publish', text)
        self.assertIn('> "$private_log" 2>&1', text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("pytest", text)
        for step in steps:
            if step.get("uses", "").startswith("actions/checkout@"):
                self.assertEqual(step["with"]["ref"], "${{ github.sha }}")
                self.assertEqual(step["with"]["persist-credentials"], "false")

    def test_only_public_projection_is_uploaded_by_inventory(self):
        steps = self.workflow()["jobs"]["inventory"]["steps"]
        uploads = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["with"]["path"], "reports/hf-official-estate-inventory-public.json")
        self.assertIn("steps.projection.outcome == 'success'", uploads[0]["if"])
        self.assertIn("rm -f", steps[-1]["run"])
        self.assertNotIn("cat ", "\n".join(step.get("run", "") for step in steps))

    def test_protected_job_has_no_implicit_failure_to_success(self):
        workflow = self.workflow()
        for job in workflow["jobs"].values():
            self.assertNotIn("continue-on-error", job)
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)
        estate = next(step for step in workflow["jobs"]["inventory"]["steps"] if step.get("id") == "estate")
        self.assertIn('exit "$code"', estate["run"])
        self.assertNotIn("exit 0", estate["run"])


class CollectorOutputBoundaryTests(unittest.TestCase):
    def test_compat_uses_the_single_public_projector(self):
        import hf_official_estate_inventory_compat as compat
        import hf_inventory_public_boundary as boundary
        self.assertIs(compat.public_report, boundary.public_report)

    def test_operator_records_are_retained_without_console_output(self):
        import hf_official_estate_inventory_compat as compat
        collector = object.__new__(compat.CurrentHubEstateInventory)
        collector.actions = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            collector.record("PRIVATE-SENTINEL", "inventory", "validated", "PRIVATE-DETAIL")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(collector.actions[0].target, "PRIVATE-SENTINEL")
        self.assertEqual(collector.actions[0].detail, "PRIVATE-DETAIL")

    def test_collection_cli_does_not_print_authenticated_counts(self):
        import hf_official_estate_inventory_compat as compat
        output = io.StringIO()
        with patch.object(compat, "CurrentHubEstateInventory") as factory, patch.object(sys, "argv", ["inventory"]), patch.dict(os.environ, {"HF_TOKEN": "unit-test-not-a-real-token"}, clear=True), contextlib.redirect_stdout(output):
            factory.return_value.run.return_value = {"summary": {"error": 0, "ok": 987654, "warning": 123456}}
            self.assertEqual(compat.main(), 0)
        self.assertNotIn("987654", output.getvalue())
        self.assertNotIn("123456", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["scope"], "OPERATOR_REPORT_WITHHELD")

    def test_projection_cli_never_constructs_an_authenticated_collector(self):
        import hf_official_estate_inventory_compat as compat
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "operator.json"
            destination = Path(directory) / "public.json"
            source.write_text(json.dumps({"assets": {"models": [{"id": "PRIVATE-SENTINEL", "private": True}]}, "summary": {"ok": 123456}}))
            with patch.object(compat, "CurrentHubEstateInventory") as factory, patch.object(sys, "argv", ["inventory", "--public-projection", str(source), "--output", str(destination)]), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(compat.main(), 0)
                factory.assert_not_called()
            rendered = destination.read_text()
            self.assertNotIn("PRIVATE-SENTINEL", rendered)
            self.assertNotIn("123456", rendered)

    def test_failed_cli_withholds_provider_error_details(self):
        import hf_official_estate_inventory_compat as compat
        output = io.StringIO()
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.object(compat, "CurrentHubEstateInventory") as factory, patch.object(sys, "argv", ["inventory"]), patch.dict(os.environ, {"HF_TOKEN": "unit-test-not-a-real-token"}, clear=True), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    factory.return_value.run.side_effect = RuntimeError("PRIVATE-SENTINEL")
                    self.assertEqual(compat.main(), 2)
                report = Path("reports/hf-official-estate-inventory-latest.json").read_text()
                self.assertNotIn("PRIVATE-SENTINEL", output.getvalue() + report)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
