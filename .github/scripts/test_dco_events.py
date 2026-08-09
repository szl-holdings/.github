#!/usr/bin/env python3
"""Executable adversarial contract for the trusted DCO checker."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import dco_check as dco


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
    ) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
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
        self.assert_rejected("does not match", dco.validate_range, self.repo, self.base, head)

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

    def test_merge_group_validates_constituents_not_synthetic_head(self) -> None:
        candidate = self.commit(
            "fix: queued change\n\nSigned-off-by: Series A Builder <builder@example.com>"
        )
        tree = self.git("rev-parse", f"{candidate}^{{tree}}")
        queue_head = self.git(
            "commit-tree",
            tree,
            "-p",
            self.base,
            "-p",
            candidate,
            input_text="Merge queue candidate\n",
        )
        self.git("reset", "--hard", queue_head)

        self.assertEqual(
            dco.validate_merge_group(self.repo, self.base, queue_head),
            1,
        )

        self.git("reset", "--hard", self.base)
        unsigned = self.commit("fix: unsigned queued change")
        tree = self.git("rev-parse", f"{unsigned}^{{tree}}")
        unsigned_queue_head = self.git(
            "commit-tree",
            tree,
            "-p",
            self.base,
            "-p",
            unsigned,
            input_text="Merge queue candidate\n",
        )
        self.git("reset", "--hard", unsigned_queue_head)
        self.assert_rejected(
            "no valid terminal",
            dco.validate_merge_group,
            self.repo,
            self.base,
            unsigned_queue_head,
        )

    def test_push_identity_contract(self) -> None:
        head = self.commit("fix: push\n\nSigned-off-by: Series A Builder <builder@example.com>")
        payload = {"ref": "refs/heads/main", "before": self.base, "after": head}
        self.assertEqual(dco.push_subject(payload, head), (self.base, head))
        self.assert_rejected("not main", dco.push_subject, {**payload, "ref": "refs/heads/dev"}, head)

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

if __name__ == "__main__":
    unittest.main()
