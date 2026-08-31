#!/usr/bin/env python3
"""Network-free tests for the one-Space public-visibility controller."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "hf_space_lifecycle_reconcile.py"
POLICY = ROOT / ".github" / "data" / "hf-space-lifecycle-policy.json"
WORKFLOW = ROOT / ".github" / "workflows" / "hf-space-lifecycle-reconcile.yml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
SPEC = importlib.util.spec_from_file_location("hf_space_lifecycle_reconcile", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

REVISION = "a" * 40
MAIN_SHA = "b" * 40


def state(
    repo_id: str,
    visibility: str,
    stage: str = "RUNNING",
    revision: str = REVISION,
    sdk: str = "docker",
) -> module.SpaceState:
    return module.SpaceState(repo_id, visibility, stage, revision, sdk)


class FakeApi:
    def __init__(self, states: dict[str, module.SpaceState]) -> None:
        self.states = copy.deepcopy(states)
        self.mutations: list[tuple[str, dict[str, object]]] = []
        self.force_bad_readback = False
        self.raise_after_send: Exception | None = None
        self.identity = {
            "type": "user",
            "auth": {"accessToken": {"role": "write"}},
            "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}],
        }
        self.write_authorized_targets = set(states)
        self.auth_checks: list[dict[str, object]] = []
        self.auth_check_error: Exception | None = None
        self.auth_check_result: object | None = None

    def whoami(self, *, cache: bool) -> dict:
        if cache:
            raise AssertionError("credential preflight must not use cached identity")
        return copy.deepcopy(self.identity)

    def auth_check(self, *, repo_id: str, repo_type: str, write: bool) -> object:
        call = {"repo_id": repo_id, "repo_type": repo_type, "write": write}
        self.auth_checks.append(call)
        if repo_type != "space" or write is not True:
            raise AssertionError("credential preflight escaped exact Space write check")
        if self.auth_check_error is not None:
            raise self.auth_check_error
        if repo_id not in self.write_authorized_targets:
            raise PermissionError("target-specific write access denied")
        return self.auth_check_result

    def space_info(self, *, repo_id: str, expand: list[str]) -> SimpleNamespace:
        if expand != ["private", "runtime", "sdk", "sha"]:
            raise AssertionError(f"unexpected expansion: {expand}")
        current = self.states[repo_id]
        return SimpleNamespace(
            id=current.repo_id,
            private=current.visibility == "private",
            runtime=SimpleNamespace(stage=current.runtime_stage),
            sha=current.revision,
            sdk=current.sdk,
        )

    def update_repo_settings(
        self, *, repo_id: str, repo_type: str, private: bool
    ) -> None:
        kwargs = {"repo_id": repo_id, "repo_type": repo_type, "private": private}
        self.mutations.append(("update_repo_settings", kwargs))
        if repo_type != "space" or private is not False:
            raise AssertionError("controller escaped its public-Space-only boundary")
        if not self.force_bad_readback:
            old = self.states[repo_id]
            self.states[repo_id] = state(
                repo_id, "public", old.runtime_stage, old.revision, old.sdk
            )
        if self.raise_after_send is not None:
            raise self.raise_after_send


def passing_guard(_environ: object) -> str:
    return MAIN_SHA


def passing_after(_environ: object) -> tuple[str, str]:
    return "main", MAIN_SHA


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.policy_sha256 = module.policy_digest(cls.policy)

    def run_controller(
        self,
        repo_id: str,
        current: module.SpaceState,
        *,
        mode: str = "plan",
        transition: str = "inspect",
        expected: bool = False,
        expected_policy: bool = False,
        api: FakeApi | None = None,
        guard=passing_guard,
        after_reader=passing_after,
    ) -> tuple[dict, int, FakeApi]:
        api = api or FakeApi({repo_id: current})
        report, code = module.reconcile(
            client=module.HubSpaceClient(api),
            policy_path=POLICY,
            target=repo_id,
            mode=mode,
            requested_transition=transition,
            expected_policy_sha256=self.policy_sha256 if expected_policy else None,
            expected_visibility=current.visibility if expected else None,
            expected_runtime_stage=current.runtime_stage if expected else None,
            expected_revision=current.revision if expected else None,
            environ={"GITHUB_SHA": MAIN_SHA},
            main_guard=guard,
            main_after_reader=after_reader,
            readback_attempts=2,
            readback_interval=0,
        )
        return report, code, api

    def test_policy_is_exact_authenticated_inventory_and_public_only(self) -> None:
        policy, targets = module.load_policy(POLICY)
        self.assertEqual(len(targets), 46)
        self.assertEqual(set(targets), module.ALLOWED_REPO_IDS)
        self.assertEqual(policy["authority"]["run_id"], module.AUTHORITY_RUN_ID)
        self.assertEqual(
            policy["authority"]["artifact_digest"],
            module.AUTHORITY_ARTIFACT_DIGEST,
        )
        self.assertEqual(policy["token_authority"]["required_org_role"], "admin")
        self.assertFalse(
            policy["token_authority"]["reported_access_token_role_is_authority"]
        )
        self.assertEqual(
            policy["token_authority"]["required_target_write_preflight"],
            'HfApi.auth_check(repo_id=target, repo_type="space", write=True)',
        )
        self.assertTrue(all(target.visibility == "public" for target in targets.values()))
        self.assertTrue(
            all(target.runtime_stage == "RUNNING" for target in targets.values())
        )

    def test_policy_rejects_unknown_duplicate_wildcard_private_and_weakened_boundary(self) -> None:
        mutations = []
        unknown = copy.deepcopy(self.policy)
        unknown["unknown"] = True
        mutations.append(unknown)
        duplicate = copy.deepcopy(self.policy)
        duplicate["targets"].append(copy.deepcopy(duplicate["targets"][0]))
        mutations.append(duplicate)
        wildcard = copy.deepcopy(self.policy)
        wildcard["targets"][0]["repo_id"] = "SZLHOLDINGS/*"
        mutations.append(wildcard)
        private = copy.deepcopy(self.policy)
        private["targets"][0]["desired_visibility"] = "private"
        mutations.append(private)
        weakened = copy.deepcopy(self.policy)
        weakened["boundaries"]["archive"] = True
        mutations.append(weakened)
        role_authority = copy.deepcopy(self.policy)
        role_authority["token_authority"][
            "reported_access_token_role_is_authority"
        ] = True
        mutations.append(role_authority)
        repointed = copy.deepcopy(self.policy)
        repointed["authority"]["artifact_digest"] = "sha256:" + "f" * 64
        mutations.append(repointed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            for changed in mutations:
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(module.LifecycleError):
                    module.load_policy(path)

    def test_arbitrary_target_rejected_before_identity_or_provider_read(self) -> None:
        class ExplodingClient:
            def verify_operator(self, _repo_id: str) -> dict:
                raise AssertionError("provider must not be called")

        report, code = module.reconcile(
            client=ExplodingClient(),
            policy_path=POLICY,
            target="SZLHOLDINGS/all",
            mode="plan",
            requested_transition="inspect",
            expected_policy_sha256=None,
            expected_visibility=None,
            expected_runtime_stage=None,
            expected_revision=None,
            environ={},
            main_guard=passing_guard,
            main_after_reader=passing_after,
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "BLOCKED_PRECONDITION")

    def test_target_write_preflight_is_exact_and_role_is_informational(self) -> None:
        repo_id = "SZLHOLDINGS/a11oy"
        api = FakeApi({repo_id: state(repo_id, "public")})
        safe = module.HubSpaceClient(api).verify_operator(repo_id)
        self.assertEqual(safe["access_token_role_reported"], "write")
        self.assertFalse(safe["access_token_role_is_authority"])
        self.assertEqual(safe["organization_role"], "admin")
        self.assertEqual(safe["target_write_authority"], "VERIFIED")
        self.assertEqual(safe["target_write_repository"], repo_id)
        self.assertEqual(
            api.auth_checks,
            [{"repo_id": repo_id, "repo_type": "space", "write": True}],
        )

        # A fine-grained label alone proves nothing when this target is read-only.
        api.identity["auth"]["accessToken"]["role"] = "fineGrained"
        api.write_authorized_targets.clear()
        with self.assertRaises(module.LifecycleError):
            module.HubSpaceClient(api).verify_operator(repo_id)
        self.assertEqual(api.mutations, [])

        # A token with write authority elsewhere must still fail this exact target.
        api.identity["auth"]["accessToken"]["role"] = "write"
        api.write_authorized_targets = {"SZLHOLDINGS/killinchu"}
        with self.assertRaises(module.LifecycleError):
            module.HubSpaceClient(api).verify_operator(repo_id)
        self.assertEqual(api.mutations, [])

    def test_target_write_preflight_rejects_identity_transport_and_malformed_results(self) -> None:
        repo_id = "SZLHOLDINGS/a11oy"
        api = FakeApi({repo_id: state(repo_id, "public")})
        for identity in (
            {"type": "org", "auth": {}, "orgs": []},
            {"type": "user", "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}]},
            {
                "type": "user",
                "auth": {"accessToken": {"role": "write"}},
                "orgs": [
                    {"name": "SZLHOLDINGS", "roleInOrg": "admin"},
                    {"name": "SZLHOLDINGS", "roleInOrg": "admin"},
                ],
            },
            {
                "type": "user",
                "auth": {"accessToken": {"role": "write"}},
                "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "write"}],
            },
        ):
            api.identity = identity
            with self.assertRaises(module.LifecycleError):
                module.HubSpaceClient(api).verify_operator(repo_id)

        api.identity = {
            "type": "user",
            "auth": {"accessToken": {"role": "fineGrained"}},
            "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": "admin"}],
        }
        for provider_error in (
            RuntimeError("unexpected redirect with hf_fake_token"),
            TimeoutError("transport failed with hf_fake_token"),
            ValueError("malformed provider response with hf_fake_token"),
        ):
            api.auth_check_error = provider_error
            with self.assertRaises(module.LifecycleError) as caught:
                module.HubSpaceClient(api).verify_operator(repo_id)
            self.assertNotIn("hf_fake_token", str(caught.exception))
            self.assertEqual(api.mutations, [])

        api.auth_check_error = None
        for ambiguous_result in (False, True, {}):
            api.auth_check_result = ambiguous_result
            with self.assertRaises(module.LifecycleError):
                module.HubSpaceClient(api).verify_operator(repo_id)
            self.assertEqual(api.mutations, [])

    def test_unknown_private_state_and_provider_denial_never_mutate(self) -> None:
        repo_id = "SZLHOLDINGS/anatomy"

        class MissingPrivateApi(FakeApi):
            def space_info(self, *, repo_id: str, expand: list[str]) -> SimpleNamespace:
                info = super().space_info(repo_id=repo_id, expand=expand)
                info.private = None
                return info

        missing = MissingPrivateApi({repo_id: state(repo_id, "public")})
        report, code, _ = self.run_controller(repo_id, state(repo_id, "public"), api=missing)
        self.assertEqual(code, 2)
        self.assertEqual(missing.mutations, [])

        class DeniedApi(FakeApi):
            def space_info(self, *, repo_id: str, expand: list[str]) -> SimpleNamespace:
                error = RuntimeError("provider body contained hf_fake_token")
                error.response = SimpleNamespace(status_code=403, headers={})
                raise error

        denied = DeniedApi({repo_id: state(repo_id, "public")})
        report, code, _ = self.run_controller(repo_id, state(repo_id, "public"), api=denied)
        self.assertEqual(code, 2)
        self.assertEqual(report["error"]["http_status"], 403)
        self.assertNotIn("hf_fake_token", json.dumps(report))
        self.assertEqual(denied.mutations, [])

    def test_plan_reports_full_and_runtime_only_convergence_truthfully(self) -> None:
        repo_id = "SZLHOLDINGS/a11oy"
        report, code, api = self.run_controller(repo_id, state(repo_id, "public"))
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "PLANNED_CONVERGED")
        self.assertEqual(api.mutations, [])
        report, code, api = self.run_controller(
            repo_id, state(repo_id, "public", "PAUSED")
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            report["result"], "PLANNED_VISIBILITY_CONVERGED_RUNTIME_OUT_OF_SCOPE"
        )
        self.assertFalse(report["convergence"]["full_policy_converged"])
        self.assertEqual(api.mutations, [])

    def test_private_paused_space_is_blocked_before_mutation(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        report, code, api = self.run_controller(
            repo_id, state(repo_id, "private", "PAUSED")
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "BLOCKED_PRECONDITION")
        self.assertEqual(api.mutations, [])

    def test_apply_requires_policy_digest_exact_before_and_transition(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        current = state(repo_id, "private")
        report, code, api = self.run_controller(
            repo_id,
            current,
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=False,
        )
        self.assertEqual(code, 2)
        self.assertEqual(api.mutations, [])
        report, code, api = self.run_controller(
            repo_id,
            current,
            mode="apply",
            transition="inspect",
            expected=True,
            expected_policy=True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(api.mutations, [])

    def test_expected_provider_drift_blocks_before_write(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        current = state(repo_id, "private")
        api = FakeApi({repo_id: current})
        report, code = module.reconcile(
            client=module.HubSpaceClient(api),
            policy_path=POLICY,
            target=repo_id,
            mode="apply",
            requested_transition="private-to-public",
            expected_policy_sha256=self.policy_sha256,
            expected_visibility="public",
            expected_runtime_stage="RUNNING",
            expected_revision=REVISION,
            environ={"GITHUB_SHA": MAIN_SHA},
            main_guard=passing_guard,
            main_after_reader=passing_after,
        )
        self.assertEqual(code, 2)
        self.assertIn("expected-before drift", report["error"]["detail"])
        self.assertEqual(api.mutations, [])

    def test_apply_uses_one_public_call_and_authenticated_readback(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        report, code, api = self.run_controller(
            repo_id,
            state(repo_id, "private"),
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=True,
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "VERIFIED")
        self.assertEqual(
            api.mutations,
            [
                (
                    "update_repo_settings",
                    {"repo_id": repo_id, "repo_type": "space", "private": False},
                )
            ],
        )

    def test_public_apply_is_precondition_failure(self) -> None:
        repo_id = "SZLHOLDINGS/a11oy"
        report, code, api = self.run_controller(
            repo_id,
            state(repo_id, "public"),
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(api.mutations, [])

    def test_exception_after_send_can_only_pass_through_readback(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        current = state(repo_id, "private")
        api = FakeApi({repo_id: current})
        api.raise_after_send = RuntimeError("provider response contained hf_fake_token")
        report, code, _ = self.run_controller(
            repo_id,
            current,
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=True,
            api=api,
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "VERIFIED")
        self.assertNotIn("hf_fake_token", json.dumps(report))

    def test_unverified_write_is_unknown_and_main_drift_is_not_verified(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        current = state(repo_id, "private")
        api = FakeApi({repo_id: current})
        api.force_bad_readback = True
        report, code, _ = self.run_controller(
            repo_id,
            current,
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=True,
            api=api,
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "UNKNOWN_AFTER_ATTEMPT")
        self.assertEqual(len(api.mutations), 1)
        report, code, _ = self.run_controller(
            repo_id,
            current,
            mode="apply",
            transition="private-to-public",
            expected=True,
            expected_policy=True,
            after_reader=lambda _env: ("main", "c" * 40),
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "CONCURRENT_DRIFT")

    def test_revision_change_after_write_is_unknown(self) -> None:
        repo_id = "SZLHOLDINGS/szl-khipu"
        current = state(repo_id, "private")
        api = FakeApi({repo_id: current})

        class RevisionChangingClient(module.HubSpaceClient):
            def set_public(self, target: str) -> None:
                super().set_public(target)
                old = self.api.states[target]
                self.api.states[target] = state(
                    target, old.visibility, old.runtime_stage, "d" * 40, old.sdk
                )

        report, code = module.reconcile(
            client=RevisionChangingClient(api),
            policy_path=POLICY,
            target=repo_id,
            mode="apply",
            requested_transition="private-to-public",
            expected_policy_sha256=self.policy_sha256,
            expected_visibility="private",
            expected_runtime_stage="RUNNING",
            expected_revision=REVISION,
            environ={"GITHUB_SHA": MAIN_SHA},
            main_guard=passing_guard,
            main_after_reader=passing_after,
            readback_attempts=1,
            readback_interval=0,
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "UNKNOWN_AFTER_ATTEMPT")

    def test_current_main_guard_checks_event_repo_ref_head_and_live_tip(self) -> None:
        base = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": module.CONTROL_REPOSITORY,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": MAIN_SHA,
            "GITHUB_TOKEN": "github-token",
        }

        def fetch(url: str, token: str) -> dict:
            self.assertEqual(token, "github-token")
            if url.endswith(f"/repos/{module.CONTROL_REPOSITORY}"):
                return {"default_branch": "main"}
            return {"sha": MAIN_SHA}

        self.assertEqual(
            module.require_current_protected_main(
                base, fetch_json=fetch, local_head=lambda: MAIN_SHA
            ),
            MAIN_SHA,
        )
        for key, bad in (
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_REPOSITORY", "szl-holdings/a11oy"),
            ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_SHA", "short"),
        ):
            changed = dict(base)
            changed[key] = bad
            with self.assertRaises(module.LifecycleError):
                module.require_current_protected_main(
                    changed, fetch_json=fetch, local_head=lambda: MAIN_SHA
                )
        with self.assertRaises(module.LifecycleError):
            module.require_current_protected_main(
                base, fetch_json=fetch, local_head=lambda: "c" * 40
            )

    def test_error_record_never_serializes_raw_provider_message(self) -> None:
        error = RuntimeError("secret provider body hf_fake_token")
        error.response = SimpleNamespace(
            status_code=404, headers={"x-request-id": "request-123"}
        )
        self.assertEqual(
            module.error_record(error),
            {"class": "RuntimeError", "http_status": 404, "request_id": "request-123"},
        )

    def test_workflow_and_source_lock_the_only_mutator(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertNotIn("  pull_request:", workflow)
        self.assertNotIn("  push:\n", workflow)
        self.assertIn("group: hf-provider-mutation-szlholdings", workflow)
        self.assertIn("environment: production", workflow)
        secret_binding = "HF_ORG_TOKEN: ${{ secrets.HF_ORG_TOKEN }}"
        secret_lines = [
            line for line in workflow.splitlines() if "HF_ORG_TOKEN" in line
        ]
        self.assertEqual(secret_lines, [f"          {secret_binding}"])
        self.assertEqual(workflow.count(secret_binding), 1)
        step_blocks = re.split(r"(?=^      - name:)", workflow, flags=re.MULTILINE)
        controller_steps = [
            block
            for block in step_blocks
            if block.startswith(
                "      - name: Plan or apply one expected-state publication"
            )
        ]
        self.assertEqual(len(controller_steps), 1)
        self.assertIn(secret_binding, controller_steps[0])
        for block in step_blocks:
            if block is not controller_steps[0]:
                self.assertNotIn("HF_ORG_TOKEN", block)
        self.assertIn("--expected-policy-sha256", workflow)
        self.assertIn("--require-hashes", workflow)
        self.assertIn("persist-credentials: false", workflow)
        uses = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
        self.assertTrue(uses)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in uses))

        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count("self.api.auth_check("), 1)
        self.assertIn('repo_type="space"', source)
        self.assertIn("write=True", source)
        self.assertIn("if auth_result is not None:", source)
        self.assertIn("follow_redirects=False", source)
        self.assertIn("endpoint=HUGGING_FACE_ENDPOINT", source)
        self.assertEqual(source.count("self.api.update_repo_settings("), 1)
        self.assertIn("private=False", source)
        for forbidden in (
            "private=True",
            "archive_repo(",
            "create_repo(",
            "delete_repo(",
            "move_repo(",
            "request_space_hardware(",
            "pause_space(",
            "restart_space(",
            "add_space_secret(",
            "add_space_variable(",
            "create_commit(",
            "upload_file(",
            "upload_folder(",
            "duplicate_space(",
            "request_space_storage(",
            "set_space_sleep_time(",
            "delete_space_secret(",
            "delete_space_variable(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn(
            "test_hf_space_lifecycle_reconcile.py",
            TESTS_WORKFLOW.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
