#!/usr/bin/env python3
"""Executable adversarial contract for the trusted DCO checker."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

import dco_check as dco


DOCTRINE_REQUIRED_WORKFLOW = (
    Path(__file__).resolve().parents[1] / "workflows" / "doctrine-required-dco.yml"
)
DOCTRINE_REQUIRED_WORKFLOW_SHA256 = (
    "43b210ab34819bd617b0892b3fa60a9c910d63fca2ca59fc93874b27ab22d51a"
)


def validate_doctrine_required_workflow(workflow: str) -> None:
    """Fail closed when the external Doctrine DCO controller drifts."""

    workflow = workflow.replace("\r\n", "\n").replace("\r", "\n")
    if hashlib.sha256(workflow.encode()).hexdigest() != DOCTRINE_REQUIRED_WORKFLOW_SHA256:
        raise ValueError("Doctrine workflow exact-byte digest drifted")

    required_markers = (
        "name: Doctrine required DCO enforcement",
        "  pull_request:\n",
        "  pull_request:\n    # Required-workflow rules ignore event filters.",
        "Required-workflow rules ignore event filters",
        "  merge_group:\n    branches: [__doctrine-ruleset-only__]\n    types: [checks_requested]",
        "permissions:\n  contents: read\n  pull-requests: read",
        "  required-dco:\n    name: Required DCO enforcement",
        "ACTUAL_TARGET_REPOSITORY: ${{ github.repository }}",
        "ACTUAL_TARGET_REPOSITORY_ID: ${{ github.repository_id }}",
        "ACTUAL_TARGET_BASE_REPOSITORY: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.repo.full_name || github.repository }}",
        "ACTUAL_TARGET_BASE_REPOSITORY_ID: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.repo.id || github.repository_id }}",
        "ACTUAL_TARGET_BASE_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.merge_group.base_sha }}",
        "ACTUAL_TARGET_HEAD_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.event.merge_group.head_sha }}",
        "ACTUAL_GITHUB_WORKFLOW_REF: ${{ github.workflow_ref }}",
        "ACTUAL_GITHUB_WORKFLOW_SHA: ${{ github.workflow_sha }}",
        "ACTUAL_WORKFLOW_REPOSITORY: ${{ job.workflow_repository }}",
        "ACTUAL_WORKFLOW_FILE_PATH: ${{ job.workflow_file_path }}",
        "ACTUAL_WORKFLOW_REF: ${{ job.workflow_ref }}",
        "ACTUAL_WORKFLOW_SHA: ${{ job.workflow_sha }}",
        'test "$ACTUAL_TARGET_REPOSITORY" = "szl-holdings/szl-doctrine"',
        'test "$ACTUAL_TARGET_REPOSITORY_ID" = "1258631185"',
        'test "$ACTUAL_TARGET_BASE_REPOSITORY" = "szl-holdings/szl-doctrine"',
        'test "$ACTUAL_TARGET_BASE_REPOSITORY_ID" = "1258631185"',
        'test "$ACTUAL_WORKFLOW_REPOSITORY" = "szl-holdings/.github"',
        'test "$ACTUAL_WORKFLOW_FILE_PATH" = ".github/workflows/doctrine-required-dco.yml"',
        'test "$ACTUAL_WORKFLOW_REF" = "szl-holdings/.github/.github/workflows/doctrine-required-dco.yml@refs/heads/main"',
        '[[ "$ACTUAL_WORKFLOW_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$ACTUAL_WORKFLOW_REF" = "$ACTUAL_GITHUB_WORKFLOW_REF"',
        'test "$ACTUAL_WORKFLOW_SHA" = "$ACTUAL_GITHUB_WORKFLOW_SHA"',
        '[[ "$ACTUAL_TARGET_BASE_SHA" =~ ^[0-9a-f]{40}$ ]]',
        '[[ "$ACTUAL_TARGET_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'PYTHONDONTWRITEBYTECODE: "1"',
        "repository: ${{ job.workflow_repository }}",
        "ref: ${{ job.workflow_sha }}",
        "path: trusted-dco",
        "repository: ${{ github.repository }}",
        "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.event.merge_group.head_sha }}",
        "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.merge_group.base_sha }}",
        "path: candidate",
        "path: target-base",
        "trusted-dco/.github/scripts/test_dco_check.py",
        "trusted-dco/.github/scripts/test_dco_events.py",
        "trusted-dco/.github/scripts/test_dco_activation.py",
        "trusted-dco/.github/scripts/dco_check.py",
        "Assert protected DCO source remained immutable",
        "status --porcelain=v1 --untracked-files=all",
        '--repo-root "$GITHUB_WORKSPACE/candidate"',
        '--event-path "$GITHUB_EVENT_PATH"',
        "--allow-draft",
    )
    for marker in required_markers:
        if marker not in workflow:
            raise ValueError(f"missing required Doctrine workflow marker: {marker!r}")

    if workflow.count(
        "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    ) != 3:
        raise ValueError("Doctrine workflow must have exactly three pinned checkouts")
    if workflow.count("persist-credentials: false") != 3:
        raise ValueError("every Doctrine workflow checkout must discard credentials")
    if workflow.count("GITHUB_TOKEN: ${{ github.token }}") != 1:
        raise ValueError("Doctrine validation must have one read-only API token binding")
    if workflow.count("--allow-draft") != 1:
        raise ValueError("Doctrine required workflow must explicitly validate draft PR commits")
    if workflow.count("name: Required DCO enforcement\n") != 1:
        raise ValueError("Doctrine required context must have one producer")
    if workflow.count("branches: [__doctrine-ruleset-only__]") != 2:
        raise ValueError("both native event families must have nonmatching filters")
    if re.search(r"(?m)^\s+if\s*:", workflow):
        raise ValueError("Doctrine workflow cannot skip identity or validation steps")
    if re.search(r"(?im)^\s*permissions\s*:\s*write-all\s*$", workflow):
        raise ValueError("Doctrine workflow cannot grant write-all permissions")
    if workflow.count("permissions:") != 1:
        raise ValueError("Doctrine workflow must define only global read permissions")

    top_level_keys = re.findall(r"(?m)^([A-Za-z][A-Za-z0-9_-]*):(?:\s|$)", workflow)
    if top_level_keys != ["name", "on", "permissions", "jobs"]:
        raise ValueError("Doctrine workflow top-level keys drifted")
    jobs_body = workflow.split("jobs:\n", 1)
    if len(jobs_body) != 2:
        raise ValueError("Doctrine workflow jobs block is missing")
    job_ids = re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", jobs_body[1])
    if job_ids != ["required-dco"]:
        raise ValueError("Doctrine workflow must contain exactly one required-dco job")
    job_keys = re.findall(
        r"(?m)^    ([A-Za-z][A-Za-z0-9_-]*):(?:\s|$)", jobs_body[1]
    )
    if job_keys != ["name", "runs-on", "timeout-minutes", "env", "steps"]:
        raise ValueError("Doctrine required-dco job keys drifted")

    expected_steps = (
        (
            "Assert protected workflow and target identity",
            ("env", "run"),
            "0a6b61215234b977e53da72fa8015abfe4ef15375c3ec1b75527b9eb670485fc",
            "f4dc1d39a40b0b6a0138472dc2d7e3760c186ca98a70f1e2c45623c37d332894",
        ),
        (
            "Checkout immutable protected DCO source",
            ("uses", "with"),
            None,
            "c7a102b9dd11848f163896138d68bce99e008e0e98aa7c6eb99e3cd7e84baf2f",
        ),
        (
            "Assert exact protected DCO source revision",
            ("env", "run"),
            "599a4104d3d9955255c9cf972575cec1b4a810b925dacdeaf0fa5510e9a202e7",
            "edf9098e8066d24005d7882ff24b81a881315572b0a12d46d2ade5a363403a9a",
        ),
        (
            "Run protected DCO contract tests",
            ("run",),
            "751319d37484a249f1d5636d64116e879e116e1b14203039e25f8ba915c8ee71",
            "f3ba09b0e582c3817cbbbe736ea209837d9626555a12afc9ea57d41438ac0ae3",
        ),
        (
            "Assert protected DCO source remained immutable",
            ("env", "run"),
            "6d4dea538b1b6dc234bdab1c82fc1063715f346fb48d6207ca103703eec354b8",
            "7851b12c267a0c0df7bca958004baca6d8fedb33a54e8f547d776d50d9c163b8",
        ),
        (
            "Checkout exact target candidate as inert graph data",
            ("uses", "with"),
            None,
            "fc33602b1d63855c3166277c4903ba901039a34b026b28bb71275f37902c4794",
        ),
        (
            "Checkout exact target base as inert graph data",
            ("uses", "with"),
            None,
            "e5ce0626f1e7505d57ea9ecdc0df2ac7947418c2f3a9f112335c474345ab87b8",
        ),
        (
            "Bind exact target graph revisions",
            ("env", "run"),
            "323203328918b0cd62d8e192df57697ae4b954faf4d7c5d45a13ab19575d7aca",
            "9024a843c8cf33882de4bcc3fbbc4bedd0f2d502b4c46ac47988267bafd4f1be",
        ),
        (
            "Validate exact target commits with protected DCO code",
            ("env", "run"),
            "925c200c57a237dfd8c21ec158b14018fed30a984c4d29deb677308cb484bbbf",
            "8b357ad998cea49994f3a9e44525d3ec5ded8618462d6263e2ff9a2d963e7866",
        ),
    )
    workflow_lines = workflow.splitlines()
    step_starts = [
        index
        for index, line in enumerate(workflow_lines)
        if line.startswith("      - name: ")
    ]
    observed_steps: list[tuple[str, tuple[str, ...], str | None, str]] = []
    for position, start in enumerate(step_starts):
        end = step_starts[position + 1] if position + 1 < len(step_starts) else len(
            workflow_lines
        )
        block = workflow_lines[start:end]
        name = block[0][14:]
        keys = tuple(
            match.group(1)
            for line in block[1:]
            if (match := re.match(r"^        ([A-Za-z][A-Za-z0-9-]*):(?:\s|$)", line))
        )
        run_body: list[str] = []
        for line_index, line in enumerate(block):
            if line not in {"        run: |", "        run: >-"}:
                continue
            body_index = line_index + 1
            while body_index < len(block):
                body_line = block[body_index]
                indentation = len(body_line) - len(body_line.lstrip(" "))
                if indentation < 10:
                    break
                run_body.append(body_line[10:])
                body_index += 1
        digest = None
        if run_body:
            digest = hashlib.sha256(("\n".join(run_body) + "\n").encode()).hexdigest()
        block_digest = hashlib.sha256(("\n".join(block) + "\n").encode()).hexdigest()
        observed_steps.append((name, keys, digest, block_digest))
    if tuple(observed_steps) != expected_steps:
        raise ValueError("Doctrine workflow ordered step contract drifted")

    checkout = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    uses = re.findall(r"(?m)^\s+uses:\s*(\S+)(?:\s+#.*)?$", workflow)
    if uses != [checkout, checkout, checkout]:
        raise ValueError("Doctrine workflow actions drifted from three pinned checkouts")

    expected_candidate_lines = (
        "- name: Checkout exact target candidate as inert graph data",
        "path: candidate",
        'test "$(git -C "$GITHUB_WORKSPACE/candidate" rev-parse HEAD)" = "$EXPECTED_HEAD_SHA"',
        'git -C "$GITHUB_WORKSPACE/candidate" fetch \\',
        'git -C "$GITHUB_WORKSPACE/candidate" cat-file -e "$EXPECTED_BASE_SHA^{commit}"',
        '--repo-root "$GITHUB_WORKSPACE/candidate"',
    )
    observed_candidate_lines = tuple(
        line.strip() for line in workflow_lines if "candidate" in line.lower()
    )
    if observed_candidate_lines != expected_candidate_lines:
        raise ValueError("Doctrine candidate graph usage drifted toward execution")

    steps = workflow.split("    steps:\n", 1)
    if len(steps) != 2:
        raise ValueError("Doctrine workflow must define one explicit steps sequence")
    first_step, separator, remainder = steps[1].partition(
        "\n      - name: Checkout immutable protected DCO source"
    )
    if not separator:
        raise ValueError("protected source checkout must immediately follow identity validation")
    if not first_step.startswith(
        "      - name: Assert protected workflow and target identity\n"
    ):
        raise ValueError("identity validation must be the first Doctrine workflow step")
    if "uses:" in first_step or "actions/" in first_step:
        raise ValueError("no action may run before the identity tuple is validated")
    if "ref: ${{ job.workflow_sha }}" not in remainder:
        raise ValueError("protected source checkout is not bound to job.workflow_sha")

    banned_patterns = {
        "manual or privileged trigger": r"(?m)^\s*(?:workflow_dispatch|pull_request_target|push)\s*:",
        "secret reference": r"(?i)\bsecrets(?:\.|\[)",
        "write permission": r"(?im)^\s*[a-z-]+\s*:\s*write\s*$",
        "status publication": r"(?i)(?:statuses\s*:|/statuses/|commit status)",
        "artifact flow": r"actions/(?:upload|download)-artifact@",
        "fail-open continuation": r"(?i)continue-on-error",
        "fail-open shell suffix": r"(?m)(?:\|\|\s*(?:true|:)(?:\s|$)|;\s*(?:true|:)(?:\s|$)|&\s*(?:#.*)?$)",
        "run cancellation": r"(?m)^\s*concurrency\s*:",
        "candidate execution": r"(?im)^\s*(?:python|node|bash|sh|npm|pnpm)\b[^\n]*candidate",
        "candidate working directory": r"(?im)^\s*working-directory\s*:\s*[^\n]*candidate",
        "escaped YAML key": r"(?im)^\s*(?:\\x[0-9a-f]{2}|\\u[0-9a-f]{4}|\\U[0-9a-f]{8})",
    }
    for label, pattern in banned_patterns.items():
        if re.search(pattern, workflow):
            raise ValueError(f"Doctrine workflow contains prohibited {label}")

    literal_runs = re.findall(r"(?m)^\s+run: \|\n((?:\s{10}.*\n?)*)", workflow)
    if not literal_runs or any(
        not block.lstrip().startswith("set -euo pipefail") for block in literal_runs
    ):
        raise ValueError("every multi-command Doctrine shell step must fail closed")
    folded_runs = re.findall(r"(?m)^\s+run: >-\n((?:\s{10}.*\n?)*)", workflow)
    if len(folded_runs) != 1 or not folded_runs[0].lstrip().startswith("python "):
        raise ValueError("Doctrine validation dispatch must be one direct Python command")


class DcoCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Series A Builder")
        self.git("config", "user.email", "builder@example.com")
        self.base = self.commit("chore: base\n\nSigned-off-by: Series A Builder <builder@example.com>")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, input_text: str | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
        )
        return completed.stdout.strip()

    def commit(
        self,
        message: str,
        name: str = "Series A Builder",
        email: str = "builder@example.com",
        committer_name: str | None = None,
        committer_email: str | None = None,
    ) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": committer_name or name,
            "GIT_COMMITTER_EMAIL": committer_email or email,
        }
        subprocess.run(
            ["git", "commit", "--allow-empty", "-F", "-"],
            cwd=self.repo,
            input=message,
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        return self.git("rev-parse", "HEAD")

    def assert_rejected(self, pattern: str, function, *args, **kwargs) -> None:
        with self.assertRaisesRegex(dco.DcoError, pattern):
            function(*args, **kwargs)

    def provider_api(
        self,
        squash_sha: str,
        source_shas: list[str],
        source_head: str,
        *,
        number: int = 411,
        pr_base_sha: str | None = None,
    ):
        (
            parents,
            author_name,
            author_email,
            committer_name,
            committer_email,
            _,
        ) = dco.commit_record(
            self.repo,
            squash_sha,
        )
        if (
            committer_name,
            committer_email,
        ) != dco.GITHUB_WEB_FLOW_COMMITTER:
            raise AssertionError("provider fixture is not a raw GitHub/web-flow commit")
        commit_path = f"/repos/szl-holdings/.github/commits/{squash_sha}"
        pulls_path = f"{commit_path}/pulls"
        metadata_path = f"/repos/szl-holdings/.github/pulls/{number}"
        commits_path = f"{metadata_path}/commits"
        provider_base = parents[0] if pr_base_sha is None else pr_base_sha
        responses: dict[str, object] = {
            commit_path: {
                "sha": squash_sha,
                "commit": {
                    "author": {"name": author_name, "email": author_email},
                    "committer": {
                        "name": committer_name,
                        "email": committer_email,
                    },
                    "verification": {
                        "verified": True,
                        "reason": "valid",
                        "signature": "signed",
                        "payload": "bound payload",
                    },
                },
                "committer": {"login": "web-flow", "type": "User"},
                "parents": [{"sha": parent} for parent in parents],
            },
            f"{pulls_path}?per_page=100&page=1": [
                {
                    "number": number,
                    "state": "closed",
                    "draft": False,
                    "merged_at": "2026-08-11T05:49:54Z",
                    "merge_commit_sha": squash_sha,
                    "base": {
                        "ref": "main",
                        "sha": provider_base,
                        "repo": {"full_name": "szl-holdings/.github"},
                    },
                    "head": {"sha": source_head},
                }
            ],
            f"{pulls_path}?per_page=100&page=2": [],
            metadata_path: {
                "base": {"sha": provider_base},
                "head": {"sha": source_head},
                "commits": len(source_shas),
                "draft": False,
            },
        }
        page_count = (
            len(source_shas) + dco.COMMITS_PER_PAGE - 1
        ) // dco.COMMITS_PER_PAGE
        for page in range(1, page_count + 1):
            start = (page - 1) * dco.COMMITS_PER_PAGE
            responses[f"{commits_path}?per_page=100&page={page}"] = [
                {"sha": sha}
                for sha in source_shas[start : start + dco.COMMITS_PER_PAGE]
            ]
        responses[f"{commits_path}?per_page=100&page={page_count + 1}"] = []
        calls: list[str] = []

        def api_get(path: str):
            calls.append(path)
            if path not in responses:
                raise AssertionError(f"unexpected provider lookup: {path}")
            return responses[path]

        paths = {
            "commit": commit_path,
            "pulls_page": f"{pulls_path}?per_page=100&page=1",
            "pulls_boundary": f"{pulls_path}?per_page=100&page=2",
            "metadata": metadata_path,
            "commits_page": f"{commits_path}?per_page=100&page=1",
            "commits_boundary": (
                f"{commits_path}?per_page=100&page={page_count + 1}"
            ),
        }
        return api_get, responses, calls, paths

    def test_two_and_five_entry_signed_groups_pass(self) -> None:
        second = self.commit("fix: one\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.commit("fix: two\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.assertEqual(dco.validate_range(self.repo, self.base, self.git("rev-parse", "HEAD")), 2)
        for number in range(3):
            self.commit(
                f"fix: grouped {number}\n\nSigned-off-by: Series A Builder <builder@example.com>"
            )
        self.assertEqual(dco.validate_range(self.repo, self.base, self.git("rev-parse", "HEAD")), 5)
        self.assertTrue(second)

    def test_unsigned_middle_commit_fails(self) -> None:
        self.commit("fix: signed\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.commit("fix: unsigned")
        self.commit("fix: signed again\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.assert_rejected("no valid terminal", dco.validate_range, self.repo, self.base, self.git("rev-parse", "HEAD"))

    def test_author_mismatch_fails(self) -> None:
        head = self.commit(
            "fix: mismatch\n\nSigned-off-by: Different Person <other@example.com>"
        )
        self.assert_rejected(
            "does not exactly match",
            dco.validate_range,
            self.repo,
            self.base,
            head,
        )

    def test_author_identity_comparison_is_exact(self) -> None:
        head = self.commit(
            "fix: exact identity\n\nSigned-off-by: series a builder <builder@example.com>"
        )
        self.assert_rejected("exactly match", dco.validate_range, self.repo, self.base, head)

    def test_malformed_and_body_only_signoffs_fail(self) -> None:
        malformed = self.commit("fix: malformed\n\nSigned-off-by: no-address")
        self.assert_rejected("no valid terminal", dco.validate_range, self.repo, self.base, malformed)
        self.git("reset", "--hard", self.base)
        body_only = self.commit(
            "fix: body only\n\nSigned-off-by: Series A Builder <builder@example.com>\n\nNot a trailer block."
        )
        self.assert_rejected("no valid terminal", dco.validate_range, self.repo, self.base, body_only)

    def test_unsigned_empty_and_merge_prefixed_commits_do_not_skip(self) -> None:
        empty = self.commit("chore: empty")
        self.assert_rejected("no valid terminal", dco.validate_range, self.repo, self.base, empty)
        self.git("reset", "--hard", self.base)
        merge_named = self.commit("Merge queue artifact")
        self.assert_rejected("no valid terminal", dco.validate_range, self.repo, self.base, merge_named)

    def test_empty_range_and_non_ancestor_fail(self) -> None:
        self.assert_rejected("empty", dco.validate_range, self.repo, self.base, self.base)
        tree = self.git("rev-parse", f"{self.base}^{{tree}}")
        unrelated = self.git("commit-tree", tree, input_text="chore: unrelated\n")
        self.assert_rejected("not an ancestor", dco.validate_range, self.repo, unrelated, self.base)

    def test_signed_two_parent_pr_merge_passes(self) -> None:
        first = self.commit("fix: first\n\nSigned-off-by: Series A Builder <builder@example.com>")
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        message = "fix: synthetic merge\n\nSigned-off-by: Series A Builder <builder@example.com>\n"
        merged = self.git("commit-tree", tree, "-p", first, "-p", self.base, input_text=message)
        self.git("reset", "--hard", merged)
        shas = self.git("rev-list", "--reverse", f"{self.base}..{merged}").splitlines()
        self.assertEqual(
            dco.validate_commits(
                self.repo,
                shas,
                merged,
                allow_merge_commits=True,
            ),
            2,
        )
        self.assert_rejected("unsupported parent count", dco.validate_range, self.repo, self.base, merged)

    def test_unsigned_second_parent_cannot_hide_behind_signed_pr_merge(self) -> None:
        first = self.commit("fix: first\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.git("switch", "-c", "unsigned-side", self.base)
        unsigned = self.commit("fix: unsigned side")
        self.git("switch", "main")
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        message = "fix: synthetic merge\n\nSigned-off-by: Series A Builder <builder@example.com>\n"
        merged = self.git("commit-tree", tree, "-p", first, "-p", unsigned, input_text=message)
        self.git("reset", "--hard", merged)
        shas = self.git("rev-list", "--reverse", f"{self.base}..{merged}").splitlines()
        self.assert_rejected(
            "no valid terminal",
            dco.validate_commits,
            self.repo,
            shas,
            merged,
            allow_merge_commits=True,
        )

    def test_octopus_merge_fails_even_for_pr_history(self) -> None:
        first = self.commit("fix: first\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.git("switch", "-c", "side-one", self.base)
        side_one = self.commit("fix: side one\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.git("switch", "-c", "side-two", self.base)
        side_two = self.commit("fix: side two\n\nSigned-off-by: Series A Builder <builder@example.com>")
        self.git("switch", "main")
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        message = "fix: synthetic merge\n\nSigned-off-by: Series A Builder <builder@example.com>\n"
        merged = self.git(
            "commit-tree",
            tree,
            "-p",
            first,
            "-p",
            side_one,
            "-p",
            side_two,
            input_text=message,
        )
        self.git("reset", "--hard", merged)
        self.assert_rejected(
            "unsupported parent count",
            dco.validate_commits,
            self.repo,
            [first, merged],
            merged,
            allow_merge_commits=True,
        )

    def test_merge_group_identity_and_hostile_ref_contract(self) -> None:
        head = self.commit("fix: queue\n\nSigned-off-by: Series A Builder <builder@example.com>")
        payload = {
            "action": "checks_requested",
            "merge_group": {
                "base_ref": "refs/heads/main",
                "head_ref": "refs/heads/gh-readonly-queue/main/pr-400-deadbeef",
                "base_sha": self.base,
                "head_sha": head,
            },
        }
        self.assertEqual(dco.merge_group_subject(payload, head), (self.base, head))
        hostile = {**payload, "merge_group": {**payload["merge_group"], "head_ref": "refs/heads/main"}}
        self.assert_rejected("queue namespace", dco.merge_group_subject, hostile, head)
        wrong_action = {**payload, "action": "destroy"}
        self.assert_rejected("checks_requested", dco.merge_group_subject, wrong_action, head)
        self.assert_rejected("differs", dco.merge_group_subject, payload, "f" * 40)

    def test_merge_group_legacy_context_has_one_terminal_producer(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / "workflows" / "dco.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(workflow.count("name: DCO sign-off check\n"), 1)
        self.assertIn("needs: dco", workflow)
        self.assertIn(
            "if: always() && github.event_name != 'pull_request_target'",
            workflow,
        )
        self.assertIn("NATIVE_DCO_RESULT: ${{ needs.dco.result }}", workflow)
        self.assertIn('test "$NATIVE_DCO_RESULT" = "success"', workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_reusable_legacy_context_faithfully_propagates_validation(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1]
            / "workflows"
            / "reusable-dco.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(workflow.count("name: DCO sign-off\n"), 1)
        self.assertIn("needs: reusable-dco", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("REUSABLE_DCO_RESULT: ${{ needs.reusable-dco.result }}", workflow)
        self.assertIn('test "$REUSABLE_DCO_RESULT" = "success"', workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_merge_group_validates_linear_squash_sequence(self) -> None:
        first = self.commit(
            "fix: first queued squash\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        second = self.commit(
            "fix: second queued squash\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        self.assertEqual(dco.validate_merge_group(self.repo, self.base, second), 2)

        self.git("reset", "--hard", self.base)
        unsigned = self.commit("fix: unsigned queued change")
        self.assert_rejected(
            "no valid terminal",
            dco.validate_merge_group,
            self.repo,
            self.base,
            unsigned,
        )

        self.git("reset", "--hard", first)
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        nonlinear_head = self.git(
            "commit-tree",
            tree,
            "-p",
            first,
            "-p",
            self.base,
            input_text=(
                "fix: nonlinear queue head\n\n"
                "Signed-off-by: Series A Builder <builder@example.com>\n"
            ),
        )
        self.git("reset", "--hard", nonlinear_head)
        self.assert_rejected(
            "linear single-parent",
            dco.validate_merge_group,
            self.repo,
            self.base,
            nonlinear_head,
        )

    def test_merge_group_provider_name_canonicalization_is_email_bound(self) -> None:
        provider_head = self.commit(
            "fix: provider-generated squash\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        self.assertEqual(
            dco.validate_merge_group(self.repo, self.base, provider_head),
            1,
        )

        self.git("reset", "--hard", self.base)
        wrong_email = self.commit(
            "fix: provider-generated mismatch\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <other@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        self.assert_rejected(
            "email does not exactly match",
            dco.validate_merge_group,
            self.repo,
            self.base,
            wrong_email,
        )

        self.git("reset", "--hard", self.base)
        wrong_case = self.commit(
            "fix: provider-generated case mismatch\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <Builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        self.assert_rejected(
            "email does not exactly match",
            dco.validate_merge_group,
            self.repo,
            self.base,
            wrong_case,
        )

    def test_push_identity_contract(self) -> None:
        head = self.commit("fix: push\n\nSigned-off-by: Series A Builder <builder@example.com>")
        payload = {"ref": "refs/heads/main", "before": self.base, "after": head}
        self.assertEqual(dco.push_subject(payload, head), (self.base, head))
        self.assert_rejected("not main", dco.push_subject, {**payload, "ref": "refs/heads/dev"}, head)

    def test_fetch_pull_head_uses_exact_ref_without_persisting_credentials(self) -> None:
        expected_head = "d" * 40
        token = "fake-read-token"
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        inherited_config = {
            "GITHUB_SERVER_URL": "https://github.example",
            "GIT_CONFIG_COUNT": "10",
            "GIT_CONFIG_KEY_9": "malicious.inherited",
            "GIT_CONFIG_VALUE_9": "ignored",
            "GIT_TRACE_CURL": "1",
            "GIT_CURL_VERBOSE": "1",
        }
        with (
            mock.patch.dict(dco.os.environ, inherited_config, clear=False),
            mock.patch.object(
                dco.subprocess,
                "run",
                return_value=completed,
            ) as fetch_run,
            mock.patch.object(
                dco,
                "git",
                side_effect=[expected_head + "\n", "commit\n"],
            ) as git_call,
        ):
            dco.fetch_pull_head(
                self.repo,
                "szl-holdings/.github",
                411,
                expected_head,
                token,
            )

        command = fetch_run.call_args.args[0]
        environment = fetch_run.call_args.kwargs["env"]
        self.assertEqual(
            command,
            [
                "git",
                "fetch",
                "--no-tags",
                "https://github.example/szl-holdings/.github.git",
                "refs/pull/411/head",
            ],
        )
        self.assertNotIn(token, repr(command))
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["GIT_TRACE_REDACT"], "1")
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(
            environment["GIT_CONFIG_KEY_0"],
            "http.https://github.example/szl-holdings/.github.git.extraheader",
        )
        self.assertEqual(
            environment["GIT_CONFIG_VALUE_0"],
            "AUTHORIZATION: basic "
            + base64.b64encode(f"x-access-token:{token}".encode()).decode(),
        )
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "credential.helper")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "")
        self.assertNotIn("GIT_CONFIG_KEY_9", environment)
        self.assertNotIn("GIT_CONFIG_VALUE_9", environment)
        self.assertNotIn("GIT_TRACE_CURL", environment)
        self.assertNotIn("GIT_CURL_VERBOSE", environment)
        self.assertEqual(
            git_call.call_args_list,
            [
                mock.call(self.repo, "rev-parse", "FETCH_HEAD"),
                mock.call(self.repo, "cat-file", "-t", expected_head),
            ],
        )

        with (
            mock.patch.dict(dco.os.environ, inherited_config, clear=False),
            mock.patch.object(
                dco.subprocess,
                "run",
                return_value=completed,
            ),
            mock.patch.object(dco, "git", return_value="e" * 40 + "\n"),
        ):
            self.assert_rejected(
                "differs from the associated pull request",
                dco.fetch_pull_head,
                self.repo,
                "szl-holdings/.github",
                411,
                expected_head,
                token,
            )

    def test_push_provider_name_canonicalization_requires_exact_source_dco(self) -> None:
        source_first = self.commit(
            "fix: source one\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        source_head = self.commit(
            "fix: source two\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        source_shas = [source_first, source_head]
        self.git("reset", "--hard", self.base)
        protected_parent = self.commit(
            "fix: intervening protected main change\n\n"
            "Signed-off-by: Series A Builder <builder@example.com>"
        )
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, calls, paths = self.provider_api(
            head,
            source_shas,
            source_head,
            pr_base_sha=self.base,
        )
        source_fetches: list[tuple[int, str]] = []

        self.assertEqual(
            dco.validate_push_range(
                self.repo,
                protected_parent,
                head,
                "szl-holdings/.github",
                "",
                api_get=api_get,
                source_fetch=lambda number, sha: source_fetches.append(
                    (number, sha)
                ),
            ),
            1,
        )
        self.assertEqual(source_fetches, [(411, source_head)])
        self.assertEqual(
            calls,
            [
                paths["commit"],
                paths["pulls_page"],
                paths["pulls_boundary"],
                paths["metadata"],
                paths["commits_page"],
                paths["commits_boundary"],
                paths["metadata"],
            ],
        )

        self.git("reset", "--hard", self.base)
        strict = self.commit(
            "fix: strict push\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        self.assertEqual(
            dco.validate_push_range(
                self.repo,
                self.base,
                strict,
                "szl-holdings/.github",
                "",
                api_get=lambda path: self.fail(f"unexpected provider lookup: {path}"),
            ),
            1,
        )

    def test_push_exact_identity_provider_squash_rejects_unsigned_source(self) -> None:
        unsigned_source = self.commit(
            "fix: unsigned provider source",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: exact-identity provider squash (#411)\n\n"
            "Signed-off-by: Lutar, Stephen P. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, calls, paths = self.provider_api(
            head,
            [unsigned_source],
            unsigned_source,
        )
        source_fetches: list[tuple[int, str]] = []

        self.assert_rejected(
            "no valid terminal",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: source_fetches.append((number, sha)),
        )
        self.assertIn(paths["commit"], calls)
        self.assertIn(paths["commits_page"], calls)
        self.assertEqual(source_fetches, [(411, unsigned_source)])

    def test_push_exact_identity_provider_squash_validates_all_sources(self) -> None:
        source_first = self.commit(
            "fix: first exact-identity source\n\n"
            "Signed-off-by: Lutar, Stephen P. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        source_head = self.commit(
            "fix: second exact-identity source\n\n"
            "Signed-off-by: Lutar, Stephen P. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: exact-identity provider squash (#411)\n\n"
            "Signed-off-by: Lutar, Stephen P. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, calls, paths = self.provider_api(
            head,
            [source_first, source_head],
            source_head,
        )
        source_fetches: list[tuple[int, str]] = []

        self.assertEqual(
            dco.validate_push_range(
                self.repo,
                self.base,
                head,
                "szl-holdings/.github",
                "",
                api_get=api_get,
                source_fetch=lambda number, sha: source_fetches.append((number, sha)),
            ),
            1,
        )
        self.assertIn(paths["commit"], calls)
        self.assertIn(paths["commits_page"], calls)
        self.assertEqual(source_fetches, [(411, source_head)])

    def test_push_provider_canonicalization_fails_closed(self) -> None:
        source_head = self.commit(
            "fix: governed source\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        for case, error in (
            ("verification", "not validly signed"),
            ("account", "web-flow"),
            ("merge", "unique exact merged"),
            ("base_ref", "does not target"),
        ):
            with self.subTest(case=case):
                api_get, responses, _, paths = self.provider_api(
                    head,
                    [source_head],
                    source_head,
                )
                commit_response = responses[paths["commit"]]
                associated_pull = responses[paths["pulls_page"]][0]
                if case == "verification":
                    verification = commit_response["commit"]["verification"]
                    verification.update(
                        {
                            "verified": False,
                            "reason": "unsigned",
                            "signature": None,
                            "payload": None,
                        }
                    )
                elif case == "account":
                    commit_response["committer"]["login"] = "attacker"
                elif case == "merge":
                    associated_pull["merge_commit_sha"] = "f" * 40
                else:
                    associated_pull["base"]["ref"] = "release/unsafe"

                with self.assertRaisesRegex(dco.DcoContractError, error):
                    dco.validate_push_range(
                        self.repo,
                        self.base,
                        head,
                        "szl-holdings/.github",
                        "",
                        api_get=api_get,
                        source_fetch=lambda number, sha: None,
                    )

        self.git("reset", "--hard", self.base)
        wrong_email = self.commit(
            "fix: provider mismatch (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <other@example.com>",
            name="Lutar, Stephen P.",
            email="builder@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        with self.assertRaisesRegex(dco.DcoContractError, "email does not exactly match"):
            dco.validate_push_range(
                self.repo,
                self.base,
                wrong_email,
                "szl-holdings/.github",
                "",
                api_get=lambda path: self.fail(f"unexpected provider lookup: {path}"),
            )

    def test_push_provider_source_validation_uses_overall_push_head(self) -> None:
        source_head = self.commit(
            "fix: source before a batched push\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        self.git("reset", "--hard", self.base)
        provider_squash = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        push_head = self.commit(
            "fix: later strict push commit\n\n"
            "Signed-off-by: Series A Builder <builder@example.com>"
        )
        api_get, _, _, _ = self.provider_api(
            provider_squash,
            [source_head],
            source_head,
        )

        self.assertEqual(
            dco.validate_push_range(
                self.repo,
                self.base,
                push_head,
                "szl-holdings/.github",
                "",
                api_get=api_get,
                source_fetch=lambda number, sha: None,
            ),
            2,
        )

    def test_push_provider_validates_two_source_bound_squashes(self) -> None:
        source_one = self.commit(
            "fix: first queued source\n\n"
            "Signed-off-by: Source One <one@example.com>",
            name="Source One",
            email="one@example.com",
        )
        self.git("reset", "--hard", self.base)
        source_two = self.commit(
            "fix: second queued source\n\n"
            "Signed-off-by: Source Two <two@example.com>",
            name="Source Two",
            email="two@example.com",
        )
        self.git("reset", "--hard", self.base)
        squash_one = self.commit(
            "fix: first provider squash (#411)\n\n"
            "Signed-off-by: Source One <one@example.com>",
            name="Canonical One",
            email="one@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        squash_two = self.commit(
            "fix: second provider squash (#412)\n\n"
            "Signed-off-by: Source Two <two@example.com>",
            name="Canonical Two",
            email="two@example.com",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        _, responses_one, _, _ = self.provider_api(
            squash_one,
            [source_one],
            source_one,
            number=411,
        )
        _, responses_two, _, _ = self.provider_api(
            squash_two,
            [source_two],
            source_two,
            number=412,
            pr_base_sha=self.base,
        )
        responses = {**responses_one, **responses_two}

        def api_get(path: str):
            if path not in responses:
                raise AssertionError(f"unexpected provider lookup: {path}")
            return responses[path]

        self.assertEqual(
            dco.validate_push_range(
                self.repo,
                self.base,
                squash_two,
                "szl-holdings/.github",
                "",
                api_get=api_get,
                source_fetch=lambda number, sha: None,
            ),
            2,
        )

    def test_push_provider_squash_binds_exact_pr_base_and_head(self) -> None:
        source_head = self.commit(
            "fix: exact source refs\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )

        api_get, responses, _, paths = self.provider_api(
            head,
            [source_head],
            source_head,
        )
        responses[paths["pulls_page"]][0]["base"]["sha"] = "e" * 40
        self.assert_rejected(
            "pull-request base moved during validation",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

        api_get, responses, _, paths = self.provider_api(
            head,
            [source_head],
            source_head,
        )
        responses[paths["pulls_page"]][0]["head"]["sha"] = "d" * 40
        self.assert_rejected(
            "pull-request head moved during validation",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

        tree = self.git("rev-parse", f"{self.base}^{{tree}}")
        unrelated_base = self.git(
            "commit-tree",
            tree,
            input_text=(
                "chore: unrelated base\n\n"
                "Signed-off-by: Series A Builder <builder@example.com>\n"
            ),
        )
        api_get, _, _, _ = self.provider_api(
            head,
            [source_head],
            source_head,
            pr_base_sha=unrelated_base,
        )
        self.assert_rejected(
            "base is not an ancestor of the squash parent",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

    def test_push_provider_squash_rejects_invalid_raw_source_history(self) -> None:
        source_first = self.commit(
            "fix: signed source one\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        unsigned_middle = self.commit(
            "fix: unsigned source middle",
            name="Stephen P. Lutar Jr.",
        )
        source_head = self.commit(
            "fix: signed source head\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        source_shas = [source_first, unsigned_middle, source_head]
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, _, _ = self.provider_api(
            head,
            source_shas,
            source_head,
        )
        self.assert_rejected(
            "no valid terminal",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

        self.git("reset", "--hard", self.base)
        mismatched_source = self.commit(
            "fix: mismatched source\n\n"
            "Signed-off-by: Any Name <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Lutar, Stephen P.",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, _, _ = self.provider_api(
            head,
            [mismatched_source],
            mismatched_source,
        )
        self.assert_rejected(
            "does not exactly match",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

    def test_push_provider_squash_rejects_arbitrary_same_email_name(self) -> None:
        source_head = self.commit(
            "fix: valid source identity\n\n"
            "Signed-off-by: Stephen P. Lutar Jr. <builder@example.com>",
            name="Stephen P. Lutar Jr.",
        )
        self.git("reset", "--hard", self.base)
        head = self.commit(
            "fix: provider squash (#411)\n\n"
            "Signed-off-by: Any Name <builder@example.com>",
            name="Lutar, Stephen P.",
            committer_name="GitHub",
            committer_email="noreply@github.com",
        )
        api_get, _, _, _ = self.provider_api(
            head,
            [source_head],
            source_head,
        )
        self.assert_rejected(
            "not an exact validated source-commit author identity",
            dco.validate_push_range,
            self.repo,
            self.base,
            head,
            "szl-holdings/.github",
            "",
            api_get=api_get,
            source_fetch=lambda number, sha: None,
        )

    def test_pr_pagination_boundaries_and_freshness(self) -> None:
        for count in (249, 250):
            shas = [f"{number + 1:040x}" for number in range(count)]

            def api_get(path: str, rows=shas):
                if "/commits?" in path:
                    page = int(path.rsplit("page=", 1)[1])
                    start = (page - 1) * 100
                    return [{"sha": sha} for sha in rows[start : start + 100]]
                return {
                    "base": {"sha": "a" * 40},
                    "head": {"sha": rows[-1]},
                    "commits": len(rows),
                    "draft": False,
                }

            self.assertEqual(
                dco.collect_pr_commits(
                    "szl-holdings/.github", 400, "a" * 40, shas[-1], api_get
                ),
                shas,
            )

        rejected = [f"{number + 1:040x}" for number in range(251)]

        def over_limit(path: str):
            if "/commits?" in path:
                raise AssertionError("commit pages must not be fetched over the cap")
            return {
                "base": {"sha": "a" * 40},
                "head": {"sha": rejected[-1]},
                "commits": len(rejected),
                "draft": False,
            }

        self.assert_rejected(
            "supported range",
            dco.collect_pr_commits,
            "szl-holdings/.github",
            400,
            "a" * 40,
            rejected[-1],
            over_limit,
        )

    def test_draft_pr_requires_explicit_protected_controller_opt_in(self) -> None:
        head = "b" * 40

        def draft_pr(path: str):
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": head}] if page == 1 else []
            return {
                "base": {"sha": "a" * 40},
                "head": {"sha": head},
                "commits": 1,
                "draft": True,
            }

        self.assert_rejected(
            "draft pull requests cannot satisfy DCO",
            dco.collect_pr_commits,
            "szl-holdings/.github",
            400,
            "a" * 40,
            head,
            draft_pr,
        )
        self.assertEqual(
            dco.collect_pr_commits(
                "szl-holdings/.github",
                400,
                "a" * 40,
                head,
                draft_pr,
                allow_draft=True,
            ),
            [head],
        )

    def test_pr_duplicate_and_count_churn_fail(self) -> None:
        head = "b" * 40

        def duplicate(path: str):
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": head}, {"sha": head}] if page == 1 else []
            return {"base": {"sha": "a" * 40}, "head": {"sha": head}, "commits": 2, "draft": False}

        self.assert_rejected(
            "duplicate",
            dco.collect_pr_commits,
            "szl-holdings/.github",
            400,
            "a" * 40,
            head,
            duplicate,
        )

        metadata_calls = 0

        def churn(path: str):
            nonlocal metadata_calls
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": head}] if page == 1 else []
            metadata_calls += 1
            return {
                "base": {"sha": "a" * 40},
                "head": {"sha": head},
                "commits": 1 if metadata_calls == 1 else 2,
                "draft": False,
            }

        self.assert_rejected(
            "count changed",
            dco.collect_pr_commits,
            "szl-holdings/.github",
            400,
            "a" * 40,
            head,
            churn,
        )

    def test_pr_history_allows_signed_merge_and_requires_graph_parity(self) -> None:
        first = self.commit("fix: first\n\nSigned-off-by: Series A Builder <builder@example.com>")
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        message = "fix: reconcile main\n\nSigned-off-by: Series A Builder <builder@example.com>\n"
        merged = self.git("commit-tree", tree, "-p", first, "-p", self.base, input_text=message)
        self.git("reset", "--hard", merged)
        shas = self.git("rev-list", "--reverse", f"{self.base}..{merged}").splitlines()
        payload = {
            "action": "synchronize",
            "repository": {"full_name": "szl-holdings/.github"},
            "pull_request": {
                "number": 400,
                "base": {"ref": "main", "sha": self.base},
                "head": {"sha": merged},
            },
        }

        def complete(path: str):
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": sha} for sha in shas] if page == 1 else []
            return {
                "base": {"sha": self.base},
                "head": {"sha": merged},
                "commits": len(shas),
                "draft": False,
            }

        self.assertEqual(
            dco.validate_pull_request_target(
                self.repo,
                payload,
                "szl-holdings/.github",
                "token",
                complete,
            ),
            2,
        )

        payload["action"] = "edited"
        self.assertEqual(
            dco.validate_pull_request_target(
                self.repo,
                payload,
                "szl-holdings/.github",
                "token",
                complete,
            ),
            2,
        )
        payload["action"] = "synchronize"

        payload["pull_request"]["base"]["ref"] = "release/2026.08"
        self.assertEqual(
            dco.validate_pull_request_target(
                self.repo,
                payload,
                "szl-holdings/.github",
                "token",
                complete,
            ),
            2,
        )
        payload["pull_request"]["base"]["ref"] = "release/"
        self.assert_rejected(
            "not governed",
            dco.validate_pull_request_target,
            self.repo,
            payload,
            "szl-holdings/.github",
            "token",
            complete,
        )
        payload["pull_request"]["base"]["ref"] = "release/team/2026.08"
        self.assert_rejected(
            "not governed",
            dco.validate_pull_request_target,
            self.repo,
            payload,
            "szl-holdings/.github",
            "token",
            complete,
        )
        payload["pull_request"]["base"]["ref"] = "feature/unprotected"
        self.assert_rejected(
            "not governed",
            dco.validate_pull_request_target,
            self.repo,
            payload,
            "szl-holdings/.github",
            "token",
            complete,
        )
        payload["pull_request"]["base"]["ref"] = "main"

        def incomplete(path: str):
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": merged}] if page == 1 else []
            return {
                "base": {"sha": self.base},
                "head": {"sha": merged},
                "commits": 1,
                "draft": False,
            }

        self.assert_rejected(
            "differs from the checked-out history",
            dco.validate_pull_request_target,
            self.repo,
            payload,
            "szl-holdings/.github",
            "token",
            incomplete,
        )

    def test_pr_history_uses_actual_merge_base_when_main_advances(self) -> None:
        head = self.commit(
            "fix: branch work\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        self.git("reset", "--hard", self.base)
        current_base = self.commit(
            "chore: advance main\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        self.git("reset", "--hard", head)
        payload = {
            "action": "synchronize",
            "repository": {"full_name": "szl-holdings/.github"},
            "pull_request": {
                "number": 400,
                "base": {"ref": "main", "sha": current_base},
                "head": {"sha": head},
            },
        }

        def complete(path: str):
            if "/commits?" in path:
                page = int(path.rsplit("page=", 1)[1])
                return [{"sha": head}] if page == 1 else []
            return {
                "base": {"sha": current_base},
                "head": {"sha": head},
                "commits": 1,
                "draft": False,
            }

        self.assertEqual(
            dco.validate_pull_request_target(
                self.repo,
                payload,
                "szl-holdings/.github",
                "token",
                complete,
            ),
            1,
        )


class DoctrineRequiredWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = DOCTRINE_REQUIRED_WORKFLOW.read_text(encoding="utf-8")

    def assert_workflow_rejected(self, mutated: str, expected: str) -> None:
        with self.assertRaisesRegex(ValueError, f"(?:{expected}|drifted)"):
            validate_doctrine_required_workflow(mutated)

    def replace_once(self, old: str, new: str) -> str:
        self.assertEqual(self.workflow.count(old), 1, old)
        return self.workflow.replace(old, new, 1)

    def test_protected_controller_contract_is_complete(self) -> None:
        validate_doctrine_required_workflow(self.workflow)
        validate_doctrine_required_workflow(self.workflow.replace("\n", "\r\n"))
        self.assertNotIn("actions/upload-artifact", self.workflow)
        self.assertNotIn("actions/download-artifact", self.workflow)
        self.assertNotIn("github.event.pull_request.head.repo", self.workflow)
        self.assertEqual(self.workflow.count("--repo-root"), 1)
        self.assertEqual(self.workflow.count("--event-path"), 1)
        self.assertEqual(self.workflow.count("python -B "), 4)
        self.assertEqual(
            self.workflow.count("branches: [__doctrine-ruleset-only__]"),
            2,
        )
        self.assertIsNone(re.search(r"(?m)^\s+if\s*:", self.workflow))

    def test_source_identity_and_revision_drift_fail_closed(self) -> None:
        mutations = (
            (
                'test "$ACTUAL_WORKFLOW_REPOSITORY" = "szl-holdings/.github"',
                'test "$ACTUAL_WORKFLOW_REPOSITORY" = "szl-holdings/szl-doctrine"',
                "missing required Doctrine workflow marker",
            ),
            (
                "doctrine-required-dco.yml@refs/heads/main",
                "dco.yml@refs/heads/main",
                "missing required Doctrine workflow marker",
            ),
            (
                'test "$ACTUAL_WORKFLOW_FILE_PATH" = ".github/workflows/doctrine-required-dco.yml"',
                'test "$ACTUAL_WORKFLOW_FILE_PATH" = ".github/workflows/dco.yml"',
                "missing required Doctrine workflow marker",
            ),
            (
                "doctrine-required-dco.yml@refs/heads/main",
                "doctrine-required-dco.yml@refs/heads/candidate",
                "missing required Doctrine workflow marker",
            ),
            (
                "ref: ${{ job.workflow_sha }}",
                "ref: ${{ github.sha }}",
                "missing required Doctrine workflow marker",
            ),
            (
                "path: trusted-dco",
                "path: candidate-source",
                "missing required Doctrine workflow marker",
            ),
        )
        for old, new, error in mutations:
            with self.subTest(old=old, new=new):
                self.assert_workflow_rejected(self.replace_once(old, new), error)

    def test_target_identity_and_exact_graph_drift_fail_closed(self) -> None:
        mutations = (
            (
                'test "$ACTUAL_TARGET_REPOSITORY" = "szl-holdings/szl-doctrine"',
                'test "$ACTUAL_TARGET_REPOSITORY" = "$GITHUB_REPOSITORY"',
            ),
            (
                'test "$ACTUAL_TARGET_REPOSITORY_ID" = "1258631185"',
                'test "$ACTUAL_TARGET_REPOSITORY_ID" != ""',
            ),
            (
                "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.event.merge_group.head_sha }}",
                "ref: ${{ github.event_name == 'pull_request' && github.sha || github.event.merge_group.head_sha }}",
            ),
            (
                "ref: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.merge_group.base_sha }}",
                "ref: ${{ github.event_name == 'pull_request' && github.sha || github.event.merge_group.base_sha }}",
            ),
        )
        for old, new in mutations:
            with self.subTest(old=old, new=new):
                self.assert_workflow_rejected(
                    self.replace_once(old, new),
                    "missing required Doctrine workflow marker",
                )

    def test_permissions_triggers_and_effects_fail_closed(self) -> None:
        mutations = (
            ("contents: read", "contents: write", "required Doctrine workflow marker"),
            ("pull-requests: read", "pull-requests: write", "required Doctrine workflow marker"),
            (
                "  pull_request:\n",
                "  pull_request_" + "target:\n",
                "required Doctrine workflow marker",
            ),
            ("  merge_group:\n", "  workflow_dispatch:\n", "required Doctrine workflow marker"),
            (
                "permissions:\n",
                "permissions:\n  statuses: write\n",
                "required Doctrine workflow marker",
            ),
            (
                "    steps:\n",
                "    concurrency:\n      cancel-in-progress: true\n    steps:\n",
                "run cancellation",
            ),
            (
                "      - name: Checkout exact target candidate as inert graph data\n",
                "      - name: Checkout exact target candidate as inert graph data\n        continue-on-error: true\n",
                "fail-open continuation",
            ),
            (
                "      - name: Checkout exact target candidate as inert graph data\n",
                "      - name: Checkout exact target candidate as inert graph data\n        if: github.actor != 'attacker'\n",
                "cannot skip identity or validation steps",
            ),
            (
                "          GITHUB_TOKEN: ${{ github.token }}",
                "          GITHUB_TOKEN: ${{ secrets['HF_TOKEN'] }}",
                "read-only API token binding",
            ),
            (
                "          set -euo pipefail\n          test \"$ACTUAL_TARGET_REPOSITORY\"",
                "          set -euo pipefail || true\n          test \"$ACTUAL_TARGET_REPOSITORY\"",
                "fail-open shell suffix",
            ),
        )
        for old, new, error in mutations:
            with self.subTest(old=old, new=new):
                self.assert_workflow_rejected(self.replace_once(old, new), error)

    def test_candidate_bytes_cannot_be_executed(self) -> None:
        candidate_execution = self.replace_once(
            'python -B "$GITHUB_WORKSPACE/trusted-dco/.github/scripts/dco_check.py"',
            'python -B "$GITHUB_WORKSPACE/candidate/.github/scripts/dco_check.py"',
        )
        self.assert_workflow_rejected(
            candidate_execution,
            "missing required Doctrine workflow marker",
        )

        candidate_working_directory = self.replace_once(
            "      - name: Validate exact target commits with protected DCO code\n",
            "      - name: Validate exact target commits with protected DCO code\n        working-directory: candidate\n",
        )
        self.assert_workflow_rejected(
            candidate_working_directory,
            "candidate working directory",
        )

    def test_identity_check_must_precede_every_action(self) -> None:
        premature_action = self.replace_once(
            "    steps:\n",
            "    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
        )
        self.assert_workflow_rejected(premature_action, "exactly three pinned checkouts")

    def test_structural_bypass_mutations_fail_closed(self) -> None:
        job_write_all = self.replace_once(
            "    timeout-minutes: 8\n",
            "    timeout-minutes: 8\n    permissions: write-all\n",
        )
        self.assert_workflow_rejected(job_write_all, "write-all permissions")

        final_fail_open = self.replace_once(
            '--event-path "$GITHUB_EVENT_PATH"',
            '--event-path "$GITHUB_EVENT_PATH" || :',
        )
        self.assert_workflow_rejected(final_fail_open, "ordered step contract drifted")

        candidate_execution = self.replace_once(
            "          set -euo pipefail\n          test \"$(git -C \"$GITHUB_WORKSPACE/candidate\" rev-parse HEAD)\"",
            "          set -euo pipefail\n          \"$GITHUB_WORKSPACE/candidate/ci.sh\"\n          test \"$(git -C \"$GITHUB_WORKSPACE/candidate\" rev-parse HEAD)\"",
        )
        self.assert_workflow_rejected(candidate_execution, "ordered step contract drifted")

        extra_action = self.replace_once(
            "      - name: Assert exact protected DCO source revision\n",
            "      - name: Run unreviewed action\n        uses: example/unreviewed@0123456789012345678901234567890123456789\n\n      - name: Assert exact protected DCO source revision\n",
        )
        self.assert_workflow_rejected(extra_action, "ordered step contract drifted")

        second_job = self.workflow + (
            "\n  bypass:\n"
            "    permissions: write-all\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: true\n"
        )
        self.assert_workflow_rejected(second_job, "write-all permissions")

    def test_exact_byte_lock_rejects_nested_and_escaped_yaml_bypasses(self) -> None:
        source_with = (
            "          repository: ${{ job.workflow_repository }}\n"
            "          ref: ${{ job.workflow_sha }}\n"
            "          path: trusted-dco\n"
            "          fetch-depth: 1\n"
            "          persist-credentials: false\n"
        )
        candidate_name = (
            "      - name: Checkout exact target candidate as inert graph data\n"
        )
        mutations = {
            "quoted permissions": self.replace_once(
                "permissions:\n", '"permissions":\n'
            ),
            "escaped permissions": self.replace_once(
                "permissions:\n", '"permissio\\u006es":\n'
            ),
            "quoted job if": self.replace_once(
                "    name: Required DCO enforcement\n",
                '    name: Required DCO enforcement\n    "if": true\n',
            ),
            "escaped job if": self.replace_once(
                "    name: Required DCO enforcement\n",
                '    name: Required DCO enforcement\n    "i\\u0066": true\n',
            ),
            "quoted step if": self.replace_once(
                candidate_name,
                candidate_name + '        "if": false\n',
            ),
            "escaped continue-on-error": self.replace_once(
                candidate_name,
                candidate_name + '        "continue-on-erro\\u0072": true\n',
            ),
            "recursive submodules": self.replace_once(
                source_with,
                source_with.replace(
                    "          persist-credentials: false\n",
                    "          submodules: recursive\n"
                    "          persist-credentials: false\n",
                ),
            ),
            "duplicate persist credentials": self.replace_once(
                source_with,
                source_with + "          persist-credentials: true\n",
            ),
            "duplicate repository": self.replace_once(
                source_with,
                source_with.replace(
                    "          ref: ${{ job.workflow_sha }}\n",
                    "          repository: szl-holdings/szl-doctrine\n"
                    "          ref: ${{ job.workflow_sha }}\n",
                ),
            ),
            "duplicate ref": self.replace_once(
                source_with,
                source_with.replace(
                    "          path: trusted-dco\n",
                    "          ref: refs/heads/main\n"
                    "          path: trusted-dco\n",
                ),
            ),
            "unnamed candidate execution": self.replace_once(
                "      - name: Validate exact target commits with protected DCO code\n",
                "      - run: |\n"
                "          \"$GITHUB_WORKSPACE/candidate/ci.sh\"\n\n"
                "      - name: Validate exact target commits with protected DCO code\n",
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assert_workflow_rejected(mutated, "exact-byte digest drifted")


if __name__ == "__main__":
    unittest.main()
