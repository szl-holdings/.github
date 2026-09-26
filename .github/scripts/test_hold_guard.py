#!/usr/bin/env python3
"""Network-free self-test for the HOLD guard and its workflow contract.

``hold_guard.py`` is the only thing that turns HOLD from prose into a merge
block. A refactor that let it return 0 on an unreadable event, a failed live
read, or a merge-queue group it could not map to a pull request would re-open
the exact hole the 2026-09-25 audit found (every HOLD PR merged green). This
test drives the REAL ``main()`` with the live read stubbed and pins:

  1. every HOLD label spelling and title marker fails (exit 1);
  2. ordinary labels and titles that merely mention "hold" pass (exit 0);
  3. a label added after the triggering event is caught by the live read;
  4. merge-queue events resolve the queued PR from the queue ref;
  5. every unevaluable input fails closed (exit 2), never 0;
  6. the caller and reusable workflows keep the triggers, permissions, exact
     source checkout, and stable ``hold-guard`` job name the ruleset needs.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("hold_guard", HERE / "hold_guard.py")
assert _spec and _spec.loader
hold_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hold_guard)

CALLER = ROOT / ".github" / "workflows" / "hold-guard.yml"
REUSABLE = ROOT / ".github" / "workflows" / "reusable-hold-guard.yml"
REPO = "szl-holdings/.github"
BASE_SHA = "786c24e4" + "0" * 32
# Live titles of the two open HOLD drafts on 2026-09-26 (GraphQL read).
PR_773_TITLE = "docs(frontier): Codex estate upgrade brief + operator [HOLD]"
PR_774_TITLE = (
    "docs(hf): 2026-09-25 GitHub ↔ Hugging Face alignment recapture [HOLD]"
)


def pr_event(number: int, title: str, labels: list[str]) -> dict:
    return {
        "action": "labeled",
        "number": number,
        "pull_request": {
            "number": number,
            "title": title,
            "labels": [{"name": name} for name in labels],
        },
    }


def merge_group_event(number: int, base: str = "main") -> dict:
    return {
        "action": "checks_requested",
        "merge_group": {
            "base_ref": f"refs/heads/{base}",
            "base_sha": BASE_SHA,
            "head_ref": f"refs/heads/gh-readonly-queue/{base}/pr-{number}-{BASE_SHA}",
            "head_sha": "a" * 40,
        },
    }


def live(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in labels],
    }


class Harness:
    """Run the real main() against a temporary event file and a stub fetch."""

    def __init__(self, event_name: str, event: object, live_pull=None, **env):
        self.event_name = event_name
        self.event = event
        self.live_pull = live_pull
        self.env = env
        self.calls: list[tuple] = []

    def fetch(self, api_url, repository, number, token):
        self.calls.append((api_url, repository, number, token))
        if isinstance(self.live_pull, Exception):
            raise self.live_pull
        if self.live_pull is None:
            raise AssertionError("the live read must not be reached")
        return self.live_pull

    def run(self) -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix="hold-guard-test-") as tmp:
            path = Path(tmp) / "event.json"
            if isinstance(self.event, str):
                path.write_text(self.event, encoding="utf-8")
            else:
                path.write_text(json.dumps(self.event), encoding="utf-8")
            environ = {
                "GITHUB_EVENT_NAME": self.event_name,
                "GITHUB_EVENT_PATH": str(path),
                "GITHUB_REPOSITORY": REPO,
                "GITHUB_API_URL": "https://api.github.com",
                "GITHUB_TOKEN": "test-token-not-a-secret",
            }
            environ.update(self.env)
            environ = {k: v for k, v in environ.items() if v is not None}
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = hold_guard.main([], environ, fetch=self.fetch)
        return code, out.getvalue() + err.getvalue()


class MarkerTests(unittest.TestCase):
    def test_every_hold_label_spelling_is_held(self) -> None:
        for name in (
            "hold",
            "HOLD",
            "Hold",
            " hold ",
            "hold-for-owner",
            "hold for owner",
            "HOLD_FOR_OWNER",
            "do-not-merge",
            "do not merge",
            "DO_NOT_MERGE",
            "Do-Not-Merge",
            "dnm",
            "DNM",
        ):
            with self.subTest(label=name):
                self.assertTrue(hold_guard.hold_reasons("chore: x", [name]))

    def test_unrelated_labels_are_clear(self) -> None:
        for name in (
            "dependencies",
            "security",
            "governance",
            "holdings",
            "threshold",
            "household",
            "hold-guard",
            "stale",
        ):
            with self.subTest(label=name):
                self.assertEqual(hold_guard.hold_reasons("chore: x", [name]), [])

    def test_title_markers_are_held(self) -> None:
        for title in (
            PR_773_TITLE,
            PR_774_TITLE,
            "[HOLD] feat: x",
            "feat: x [hold]",
            "feat: x [ HOLD ]",
            "[DNM] feat: x",
            "DNM: feat: x",
            "feat: x (dnm)",
            "feat: x [do not merge]",
            "feat: x [Do-Not-Merge]",
        ):
            with self.subTest(title=title):
                self.assertTrue(hold_guard.hold_reasons(title, []))

    def test_titles_that_only_mention_hold_are_clear(self) -> None:
        # Prose is not a marker: HOLD must be declared with a label or the
        # bracketed marker. The szl-frontier #190/#193 titles said "under
        # HOLD" and are the reason this boundary is pinned explicitly.
        for title in (
            "feat(frontier): operational intake plane (F01-F34) under HOLD",
            "ci(hold-guard): fail pull requests that carry a hold marker",
            "chore(deps): bump szl-holdings/.github reusable pins",
            "fix: threshold handling for household data",
            "feat: add dnmx parser",
            "HOLD guard",
        ):
            with self.subTest(title=title):
                self.assertEqual(hold_guard.hold_reasons(title, []), [])

    def test_annotation_cannot_start_a_new_workflow_command(self) -> None:
        escaped = hold_guard.annotation("a\n::add-mask::x\r%")
        self.assertNotIn("\n", escaped)
        self.assertNotIn("\r", escaped)
        self.assertEqual(escaped, "a%0A::add-mask::x%0D%25")


class MainTests(unittest.TestCase):
    def test_clear_pull_request_passes_after_live_read(self) -> None:
        harness = Harness(
            "pull_request",
            pr_event(7, "feat: x", ["enhancement"]),
            live(7, "feat: x", ["enhancement"]),
        )
        code, output = harness.run()
        self.assertEqual(code, 0, output)
        self.assertEqual(
            harness.calls,
            [("https://api.github.com", REPO, 7, "test-token-not-a-secret")],
        )
        self.assertIn("carries no HOLD marker", output)

    def test_open_hold_drafts_773_and_774_fail(self) -> None:
        for number, title in ((773, PR_773_TITLE), (774, PR_774_TITLE)):
            with self.subTest(pr=number):
                code, output = Harness(
                    "pull_request",
                    pr_event(number, title, []),
                    live(number, title, []),
                ).run()
                self.assertEqual(code, 1, output)
                self.assertIn(f"::error title=HOLD::{REPO}#{number} is on HOLD", output)

    def test_hold_label_fails(self) -> None:
        code, output = Harness(
            "pull_request",
            pr_event(9, "feat: x", ["hold"]),
            live(9, "feat: x", ["hold"]),
        ).run()
        self.assertEqual(code, 1, output)
        self.assertIn("label 'hold'", output)

    def test_label_added_after_the_event_is_caught_live(self) -> None:
        code, output = Harness(
            "pull_request",
            pr_event(9, "feat: x", []),
            live(9, "feat: x", ["do-not-merge"]),
        ).run()
        self.assertEqual(code, 1, output)
        self.assertIn("(live pull request)", output)

    def test_stale_payload_marker_still_fails(self) -> None:
        # The union is deliberate: the later unlabeled/edited event produces a
        # fresh run whose payload and live read are both clear.
        code, output = Harness(
            "pull_request",
            pr_event(9, "feat: x [HOLD]", []),
            live(9, "feat: x", []),
        ).run()
        self.assertEqual(code, 1, output)
        self.assertIn("(event payload)", output)

    def test_pull_request_target_is_accepted(self) -> None:
        code, output = Harness(
            "pull_request_target",
            pr_event(5, "feat: x", []),
            live(5, "feat: x", []),
        ).run()
        self.assertEqual(code, 0, output)

    def test_merge_group_resolves_the_queued_pull_request(self) -> None:
        harness = Harness("merge_group", merge_group_event(42), live(42, "feat: x", []))
        code, output = harness.run()
        self.assertEqual(code, 0, output)
        self.assertEqual(harness.calls[0][2], 42)

    def test_merge_group_with_hold_label_fails(self) -> None:
        code, output = Harness(
            "merge_group", merge_group_event(42), live(42, "feat: x", ["HOLD"])
        ).run()
        self.assertEqual(code, 1, output)

    def test_merge_group_on_a_slashed_base_branch(self) -> None:
        harness = Harness(
            "merge_group",
            merge_group_event(8, base="release/2026-09"),
            live(8, "fix: y", []),
        )
        code, output = harness.run()
        self.assertEqual(code, 0, output)
        self.assertEqual(harness.calls[0][2], 8)


class FailClosedTests(unittest.TestCase):
    def assert_unverified(self, harness: Harness) -> str:
        code, output = harness.run()
        self.assertEqual(code, 2, output)
        self.assertIn("::error title=hold-guard could not evaluate::", output)
        return output

    def test_unsupported_events_fail_closed(self) -> None:
        for event_name in ("push", "workflow_dispatch", "schedule", ""):
            with self.subTest(event=event_name):
                self.assert_unverified(Harness(event_name, {"ref": "refs/heads/main"}))

    def test_live_read_failures_fail_closed(self) -> None:
        for error in (
            hold_guard.GuardError("cannot read live pull request #9: HTTP 403"),
            hold_guard.GuardError("cannot read live pull request #9: HTTP 503"),
        ):
            with self.subTest(error=str(error)):
                self.assert_unverified(
                    Harness("pull_request", pr_event(9, "feat: x", []), error)
                )

    def test_live_read_of_a_different_pull_request_fails_closed(self) -> None:
        self.assert_unverified(
            Harness("pull_request", pr_event(9, "feat: x", []), live(10, "feat: x", []))
        )

    def test_malformed_live_labels_fail_closed(self) -> None:
        self.assert_unverified(
            Harness(
                "pull_request",
                pr_event(9, "feat: x", []),
                {"number": 9, "title": "feat: x", "labels": None},
            )
        )

    def test_missing_token_fails_closed_before_any_read(self) -> None:
        self.assert_unverified(
            Harness("pull_request", pr_event(9, "feat: x", []), None, GITHUB_TOKEN=None)
        )

    def test_bad_environment_fails_closed(self) -> None:
        for env in (
            {"GITHUB_REPOSITORY": "not a repo"},
            {"GITHUB_API_URL": "http://api.github.com"},
            {"GITHUB_EVENT_PATH": None},
        ):
            with self.subTest(env=env):
                self.assert_unverified(
                    Harness("pull_request", pr_event(9, "feat: x", []), None, **env)
                )

    def test_malformed_payloads_fail_closed(self) -> None:
        cases = (
            ("pull_request", "{not json"),
            ("pull_request", []),
            ("pull_request", {"action": "opened"}),
            ("pull_request", {"pull_request": {"number": "9", "title": "x", "labels": []}}),
            ("pull_request", {"pull_request": {"number": True, "title": "x", "labels": []}}),
            ("pull_request", {"pull_request": {"number": 9, "title": None, "labels": []}}),
            ("pull_request", {"pull_request": {"number": 9, "title": "x", "labels": [{}]}}),
            ("merge_group", {"action": "destroyed", "merge_group": merge_group_event(1)["merge_group"]}),
            ("merge_group", {"action": "checks_requested"}),
            (
                "merge_group",
                {
                    "action": "checks_requested",
                    "merge_group": {"base_ref": "refs/heads/main", "head_ref": "refs/heads/main"},
                },
            ),
            (
                "merge_group",
                {
                    "action": "checks_requested",
                    "merge_group": {
                        "base_ref": "refs/heads/other",
                        "head_ref": f"refs/heads/gh-readonly-queue/main/pr-3-{BASE_SHA}",
                    },
                },
            ),
        )
        for event_name, event in cases:
            with self.subTest(event_name=event_name, event=event):
                self.assert_unverified(Harness(event_name, event, live(9, "x", [])))


class FetchTests(unittest.TestCase):
    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    def http_error(self, code: int) -> HTTPError:
        return HTTPError("https://api.github.com/x", code, "err", {}, None)

    def test_request_shape_and_success(self) -> None:
        seen = []

        def opener(request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"), timeout))
            return self.Response(json.dumps(live(3, "t", [])).encode())

        data = hold_guard.fetch_pull(
            "https://api.github.com/", REPO, 3, "tok", opener=opener, sleep=lambda s: None
        )
        self.assertEqual(data["number"], 3)
        self.assertEqual(
            seen, [("https://api.github.com/repos/szl-holdings/.github/pulls/3", "Bearer tok", 20)]
        )

    def test_transient_errors_retry_then_fail_closed(self) -> None:
        attempts = []

        def opener(request, timeout):
            attempts.append(1)
            raise self.http_error(503)

        with self.assertRaises(hold_guard.GuardError):
            hold_guard.fetch_pull(
                "https://api.github.com", REPO, 3, "tok", opener=opener, sleep=lambda s: None
            )
        self.assertEqual(len(attempts), hold_guard.FETCH_ATTEMPTS)

    def test_transient_error_then_success(self) -> None:
        results = [URLError("reset"), self.Response(json.dumps(live(3, "t", [])).encode())]

        def opener(request, timeout):
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        data = hold_guard.fetch_pull(
            "https://api.github.com", REPO, 3, "tok", opener=opener, sleep=lambda s: None
        )
        self.assertEqual(data["number"], 3)

    def test_permanent_http_error_does_not_retry(self) -> None:
        attempts = []

        def opener(request, timeout):
            attempts.append(1)
            raise self.http_error(404)

        with self.assertRaises(hold_guard.GuardError):
            hold_guard.fetch_pull(
                "https://api.github.com", REPO, 3, "tok", opener=opener, sleep=lambda s: None
            )
        self.assertEqual(len(attempts), 1)

    def test_non_json_body_fails_closed(self) -> None:
        with self.assertRaises(hold_guard.GuardError):
            hold_guard.fetch_pull(
                "https://api.github.com",
                REPO,
                3,
                "tok",
                opener=lambda request, timeout: self.Response(b"<html>"),
                sleep=lambda s: None,
            )


PINNED_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*[^@\s]+@[0-9a-f]{40}\s+#\s*v\S+\s*$")


class WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.caller = CALLER.read_text(encoding="utf-8")
        self.reusable = REUSABLE.read_text(encoding="utf-8")

    def test_caller_reruns_on_every_hold_relevant_event(self) -> None:
        match = re.search(
            r"(?m)^  pull_request:\n    types: \[(?P<types>[^\]]*)\]$", self.caller
        )
        self.assertIsNotNone(match, "pull_request types must be a literal flow list")
        types = {item.strip() for item in match.group("types").split(",")}
        self.assertTrue(
            {"opened", "synchronize", "reopened", "edited", "labeled", "unlabeled"}
            <= types,
            types,
        )
        self.assertIn("\n  merge_group:\n    types: [checks_requested]\n", self.caller)
        self.assertNotRegex(self.caller, r"(?m)^\s+branches:")
        self.assertNotRegex(self.caller, r"(?m)^\s+paths:")

    def test_caller_job_name_and_least_privilege(self) -> None:
        self.assertIn(
            "\njobs:\n  hold-guard:\n    name: hold-guard\n", self.caller
        )
        self.assertIn("uses: ./.github/workflows/reusable-hold-guard.yml", self.caller)
        self.assertIn("\npermissions:\n  contents: read\n", self.caller)
        self.assertIn(
            "    permissions:\n      contents: read\n      pull-requests: read\n",
            self.caller,
        )

    def test_reusable_job_name_and_least_privilege(self) -> None:
        self.assertIn("\non:\n  workflow_call: {}\n", self.reusable)
        self.assertIn("\njobs:\n  hold-guard:\n    name: hold-guard\n", self.reusable)
        self.assertIn("\npermissions:\n  contents: read\n", self.reusable)
        self.assertIn(
            "    permissions:\n      contents: read\n      pull-requests: read\n",
            self.reusable,
        )

    def test_reusable_runs_only_the_exact_guard_source(self) -> None:
        for marker in (
            "repository: ${{ job.workflow_repository }}",
            "ref: ${{ job.workflow_sha }}",
            "persist-credentials: false",
            "sparse-checkout: .github/scripts/hold_guard.py",
            "sparse-checkout-cone-mode: false",
            "GITHUB_TOKEN: ${{ github.token }}",
            "python3 -I hold-guard-tools/.github/scripts/hold_guard.py",
        ):
            self.assertIn(marker, self.reusable)
        # Only one checkout: the guard's own source. Candidate content is
        # never checked out or executed.
        self.assertEqual(self.reusable.count("actions/checkout@"), 1)

    def test_no_secrets_writes_or_privileged_triggers(self) -> None:
        for text in (self.caller, self.reusable):
            for forbidden in (
                "secrets.",
                "secrets: inherit",
                ": write",
                "pull_request" + "_target",
                "workflow_dispatch",
                "id-token",
                "${{ github.event.pull_request.title",
            ):
                self.assertNotIn(forbidden, text)

    def test_every_action_is_sha_pinned_with_a_version_comment(self) -> None:
        for path, text in ((CALLER, self.caller), (REUSABLE, self.reusable)):
            for number, line in enumerate(text.splitlines(), start=1):
                if re.match(r"^\s*(?:-\s+)?uses:", line) and "./.github/" not in line:
                    with self.subTest(file=path.name, line=number):
                        self.assertRegex(line, PINNED_USES)


if __name__ == "__main__":
    unittest.main()
