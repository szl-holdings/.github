#!/usr/bin/env python3
"""Network-free contracts for SZL Holographic Space Fabric v2."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / ".github" / "scripts" / "rollout_holographic_spaces_v2.py"
RUNNER_PATH = ROOT / ".github" / "scripts" / "run_holographic_spaces_v2.py"
ASSETS = ROOT / "design" / "holographic-v2"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


core = load("holographic_space_core_test", CORE_PATH)
runner = load("holographic_space_runner_test", RUNNER_PATH)


class AssetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = (ASSETS / "szl-space-hologram.css").read_text(encoding="utf-8")
        cls.javascript = (ASSETS / "szl-space-hologram.js").read_text(encoding="utf-8")
        cls.registry = json.loads((ASSETS / "theme-registry.json").read_text(encoding="utf-8"))

    def test_registry_defines_unique_product_families(self) -> None:
        families = self.registry["curated_families"]
        self.assertGreaterEqual(len(families), 13)
        self.assertEqual(len({value["motif"] for value in families.values()}), len(families))
        self.assertFalse(self.registry["unknown_space_policy"]["reshuffle_between_deployments"])

    def test_assets_are_non_tracking_and_local(self) -> None:
        combined = self.css + self.javascript
        for prohibited in (
            "fetch(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "sessionStorage",
            "document.cookie",
            "google-analytics",
            "fonts.googleapis.com",
            "cdn.jsdelivr.net",
            "unpkg.com",
        ):
            self.assertNotIn(prohibited, combined)

    def test_accessibility_and_performance_contracts(self) -> None:
        for token in (
            "prefers-reduced-motion",
            "prefers-contrast",
            "forced-colors",
            "pointer: coarse",
            "focus-visible",
            "@media print",
        ):
            self.assertIn(token, self.css)
        for token in ("hardwareConcurrency", "deviceMemory", "saveData", "visibilitychange"):
            self.assertIn(token, self.javascript)

    def test_unknown_space_identity_is_deterministic(self) -> None:
        self.assertIn("0x811c9dc5", self.javascript)
        self.assertIn("Math.imul", self.javascript)
        self.assertIn('source: "deterministic"', self.javascript)
        self.assertIn("szlSpaceThemeSource", self.javascript)

    def test_motifs_change_geometry_not_only_color(self) -> None:
        for motif in (
            "command-grid",
            "signal-aurora",
            "bathymetric-radar",
            "parcel-topography",
            "threat-lattice",
            "case-lines",
            "editorial-orbit",
            "graph-mesh",
            "build-circuit",
            "recursive-weave",
            "agent-swarm",
            "cell-membrane",
            "checksum-ledger",
        ):
            self.assertIn(f'data-szl-space-motif="{motif}"', self.css)
        self.assertEqual(self.css.count("{"), self.css.count("}"))
        self.assertEqual(self.javascript.count("{"), self.javascript.count("}"))


class AdapterContract(unittest.TestCase):
    def test_static_adapter_is_idempotent(self) -> None:
        original = "<!doctype html><html><head><title>X</title></head><body><main>X</main></body></html>"
        once = core.adapt_static(original, "./szl-space-hologram.css", "./szl-space-hologram.js", "demo-space")
        twice = core.adapt_static(once, "./szl-space-hologram.css", "./szl-space-hologram.js", "demo-space")
        self.assertEqual(once, twice)
        self.assertEqual(once.count(core.STYLE_MARKER), 1)
        self.assertEqual(once.count(core.SCRIPT_MARKER), 1)
        self.assertIn("demo-space", once)

    def test_next_adapter_is_idempotent(self) -> None:
        original = "export default function Root({children}) { return <html><head></head><body>{children}</body></html> }"
        once = core.adapt_next(original, "demo-space")
        self.assertEqual(once, core.adapt_next(once, "demo-space"))
        self.assertIn("/szl-space-hologram.css", once)
        self.assertIn("/szl-space-hologram.js", once)

    def test_gradio_adapter_adds_and_merges_shell_arguments(self) -> None:
        original = '''"""demo"""\nfrom __future__ import annotations\nimport gradio as gr\n\nwith gr.Blocks(title="Demo") as demo:\n    gr.Markdown("Hello")\n'''
        patched = core.adapt_gradio(original)
        self.assertLess(patched.index("from __future__ import annotations"), patched.index("from szl_hologram_assets"))
        self.assertIn("css=A11OY_HOLO_CSS", patched)
        self.assertIn("head=A11OY_HOLO_HEAD", patched)
        compile(patched, "app.py", "exec")
        self.assertEqual(core.adapt_gradio(patched), patched)

        custom = "import gradio as gr\nwith gr.Blocks(css=BASE_CSS, head=BASE_HEAD) as demo:\n    pass\n"
        merged = core.adapt_gradio(custom)
        self.assertIn("merge_hologram_css(BASE_CSS)", merged)
        self.assertIn("merge_hologram_head(BASE_HEAD)", merged)
        compile(merged, "app.py", "exec")

    def test_streamlit_adapter_orders_import_before_render_with_or_without_page_config(self) -> None:
        with_config = "import streamlit as st\nst.set_page_config(page_title='Demo')\nst.title('Hello')\n"
        patched = runner._fixed_streamlit_adapter(with_config, "demo-space")
        render_call = patched.index("render_szl_hologram(")
        self.assertLess(patched.index("from szl_hologram_streamlit"), render_call)
        self.assertLess(patched.index("st.set_page_config"), render_call)
        compile(patched, "app.py", "exec")

        without_config = "import streamlit as st\nst.title('Hello')\n"
        patched = runner._fixed_streamlit_adapter(without_config, "demo-space")
        render_call = patched.index("render_szl_hologram(")
        self.assertLess(patched.index("from szl_hologram_streamlit"), render_call)
        self.assertLess(render_call, patched.index("st.title"))
        compile(patched, "app.py", "exec")

    def test_generated_helpers_compile(self) -> None:
        compile(core.gradio_helper(), "szl_hologram_assets.py", "exec")
        compile(core.streamlit_helper(), "szl_hologram_streamlit.py", "exec")


class ControllerSafetyContract(unittest.TestCase):
    def test_default_mode_is_dry_run(self) -> None:
        args = core.parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.merge_green)
        self.assertEqual(args.token_env, "SZL_GITHUB_TOKEN")

    def test_source_never_force_pushes_or_mutates_protection(self) -> None:
        source = CORE_PATH.read_text(encoding="utf-8") + RUNNER_PATH.read_text(encoding="utf-8")
        for prohibited in (
            "--force",
            "force=true",
            "force: true",
            "branches/protection",
            "required_status_checks",
            "delete_branch_on_merge",
        ):
            self.assertNotIn(prohibited, source)
        self.assertIn('"default_branch_writes": False', source)
        self.assertIn('"direct_huggingface_writes": False', source)
        self.assertIn("ALLOWED_CHECK_CONCLUSIONS", source)

    def test_exact_mapping_beats_heuristic_mapping(self) -> None:
        space = core.Space("demo", "gradio", "RUNNING", "https://huggingface.co/spaces/SZLHOLDINGS/demo")
        repo = {"full_name": "szl-holdings/demo-source", "name": "something", "homepage": "", "description": "", "topics": []}
        score, reason = core.mapping_score(space, repo, {"demo": "szl-holdings/demo-source"})
        self.assertEqual(score, 1000)
        self.assertEqual(reason, "canonical source map")

    def test_asset_loader_verifies_schema(self) -> None:
        css, javascript, registry = core.read_assets(ASSETS)
        self.assertTrue(css)
        self.assertTrue(javascript)
        self.assertEqual(json.loads(registry)["schema"], "szl.holographic-space-theme-registry/v2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
