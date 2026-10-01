#!/usr/bin/env python3
"""Execute the attestor's queue precondition against offline GitHub responses."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
