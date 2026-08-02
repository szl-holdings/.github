#!/usr/bin/env python3
"""Network-free regressions for personal GitHub notification inbox clearance."""
from __future__ import annotations

import importlib.util
import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("clear_personal_notifications.py")
SPEC = importlib.util.spec_from_file_location("clear_personal_notifications", MODULE_PATH)
assert SPEC and SPEC.loader
clearer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clearer
SPEC.loader.exec_module(clearer)


class FakeGitHub:
    def __init__(self, count: int, *, inject_concurrent: bool = False) -> None:
        self.threads = {
            str(index): {"unread": index % 2 == 0, "done": False}
            for index in range(1, count + 1)
        }
        self.inject_concurrent = inject_concurrent
        self.injected = False
        self.deleted: list[str] = []

    def request(self, token, method, path, payload=None):
        self.assert_token(token)
        if method == "GET" and path == "/user":
            return 200, {"login": "stephenlutar2-hash"}

        if method == "GET" and path.startswith("/notifications?"):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            include_read = query["all"][0] == "true"
            page = int(query["page"][0])
            per_page = int(query["per_page"][0])
            active = [
                thread_id
                for thread_id, state in sorted(
                    self.threads.items(), key=lambda pair: int(pair[0])
                )
                if not state["done"] and (include_read or state["unread"])
            ]
            start = (page - 1) * per_page
            payload_out = [{"id": item} for item in active[start : start + per_page]]
            return 200, payload_out

        if method == "DELETE" and path.startswith("/notifications/threads/"):
            thread_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            if thread_id not in self.threads:
                raise AssertionError(f"unknown thread: {thread_id}")
            self.threads[thread_id]["done"] = True
            self.deleted.append(thread_id)
            if self.inject_concurrent and not self.injected:
                self.injected = True
                self.threads["999"] = {"unread": True, "done": False}
            return 204, None

        raise AssertionError(f"unexpected request: {method} {path} {payload}")

    @staticmethod
    def assert_token(token):
        if token != "classic-token":
            raise AssertionError("wrong token")


class NotificationClearanceTests(unittest.TestCase):
    def test_inventory_includes_read_threads_and_paginates_at_api_maximum(self):
        api = FakeGitHub(53)
        with patch.object(clearer, "request", api.request):
            ids = clearer.notification_thread_ids(
                "classic-token", include_read=True
            )
            unread = clearer.notification_thread_ids(
                "classic-token", include_read=False
            )
        self.assertEqual(len(ids), 53)
        self.assertEqual(len(unread), 26)
        self.assertEqual(clearer.PER_PAGE, 50)

    def test_mark_thread_done_uses_documented_delete_endpoint(self):
        api = FakeGitHub(1)
        with patch.object(clearer, "request", api.request):
            clearer.mark_thread_done("classic-token", "1")
        self.assertEqual(api.deleted, ["1"])
        self.assertTrue(api.threads["1"]["done"])

    def test_clear_inbox_moves_read_and_unread_threads_to_done(self):
        api = FakeGitHub(4)
        with (
            patch.object(clearer, "request", api.request),
            patch.object(clearer.time, "sleep", return_value=None),
        ):
            report = clearer.clear_inbox("classic-token")
        self.assertEqual(report["before_inbox_count"], 4)
        self.assertEqual(report["before_unread_count"], 2)
        self.assertEqual(report["after_inbox_count"], 0)
        self.assertEqual(report["after_unread_count"], 0)
        self.assertEqual(report["cleared_count"], 4)
        self.assertEqual(report["status"], "CLEARED")
        self.assertFalse(report["notification_content_recorded"])
        self.assertFalse(report["thread_ids_recorded"])
        self.assertTrue(all(state["done"] for state in api.threads.values()))

    def test_clear_inbox_catches_notification_arriving_during_clearance(self):
        api = FakeGitHub(2, inject_concurrent=True)
        with (
            patch.object(clearer, "request", api.request),
            patch.object(clearer.time, "sleep", return_value=None),
        ):
            report = clearer.clear_inbox("classic-token")
        self.assertEqual(report["before_inbox_count"], 2)
        self.assertEqual(report["cleared_count"], 3)
        self.assertGreaterEqual(report["clearance_rounds"], 2)
        self.assertTrue(api.threads["999"]["done"])


if __name__ == "__main__":
    unittest.main()
