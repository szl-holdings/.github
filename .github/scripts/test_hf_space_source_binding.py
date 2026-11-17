#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
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
try:
    import requests as requests_real
    REAL_REQUESTS = True
except ImportError:
    REAL_REQUESTS = False
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    requests_stub.Request = lambda method, url: SimpleNamespace(
        prepare=lambda: SimpleNamespace(url=url))
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
    def __init__(self, payload, status=200, content_type="application/json", raw=None):
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.content = json.dumps(payload).encode("utf-8") if raw is None else raw
        self.url = None
        self.closed = False
        self.read_bytes = 0
        response = self
        class Body(io.BytesIO):
            def read(self, size=-1):
                value = super().read(size)
                response.read_bytes += len(value)
                return value
        self.raw = Body(self.content)

    def json(self):
        return self._payload

    def close(self):
        self.closed = True
        self.raw.close()


class FakeSession(binding._ReadSession):
    def __init__(self, response):
        self.responses = list(response) if isinstance(response, list) else [response]
        self.headers = {}
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.get("headers", {}))
        request = SimpleNamespace(method="GET", url=url, headers=headers)
        if kwargs.get("auth") is not None:
            kwargs["auth"](request)
        kwargs["headers"] = dict(request.headers)
        self.calls.append((url, kwargs))
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if response.url is None:
            response.url = url
        return response

    def close(self):
        self.closed = True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"HF_TOKEN": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sha = "a" * 40
        self.normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "/api/build-info"
        )

    @staticmethod
    def observed_payload(
        revision: str,
        *,
        receipt_minted: bool = False,
        release_receipt: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "OBSERVED",
            "build": {"state": "OBSERVED", "revision": revision},
            "runtime": {"python": "3.12"},
            "receipt_minted": receipt_minted,
        }
        if release_receipt is not None:
            payload["release_receipt"] = release_receipt
        return payload

    def valid_receipt(self, revision: str | None = None) -> dict[str, object]:
        source_revision = revision or self.sha
        attestation_id = "123456789"
        return {
            "state": "GITHUB_OIDC_ATTESTED",
            "source_revision": source_revision,
            "subject": "hf-deploy-manifest.json",
            "subject_sha256": "c" * 64,
            "attestation_id": attestation_id,
            "attestation_url": (
                "https://github.com/szl-holdings/killinchu/attestations/"
                + attestation_id
            ),
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

    def test_runtime_probe_accepts_valid_existing_oidc_receipt(self):
        payload = self.observed_payload(
            self.sha,
            receipt_minted=True,
            release_receipt=self.valid_receipt(),
        )
        report = binding.verify_runtime_probe(
            self.normalized,
            session=FakeSession(FakeResponse(payload)),
        )
        observation = report["observations"][0]
        self.assertTrue(report["matched"])
        self.assertTrue(observation["receipt_minted"])
        self.assertTrue(observation["receipt_valid"])
        self.assertEqual(observation["receipt_state"], "GITHUB_OIDC_ATTESTED")

    def test_runtime_probe_rejects_unbound_or_malformed_existing_receipt(self):
        invalid_receipts = [
            None,
            self.valid_receipt("b" * 40),
            {**self.valid_receipt(), "subject_sha256": "short"},
            {**self.valid_receipt(), "attestation_id": "not-numeric"},
            {
                **self.valid_receipt(),
                "attestation_url": "https://evil.example/attestations/123456789",
            },
        ]
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt):
                payload = self.observed_payload(
                    self.sha,
                    receipt_minted=True,
                    release_receipt=receipt,
                )
                with self.assertRaisesRegex(
                    binding.SourceBindingError, "did not converge"
                ):
                    binding.verify_runtime_probe(
                        self.normalized,
                        session=FakeSession(FakeResponse(payload)),
                        timeout_seconds=0,
                    )

    def test_runtime_probe_rejects_missing_or_non_boolean_receipt_flag(self):
        for value in (None, "false", 0, 1):
            with self.subTest(value=value):
                payload = self.observed_payload(self.sha)
                payload["receipt_minted"] = value
                with self.assertRaises(binding.SourceBindingError):
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
        response = FakeResponse({}, status=200, content_type="text/html", raw=b"not json")
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



class SourceReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.sha = "b" * 40
        self.normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy", "SZL_GIT_SHA", self.sha, "/api/build-info"
        )
        self.payload = SourceBindingTests.observed_payload(self.sha)
        self.clock = FakeClock()
        patcher = mock.patch.dict(os.environ, {"HF_TOKEN": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def verify(self, session, timeout=0):
        return binding.verify_runtime_probe(
            self.normalized, session=session, timeout_seconds=timeout,
            interval_seconds=1, monotonic=self.clock.monotonic, sleep=self.clock.sleep,
        )

    def rejected(self, session, code):
        with self.assertRaises(binding.SourceBindingError) as raised:
            self.verify(session)
        observation = raised.exception.evidence["observations"][-1]
        self.assertFalse(observation["matched"])
        self.assertEqual(observation["error_code"], code)
        return observation

    def test_anonymous_identity_has_no_ambient_credentials_or_public_claim(self):
        response = FakeResponse(self.payload)
        session = FakeSession(response)
        session.headers.update({"Authorization": "ambient", "Cookie": "ambient",
                                "Proxy-Authorization": "ambient", "Host": "other.invalid"})
        result = self.verify(session)
        self.assertTrue(result["matched"])
        self.assertEqual(result["availability_scope"], "not_evaluated")
        self.assertEqual(result["observations"][0]["authentication"], "anonymous")
        headers = session.calls[0][1]["headers"]
        for name in ("Authorization", "Cookie", "Proxy-Authorization", "Host"):
            self.assertNotIn(name, headers)
        self.assertTrue(session.calls[0][1]["stream"])
        self.assertFalse(session.calls[0][1]["allow_redirects"])
        self.assertTrue(response.closed)

    def test_authenticated_identity_is_scoped_and_never_claims_public_availability(self):
        for status in (401, 404):
            with self.subTest(status=status):
                session = FakeSession([FakeResponse({}, status=status),
                                       FakeResponse({"token": "synthetic-space-jwt"}),
                                       FakeResponse(self.payload)])
                with mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}):
                    report = self.verify(session)
                self.assertTrue(report["matched"])
                observation = report["observations"][0]
                self.assertEqual(observation["authentication"], "space_read_jwt")
                self.assertEqual(observation["availability_scope"], "not_evaluated")
                self.assertEqual(observation["anonymous_http_status"], status)
                self.assertNotIn("private", observation)
                self.assertEqual(len(session.calls), 3)
                first, jwt, last = session.calls
                self.assertEqual(first[0], last[0])
                self.assertEqual(jwt[0], "https://huggingface.co/api/spaces/SZLHOLDINGS/a11oy/jwt")
                self.assertNotIn("Authorization", first[1]["headers"])
                self.assertEqual(jwt[1]["headers"]["Authorization"], "Bearer synthetic-hub-token")
                self.assertEqual(last[1]["headers"]["Authorization"], "Bearer synthetic-space-jwt")
                self.assertEqual(first[1]["headers"][binding.PROBE_ATTEMPT_HEADER],
                                 last[1]["headers"][binding.PROBE_ATTEMPT_HEADER])
                self.assertNotIn("synthetic-space-jwt", json.dumps(report))
                self.assertNotIn("synthetic-hub-token", json.dumps(report))

    def test_credentials_reject_other_origins_paths_and_methods(self):
        hub = "https://huggingface.co/api/spaces/SZLHOLDINGS/a11oy/jwt"
        runtime = binding.live_origin(self.normalized["repo_id"]) + "/api/build-info"
        for destination in ("https://other.hf.space/api/build-info", "http://huggingface.co/api",
                            "https://huggingface.co.evil.invalid/api", "https://u@huggingface.co/api",
                            "https://huggingface.co:444/api", "https://huggingface.co/api/spaces/x/y/jwt"):
            with self.subTest(destination=destination), self.assertRaises(binding.SourceBindingError):
                auth = binding._ScopedReadAuth(hub, "synthetic-hub-token", hub_jwt=True)
                auth(SimpleNamespace(method="GET", url=destination, headers={}))
        with self.assertRaises(binding.SourceBindingError):
            binding._ScopedReadAuth("https://huggingface.co/other", "token", hub_jwt=True)
        with self.assertRaises(binding.SourceBindingError):
            binding._ScopedReadAuth("https://other.invalid/path", "token")
        with self.assertRaises(binding.SourceBindingError):
            binding._ScopedReadAuth(runtime, "token")(SimpleNamespace(method="POST", url=runtime, headers={}))

    def test_runtime_credential_rejects_same_origin_wrong_path_or_query(self):
        selected = binding.live_origin(self.normalized["repo_id"]) + "/api/build-info?view=release"
        auth = binding._ScopedReadAuth(selected, "synthetic-space-jwt")
        for target in (selected.replace("/api/build-info", "/other"),
                       selected.replace("view=release", "view=other"),
                       selected + "&extra=1", selected.split("?")[0]):
            with self.subTest(target=target), self.assertRaises(binding.SourceBindingError):
                auth(SimpleNamespace(method="GET", url=target, headers={}))
        request = auth(SimpleNamespace(method="GET", url=selected, headers={}))
        self.assertEqual(request.headers["Authorization"], "Bearer synthetic-space-jwt")
        response = FakeResponse(self.payload)
        response.url = binding.live_origin(self.normalized["repo_id"]) + "/other"
        self.rejected(FakeSession(response), "RESPONSE_TARGET")

    def test_failure_evidence_retains_existing_timing_schema(self):
        with self.assertRaises(binding.SourceBindingError) as raised:
            self.verify(FakeSession(FakeResponse({}, status=503)))
        evidence = raised.exception.evidence
        self.assertEqual(evidence["elapsed_seconds"], 0.0)
        self.assertEqual(evidence["interval_seconds"], 1)
        self.assertEqual(evidence["timeout_seconds"], 0)
        self.assertNotIn("converged_after_seconds", evidence)

    def test_runtime_bodies_are_bounded_before_json_admission(self):
        payload = dict(self.payload, padding="x" * binding.RUNTIME_JSON_MAX_BYTES)
        response = FakeResponse(payload)
        self.rejected(FakeSession(response), "BODY_LIMIT")
        self.assertEqual(response.read_bytes, binding.RUNTIME_JSON_MAX_BYTES + 1)
        self.assertTrue(response.closed)

    def test_declared_length_encoding_and_truncation_fail_closed(self):
        for headers, code in (
            ({"Content-Length": str(binding.RUNTIME_JSON_MAX_BYTES + 1)}, "BODY_LIMIT"),
            ({"Content-Length": "2, 2"}, "CONTENT_LENGTH"),
            ({"Content-Length": "-1"}, "CONTENT_LENGTH"),
            ({"Content-Length": "2", "content-length": "2"}, "CONTENT_LENGTH"),
            ({"Content-Length": "3"}, "BODY_LENGTH_MISMATCH"),
            ({"Content-Encoding": "gzip"}, "CONTENT_ENCODING"),
        ):
            with self.subTest(headers=headers):
                response = FakeResponse({})
                response.headers.update(headers)
                self.rejected(FakeSession(response), code)
                self.assertTrue(response.closed)
                if code != "BODY_LENGTH_MISMATCH":
                    self.assertEqual(response.read_bytes, 0)

    def test_error_bodies_and_redirects_are_bounded(self):
        for status in (302, 401, 404, 503):
            with self.subTest(status=status):
                response = FakeResponse({}, status=status,
                                        raw=b"x" * (binding.ERROR_BODY_MAX_BYTES + 50))
                self.rejected(FakeSession(response), "BODY_LIMIT")
                self.assertLessEqual(response.read_bytes, binding.ERROR_BODY_MAX_BYTES + 1)
                self.assertTrue(response.closed)
        response = FakeResponse({}, status=302)
        with self.assertRaises(binding.SourceBindingError) as raised:
            self.verify(FakeSession(response))
        self.assertEqual(raised.exception.evidence["observations"][0]["http_status"], 302)

    def test_jwt_body_type_size_and_bearer_validation(self):
        cases = [
            ({"token": "x" * binding.JWT_JSON_MAX_BYTES}, "BODY_LIMIT"),
            ({"token": ["not", "a", "token"]}, "INVALID_BEARER"),
            ({"token": ""}, "INVALID_BEARER"),
            ({"token": "bad\r\nheader"}, "INVALID_BEARER"),
            ({"token": "x" * (binding.TOKEN_MAX_CHARS + 1)}, "INVALID_BEARER"),
        ]
        for payload, code in cases:
            with self.subTest(code=code):
                jwt_response = FakeResponse(payload)
                session = FakeSession([FakeResponse({}, status=401), jwt_response])
                with mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}):
                    self.rejected(session, code)
                self.assertEqual(len(session.calls), 2)
                self.assertTrue(jwt_response.closed)

    def test_json_transport_and_response_origin_errors_are_sanitized(self):
        self.rejected(FakeSession(FakeResponse({}, raw=b"not-json")), "INVALID_JSON")
        response = FakeResponse(self.payload)
        response.url = "https://other.hf.space/api/build-info"
        self.rejected(FakeSession(response), "RESPONSE_ORIGIN")
        class FailedSession(binding._ReadSession):
            def get(self, *args, **kwargs):
                raise RuntimeError("synthetic-sensitive-body-or-token")
        observation = self.rejected(FailedSession(), "TRANSPORT_UNAVAILABLE")
        self.assertNotIn("synthetic-sensitive", json.dumps(observation))

    def test_exact_response_after_deadline_is_not_admitted(self):
        clock = self.clock
        class LateSession(FakeSession):
            def get(self, *args, **kwargs):
                response = super().get(*args, **kwargs)
                clock.now = 2.0
                return response
        session = LateSession(FakeResponse(self.payload))
        self.rejected(session, "DEADLINE_EXCEEDED")
        self.assertEqual(len(session.calls), 1)

    def test_jwt_and_authenticated_retry_share_remaining_budget(self):
        clock = self.clock
        class TimedSession(FakeSession):
            def get(self, *args, **kwargs):
                response = super().get(*args, **kwargs)
                clock.now += 0.3
                return response
        session = TimedSession([FakeResponse({}, status=401),
                                FakeResponse({"token": "synthetic-space-jwt"}),
                                FakeResponse(self.payload)])
        with mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}):
            self.assertTrue(self.verify(session)["matched"])
        self.assertAlmostEqual(session.calls[0][1]["timeout"], 1.0)
        self.assertAlmostEqual(session.calls[1][1]["timeout"], 0.7)
        self.assertAlmostEqual(session.calls[2][1]["timeout"], 0.4)

    def test_expired_jwt_request_cannot_start_authenticated_retry(self):
        clock = self.clock
        class ExpiredJwtSession(FakeSession):
            def get(self, *args, **kwargs):
                response = super().get(*args, **kwargs)
                if len(self.calls) == 2:
                    clock.now = 2.0
                return response
        session = ExpiredJwtSession([FakeResponse({}, status=401),
                                     FakeResponse({"token": "synthetic-space-jwt"})])
        with mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}):
            self.rejected(session, "DEADLINE_EXCEEDED")
        self.assertEqual(len(session.calls), 2)

    def test_capability_cache_does_not_cross_verification_calls(self):
        with mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}):
            for token in ("synthetic-first-jwt", "synthetic-second-jwt"):
                session = FakeSession([FakeResponse({}, status=401), FakeResponse({"token": token}),
                                       FakeResponse(self.payload)])
                self.assertTrue(self.verify(session)["matched"])
                self.assertEqual(len(session.calls), 3)
                self.assertEqual(session.calls[-1][1]["headers"]["Authorization"], "Bearer " + token)

    def test_verify_does_not_write_hub_variables(self):
        with mock.patch.object(binding, "HfApi", side_effect=AssertionError("no SDK mutation")):
            self.assertTrue(self.verify(FakeSession(FakeResponse(self.payload)))["matched"])

    def test_owned_session_is_closed_and_environment_trust_is_not_disabled(self):
        session = FakeSession(FakeResponse(self.payload))
        session.trust_env = True
        session.proxies = {"https": "configured-proxy"}
        session.verify = "configured-ca.pem"
        with mock.patch.object(binding, "_ReadSession", return_value=session):
            binding.verify_runtime_probe(self.normalized, timeout_seconds=0,
                                         monotonic=self.clock.monotonic, sleep=self.clock.sleep)
        self.assertTrue(session.closed)
        self.assertTrue(session.trust_env)
        self.assertEqual(session.proxies, {"https": "configured-proxy"})
        self.assertEqual(session.verify, "configured-ca.pem")
        self.assertNotIn("proxies", session.calls[0][1])
        self.assertNotIn("verify", session.calls[0][1])


@unittest.skipUnless(REAL_REQUESTS, "real Requests is required; publisher-lock CI supplies it")
class RealRequestsSourceReadTests(unittest.TestCase):
    def setUp(self):
        self.normalized = binding.normalize_binding(
            "SZLHOLDINGS/a11oy", "SZL_GIT_SHA", "c" * 40, "/api/build-info"
        )
        self.payload = SourceBindingTests.observed_payload("c" * 40)

    def session(self, responses):
        calls = []
        class Adapter(requests_real.adapters.BaseAdapter):
            def send(self, request, **kwargs):
                calls.append((request, kwargs))
                status, body, headers = responses.pop(0)
                response = requests_real.Response()
                response.status_code = status
                response.url = request.url
                response.request = request
                response.headers.update(headers)
                response.raw = io.BytesIO(body)
                return response
            def close(self): pass
        session = binding._ReadSession()
        session.mount("https://", Adapter())
        return session, calls

    def test_configured_proxy_ca_survive_while_netrc_cookies_and_origin_auth_do_not(self):
        session, calls = self.session([(200, json.dumps(self.payload).encode(), {})])
        session.auth = ("ambient-user", "ambient-password")
        session.headers.update({"Authorization": "Bearer ambient",
                                "Cookie": "ambient=secret", "Proxy-Authorization": "ambient",
                                "Host": "wrong.invalid"})
        session.cookies.set("ambient", "cookie")
        environment = {
            "HTTPS_PROXY": "http://configured-proxy.invalid:3128",
            "NO_PROXY": "unrelated.invalid",
            "REQUESTS_CA_BUNDLE": "synthetic-configured-ca.pem",
        }
        with session, mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            requests_real.sessions, "get_netrc_auth", side_effect=AssertionError("netrc must not be read")
        ):
            report = binding.verify_runtime_probe(self.normalized, session=session, timeout_seconds=5)
        self.assertTrue(report["matched"])
        request, options = calls[0]
        self.assertEqual(options["proxies"]["https"], environment["HTTPS_PROXY"])
        self.assertEqual(options["verify"], environment["REQUESTS_CA_BUNDLE"])
        for header in ("Authorization", "Cookie", "Proxy-Authorization", "Host"):
            self.assertNotIn(header, request.headers)
        self.assertTrue(options["stream"])

    def test_redirect_preparation_neither_reads_netrc_nor_follows_target(self):
        body = b"x" * (binding.ERROR_BODY_MAX_BYTES + 1)
        session, calls = self.session([(302, body, {"Location": "https://other.hf.space/private"})])
        with session, mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            requests_real.sessions, "get_netrc_auth", side_effect=AssertionError("netrc must not be read")
        ), self.assertRaises(binding.SourceBindingError) as raised:
            binding.verify_runtime_probe(self.normalized, session=session, timeout_seconds=0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(raised.exception.evidence["observations"][0]["error_code"], "BODY_LIMIT")

    def test_runtime_credential_preserves_valid_url_preparation_and_exact_target(self):
        selected = binding.live_origin(self.normalized["repo_id"]) + "/api/%62uild-info?view=%7E"
        auth = binding._ScopedReadAuth(selected, "synthetic-space-jwt")
        prepared = requests_real.Request("GET", selected).prepare()
        self.assertEqual(prepared.url,
                         binding.live_origin(self.normalized["repo_id"]) + "/api/build-info?view=~")
        self.assertEqual(auth(prepared).headers["Authorization"], "Bearer synthetic-space-jwt")
        for target in (prepared.url.replace("/api/build-info", "/other"),
                       prepared.url.replace("view=~", "view=other"),
                       prepared.url + "&extra=1"):
            with self.subTest(target=target), self.assertRaises(binding.SourceBindingError):
                auth(requests_real.Request("GET", target).prepare())

    def test_plain_session_cannot_reintroduce_redirect_prefetch(self):
        with requests_real.Session() as session, mock.patch.object(
            session, "get", side_effect=AssertionError("unsafe session must not run")
        ):
            with self.assertRaisesRegex(binding.SourceBindingError, "redirect-blocking"):
                binding.verify_runtime_probe(self.normalized, session=session, timeout_seconds=0)

    def test_real_prepared_requests_keep_hub_and_space_credentials_separate(self):
        session, calls = self.session([
            (401, b"{}", {}),
            (200, b'{"token":"synthetic-runtime-jwt"}', {}),
            (200, json.dumps(self.payload).encode(), {}),
        ])
        with session, mock.patch.dict(os.environ, {"HF_TOKEN": "synthetic-hub-token"}, clear=True):
            report = binding.verify_runtime_probe(self.normalized, session=session, timeout_seconds=5)
        self.assertTrue(report["matched"])
        self.assertNotIn("Authorization", calls[0][0].headers)
        self.assertEqual(calls[1][0].headers["Authorization"], "Bearer synthetic-hub-token")
        self.assertEqual(calls[2][0].headers["Authorization"], "Bearer synthetic-runtime-jwt")
        self.assertEqual(report["observations"][0]["authentication"], "space_read_jwt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
