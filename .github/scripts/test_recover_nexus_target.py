#!/usr/bin/env python3
"""Network-free contracts for the exact Nexus target bootstrap."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("recover_nexus_target", HERE / "recover_nexus_target.py")
assert SPEC and SPEC.loader
recovery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recovery
SPEC.loader.exec_module(recovery)


def http_error(code: int) -> RuntimeError:
    error = RuntimeError("hf_secret_material must never enter evidence")
    error.response = types.SimpleNamespace(status_code=code)
    return error


def central_event() -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "szl-holdings/.github",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": recovery.WORKFLOW_REF,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
    }


class RecoveryContracts(unittest.TestCase):
    def test_disabled_grant_denies_dispatch_before_provider_access(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        grant_source = HERE.parent / "data" / "nexus-target-bootstrap-authorization.json"
        event = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_WORKFLOW_REF": recovery.WORKFLOW_REF,
            "GITHUB_WORKFLOW_SHA": "a" * 40,
            "HF_ORG_TOKEN_CANDIDATE": "hf_secret_material",
        }
        with tempfile.TemporaryDirectory() as temporary:
            grant = Path(temporary) / "disabled-grant.json"
            grant_data = json.loads(grant_source.read_text(encoding="utf-8"))
            grant_data["enabled"] = False
            grant.write_text(json.dumps(grant_data), encoding="utf-8")
            with self.assertRaises(recovery.RecoveryError):
                recovery.check_context(event, policy, grant)
            report = Path(temporary) / "receipt.json"
            with patch.dict(os.environ, event, clear=True):
                with patch.object(recovery, "recover") as provider:
                    for mode in (["--preflight"], []):
                        self.assertEqual(1, recovery.main([
                            "--policy", str(policy),
                            "--grant", str(grant),
                            "--report", str(report),
                            *mode,
                        ]))
                        provider.assert_not_called()
            receipt = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual("BLOCKED_BOUNDARY", receipt["state"])
            self.assertNotIn("hf_secret_material", json.dumps(receipt))

    def test_future_grant_must_be_exact_and_protected(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        grant = HERE.parent / "data" / "nexus-target-bootstrap-authorization.json"
        event = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_WORKFLOW_REF": recovery.WORKFLOW_REF,
            "GITHUB_WORKFLOW_SHA": "a" * 40,
        }
        with tempfile.TemporaryDirectory() as temporary:
            enabled_grant = Path(temporary) / "grant.json"
            grant_data = json.loads(grant.read_text(encoding="utf-8"))
            grant_data["enabled"] = True
            enabled_grant.write_text(json.dumps(grant_data), encoding="utf-8")
            recovery.check_context(event, policy, enabled_grant)
            preflight_receipt = Path(temporary) / "preflight.json"
            with patch.dict(os.environ, event, clear=True):
                with patch.object(recovery, "recover") as provider:
                    self.assertEqual(0, recovery.main([
                        "--policy", str(policy),
                        "--grant", str(enabled_grant),
                        "--report", str(preflight_receipt),
                        "--preflight",
                    ]))
                    provider.assert_not_called()
            self.assertEqual(
                "AUTHORIZED_TARGET_BOOTSTRAP_PENDING",
                json.loads(preflight_receipt.read_text(encoding="utf-8"))["state"],
            )
            with self.assertRaises(recovery.RecoveryError):
                recovery.check_context(
                    {**event, "GITHUB_REF": "refs/heads/unprotected"}, policy, enabled_grant
                )
            grant_data["target"] = "SZLHOLDINGS/other"
            enabled_grant.write_text(json.dumps(grant_data), encoding="utf-8")
            with self.assertRaises(recovery.RecoveryError):
                recovery.check_context(event, policy, enabled_grant)
            weakened_policy = Path(temporary) / "policy.json"
            policy_data = json.loads(policy.read_text(encoding="utf-8"))
            policy_data["boundaries"]["create"] = True
            weakened_policy.write_text(json.dumps(policy_data), encoding="utf-8")
            grant_data["target"] = "SZLHOLDINGS/nexus"
            enabled_grant.write_text(json.dumps(grant_data), encoding="utf-8")
            with self.assertRaises(recovery.RecoveryError):
                recovery.check_context(event, weakened_policy, enabled_grant)

    def test_absent_target_uses_only_atomic_public_docker_create(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.calls = []
                self.checks = 0

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                self.calls.append(("auth_check", kwargs))
                self.checks += 1
                if self.checks == 1:
                    raise http_error(404)

            def create_repo(self, **kwargs):
                self.calls.append(("create_repo", kwargs))

            def repo_info(self, **kwargs):
                self.calls.append(("repo_info", kwargs))
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=False, sdk="docker")

        holder = {}

        def factory(**kwargs):
            holder["api"] = Api(**kwargs)
            return holder["api"]

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=factory
        )
        self.assertEqual("CREATED_PUBLIC_WRITE_CONFIRMED", result["state"])
        self.assertEqual((
            "create_repo",
            {
                "repo_id": "SZLHOLDINGS/nexus",
                "repo_type": "space",
                "space_sdk": "docker",
                "private": False,
                "exist_ok": False,
            },
        ), holder["api"].calls[1])
        self.assertEqual(2, holder["api"].checks)
        self.assertNotIn("hf_secret_material", json.dumps(result))

    def test_occupied_private_target_conflicts_without_duplicate(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.create_args = None

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                raise http_error(404)

            def create_repo(self, **kwargs):
                self.create_args = kwargs
                raise http_error(409)

        holder = {}

        def factory(**kwargs):
            holder["api"] = Api(**kwargs)
            return holder["api"]

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=factory
        )
        self.assertEqual("BLOCKED_OCCUPIED_TARGET", result["state"])
        self.assertEqual(False, holder["api"].create_args["exist_ok"])
        self.assertEqual(409, result["attempts"][0]["status_code"])
        self.assertNotIn("hf_secret_material", json.dumps(result))

    def test_create_requires_verified_org_admin_role(self) -> None:
        class Api:
            def __init__(self, *, token):
                pass

            def whoami(self):
                return {"name": "writer", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "write"}]}

            def auth_check(self, **kwargs):
                raise http_error(404)

            def create_repo(self, **kwargs):
                raise AssertionError("create must not be reached")

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("BLOCKED_NO_TARGET_WRITER", result["state"])
        self.assertEqual("OrgAdminUnverified", result["attempts"][0]["error_type"])

    def test_post_create_mismatch_is_unknown_after_attempt(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.checks = 0

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                self.checks += 1
                if self.checks == 1:
                    raise http_error(404)

            def create_repo(self, **kwargs):
                pass

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True, sdk="docker")

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("UNKNOWN_AFTER_ATTEMPT", result["state"])
        self.assertEqual("post_create_readback", result["attempts"][0]["phase"])

    def test_existing_private_target_is_not_mutated(self) -> None:
        class Api:
            def __init__(self, *, token):
                pass

            def whoami(self):
                return {"name": "founder"}

            def auth_check(self, **kwargs):
                pass

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True, sdk="docker")

            def create_repo(self, **kwargs):
                raise AssertionError("existing target must not be recreated")

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("BLOCKED_EXISTING_TARGET_MISMATCH", result["state"])

    def test_grant_numbers_duplicates_and_shape_cannot_authorize(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        original = json.loads((HERE.parent / "data" / "nexus-target-bootstrap-authorization.json").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            grant = Path(temporary) / "synthetic-grant.json"
            for value in (False, 0, 1, 1.0, "true", None):
                with self.subTest(enabled=value):
                    grant.write_text(json.dumps({**original, "enabled": value}))
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.check_context(central_event(), policy, grant)
            raw = json.dumps({**original, "enabled": True})
            for malformed in (
                raw.replace('"enabled": true', '"enabled": false, "enabled": true'),
                raw.replace('"enabled": true', '"enabled": true, "extra": true'),
                json.dumps({key: value for key, value in original.items() if key != "enabled"}),
                '[]',
            ):
                with self.subTest(raw=malformed):
                    grant.write_text(malformed)
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.check_context(central_event(), policy, grant)

    def test_policy_nonfinite_overflow_duplicate_and_nonregular_are_rejected(self) -> None:
        source = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        original = json.loads(source.read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "policy.json"
            for value in ('NaN', 'Infinity', '-Infinity', '1e999', '-1e999'):
                with self.subTest(value=value):
                    policy.write_text(json.dumps(original)[:-1] + ', "extra": {"nested": ' + value + '}}')
                    with self.assertRaises(recovery.RecoveryError):
                        recovery._load_json(policy)
            policy.write_text('{"targets":[],"targets":[]}')
            with self.assertRaises(recovery.RecoveryError):
                recovery._load_json(policy)
            policy.write_bytes(b' ' * (recovery.MAX_POLICY_BYTES + 1))
            with self.assertRaises(recovery.RecoveryError):
                recovery._load_json(policy)
            with self.assertRaises(recovery.RecoveryError):
                recovery._load_json(Path(temporary))
            policy.unlink()
            policy.symlink_to(source)
            with self.assertRaises(recovery.RecoveryError):
                recovery._load_json(policy)

    def test_native_dispatch_context_is_required_before_provider_access(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        original = json.loads((HERE.parent / "data" / "nexus-target-bootstrap-authorization.json").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            grant = Path(temporary) / "synthetic-grant.json"
            grant.write_text(json.dumps({**original, "enabled": True}))
            for key, value in (
                ("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "OTHER/.github"),
                ("GITHUB_EVENT_NAME", "push"), ("GITHUB_REF", "refs/heads/feature"),
                ("GITHUB_REF_PROTECTED", "false"), ("GITHUB_WORKFLOW_REF", "OTHER/.github/workflow@main"),
                ("GITHUB_SHA", "main"), ("GITHUB_WORKFLOW_SHA", "b" * 40),
            ):
                with self.subTest(key=key):
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.check_context({**central_event(), key: value}, policy, grant)
                    event = central_event()
                    del event[key]
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.check_context(event, policy, grant)

    def test_client_lock_byte_drift_blocks_before_provider_access(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        original = json.loads((HERE.parent / "data" / "nexus-target-bootstrap-authorization.json").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            grant = Path(temporary) / "synthetic-grant.json"
            grant.write_text(json.dumps({**original, "enabled": True}))
            lock = Path(temporary) / "hf-publisher.lock"
            lock.write_bytes(recovery.LOCK_PATH.read_bytes())
            with patch.object(recovery, "LOCK_PATH", lock):
                recovery.check_context(central_event(), policy, grant)
                lock.write_bytes(lock.read_bytes() + b'\n')
                with self.assertRaises(recovery.RecoveryError):
                    recovery.check_context(central_event(), policy, grant)

    def test_first_create_invocation_is_terminal_across_all_credentials(self) -> None:
        for status in (401, 403, 409, 500, None):
            for identical in (False, True):
                with self.subTest(status=status, identical=identical):
                    calls = []

                    class Api:
                        def __init__(self, *, token):
                            calls.append(("api", token))

                        def whoami(self):
                            return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

                        def auth_check(self, **kwargs):
                            raise http_error(404)

                        def create_repo(self, **kwargs):
                            calls.append(("create", kwargs))
                            raise http_error(status)

                    event = {variable: "hf_fixture" + ("0" if identical else str(index))
                             for index, (_source, variable) in enumerate(recovery.TOKEN_SOURCES)}
                    result = recovery.recover(event, api_factory=Api)
                    self.assertEqual(1, sum(kind == "create" for kind, _ in calls))
                    self.assertEqual(1, sum(kind == "api" for kind, _ in calls))
                    expected = "BLOCKED_CREATE_REJECTED" if status in (401, 403) else (
                        "BLOCKED_OCCUPIED_TARGET" if status == 409 else "UNKNOWN_AFTER_ATTEMPT")
                    self.assertEqual(expected, result["state"])
                    self.assertNotIn("hf_fixture", json.dumps(result))

    def test_duplicate_credentials_are_not_retried_for_identity(self) -> None:
        calls = []

        class Api:
            def __init__(self, *, token):
                calls.append(token)

            def whoami(self):
                raise http_error(401)

        result = recovery.recover(
            {variable: "hf_same_fixture" for _source, variable in recovery.TOKEN_SOURCES}, api_factory=Api)
        self.assertEqual(1, len(calls))
        self.assertEqual("BLOCKED_NO_TARGET_WRITER", result["state"])

    def test_existing_and_created_target_readback_requires_exact_public_docker(self) -> None:
        for created in (False, True):
            for change in ({"sdk": "gradio"}, {"sdk": None}, {"id": "SZLHOLDINGS/other"},
                           {"private": True}, {"private": 0}, {}):
                with self.subTest(created=created, change=change):
                    calls = []

                    class Api:
                        def __init__(self, *, token):
                            self.checks = 0
                            calls.append("api")

                        def whoami(self):
                            return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

                        def auth_check(self, **kwargs):
                            self.checks += 1
                            if created and self.checks == 1:
                                raise http_error(404)

                        def create_repo(self, **kwargs):
                            calls.append("create")

                        def repo_info(self, **kwargs):
                            values = {"id": "SZLHOLDINGS/nexus", "private": False, "sdk": "docker", **change}
                            if values["sdk"] is None:
                                del values["sdk"]
                            return types.SimpleNamespace(**values)

                    result = recovery.recover(
                        {variable: "hf_fixture" + str(index)
                         for index, (_source, variable) in enumerate(recovery.TOKEN_SOURCES)}, api_factory=Api)
                    self.assertEqual(1, calls.count("api"))
                    self.assertEqual(int(created), calls.count("create"))
                    if change:
                        expected = "UNKNOWN_AFTER_ATTEMPT" if created else "BLOCKED_EXISTING_TARGET_MISMATCH"
                    else:
                        expected = "CREATED_PUBLIC_WRITE_CONFIRMED" if created else "EXISTING_PUBLIC_WRITE_CONFIRMED"
                    self.assertEqual(expected, result["state"])

    def test_status_metadata_cannot_record_arbitrary_provider_content(self) -> None:
        for value in ("hf_secret_material", True, 999, None):
            with self.subTest(value=value):
                result = recovery._attempt("fixture", "context", http_error(value))
                self.assertIsNone(result["status_code"])
                self.assertNotIn("hf_secret_material", json.dumps(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
