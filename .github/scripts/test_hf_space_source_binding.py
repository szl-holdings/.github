#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
import unittest.mock as mock
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.path.join(HERE, "hf_space_source_binding.py")

# The contract tests are network-free and must run in the repository's stdlib-only
# test job. Stub import-time client modules only when they are not installed; every
# API interaction is injected below.
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub
if "huggingface_hub" not in sys.modules:
    hub_stub = types.ModuleType("huggingface_hub")
    hub_stub.HfApi = object
    sys.modules["huggingface_hub"] = hub_stub

SPEC = importlib.util.spec_from_file_location("hf_space_source_binding", MODULE_PATH)
assert SPEC and SPEC.loader
binding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding)


class FakeApi:
    def __init__(self, values=None):
        self.values = values or {}
        self.add_calls = []

    def add_space_variable(self, **kwargs):
        self.add_calls.append(kwargs)
        self.values[kwargs["key"]] = SimpleNamespace(value=kwargs["value"])

    def get_space_variables(self, repo_id):
        self.repo_id = repo_id
        return self.values


class FakeResponse:
    def __init__(self, payload, status=200, content_type="application/json"):
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.responses = list(response) if isinstance(response, list) else [response]
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "/api/build-info"
        )

    @staticmethod
    def observed_payload(revision: str) -> dict[str, object]:
        return {
            "status": "OBSERVED",
            "build": {"state": "OBSERVED", "revision": revision},
            "runtime": {"python": "3.12"},
            "receipt_minted": False,
        }

    def test_normalize_requires_exact_repo_key_sha_and_same_host_path(self):
        self.assertEqual(self.normalized["revision"], self.sha)
        for args in (
            ("bad", "SZL_GIT_SHA", self.sha, "/api/build-info"),
            ("SZLHOLDINGS/a11oy", "bad-key", self.sha, "/api/build-info"),
            ("SZLHOLDINGS/a11oy", "SZL_GIT_SHA", "short", "/api/build-info"),
            ("SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "https://evil.example/x"),
            ("SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "//evil.example/x"),
        ):
            with self.subTest(args=args):
                with self.assertRaises(binding.SourceBindingError):
                    binding.normalize_binding(*args)

    def test_bind_updates_one_variable_then_reads_it_back(self):
        api = FakeApi()
        report = binding.bind_variable(api, self.normalized)
        self.assertTrue(report["matched"])
        self.assertEqual(len(api.add_calls), 1)
        self.assertEqual(api.add_calls[0]["repo_id"], "SZLHOLDINGS/a11oy")
        self.assertEqual(api.add_calls[0]["key"], "SZL_GIT_SHA")
        self.assertEqual(api.add_calls[0]["value"], self.sha)
        self.assertNotIn("token", api.add_calls[0])

    def test_variable_readback_mismatch_fails_closed(self):
        api = FakeApi({"SZL_GIT_SHA": SimpleNamespace(value="b" * 40)})
        with self.assertRaisesRegex(binding.SourceBindingError, "readback mismatch"):
            binding.verify_variable(api, self.normalized)

    def test_runtime_probe_requires_observed_exact_revision_and_no_receipt(self):
        payload = self.observed_payload(self.sha)
        session = FakeSession(FakeResponse(payload))
        report = binding.verify_runtime_probe(self.normalized, session=session)
        canonical = "https://szlholdings-a11oy.hf.space/api/build-info"
        self.assertTrue(report["matched"])
        self.assertEqual(report["url"], canonical)
        self.assertEqual(session.calls[0][0], canonical)
        self.assertNotIn("__szl_", session.calls[0][0])
        request = session.calls[0][1]
        self.assertFalse(request["allow_redirects"])
        self.assertEqual(
            request["headers"][binding.PROBE_SOURCE_HEADER],
            self.sha,
        )
        self.assertEqual(request["headers"][binding.PROBE_ATTEMPT_HEADER], "1")
        self.assertEqual(
            request["headers"]["Cache-Control"],
            "no-cache, no-store, max-age=0",
        )

        payload["build"]["revision"] = "b" * 40
        with self.assertRaisesRegex(binding.SourceBindingError, "did not converge"):
            binding.verify_runtime_probe(
                self.normalized,
                session=FakeSession(FakeResponse(payload)),
                timeout_seconds=0,
            )

    def test_runtime_probe_preserves_caller_query_verbatim(self):
        normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy",
            "SZL_GIT_SHA",
            self.sha,
            "/api/build-info?refresh=1&mode=full",
        )
        session = FakeSession(FakeResponse(self.observed_payload(self.sha)))
        report = binding.verify_runtime_probe(normalized, session=session)
        canonical = (
            "https://szlholdings-a11oy.hf.space/"
            "api/build-info?refresh=1&mode=full"
        )
        self.assertEqual(report["url"], canonical)
        self.assertEqual(session.calls[0][0], canonical)
        self.assertNotIn("__szl_source_revision", session.calls[0][0])
        self.assertNotIn("__szl_probe_attempt", session.calls[0][0])

    def test_runtime_probe_converges_from_stale_revision_and_records_every_attempt(self):
        stale = self.observed_payload("b" * 40)
        current = self.observed_payload(self.sha)
        clock = FakeClock()
        session = FakeSession([FakeResponse(stale), FakeResponse(current)])
        report = binding.verify_runtime_probe(
            self.normalized,
            session=session,
            timeout_seconds=10,
            interval_seconds=2,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(report["matched"])
        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual(len(report["observations"]), 2)
        self.assertFalse(report["observations"][0]["matched"])
        self.assertTrue(report["observations"][1]["matched"])
        self.assertEqual(session.calls[0][0], session.calls[1][0])
        first_headers = session.calls[0][1]["headers"]
        second_headers = session.calls[1][1]["headers"]
        self.assertEqual(first_headers[binding.PROBE_ATTEMPT_HEADER], "1")
        self.assertEqual(second_headers[binding.PROBE_ATTEMPT_HEADER], "2")
        self.assertEqual(first_headers[binding.PROBE_SOURCE_HEADER], self.sha)
        self.assertEqual(second_headers[binding.PROBE_SOURCE_HEADER], self.sha)

    def test_runtime_probe_retries_transient_404_without_changing_url(self):
        current = self.observed_payload(self.sha)
        clock = FakeClock()
        session = FakeSession(
            [
                FakeResponse(
                    {"detail": "Application not found"},
                    status=404,
                    content_type="text/html",
                ),
                FakeResponse(current),
            ]
        )
        report = binding.verify_runtime_probe(
            self.normalized,
            session=session,
            timeout_seconds=10,
            interval_seconds=2,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(report["matched"])
        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual(report["observations"][0]["http_status"], 404)
        self.assertEqual(report["observations"][1]["http_status"], 200)
        self.assertEqual(session.calls[0][0], session.calls[1][0])
        self.assertNotIn("__szl_", session.calls[0][0])

    def test_runtime_probe_exhaustion_is_bounded_and_retains_observations(self):
        stale = self.observed_payload("b" * 40)
        clock = FakeClock()
        with self.assertRaises(binding.SourceBindingError) as raised:
            binding.verify_runtime_probe(
                self.normalized,
                session=FakeSession(FakeResponse(stale)),
                timeout_seconds=4,
                interval_seconds=2,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )
        evidence = raised.exception.evidence
        self.assertIsNotNone(evidence)
        self.assertFalse(evidence["matched"])
        self.assertEqual(evidence["attempt_count"], 3)
        self.assertEqual(clock.now, 4)

    def test_runtime_probe_rejects_non_json_and_non_200(self):
        with self.assertRaises(binding.SourceBindingError):
            binding.verify_runtime_probe(
                self.normalized,
                session=FakeSession(FakeResponse({}, status=503)),
                timeout_seconds=0,
            )
        response = FakeResponse({}, status=200, content_type="text/html")
        response.json = mock.Mock(side_effect=ValueError("not json"))
        with self.assertRaises(binding.SourceBindingError):
            binding.verify_runtime_probe(
                self.normalized,
                session=FakeSession(response),
                timeout_seconds=0,
            )

    def test_source_contains_no_synthetic_query_or_privileged_mutation(self):
        with open(MODULE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in (
            "__szl_source_revision",
            "__szl_probe_attempt",
            "add_space_secret",
            "delete_space_secret",
            "request_space_hardware",
            "set_space_sleep_time",
            "update_repo_settings",
            "restart_space",
            "duplicate_space",
        ):
            self.assertNotIn(forbidden, source)

    def test_cli_failure_report_contains_no_token(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "failure.json")
            argv = [
                "hf_space_source_binding.py",
                "--mode",
                "verify",
                "--repo-id",
                "SZLHOLDINGS/a11oy",
                "--variable",
                "SZL_GIT_SHA",
                "--revision",
                self.sha,
                "--probe-path",
                "/api/build-info",
                "--output",
                output,
                "--timeout-seconds",
                "0",
            ]
            secret = "super-secret-token"
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                os.environ, {"HF_TOKEN": secret}, clear=False
            ), mock.patch.object(
                binding,
                "run",
                side_effect=binding.SourceBindingError(
                    "fail closed", evidence={"matched": False, "observations": []}
                ),
            ):
                self.assertEqual(binding.main(), 1)
            with open(output, encoding="utf-8") as fh:
                report = json.load(fh)
        self.assertFalse(report["ok"])
        self.assertFalse(report["runtime_probe"]["matched"])
        self.assertNotIn(secret, json.dumps(report, sort_keys=True))


class ReusableWorkflowSourceBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(HERE, "..", "workflows", "reusable-hf-deploy.yml")
        with open(path, encoding="utf-8") as fh:
            cls.workflow = fh.read()
        witness_path = os.path.join(
            HERE, "..", "workflows", "reusable-hf-deploy-source-witness.yml"
        )
        with open(witness_path, encoding="utf-8") as fh:
            cls.witness_workflow = fh.read()

    def test_source_binding_inputs_are_optional_but_paired(self):
        self.assertIn("source-revision-variable:", self.workflow)
        self.assertIn("source-revision-probe-path:", self.workflow)
        self.assertIn(
            "source-revision-variable and source-revision-probe-path must be supplied together",
            self.workflow,
        )

    def test_exact_checked_out_sha_is_derived_inside_runner(self):
        self.assertIn('SOURCE_SHA="$(git -C caller rev-parse HEAD)"', self.workflow)
        self.assertNotIn("SOURCE_SHA: ${{ github.sha }}", self.workflow)

    def test_publication_binding_attestation_and_runtime_verification_are_ordered(self):
        deploy = self.workflow.index("Deploy Dockerfile-derived files to the Space")
        bind = self.workflow.index("Bind exact source revision after publication")
        attest = self.workflow.index("Attest exact running commit, bytes, and smoke routes")
        verify = self.workflow.index("Verify running application source identity")
        self.assertLess(deploy, bind)
        self.assertLess(bind, attest)
        self.assertLess(attest, verify)

    def test_inputs_enter_shell_only_through_environment(self):
        for safe in (
            "SOURCE_REVISION_VARIABLE: ${{ inputs.source-revision-variable }}",
            "SOURCE_REVISION_PROBE_PATH: ${{ inputs.source-revision-probe-path }}",
            '--variable "$SOURCE_REVISION_VARIABLE"',
            '--probe-path "$SOURCE_REVISION_PROBE_PATH"',
            "--timeout-seconds 180",
            "--interval-seconds 5",
        ):
            self.assertIn(safe, self.workflow)
        for unsafe in (
            '--variable "${{ inputs.source-revision-variable }}"',
            '--probe-path "${{ inputs.source-revision-probe-path }}"',
        ):
            self.assertNotIn(unsafe, self.workflow)

    def test_workflow_uses_hash_locked_clients_and_immutable_tool_revision(self):
        self.assertIn("requirements/hf-publisher.lock", self.workflow)
        self.assertIn("--require-hashes", self.workflow)
        self.assertIn("--only-binary=:all:", self.workflow)
        self.assertIn("--ignore-installed", self.workflow)
        self.assertNotIn('"huggingface_hub==1.19.0"', self.workflow)
        self.assertNotIn('"requests==2.32.5"', self.workflow)
        self.assertNotIn("github.job_workflow_sha", self.workflow)
        self.assertIn("repository: ${{ job.workflow_repository }}", self.workflow)
        self.assertIn("ref: ${{ job.workflow_sha }}", self.workflow)
        self.assertIn("EXPECTED_TOOLS_SHA: ${{ job.workflow_sha }}", self.workflow)
        self.assertIn(
            'ACTUAL_TOOLS_SHA="$(git -C tools rev-parse --verify HEAD)"',
            self.workflow,
        )
        self.assertIn(
            '[[ ! "$EXPECTED_TOOLS_SHA" =~ ^[0-9a-f]{40}$ ]]',
            self.workflow,
        )
        self.assertIn(
            '[ "$ACTUAL_TOOLS_SHA" != "$EXPECTED_TOOLS_SHA" ]',
            self.workflow,
        )
        self.assertIn(
            '"$RUNNER_TEMP/hf-publisher-venv/bin/python" -I -P '
            "tools/.github/scripts/hf_space_source_binding.py",
            self.workflow,
        )
        self.assertNotIn(
            "python3 tools/.github/scripts/hf_space_source_binding.py",
            self.workflow,
        )

    def test_contract_only_witness_is_exact_read_only_and_non_secret(self):
        deploy_start = self.workflow.index("  hf-deploy:")
        contract_start = self.workflow.index("  exact-source-contract:")
        deploy = self.workflow[deploy_start:contract_start]
        contract = self.workflow[contract_start:]

        self.assertIn("if: ${{ inputs.contract-only == false }}", deploy)
        self.assertIn("if: ${{ inputs.contract-only == true }}", contract)
        self.assertIn("permissions:\n      contents: read", contract)
        self.assertEqual(contract.count("uses:"), 1)
        self.assertIn("repository: ${{ job.workflow_repository }}", contract)
        self.assertIn("ref: ${{ job.workflow_sha }}", contract)
        self.assertIn("EXPECTED_EVENT_SHA: ${{ github.sha }}", contract)
        self.assertIn(
            '[ "$EXPECTED_WORKFLOW_SHA" != "$EXPECTED_EVENT_SHA" ]',
            contract,
        )
        for forbidden in (
            "HF_TOKEN",
            "pip install",
            "hf_deploy_from_dockerfile.py",
            "hf_space_source_binding.py",
            "curl ",
            "gh api",
        ):
            self.assertNotIn(forbidden, contract)

    def test_tests_workflow_calls_actual_reusable_contract(self):
        self.assertNotIn("github.job_workflow_sha", self.witness_workflow)
        self.assertIn(
            "name: Reusable publisher exact-source witness",
            self.witness_workflow,
        )
        self.assertIn("  push:", self.witness_workflow)
        self.assertIn(
            "uses: ./.github/workflows/reusable-hf-deploy.yml",
            self.witness_workflow,
        )
        self.assertIn("contract-only: true", self.witness_workflow)
        self.assertIn("HF_TOKEN: ${{ github.token }}", self.witness_workflow)
        self.assertIn("permissions:\n  contents: read", self.witness_workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
