#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("estate_alignment_contract.py")
SPEC = importlib.util.spec_from_file_location("estate_alignment_contract", MODULE_PATH)
assert SPEC and SPEC.loader
alignment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alignment)


class EstateAlignmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = alignment.load_json(
            ROOT / "docs" / "ESTATE_ALIGNMENT_CONTRACT_V1.json"
        )

    def test_current_contract_and_documents_are_aligned(self) -> None:
        self.assertEqual(alignment.validate_contract(self.contract), [])
        self.assertEqual(alignment.validate_documents(ROOT, self.contract), [])

    def test_exact_taxonomy_is_not_inferred_from_counts(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["taxonomy"]["commercial_flagships"][0]["slug"] = "immune"
        failures = alignment.validate_contract(candidate)
        self.assertTrue(any("commercial_flagships" in row for row in failures))
        self.assertTrue(any("folded capability" in row for row in failures))

    def test_space_inventory_rejects_missing_or_unclassified_surfaces(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["portfolio_spaces"].pop()
        failures = alignment.validate_contract(candidate)
        self.assertTrue(any("portfolio Space" in row for row in failures))

        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["portfolio_spaces"][0][
            "class"
        ] = "product_because_public"
        failures = alignment.validate_contract(candidate)
        self.assertIn("unknown portfolio Space class", failures)

    def test_hub_inventory_cannot_become_publication_policy(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["policy_authority"] = True
        failures = alignment.validate_contract(candidate)
        self.assertIn("Hub inventory must not be publication policy", failures)

        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["governed_keep_list"] = "self"
        failures = alignment.validate_contract(candidate)
        self.assertIn("governed keep-list authority mismatch", failures)

    def test_live_readback_qualifies_the_exact_pull_request_head(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "estate-one-fabric-alignment.yml"
        ).read_text(encoding="utf-8")
        live_job = workflow.split("  live-contract:\n", 1)[1]
        self.assertNotIn("github.event_name != 'pull_request'", live_job)
        exact_head = "${{ github.event.pull_request.head.sha || github.sha }}"
        self.assertGreaterEqual(live_job.count(exact_head), 2)
        self.assertIn("--live", live_job)

    def test_strict_loader_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        with self.assertRaisesRegex(alignment.AlignmentError, "duplicate JSON key"):
            alignment.load_json_bytes(b'{"a":1,"a":2}', label="duplicate")
        with self.assertRaisesRegex(alignment.AlignmentError, "non-finite"):
            alignment.load_json_bytes(b'{"a":NaN}', label="nonfinite")

    def test_product_contract_comparison_rejects_source_drift(self) -> None:
        product = {
            "estate": {
                "product_surface": "https://a-11-oy.com",
                "proof_surface": "https://a11oy.net",
                "artifact_organization": "SZLHOLDINGS",
            },
            "authorities": {
                "lean_kernel": {"locked_proven_ids": alignment.LOCKED_EIGHT}
            },
            "public_product_taxonomy": {
                "public_domain_bodies": alignment.EXPECTED_BODIES,
                "internal_engines": alignment.EXPECTED_ENGINES,
                "folded_into_killinchu": list(alignment.EXPECTED_FOLDS),
            },
            "verticals": [
                {
                    "slug": row["slug"],
                    "canonical_source": row["source"],
                }
                for row in self.contract["taxonomy"]["public_domain_bodies"]
            ],
        }
        self.assertEqual(
            alignment.validate_product_contract(product, self.contract), []
        )
        product["verticals"][-1]["canonical_source"] = "szl-holdings/lyte-lattice"
        failures = alignment.validate_product_contract(product, self.contract)
        self.assertTrue(any("canonical source drift for lyte" in row for row in failures))

    def test_receipt_contains_no_write_authority(self) -> None:
        receipt = alignment.build_receipt(ROOT, live=False)
        self.assertEqual(receipt["state"], "ALIGNED")
        self.assertFalse(receipt["authority"]["provider_writes"])
        self.assertFalse(receipt["authority"]["secret_values_recorded"])
        self.assertFalse(receipt["authority"]["public_effectors_enabled"])
        self.assertEqual(len(receipt["receipt_sha256"]), 64)

    def test_runtime_binding_requires_exact_canonical_revision(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/terra",
            "canonical_source": "szl-holdings/a11oy:verticals/terra",
            "deployment_source": "szl-holdings/a11oy",
        }
        expected = "a" * 40
        requested: list[str] = []

        def fetch(url: str, **_kwargs) -> bytes:
            requested.append(url)
            self.assertEqual(
                alignment.urllib.parse.urlsplit(url).path,
                "/api/build-info",
            )
            return json.dumps(
                {
                    "source_repository": "szl-holdings/a11oy",
                    "build": {"revision": expected},
                }
            ).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)
        self.assertTrue(observation["matched"])
        self.assertEqual(observation["canonical_source"], "szl-holdings/a11oy")
        self.assertEqual(observation["observed_revision"], expected)
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)
        self.assertEqual(len(set(requested)), alignment.RUNTIME_OBSERVATIONS)
        self.assertTrue(all("cache_bust=" in url for url in requested))

        stale = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source_repository": "szl-holdings/szl-real-estate",
                    "source_revision": "b" * 40,
                }
            ).encode(),
        )
        self.assertFalse(stale["matched"])
        self.assertEqual(stale["observed_revision"], "b" * 40)
        self.assertEqual(stale["observed_source"], "szl-holdings/szl-real-estate")

    def test_runtime_binding_falls_back_to_static_deployment_receipt(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/szl-command-lab",
            "canonical_source": "szl-holdings/szl-command-lab",
            "deployment_source": "szl-holdings/szl-command-lab",
        }
        expected = "c" * 40
        requested: list[str] = []

        def fetch(url: str, **_kwargs) -> bytes:
            requested.append(url)
            if alignment.urllib.parse.urlsplit(url).path == "/api/build-info":
                raise OSError("not implemented")
            return json.dumps(
                {
                    "source": {
                        "repository": "szl-holdings/szl-command-lab",
                        "revision": expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)
        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(requested), 2 * alignment.RUNTIME_OBSERVATIONS)

    def test_incomplete_build_info_falls_back_to_complete_deployment(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/terra",
            "canonical_source": "szl-holdings/a11oy:verticals/terra",
            "deployment_source": "szl-holdings/a11oy",
        }
        expected = "c" * 40
        requested: list[str] = []

        def fetch(url: str, **_kwargs) -> bytes:
            requested.append(url)
            path = alignment.urllib.parse.urlsplit(url).path
            if path == "/api/build-info":
                return json.dumps({"build": {"revision": expected}}).encode()
            return json.dumps(
                {
                    "source": {
                        "repository": "szl-holdings/a11oy",
                        "revision": expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)

        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(observation["attempts"]), 2)
        self.assertFalse(observation["attempts"][0]["complete"])
        self.assertTrue(observation["attempts"][0]["stable"])
        self.assertEqual(len(requested), 2 * alignment.RUNTIME_OBSERVATIONS)

    def test_inconsistent_runtime_observations_fail_closed(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/terra",
            "canonical_source": "szl-holdings/a11oy:verticals/terra",
            "deployment_source": "szl-holdings/a11oy",
        }
        expected = "d" * 40
        revisions = iter((expected, "e" * 40))

        def fetch(url: str, **_kwargs) -> bytes:
            self.assertEqual(
                alignment.urllib.parse.urlsplit(url).path,
                "/api/build-info",
            )
            return json.dumps(
                {
                    "source_repository": "szl-holdings/a11oy",
                    "source_revision": next(revisions),
                }
            ).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)

        self.assertFalse(observation["matched"])
        self.assertEqual(observation["binding_path"], "/api/build-info")
        self.assertFalse(observation["attempts"][0]["stable"])
        self.assertEqual(len(observation["attempts"][0]["observations"]), 2)

    def test_fetch_rejects_cross_origin_redirect_destination(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self) -> str:
                return "https://attacker.invalid/deployment.json"

            def read(self, _limit: int) -> bytes:
                return b"{}"

        with (
            patch.object(alignment.urllib.request, "urlopen", return_value=Response()),
            self.assertRaisesRegex(alignment.AlignmentError, "cross-origin redirect"),
        ):
            alignment.fetch_bytes(
                "https://szlholdings-terra.hf.space/deployment.json",
                attempts=1,
                required_origin="https://szlholdings-terra.hf.space",
            )

        redirected_error = alignment.urllib.error.HTTPError(
            "https://attacker.invalid/deployment.json",
            404,
            "not found",
            {},
            None,
        )
        with (
            patch.object(
                alignment.urllib.request,
                "urlopen",
                side_effect=redirected_error,
            ),
            self.assertRaisesRegex(alignment.AlignmentError, "cross-origin redirect"),
        ):
            alignment.fetch_bytes(
                "https://szlholdings-terra.hf.space/deployment.json",
                attempts=1,
                required_origin="https://szlholdings-terra.hf.space",
            )

    def test_conflicting_runtime_revision_fields_fail_closed(self) -> None:
        with self.assertRaisesRegex(alignment.AlignmentError, "conflicting"):
            alignment.source_revision(
                {
                    "source_revision": "d" * 40,
                    "build": {"revision": "e" * 40},
                }
            )

        row = {
            "repo_id": "SZLHOLDINGS/a11oy",
            "canonical_source": "szl-holdings/a11oy",
            "deployment_source": "szl-holdings/a11oy",
        }
        observation = alignment.runtime_source_binding(
            row,
            "d" * 40,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source_revision": "d" * 40,
                    "build": {"revision": "e" * 40},
                }
            ).encode(),
        )
        self.assertFalse(observation["matched"])
        self.assertEqual(len(observation["attempts"]), 1)

    def test_live_alignment_checks_every_portfolio_runtime(self) -> None:
        product = {
            "estate": {
                "product_surface": "https://a-11-oy.com",
                "proof_surface": "https://a11oy.net",
                "artifact_organization": "SZLHOLDINGS",
            },
            "authorities": {
                "lean_kernel": {"locked_proven_ids": alignment.LOCKED_EIGHT}
            },
            "public_product_taxonomy": {
                "public_domain_bodies": alignment.EXPECTED_BODIES,
                "internal_engines": alignment.EXPECTED_ENGINES,
                "folded_into_killinchu": list(alignment.EXPECTED_FOLDS),
            },
            "verticals": [
                {"slug": row["slug"], "canonical_source": row["source"]}
                for row in self.contract["taxonomy"]["public_domain_bodies"]
            ],
        }
        revision = "f" * 40
        space_ids = sorted(alignment.EXPECTED_PORTFOLIO_SPACES | {"SZLHOLDINGS/README"})

        def fetch(url: str, **_kwargs) -> bytes:
            if "/repos/" in url:
                return b'{"archived":false,"visibility":"public","default_branch":"main"}'
            return json.dumps(product).encode()

        def list_hf(kind: str):
            if kind == "models":
                return [{}] * 44
            if kind == "datasets":
                return [{}] * 33
            return [{"id": repo_id} for repo_id in space_ids]

        seen: list[str] = []

        def binding(row, expected_revision):
            seen.append(row["repo_id"])
            matched = row["repo_id"] != "SZLHOLDINGS/ayllu"
            return {
                "repo_id": row["repo_id"],
                "expected_revision": expected_revision,
                "observed_revision": expected_revision if matched else "0" * 40,
                "matched": matched,
            }

        with (
            patch.object(alignment, "fetch_bytes", side_effect=fetch),
            patch.object(alignment, "github_main_sha", return_value=revision),
            patch.object(alignment, "list_hf", side_effect=list_hf),
            patch.object(alignment, "runtime_source_binding", side_effect=binding),
        ):
            failures, observation = alignment.validate_live(self.contract)

        self.assertEqual(
            set(seen),
            alignment.EXPECTED_PORTFOLIO_SPACES | {alignment.ORG_CARD_SPACE_ID},
        )
        self.assertEqual(len(observation["runtime_source_bindings"]), 16)
        self.assertEqual(
            observation["organization_card_source_binding"]["repo_id"],
            alignment.ORG_CARD_SPACE_ID,
        )
        self.assertEqual(
            [row["repo_id"] for row in observation["runtime_source_bindings"]],
            [
                row["repo_id"]
                for row in self.contract["huggingface_inventory_snapshot"][
                    "portfolio_spaces"
                ]
            ],
        )
        self.assertTrue(
            any("runtime source revision drift for SZLHOLDINGS/ayllu" in row for row in failures)
        )


    def test_org_card_contract_is_exact_and_outside_portfolio_count(self) -> None:
        org_card = self.contract["organization_card_control_surface"]
        self.assertEqual(org_card["repo_id"], alignment.ORG_CARD_SPACE_ID)
        self.assertEqual(
            org_card["deployment_source"], alignment.ORG_CARD_DEPLOYMENT_SOURCE
        )
        self.assertEqual(org_card["runtime_origin"], alignment.ORG_CARD_RUNTIME_ORIGIN)
        self.assertEqual(org_card["binding_paths"], list(alignment.ORG_CARD_BINDING_PATHS))
        self.assertIs(org_card["portfolio_member"], False)
        portfolio_ids = {
            row["repo_id"]
            for row in self.contract["huggingface_inventory_snapshot"]["portfolio_spaces"]
        }
        self.assertEqual(len(portfolio_ids), 16)
        self.assertNotIn(alignment.ORG_CARD_SPACE_ID, portfolio_ids)

    def test_org_card_runtime_binding_uses_static_deployment_receipt_only(self) -> None:
        expected = "a" * 40
        requested: list[tuple[str, str | None]] = []

        def fetch(url: str, **kwargs) -> bytes:
            requested.append((url, kwargs.get("required_origin")))
            return json.dumps(
                {
                    "source": {
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(
            self.contract["organization_card_control_surface"],
            expected,
            fetch=fetch,
        )

        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)
        for url, required_origin in requested:
            parsed = alignment.urllib.parse.urlsplit(url)
            self.assertEqual(parsed.netloc, "szlholdings-readme.static.hf.space")
            self.assertEqual(parsed.path, "/deployment.json")
            self.assertEqual(required_origin, alignment.ORG_CARD_RUNTIME_ORIGIN)

    def test_org_card_binding_fails_closed_on_stale_conflicting_or_redirected_evidence(self) -> None:
        expected = "b" * 40
        row = self.contract["organization_card_control_surface"]

        stale = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source": {
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": "c" * 40,
                    }
                }
            ).encode(),
        )
        self.assertFalse(stale["matched"])

        conflicting = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source_repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                    "source_revision": expected,
                    "build": {"revision": "d" * 40},
                }
            ).encode(),
        )
        self.assertFalse(conflicting["matched"])

        redirected = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: (_ for _ in ()).throw(
                alignment.AlignmentError("cross-origin redirect rejected")
            ),
        )
        self.assertFalse(redirected["matched"])

    def test_org_card_contract_rejects_wrong_origin_and_membership(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["organization_card_control_surface"]["runtime_origin"] = (
            "https://szlholdings-readme.hf.space"
        )
        candidate["organization_card_control_surface"]["portfolio_member"] = True
        failures = alignment.validate_contract(candidate)
        self.assertIn("organization-card runtime origin mismatch", failures)
        self.assertIn(
            "organization-card must remain outside the portfolio count", failures
        )


if __name__ == "__main__":
    unittest.main()
