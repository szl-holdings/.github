#!/usr/bin/env python3
"""Network-free contracts for the Hugging Face Adaptive Theatre v3 rollout."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "rollout_hf_adaptive_theatre_v3.py"
CSS = ROOT / ".github" / "assets" / "szl-space-adaptive-v3.css"
JS = ROOT / ".github" / "assets" / "szl-space-adaptive-v3.js"
spec = importlib.util.spec_from_file_location("rollout", SCRIPT)
assert spec and spec.loader
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


class HfAdaptiveTheatreV3Contract(unittest.TestCase):
    def test_assets_cover_mobile_through_theatre(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertIn("--szl-space-control: 44px", css)
        self.assertIn("--szl-space-coarse-control: 48px", css)
        self.assertIn("max-width: 640px", css)
        self.assertIn("min-width: 1680px", css)
        self.assertIn('data-szl-space-display-mode="theatre"', css)
        self.assertIn("orientation: landscape", css)
        for mode in ("mobile", "tablet", "desktop", "theatre"):
            self.assertIn(f'"{mode}"', js)

    def test_assets_are_local_accessible_and_truth_neutral(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        for token in ("safe-area-inset-bottom", "overflow-x: auto", ":focus-visible", "prefers-reduced-motion", "forced-colors", "@media print"):
            self.assertIn(token, css)
        for token in ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage", "document.cookie", "analytics"):
            self.assertNotIn(token, js)
        self.assertNotIn("MEASURED", js)
        self.assertNotIn("DSSE-LIVE", js)
        self.assertEqual(css.count("{"), css.count("}"))

    def test_source_mapping_is_deterministic_and_fold_aware(self) -> None:
        repos = {
            "killinchu": {"name": "killinchu"},
            "governed-receipt-spec": {"name": "governed-receipt-spec"},
            "custom": {"name": "custom"},
        }
        self.assertEqual(rollout.source_repo({"slug": "killinchu", "card": {}}, repos), ("killinchu", "override"))
        self.assertEqual(rollout.source_repo({"slug": "anatomy", "card": {}}, repos), (None, "intentional-fold"))
        self.assertEqual(
            rollout.source_repo({"slug": "elsewhere", "card": {"source_repo": "https://github.com/szl-holdings/custom"}}, repos),
            ("custom", "card"),
        )

    def test_adapter_requires_existing_reviewed_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(rollout.RolloutError, "NO_REVIEWED_HOLOGRAPHIC_HOST"):
                rollout.install_assets(root, CSS, JS)

    def test_adapter_is_idempotent_and_keeps_identity_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "szl-holo-v2.css").write_text("body { color: inherit; }\n", encoding="utf-8")
            (root / "szl-holo-v2.js").write_text("window.identity = 'space-owned';\n", encoding="utf-8")
            with mock.patch.object(rollout, "run", return_value=mock.Mock(stdout="", returncode=0)):
                first = rollout.install_assets(root, CSS, JS)
                second = rollout.install_assets(root, CSS, JS)
            host_css = (root / "szl-holo-v2.css").read_text(encoding="utf-8")
            host_js = (root / "szl-holo-v2.js").read_text(encoding="utf-8")
            self.assertEqual(host_css.count(rollout.MARKER), 1)
            self.assertEqual(host_js.count(rollout.JS_MARKER), 1)
            self.assertIn("space-owned", host_js)
            self.assertEqual(first["css_hosts"], second["css_hosts"])

    def test_missing_cross_repo_token_is_explicit_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            argv = [str(SCRIPT), "--report", str(report), "--css", str(CSS), "--js", str(JS)]
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch("sys.argv", argv):
                self.assertEqual(rollout.main(), 2)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "UNAVAILABLE")
            self.assertFalse(payload["token_recorded"])
            self.assertNotIn("Bearer", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
