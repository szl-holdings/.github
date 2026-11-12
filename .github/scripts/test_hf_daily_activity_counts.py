#!/usr/bin/env python3
"""Network-free tests for the daily activity Hub inventory pager."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("hf_daily_activity_counts.py")
SPEC = importlib.util.spec_from_file_location("hf_daily_activity_counts", MODULE_PATH)
assert SPEC and SPEC.loader
counts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = counts
SPEC.loader.exec_module(counts)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-daily-activity.yml"
ORG = counts.ORG


def _repo(kind: str, name: str) -> dict:
    return {"id": f"{ORG}/{name}", "kind": kind}


def _page(items: list[dict], link: str = "") -> tuple[int, bytes, str]:
    return 200, json.dumps(items).encode(), link


class FakeGet:
    def __init__(self, pages: dict[str, tuple[int, bytes, str]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, url: str, token: str | None):
        self.calls.append((url, token))
        if url not in self.pages:
            raise AssertionError(f"unexpected URL {url}")
        return self.pages[url]


class DailyActivityCountTests(unittest.TestCase):
    def test_dataset_pages_are_followed_until_the_link_ends(self) -> None:
        first = f"https://huggingface.co/api/datasets?author={ORG}&limit=50"
        second = f"https://huggingface.co/api/datasets?author={ORG}&limit=50&cursor=page-2"
        transport = FakeGet(
            {
                first: _page(
                    [_repo("dataset", "one"), _repo("dataset", "two")],
                    f'<{second}>; rel="next"',
                ),
                second: _page([_repo("dataset", "three")]),
            }
        )
        found = counts.list_author_repos("datasets", transport, "hf-token", page_limit=50)
        self.assertEqual(
            [item["id"] for item in found],
            [f"{ORG}/one", f"{ORG}/two", f"{ORG}/three"],
        )
        self.assertEqual([call[1] for call in transport.calls], ["hf-token", "hf-token"])

    def test_off_host_next_link_is_not_requested(self) -> None:
        first = f"https://huggingface.co/api/datasets?author={ORG}&limit=100"
        transport = FakeGet(
            {
                first: _page(
                    [_repo("dataset", "one")],
                    '<https://evil.example/api/datasets?author=SZLHOLDINGS>; rel="next"',
                )
            }
        )
        with self.assertRaises(RuntimeError):
            counts.list_author_repos("datasets", transport, "hf-token")
        self.assertEqual([call[0] for call in transport.calls], [first])

    def test_next_link_that_drops_the_author_filter_is_not_requested(self) -> None:
        first = f"https://huggingface.co/api/models?author={ORG}&limit=100"
        transport = FakeGet(
            {
                first: _page(
                    [_repo("model", "one")],
                    '<https://huggingface.co/api/models?limit=100&cursor=x>; rel="next"',
                )
            }
        )
        with self.assertRaisesRegex(RuntimeError, "author filter"):
            counts.list_author_repos("models", transport, "hf-token")
        self.assertEqual(len(transport.calls), 1)

    def test_duplicate_or_foreign_record_fails_closed(self) -> None:
        first = f"https://huggingface.co/api/spaces?author={ORG}&limit=100"
        duplicate = FakeGet({first: _page([_repo("space", "one"), _repo("space", "one")])})
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            counts.list_author_repos("spaces", duplicate, None)
        foreign = FakeGet({first: _page([{"id": "other/not-ours"}])})
        with self.assertRaisesRegex(RuntimeError, "record id"):
            counts.list_author_repos("spaces", foreign, None)

    def test_non_list_page_and_http_error_fail_closed(self) -> None:
        first = f"https://huggingface.co/api/datasets?author={ORG}&limit=100"
        wrapped = FakeGet({first: (200, b'{"items": []}', "")})
        with self.assertRaisesRegex(RuntimeError, "not a list"):
            counts.list_author_repos("datasets", wrapped, None)
        failed = FakeGet({first: (500, b"[]", "")})
        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            counts.list_author_repos("datasets", failed, None)

    def test_cycle_and_page_bound_fail_closed(self) -> None:
        first = f"https://huggingface.co/api/datasets?author={ORG}&limit=100"
        looping = FakeGet({first: _page([_repo("dataset", "one")], f'<{first}>; rel="next"')})
        with self.assertRaisesRegex(RuntimeError, "cycle"):
            counts.list_author_repos("datasets", looping, None, max_pages=3)
        second = f"https://huggingface.co/api/datasets?author={ORG}&limit=1&cursor=more"
        bounded = FakeGet(
            {
                f"https://huggingface.co/api/datasets?author={ORG}&limit=1": _page(
                    [_repo("dataset", "one")],
                    f'<{second}>; rel="next"',
                ),
                second: _page(
                    [_repo("dataset", "two")],
                    f'<{second}&again=1>; rel="next"',
                ),
            }
        )
        with self.assertRaisesRegex(RuntimeError, "page bound"):
            counts.list_author_repos("datasets", bounded, None, page_limit=1, max_pages=2)

    def test_link_parser_accepts_one_next_and_rejects_malformed_headers(self) -> None:
        self.assertIsNone(counts.parse_next_link(""))
        self.assertIsNone(counts.parse_next_link('<https://huggingface.co/api/datasets?author=SZLHOLDINGS>; rel="prev"'))
        self.assertEqual(
            counts.parse_next_link('<https://huggingface.co/api/datasets?author=SZLHOLDINGS&cursor=1>; rel="next"'),
            "https://huggingface.co/api/datasets?author=SZLHOLDINGS&cursor=1",
        )
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            counts.parse_next_link("not a link")
        with self.assertRaisesRegex(RuntimeError, "multiple"):
            counts.parse_next_link(
                '<https://huggingface.co/a>; rel="next", <https://huggingface.co/b>; rel="next"'
            )

    def test_collections_stay_on_one_request_even_when_a_next_link_is_present(self) -> None:
        url = f"https://huggingface.co/api/collections?namespace={ORG}&limit=20"
        transport = FakeGet(
            {
                url: (
                    200,
                    json.dumps([{"slug": "other/collection"}] * 20).encode(),
                    '<https://huggingface.co/api/collections?sort=trending&cursor=next>; rel="next"',
                )
            }
        )
        self.assertEqual(counts.count_collections(transport, "hf-token"), 20)
        self.assertEqual(transport.calls, [(url, "hf-token")])

    def test_http_client_refuses_redirects(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/steal")
                self.end_headers()

            def log_message(self, fmt, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/datasets"
            with self.assertRaises(RuntimeError):
                counts.http_get(url, "hf-token")
        finally:
            server.shutdown()
            server.server_close()

    def test_workflow_calls_the_pager_and_does_not_publish_on_pull_request(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 .github/scripts/hf_daily_activity_counts.py", text)
        self.assertIn("python3 .github/scripts/test_hf_daily_activity_counts.py", text)
        self.assertNotIn("limit=50", text)
        self.assertNotIn("/api/datasets?", text)
        self.assertIn("if: github.event_name != 'pull_request'", text)
        self.assertIn("if: github.event_name == 'pull_request'", text)


if __name__ == "__main__":
    unittest.main()
