from __future__ import annotations

import ast
import datetime as dt
import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "estate_deadman.py"
SPEC = spec_from_file_location("estate_deadman", MODULE_PATH)
assert SPEC and SPEC.loader
estate_deadman = module_from_spec(SPEC)
sys.modules[SPEC.name] = estate_deadman
SPEC.loader.exec_module(estate_deadman)

ContractError = estate_deadman.ContractError
GitHubApi = estate_deadman.GitHubApi
evaluate_target = estate_deadman.evaluate_target
issue_body = estate_deadman.issue_body
load_policy = estate_deadman.load_policy
offline_contract = estate_deadman.offline_contract
validate_policy = estate_deadman.validate_policy

NOW = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)


def stamp(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def target() -> dict[str, Any]:
    return {
        "id": "autonomic-public-estate-sre",
        "repository": "szl-holdings/szl-org-health",
        "workflow_path": ".github/workflows/autonomic-sre.yml",
        "branch": "main",
        "event": "schedule",
        "max_success_age_minutes": 30,
        "max_active_age_minutes": 20,
        "bootstrap_grace_minutes": 45,
    }


def policy() -> dict[str, Any]:
    return {
        "schema": "szl.estate-deadman-policy/v1",
        "controller_repository": "szl-holdings/.github",
        "controller_branch": "main",
        "confirmation": {"samples": 2, "interval_seconds": 60},
        "incident": {
            "title": "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            "refresh_minutes": 60,
        },
        "targets": [target()],
    }


def run(
    *,
    run_id: int,
    status: str,
    conclusion: str | None,
    created_minutes_ago: int,
    completed_minutes_ago: int | None = None,
) -> dict[str, Any]:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "created_at": stamp(created_minutes_ago),
        "run_started_at": stamp(created_minutes_ago),
        "completed_at": (
            stamp(completed_minutes_ago)
            if completed_minutes_ago is not None
            else None
        ),
        "html_url": f"https://github.com/szl-holdings/example/actions/runs/{run_id}",
    }


class PolicyContractTests(unittest.TestCase):
    def test_repository_policy_loads_and_hashes(self) -> None:
        loaded, digest = load_policy(ROOT / "governance" / "estate-deadman.v1.json")
        self.assertEqual(loaded["schema"], "szl.estate-deadman-policy/v1")
        self.assertEqual(len(loaded["targets"]), 3)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(item["event"] == "schedule" for item in loaded["targets"]))

    def test_policy_rejects_external_repository(self) -> None:
        raw = policy()
        raw["targets"][0]["repository"] = "outside/example"
        with self.assertRaises(ContractError):
            validate_policy(raw)

    def test_policy_rejects_noncanonical_workflow_path(self) -> None:
        raw = policy()
        raw["targets"][0]["workflow_path"] = "../../workflow.yml"
        with self.assertRaises(ContractError):
            validate_policy(raw)

    def test_policy_rejects_non_schedule_monitor(self) -> None:
        raw = policy()
        raw["targets"][0]["event"] = "workflow_dispatch"
        with self.assertRaises(ContractError):
            validate_policy(raw)

    def test_policy_rejects_single_sample_confirmation(self) -> None:
        raw = policy()
        raw["confirmation"]["samples"] = 1
        with self.assertRaises(ContractError):
            validate_policy(raw)

    def test_offline_contract_denies_mutating_authority(self) -> None:
        valid = validate_policy(policy())
        receipt = offline_contract(valid, "a" * 64)
        self.assertTrue(receipt["valid"])
        self.assertTrue(receipt["authority"]["two_sample_confirmation"])
        for key in (
            "workflow_mutation",
            "branch_mutation",
            "deployment_mutation",
            "dns_mutation",
            "product_execution",
        ):
            self.assertFalse(receipt["authority"][key], key)


class EvaluationTests(unittest.TestCase):
    def observe(
        self,
        runs: list[dict[str, Any]],
        *,
        workflow_state: str = "active",
        change_minutes_ago: int = 120,
    ):
        return evaluate_target(
            target(),
            workflow={
                "id": 100,
                "state": workflow_state,
                "path": ".github/workflows/autonomic-sre.yml",
            },
            runs=runs,
            workflow_revision="a" * 40,
            workflow_changed_at=stamp(change_minutes_ago),
            now=NOW,
        )

    def test_recent_success_is_healthy(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=5,
                    completed_minutes_ago=4,
                )
            ]
        )
        self.assertTrue(observed.healthy)
        self.assertEqual(observed.state, "HEALTHY")
        self.assertEqual(observed.success_age_minutes, 4)

    def test_stale_success_fails(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=50,
                    completed_minutes_ago=49,
                )
            ]
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "STALE_SUCCESS")

    def test_latest_failure_overrides_recent_success(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=11,
                    status="completed",
                    conclusion="failure",
                    created_minutes_ago=2,
                    completed_minutes_ago=1,
                ),
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=8,
                    completed_minutes_ago=7,
                ),
            ]
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "LATEST_RUN_FAILED")
        self.assertEqual(observed.last_success_run_id, 10)

    def test_fresh_active_run_with_success_baseline_is_healthy(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=12,
                    status="in_progress",
                    conclusion=None,
                    created_minutes_ago=3,
                ),
                run(
                    run_id=11,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=10,
                    completed_minutes_ago=9,
                ),
            ]
        )
        self.assertTrue(observed.healthy)
        self.assertEqual(observed.state, "RUNNING")

    def test_old_active_run_is_stuck(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=12,
                    status="in_progress",
                    conclusion=None,
                    created_minutes_ago=45,
                ),
                run(
                    run_id=11,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=50,
                    completed_minutes_ago=49,
                ),
            ]
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "STUCK_ACTIVE")

    def test_new_workflow_without_run_is_bootstrapping(self) -> None:
        observed = self.observe([], change_minutes_ago=10)
        self.assertTrue(observed.healthy)
        self.assertEqual(observed.state, "BOOTSTRAPPING")

    def test_old_workflow_without_run_fails(self) -> None:
        observed = self.observe([], change_minutes_ago=90)
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "NO_SCHEDULED_RUN")

    def test_disabled_workflow_fails_even_with_recent_success(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=5,
                    completed_minutes_ago=4,
                )
            ],
            workflow_state="disabled_manually",
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "WORKFLOW_DISABLED")


class ApiRouteTests(unittest.TestCase):
    class RecordingApi(GitHubApi):
        def __init__(self) -> None:
            self.token = "suppressed"
            self.timeout = 1
            self.paths: list[tuple[str, str]] = []

        def request(
            self,
            method: str,
            path: str,
            payload: Mapping[str, Any] | None = None,
        ) -> Any:
            self.paths.append((method, path))
            if path.endswith("/actions/workflows/autonomic-sre.yml"):
                return {
                    "id": 100,
                    "state": "active",
                    "path": ".github/workflows/autonomic-sre.yml",
                }
            if "/runs?" in path:
                return {"workflow_runs": []}
            if "/commits?" in path:
                return []
            if path.endswith("/branches/main"):
                return {
                    "commit": {
                        "sha": "a" * 40,
                        "commit": {"verification": {"verified": True}},
                    }
                }
            raise AssertionError(path)

    def test_workflow_routes_are_repository_and_filename_bound(self) -> None:
        api = self.RecordingApi()
        current = target()
        api.workflow(current)
        api.workflow_runs(current)
        api.workflow_change(current)
        combined = "\n".join(path for _, path in api.paths)
        self.assertIn("/repos/szl-holdings/szl-org-health/", combined)
        self.assertIn("/actions/workflows/autonomic-sre.yml", combined)
        self.assertIn("event=schedule", combined)
        self.assertIn("path=.github%2Fworkflows%2Fautonomic-sre.yml", combined)
        self.assertNotIn("https://", combined)
        self.assertNotIn("..", combined)

    def test_controller_tip_requires_verified_commit(self) -> None:
        api = self.RecordingApi()
        self.assertEqual(
            api.verified_branch_tip("szl-holdings/.github", "main"),
            "a" * 40,
        )


class IncidentContractTests(unittest.TestCase):
    def test_issue_body_contains_only_bounded_evidence(self) -> None:
        report = {
            "generated_at": stamp(0),
            "evidence_sha256": "b" * 64,
            "final_sample": [
                {
                    "id": "autonomic-public-estate-sre",
                    "healthy": False,
                    "state": "LATEST_RUN_FAILED",
                    "latest_run_id": 123,
                    "latest_conclusion": "failure",
                    "success_age_minutes": 7,
                    "reason": "latest completed scheduled run did not succeed",
                }
            ],
        }
        body = issue_body(report)
        self.assertIn("Two independent samples", body)
        self.assertIn("LATEST_RUN_FAILED", body)
        self.assertIn("SZL_ESTATE_DEADMAN_STATE_BEGIN", body)
        self.assertNotIn("password", body.lower())
        self.assertNotIn("authorization", body.lower())

    def test_module_has_no_dynamic_execution_or_subprocess(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"eval", "exec", "compile", "__import__"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/dispatches", source)
        self.assertNotIn("restart_space", source)
        self.assertNotIn("/git/refs", source)
        self.assertNotIn("/deployments", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
