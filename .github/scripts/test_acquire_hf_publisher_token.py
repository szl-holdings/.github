#!/usr/bin/env python3
"""Network-free contracts for independent Hugging Face token selection."""
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


_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "acquire_hf_publisher_token",
    _HERE / "acquire_hf_publisher_token.py",
)
assert _SPEC and _SPEC.loader
auth = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = auth
_SPEC.loader.exec_module(auth)


class PublisherCredentialSelectionTests(unittest.TestCase):
    @staticmethod
    def _result(source: str, access: str = "EXISTING_WRITE_CONFIRMED"):
        return auth.ValidationResult(
            source=source,
            identity_sha256="a" * 64,
            target_access=access,
        )

    def test_invalid_first_secret_cannot_mask_later_valid_secret(self) -> None:
        attempted: list[str] = []

        def validator(token: str, **kwargs):
            source = kwargs["source"]
            attempted.append(source)
            if source == "HF_ORG_TOKEN":
                raise RuntimeError("simulated inaccessible target")
            return self._result(source)

        token, selected, attempts = auth.select_credential(
            resource=None,
            target_repo="SZLHOLDINGS/nexus",
            target_type="space",
            allow_create=False,
            environment={
                "HF_ORG_TOKEN_CANDIDATE": "hf_invalid_first",
                "HF_ORG_TOKEN1_CANDIDATE": "hf_valid_second",
            },
            validator=validator,
        )

        self.assertEqual("hf_valid_second", token)
        self.assertEqual("HF_ORG_TOKEN1", selected.source)
        self.assertEqual(["HF_ORG_TOKEN", "HF_ORG_TOKEN1"], attempted)
        self.assertFalse(attempts[0].valid)
        self.assertTrue(attempts[1].valid)

    def test_target_creation_is_not_authorized_for_nexus(self) -> None:
        seen: list[bool] = []

        def validator(_token: str, **kwargs):
            seen.append(kwargs["allow_create"])
            raise RuntimeError("target unavailable")

        with self.assertRaises(auth.CredentialSelectionError):
            auth.select_credential(
                resource=None,
                target_repo="SZLHOLDINGS/nexus",
                target_type="space",
                allow_create=False,
                environment={"HF_TOKEN_CANDIDATE": "hf_candidate"},
                validator=validator,
            )

        self.assertEqual([False], seen)

    def test_explicit_recovery_creates_only_exact_public_docker_space(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.calls = []
                self.checks = 0

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                self.checks += 1
                self.calls.append(("auth_check", kwargs))
                if self.checks == 1:
                    raise self._error(404)

            def create_repo(self, **kwargs):
                self.calls.append(("create_repo", kwargs))

            def repo_info(self, **kwargs):
                self.calls.append(("repo_info", kwargs))
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=False)

            @staticmethod
            def _error(code):
                error = RuntimeError("secret must not enter evidence")
                error.response = types.SimpleNamespace(status_code=code)
                return error

        holder = {}

        def factory(**kwargs):
            holder["api"] = Api(**kwargs)
            return holder["api"]

        result = auth.recover_public_nexus(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=factory
        )
        self.assertEqual("CREATED_PUBLIC_WRITE_CONFIRMED", result["state"])
        self.assertEqual(
            (
                "create_repo",
                {
                    "repo_id": "SZLHOLDINGS/nexus",
                    "repo_type": "space",
                    "space_sdk": "docker",
                    "private": False,
                    "exist_ok": False,
                },
            ),
            holder["api"].calls[1],
        )
        self.assertEqual(2, holder["api"].checks)
        self.assertNotIn("hf_secret_material", json.dumps(result))

    def test_inaccessible_existing_target_cannot_be_recreated_or_unprivated(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.creates = 0

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                error = RuntimeError("inaccessible")
                error.response = types.SimpleNamespace(status_code=404)
                raise error

            def create_repo(self, **kwargs):
                self.creates += 1
                self.args = kwargs
                error = RuntimeError("already occupied")
                error.response = types.SimpleNamespace(status_code=409)
                raise error

        holder = {}

        def factory(**kwargs):
            holder["api"] = Api(**kwargs)
            return holder["api"]

        result = auth.recover_public_nexus(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=factory
        )
        self.assertEqual("BLOCKED_NO_TARGET_WRITER", result["state"])
        self.assertEqual(1, holder["api"].creates)
        self.assertEqual(False, holder["api"].args["exist_ok"])
        self.assertEqual(409, result["attempts"][0]["status_code"])
        self.assertNotIn("hf_secret_material", json.dumps(result))

    def test_recovery_requires_verified_org_admin(self) -> None:
        class Api:
            def __init__(self, *, token):
                pass

            def whoami(self):
                return {"name": "writer", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "write"}]}

            def auth_check(self, **kwargs):
                error = RuntimeError("not found")
                error.response = types.SimpleNamespace(status_code=404)
                raise error

            def create_repo(self, **kwargs):
                raise AssertionError("create_repo must not be reached")

        result = auth.recover_public_nexus(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_write_only"}, api_factory=Api
        )
        self.assertEqual("BLOCKED_NO_TARGET_WRITER", result["state"])
        self.assertEqual("OrgAdminUnverified", result["attempts"][0]["error_type"])

    def test_create_readback_failure_is_unknown_after_attempt(self) -> None:
        class Api:
            def __init__(self, *, token):
                self.checks = 0

            def whoami(self):
                return {"name": "founder", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]}

            def auth_check(self, **kwargs):
                self.checks += 1
                if self.checks == 1:
                    error = RuntimeError("not found")
                    error.response = types.SimpleNamespace(status_code=404)
                    raise error

            def create_repo(self, **kwargs):
                return "https://huggingface.co/spaces/SZLHOLDINGS/nexus"

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True)

        result = auth.recover_public_nexus(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("UNKNOWN_AFTER_ATTEMPT", result["state"])
        self.assertEqual("post_create_readback", result["attempts"][0]["phase"])

    def test_writable_private_target_is_reported_without_visibility_change(self) -> None:
        class Api:
            def __init__(self, *, token):
                pass

            def whoami(self):
                return {"name": "founder"}

            def auth_check(self, **kwargs):
                return None

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(id="SZLHOLDINGS/nexus", private=True)

            def create_repo(self, **kwargs):
                raise AssertionError("existing target must never be recreated")

        result = auth.recover_public_nexus(
            {"HF_ORG_TOKEN_CANDIDATE": "hf_secret_material"}, api_factory=Api
        )
        self.assertEqual("BLOCKED_EXISTING_TARGET_MISMATCH", result["state"])

    def test_recovery_boundary_refuses_non_main_dispatch_before_provider_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            token_file = root / "token"
            policy = _HERE.parent / "data" / "hf-space-lifecycle-policy.json"
            with (
                patch.dict(os.environ, {
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REF": "refs/heads/unprotected",
                    "GITHUB_REPOSITORY": "szl-holdings/.github",
                    "HF_ORG_TOKEN_CANDIDATE": "hf_secret_material",
                }),
                patch.object(
                    auth,
                    "recover_public_nexus",
                    side_effect=AssertionError("provider must not be touched"),
                ),
            ):
                code = auth.main([
                    "--target-repo", "SZLHOLDINGS/nexus",
                    "--target-type", "space",
                    "--recover-exact-public-nexus",
                    "--recovery-policy", str(policy),
                    "--token-file", str(token_file),
                    "--report", str(report),
                ])
            self.assertEqual(1, code)
            self.assertFalse(token_file.exists())
            self.assertNotIn("hf_secret_material", report.read_text(encoding="utf-8"))

    def test_protected_policy_must_declare_exact_public_nexus(self) -> None:
        policy_path = _HERE.parent / "data" / "hf-space-lifecycle-policy.json"
        auth._assert_public_nexus_policy(policy_path)
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "policy.json"
            data = json.loads(policy_path.read_text(encoding="utf-8"))
            for target in data["targets"]:
                if target["repo_id"] == "SZLHOLDINGS/nexus":
                    target["desired_visibility"] = "private"
            wrong.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(auth.CredentialSelectionError):
                auth._assert_public_nexus_policy(wrong)

    def test_repository_404_never_proves_creation_authority(self) -> None:
        class FakeRepositoryNotFoundError(RuntimeError):
            pass

        class FakeHfApi:
            def __init__(self, *, token: str):
                self.token = token

            def whoami(self):
                return {"name": "publisher-candidate"}

            def auth_check(self, *, repo_id: str, repo_type: str, write: bool):
                self.asserted = (repo_id, repo_type, write)
                raise FakeRepositoryNotFoundError("404: target unavailable")

        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.HfApi = FakeHfApi
        fake_utils = types.ModuleType("huggingface_hub.utils")
        fake_utils.RepositoryNotFoundError = FakeRepositoryNotFoundError

        with patch.dict(
            sys.modules,
            {
                "huggingface_hub": fake_hub,
                "huggingface_hub.utils": fake_utils,
            },
        ):
            for allow_create in (False, True):
                with self.subTest(allow_create=allow_create):
                    with self.assertRaises(FakeRepositoryNotFoundError):
                        auth.validate_token(
                            "hf_candidate",
                            source="HF_ORG_TOKEN",
                            target_repo="SZLHOLDINGS/nexus",
                            target_type="space",
                            allow_create=allow_create,
                        )

    def test_oidc_subprocess_cannot_inherit_fallback_credentials(self) -> None:
        inherited = {
            variable: f"hf_secret_{index}"
            for index, pair in enumerate(auth.TOKEN_ENV_ORDER)
            for variable in pair
        }
        inherited.update(
            {
                "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.invalid/token",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "runner-oidc-token",
                "PATH": os.environ.get("PATH", ""),
            }
        )
        captured: dict[str, str] = {}

        def run(_command, **kwargs):
            captured.update(kwargs["env"])
            return types.SimpleNamespace(
                returncode=0,
                stdout="hf_oidc_result\n",
                stderr="",
            )

        with (
            patch.dict(os.environ, inherited, clear=True),
            patch.object(auth.subprocess, "run", side_effect=run),
        ):
            token = auth.acquire_oidc_token("space:SZLHOLDINGS/nexus")

        self.assertEqual("hf_oidc_result", token)
        for pair in auth.TOKEN_ENV_ORDER:
            for variable in pair:
                self.assertNotIn(variable, captured)
        self.assertEqual(
            "https://oidc.invalid/token",
            captured["ACTIONS_ID_TOKEN_REQUEST_URL"],
        )
        self.assertEqual(
            "runner-oidc-token",
            captured["ACTIONS_ID_TOKEN_REQUEST_TOKEN"],
        )
        self.assertEqual("space:SZLHOLDINGS/nexus", captured["HF_OIDC_RESOURCE"])
        self.assertEqual("1", captured["HF_HUB_DISABLE_IMPLICIT_TOKEN"])

    def test_report_and_console_fields_cannot_contain_token_bytes(self) -> None:
        token = "hf_secret_material"
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "credential.json"
            selected = self._result("HF_ORG_TOKEN1")
            auth._write_report(
                report,
                target_repo="SZLHOLDINGS/nexus",
                target_type="space",
                resource=None,
                selected=selected,
                attempts=[
                    auth.Attempt(
                        source=selected.source,
                        present=True,
                        valid=True,
                        target_access=selected.target_access,
                    )
                ],
            )
            raw = report.read_text(encoding="utf-8")
            payload = json.loads(raw)

        self.assertNotIn(token, raw)
        self.assertFalse(payload["token_persisted"])
        self.assertFalse(payload["token_logged"])

    def test_selected_token_uses_an_exclusive_mode_0600_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "publisher.token"
            with patch.dict(os.environ, {"RUNNER_TEMP": directory}):
                auth._write_token_file(token_file, "hf_valid_second")
            text = token_file.read_text(encoding="utf-8")
            mode = token_file.stat().st_mode & 0o777

        self.assertEqual("hf_valid_second\n", text)
        self.assertEqual(0o600, mode)
        self.assertNotIn("hf_invalid_first", text)

    def test_token_file_refuses_overwrite_and_symlink_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing.token"
            existing.write_text("do-not-replace\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"RUNNER_TEMP": directory}),
                self.assertRaisesRegex(
                    auth.CredentialSelectionError,
                    "already exists",
                ),
            ):
                auth._write_token_file(existing, "hf_valid_second")
            self.assertEqual("do-not-replace\n", existing.read_text(encoding="utf-8"))

            target = root / "target.token"
            target.write_text("target\n", encoding="utf-8")
            link = root / "linked.token"
            os.symlink(target, link)
            with (
                patch.dict(os.environ, {"RUNNER_TEMP": directory}),
                self.assertRaisesRegex(
                    auth.CredentialSelectionError,
                    "already exists",
                ),
            ):
                auth._write_token_file(link, "hf_valid_second")
            self.assertEqual("target\n", target.read_text(encoding="utf-8"))

    def test_token_file_cannot_escape_runner_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner_temp = root / "runner"
            outside = root / "outside"
            runner_temp.mkdir()
            outside.mkdir()
            with (
                patch.dict(os.environ, {"RUNNER_TEMP": str(runner_temp)}),
                self.assertRaisesRegex(
                    auth.CredentialSelectionError,
                    "direct child of RUNNER_TEMP",
                ),
            ):
                auth._write_token_file(outside / "publisher.token", "hf_valid_second")


class NexusWorkflowCredentialContractTests(unittest.TestCase):
    def test_workflow_validates_each_secret_independently(self) -> None:
        workflow = (_HERE.parent / "workflows" / "publish-nexus-space.yml").read_text(
            encoding="utf-8"
        )

        for variable in (
            "HF_ORG_TOKEN_CANDIDATE",
            "HF_ORG_TOKEN1_CANDIDATE",
            "HF_WRITE_TOKEN_CANDIDATE",
            "HF_TOKEN_CANDIDATE",
        ):
            self.assertEqual(2, workflow.count(variable), variable)
        self.assertIn("acquire_hf_publisher_token.py", workflow)
        self.assertIn('--token-file "$RUNNER_TEMP/nexus-hf-token"', workflow)
        self.assertNotIn("$GITHUB_ENV", workflow)
        self.assertIn("--target-type space", workflow)
        self.assertNotIn(
            "secrets.HF_ORG_TOKEN || secrets.HF_ORG_TOKEN1",
            workflow,
        )

    def test_selector_regression_suite_is_required_by_pr_validation(self) -> None:
        workflow = (
            _HERE.parent / "workflows" / "test-hf-publisher-credential-selector.yml"
        ).read_text(encoding="utf-8")

        for path in (
            ".github/scripts/acquire_hf_publisher_token.py",
            ".github/scripts/test_acquire_hf_publisher_token.py",
            ".github/workflows/publish-nexus-space.yml",
            ".github/workflows/test-hf-publisher-credential-selector.yml",
        ):
            self.assertIn(path, workflow)
        self.assertIn(
            "python -I -B .github/scripts/test_acquire_hf_publisher_token.py",
            workflow,
        )

    def test_recovery_is_owner_dispatch_only_and_serializes_publication(self) -> None:
        workflow = (_HERE.parent / "workflows" / "publish-nexus-space.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("recover_missing_target:", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("--recover-exact-public-nexus", workflow)
        self.assertIn(
            "--recovery-policy tools/.github/data/hf-space-lifecycle-policy.json",
            workflow,
        )
        self.assertIn("'publish' }}", workflow)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", workflow)

    def test_selected_token_is_never_printed_or_redeclared(self) -> None:
        workflow = (_HERE.parent / "workflows" / "publish-nexus-space.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("echo $HF_TOKEN", workflow)
        self.assertNotIn("echo ${HF_TOKEN", workflow)
        self.assertEqual(0, workflow.count("HF_TOKEN: ${{"))
        self.assertEqual(3, workflow.count('HF_TOKEN="$(<"$TOKEN_FILE")"'))

        cleanup = workflow.index("Remove the ephemeral publisher credential")
        upload = workflow.index("Upload immutable Nexus deployment evidence")
        self.assertLess(cleanup, upload)
        self.assertIn("if: always()", workflow[cleanup:upload])
        self.assertNotIn("HF_TOKEN", workflow[upload:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
