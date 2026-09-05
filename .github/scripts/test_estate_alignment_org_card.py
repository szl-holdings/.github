#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent regressions for README as a source-bound control surface."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("estate_alignment_contract.py")
CONTRACT_PATH = MODULE_PATH.parents[2] / "docs" / "ESTATE_ALIGNMENT_CONTRACT_V1.json"
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
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.row = self.contract["organization_card_control_surface"]
        self.expected = "a" * 40

    def test_control_surface_is_not_a_seventeenth_portfolio_member(self) -> None:
        self.assertEqual(self.row["repo_id"], alignment.ORG_CARD_SPACE_ID)
        self.assertFalse(self.row["portfolio_member"])
        self.assertEqual(
            self.row["deployment_source"], alignment.ORG_CARD_DEPLOYMENT_SOURCE
        )
        self.assertEqual(
            self.row["runtime_origin"], alignment.ORG_CARD_RUNTIME_ORIGIN
        )
        portfolio = self.contract["huggingface_inventory_snapshot"]["portfolio_spaces"]
        portfolio_ids = {row["repo_id"] for row in portfolio}
        self.assertEqual(len(portfolio_ids), 17)
        self.assertNotIn(alignment.ORG_CARD_SPACE_ID, portfolio_ids)

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
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": self.expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(
            self.row, self.expected, fetch=fetch
        )
        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)
        self.assertTrue(
            all(
                origin == alignment.ORG_CARD_RUNTIME_ORIGIN
                for _, origin in requested
            )
        )

    def test_missing_stale_conflicting_and_unstable_receipts_fail_closed(self) -> None:
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
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": "b" * 40,
                    }
                }
            ).encode(),
        )
        self.assertFalse(stale["matched"])
        self.assertEqual(stale["observed_revision"], "b" * 40)

        conflicting = alignment.runtime_source_binding(
            self.row,
            self.expected,
            fetch=lambda *_args, **_kwargs: json.dumps(
                {
                    "source_repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                    "source_revision": self.expected,
                    "build": {"revision": "c" * 40},
                }
            ).encode(),
        )
        self.assertFalse(conflicting["matched"])

        revisions = iter((self.expected, "d" * 40))
        unstable = alignment.runtime_source_binding(
            self.row,
            self.expected,
            fetch=lambda *_args, **_kwargs: json.dumps(
                {
                    "source": {
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": next(revisions),
                    }
                }
            ).encode(),
        )
        self.assertFalse(unstable["matched"])
        self.assertFalse(unstable["attempts"][0]["stable"])

    def test_wrong_origin_binding_path_and_membership_are_rejected(self) -> None:
        wrong_origin = copy.deepcopy(self.contract)
        wrong_origin["organization_card_control_surface"]["runtime_origin"] = (
            "https://szlholdings-readme.hf.space"
        )
        self.assertIn(
            "organization-card runtime origin mismatch",
            alignment.validate_contract(wrong_origin),
        )

        wrong_path = copy.deepcopy(self.contract)
        wrong_path["organization_card_control_surface"]["binding_paths"] = [
            "/api/build-info"
        ]
        self.assertIn(
            "organization-card binding path mismatch",
            alignment.validate_contract(wrong_path),
        )

        counted = copy.deepcopy(self.contract)
        counted["organization_card_control_surface"]["portfolio_member"] = True
        self.assertIn(
            "organization-card must remain outside the portfolio count",
            alignment.validate_contract(counted),
        )

    def test_custom_runtime_binding_is_reserved_for_the_org_card(self) -> None:
        portfolio_row = dict(
            self.contract["huggingface_inventory_snapshot"]["portfolio_spaces"][0]
        )
        portfolio_row["runtime_origin"] = alignment.ORG_CARD_RUNTIME_ORIGIN
        portfolio_row["binding_paths"] = ["/deployment.json"]
        with self.assertRaisesRegex(
            alignment.AlignmentError,
            "custom runtime binding is reserved",
        ):
            alignment.runtime_source_binding(portfolio_row, self.expected)

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
            with self.assertRaisesRegex(
                alignment.AlignmentError, "cross-origin redirect"
            ):
                alignment.fetch_bytes(
                    alignment.ORG_CARD_RUNTIME_ORIGIN + "/deployment.json",
                    attempts=1,
                    required_origin=alignment.ORG_CARD_RUNTIME_ORIGIN,
                    sleep=lambda _seconds: None,
                )


if __name__ == "__main__":
    unittest.main()
