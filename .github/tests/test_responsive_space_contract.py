#!/usr/bin/env python3
"""Network-free tests for the Public Experience v3 rollout extension."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".github" / "scripts" / "responsive_space_contract.py"
CORE_MODULE = ROOT / ".github" / "scripts" / "rollout_holographic_spaces_v2.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


responsive = _load("responsive_space_contract_test", MODULE)
rollout_core = _load("responsive_source_root_core_test", CORE_MODULE)
responsive.install(rollout_core)


class Change:
    def __init__(self, path: str, content: str):
        self.path = path
        self.content = content


class FakeGitHub:
    def __init__(self, files: dict[str, str]):
        self.files = dict(files)

    def tree(self, _full_name: str, _default_branch: str):
        return [{"path": path} for path in sorted(self.files)]

    def file(self, _full_name: str, path: str, _default_branch: str):
        if path not in self.files:
            raise AssertionError(f"unexpected file read: {path}")
        return self.files[path], "sha"


def _repo(full_name: str) -> dict[str, object]:
    return {
        "full_name": full_name,
        "name": full_name.split("/", 1)[-1],
        "default_branch": "main",
        "homepage": "",
        "description": "",
        "topics": [],
        "archived": False,
        "disabled": False,
        "fork": False,
    }


class ResponsiveSpaceContractTests(unittest.TestCase):
    def test_assets_cover_phone_tablet_desktop_theatre_and_zoom(self) -> None:
        css, javascript = responsive._read_assets()
        for marker in (
            "max-width: 479px",
            "min-width: 768px",
            "min-width: 1024px",
            "min-width: 1440px",
            "min-width: 1920px",
            "min-width: 2560px",
            "100dvh",
            "safe-area-inset",
            "--szl-touch-target",
            "--szl-touch-target-coarse",
            "--szl-effective-inline-size",
            "data-szl-zoom-tier",
            "overflow-x: clip",
            "prefers-reduced-motion",
            "prefers-contrast",
            "forced-colors",
            "@media print",
        ):
            self.assertIn(marker, css)
        for marker in (
            "__SZL_PUBLIC_EXPERIENCE_V3__",
            "szlPublicExperienceV3",
            "szlSpaceHoloV2",
            "szlViewportTier",
            "szlZoomTier",
            "szlAudience",
            "visualViewport",
            "requestAnimationFrame",
            "MutationObserver",
            "document.title",
            "effectiveWidth",
            "phone",
            "tablet",
            "theatre",
            "ultrawide",
        ):
            self.assertIn(marker, javascript)

    def test_assets_are_local_and_nontracking(self) -> None:
        css, javascript = responsive._read_assets()
        self.assertNotIn("@import", css)
        for token in (
            "fetch(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "sessionStorage",
            "document.cookie",
        ):
            self.assertNotIn(token, javascript)
        self.assertEqual(css.count("{"), css.count("}"))

    def test_zoom_navigation_is_bounded_and_not_a_fixed_viewport_sheet(self) -> None:
        _, javascript = responsive._read_assets()
        self.assertIn(":host([data-szl-zoom-tier=high])", javascript)
        self.assertIn("position:absolute!important", javascript)
        self.assertIn("max-height:min(56dvh,420px)", javascript)
        self.assertIn("min-width:54px!important", javascript)
        self.assertIn("min-height:48px!important", javascript)
        self.assertIn("border-radius:10px!important", javascript)
        self.assertNotIn("nav{position:fixed!important", javascript)

    def test_empty_title_fallback_is_non_destructive(self) -> None:
        _, javascript = responsive._read_assets()
        self.assertIn('if (String(document.title || "").trim()) return;', javascript)
        self.assertIn('document.title = declaredIdentity() + " · SZL Holdings";', javascript)
        self.assertIn("SZLPublicExperience", javascript)
        self.assertIn("snapshot: snapshot", javascript)

    def test_append_once_is_idempotent(self) -> None:
        once = responsive._append_once("base", "SZL Public Experience v3\n", responsive.CSS_MARKER)
        twice = responsive._append_once(once, "SZL Public Experience v3\n", responsive.CSS_MARKER)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(responsive.CSS_MARKER), 1)

    def _core(self, original_plan):
        def streamlit_helper():
            return (
                "markup = f\"\"\"<script>"
                "document.documentElement.dataset.szlSpaceSlug={slug!r};</script>"
                "\"\"\"\n"
            )

        return SimpleNamespace(
            read_assets=lambda root: ("base css", "base js", "{}"),
            plan_repository=original_plan,
            pr_body=lambda plan, digest: "base body",
            streamlit_helper=streamlit_helper,
            gradio_helper=lambda: "gradio helper",
            NEXT_LAYOUTS=("app/layout.tsx",),
            STATIC_INDEXES=("index.html",),
            PYTHON_ENTRIES=("app.py",),
            Change=Change,
            BRANCH="design/old",
        )

    def test_install_extends_assets_and_moves_review_branch(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned",
                adapter="static",
                entrypoint="index.html",
                changes=[Change("szl-space-hologram.css", args[-2])],
            )
        )
        responsive.install(core)
        css, javascript, registry = core.read_assets(Path("unused"))
        self.assertIn(responsive.CSS_MARKER, css)
        self.assertIn(responsive.JS_MARKER, javascript)
        self.assertEqual(registry, "{}")
        self.assertEqual(core.BRANCH, "design/szl-public-experience-v3")
        helper = core.streamlit_helper()
        self.assertIn("dataset.szlPublicExperienceV3", helper)
        self.assertIn("dataset.szlViewportTier", helper)
        self.assertIn("dataset.szlZoomTier", helper)
        self.assertIn("document.title", helper)
        self.assertIn("SZL Holdings", helper)

    def test_already_integrated_repository_becomes_reviewable_refresh(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="already-integrated",
                adapter=None,
                entrypoint=None,
                changes=[],
            )
        )
        responsive.install(core)

        class GitHub:
            @staticmethod
            def tree(full_name, default_branch):
                return [
                    {"path": "index.html"},
                    {"path": "szl-space-hologram.css"},
                    {"path": "szl-space-hologram.js"},
                ]

            @staticmethod
            def file(full_name, path, default_branch):
                return ("legacy v2 asset", "sha")

        css = "v2\nSZL Public Experience v3\n"
        javascript = "v2\n__SZL_PUBLIC_EXPERIENCE_V3__\n"
        plan = core.plan_repository(
            GitHub(),
            {"full_name": "szl-holdings/example", "default_branch": "main"},
            [],
            100,
            "test",
            css,
            javascript,
        )
        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-existing-host")
        self.assertEqual(plan.entrypoint, "index.html")
        self.assertEqual(
            {change.path for change in plan.changes},
            {"szl-space-hologram.css", "szl-space-hologram.js"},
        )

    def test_product_owned_asset_host_is_refreshed_without_duplicate_shell(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned",
                adapter="static",
                entrypoint="app/static/index.html",
                changes=[Change("app/static/szl-space-hologram.css", args[-2])],
            )
        )
        responsive.install(core)

        class GitHub:
            @staticmethod
            def tree(full_name, default_branch):
                return [
                    {"path": "app/static/index.html"},
                    {"path": "app/static/holo.css"},
                    {"path": "app/static/holo.js"},
                ]

            @staticmethod
            def file(full_name, path, default_branch):
                return ("product-owned asset", "sha")

        plan = core.plan_repository(
            GitHub(),
            {"full_name": "szl-holdings/david-leads", "default_branch": "main"},
            [],
            1000,
            "canonical source map",
            "combined css",
            "combined js",
        )
        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-existing-host")
        self.assertEqual(plan.entrypoint, "app/static/index.html")
        self.assertEqual(
            {change.path for change in plan.changes},
            {"app/static/holo.css", "app/static/holo.js"},
        )
        for change in plan.changes:
            self.assertIn(
                "SZL Public Experience v3"
                if change.path.endswith(".css")
                else "__SZL_PUBLIC_EXPERIENCE_V3__",
                change.content,
            )

    def test_reviewed_nested_static_root_receives_adjacent_assets(self) -> None:
        original_map = rollout_core.LOCAL_SOURCE_MAP
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-map.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "szl.public-space-source-map/v1",
                        "sources": [
                            {
                                "space": "ayllu",
                                "repo": "szl-holdings/ayllu",
                                "source_root": "ayllu/static/chamber.html",
                                "ownership": "source-owned-incubation-lab",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rollout_core.LOCAL_SOURCE_MAP = path
            try:
                github = FakeGitHub(
                    {
                        "ayllu/static/chamber.html": (
                            "<!doctype html><html><head><title>Ayllu</title></head>"
                            "<body><main>Council</main></body></html>"
                        )
                    }
                )
                space = rollout_core.Space(
                    "ayllu",
                    "docker",
                    "RUNNING",
                    "https://huggingface.co/spaces/SZLHOLDINGS/ayllu",
                )
                plan = rollout_core.plan_repository(
                    github,
                    _repo("szl-holdings/ayllu"),
                    [space],
                    1000,
                    "canonical source map",
                    "combined css",
                    "combined javascript",
                )
            finally:
                rollout_core.LOCAL_SOURCE_MAP = original_map

        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-explicit-static")
        self.assertEqual(plan.entrypoint, "ayllu/static/chamber.html")
        self.assertEqual(
            {change.path for change in plan.changes},
            {
                "ayllu/static/chamber.html",
                "ayllu/static/szl-space-hologram.css",
                "ayllu/static/szl-space-hologram.js",
            },
        )
        html = next(
            change.content
            for change in plan.changes
            if change.path == "ayllu/static/chamber.html"
        )
        self.assertIn("./szl-space-hologram.css", html)
        self.assertIn("./szl-space-hologram.js", html)
        self.assertIn("data-szl-space-holo-v2", html)

    def test_existing_immune_asset_host_prevents_duplicate_shell(self) -> None:
        original_map = rollout_core.LOCAL_SOURCE_MAP
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-map.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "szl.public-space-source-map/v1",
                        "sources": [
                            {
                                "space": "immune",
                                "repo": "szl-holdings/immune",
                                "source_root": "frontend/index.html",
                                "ownership": "source-owned-capability-channel",
                            },
                            {
                                "space": "immune-lattice",
                                "repo": "szl-holdings/immune",
                                "source_root": "frontend/index.html",
                                "ownership": "source-owned-capability-channel",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rollout_core.LOCAL_SOURCE_MAP = path
            try:
                github = FakeGitHub(
                    {
                        "frontend/index.html": (
                            "<!doctype html><html><head><title>Immune</title></head>"
                            "<body><main>Immune</main></body></html>"
                        ),
                        "frontend/szl-holo-v2.css": "product css",
                        "frontend/szl-holo-v2.js": "product js",
                    }
                )
                spaces = [
                    rollout_core.Space(
                        "immune",
                        "docker",
                        "RUNNING",
                        "https://huggingface.co/spaces/SZLHOLDINGS/immune",
                    ),
                    rollout_core.Space(
                        "immune-lattice",
                        "docker",
                        "RUNNING",
                        "https://huggingface.co/spaces/SZLHOLDINGS/immune-lattice",
                    ),
                ]
                plan = rollout_core.plan_repository(
                    github,
                    _repo("szl-holdings/immune"),
                    spaces,
                    1000,
                    "canonical source map",
                    "combined css",
                    "combined javascript",
                )
            finally:
                rollout_core.LOCAL_SOURCE_MAP = original_map

        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-existing-host")
        self.assertEqual(
            {change.path for change in plan.changes},
            {"frontend/szl-holo-v2.css", "frontend/szl-holo-v2.js"},
        )
        self.assertNotIn(
            "frontend/szl-space-hologram.css",
            {change.path for change in plan.changes},
        )

    def test_unsafe_explicit_root_fails_closed(self) -> None:
        original_map = rollout_core.LOCAL_SOURCE_MAP
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-map.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "szl.public-space-source-map/v1",
                        "sources": [
                            {
                                "space": "ayllu",
                                "repo": "szl-holdings/ayllu",
                                "source_root": "../outside.html",
                                "ownership": "source-owned-incubation-lab",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rollout_core.LOCAL_SOURCE_MAP = path
            try:
                space = rollout_core.Space(
                    "ayllu",
                    "docker",
                    "RUNNING",
                    "https://huggingface.co/spaces/SZLHOLDINGS/ayllu",
                )
                with self.assertRaises(rollout_core.RolloutError) as context:
                    rollout_core.plan_repository(
                        FakeGitHub({}),
                        _repo("szl-holdings/ayllu"),
                        [space],
                        1000,
                        "canonical source map",
                        "combined css",
                        "combined javascript",
                    )
            finally:
                rollout_core.LOCAL_SOURCE_MAP = original_map
        self.assertEqual(context.exception.code, "EXPLICIT_STATIC_ROOT_INVALID")

    def test_pr_body_states_additive_truth_boundary(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned", adapter="static", entrypoint="index.html", changes=[]
            )
        )
        responsive.install(core)
        body = core.pr_body(SimpleNamespace(), "digest")
        self.assertIn("SZL Public Experience v3.1", body)
        self.assertIn("phone widths from 320px", body)
        self.assertIn("400% zoom", body)
        self.assertIn("fallback title", body)
        self.assertIn("investor", body)
        self.assertIn("additive", body.lower())
        self.assertIn("does not replace", body.lower())
        self.assertIn("protected source map", body.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
