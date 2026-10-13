#!/usr/bin/env python3
"""Execute the attestor's queue precondition against offline GitHub responses."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
# The shared verifier's acceptance-case suite runs from this existing entry
# point (Tests workflow) as well as standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_release_admission_verifier import (  # noqa: E402,F401
    AcceptanceCaseTests,
    CheckerCompatibilityTests,
    CommandLineTests,
    RetainedReceiptTests,
)
WORKFLOW = ROOT / ".github/workflows/attest-and-approve.yml"
GH_STUB = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

fixture = json.loads(Path(os.environ['QUEUE_FIXTURE']).read_text())
args = sys.argv[1:]
with Path(os.environ['QUEUE_CALLS']).open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
route = next((arg for arg in args if arg.startswith('repos/')), '')
if route.endswith('/rulesets?per_page=100'):
    for ruleset in fixture['rulesets']:
        print(ruleset['id'])
elif '/rulesets/' in route:
    ruleset_id = int(route.rsplit('/', 1)[1])
    print(json.dumps(next(row for row in fixture['rulesets'] if row['id'] == ruleset_id)))
elif '/rules/branches/' in route:
    if route != fixture['expected_route']:
        print('wrong governed branch', file=sys.stderr)
        sys.exit(9)
    if '--paginate' not in args or '--slurp' not in args:
        print('effective rule pages were not collected', file=sys.stderr)
        sys.exit(10)
    if fixture.get('effective_error'):
        print('effective rules unavailable', file=sys.stderr)
        sys.exit(11)
    print(json.dumps(fixture['effective_pages']))
else:
    print('unexpected provider request', file=sys.stderr)
    sys.exit(12)
"""


class AttestationQueuePreconditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for executable in ("bash", "jq", "python3"):
            if shutil.which(executable) is None:
                raise RuntimeError(f"queue precondition tests require {executable}")
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        start = cls.source.index('          gh api "repos/$REPOSITORY/rulesets?per_page=100"')
        end = cls.source.index("          CAN_APPROVE=", start)
        cls.script = "set -euo pipefail\n" + textwrap.dedent(cls.source[start:end])

    def run_precondition(
        self,
        effective_pages: object,
        *,
        enforcement: str = "active",
        branch: str = "main",
        target: str = "branch",
        include: tuple[str, ...] = ("~DEFAULT_BRANCH",),
        exclude: tuple[str, ...] = (),
        bypass: bool = False,
        effective_error: bool = False,
        no_rulesets: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            fixture = {
                "rulesets": [] if no_rulesets else [{
                    "id": 1,
                    "enforcement": enforcement,
                    "target": target,
                    "conditions": {"ref_name": {"include": include, "exclude": exclude}},
                    "bypass_actors": [{"actor_type": "User", "actor_id": 123}] if bypass else [],
                    "rules": [{"type": "merge_queue"}],
                }],
                "expected_route": "repos/szl-holdings/.github/rules/branches/main?per_page=100",
                "effective_pages": effective_pages,
                "effective_error": effective_error,
            }
            (temporary / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
            stub = temporary / "gh"
            stub.write_text(GH_STUB, encoding="utf-8")
            stub.chmod(0o755)
            environment = os.environ.copy()
            environment.update({
                "PATH": str(temporary) + os.pathsep + environment["PATH"],
                "REPOSITORY": "szl-holdings/.github",
                "PR_BASE_REF": branch,
                "RUNNER_TEMP": str(temporary),
                "QUEUE_FIXTURE": str(temporary / "fixture.json"),
                "QUEUE_CALLS": str(temporary / "calls.jsonl"),
            })
            completed = subprocess.run(
                ["bash", "-c", self.script], env=environment,
                text=True, capture_output=True, check=False,
            )
            calls = [json.loads(line) for line in
                     (temporary / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
            return completed, calls

    def test_active_queue_for_main_is_admitted(self) -> None:
        result, _ = self.run_precondition([[{"type": "merge_queue"}]])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_nonqueued_release_attestation_checks_the_main_queue(self) -> None:
        result, calls = self.run_precondition(
            [[{"type": "merge_queue"}]], branch="release/2026-09",
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("repos/szl-holdings/.github/rules/branches/main?per_page=100", calls[-1])

    def test_inactive_and_nonapplicable_listed_queues_are_rejected(self) -> None:
        # The effective endpoint omits each of these listed rulesets. Executing
        # the real workflow fragment catches the previous any-ruleset false pass.
        for parameters in (
            {"enforcement": "disabled"},
            {"enforcement": "evaluate"},
            {"include": ("refs/heads/other",)},
            {"exclude": ("refs/heads/main",)},
            {"target": "tag", "include": ("refs/tags/*",)},
            {"include": ("refs/heads/release/*",)},
        ):
            with self.subTest(parameters=parameters):
                result, _ = self.run_precondition([[]], **parameters)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("no active merge queue rule applies", result.stdout)

    def test_effective_queue_on_later_page_is_admitted(self) -> None:
        result, calls = self.run_precondition([
            [{"type": "required_status_checks"}], [{"type": "merge_queue"}],
        ])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("--paginate", calls[-1])
        self.assertIn("--slurp", calls[-1])

    def test_inherited_effective_queue_is_admitted(self) -> None:
        result, _ = self.run_precondition([[{
            "type": "merge_queue", "ruleset_source_type": "Organization",
            "ruleset_source": "szl-holdings", "ruleset_id": 1,
        }]])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_provider_failure_is_not_queue_evidence(self) -> None:
        result, _ = self.run_precondition([[{"type": "merge_queue"}]], effective_error=True)
        self.assertNotEqual(result.returncode, 0)

    def test_empty_or_malformed_effective_response_is_rejected(self) -> None:
        for response in ([], None, {}, [{"type": "merge_queue"}], [[None]]):
            with self.subTest(response=response):
                result, _ = self.run_precondition(response)
                self.assertNotEqual(result.returncode, 0)

    def test_existing_bypass_and_no_ruleset_guards_still_reject(self) -> None:
        for parameters in ({"bypass": True}, {"no_rulesets": True}):
            with self.subTest(parameters=parameters):
                result, calls = self.run_precondition([[{"type": "merge_queue"}]], **parameters)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any("/rules/branches/" in " ".join(call) for call in calls))

    def test_main_and_release_merge_paths_remain_distinct(self) -> None:
        step = self.source.split("- name: Verify gates and preconditions P1-P7", 1)[1]
        step = step.split("- name: Build and sign the merge BAP", 1)[0]
        self.assertIn("rules/branches/main?per_page=100", step)
        self.assertIn('if [ "$PR_BASE_REF" = "main" ]; then', self.source)
        self.assertIn('[[ "$PR_BASE_REF" == release/* ]]', self.source)
        self.assertIn('gh pr merge "$PR" --repo "$REPOSITORY" --auto --squash', self.source)


def workflow_step(source: str, name: str) -> str:
    start = source.index(f"      - name: {name}\n")
    following = source.find("\n      - name: ", start + 1)
    return source[start:] if following < 0 else source[start:following + 1]


def step_script(source: str, name: str) -> str:
    step = workflow_step(source, name)
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


ADMISSION_STEP = "Verify exact-head admission evidence"
MUTATING_STEPS = (
    "Build and sign the merge BAP",
    "Install Cosign",
    "Sign the merge BAP with Actions OIDC",
    "Upload the signed merge BAP",
    "Revalidate current PR generation before App mutations",
    "Approve as the App and verify the review identity",
    "Publish required App attestation status",
    "Request protected merge after attestation",
)


class AdmissionVerifierWiringTests(unittest.TestCase):
    """Acceptance cases 2-5 and 7-8 at the attestor boundary (source contract)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_verifier_runs_before_every_signing_approval_status_or_merge_step(self) -> None:
        verifier = self.source.index(f"      - name: {ADMISSION_STEP}\n")
        for name in MUTATING_STEPS:
            with self.subTest(step=name):
                step = workflow_step(self.source, name)
                self.assertGreater(self.source.index(step), verifier)
                # Implicit success() gating: a failed verifier stops this step.
                for escape in ("always()", "failure()", "cancelled()", "continue-on-error"):
                    self.assertNotIn(escape, step)
        step = workflow_step(self.source, ADMISSION_STEP)
        self.assertIn("if: steps.subject.outputs.kind == 'merge_group' || steps.subject.outputs.draft == 'false'", step)
        self.assertNotIn("continue-on-error", step)

    def test_verifier_reads_with_the_workflow_token_from_trusted_controller_bytes(self) -> None:
        step = workflow_step(self.source, ADMISSION_STEP)
        self.assertIn("GH_TOKEN: ${{ github.token }}", step)
        self.assertNotIn("app-token", step)
        self.assertIn("python3 -I .github/scripts/release_admission_verifier.py", step)
        checkout = workflow_step(self.source, "Checkout trusted admission verifier source")
        self.assertIn("persist-credentials: false", checkout)
        self.assertNotIn("ref:", checkout)
        self.assertLess(self.source.index(checkout), self.source.index("- name: Mint the independent App token"))
        job_permissions = self.source.split("    permissions:\n", 1)[1].split("    runs-on:", 1)[0]
        writes = sorted(line.split(":")[0].strip() for line in job_permissions.splitlines() if line.strip().endswith(": write"))
        self.assertEqual(writes, ["contents", "id-token", "pull-requests"])
        self.assertIn("checks: read", job_permissions)

    def test_single_page_gate_lookup_is_replaced_by_the_verifier(self) -> None:
        self.assertNotIn("check-runs?filter=latest&per_page=100", self.source)
        self.assertNotIn("REQUIRED=(", self.source)
        self.assertNotIn("check-runs.json", self.source)
        step = workflow_step(self.source, ADMISSION_STEP)
        for marker in ('--event "$SUBJECT_KIND"', '--gate-run-id "$SOURCE_GATE_RUN_ID"',
                       '--head-sha "$HEAD_SHA"', '--base-sha "$PR_BASE_SHA"', "--phase attest"):
            self.assertIn(marker, step, marker)

    def test_bap_and_app_review_bind_the_exact_admission_evidence(self) -> None:
        bap = workflow_step(self.source, "Build and sign the merge BAP")
        self.assertIn('--slurpfile admission "$RUNNER_TEMP/admission.json"', bap)
        self.assertIn("evidence_fingerprint: $admission[0].evidence_fingerprint", bap)
        self.assertIn("receipt_verdict: $admission[0].receipt_verdict", bap)
        approve = workflow_step(self.source, "Approve as the App and verify the review identity")
        self.assertIn("ADMISSION_FINGERPRINT: ${{ steps.admission.outputs.fingerprint }}", approve)
        self.assertIn("Admission evidence: $ADMISSION_FINGERPRINT", approve)
        self.assertIn("contains($admission)", approve)
        self.assertLess(approve.index("ADMISSION_FINGERPRINT\" =~"), approve.index("-X POST"))


class AdmissionVerifierStepExecutionTests(unittest.TestCase):
    """Execute the real attestor verifier step with a stub verifier process."""

    @classmethod
    def setUpClass(cls) -> None:
        for executable in ("bash", "jq"):
            if shutil.which(executable) is None:
                raise RuntimeError(f"admission step execution tests require {executable}")
        cls.script = "set -euo pipefail\n" + step_script(WORKFLOW.read_text(encoding="utf-8"), ADMISSION_STEP)

    def run_step(self, *, kind: str, result: object | None, code: int) -> tuple[subprocess.CompletedProcess[str], str, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            stub = temporary / "bin"
            stub.mkdir()
            (stub / "python3").write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$@" > "$STUB_ARGS"\n'
                'out=""\n'
                'while [ $# -gt 0 ]; do if [ "$1" = "--output" ]; then out="$2"; fi; shift; done\n'
                'if [ -n "$STUB_RESULT" ]; then printf "%s" "$STUB_RESULT" > "$out"; fi\n'
                'exit "$STUB_CODE"\n', encoding="utf-8")
            (stub / "python3").chmod(0o755)
            output = temporary / "github_output"
            output.write_text("", encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "PATH": str(stub) + os.pathsep + environment["PATH"],
                "RUNNER_TEMP": str(temporary), "GITHUB_OUTPUT": str(output),
                "GH_TOKEN": "read-token", "HEAD_SHA": "a" * 40, "SUBJECT_KIND": kind, "PR": "7",
                "PR_HEAD_SHA": "a" * 40, "PR_BASE_REF": "main", "PR_BASE_SHA": "b" * 40,
                "PR_BODY_SHA256": "9" * 64, "SOURCE_GATE_RUN_ID": "5001",
                "REPOSITORY": "szl-holdings/.github",
                "STUB_RESULT": "" if result is None else json.dumps(result), "STUB_CODE": str(code),
                "STUB_ARGS": str(temporary / "args.txt"),
            })
            completed = subprocess.run(["bash", "-c", self.script], env=environment, text=True,
                                       capture_output=True, check=False)
            args = (temporary / "args.txt").read_text(encoding="utf-8").splitlines() \
                if (temporary / "args.txt").exists() else []
            return completed, output.read_text(encoding="utf-8"), args

    def test_admit_publishes_only_a_well_formed_fingerprint(self) -> None:
        fingerprint = "sha256:" + "4" * 64
        completed, output, args = self.run_step(kind="pull_request", code=0, result={
            "decision": "ADMIT", "basis": "CP_EBOM_ALLOW_EXACT_SCOPE", "reasons": [],
            "evidence_fingerprint": fingerprint})
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn(f"fingerprint={fingerprint}", output)
        self.assertIn("--body-sha256", args)
        _, _, merge_args = self.run_step(kind="merge_group", code=0, result={
            "decision": "ADMIT", "basis": "CP_EBOM_ALLOW_EXACT_SCOPE", "reasons": [],
            "evidence_fingerprint": fingerprint})
        self.assertNotIn("--body-sha256", merge_args)
        self.assertEqual(merge_args[merge_args.index("--event") + 1], "merge_group")

    def test_hold_block_missing_or_inconsistent_verdicts_stop_the_attestor(self) -> None:
        fingerprint = "sha256:" + "4" * 64
        for label, code, result in (
            ("hold", 3, {"decision": "HOLD", "basis": "OWNER_DECISION_REQUIRED",
                         "reasons": ["OWNER_DECISION_MISSING"], "evidence_fingerprint": fingerprint}),
            ("block", 2, {"decision": "BLOCK", "basis": "CP_EBOM_DENY", "reasons": ["CP_EBOM_DENY"],
                          "evidence_fingerprint": None}),
            ("no verdict", 1, None),
            ("zero exit but hold", 0, {"decision": "HOLD", "basis": "x", "reasons": [],
                                       "evidence_fingerprint": fingerprint}),
            ("admit without fingerprint", 0, {"decision": "ADMIT", "basis": "x", "reasons": [],
                                              "evidence_fingerprint": None}),
        ):
            with self.subTest(label):
                completed, output, _ = self.run_step(kind="pull_request", code=code, result=result)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("fingerprint=", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
