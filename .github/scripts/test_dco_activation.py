#!/usr/bin/env python3
"""Static contract for native provenance compatibility and reusable DCO."""

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

    def step_block(self, workflow: str, start: str, end: str) -> str:
        start_marker = f"      - name: {start}\n"
        end_marker = f"      - name: {end}\n"
        self.assertEqual(workflow.count(start_marker), 1)
        block = workflow.split(start_marker, 1)[1]
        self.assertIn(end_marker, block)
        return block.split(end_marker, 1)[0]

    def assert_source_is_bound_to_event_base(self, block: str) -> None:
        for marker in (
            "EXPECTED_BASE_REF: ${{ github.event.pull_request.base.ref }}",
            "EXPECTED_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
            '[[ "$EXPECTED_BASE_REF" == "main" \\',
            '|| "$EXPECTED_BASE_REF" =~ ^release/[^/]+$ ]]',
            ".github/workflows/dco.yml@refs/heads/$EXPECTED_BASE_REF",
            "git/ref/heads/$EXPECTED_BASE_REF",
            'test "$protected_sha" = "$EXPECTED_BASE_SHA"',
        ):
            self.assertIn(marker, block)
        self.assertNotIn('.github/workflows/dco.yml@refs/heads/main"', block)
        self.assertNotIn("git/ref/heads/main", block)

    def assert_candidate_workflow_guard(self, block: str) -> None:
        markers = (
            "declared_file_count=",
            "pulls/$EXPECTED_PR_NUMBER/files?per_page=100",
            "listed_file_count=",
            'test "$listed_file_count" -eq "$declared_file_count"',
            'test "$listed_file_count" -le 3000',
            'startswith(".github/workflows/")',
            'test "$candidate_workflows" -eq 0',
        )
        positions = []
        for marker in markers:
            self.assertIn(marker, block)
            positions.append(block.index(marker))
        self.assertEqual(positions, sorted(positions))

    def assert_cross_base_reconciliation_fails_closed(self, block: str) -> None:
        markers = (
            "TRIGGER_BASE_REF: ${{ github.event.pull_request.base.ref }}",
            "TRIGGER_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
            'if [[ "$base_ref" != "$TRIGGER_BASE_REF" \\',
            '|| "$base_sha" != "$TRIGGER_BASE_SHA" ]]; then',
            'description="Surviving PR base differs from trigger base"',
            'echo "published=true" >>"$GITHUB_OUTPUT"',
            "exit 1",
        )
        for marker in markers:
            self.assertIn(marker, block)
        self.assertLess(
            block.index('if [[ "$base_ref" != "$TRIGGER_BASE_REF"'),
            block.index('echo "reconcile=true"'),
        )
        guard_start = block.index('if [[ "$base_ref" != "$TRIGGER_BASE_REF"')
        guard_end = block.index('echo "reconcile=true"')
        self.assertIn("exit 1", block[guard_start:guard_end])

    def test_native_workflow_preserves_all_governed_event_gates(self) -> None:
        for marker in (
            "name: Solo-builder provenance compatibility",
            "pull_request" + "_target:",
            "- main",
            "- 'release/*'",
            "- synchronize",
            "- ready_for_review",
            "- converted_to_draft",
            "- closed",
            "merge_" + "group:",
            "types: [checks_requested]",
            "permissions: {}",
            "pull-request-provenance:",
            "merge-group-provenance:",
            "Reconcile surviving provenance status",
            "github.event.before",
            "AFFECTED_HEAD_SHA:",
            "Finalize pull-request provenance failure",
            "Finalize reconciliation failure",
            "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
            "EXPECTED_BASE_SHA:",
            "EXPECTED_HEAD_SHA:",
            "statuses: write",
            "statuses/$EXPECTED_HEAD_SHA",
            '-f context="DCO sign-off check"',
            "github.workflow_sha",
            "github.workflow_ref",
            "source_workflow_blob",
            "protected_workflow_blob",
            ".github/workflows/dco.yml@refs/heads/$EXPECTED_BASE_REF",
            "--paginate --slurp",
            'startswith(".github/workflows/")',
            "git/ref/heads/$EXPECTED_BASE_REF",
            "merge_base_commit.sha == $base",
            "legacy-dco-compatibility:",
            "name: DCO sign-off check",
            "needs: merge-group-provenance",
            "if: always() && github.event_name == 'merge_group'",
            "PROVENANCE_RESULT: ${{ needs.merge-group-provenance.result }}",
            'test "$PROVENANCE_RESULT" = "success"',
        ):
            self.assertIn(marker, self.native)
        self.assertEqual(self.native.count("statuses: write"), 2)
        self.assertEqual(self.native.count("candidate_workflows"), 4)
        self.assertNotIn(
            '.github/workflows/dco.yml@refs/heads/main"', self.native
        )
        merge_job = self.native.split("  merge-group-provenance:\n", 1)[1].split(
            "  legacy-dco-compatibility:\n", 1
        )[0]
        self.assertIn("contents: read", merge_job)
        self.assertNotIn("statuses: write", merge_job)
        self.assertNotIn("pull-requests: read", merge_job)
        self.assertNotIn("\n  pull_request:\n", self.native)
        self.assertNotIn("\n  push:\n", self.native)
        self.assertNotIn("workflow_" + "dispatch:", self.native)
        self.assertNotRegex(self.native, r"(?m)^\s*(?:-\s*)?uses:\s")
        self.assertNotIn("actions/checkout", self.native)
        self.assertNotIn("persist-credentials", self.native)
        self.assertNotIn("GITHUB_WORKSPACE", self.native)
        self.assertNotIn(".github/scripts/", self.native)
        self.assertNotIn("dco_check.py", self.native)
        self.assertNotIn("Signed-off-by", self.native)
        self.assertNotIn("secrets.", self.native)
        self.assertNotIn("contents: write", self.native)
        self.assertNotIn("id-token:", self.native)

    def test_pr_and_reconciliation_sources_follow_the_exact_target_base(self) -> None:
        blocks = (
            self.step_block(
                self.native,
                "Assert exact protected workflow source",
                "Validate exact live pull-request provenance",
            ),
            self.step_block(
                self.native,
                "Assert exact protected reconciliation source",
                "Resolve the surviving governed pull request",
            ),
        )
        for block in blocks:
            self.assert_source_is_bound_to_event_base(block)
            mutations = (
                block.replace(
                    "EXPECTED_BASE_REF: ${{ github.event.pull_request.base.ref }}",
                    "EXPECTED_BASE_REF: main",
                    1,
                ),
                block.replace(
                    "@refs/heads/$EXPECTED_BASE_REF",
                    "@refs/heads/main",
                    1,
                ),
                block.replace(
                    "git/ref/heads/$EXPECTED_BASE_REF",
                    "git/ref/heads/main",
                    1,
                ),
                block.replace(
                    'test "$protected_sha" = "$EXPECTED_BASE_SHA"',
                    "true",
                    1,
                ),
            )
            for mutated in mutations:
                with self.assertRaises(AssertionError):
                    self.assert_source_is_bound_to_event_base(mutated)

    def test_reconciliation_rechecks_candidate_files_and_rejects_cross_base(self) -> None:
        revalidation = self.step_block(
            self.native,
            "Revalidate the surviving exact head",
            "Publish successful reconciled compatibility status",
        )
        self.assert_candidate_workflow_guard(revalidation)
        candidate_mutations = (
            revalidation.replace(
                'test "$listed_file_count" -eq "$declared_file_count"',
                "true",
                1,
            ),
            revalidation.replace(
                'startswith(".github/workflows/")',
                'startswith(".github/actions/")',
                1,
            ),
            revalidation.replace(
                'test "$candidate_workflows" -eq 0',
                'test "$candidate_workflows" -ge 0',
                1,
            ),
        )
        for mutated in candidate_mutations:
            with self.assertRaises(AssertionError):
                self.assert_candidate_workflow_guard(mutated)

        resolution = self.step_block(
            self.native,
            "Resolve the surviving governed pull request",
            "Revalidate the surviving exact head",
        )
        self.assert_cross_base_reconciliation_fails_closed(resolution)
        cross_base_mutations = {
            "main-to-release": resolution.replace(
                'if [[ "$base_ref" != "$TRIGGER_BASE_REF" \\',
                "if [[ false \\",
                1,
            ),
            "release-to-main": resolution.replace(
                '|| "$base_sha" != "$TRIGGER_BASE_SHA" ]]; then',
                "]]; then",
                1,
            ),
            "fail-open": resolution.replace(
                'echo "published=true" >>"$GITHUB_OUTPUT"\n'
                "            exit 1\n"
                "          fi\n"
                "          {\n",
                'echo "published=true" >>"$GITHUB_OUTPUT"\n'
                "            true\n"
                "          fi\n"
                "          {\n",
                1,
            ),
        }
        for label, mutated in cross_base_mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    self.assert_cross_base_reconciliation_fails_closed(mutated)

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
        self.assertNotEqual(
            "Solo-builder provenance compatibility", "Reusable DCO validation"
        )
        self.assertIn("name: Solo-builder provenance compatibility", self.native)
        self.assertNotIn("name: Reusable DCO validation", self.native)
        self.assertIn("name: Reusable DCO validation", self.reusable)
        self.assertNotIn("name: Solo-builder provenance compatibility", self.reusable)
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
