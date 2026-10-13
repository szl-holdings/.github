#!/usr/bin/env python3
"""Source contract for the protected merge-queue enqueue controller."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/merge-queue-enqueue.yml"


class MergeQueueEnqueueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_only_from_trusted_default_branch_gate_completion(self) -> None:
        required = (
            "workflow_run:",
            "FORGE-9 gates",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.event == 'pull_request'",
            "ref: ${{ github.event.repository.default_branch }}",
            "Checkout trusted controller source",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)
        self.assertNotRegex(self.source, re.compile(r"^\s+pull_request:\s*$", re.M))
        self.assertNotIn("github.event.pull_request.head.sha", self.source)

    def test_write_token_never_reaches_checkout_or_contract_test(self) -> None:
        secret = "GH_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}"
        self.assertEqual(self.source.count(secret), 1)
        secret_offset = self.source.index(secret)
        self.assertGreater(secret_offset, self.source.index("Checkout trusted controller source"))
        self.assertGreater(secret_offset, self.source.index("Verify the enqueue-only source contract"))
        self.assertNotIn(secret, self.source.split("steps:", 1)[0])

    def test_uses_only_the_queue_mutation(self) -> None:
        self.assertIn("enqueuePullRequest", self.source)
        self.assertIn("dequeuePullRequest", self.source)
        self.assertIn("expectedHeadOid", self.source)
        forbidden = (
            "mergePullRequest",
            "gh pr merge",
            "--admin",
            "/merge\"",
            "updatePullRequestBranch",
            "updateRef",
            "force=true",
        )
        for marker in forbidden:
            self.assertNotIn(marker, self.source, marker)

    def test_requires_exact_generation_head_body_and_app_provenance(self) -> None:
        required = (
            "SOURCE_GATE_RUN_ID",
            "LATEST_GATE_RUN_ID",
            "PR body sha256:",
            "Gate run:",
            "CURRENT_BODY_SHA256",
            "GRAPH_BODY_SHA256",
            "CURRENT_BASE_REF",
            "CURRENT_BASE_SHA",
            "baseRefName",
            "ref(qualifiedName:$base){target{oid}}",
            ".data.repository.ref.target.oid",
            "Base: $CURRENT_BASE_REF@$CURRENT_BASE_SHA",
            "--paginate --slurp",
            "attestation/qillqaq",
            "qillqaq-attestor[bot]",
            '.creator.type == "Bot"',
            '.user.type == "Bot"',
            "commit_id == $head",
            "CURRENT_HEAD",
            "EXPECTED_HEAD",
            "headRefOid",
            "isDraft",
            "GRAPH_STATE",
            "CURRENT_STATE",
            "'OPEN'",
            "queue-postcheck.json",
            "queue-after-dequeue.json",
            "queue absence verified",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)

    def test_draft_deferral_is_complete_and_fail_closed(self) -> None:
        guard = re.compile(
            r'if \[ "\$CURRENT_DRAFT" = \'true\' \]; then\s+'
            r'echo "Gate run .* queue request deferred"\s+'
            r'exit 0\s+fi\s+'
            r'\[ "\$CURRENT_DRAFT" = \'false\' \]',
            re.S,
        )
        self.assertRegex(self.source, guard)

    def test_is_same_repository_only_and_does_not_expose_token(self) -> None:
        required = (
            '.head.repo.full_name == $repository',
            "trusted_default_branch_controller",
            "direct_merge_attempted",
            "bypass_used",
            "token_value_recorded",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)
        self.assertNotIn("set -x", self.source)
        self.assertNotIn("echo $GH_TOKEN", self.source)
        self.assertNotIn('echo "$GH_TOKEN"', self.source)

    def test_receipt_is_retained_and_never_claims_a_merge(self) -> None:
        self.assertIn("retention-days: 90", self.source)
        self.assertIn("merge-queue-enqueue-${{ github.run_id }}", self.source)
        self.assertIn("merge_performed", self.source)
        self.assertIn("false", self.source)

    # Acceptance case 9: re-verify immediately before enqueue, fail on drift,
    # and keep the existing queue cleanup/readback behaviour.
    def test_case09_admission_is_reverified_immediately_before_the_queue_mutation(self) -> None:
        attested = self.source.index("attested=1")
        final = self.source.index('FINAL_HEAD="$(jq -r .head.sha')
        before = self.source.index("queue-before.json")
        invocation = "python3 -I .github/scripts/release_admission_verifier.py"
        verifier = self.source.index(invocation)
        mutation = self.source.index("enqueuePullRequest")
        self.assertLess(attested, final)
        self.assertLess(final, before)
        self.assertLess(before, verifier)
        self.assertLess(verifier, mutation)
        self.assertEqual(self.source.count(invocation), 1)
        fragment = self.source[verifier:mutation]
        for marker in (
            "--phase enqueue",
            '--head-sha "$EXPECTED_HEAD"',
            '--base-sha "$CURRENT_BASE_SHA"',
            '--gate-run-id "$SOURCE_GATE_RUN_ID"',
            '--body-sha256 "$CURRENT_BODY_SHA256"',
            "Admission evidence: $ADMISSION_FINGERPRINT",
            "admission evidence changed between attestation and enqueue",
        ):
            self.assertIn(marker, fragment, marker)
        self.assertNotIn("|| true", fragment)
        self.assertNotIn("continue-on-error", self.source)
        # The existing post-enqueue drift check and verified dequeue remain.
        for marker in ("queue-postcheck.json", "dequeuePullRequest", "queue absence verified"):
            self.assertGreater(self.source.index(marker), mutation, marker)

    def test_case09_verifier_never_receives_the_write_token(self) -> None:
        self.assertIn("ADMISSION_READ_TOKEN: ${{ github.token }}", self.source)
        self.assertIn("env -u GH_TOKEN python3 -I .github/scripts/release_admission_verifier.py", self.source)
        self.assertIn("--token-env ADMISSION_READ_TOKEN", self.source)
        self.assertIn("admission_rechecked_immediately_before_enqueue: true", self.source)
        # The controller self-tests the verifier contract from its exact
        # trusted bytes before the write token exists in any step.
        contract = self.source.index("python .github/scripts/test_release_admission_verifier.py")
        self.assertGreater(contract, self.source.index("Verify the enqueue-only source contract"))
        self.assertLess(contract, self.source.index("GH_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}"))


class PreEnqueueAdmissionExecutionTests(unittest.TestCase):
    """Execute the real pre-enqueue fragment with stubbed verifier and GitHub reads."""

    @classmethod
    def setUpClass(cls) -> None:
        for executable in ("bash", "jq", "env"):
            if shutil.which(executable) is None:
                raise RuntimeError(f"pre-enqueue execution tests require {executable}")
        source = WORKFLOW.read_text(encoding="utf-8")
        start = source.index("          # Re-run the shared admission verifier")
        end = source.index('          if [ -n "$QUEUE_ENTRY" ]; then', start)
        cls.script = ("set -euo pipefail\n" + textwrap.dedent(source[start:end])
                      + "echo REACHED_ENQUEUE_MUTATION\n")

    def run_fragment(self, *, decision: str, code: int, fingerprint: str | None,
                     review_body: str) -> tuple[subprocess.CompletedProcess[str], dict[str, str], list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            (temporary / "reports/merge-queue-enqueue").mkdir(parents=True)
            stub = temporary / "bin"
            stub.mkdir()
            (stub / "python3").write_text(
                "#!/usr/bin/env bash\n"
                'env > "$STUB_ENV"\n'
                'out=""\n'
                'while [ $# -gt 0 ]; do if [ "$1" = "--output" ]; then out="$2"; fi; shift; done\n'
                'printf "%s" "$STUB_RESULT" > "$out"\n'
                'exit "$STUB_CODE"\n', encoding="utf-8")
            (stub / "gh").write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$STUB_CALLS"\n'
                'case "$*" in *"/reviews?per_page=100 --paginate --slurp"*) printf "%s" "$STUB_REVIEWS";; '
                '*) echo "unexpected provider request" >&2; exit 12;; esac\n', encoding="utf-8")
            for name in ("python3", "gh"):
                (stub / name).chmod(0o755)
            result = {"decision": decision, "reasons": ["X: y"], "evidence_fingerprint": fingerprint}
            reviews = [[{"user": {"login": "qillqaq-attestor[bot]", "type": "Bot"}, "state": "APPROVED",
                         "commit_id": "a" * 40, "body": review_body}]]
            environment = os.environ.copy()
            environment.update({
                "PATH": str(stub) + os.pathsep + environment["PATH"],
                "GH_TOKEN": "write-token-must-not-reach-verifier",
                "ADMISSION_READ_TOKEN": "read-token",
                "REPOSITORY": "szl-holdings/.github", "EXPECTED_HEAD": "a" * 40, "PR": "7",
                "CURRENT_BASE_REF": "main", "CURRENT_BASE_SHA": "b" * 40,
                "SOURCE_GATE_RUN_ID": "5001", "CURRENT_BODY_SHA256": "9" * 64, "QUEUE_ENTRY": "",
                "STUB_RESULT": json.dumps(result), "STUB_CODE": str(code),
                "STUB_ENV": str(temporary / "env.txt"), "STUB_CALLS": str(temporary / "calls.txt"),
                "STUB_REVIEWS": json.dumps(reviews),
            })
            completed = subprocess.run(["bash", "-c", self.script], cwd=temporary, env=environment,
                                       text=True, capture_output=True, check=False)
            seen = {}
            if (temporary / "env.txt").exists():
                for line in (temporary / "env.txt").read_text(encoding="utf-8").splitlines():
                    key, _, value = line.partition("=")
                    seen[key] = value
            calls = ((temporary / "calls.txt").read_text(encoding="utf-8").splitlines()
                     if (temporary / "calls.txt").exists() else [])
            return completed, seen, calls

    def test_matching_admission_reaches_the_mutation_without_the_write_token(self) -> None:
        fingerprint = "sha256:" + "4" * 64
        result, seen, _ = self.run_fragment(decision="ADMIT", code=0, fingerprint=fingerprint,
                                            review_body=f"ATTESTED. Admission evidence: {fingerprint}")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("REACHED_ENQUEUE_MUTATION", result.stdout)
        self.assertNotIn("GH_TOKEN", seen)
        self.assertEqual(seen.get("ADMISSION_READ_TOKEN"), "read-token")

    def test_hold_block_or_drifted_evidence_stops_before_the_mutation(self) -> None:
        fingerprint = "sha256:" + "4" * 64
        for label, arguments in (
            ("hold", dict(decision="HOLD", code=3, fingerprint=None, review_body="x")),
            ("block", dict(decision="BLOCK", code=2, fingerprint=None, review_body="x")),
            ("lying exit", dict(decision="HOLD", code=0, fingerprint=fingerprint,
                                review_body=f"Admission evidence: {fingerprint}")),
            ("drifted since review", dict(decision="ADMIT", code=0, fingerprint=fingerprint,
                                          review_body="Admission evidence: sha256:" + "5" * 64)),
            ("malformed fingerprint", dict(decision="ADMIT", code=0, fingerprint="sha256:zz",
                                           review_body="Admission evidence: sha256:zz")),
        ):
            with self.subTest(label):
                result, _, _ = self.run_fragment(**arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("REACHED_ENQUEUE_MUTATION", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
