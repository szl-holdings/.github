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
        self.response = response
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "/api/build-info"
        )

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
        payload = {
            "status": "OBSERVED",
            "build": {"state": "OBSERVED", "revision": self.sha},
            "runtime": {"python": "3.12"},
            "receipt_minted": False,
        }
        session = FakeSession(FakeResponse(payload))
        report = binding.verify_runtime_probe(self.normalized, session=session)
        self.assertTrue(report["matched"])
        self.assertEqual(
            session.calls[0][0],
            "https://szlholdings-a11oy.hf.space/api/build-info",
        )
        self.assertFalse(session.calls[0][1]["allow_redirects"])

        payload["build"]["revision"] = "b" * 40
        with self.assertRaisesRegex(binding.SourceBindingError, "runtime source binding mismatch"):
            binding.verify_runtime_probe(
                self.normalized, session=FakeSession(FakeResponse(payload))
            )

    def test_runtime_probe_rejects_non_json_and_non_200(self):
        with self.assertRaises(binding.SourceBindingError):
            binding.verify_runtime_probe(
                self.normalized,
                session=FakeSession(FakeResponse({}, status=503)),
            )
        response = FakeResponse({}, status=200, content_type="text/html")
        response.json = mock.Mock(side_effect=ValueError("not json"))
        with self.assertRaises(binding.SourceBindingError):
            binding.verify_runtime_probe(self.normalized, session=FakeSession(response))

    def test_source_contains_no_secret_or_hardware_mutation(self):
        with open(MODULE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in (
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
            ]
            secret = "super-secret-token"
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                os.environ, {"HF_TOKEN": secret}, clear=False
            ), mock.patch.object(
                binding,
                "run",
                side_effect=binding.SourceBindingError("fail closed"),
            ):
                self.assertEqual(binding.main(), 1)
            with open(output, encoding="utf-8") as fh:
                report = json.load(fh)
        self.assertFalse(report["ok"])
        self.assertNotIn(secret, json.dumps(report, sort_keys=True))


class ReusableWorkflowSourceBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(HERE, "..", "workflows", "reusable-hf-deploy.yml")
        with open(path, encoding="utf-8") as fh:
            cls.workflow = fh.read()

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
        ):
            self.assertIn(safe, self.workflow)
        for unsafe in (
            '--variable "${{ inputs.source-revision-variable }}"',
            '--probe-path "${{ inputs.source-revision-probe-path }}"',
        ):
            self.assertNotIn(unsafe, self.workflow)

    def test_workflow_uses_exact_supported_clients_and_immutable_tool_revision(self):
        self.assertIn('"huggingface_hub==1.19.0"', self.workflow)
        self.assertIn('"requests==2.32.5"', self.workflow)
        self.assertIn("ref: ${{ github.job_workflow_sha }}", self.workflow)
        self.assertNotIn("repository: szl-holdings/.github\n          ref: main", self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
