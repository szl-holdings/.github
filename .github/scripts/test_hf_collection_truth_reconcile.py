#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hf_collection_truth_reconcile", HERE / "hf_collection_truth_reconcile.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def item(item_id: str, object_id: str) -> SimpleNamespace:
    return SimpleNamespace(item_id=item_id, item_object_id=object_id)


class FakeApi:
    def __init__(self, *, duplicate_start: bool = False, missing_anchor: bool = False) -> None:
        anchors = sorted(module.REQUIRED_TRAINED_WEIGHTS)
        if missing_anchor:
            anchors.pop()
        self.start = SimpleNamespace(
            title=module.START_TITLE,
            slug="SZLHOLDINGS/start-here",
            description="Canonical site: a11oy.com.",
            items=[],
        )
        self.trained = SimpleNamespace(
            title=module.TRAINED_TITLE,
            slug="SZLHOLDINGS/trained-models",
            description="weights only",
            items=[item(repo_id, f"anchor-{index}") for index, repo_id in enumerate(anchors)]
            + [item(module.NEMO_REPO, "nemo-object")],
        )
        self.duplicate_start = duplicate_start
        self.updated: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, str]] = []

    def list_collections(self, *, owner: str, limit: int):
        assert owner == module.ORG
        assert limit == 99
        result = [self.start, self.trained]
        if self.duplicate_start:
            result.append(
                SimpleNamespace(title=module.START_TITLE, slug="SZLHOLDINGS/start-here-copy")
            )
        return result

    def get_collection(self, slug: str):
        if slug == self.start.slug:
            return self.start
        if slug == self.trained.slug:
            return self.trained
        raise AssertionError(f"unexpected slug: {slug}")

    def update_collection_metadata(self, *, collection_slug: str, description: str):
        assert collection_slug == self.start.slug
        self.updated.append((collection_slug, description))
        self.start.description = description

    def delete_collection_item(self, *, collection_slug: str, item_object_id: str):
        assert collection_slug == self.trained.slug
        self.deleted.append((collection_slug, item_object_id))
        self.trained.items = [
            candidate
            for candidate in self.trained.items
            if candidate.item_object_id != item_object_id
        ]


class ReconcileTests(unittest.TestCase):
    def test_dry_run_is_zero_effect(self) -> None:
        api = FakeApi()
        report = module.CollectionTruthReconciler(api, publish=False).run()
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["verification"]["status"], "NOT_EVALUATED")
        self.assertEqual(api.updated, [])
        self.assertEqual(api.deleted, [])
        self.assertIn("a11oy.com", api.start.description)

    def test_publish_repairs_domain_and_recipe_membership_then_reads_back(self) -> None:
        api = FakeApi()
        report = module.CollectionTruthReconciler(api, publish=True).run()
        self.assertEqual(report["verification"]["errors"], [])
        self.assertEqual(api.start.description, module.START_DESCRIPTION)
        self.assertNotIn(module.NEMO_REPO, report["verification"]["trained_items"])
        self.assertEqual(api.deleted, [(api.trained.slug, "nemo-object")])
        self.assertEqual(len(api.updated), 1)

    def test_duplicate_collection_title_fails_closed(self) -> None:
        with self.assertRaisesRegex(module.ReconcileError, "duplicate collection title"):
            module.CollectionTruthReconciler(
                FakeApi(duplicate_start=True), publish=True
            ).run()

    def test_missing_trained_weight_anchor_refuses_removal(self) -> None:
        api = FakeApi(missing_anchor=True)
        with self.assertRaisesRegex(module.ReconcileError, "anchors are missing"):
            module.CollectionTruthReconciler(api, publish=True).run()
        self.assertEqual(api.deleted, [])

    def test_contract_is_narrow(self) -> None:
        source = (HERE / "hf_collection_truth_reconcile.py").read_text(encoding="utf-8")
        self.assertIn("https://a-11-oy.com", source)
        self.assertIn(module.NEMO_REPO, source)
        self.assertNotIn("create_collection(", source)
        self.assertNotIn("delete_collection(", source)
        self.assertNotIn("upload_file(", source)

    def test_hub_token_selection_uses_approved_fallback_order(self) -> None:
        self.assertEqual(
            module._hub_token_from_environment(
                {
                    "HF_ORG_TOKEN": "org-primary",
                    "HF_ORG_TOKEN1": "org-secondary",
                    "HF_TOKEN": "generic",
                }
            ),
            "org-primary",
        )
        self.assertEqual(
            module._hub_token_from_environment(
                {"HF_ORG_TOKEN1": "org-secondary", "HF_TOKEN": "generic"}
            ),
            "org-secondary",
        )
        self.assertEqual(
            module._hub_token_from_environment({"HF_TOKEN": "generic"}),
            "generic",
        )
        self.assertIsNone(module._hub_token_from_environment({}))

    def test_manual_publish_is_pinned_to_main(self) -> None:
        workflow = (
            HERE.parent / "workflows" / "hf-collection-truth-reconcile.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('[ "$GITHUB_REF" = "refs/heads/main" ]', workflow)


if __name__ == "__main__":
    unittest.main()
