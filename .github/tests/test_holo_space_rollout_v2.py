#!/usr/bin/env python3
"""Network-free contracts for the Holo-Constellation Space rollout."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "holo_space_rollout_v2.py"
REGISTRY = ROOT / "design" / "holographic-space-v2" / "space-registry.json"

spec = importlib.util.spec_from_file_location("holo_space_rollout_v2", SCRIPT)
assert spec and spec.loader
rollout = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rollout
spec.loader.exec_module(rollout)


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_registry_points_to_canonical_versioned_assets(self) -> None:
        self.assertEqual(self.registry["schema"], "szl.holographic-space-registry/v2")
        assets = self.registry["canonical_assets"]
        self.assertEqual(assets["repository"], "szl-holdings/a11oy")
        self.assertEqual(assets["css"], "console/assets/szl-holo-v2.css")
        self.assertEqual(assets["javascript"], "console/assets/szl-holo-v2.js")

    def test_supported_adapters_are_explicit(self) -> None:
        self.assertEqual(
            set(self.registry["supported_adapters"]),
            {"static-html", "next-layout", "gradio-python", "streamlit-python"},
        )

    def test_safety_contract_prohibits_shortcuts(self) -> None:
        safety = self.registry["safety"]
        self.assertIs(safety["default_branch_write"], False)
        self.assertIs(safety["force_push"], False)
        self.assertIs(safety["branch_protection_change"], False)
        self.assertIs(safety["direct_hugging_face_write"], False)
        self.assertIs(safety["decorative_motion_is_measured_telemetry"], False)


class ThemeTests(unittest.TestCase):
    def test_theme_is_deterministic_and_space_specific(self) -> None:
        first = rollout.theme("szl-real-estate")
        second = rollout.theme("szl-real-estate")
        other = rollout.theme("vessels-command")
        self.assertEqual(first, second)
        self.assertNotEqual(first["palette"], other["palette"])
        self.assertNotEqual(first["id"], other["id"])
        self.assertEqual(first["archetype"], "terra")
        self.assertEqual(other["archetype"], "vessels")

    def test_unknown_space_is_stable_and_independent(self) -> None:
        theme = rollout.theme("new-unseen-space")
        self.assertEqual(theme["archetype"], "independent")
        self.assertIn(theme["motif"], rollout.FALLBACK_MOTIFS)
        self.assertEqual(rollout.fnv1a("new-unseen-space"), rollout.fnv1a("new-unseen-space"))

    def test_unique_javascript_hard_codes_the_space_theme(self) -> None:
        source = "function resolveTheme() {\n  return {};\n}\n"
        rendered = rollout.unique_javascript(source, rollout.theme("lyte-lattice"))
        self.assertIn('"id":"lyte-lattice"', rendered)
        self.assertIn('"source":"space-specific"', rendered)
        self.assertEqual(rendered.count("function resolveTheme()"), 1)


class AdapterTests(unittest.TestCase):
    def test_static_adapter_is_idempotent(self) -> None:
        source = '<!doctype html><html lang="en"><head><title>X</title></head><body><main>X</main></body></html>'
        once = rollout.adapt_static(source, "demo-space", "./szl-holo-v2.css", "./szl-holo-v2.js")
        twice = rollout.adapt_static(once, "demo-space", "./szl-holo-v2.css", "./szl-holo-v2.js")
        self.assertEqual(once, twice)
        self.assertEqual(once.count(rollout.STATIC_MARKER), 1)
        self.assertEqual(once.count("szl-holo-v2.css"), 1)
        self.assertEqual(once.count("szl-holo-v2.js"), 1)

    def test_static_adapter_fails_closed_on_fragment(self) -> None:
        with self.assertRaises(rollout.RolloutError) as raised:
            rollout.adapt_static("<main>fragment</main>", "demo", "x.css", "x.js")
        self.assertEqual(raised.exception.code, "HTML_SHAPE_UNSUPPORTED")

    def test_gradio_adapter_adds_and_composes_css_and_head(self) -> None:
        source = '''"""demo"""\nfrom __future__ import annotations\nimport gradio as gr\nBASE_CSS = "x"\nwith gr.Blocks(css=BASE_CSS, title="Demo") as demo:\n    gr.Markdown("Hello")\n'''
        patched = rollout.adapt_gradio(source)
        self.assertLess(patched.index("from __future__ import annotations"), patched.index("from szl_holo_space_v2"))
        self.assertIn("css=(BASE_CSS) + SZL_HOLO_CSS", patched)
        self.assertIn("head=SZL_HOLO_HEAD", patched)
        self.assertEqual(rollout.adapt_gradio(patched), patched)
        compile(patched, "app.py", "exec")

    def test_gradio_adapter_supports_positional_interface(self) -> None:
        source = "import gradio as gr\ndemo = gr.Interface(fn, 'text', 'text')\n"
        patched = rollout.adapt_gradio(source)
        self.assertIn("css=SZL_HOLO_CSS", patched)
        self.assertIn("head=SZL_HOLO_HEAD", patched)
        compile(patched, "app.py", "exec")

    def test_streamlit_adapter_runs_after_page_config(self) -> None:
        source = '''import streamlit as st\nst.set_page_config(page_title="Demo")\nst.title("Hello")\n'''
        patched = rollout.adapt_streamlit(source)
        self.assertLess(patched.index("from szl_holo_space_v2"), patched.index("st.set_page_config"))
        self.assertLess(patched.index("st.set_page_config"), patched.index("install_streamlit_holo(st)"))
        self.assertLess(patched.index("install_streamlit_holo(st)"), patched.index("st.title"))
        self.assertEqual(rollout.adapt_streamlit(patched), patched)
        compile(patched, "app.py", "exec")

    def test_generated_helpers_are_valid_python(self) -> None:
        css = ":root{color:white}"
        javascript = "function resolveTheme() { return {}; }"
        theme = rollout.theme("demo-space")
        compile(rollout.gradio_helper(css, javascript, theme), "szl_holo_space_v2.py", "exec")
        compile(rollout.streamlit_helper(css, theme), "szl_holo_space_v2.py", "exec")


class MappingTests(unittest.TestCase):
    def test_source_map_parser_accepts_structured_entries(self) -> None:
        value = {
            "spaces": [
                {
                    "space_id": "SZLHOLDINGS/lyte-lattice",
                    "source_repo": "szl-holdings/lyte-lattice",
                    "source_path": "space",
                }
            ]
        }
        self.assertEqual(
            rollout.source_map_entries(value),
            [("lyte-lattice", "szl-holdings/lyte-lattice", "space")],
        )

    def test_multiple_space_path_collision_fails_closed(self) -> None:
        space_a = rollout.Space("SZLHOLDINGS/a", "a", "gradio", "RUNNING")
        space_b = rollout.Space("SZLHOLDINGS/b", "b", "gradio", "RUNNING")
        first = rollout.Plan("szl-holdings/demo", "main", [space_a], "gradio-python", "app.py", [rollout.Change("app.py", "a")])
        second = rollout.Plan("szl-holdings/demo", "main", [space_b], "gradio-python", "app.py", [rollout.Change("app.py", "b")])
        merged = rollout.merge_plans([first, second])[0]
        self.assertEqual(merged.status, "report-only")
        self.assertEqual(merged.error["code"], "CHANGE_PATH_COLLISION")


class SafetyTests(unittest.TestCase):
    def test_default_mode_is_dry_run(self) -> None:
        args = rollout.parse_args([])
        self.assertFalse(args.apply)
        self.assertEqual(args.max_repos, 100)

    def test_controller_has_no_force_or_protection_mutation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for prohibited in (
            "--force",
            "force=true",
            "branches/protection",
            "required_status_checks",
            "delete_branch_on_merge",
            "api/spaces/",
        ):
            self.assertNotIn(prohibited, source)
        self.assertIn("default_branch_writes", source)
        self.assertIn("direct_hugging_face_writes", source)
        self.assertIn("create_branch", source)
        self.assertIn("create_pr", source)

    def test_digest_is_stable(self) -> None:
        self.assertEqual(rollout.asset_digest("a", "b"), rollout.asset_digest("a", "b"))
        self.assertNotEqual(rollout.asset_digest("a", "b"), rollout.asset_digest("b", "a"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
