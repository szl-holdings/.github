#!/usr/bin/env python3
"""Focused regression tests for the fail-closed DCO checker."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.error import URLError

import dco_check


API_URL = "https://api.github.test"
REPOSITORY = "szl-holdings/example"
PR_NUMBER = 399
TOKEN = "test-token"


def _commit(index: int, message: str) -> dict[str, object]:
    return {
        "sha": f"{index:040x}",
        "commit": {"message": message},
    }


def _signed_commits(count: int, *, start: int = 1) -> list[dict[str, object]]:
    return [
        _commit(
            index,
            f"fix: commit {index}\n\nSigned-off-by: Test User <test@example.com>",
        )
        for index in range(start, start + count)
    ]


def _commit_pages(commits: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    return [
        commits[index : index + dco_check.COMMITS_PER_PAGE]
        for index in range(0, len(commits), dco_check.COMMITS_PER_PAGE)
    ]


UNSIGNED_EMPTY_COMMIT = _commit(1, "chore: intentionally empty commit")
UNSIGNED_MERGE_COMMIT = _commit(
    2,
    "Merge substantive policy update\n\nThis commit changes governed behavior.",
)
SIGNED_MULTI_COMMIT_PR = [
    _commit(3, "feat: first\n\nSigned-off-by: Test User <test@example.com>"),
    _commit(4, "fix: second\n\nSigned-off-by: Other User <other@example.com>"),
]


class _Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _SequenceOpener:
    def __init__(self, *responses: object) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, request: object, timeout: int) -> _Response:
        del timeout
        self.urls.append(request.full_url)  # type: ignore[attr-defined]
        if not self._responses:
            raise AssertionError("unexpected API request")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, _Response):
            return response
        return _Response(response)


def _authoritative_responses(count: int) -> list[object]:
    commits = _signed_commits(count)
    return [{"commits": count}, *_commit_pages(commits), []]


class DcoCheckTests(unittest.TestCase):
    def test_metadata_api_retrieval_failure_fails_closed(self) -> None:
        opener = _SequenceOpener(URLError("metadata unavailable"))

        with self.assertRaisesRegex(dco_check.DcoContractError, "retrieval failed"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

    def test_commits_api_retrieval_failure_fails_closed(self) -> None:
        opener = _SequenceOpener(
            {"commits": 1},
            URLError("commits unavailable"),
        )

        with self.assertRaisesRegex(dco_check.DcoContractError, "retrieval failed"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

    def test_unexpectedly_empty_commit_list_fails_closed(self) -> None:
        opener = _SequenceOpener({"commits": 1}, [])

        with self.assertRaisesRegex(dco_check.DcoContractError, "count mismatch"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

    def test_unsigned_empty_commit_is_rejected(self) -> None:
        self.assertEqual(
            dco_check.unsigned_commit_shas([UNSIGNED_EMPTY_COMMIT]),
            [UNSIGNED_EMPTY_COMMIT["sha"]],
        )

    def test_unsigned_substantive_merge_prefixed_commit_is_rejected(self) -> None:
        self.assertEqual(
            dco_check.unsigned_commit_shas([UNSIGNED_MERGE_COMMIT]),
            [UNSIGNED_MERGE_COMMIT["sha"]],
        )

    def test_fully_signed_multi_commit_pr_passes(self) -> None:
        self.assertEqual(dco_check.unsigned_commit_shas(SIGNED_MULTI_COMMIT_PR), [])

    def test_249_commits_are_retrieved_completely(self) -> None:
        opener = _SequenceOpener(*_authoritative_responses(249))

        declared, commits = dco_check.fetch_authoritative_pr_commits(
            API_URL,
            REPOSITORY,
            PR_NUMBER,
            TOKEN,
            opener=opener,
        )

        self.assertEqual(declared, 249)
        self.assertEqual(len(commits), 249)
        self.assertTrue(opener.urls[-1].endswith("per_page=100&page=4"))

    def test_exactly_250_commits_are_retrieved_completely(self) -> None:
        opener = _SequenceOpener(*_authoritative_responses(250))

        declared, commits = dco_check.fetch_authoritative_pr_commits(
            API_URL,
            REPOSITORY,
            PR_NUMBER,
            TOKEN,
            opener=opener,
        )

        self.assertEqual(declared, 250)
        self.assertEqual(len(commits), 250)
        self.assertTrue(opener.urls[-1].endswith("per_page=100&page=4"))

    def test_251_commits_are_rejected_before_commit_pagination(self) -> None:
        opener = _SequenceOpener({"commits": 251})

        with self.assertRaisesRegex(dco_check.DcoContractError, "capped at 250"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

        self.assertEqual(len(opener.urls), 1)

    def test_declared_and_retrieved_short_count_mismatch_is_rejected(self) -> None:
        commits = _signed_commits(248)
        opener = _SequenceOpener(
            {"commits": 249},
            *_commit_pages(commits),
        )

        with self.assertRaisesRegex(dco_check.DcoContractError, "count mismatch"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

    def test_nonempty_boundary_page_count_mismatch_is_rejected(self) -> None:
        commits = _signed_commits(249)
        opener = _SequenceOpener(
            {"commits": 249},
            *_commit_pages(commits),
            [_signed_commits(1, start=250)[0]],
        )

        with self.assertRaisesRegex(dco_check.DcoContractError, "count mismatch"):
            dco_check.fetch_authoritative_pr_commits(
                API_URL,
                REPOSITORY,
                PR_NUMBER,
                TOKEN,
                opener=opener,
            )

    def test_workflow_contains_no_message_prefix_or_file_count_bypass(self) -> None:
        workflow_path = Path(__file__).parents[1] / "workflows" / "dco.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertNotIn("head_commit.message", workflow)
        self.assertNotIn("changed_files", workflow)
        self.assertIn("dco_check.py", workflow)


if __name__ == "__main__":
    unittest.main()
