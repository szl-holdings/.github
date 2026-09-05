#!/usr/bin/env python3
"""Network-free contracts for rollout source and publisher authority."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / ".github" / "scripts" / "rollout_holographic_spaces_v2.py"
AUTHORITY_PATH = ROOT / ".github" / "scripts" / "source_authority_contract.py"
SOURCE_MAP = ROOT / "design" / "responsive-v3" / "flagship-space-sources.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


core = load("rollout_source_authority_core_test", CORE_PATH)
authority = load("rollout_source_authority_contract_test", AUTHORITY_PATH)
authority.install(core)


def repo(full_name: str, **values):
    name = full_name.split("/", 1)[-1]
    return {
        "full_name": full_name,
        "name": name,
        "default_branch": "main",
        "homepage": "",
        "description": "",
        "topics": [],
        "archived": False,
        "disabled": False,
        "fork": False,
        **values,
    }


class SourceAuthorityContract(unittest.TestCase):
    def test_terra_map_names_the_actual_publisher(self) -> None:
        payload = json.loads(SOURCE_MAP.read_text(encoding="utf-8"))
        terra = next(item for item in payload["sources"] if item["space"] == "terra")
        self.assertEqual(terra["repo"], "szl-holdings/a11oy")
        self.assertEqual(
            terra["source_root"],
            "scripts/hf_publish_vertical_flagships_v4_impl.py",
        )
        self.assertEqual(
            terra["ownership"],
            authority.PUBLISHER_OWNERSHIP,
        )
        self.assertEqual(
            terra["product_source"],
            "szl-holdings/szl-real-estate",
        )
        self.assertEqual(
            terra["product_source_deployment_state"],
            "LINKED_NOT_PUBLISHED",
        )

    def test_explicit_publisher_mapping_beats_product_repo_heuristics(self) -> None:
        spaces = [
            core.Space("terra", "docker", "RUNNING", "https://example.invalid/terra"),
            core.Space("a11oy", "docker", "RUNNING", "https://example.invalid/a11oy"),
        ]
        repositories = [
            repo("szl-holdings/a11oy"),
            repo(
                "szl-holdings/szl-real-estate",
                homepage="https://huggingface.co/spaces/SZLHOLDINGS/terra",
                description="Terra public Space frontend",
                topics=["huggingface"],
            ),
        ]
        grouped, unmapped = core.group_mappings(
            spaces,
            repositories,
            {
                "terra": "szl-holdings/a11oy",
                "a11oy": "szl-holdings/a11oy",
            },
        )
        self.assertIn("szl-holdings/a11oy", grouped)
        self.assertEqual(
            [space.slug for space in grouped["szl-holdings/a11oy"][0]],
            ["terra"],
        )
        self.assertNotIn("szl-holdings/szl-real-estate", grouped)
        self.assertTrue(
            any(
                item["slug"] == "a11oy"
                and "managed outside" in item["reason"]
                for item in unmapped
            )
        )

    def test_provider_mapping_cannot_bypass_excluded_repositories(self) -> None:
        remote = core.Space(
            "provider-only",
            "docker",
            "RUNNING",
            "https://example.invalid/provider-only",
        )
        grouped, unmapped = core.group_mappings(
            [remote],
            [repo("szl-holdings/a11oy")],
            {"provider-only": "szl-holdings/a11oy"},
        )
        self.assertEqual(grouped, {})
        self.assertEqual(unmapped[0]["slug"], "provider-only")
        self.assertIn("no source repository", unmapped[0]["reason"])

    def test_local_excluded_mapping_requires_publisher_ownership(self) -> None:
        original = core.LOCAL_SOURCE_MAP
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-map.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "szl.public-space-source-map/v1",
                        "sources": [
                            {
                                "space": "unauthorized-central",
                                "repo": "szl-holdings/a11oy",
                                "ownership": "source-owned-flagship",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            core.LOCAL_SOURCE_MAP = path
            try:
                with self.assertRaises(core.RolloutError) as context:
                    core.group_mappings(
                        [
                            core.Space(
                                "unauthorized-central",
                                "docker",
                                "RUNNING",
                                "https://example.invalid/unauthorized-central",
                            )
                        ],
                        [repo("szl-holdings/a11oy")],
                        {"unauthorized-central": "szl-holdings/a11oy"},
                    )
            finally:
                core.LOCAL_SOURCE_MAP = original
        self.assertEqual(
            context.exception.code,
            "LOCAL_EXCLUDED_REPOSITORY_UNAUTHORIZED",
        )

    def test_missing_explicit_repository_never_falls_back_to_product_repo(self) -> None:
        terra = core.Space(
            "terra",
            "docker",
            "RUNNING",
            "https://example.invalid/terra",
        )
        grouped, unmapped = core.group_mappings(
            [terra],
            [
                repo(
                    "szl-holdings/szl-real-estate",
                    homepage="https://huggingface.co/spaces/SZLHOLDINGS/terra",
                    description="Terra public Space frontend",
                    topics=["huggingface"],
                )
            ],
            {"terra": "szl-holdings/a11oy"},
        )
        self.assertEqual(grouped, {})
        self.assertEqual(unmapped[0]["declared_repository"], "szl-holdings/a11oy")
        self.assertIn("fallback is forbidden", unmapped[0]["reason"])

    def test_generated_publisher_is_recorded_without_a_guessed_frontend_edit(self) -> None:
        class GitHub:
            @staticmethod
            def tree(full_name, default_branch):
                self.assertEqual(full_name, "szl-holdings/a11oy")
                self.assertEqual(default_branch, "main")
                return [
                    {
                        "path": (
                            "scripts/"
                            "hf_publish_vertical_flagships_v4_impl.py"
                        )
                    }
                ]

        terra = core.Space(
            "terra",
            "docker",
            "RUNNING",
            "https://example.invalid/terra",
        )
        plan = core.plan_repository(
            GitHub(),
            repo("szl-holdings/a11oy"),
            [terra],
            1000,
            "canonical source map",
            "css",
            "javascript",
        )
        self.assertEqual(plan.status, authority.PUBLISHER_MANAGED_STATUS)
        self.assertEqual(plan.adapter, "publisher-generator")
        self.assertEqual(
            plan.entrypoint,
            "scripts/hf_publish_vertical_flagships_v4_impl.py",
        )
        self.assertEqual(plan.changes, [])
        self.assertIsNone(plan.error)

    def test_missing_publisher_entrypoint_fails_closed(self) -> None:
        class GitHub:
            @staticmethod
            def tree(_full_name, _default_branch):
                return []

        terra = core.Space(
            "terra",
            "docker",
            "RUNNING",
            "https://example.invalid/terra",
        )
        with self.assertRaises(core.RolloutError) as context:
            core.plan_repository(
                GitHub(),
                repo("szl-holdings/a11oy"),
                [terra],
                1000,
                "canonical source map",
                "css",
                "javascript",
            )
        self.assertEqual(context.exception.code, "PUBLISHER_ENTRYPOINT_MISSING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
