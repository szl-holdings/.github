#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic offline cases for coverage, source movement, and commitments."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import estate_operational_inventory as inventory

HEAD = "a" * 40
TREE = "b" * 40


def repository(name="synthetic", **changes):
    value = {"id": "R_" + name, "name": name, "isPrivate": False, "isArchived": False,
             "description": "Synthetic", "licenseInfo": {"spdxId": "Apache-2.0"},
             "defaultBranchRef": {"name": "main", "target": {"oid": HEAD,
                 "tree": {"oid": TREE, "entries": [{"name": "README.md", "type": "blob"}]},
                 "statusCheckRollup": {"state": "SUCCESS"}}}}
    value.update(changes)
    return value


def page(rows, count=None, next_page=False, cursor=None, **changes):
    value = {"data": {"organization": {"repositories": {
        "nodes": copy.deepcopy(rows), "totalCount": len(rows) if count is None else count,
        "pageInfo": {"hasNextPage": next_page, "endCursor": cursor}}}}}
    value.update(changes)
    return value


class CoverageTests(unittest.TestCase):
    def test_pagination_is_coverage_checked(self):
        first = [repository(f"synthetic-{index}") for index in range(100)]
        responses = iter([page(first, 101, True, "next"), page([repository("last")], 101)])
        rows, coverage = inventory.census(lambda *_: next(responses))
        self.assertEqual(len(rows), 101)
        self.assertEqual(coverage["state"], "OBSERVED")

    def test_duplicate_identity_and_private_rows_fail_closed(self):
        cases = [[repository(), repository("other", id="R_synthetic")],
                 [repository(), repository("private", isPrivate=True)]]
        for rows in cases:
            with self.subTest(rows=len(rows)):
                result, coverage = inventory.census(lambda *_: page(rows))
                self.assertEqual(list(result), ["synthetic"])
                self.assertEqual(coverage["state"], "PARTIAL")

    def test_graphql_errors_preserve_observed_rows_without_passing(self):
        rows, coverage = inventory.census(lambda *_: page([repository()], errors=[{"message": "not serialized"}]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(coverage["failures"], ["GRAPHQL_PARTIAL_DATA"])

    def test_missing_terminal_rows_cannot_satisfy_reported_count(self):
        _, coverage = inventory.census(lambda *_: page([repository()], count=2))
        self.assertEqual(coverage["failures"], ["CENSUS_CARDINALITY"])

    def test_cursor_and_count_movement_cannot_pass(self):
        rows = [repository(f"synthetic-{index}") for index in range(100)]
        responses = iter([page(rows, 101, True, "next"), page([repository("last")], 102)])
        observed, coverage = inventory.census(lambda *_: next(responses))
        self.assertEqual(len(observed), 100)
        self.assertEqual(coverage["failures"], ["CENSUS_COUNT_MOVED"])
        _, coverage = inventory.census(lambda *_: page([repository()], count=101, next_page=True, cursor="next"))
        self.assertEqual(coverage["failures"], ["CENSUS_CURSOR"])


class SourceTests(unittest.TestCase):
    def test_success_rollup_cannot_establish_required_ci_or_readiness(self):
        row = inventory.project({"synthetic": repository()})[0]
        self.assertEqual(row["ci"]["state"], "SUCCESS")
        self.assertFalse(row["ci"]["required_checks_known"])
        self.assertEqual(row["readiness"], "NOT_OBSERVED")

    def test_empty_repo_and_malformed_tree_do_not_become_present(self):
        row = inventory.project({"synthetic": repository(defaultBranchRef=None)})[0]
        self.assertEqual(row["head_state"], "UNKNOWN")
        self.assertEqual(row["documents"]["README"], "UNKNOWN")
        with self.assertRaises(inventory.ObservationError):
            inventory.documents([{"name": "README.md", "type": None}])

    def test_malformed_nested_provider_data_preserves_other_rows(self):
        bad = repository("bad")
        bad["defaultBranchRef"]["target"]["statusCheckRollup"] = []
        rows = inventory.project({"bad": bad, "good": repository("good")})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["failures"], ["HEAD_OR_TREE_UNAVAILABLE"])
        self.assertEqual(rows[1]["ci"]["state"], "SUCCESS")
        inventory.recheck(lambda *_: [], rows)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["head_state"] == "UNKNOWN_RECHECK" for row in rows))

    def test_recheck_is_sha_pinned_and_head_movement_is_reported(self):
        rows = inventory.project({"synthetic": repository()})
        def request(query):
            self.assertIn(f'{HEAD}:.github', query)
            self.assertNotIn("HEAD:.github", query)
            return {"data": {"r0": {"object": {"entries": [{"name": "SECURITY.md", "type": "blob"}]},
                                      "defaultBranchRef": {"target": {"oid": "c" * 40}}}}}
        inventory.recheck(request, rows)
        self.assertEqual(rows[0]["head_state"], "MOVED")
        self.assertIn("DEFAULT_HEAD_MOVED", rows[0]["failures"])
        self.assertEqual(rows[0]["documents"]["SECURITY"], "PRESENT")

    def test_failed_recheck_does_not_infer_missing_security_document(self):
        rows = inventory.project({"synthetic": repository()})
        inventory.recheck(lambda *_: {"errors": [{"message": "unavailable"}]}, rows)
        self.assertEqual(rows[0]["documents"]["SECURITY"], "UNKNOWN")
        self.assertEqual(rows[0]["head_state"], "UNKNOWN_RECHECK")

    def test_transport_refuses_mutation_and_discards_stderr(self):
        client = inventory.GitHubGraphQL()
        with self.assertRaises(inventory.ObservationError):
            client("mutation{deleteRepository(input:{}){clientMutationId}}")
        with patch.object(inventory.subprocess, "run") as run:
            run.return_value = inventory.subprocess.CompletedProcess([], 0, b'{"data":{}}')
            client("query{viewer{login}}")
            call = run.call_args
            self.assertIn("github.com", call.args[0])
            self.assertEqual(call.kwargs["stderr"], inventory.subprocess.DEVNULL)
            self.assertNotIn("login", json.dumps(client.responses))
            client('query{repository(owner:"szl-holdings",name:"mutation-tests"){name}}')


class CommitmentTests(unittest.TestCase):
    def test_source_changes_after_batch_recheck_cannot_pass_final_census(self):
        for changed in ("archive", "head"):
            with self.subTest(change=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for path in inventory.AUTHORITIES:
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps({"schema": "szl.archive-portfolio/v2", "repositories": []}))
                calls = 0
                def request(query, _variables=None):
                    nonlocal calls
                    if query == inventory.QUERY:
                        calls += 1
                        row = repository()
                        if calls == 2:
                            if changed == "archive":
                                row["isArchived"] = True
                            else:
                                row["defaultBranchRef"]["target"]["oid"] = "c" * 40
                        return page([row])
                    return {"data": {"r0": {"object": None, "defaultBranchRef": {"target": {"oid": HEAD}}}}}
                with patch.object(inventory.alignment, "build_receipt", return_value={"state": "ALIGNED"}), \
                     patch.object(inventory.alignment, "canonical_repositories", return_value=set()), \
                     patch.object(inventory.router, "validate", return_value={"status": "PASS"}):
                    result = inventory.collect(root, request)
                self.assertEqual(result["state"], "PARTIAL")
                self.assertEqual(result["repositories"][0]["head_state"], "STATE_CHANGED" if changed == "archive" else "MOVED")

    def test_inherited_validator_diagnostics_never_enter_saved_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in inventory.AUTHORITIES:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"schema": "szl.archive-portfolio/v2", "repositories": []}))
            sentinel = "hf_" + "synthetic" * 8
            with patch.object(inventory.alignment, "build_receipt", return_value={"state": "DIVERGENT", "failures": [sentinel]}), \
                 patch.object(inventory.alignment, "canonical_repositories", return_value=set()), \
                 patch.object(inventory.router, "validate", return_value={"status": "FAIL", "failures": [sentinel]}):
                result = inventory.collect(root, lambda *_: page([]))
            output = root / "evidence"
            inventory.save(result, output)
            self.assertEqual(result["state"], "PARTIAL")
            self.assertNotIn(sentinel, (output / "inventory.json").read_text())
            self.assertNotIn(sentinel, (output / "inventory.md").read_text())
            self.assertEqual(result["canonical_validation"]["alignment"]["failures"], ["ALIGNMENT_VALIDATION_FAILED"])

    def test_membership_change_and_invalid_csv_preserve_partial_source_rows(self):
        for moved in (False, True):
            with self.subTest(membership_moved=moved), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for path in inventory.AUTHORITIES:
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps({"schema": "szl.archive-portfolio/v2", "repositories": []}))
                calls = 0
                def request(query, _variables=None):
                    nonlocal calls
                    if query == inventory.QUERY:
                        calls += 1
                        return page([repository(id="changed" if moved and calls == 2 else "R_synthetic")])
                    return {"data": {"r0": {"object": None, "defaultBranchRef": {"target": {"oid": HEAD}}}}}
                with patch.object(inventory.alignment, "build_receipt", return_value={"state": "ALIGNED"}), \
                     patch.object(inventory.alignment, "canonical_repositories", return_value=set()), \
                     patch.object(inventory.router, "validate", return_value={"status": "PASS"}):
                    result = inventory.collect(root, request, root / "missing.csv", "2026-09-29T00:00:00Z")
                self.assertEqual(len(result["repositories"]), 1)
                self.assertEqual(result["state"], "PARTIAL")
                self.assertFalse(result["organization_complete"])
                self.assertIn("SNAPSHOT_UNAVAILABLE_OR_INVALID", result["failures"])
                if moved:
                    self.assertIn("VISIBLE_MEMBERSHIP_CHANGED_OR_UNAVAILABLE", result["failures"])

    def test_partial_census_cannot_claim_snapshot_repository_disappearance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.csv"
            path.write_text("repo,archived\nsynthetic,False\n", encoding="utf-8")
            result = inventory.snapshot_delta(path, "2026-09-29T00:00:00Z", [], False)
            self.assertEqual(result["not_observed"], "UNKNOWN_PARTIAL_CENSUS")
            self.assertEqual(result["trust"], "UNSIGNED_INPUT_CONTEXT")
            with self.assertRaises(inventory.ObservationError):
                inventory.snapshot_delta(path, None, [], True)

    def test_empty_or_duplicate_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.csv"
            for text in ("", "repo,archived\n", "repo,archived\nsynthetic,False\nsynthetic,True\n"):
                with self.subTest(source=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(inventory.ObservationError):
                        inventory.snapshot_delta(path, "2026-09-29T00:00:00Z", [], True)

    def test_report_and_receipt_commitments_reject_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-generation"
            value = {"state": "PARTIAL", "repositories": [], "scope": "AUTHENTICATED_VISIBLE_PUBLIC",
                     "claim_boundary": "Synthetic incomplete observation", "receipt_sha256": "previous-digest"}
            inventory.save(value, output)
            receipt = json.loads((output / "inventory.json").read_bytes())
            commitment = receipt.pop("receipt_sha256")
            self.assertEqual(inventory.digest(inventory.encoded(receipt)), commitment)
            self.assertEqual(inventory.digest((output / "inventory.md").read_bytes()), receipt["report_sha256"])
            receipt["state"] = "OBSERVED"
            self.assertNotEqual(inventory.digest(inventory.encoded(receipt)), commitment)

    def test_preexisting_generation_is_preserved_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "previous-generation"
            output.mkdir()
            path = output / "inventory.json"
            path.write_bytes(b"previous immutable evidence\n")
            value = {"state": "PARTIAL", "repositories": [], "scope": "AUTHENTICATED_VISIBLE_PUBLIC",
                     "claim_boundary": "Synthetic incomplete observation"}
            with self.assertRaises(FileExistsError):
                inventory.save(value, output)
            self.assertEqual(path.read_bytes(), b"previous immutable evidence\n")
            self.assertFalse((output / "inventory.md").exists())
            with self.assertRaises(FileExistsError):
                inventory.save(value, Path(temporary))


if __name__ == "__main__":
    unittest.main()
