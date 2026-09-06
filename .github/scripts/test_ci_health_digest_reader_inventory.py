#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_health_digest_http as http


def repositories(count: int, private: int = 3):
    return tuple(
        {
            "name": f"repo-{index:03d}",
            "full_name": f"szl-holdings/repo-{index:03d}",
            "default_branch": "main",
            "archived": False,
            "private": index >= count - private,
            "visibility": "private" if index >= count - private else "public",
        }
        for index in range(count)
    )


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.empty = {env: "" for _, _, env in http.CANDIDATE_ENVIRONMENT}

    def test_exact_authoritative_total(self):
        estate = repositories(123)
        with patch.dict(os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False), patch.object(
            http, "request_json", return_value=(200, {"public_repos": 120, "total_private_repos": 3})
        ):
            result = http.validate_authoritative_inventory("token", estate)
        self.assertEqual(result["repository_count"], 123)
        self.assertTrue(result["inventory_match"])

    def test_partial_inventory_is_rejected(self):
        estate = repositories(122, private=2)
        with patch.dict(os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False), patch.object(
            http, "request_json", return_value=(200, {"public_repos": 120, "total_private_repos": 3})
        ):
            with self.assertRaisesRegex(http.DigestError, "listed=122 authoritative=123"):
                http.validate_authoritative_inventory("token", estate)

    def test_stale_first_alias_cannot_mask_valid_second(self):
        estate = repositories(123)
        state = dict(self.empty)
        state.update({"DIGEST_APP_TOKEN": "stale", "ORG_REPO_WORKFLOW_TOKEN": "valid"})

        def inventory(token):
            if token == "stale":
                raise http.ApiError(operation="inventory", status=401, detail_class="unauthenticated")
            return estate

        with patch.dict(os.environ, state, clear=False), patch.object(
            http, "list_repositories", side_effect=inventory
        ), patch.object(http, "request_json", return_value=(200, {"workflows": []})):
            selected = http.select_reader()
        self.assertEqual(selected.credential_name, "ORG_REPO_WORKFLOW_TOKEN")
        self.assertEqual(selected.attempts[0]["failure_class"], "unauthenticated")
        self.assertNotIn("stale", repr(selected))
        self.assertNotIn("valid", repr(selected))

    def test_duplicate_secret_values_are_probed_once(self):
        state = dict(self.empty)
        state.update({"ORG_REPO_WORKFLOW_TOKEN": "same", "SZL_GITHUB_TOKEN": "same"})
        calls = []
        def inventory(token):
            calls.append(token)
            raise http.DigestError("rejected")
        with patch.dict(os.environ, state, clear=False), patch.object(http, "list_repositories", side_effect=inventory):
            with self.assertRaises(http.ReaderSelectionError):
                http.select_reader()
        self.assertEqual(calls, ["same"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
