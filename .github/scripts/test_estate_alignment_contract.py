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

    def test_inventory_only_space_cannot_be_promoted_or_hidden(self) -> None:
        snapshot = self.contract["huggingface_inventory_snapshot"]
        self.assertEqual(
            {row["repo_id"] for row in snapshot["inventory_only_spaces"]},
            alignment.EXPECTED_INVENTORY_ONLY_SPACES,
        )
        self.assertEqual(snapshot["public_space_count"], 15)
        self.assertEqual(snapshot["portfolio_space_count"], 14)

        promoted = copy.deepcopy(self.contract)
        promoted["huggingface_inventory_snapshot"]["inventory_only_spaces"][0][
            "governed_keep"
        ] = True
        self.assertIn(
            "inventory-only Space cannot be a keeper",
            alignment.validate_contract(promoted),
        )

        hidden = copy.deepcopy(self.contract)
        row = hidden["huggingface_inventory_snapshot"]["inventory_only_spaces"].pop()
        hidden["huggingface_inventory_snapshot"]["portfolio_spaces"].append(row)
        failures = alignment.validate_contract(hidden)
        self.assertTrue(any("portfolio Space set mismatch" in item for item in failures))
        self.assertTrue(any("inventory-only Space set mismatch" in item for item in failures))

    def test_hub_inventory_cannot_become_publication_policy(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["policy_authority"] = True
        failures = alignment.validate_contract(candidate)
        self.assertIn("Hub inventory must not be publication policy", failures)

        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["governed_keep_list"] = "self"
        failures = alignment.validate_contract(candidate)
        self.assertIn("governed keep-list authority mismatch", failures)

    def test_public_membership_observation_does_not_reclassify_fleet(self) -> None:
        observation = self.contract["public_space_membership_observation"]
        self.assertEqual(alignment.validate_public_space_observation(observation), [])
        self.assertEqual(observation["public_space_count"], 75)
        self.assertFalse(observation["policy_authority"])
        self.assertEqual(observation["policy_alignment"], "UNKNOWN")
        self.assertEqual(
            {row["repo_id"] for row in observation["policy_conflicts"]},
            {"SZLHOLDINGS/llm-router-live", "SZLHOLDINGS/szl-atelier"},
        )
        historical = self.contract["huggingface_inventory_snapshot"]
        self.assertEqual(historical["public_space_count"], 15)
        self.assertEqual(historical["portfolio_space_count"], 14)
        self.assertEqual(
            {row["repo_id"] for row in historical["inventory_only_spaces"]},
            {"SZLHOLDINGS/yarqa"},
        )
        self.assertNotIn(alignment.ORG_CARD_SPACE_ID, alignment.EXPECTED_PUBLIC_SPACE_IDS)

    def test_public_membership_observation_rejects_malformed_or_promoted_evidence(self) -> None:
        original = self.contract["public_space_membership_observation"]
        candidates = []
        for label, key, value in (
            ("policy authority", "policy_authority", True),
            ("wrong author", "author", "another-owner"),
            ("wrong scope", "scope", "authenticated-private-list"),
            ("false policy convergence", "policy_alignment", "ALIGNED"),
            ("hidden conflict", "policy_conflicts", []),
            ("count", "public_space_count", 36),
            ("boolean count", "public_space_count", True),
            ("missing rows", "spaces", None),
        ):
            candidate = copy.deepcopy(original)
            candidate[key] = value
            candidates.append((label, candidate))
        for label, mutate in (
            ("missing ID", lambda rows: rows.pop()),
            ("unexpected ID", lambda rows: rows.append({"repo_id": "SZLHOLDINGS/unreviewed", "revision": "a" * 40})),
            ("duplicate ID", lambda rows: rows.append(copy.deepcopy(rows[0]))),
            ("wrong namespace", lambda rows: rows[0].update(repo_id="another-owner/a11oy")),
            ("README", lambda rows: rows[0].update(repo_id=alignment.ORG_CARD_SPACE_ID)),
            ("mutable revision", lambda rows: rows[0].update(revision="main")),
            ("malformed ID", lambda rows: rows[0].update(repo_id=[])),
            ("classification injection", lambda rows: rows[0].update(disposition="KEEP")),
            ("unsorted IDs", lambda rows: rows.reverse()),
        ):
            candidate = copy.deepcopy(original)
            mutate(candidate["spaces"])
            candidates.append((label, candidate))
        for label, candidate in candidates:
            with self.subTest(label=label):
                self.assertTrue(alignment.validate_public_space_observation(candidate))
        self.assertTrue(alignment.validate_public_space_observation(None))

    def test_live_public_membership_requires_exact_ids_not_only_matching_count(self) -> None:
        observation = self.contract["public_space_membership_observation"]
        rows = [{"id": row["repo_id"]} for row in observation["spaces"]]
        failures, observed = alignment.validate_live_public_space_membership(rows, observation)
        self.assertEqual(failures, [])
        self.assertEqual(observed, alignment.EXPECTED_PUBLIC_SPACE_IDS)
        with_org_card = rows + [{"id": alignment.ORG_CARD_SPACE_ID}]
        failures, observed = alignment.validate_live_public_space_membership(with_org_card, observation)
        self.assertEqual(failures, [])
        self.assertNotIn(alignment.ORG_CARD_SPACE_ID, observed)
        for label, candidate in (
            ("missing", rows[:-1]),
            ("extra", rows + [{"id": "SZLHOLDINGS/unreviewed"}]),
            ("same count wrong ID", rows[:-1] + [{"id": "SZLHOLDINGS/unreviewed"}]),
            ("duplicate", rows + [rows[0]]),
            ("malformed", rows + [None]),
            ("wrong namespace", rows + [{"id": "another-owner/a11oy"}]),
            ("unavailable", None),
            ("empty success", []),
        ):
            with self.subTest(label=label):
                failures, _observed = alignment.validate_live_public_space_membership(candidate, observation)
                self.assertTrue(failures)

    def test_public_membership_loader_preserves_strict_validation(self) -> None:
        observation = self.contract["public_space_membership_observation"]
        rows = [{"id": row["repo_id"]} for row in observation["spaces"]]
        with patch.object(
            alignment, "fetch_hf_page", return_value=(json.dumps(rows).encode(), None)
        ):
            loaded = alignment.list_hf("spaces")
        failures, observed = alignment.validate_live_public_space_membership(loaded, observation)
        self.assertEqual(failures, [])
        self.assertEqual(observed, alignment.EXPECTED_PUBLIC_SPACE_IDS)
        self.assertTrue(loaded.complete)
        self.assertEqual(loaded.pages, 1)
        for malformed in (None, "invalid", 42, []):
            with self.subTest(malformed=malformed), patch.object(
                alignment, "fetch_hf_page",
                return_value=(json.dumps(rows + [malformed]).encode(), None)
            ):
                with self.assertRaisesRegex(alignment.AlignmentError, "malformed row"):
                    alignment.list_hf("spaces")

    def test_listing_equality_preserves_rows_and_checks_coverage_metadata(self) -> None:
        rows = [{"id": "SZLHOLDINGS/synthetic"}]
        first = alignment.HFListing(rows, pages=1)
        second = alignment.HFListing(rows, pages=1)
        second.observed_at = first.observed_at
        self.assertEqual(first, second)
        self.assertEqual(first, rows)
        self.assertEqual(rows, first)
        second.pages = 2
        self.assertNotEqual(first, second)
        second.pages = 1
        second.complete = False
        self.assertNotEqual(first, second)
        second.complete = True
        second.observed_at = "different-observation"
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, object())

    def test_provider_loader_refuses_unproved_terminal_or_oversized_page(self) -> None:
        for kind in ("spaces", "models", "datasets"):
            rows = [{"id": f"SZLHOLDINGS/synthetic-{i}"} for i in range(101)]
            with self.subTest(kind=kind, count=100), patch.object(
                alignment, "fetch_hf_page",
                return_value=(json.dumps(rows[:100]).encode(), None),
            ):
                with self.assertRaisesRegex(alignment.AlignmentError, "completion proof"):
                    alignment.list_hf(kind)
            with self.subTest(kind=kind, count=101), patch.object(
                alignment, "fetch_hf_page",
                return_value=(json.dumps(rows).encode(), None),
            ):
                with self.assertRaisesRegex(alignment.AlignmentError, "oversized page"):
                    alignment.list_hf(kind)

    def test_hf_inventory_cursor_pages_preserve_exact_author_membership(self) -> None:
        for count in (0, 1, 99, 101, 237):
            kind = "models"
            rows = [{"id": f"SZLHOLDINGS/synthetic-{i:04d}"} for i in range(count)]
            pages = [rows[i:i + alignment.HF_PAGE_SIZE] for i in range(0, count, alignment.HF_PAGE_SIZE)]
            if not pages:
                pages = [[]]
            calls: list[str] = []

            def provider(url: str):
                page_index = len(calls)
                calls.append(url)
                next_link = None
                if page_index < len(pages) - 1:
                    next_url = (
                        f"{alignment.HF_API}/{kind}?author=SZLHOLDINGS"
                        f"&limit=100&full=true&cursor=page-{page_index + 2}"
                    )
                    next_link = f'<{next_url}>; rel="next"'
                return json.dumps(pages[page_index]).encode(), next_link

            with self.subTest(count=count), patch.object(
                alignment, "fetch_hf_page", side_effect=provider
            ):
                loaded = alignment.list_hf(kind)
                self.assertEqual(list(loaded), rows)
                self.assertEqual(loaded.pages, len(pages))
                self.assertTrue(loaded.complete)
                self.assertEqual(len(calls), len(pages))

    def test_hf_inventory_rejects_cross_origin_links_duplicates_and_cursor_loops(self) -> None:
        kind = "datasets"
        first = [{"id": f"SZLHOLDINGS/synthetic-{i:04d}"} for i in range(100)]
        prefix = f"{alignment.HF_API}/{kind}?author=SZLHOLDINGS&limit=100&full=true"
        for candidate in (
            f"https://attacker.invalid/api/{kind}?author=SZLHOLDINGS&limit=100&full=true&cursor=2",
            f"{alignment.HF_API}/{kind}?author=OTHER&limit=100&full=true&cursor=2",
            f"{alignment.HF_API}/{kind}?author=SZLHOLDINGS&limit=100&full=true&cursor=2&sort=likes",
            f"{alignment.HF_API}/{kind}?author=SZLHOLDINGS&limit=100&full=true&cursor=2&cursor=3",
        ):
            with self.subTest(next_url=candidate), patch.object(
                alignment, "fetch_hf_page",
                return_value=(json.dumps(first).encode(), f'<{candidate}>; rel="next"'),
            ):
                with self.assertRaises(alignment.AlignmentError):
                    alignment.list_hf(kind)

        next_url = prefix + "&cursor=2"
        with patch.object(alignment, "fetch_hf_page", side_effect=[
            (json.dumps(first).encode(), f'<{next_url}>; rel="next"'),
            (json.dumps(first).encode(), f'<{next_url}>; rel="next"'),
        ]):
            with self.assertRaisesRegex(alignment.AlignmentError, "duplicated an ID"):
                alignment.list_hf(kind)
        with patch.object(alignment, "fetch_hf_page", side_effect=[
            (json.dumps(first).encode(), f'<{next_url}>; rel="next"'),
            (json.dumps([{"id": "SZLHOLDINGS/next"}]).encode(), f'<{next_url}>; rel="next"'),
        ]):
            with self.assertRaisesRegex(alignment.AlignmentError, "repeated a cursor"):
                alignment.list_hf(kind)
        with patch.object(alignment, "fetch_hf_page", return_value=(
            json.dumps(first).encode(), '<https://huggingface.co/api/models?cursor=2>; rel="next"',
        )):
            with self.assertRaises(alignment.AlignmentError):
                alignment.list_hf(kind)

    def test_hf_pagination_rejects_duplicate_params_before_fetch(self) -> None:
        base = f"{alignment.HF_API}/models?author=SZLHOLDINGS&limit=100&full=true"
        for candidate in (
            base + "&cursor=1&cursor=2",
            base + "&cursor=1&full=true",
            base + "&cursor=1&author=SZLHOLDINGS",
            base + "&cursor=",
        ):
            with self.subTest(url=candidate), self.assertRaisesRegex(
                alignment.AlignmentError, "scope"
            ):
                alignment.validate_hf_page_url(candidate, "models", next_page=True)

    def test_hf_inventory_page_budget_and_network_errors_fail_closed(self) -> None:
        calls: list[str] = []
        def endless(url: str):
            calls.append(url)
            next_url = (
                f"{alignment.HF_API}/models?author=SZLHOLDINGS"
                f"&limit=100&full=true&cursor={len(calls)}"
            )
            offset = (len(calls) - 1) * 100
            current = [
                {"id": f"SZLHOLDINGS/synthetic-{offset + i:04d}"}
                for i in range(100)
            ]
            return json.dumps(current).encode(), f'<{next_url}>; rel="next"'

        with patch.object(alignment, "fetch_hf_page", side_effect=endless):
            with self.assertRaisesRegex(alignment.AlignmentError, "page budget"):
                alignment.list_hf("models")
        self.assertEqual(len(calls), alignment.HF_MAX_PAGES)
        with patch.object(
            alignment, "fetch_hf_page", side_effect=TimeoutError("provider timeout")
        ):
            with self.assertRaises(TimeoutError):
                alignment.list_hf("models")

    def test_unavailable_live_evidence_cannot_be_issued_as_divergent_or_aligned(self) -> None:
        revision = "a" * 40
        with (
            patch.object(alignment, "checked_out_revision", return_value=revision),
            patch.object(alignment, "validate_live", side_effect=alignment.AlignmentError(
                "Hugging Face models inventory exceeded page budget"
            )),
        ):
            receipt = alignment.build_receipt(ROOT, live=True)
        self.assertEqual(receipt["state"], "UNAVAILABLE")
        self.assertEqual(receipt["failures"], [])
        self.assertEqual(len(receipt["unavailable"]), 1)
        self.assertIsNone(receipt["live_observation"])

        with (
            patch.object(alignment, "checked_out_revision", return_value=revision),
            patch.object(alignment, "validate_live", return_value=(
                ["verified source mismatch"], {"unavailable": ["provider timeout"]}
            )),
        ):
            receipt = alignment.build_receipt(ROOT, live=True)
        self.assertEqual(receipt["state"], "UNAVAILABLE")
        self.assertIn("verified source mismatch", receipt["failures"])
        self.assertEqual(receipt["unavailable"], ["provider timeout"])

    def test_live_readback_runs_after_publication_or_explicit_audit(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "estate-one-fabric-alignment.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn('workflows: ["Hugging Face organization front door"]', workflow)
        local_job, live_job = workflow.split("  live-contract:\n", 1)
        self.assertIn("github.event_name != 'workflow_run'", local_job)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", live_job)
        self.assertNotIn("github.event_name == 'pull_request'", live_job)
        self.assertIn("github.event_name == 'schedule'", live_job)
        self.assertIn("github.event_name == 'workflow_dispatch'", live_job)
        self.assertIn("needs.local-contract.result == 'success'", live_job)
        self.assertNotIn("github.event_name == 'push'", live_job)
        # Checkout uses the effect gate's admitted exact-event expression. The
        # preceding guard rejects foreign PRs and stale workflow_run commits.
        exact_head = "${{ github.event.pull_request.head.sha || github.event.merge_group.head_sha || github.sha }}"
        self.assertEqual(workflow.count("ref: " + exact_head), 2)
        self.assertEqual(workflow.count("ADMITTED_SHA: " + exact_head), 2)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha", workflow)
        self.assertIn('[ "$RUN_HEAD_REPOSITORY" != "$THIS_REPOSITORY" ] || [ "$RUN_HEAD_BRANCH" != "main" ]', workflow)
        self.assertIn('[[ "$sha" =~ ^[0-9a-f]{40}$ ]]', workflow)

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

        wrong_source = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source_repository": "szl-holdings/szl-real-estate",
                    "source_revision": expected,
                }
            ).encode(),
        )
        self.assertFalse(wrong_source["matched"])
        self.assertEqual(
            wrong_source["attempts"][0]["source_evidence"], "conflicting"
        )

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

    def test_exact_revision_only_build_info_is_bound_by_contract_origin(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/terra",
            "canonical_source": "szl-holdings/a11oy:verticals/terra",
            "deployment_source": "szl-holdings/a11oy",
        }
        expected = "c" * 40
        requested: list[str] = []

        def fetch(url: str, **_kwargs) -> bytes:
            requested.append(url)
            self.assertEqual(
                alignment.urllib.parse.urlsplit(url).path,
                "/api/build-info",
            )
            return json.dumps({"build": {"revision": expected}}).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)

        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/api/build-info")
        self.assertIsNone(observation["observed_source"])
        self.assertEqual(
            observation["attempts"][0]["source_evidence"],
            "contract-bound-origin",
        )
        self.assertEqual(len(observation["attempts"]), 1)
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)

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
        space_ids = sorted(alignment.EXPECTED_PUBLIC_SPACE_IDS)

        def fetch(url: str, **_kwargs) -> bytes:
            if "/repos/" in url:
                return b'{"archived":false,"visibility":"public","default_branch":"main"}'
            if url == f"{alignment.HF_API}/spaces/{alignment.ORG_CARD_SPACE_ID}":
                return json.dumps({"id": alignment.ORG_CARD_SPACE_ID}).encode()
            return json.dumps(product).encode()

        def list_hf(kind: str):
            if kind == "models":
                rows = [{"id": f"SZLHOLDINGS/test-model-{i}"} for i in range(69)]
            elif kind == "datasets":
                rows = [{"id": f"SZLHOLDINGS/test-dataset-{i}"} for i in range(174)]
            else:
                rows = [{"id": repo_id} for repo_id in space_ids]
            return alignment.HFListing(rows, pages=1)

        seen: list[str] = []

        def binding(row, expected_revision):
            seen.append(row["repo_id"])
            return {
                "repo_id": row["repo_id"],
                "expected_revision": expected_revision,
                "observed_revision": expected_revision,
                "matched": True,
            }

        with (
            patch.object(alignment, "fetch_bytes", side_effect=fetch),
            patch.object(alignment, "github_main_sha", return_value=revision),
            patch.object(alignment, "list_hf", side_effect=list_hf),
            patch.object(alignment, "runtime_source_binding", side_effect=binding),
        ):
            failures, observation = alignment.validate_live(self.contract)

        self.assertEqual(failures, [])
        self.assertEqual(
            set(seen),
            alignment.EXPECTED_PORTFOLIO_SPACES | {alignment.ORG_CARD_SPACE_ID},
        )
        self.assertNotIn("SZLHOLDINGS/yarqa", seen)
        self.assertEqual(len(observation["runtime_source_bindings"]), 14)
        self.assertEqual(observation["huggingface"]["public_listed_spaces"], 75)
        self.assertEqual(observation["huggingface"]["portfolio_spaces"], 14)
        self.assertEqual(observation["huggingface"]["inventory_only_spaces"], 1)
        self.assertEqual(
            observation["huggingface"]["inventory_only_space_ids"],
            ["SZLHOLDINGS/yarqa"],
        )
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
        self.assertEqual(len(portfolio_ids), 14)
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
