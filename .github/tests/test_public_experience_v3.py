#!/usr/bin/env python3
"""Network-free contracts for the Public Experience v3 browser auditor."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".github" / "scripts" / "audit_public_experience_v3.py"
spec = importlib.util.spec_from_file_location("audit_public_experience_v3_test", MODULE)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class PublicExperienceV3Tests(unittest.TestCase):
    def test_viewport_matrix_covers_phone_tablet_desktop_theatre_and_zoom(self) -> None:
        by_name = {case.name: case for case in audit.VIEWPORTS}
        for name in (
            "phone-320",
            "phone-375",
            "tablet-768",
            "desktop-1024",
            "desktop-1440",
            "theatre-2560",
            "ultrawide-3440",
            "reduced-motion-375",
            "zoom-200",
            "zoom-400",
        ):
            self.assertIn(name, by_name)
        self.assertTrue(by_name["phone-320"].touch)
        self.assertEqual(by_name["reduced-motion-375"].reduced_motion, "reduce")
        self.assertEqual(by_name["zoom-400"].zoom, 4.0)

    def test_space_host_candidates_are_sdk_aware(self) -> None:
        self.assertEqual(
            audit.space_candidates("Lyte-Lattice", "static"),
            (
                "https://szlholdings-lyte-lattice.static.hf.space/",
                "https://szlholdings-lyte-lattice.hf.space/",
            ),
        )
        self.assertEqual(
            audit.space_candidates("a11oy", "docker"),
            ("https://szlholdings-a11oy.hf.space/",),
        )

    def test_canonical_origins_keep_distinct_roles(self) -> None:
        targets = audit.canonical_targets()
        self.assertEqual([target.name for target in targets], ["a-11-oy.com", "a11oy.net"])
        self.assertEqual(targets[0].role, "static-product-front-door")
        self.assertEqual(targets[1].role, "independent-proof-origin")
        self.assertFalse(any(target.require_v3 for target in targets))

    def test_findings_fail_closed_on_operational_and_responsive_defects(self) -> None:
        metrics = {
            "http_status": 503,
            "title": "",
            "text_characters": 0,
            "overflow_px": 80,
            "v3_marker": False,
            "small_target_count": 3,
            "blocking_overlays": [{"coverage": 1.0}],
            "main_landmark": False,
            "console_errors": ["boom"],
        }
        failures, warnings = audit.classify_findings(
            metrics,
            touch=True,
            require_v3=True,
            page_errors=["uncaught"],
        )
        rendered = "\n".join(failures)
        for fragment in (
            "HTTP 503",
            "title is empty",
            "meaningful text",
            "horizontal overflow",
            "v3 marker",
            "44×44",
            "fixed overlay",
            "uncaught page error",
        ):
            self.assertIn(fragment, rendered)
        self.assertTrue(any("main landmark" in value for value in warnings))
        self.assertTrue(any("console error" in value for value in warnings))

    def test_passing_metrics_remain_green(self) -> None:
        metrics = {
            "http_status": 200,
            "title": "A11oy",
            "text_characters": 300,
            "overflow_px": 0,
            "v3_marker": True,
            "small_target_count": 0,
            "blocking_overlays": [],
            "main_landmark": True,
            "console_errors": [],
        }
        failures, warnings = audit.classify_findings(
            metrics,
            touch=True,
            require_v3=True,
            page_errors=[],
        )
        self.assertEqual(failures, [])
        self.assertEqual(warnings, [])

    def test_report_is_secret_free_and_counts_target_failures_once(self) -> None:
        target = audit.Target("SZLHOLDINGS/a11oy", "hugging-face-space", ("https://example.invalid",), True)
        first = audit.CaseResult("SZLHOLDINGS/a11oy", target.role, "phone", target.candidates[0], failures=["x"])
        second = audit.CaseResult("SZLHOLDINGS/a11oy", target.role, "desktop", target.candidates[0], failures=["y"])
        report = audit.build_report([target], [first, second])
        self.assertFalse(report["token_value_recorded"])
        self.assertEqual(report["summary"]["failed_cases"], 2)
        self.assertEqual(report["summary"]["failing_targets"], 1)
        self.assertEqual(report["summary"]["failing_target_names"], ["SZLHOLDINGS/a11oy"])

    def test_source_is_get_only_and_has_no_mutation_endpoint(self) -> None:
        text = MODULE.read_text(encoding="utf-8")
        for fragment in (
            'method="POST"',
            "/restart",
            "/hardware",
            "upload_file",
            "create_commit",
            "delete_repo",
            "change_discussion_status",
        ):
            self.assertNotIn(fragment, text)
        self.assertIn("page.goto", text)
        self.assertIn("screenshot", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
