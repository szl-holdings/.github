from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "estate_deadman.py"
WORKFLOW_CONTRACT_PATH = (
    ROOT / ".github" / "scripts" / "validate_estate_deadman_workflow.py"
)
SPEC = spec_from_file_location("estate_deadman", MODULE_PATH)
assert SPEC and SPEC.loader
estate_deadman = module_from_spec(SPEC)
sys.modules[SPEC.name] = estate_deadman
SPEC.loader.exec_module(estate_deadman)
WORKFLOW_SPEC = spec_from_file_location(
    "validate_estate_deadman_workflow", WORKFLOW_CONTRACT_PATH
)
assert WORKFLOW_SPEC and WORKFLOW_SPEC.loader
workflow_contract = module_from_spec(WORKFLOW_SPEC)
WORKFLOW_SPEC.loader.exec_module(workflow_contract)

ContractError = estate_deadman.ContractError
GitHubApi = estate_deadman.GitHubApi
TargetObservation = estate_deadman.TargetObservation
confirmed_failure_ids = estate_deadman.confirmed_failure_ids
classify_confirmation = estate_deadman.classify_confirmation
evaluate_target = estate_deadman.evaluate_target
issue_body = estate_deadman.issue_body
load_policy = estate_deadman.load_policy
offline_contract = estate_deadman.offline_contract
parse_incident_state = estate_deadman.parse_incident_state
reconcile_incident = estate_deadman.reconcile_incident
validate_policy = estate_deadman.validate_policy
WorkflowContractError = workflow_contract.WorkflowContractError
validate_workflow_source = workflow_contract.validate_workflow_source

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
        },
        "targets": [target()],
    }


def report(*, healthy: bool = False, generated_at: str | None = None) -> dict[str, Any]:
    final_sample = [
        {
            "id": "autonomic-public-estate-sre",
            "healthy": healthy,
            "state": "HEALTHY" if healthy else "LATEST_RUN_FAILED",
            "latest_run_id": 123,
            "latest_conclusion": "success" if healthy else "failure",
            "success_age_minutes": 7,
            "reason": "bounded test evidence",
        }
    ]
    return {
        "schema": "szl.estate-deadman-receipt/v1",
        "generated_at": generated_at or stamp(0),
        "controller_repository": "szl-holdings/.github",
        "controller_branch": "main",
        "controller_revision": "a" * 40,
        "controller_run_id": 987654,
        "controller_run_attempt": 1,
        "policy_sha256": "b" * 64,
        "evidence_sha256": "c" * 64,
        "confirmation_state": "HEALTHY" if healthy else "CONFIRMED_FAILURE",
        "confirmed_healthy": healthy,
        "confirmed_failed_target_ids": (
            [] if healthy else ["autonomic-public-estate-sre"]
        ),
        "final_sample": final_sample,
    }


def observation(item_id: str, healthy: bool) -> Any:
    return TargetObservation(
        id=item_id,
        repository=f"szl-holdings/{item_id}",
        workflow_path=".github/workflows/test.yml",
        healthy=healthy,
        state="HEALTHY" if healthy else "LATEST_RUN_FAILED",
        reason="test",
        workflow_state="active",
        workflow_id=1,
        workflow_revision="a" * 40,
        workflow_changed_at=stamp(60),
        latest_run_id=1,
        latest_status="completed",
        latest_conclusion="success" if healthy else "failure",
        latest_created_at=stamp(5),
        latest_updated_at=stamp(4),
        latest_html_url="https://github.com/szl-holdings/example/actions/runs/1",
        last_success_run_id=1 if healthy else None,
        last_success_updated_at=stamp(4) if healthy else None,
        success_age_minutes=4 if healthy else None,
        active_age_minutes=None,
    )


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
        "updated_at": (
            stamp(completed_minutes_ago) if completed_minutes_ago is not None else None
        ),
        "html_url": f"https://github.com/szl-holdings/example/actions/runs/{run_id}",
    }


class PolicyContractTests(unittest.TestCase):
    def test_repository_policy_loads_and_hashes(self) -> None:
        path = ROOT / "governance" / "estate-deadman.v1.json"
        loaded, digest = load_policy(path)
        self.assertEqual(loaded["schema"], "szl.estate-deadman-policy/v1")
        self.assertEqual(len(loaded["targets"]), 3)
        canonical_source = path.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(digest, hashlib.sha256(canonical_source).hexdigest())
        self.assertTrue(all(item["event"] == "schedule" for item in loaded["targets"]))

    def test_policy_rejects_duplicate_json_keys(self) -> None:
        source = (ROOT / "governance" / "estate-deadman.v1.json").read_text(
            encoding="utf-8"
        )
        ambiguous = source.replace(
            '  "schema": "szl.estate-deadman-policy/v1",',
            '  "schema": "attacker-value",\n'
            '  "schema": "szl.estate-deadman-policy/v1",',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(ambiguous, encoding="utf-8", newline="\n")
            with self.assertRaises(ContractError):
                load_policy(path)

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

    def test_policy_rejects_three_sample_mode_without_full_sampling_contract(
        self,
    ) -> None:
        raw = policy()
        raw["confirmation"]["samples"] = 3
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

    def test_two_sample_failure_must_be_same_target(self) -> None:
        samples = [
            [observation("target-a", False), observation("target-b", True)],
            [observation("target-a", True), observation("target-b", False)],
        ]
        self.assertEqual(confirmed_failure_ids(samples, 2), [])
        self.assertEqual(classify_confirmation(samples, []), "INCONCLUSIVE")

    def test_two_sample_failure_intersection_keeps_only_confirmed_target(self) -> None:
        samples = [
            [observation("target-a", False), observation("target-b", True)],
            [observation("target-a", False), observation("target-b", False)],
        ]
        self.assertEqual(confirmed_failure_ids(samples, 2), ["target-a"])
        self.assertEqual(
            classify_confirmation(samples, ["target-a"]), "CONFIRMED_FAILURE"
        )

    def test_all_healthy_sample_is_confirmed_healthy(self) -> None:
        samples = [[observation("target-a", True), observation("target-b", True)]]
        self.assertEqual(classify_confirmation(samples, []), "HEALTHY")

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
        self.assertEqual(observed.success_age_minutes, 5)

    def test_old_rerun_completion_cannot_refresh_schedule_liveness(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=12 * 60,
                    completed_minutes_ago=1,
                )
            ]
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "STALE_SUCCESS")
        self.assertEqual(observed.success_age_minutes, 12 * 60)

    def test_future_scheduled_run_timestamp_fails_closed(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=10,
                    status="completed",
                    conclusion="success",
                    created_minutes_ago=-5,
                    completed_minutes_ago=-4,
                )
            ]
        )
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "STALE_SUCCESS")
        self.assertIsNone(observed.success_age_minutes)

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

    def test_malformed_newest_run_cannot_hide_behind_older_green(self) -> None:
        malformed = run(
            run_id=11,
            status="completed",
            conclusion="failure",
            created_minutes_ago=1,
            completed_minutes_ago=0,
        )
        malformed["created_at"] = "MALFORMED"
        older_green = run(
            run_id=10,
            status="completed",
            conclusion="success",
            created_minutes_ago=5,
            completed_minutes_ago=4,
        )
        with self.assertRaises(ContractError):
            self.observe([malformed, older_green])

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

    def test_active_run_cannot_conceal_newer_failed_completed_baseline(self) -> None:
        observed = self.observe(
            [
                run(
                    run_id=13,
                    status="in_progress",
                    conclusion=None,
                    created_minutes_ago=2,
                ),
                run(
                    run_id=12,
                    status="completed",
                    conclusion="failure",
                    created_minutes_ago=5,
                    completed_minutes_ago=4,
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
        self.assertFalse(observed.healthy)
        self.assertEqual(observed.state, "ACTIVE_WITH_FAILED_BASELINE")

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

    class IncidentApi(GitHubApi):
        def __init__(self, items: list[dict[str, Any]], *, incomplete: bool = False):
            self.token = "suppressed"
            self.timeout = 1
            self.items = items
            self.incomplete = incomplete

        def request(
            self,
            method: str,
            path: str,
            payload: Mapping[str, Any] | None = None,
        ) -> Any:
            if path.startswith("/search/issues?"):
                self.assert_request(method, path, payload)
                return {
                    "total_count": len(self.items),
                    "incomplete_results": self.incomplete,
                    "items": self.items,
                }
            if path == ("/repos/szl-holdings/.github/actions/runs/987654/attempts/1"):
                return {
                    "id": 987654,
                    "run_attempt": 1,
                    "event": "schedule",
                    "path": ".github/workflows/estate-deadman.yml",
                    "head_branch": "main",
                    "head_sha": "a" * 40,
                    "status": "completed",
                    "conclusion": "failure",
                    "created_at": stamp(2),
                    "run_started_at": stamp(2),
                    "updated_at": stamp(-1),
                    "repository": {"full_name": "szl-holdings/.github"},
                    "head_repository": {"full_name": "szl-holdings/.github"},
                }
            raise AssertionError((method, path, payload))

        @staticmethod
        def assert_request(
            method: str, path: str, payload: Mapping[str, Any] | None
        ) -> None:
            if method != "GET" or not path.startswith("/search/issues?"):
                raise AssertionError((method, path, payload))

    @staticmethod
    def incident_item(*, login: str = "github-actions[bot]") -> dict[str, Any]:
        return {
            "number": 42,
            "title": "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            "body": issue_body(report()),
            "updated_at": stamp(0),
            "user": {
                "login": login,
                "type": "Bot" if login == "github-actions[bot]" else "User",
            },
        }

    def test_public_exact_title_spoof_cannot_own_the_controller_incident(self) -> None:
        api = self.IncidentApi([self.incident_item(login="untrusted-user")])
        self.assertIsNone(
            api.find_incident(
                "szl-holdings/.github",
                "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            )
        )

    def test_controller_incident_requires_bot_author_and_bound_state(self) -> None:
        api = self.IncidentApi([self.incident_item()])
        incident = api.find_incident(
            "szl-holdings/.github",
            "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
        )
        self.assertIsNotNone(incident)
        assert incident is not None
        self.assertEqual(
            incident["_controller_state"]["controller_repository"],
            "szl-holdings/.github",
        )
        self.assertEqual(incident["_referenced_run_authenticated_at"], stamp(0))

    def test_controller_incident_rejects_wrong_immutable_attempt(self) -> None:
        item = self.incident_item()
        body = item["body"].replace(
            '"controller_run_attempt":1', '"controller_run_attempt":2'
        )
        item["body"] = body
        api = self.IncidentApi([item])
        with self.assertRaises(AssertionError):
            api.find_incident(
                "szl-holdings/.github",
                "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            )

    def test_controller_incident_rejects_future_marker_outside_attempt(self) -> None:
        item = self.incident_item()
        item["body"] = issue_body(report(generated_at=stamp(-10)))
        api = self.IncidentApi([item])
        with self.assertRaises(ContractError):
            api.find_incident(
                "szl-holdings/.github",
                "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            )

    def test_duplicate_controller_incidents_fail_closed(self) -> None:
        api = self.IncidentApi([self.incident_item(), self.incident_item()])
        with self.assertRaises(ContractError):
            api.find_incident(
                "szl-holdings/.github",
                "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            )

    def test_incomplete_incident_search_fails_closed(self) -> None:
        api = self.IncidentApi([], incomplete=True)
        with self.assertRaises(ContractError):
            api.find_incident(
                "szl-holdings/.github",
                "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
            )


class IncidentContractTests(unittest.TestCase):
    def test_issue_body_contains_only_bounded_evidence(self) -> None:
        receipt = report()
        receipt["final_sample"] = [
            {
                "id": "autonomic-public-estate-sre",
                "healthy": False,
                "state": "LATEST_RUN_FAILED",
                "latest_run_id": 123,
                "latest_conclusion": "failure",
                "success_age_minutes": 7,
                "reason": "latest completed scheduled run did not succeed",
            }
        ]
        body = issue_body(receipt)
        self.assertIn("Two independent samples", body)
        self.assertIn("LATEST_RUN_FAILED", body)
        self.assertIn("SZL_ESTATE_DEADMAN_STATE_BEGIN", body)
        self.assertNotIn("password", body.lower())
        self.assertNotIn("authorization", body.lower())
        state = parse_incident_state(body, "szl-holdings/.github")
        self.assertEqual(state["controller_revision"], "a" * 40)

    def test_confirmed_failure_refreshes_marker_consistent_incident_every_cycle(
        self,
    ) -> None:
        class ReconcileApi:
            def __init__(self) -> None:
                self.updated = False
                self.body: str | None = None

            def find_incident(self, repository: str, title: str) -> dict[str, Any]:
                body = issue_body(report(generated_at=stamp(120)))
                return {
                    "number": 42,
                    "updated_at": stamp(1),
                    "_controller_state": parse_incident_state(body, repository),
                    "_referenced_run_authenticated_at": stamp(120),
                }

            def update_issue(
                self,
                repository: str,
                number: int,
                *,
                body: str | None = None,
                state: str | None = None,
            ) -> dict[str, Any]:
                self.updated = True
                self.body = body
                return {"number": number}

            def issue(self, repository: str, number: int) -> dict[str, Any]:
                return {
                    "number": number,
                    "title": "[ESTATE-DEADMAN] Critical scheduled control plane degraded",
                    "state": "open",
                    "body": self.body,
                }

        api = ReconcileApi()
        result = reconcile_incident(api, policy(), report(), NOW)
        self.assertEqual(result["action"], "refreshed")
        self.assertTrue(api.updated)

    def test_workflow_permissions_are_exact_and_structural(self) -> None:
        source = (ROOT / ".github" / "workflows" / "estate-deadman.yml").read_text(
            encoding="utf-8"
        )
        result = validate_workflow_source(source)
        self.assertEqual(
            result["permissions"],
            {"actions": "read", "contents": "read", "issues": "write"},
        )
        attacks = (
            source.replace("  issues: write\n", "  issues: write\n  id-token: write\n"),
            source.replace("  issues: write", "  issues: read\n  # issues: write"),
            source.replace(
                "  supervise:\n",
                "  supervise:\n    permissions: write-all\n",
            ),
            source.replace(
                "  supervise:\n",
                '  supervise:\n    "permis\\u0073ions": write-all\n',
            ),
            source.replace(
                "  supervise:\n",
                "  supervise:\n    ? permissions\n    : write-all\n",
            ),
            source.replace(
                "  supervise:\n",
                "  supervise:\n    !!str permissions: write-all\n",
            ),
            source.replace(
                "  supervise:\n    name: Observe, confirm, incident, and attest\n",
                "  supervise:\n    &p permissions: write-all\n    name:\n      *p\n",
            ),
            source.replace(
                "jobs:\n",
                "x-authority: &widened\n  permissions: write-all\n\njobs:\n",
            ).replace(
                "  supervise:\n",
                "  supervise:\n    <<: *widened\n",
            ),
            source.replace(
                '    - cron: "7,22,37,52 * * * *"',
                '    - cron: "0 0 1 1 *"\n    # cron: "7,22,37,52 * * * *"',
            ),
            source.replace(
                "  supervise:\n",
                '  supervise:\n    "permissions": {contents: "write", issues: "write", id-token: "write"}\n',
            ),
            source.replace(
                "  supervise:\n",
                "  supervise:\n    permissions:\n      statuses: write\n",
            ),
            source.replace(
                "      - name: Set up Python\n",
                "      - name: Attacker checkout\n"
                "        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
                "        with:\n"
                "          repository: untrusted/example\n"
                "          ref: refs/heads/main\n\n"
                "      - name: Set up Python\n",
            ),
            source.replace(
                "      - name: Set up Python\n",
                "      - name: Exfiltrate write token\n"
                "        env:\n"
                "          TOKEN: ${{ github.token }}\n"
                '        run: curl -X POST -H "Authorization: Bearer $TOKEN" https://api.github.com/repos/example/issues\n\n'
                "      - name: Set up Python\n",
            ),
            source.replace(
                "          ref: ${{ github.sha }}",
                "          repository: untrusted/example\n"
                "          ref: refs/heads/attacker\n"
                "          # ref: ${{ github.sha }}",
            ),
            source.replace(
                '          repositories: ".github,szl-org-health,a11oy"',
                '          repositories: ".github,szl-org-health,a11oy,attacker"',
            ),
            source.replace(
                "          permission-actions: read",
                "          permission-actions: write",
            ),
            source.replace(
                "          ESTATE_READ_TOKEN: ${{ steps.reader.outputs.token }}",
                "          ESTATE_READ_TOKEN: ${{ github.token }}",
            ),
            source.replace(
                "      - name: Require exact schedule authority\n",
                "      - name: Require exact schedule authority\n        if: false\n",
            ),
            source.replace(
                "      - name: Require exact schedule authority\n",
                '      - name: Require exact schedule authority\n        "i\\u0066": false\n',
            ),
            source.replace(
                "      - name: Re-prove dead-man contracts before live observation\n"
                "        env:\n"
                '          PYTHONDONTWRITEBYTECODE: "1"\n'
                "        run: |",
                "      - name: Re-prove dead-man contracts before live observation\n"
                "        env:\n"
                '          PYTHONDONTWRITEBYTECODE: "1"\n'
                "        run: true\n"
                "        # run: |",
            ),
            source.replace(
                '          test "$(git status --porcelain --untracked-files=all)" = ""',
                '          # test "$(git status --porcelain --untracked-files=all)" = ""',
            ),
            source.replace(
                "      - name: Require a confirmed healthy control plane\n",
                "      - name: Require a confirmed healthy control plane\n        continue-on-error: true\n",
            ),
            source.replace(
                "      - name: Require a confirmed healthy control plane\n",
                '      - name: Require a confirmed healthy control plane\n        "continue-on-err\\u006fr": true\n',
            ),
            source.replace(
                "          jq -e '.confirmed_healthy == true' reports/estate-deadman.json >/dev/null",
                "          true\n          # jq -e '.confirmed_healthy == true' reports/estate-deadman.json >/dev/null",
            ),
            source.replace(
                '          test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
                '          # test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
            ),
        )
        for attack_index, attack in enumerate(attacks):
            self.assertNotEqual(attack, source, f"attack {attack_index} was a no-op")
            with self.subTest(attack_index=attack_index, attack=attack[:120]):
                with self.assertRaises(WorkflowContractError):
                    validate_workflow_source(attack)

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

    def test_main_reports_secondary_receipt_write_failure_without_messages(
        self,
    ) -> None:
        stderr = io.StringIO()
        with (
            patch.object(
                estate_deadman,
                "load_policy",
                side_effect=RuntimeError("primary-secret-message"),
            ),
            patch.object(
                estate_deadman,
                "write_json_atomic",
                side_effect=OSError("secondary-secret-message"),
            ),
            redirect_stderr(stderr),
        ):
            result = estate_deadman.main(
                ["--policy", "ignored.json", "--output", "blocked.json"]
            )

        rendered = stderr.getvalue()
        self.assertEqual(result, 1)
        self.assertIn('"error_kind": "RUNTIMEERROR"', rendered)
        self.assertIn('"failure_write_error_kind": "OSERROR"', rendered)
        self.assertNotIn("primary-secret-message", rendered)
        self.assertNotIn("secondary-secret-message", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
