#!/usr/bin/env python3
"""Offline regression coverage. Every repository and PR below is synthetic."""
from __future__ import annotations

import copy
import pathlib
import socket
import unittest
from unittest.mock import patch

from final_estate_v5_core import GitHubClient
from final_estate_v5_inventory import CensusError, PublicPullRequestObserver
from final_estate_v5_probes import evaluate_open_public_prs

ORG = "szl-holdings"
API = "https://api.github.com"


def repository(name: str, identity: int) -> dict:
    return {"id": identity, "full_name": f"{ORG}/{name}", "private": False,
            "visibility": "public", "owner": {"login": ORG}, "archived": False}


def pull(number: int = 1, *, name: str = "a11oy", identity: int | None = None, search: bool = True) -> dict:
    full = f"{ORG}/{name}"
    row = {"id": identity if identity is not None else number + 1000,
           "number": number, "state": "open", "draft": True,
           "title": "SYNTHETIC fixture", "updated_at": "2026-09-16T00:00:00Z",
           "html_url": f"https://github.com/{full}/pull/{number}"}
    if search:
        row.update(repository_url=f"{API}/repos/{full}",
                   pull_request={"url": f"{API}/repos/{full}/pulls/{number}"})
    else:
        row.update(url=f"{API}/repos/{full}/pulls/{number}",
                   base={"repo": {"full_name": full, "private": False}})
    return row


class Response:
    def __init__(self, value):
        self.value = value

    def json(self):
        if isinstance(self.value, Exception):
            raise self.value
        return copy.deepcopy(self.value)


class Transport:
    def __init__(self):
        self.search = {"total_count": 0, "incomplete_results": False, "items": []}
        self.repositories = [repository(".github", 1), repository("a11oy", 2)]
        self.count = 2
        self.prs = {}
        self.calls = []
        self.hook = None

    def __call__(self, method, path, *, params=None, **kwargs):
        if method != "GET" or kwargs:
            raise AssertionError("The inventory must only perform GET reads")
        params = params or {}
        self.calls.append((method, path, copy.deepcopy(params)))
        if self.hook:
            replacement = self.hook(path, params, self)
            if replacement is not None:
                return Response(replacement)
        if path == "/search/issues":
            if isinstance(self.search, list):
                return Response(self.search[params["page"] - 1])
            return Response(self.search)
        if path == f"/orgs/{ORG}":
            return Response({"login": ORG, "public_repos": self.count})
        if path == f"/orgs/{ORG}/repos":
            start = (params["page"] - 1) * params["per_page"]
            return Response(self.repositories[start:start + params["per_page"]])
        if path.startswith(f"/repos/{ORG}/") and path.endswith("/pulls"):
            name = path.split("/")[3]
            start = (params["page"] - 1) * params["per_page"]
            rows = self.prs.get(name, [])
            return Response(rows[start:start + params["per_page"]])
        raise AssertionError(f"Unexpected test path: {path}")


def gate(transport):
    client = GitHubClient(None)
    client.request = transport
    return evaluate_open_public_prs(client), client


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.no_network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in fixtures"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)


class PriorFalseGreenRegressionTests(OfflineTests):
    """Run these methods against unchanged prior core/probe source to reproduce."""
    def test_missing_search_payload_cannot_prove_zero(self):
        t = Transport(); t.search = {}
        self.assertFalse(gate(t)[0].ok)

    def test_null_items_cannot_prove_zero(self):
        t = Transport(); t.search["items"] = None
        self.assertFalse(gate(t)[0].ok)

    def test_incomplete_search_cannot_prove_zero(self):
        t = Transport(); t.search["incomplete_results"] = True
        self.assertFalse(gate(t)[0].ok)

    def test_positive_total_empty_items_cannot_prove_zero(self):
        t = Transport(); t.search["total_count"] = 40
        self.assertFalse(gate(t)[0].ok)

    def test_issue_rows_cannot_disappear_into_zero(self):
        t = Transport(); t.search.update(total_count=1, items=[{"id": 1, "number": 1, "state": "open"}])
        self.assertFalse(gate(t)[0].ok)

    def test_scoped_repository_listing_cannot_prove_zero(self):
        t = Transport(); t.count = 3
        self.assertFalse(gate(t)[0].ok)

    def test_zero_search_is_checked_against_repository_pull_lists(self):
        t = Transport(); t.prs["a11oy"] = [pull(search=False)]
        result, _ = gate(t)
        self.assertFalse(result.ok)
        self.assertEqual(result.evidence["open_pull_requests"][0]["number"], 1)

    def test_unreadable_repository_cannot_prove_zero(self):
        t = Transport()
        t.hook = lambda p, _q, _t: RuntimeError("SYNTHETIC redacted failure") if p.endswith("/pulls") else None
        self.assertFalse(gate(t)[0].ok)

    def test_fake_empty_client_without_census_cannot_authorize(self):
        class IncompleteClient:
            def open_public_pull_requests(self):
                return []
        self.assertFalse(evaluate_open_public_prs(IncompleteClient()).ok)

    def test_missing_source_repository_cannot_authorize(self):
        t = Transport(); t.repositories[1] = repository("other", 2)
        self.assertFalse(gate(t)[0].ok)

    def test_repository_membership_change_cannot_authorize(self):
        t = Transport()
        def hook(p, q, current):
            seen = sum(path == f"/orgs/{ORG}/repos" for _, path, _ in current.calls)
            if p == f"/orgs/{ORG}/repos" and seen >= 2:
                return [repository(".github", 1), repository("a11oy", 999)]
            return None
        t.hook = hook
        self.assertFalse(gate(t)[0].ok)

    def test_new_pull_during_second_read_cannot_authorize(self):
        t = Transport()
        def hook(p, q, current):
            seen = sum(path == f"/repos/{ORG}/a11oy/pulls" for _, path, _ in current.calls)
            if p == f"/repos/{ORG}/a11oy/pulls" and seen >= 2:
                return [pull(search=False)]
            return None
        t.hook = hook
        self.assertFalse(gate(t)[0].ok)


class InventoryContractTests(OfflineTests):
    def test_complete_empty_census_is_allowed_and_bound(self):
        result, client = gate(Transport())
        self.assertTrue(result.ok)
        e = client.public_pr_observation
        self.assertTrue(e["zero_closure_authorized"])
        self.assertEqual(e["public_repositories_queried_twice"], 2)
        self.assertEqual(len(e["repository_membership_sha256"]), 64)
        self.assertFalse(e["atomic_snapshot"])
        self.assertFalse(e["source_content_audit"])

    def test_positive_search_blocks_without_slow_census(self):
        t = Transport(); t.search.update(total_count=1, items=[pull()])
        result, client = gate(t)
        self.assertFalse(result.ok)
        self.assertEqual(len(t.calls), 1)
        self.assertFalse(client.public_pr_observation["zero_closure_authorized"])

    def test_pagination_collects_all_101_results(self):
        t = Transport(); t.search = [
            {"total_count": 101, "incomplete_results": False, "items": [pull(n) for n in range(1, 101)]},
            {"total_count": 101, "incomplete_results": False, "items": [pull(101)]}]
        result, _ = gate(t)
        self.assertEqual(len(result.evidence["open_pull_requests"]), 101)
        self.assertFalse(result.ok)

    def test_100_search_results_need_no_extra_page(self):
        t = Transport(); t.search.update(total_count=100, items=[pull(n) for n in range(1, 101)])
        self.assertEqual(len(PublicPullRequestObserver(t).observe().items), 100)
        self.assertEqual(len(t.calls), 1)

    def test_search_total_change_rejects_mixed_snapshot(self):
        t = Transport(); t.search = [
            {"total_count": 101, "incomplete_results": False, "items": [pull(n) for n in range(1, 101)]},
            {"total_count": 102, "incomplete_results": False, "items": [pull(101), pull(102)]}]
        with self.assertRaisesRegex(CensusError, "SEARCH_MOVED"):
            PublicPullRequestObserver(t).observe()

    def test_search_duplicate_ids_rejected(self):
        t = Transport(); t.search.update(total_count=2, items=[pull(1), pull(2, identity=1001)])
        with self.assertRaisesRegex(CensusError, "SEARCH_DUPLICATE"):
            PublicPullRequestObserver(t).observe()

    def test_search_duplicate_locations_rejected(self):
        t = Transport(); t.search.update(total_count=2, items=[pull(1), pull(1, identity=2000)])
        with self.assertRaisesRegex(CensusError, "SEARCH_DUPLICATE"):
            PublicPullRequestObserver(t).observe()

    def test_no_partial_count_after_missing_search_page(self):
        t = Transport(); t.search.update(total_count=101, items=[pull()])
        result, _ = gate(t)
        self.assertFalse(result.ok)
        self.assertEqual(result.evidence, {})

    def test_101_public_repositories_paginate_and_recheck(self):
        t = Transport(); t.repositories.extend(repository(f"r{i:03}", i + 3) for i in range(99)); t.count = 101
        result, client = gate(t)
        self.assertTrue(result.ok)
        self.assertEqual(client.public_pr_observation["public_repositories_queried_twice"], 101)
        self.assertEqual(sum(p.endswith("/pulls") for _, p, _ in t.calls), 202)

    def test_archived_repositories_are_not_silently_excluded(self):
        t = Transport(); t.repositories[1]["archived"] = True; t.prs["a11oy"] = [pull(search=False)]
        self.assertFalse(gate(t)[0].ok)

    def test_all_repository_pull_pages_are_collected(self):
        t = Transport(); t.prs["a11oy"] = [pull(n, search=False) for n in range(1, 102)]
        result, client = gate(t)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.evidence["open_pull_requests"]), 101)
        self.assertTrue(client.public_pr_observation["search_disagrees"])

    def test_repeated_repository_pull_page_is_rejected(self):
        t = Transport()
        t.hook = lambda p, q, current: [pull(n, search=False) for n in range(1, 101)] if p.endswith("a11oy/pulls") else None
        with self.assertRaisesRegex(CensusError, "PULL_DUPLICATE"):
            PublicPullRequestObserver(t).observe()

    def test_duplicate_repository_ids_are_rejected(self):
        t = Transport(); t.repositories[1]["id"] = 1
        self.assertFalse(gate(t)[0].ok)

    def test_duplicate_repository_names_are_rejected(self):
        t = Transport(); t.repositories[1]["full_name"] = f"{ORG}/.github"
        self.assertFalse(gate(t)[0].ok)

    def test_org_count_change_is_rejected(self):
        t = Transport()
        def hook(p, q, current):
            count = sum(path == f"/orgs/{ORG}" for _, path, _ in current.calls)
            if p == f"/orgs/{ORG}" and count >= 2:
                return {"login": ORG, "public_repos": 3}
            return None
        t.hook = hook
        self.assertFalse(gate(t)[0].ok)

    def test_new_repository_after_final_pull_read_is_rejected(self):
        t = Transport()
        def hook(p, q, current):
            count = sum(path == f"/orgs/{ORG}" for _, path, _ in current.calls)
            if p == f"/orgs/{ORG}" and count >= 3:
                return {"login": ORG, "public_repos": 3}
            return None
        t.hook = hook
        self.assertFalse(gate(t)[0].ok)

    def test_fixed_org_identity_is_checked(self):
        t = Transport(); t.hook = lambda p, q, c: {"login": "other", "public_repos": 2} if p == f"/orgs/{ORG}" else None
        self.assertFalse(gate(t)[0].ok)

    def test_rejected_response_does_not_echo_exception_or_token(self):
        t = Transport(); t.hook = lambda p, q, c: RuntimeError("SYNTHETIC_SECRET_NOT_FOR_OUTPUT")
        result, client = gate(t)
        self.assertFalse(result.ok)
        self.assertNotIn("SYNTHETIC_SECRET", result.detail)
        self.assertIsNone(client.public_pr_observation)

    def test_prior_evidence_is_cleared_after_failed_reobservation(self):
        t = Transport(); _, client = gate(t)
        self.assertIsNotNone(client.public_pr_observation)
        t.search = {}
        self.assertFalse(evaluate_open_public_prs(client).ok)
        self.assertIsNone(client.public_pr_observation)

    def test_expired_deadline_prevents_request(self):
        t = Transport(); now = [0.0]; observer = PublicPullRequestObserver(t, clock=lambda: now[0]); now[0] = 481.0
        with self.assertRaisesRegex(CensusError, "OBSERVATION_BUDGET"):
            observer.observe()
        self.assertEqual(t.calls, [])

    def test_deadline_after_response_prevents_acceptance(self):
        t = Transport(); now = [0.0]; observer = PublicPullRequestObserver(t, clock=lambda: now[0])
        def hook(p, q, c):
            now[0] = 481.0
        t.hook = hook
        with self.assertRaisesRegex(CensusError, "OBSERVATION_BUDGET"):
            observer.observe()

    def test_request_budget_prevents_request(self):
        t = Transport(); observer = PublicPullRequestObserver(t); observer.calls = 512
        with self.assertRaisesRegex(CensusError, "OBSERVATION_BUDGET"):
            observer.observe()
        self.assertEqual(t.calls, [])

    def test_existing_workflows_execute_the_new_suite(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "workflows"
        for name in ("final-estate-reconciliation-v5.yml", "final-estate-reconciliation-v5-pr.yml"):
            text = (root / name).read_text()
            self.assertIn("python .github/scripts/test_final_estate_v5_inventory.py", text)
            self.assertIn("      - .github/scripts/test_final_estate_v5_inventory.py", text)
            self.assertIn("      - .github/scripts/final_estate_v5_inventory.py", text)


def search_case(field, value):
    def test(self):
        t = Transport(); t.search[field] = copy.deepcopy(value)
        self.assertFalse(gate(t)[0].ok)
    return test


for name, field, value in (
    ("boolean_total", "total_count", True),
    ("float_total", "total_count", 0.0),
    ("negative_total", "total_count", -1),
    ("overbound_total", "total_count", 1001),
    ("string_total", "total_count", "0"),
    ("null_total", "total_count", None),
    ("string_false", "incomplete_results", "false"),
    ("integer_false", "incomplete_results", 0),
    ("null_incomplete", "incomplete_results", None),
    ("object_items", "items", {}),
    ("string_items", "items", ""),
    ("boolean_items", "items", False),
    ("nonpr_item", "items", [None]),
):
    setattr(InventoryContractTests, "test_search_rejects_" + name, search_case(field, value))


def item_case(field, value, *, native=False):
    def test(self):
        t = Transport(); row = pull(search=not native); row[field] = copy.deepcopy(value)
        if native:
            t.prs["a11oy"] = [row]
        else:
            t.search.update(total_count=1, items=[row])
        self.assertFalse(gate(t)[0].ok)
    return test


for name, field, value in (
    ("boolean_number", "number", True),
    ("zero_number", "number", 0),
    ("string_id", "id", "1001"),
    ("closed_state", "state", "closed"),
    ("unknown_draft", "draft", None),
    ("null_discriminator", "pull_request", None),
    ("foreign_pr_uri", "pull_request", {"url": "https://example.invalid/pull/1"}),
    ("wrong_org", "repository_url", "https://api.github.com/repos/other/a11oy"),
    ("path_injection", "repository_url", "https://api.github.com/repos/szl-holdings/a11oy/../../other"),
    ("mismatched_web_id", "html_url", "https://github.com/szl-holdings/a11oy/pull/2"),
):
    setattr(InventoryContractTests, "test_item_rejects_" + name, item_case(field, value))

for name, field, value in (
    ("null_base", "base", None),
    ("private_base", "base", {"repo": {"full_name": "szl-holdings/a11oy", "private": True}}),
    ("foreign_base", "base", {"repo": {"full_name": "other/a11oy", "private": False}}),
    ("api_id_mismatch", "url", "https://api.github.com/repos/szl-holdings/a11oy/pulls/2"),
):
    setattr(InventoryContractTests, "test_native_item_rejects_" + name, item_case(field, value, native=True))


def repository_case(field, value):
    def test(self):
        t = Transport(); t.repositories[1][field] = copy.deepcopy(value)
        self.assertFalse(gate(t)[0].ok)
    return test


for name, field, value in (
    ("private", "private", True), ("missing_visibility", "private", None),
    ("conflicting_visibility", "visibility", "private"),
    ("boolean_id", "id", True), ("null_owner", "owner", None),
    ("wrong_owner", "owner", {"login": "other"}),
    ("foreign_repository", "full_name", "other/a11oy"),
    ("path_injection", "full_name", "szl-holdings/a11oy/../outside"),
):
    setattr(InventoryContractTests, "test_repository_rejects_" + name, repository_case(field, value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
