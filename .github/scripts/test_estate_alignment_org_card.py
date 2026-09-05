#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("estate_alignment_contract.py")
SPEC = importlib.util.spec_from_file_location("estate_alignment_contract_org_card", MODULE_PATH)
assert SPEC and SPEC.loader
alignment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alignment)


class FakeResponse:
    def __init__(self, final_url: str, payload: bytes = b"{}") -> None:
        self.final_url = final_url
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self.final_url

    def read(self, _limit: int) -> bytes:
        return self.payload


class OrganizationCardSourceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = alignment.org_card_runtime_row()
        self.expected = "a" * 40

    def test_control_surface_is_not_a_seventeenth_portfolio_member(self) -> None:
        self.assertEqual(self.row["repo_id"], "SZLHOLDINGS/README")
        self.assertFalse(self.row["portfolio_member"])
        self.assertNotIn(self.row["repo_id"], alignment.EXPECTED_PORTFOLIO_SPACES)
        self.assertEqual(self.row["deployment_source"], "szl-holdings/.github")

    def test_exact_static_deployment_receipt_is_required(self) -> None:
        requested: list[tuple[str, str | None]] = []

        def fetch(url: str, **kwargs) -> bytes:
            requested.append((url, kwargs.get("required_origin")))
            parsed = alignment.urllib.parse.urlsplit(url)
            self.assertEqual(parsed.netloc, "szlholdings-readme.static.hf.space")
            self.assertEqual(parsed.path, "/deployment.json")
            return json.dumps(
                {
                    "source": {
                        "repository": "szl-holdings/.github",
                        "revision": self.expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(self.row, self.expected, fetch=fetch)
        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)
        self.assertTrue(
            all(origin == alignment.ORG_CARD_ORIGIN for _, origin in requested)
        )

    def test_missing_stale_and_unstable_receipts_fail_closed(self) -> None:
        missing = alignment.runtime_source_binding(
            self.row,
            self.expected,
            fetch=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
        )
        self.assertFalse(missing["matched"])

        stale = alignment.runtime_source_binding(
            self.row,
            self.expected,
            fetch=lambda *_args, **_kwargs: json.dumps(
                {
                    "source": {
                        "repository": "szl-holdings/.github",
                        "revision": "b" * 40,
                    }
                }
            ).encode(),
        )
        self.assertFalse(stale["matched"])
        self.assertEqual(stale["observed_revision"], "b" * 40)

        revisions = iter((self.expected, "c" * 40))
        unstable = alignment.runtime_source_binding(
            self.row,
            self.expected,
            fetch=lambda *_args, **_kwargs: json.dumps(
                {
                    "source": {
                        "repository": "szl-holdings/.github",
                        "revision": next(revisions),
                    }
                }
            ).encode(),
        )
        self.assertFalse(unstable["matched"])
        self.assertFalse(unstable["attempts"][0]["stable"])

    def test_wrong_origin_and_binding_path_are_rejected(self) -> None:
        wrong_origin = dict(self.row)
        wrong_origin["runtime_origin"] = "https://szlholdings-readme.hf.space"
        with self.assertRaisesRegex(alignment.AlignmentError, "exact static origin"):
            alignment.runtime_source_binding(wrong_origin, self.expected)

        wrong_path = dict(self.row)
        wrong_path["binding_paths"] = ["/api/build-info"]
        with self.assertRaisesRegex(alignment.AlignmentError, "deployment.json only"):
            alignment.runtime_source_binding(wrong_path, self.expected)

    def test_cross_origin_redirect_is_rejected(self) -> None:
        with patch.object(
            alignment.urllib.request,
            "urlopen",
            return_value=FakeResponse(
                "https://shared-receipts.invalid/deployment.json",
                b'{"source":{"repository":"szl-holdings/.github","revision":"'
                + self.expected.encode()
                + b'"}}',
            ),
        ):
            with self.assertRaisesRegex(alignment.AlignmentError, "cross-origin redirect"):
                alignment.fetch_bytes(
                    alignment.ORG_CARD_ORIGIN + "/deployment.json",
                    attempts=1,
                    required_origin=alignment.ORG_CARD_ORIGIN,
                    sleep=lambda _seconds: None,
                )


if __name__ == "__main__":
    unittest.main()
