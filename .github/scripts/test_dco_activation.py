#!/usr/bin/env python3
"""Static contract for the native and reusable trusted DCO producers."""

from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parent
WORKFLOWS = SCRIPTS.parent / "workflows"
GOVERNANCE = SCRIPTS.parents[1] / ".governance"


class DcoActivationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.native = (WORKFLOWS / "dco.yml").read_text(encoding="utf-8")
        self.reusable = (WORKFLOWS / "reusable-dco.yml").read_text(encoding="utf-8")
        self.attestor = (WORKFLOWS / "attest-and-approve.yml").read_text(
            encoding="utf-8"
        )
        self.solo_policy = (GOVERNANCE / "solo-operator-policy.md").read_text(
            encoding="utf-8"
        )
        self.checker = (SCRIPTS / "dco_check.py").read_text(encoding="utf-8")
        self.forge_verifier = (SCRIPTS / "verify_forge9_governance.py").read_text(
            encoding="utf-8"
        )
        self.forge_runner = (SCRIPTS / "run_forge9_gate.py").read_text(
            encoding="utf-8"
        )

    def test_native_workflow_preserves_all_governed_event_gates(self) -> None:
        for marker in (
            "name: Native DCO enforcement",
            "pull_request" + "_target:",
            "- main",
            "- 'release/*'",
            "types: [opened, synchronize, reopened, ready_for_review, edited, closed]",
            "merge_" + "group:",
            "types: [checks_requested]",
            "Reconcile surviving DCO status",
            "github.event.before",
            "AFFECTED_HEAD_SHA:",
            "reconcile-candidate",
            "reconcile-base",
            "reconcile-trusted",
            "dco-reconcile-event.json",
            "Finalize pull-request DCO failure",
            "Finalize reconciliation failure",
            "persist-credentials: false",
            "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
            "EXPECTED_BASE_SHA:",
            "EXPECTED_HEAD_SHA:",
            "statuses: write",
            "statuses/$EXPECTED_HEAD_SHA",
            '-f context="DCO sign-off check"',
            "github.workflow_sha",
            "--paginate --slurp",
            "trusted/.github/scripts/dco_check.py",
            "Run strict real-commit DCO self-tests",
            "native-dco-compatibility:",
            "name: DCO sign-off check",
            "needs: dco",
            "if: always() && github.event_name != 'pull_request_target'",
            "NATIVE_DCO_RESULT: ${{ needs.dco.result }}",
            'test "$NATIVE_DCO_RESULT" = "success"',
        ):
            self.assertIn(marker, self.native)
        self.assertNotIn("\n  pull_request:\n", self.native)
        self.assertNotIn("workflow_" + "dispatch:", self.native)

    def test_reusable_workflow_is_exact_and_secretless(self) -> None:
        for marker in (
            "name: Reusable DCO validation",
            "repository: ${{ job.workflow_repository }}",
            "ref: ${{ job.workflow_sha }}",
            "GH_TOKEN: ${{ github.token }}",
            "GITHUB_TOKEN: ${{ github.token }}",
            "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
            "refs/pull/${{ github.event.pull_request.number }}/head",
            "persist-credentials: false",
            "trusted-dco/.github/scripts/dco_check.py",
            "Run strict real-commit DCO self-tests",
            "reusable-dco-compatibility:",
            "name: DCO sign-off",
            "needs: reusable-dco",
            "REUSABLE_DCO_RESULT: ${{ needs.reusable-dco.result }}",
            'test "$REUSABLE_DCO_RESULT" = "success"',
        ):
            self.assertIn(marker, self.reusable)
        self.assertNotIn("secrets.", self.reusable)
        self.assertNotIn("secrets: inherit", self.reusable)
        self.assertNotIn("grep ", self.reusable)
        self.assertEqual(self.reusable.count("name: DCO sign-off\n"), 1)
        self.assertNotIn("continue-on-error", self.reusable)

    def test_source_namespaces_are_distinct_and_legacy_status_survives(self) -> None:
        self.assertNotEqual("Native DCO enforcement", "Reusable DCO validation")
        self.assertIn("name: Native DCO enforcement", self.native)
        self.assertNotIn("name: Reusable DCO validation", self.native)
        self.assertIn("name: Reusable DCO validation", self.reusable)
        self.assertNotIn("name: Native DCO enforcement", self.reusable)
        self.assertIn('context="DCO sign-off check"', self.native)
        self.assertEqual(self.native.count("name: DCO sign-off check\n"), 1)
        self.assertNotIn("continue-on-error", self.native)

    def test_physical_parser_and_bounded_event_contract_are_consumed(self) -> None:
        for marker in (
            "PATCH_DIVIDER_PATTERN",
            "TRAILER_TOKEN_PATTERN",
            "valid_dco_identities",
            "MAX_PULL_REQUEST_COMMITS = 250",
            'event_name in {"pull_request_target", "pull_request"}',
            'group.get("base_sha")',
            'group.get("head_sha")',
            '"merge-base", "--is-ancestor"',
        ):
            self.assertIn(marker, self.checker)

    def test_committed_ruleset_fixtures_are_not_live_activation_evidence(self) -> None:
        production_sources = self.native + self.reusable + self.checker
        self.assertNotIn(".governance/ruleset", production_sources)
        self.assertNotIn("ruleset-release.json", production_sources)
        self.assertNotIn("integration_id", production_sources)

    def test_attestor_accepts_only_canonical_solo_operator_confirmations(self) -> None:
        marker = (
            "^Solo-Operator-Authorization:[[:space:]]*"
            "(confirmed|CONFIRMED)[[:space:]]*$"
        )
        self.assertIn(f"awk '/{marker}/", self.attestor)
        self.assertIn(f'"{marker}"', self.forge_verifier)
        self.assertIn('AUTHORIZATION_COUNT="$(', self.attestor)
        self.assertIn("{ count += 1 } END { print count + 0 }", self.attestor)
        self.assertIn('[ "$AUTHORIZATION_COUNT" -eq 1 ]', self.attestor)
        self.assertIn(
            "P5 governance change requires exactly one canonical "
            "solo-operator authorization",
            self.attestor,
        )
        self.assertNotIn(
            "Solo-Operator-Authorization:[[:space:]]*confirmed'",
            self.attestor,
        )

    def test_solo_operator_policy_documents_both_canonical_confirmations(self) -> None:
        expected_markers = {
            "Solo-Operator-Authorization: confirmed",
            "Solo-Operator-Authorization: CONFIRMED",
        }
        actual_markers = {
            line.strip()
            for line in self.solo_policy.splitlines()
            if line.startswith("Solo-Operator-Authorization:")
        }
        self.assertEqual(actual_markers, expected_markers)
        self.assertIn("must include exactly one", self.solo_policy)
        self.assertIn(
            "The authorization value is case-sensitive. Mixed-case values, "
            "prefixes,\nsuffixes, and additional text are invalid.",
            self.solo_policy,
        )

    def test_forge9_requires_strict_behavior_not_retired_implementation(self) -> None:
        self.assertNotIn('"interpret-trailers", "--parse"', self.forge_verifier)
        for marker in (
            "PATCH_DIVIDER_PATTERN =",
            "TRAILER_TOKEN_PATTERN =",
            "def _is_patch_divider(",
            "def valid_dco_identities(",
            "Signed-off-by does not exactly match the commit author",
            "class RealCommitPhysicalMessageTests",
            "test_git_density_admission_matches_interpret_trailers",
            "name: Reusable DCO validation",
            "repository: ${{ job.workflow_repository }}",
            "ref: ${{ job.workflow_sha }}",
        ):
            self.assertIn(marker, self.forge_verifier)
        for suite in (
            ".github/scripts/test_dco_check.py",
            ".github/scripts/test_dco_events.py",
            ".github/scripts/test_dco_activation.py",
        ):
            self.assertIn(suite, self.forge_runner)


if __name__ == "__main__":
    unittest.main()
