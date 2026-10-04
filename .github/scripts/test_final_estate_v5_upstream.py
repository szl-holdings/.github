#!/usr/bin/env python3
from __future__ import annotations

import os
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import final_estate_reconciliation_v5 as controller
from final_estate_reconciliation_v5 import evaluate_upstream_readiness
from final_estate_v5_core import Gate, GitHubClient, MAX_RESPONSE_BYTES
import final_estate_v5_core as core
from final_estate_v5_probes import safe_probe
from test_final_estate_v5_probes import FakeResponse, FakeSession

patch = unittest.mock.patch
SHA = "a" * 40
SOURCE_ENV = {
    "GITHUB_SHA": SHA, "EVIDENCE_GENERATION": SHA,
    "GITHUB_REPOSITORY": "szl-holdings/.github", "GITHUB_REF": "refs/heads/main",
    "GITHUB_EVENT_NAME": "push",
}


class FinalEstateReadOnlyBoundaryTests(unittest.TestCase):
    def source_gate(self, changes=None, actual=SHA, protected=SHA):
        client = unittest.mock.Mock()
        client.controller_head.return_value = protected
        with patch.dict(os.environ, {**SOURCE_ENV, **(changes or {})}, clear=True), patch.object(
            controller.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, actual + "\n")
        ):
            return controller.evaluate_controller_source(client), client

    def test_exact_main_source_admitted_on_all_existing_trigger_lanes(self):
        for event in ("push", "workflow_dispatch", "workflow_run"):
            changes = {"GITHUB_EVENT_NAME": event}
            if event == "workflow_run":
                changes["UPSTREAM_WORKFLOW"] = "HF Release Readiness Terminal"
            gate, client = self.source_gate(changes)
            self.assertTrue(gate.ok)
            self.assertFalse(gate.evidence["atomic_lease"])
            client.controller_head.assert_called_once_with()

    def test_stale_upstream_or_untrusted_event_rejected_before_provider_read(self):
        for changes in (
            {"EVIDENCE_GENERATION": "b" * 40}, {"GITHUB_SHA": "0" * 40},
            {"GITHUB_REF": "refs/heads/proposal"}, {"GITHUB_REPOSITORY": "elsewhere/.github"},
            {"GITHUB_EVENT_NAME": "pull_request"},
            {"GITHUB_EVENT_NAME": "workflow_run", "UPSTREAM_WORKFLOW": "other workflow"},
        ):
            with self.subTest(changes=changes):
                gate, client = self.source_gate(changes)
                self.assertFalse(gate.ok)
                client.controller_head.assert_not_called()

    def test_installed_mismatch_or_current_main_movement_rejected(self):
        for actual, protected in (("b" * 40, SHA), (SHA, "b" * 40)):
            self.assertFalse(self.source_gate(actual=actual, protected=protected)[0].ok)

    def test_unverified_source_does_not_probe_or_read_evidence(self):
        with patch.object(controller, "evaluate_controller_source", return_value=Gate("source", False, "stale", {})), patch.object(
            controller, "safe_probe", side_effect=AssertionError("no public call allowed")
        ), patch.object(controller, "evaluate_issue_gate", side_effect=AssertionError("no evidence call allowed")):
            report = controller.evaluate(unittest.mock.Mock())
        self.assertFalse(report["operational_verified"])
        self.assertEqual(report["status"], "NOT_VERIFIED")

    def test_main_movement_after_successful_observations_prevents_success(self):
        passed = Gate("fixture", True, "SYNTHETIC", {})
        with patch.object(controller, "evaluate_controller_source", side_effect=[passed, Gate("source", False, "moved", {})]), patch.object(
            controller, "evaluate_upstream_readiness", return_value=passed
        ), patch.object(controller, "evaluate_issue_gate", return_value=passed), patch.object(
            controller, "evaluate_release_revision_consistency", return_value=passed
        ), patch.object(controller, "evaluate_replit_decommission", return_value=passed), patch.object(
            controller, "evaluate_a11oy_source", return_value=(passed, SHA)
        ), patch.object(controller, "safe_probe", return_value=passed), patch.object(
            controller, "evaluate_open_public_prs", return_value=passed
        ):
            report = controller.evaluate(unittest.mock.Mock())
        self.assertEqual(report["summary"]["error"], 1)
        self.assertFalse(report["operational_verified"])

    def test_controller_requires_actual_protected_branch_boolean(self):
        client = GitHubClient(None)
        for protected in (False, None, 1, "true"):
            response = unittest.mock.Mock()
            response.json.return_value = {"name": "main", "protected": protected, "commit": {"sha": SHA}}
            with patch.object(client, "request", return_value=response), self.assertRaisesRegex(RuntimeError, "PROTECTED_MAIN"):
                client.controller_head()

    def test_github_write_and_out_of_scope_targets_fail_before_transport(self):
        client = GitHubClient("SYNTHETIC-NOT-A-CREDENTIAL")
        with patch.object(client.session, "request", side_effect=AssertionError("no network")) as transport:
            for method, path, payload in (
                ("POST", "/repos/szl-holdings/.github/issues", {}),
                ("PATCH", "/repos/szl-holdings/.github/issues/263", {}),
                ("GET", "/repos/szl-holdings/.github/issues/263", {}),
                ("GET", "/repos/other/repo/pulls", None),
                ("GET", "/repos/szl-holdings/../pulls", None),
                ("GET", "https://other.invalid/", None),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(RuntimeError, "READ_SCOPE"):
                    client.request(method, path, payload=payload)
            transport.assert_not_called()
        self.assertFalse(client.session.trust_env)
        self.assertFalse(hasattr(client, "upsert_report_issue"))

    def test_github_redirect_and_oversized_body_fail_without_following(self):
        client = GitHubClient(None)
        response = unittest.mock.Mock(status_code=302)
        with patch.object(client.session, "request", return_value=response) as transport, self.assertRaisesRegex(RuntimeError, "HTTP 302"):
            client.request("GET", "/orgs/szl-holdings")
        self.assertFalse(transport.call_args.kwargs["allow_redirects"])
        response.close.assert_called_once_with()
        response = unittest.mock.Mock(status_code=200)
        response.iter_content.return_value = iter([b"x" * MAX_RESPONSE_BYTES, b"x"])
        with patch.object(client.session, "request", return_value=response), self.assertRaisesRegex(RuntimeError, "RESPONSE_BUDGET"):
            client.request("GET", "/orgs/szl-holdings")
        response.close.assert_called_once_with()

    def test_github_call_budget_prevents_extra_transport(self):
        client = GitHubClient(None)
        client.calls = 532
        with patch.object(client.session, "request") as transport, self.assertRaisesRegex(RuntimeError, "READ_BUDGET"):
            client.request("GET", "/orgs/szl-holdings")
        transport.assert_not_called()

    def test_bounded_github_body_still_decodes_and_closes_real_response(self):
        response = core.requests.Response()
        response.status_code = 200
        response.raw = io.BytesIO(b'{"login":"szl-holdings","public_repos":3}')
        client = GitHubClient(None)
        with patch.object(client.session, "request", return_value=response), patch.object(response, "close", wraps=response.close) as closed:
            value = client.request("GET", "/orgs/szl-holdings").json()
        self.assertEqual(value["public_repos"], 3)
        closed.assert_called_once_with()

    def test_expired_stream_deadline_rejects_even_small_complete_body(self):
        response = unittest.mock.Mock()
        response.iter_content.return_value = iter([b"{}"])
        with patch.object(core.time, "monotonic", return_value=10), self.assertRaisesRegex(RuntimeError, "RESPONSE_BUDGET"):
            core.bounded_content(response, deadline=9)
        response.close.assert_called_once_with()

    def test_public_probe_rejects_redirect_or_oversized_body(self):
        spec = controller.PROBES["a11oy_product"]
        for status, body in ((302, b"redirect"), (200, b"x" * (MAX_RESPONSE_BYTES + 1))):
            session = FakeSession(
                head=FakeResponse(status_code=200, url=spec.url, content_type="text/html"),
                get=FakeResponse(status_code=status, url=spec.url, content_type="text/html", body=body),
            )
            with patch.object(session, "get", wraps=session.get) as transport:
                self.assertFalse(safe_probe("a11oy_product", spec, None, session=session).ok)
            self.assertFalse(transport.call_args.kwargs["allow_redirects"])
            self.assertTrue(transport.call_args.kwargs["stream"])

    def test_removed_issue_flag_is_rejected_before_client_creation(self):
        with patch.object(sys, "argv", ["verifier", "--publish-issue"]), patch.object(controller, "GitHubClient") as client, patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as error:
            controller.main()
        self.assertEqual(error.exception.code, 2)
        client.assert_not_called()

    def test_failed_verdict_is_written_but_enforced_and_oversize_is_not_written(self):
        report = {"status": "NOT_VERIFIED", "operational_verified": False}
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "report.json"
            with patch.object(sys, "argv", ["verifier", "--output", str(output), "--enforce"]), patch.object(controller, "evaluate", return_value=report), patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(controller.main(), 1)
                self.assertEqual(json.loads(output.read_bytes()), report)
                output.unlink()
                with patch.object(controller, "MAX_REPORT_BYTES", 1), self.assertRaisesRegex(RuntimeError, "REPORT_BUDGET"):
                    controller.main()
                self.assertFalse(output.exists())


class FinalEstateUpstreamTests(unittest.TestCase):
    def test_successful_readiness_workflow_passes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "UPSTREAM_WORKFLOW": "HF Release Readiness Terminal",
                "UPSTREAM_CONCLUSION": "success",
                "UPSTREAM_RUN_URL": "https://github.com/example/actions/runs/1",
            },
            clear=False,
        ):
            gate = evaluate_upstream_readiness()
        self.assertTrue(gate.ok)
        self.assertTrue(gate.evidence["workflow_run_bound"])
        self.assertEqual(gate.evidence["conclusion"], "success")

    def test_failed_or_missing_readiness_conclusion_fails_closed(self) -> None:
        for conclusion in ("failure", "cancelled", ""):
            with self.subTest(conclusion=conclusion):
                with patch.dict(
                    os.environ,
                    {
                        "UPSTREAM_WORKFLOW": "HF Release Readiness Terminal",
                        "UPSTREAM_CONCLUSION": conclusion,
                    },
                    clear=False,
                ):
                    gate = evaluate_upstream_readiness()
                self.assertFalse(gate.ok)

    def test_direct_manual_evaluation_keeps_issue_evidence_authoritative(self) -> None:
        clean = dict(os.environ)
        clean.pop("UPSTREAM_WORKFLOW", None)
        clean.pop("UPSTREAM_CONCLUSION", None)
        clean.pop("UPSTREAM_RUN_URL", None)
        with patch.dict(os.environ, clean, clear=True):
            gate = evaluate_upstream_readiness()
        self.assertTrue(gate.ok)
        self.assertFalse(gate.evidence["workflow_run_bound"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
