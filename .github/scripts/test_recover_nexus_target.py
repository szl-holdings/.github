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


class RecoveryContracts(unittest.TestCase):
    def test_disabled_grant_denies_dispatch_before_provider_access(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        grant = HERE.parent / "data" / "nexus-target-bootstrap-authorization.json"
        event = {
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "HF_ORG_TOKEN_CANDIDATE": "hf_secret_material",
        }
        with self.assertRaises(recovery.RecoveryError):
            recovery.check_context(event, policy, grant)
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "receipt.json"
            with patch.dict(os.environ, event, clear=True):
                with patch.object(recovery, "recover") as provider:
                    self.assertEqual(1, recovery.main([
                        "--policy", str(policy),
                        "--grant", str(grant),
                        "--report", str(report),
                        "--preflight",
                    ]))
                    provider.assert_not_called()
            receipt = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual("BLOCKED_BOUNDARY", receipt["state"])
            self.assertNotIn("hf_secret_material", json.dumps(receipt))

    def test_future_grant_must_be_exact_and_protected(self) -> None:
        policy = HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        grant = HERE.parent / "data" / "nexus-target-bootstrap-authorization.json"
        event = {
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
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
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=False)

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
        self.assertEqual("BLOCKED_NO_TARGET_WRITER", result["state"])
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
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True)

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
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True)

            def create_repo(self, **kwargs):
                raise AssertionError("existing target must not be recreated")

        result = recovery.recover(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("BLOCKED_EXISTING_TARGET_MISMATCH", result["state"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
