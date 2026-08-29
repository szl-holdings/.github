#!/usr/bin/env python3
"""Unit tests for SZL Production Auditor v5 — fail-closed profile and redaction."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITOR_PATH = ROOT / "szl_production_auditor_v5.py"
PROFILE_PATH = ROOT / "szl_production_readiness_profile_v5.json"


def load_auditor():
    spec = importlib.util.spec_from_file_location("szl_production_auditor_v5", AUDITOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load auditor")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = load_auditor()


class ProfileTests(unittest.TestCase):
    def test_canonical_profile_validates(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(AUD.validate_profile(profile), [])
        self.assertEqual(len(profile["gates"]), 17)
        self.assertEqual(len(profile["repositories"]), 76)
        self.assertEqual(len(profile["release_rings"]), 5)

    def test_missing_keys_fail_closed(self) -> None:
        errors = AUD.validate_profile({"schema": "x"})
        self.assertTrue(any("missing keys" in e for e in errors))

    def test_duplicate_gate_ids_fail(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile["gates"] = profile["gates"] + [profile["gates"][0]]
        errors = AUD.validate_profile(profile)
        self.assertTrue(any("duplicate gate" in e for e in errors))

    def test_http_web_target_rejected(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile["web_targets"] = [{"base_url": "http://example.com", "id": "x"}]
        errors = AUD.validate_profile(profile)
        self.assertTrue(any("non-HTTPS" in e for e in errors))


class RedactionTests(unittest.TestCase):
    def test_redact_tokens(self) -> None:
        text = "token ghp_abcdefghijklmnopqrstuvwxyz123456 and hf_abcdefghijklmnopqrstuvwxyz"
        out = AUD.redact(text)
        self.assertNotIn("ghp_", out)
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz", out)
        self.assertIn("[REDACTED]", out)

    def test_heading_skip(self) -> None:
        self.assertTrue(AUD.heading_skip([1, 3]))
        self.assertFalse(AUD.heading_skip([1, 2, 3]))


class ReportTests(unittest.TestCase):
    def test_missing_evidence_is_unknown_not_pass(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        report = AUD.Report(profile)
        results = {g["id"]: g["status"] for g in report.gate_results()}
        self.assertTrue(all(status == "UNKNOWN" for status in results.values()))
        self.assertNotIn("PASS", results.values())

    def test_blocking_fail_wins(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        report = AUD.Report(profile)
        report.finding("G00", "P0", "FAIL", "org", "ruleset", "zero approvals", "fix")
        report.proof("G00", "x", "org", "PASS")
        results = {g["id"]: g["status"] for g in report.gate_results()}
        self.assertEqual(results["G00"], "FAIL")

    def test_canonical_json_stable(self) -> None:
        a = AUD.canonical_json({"b": 1, "a": 2})
        b = AUD.canonical_json({"a": 2, "b": 1})
        self.assertEqual(a, b)

    def test_validate_only_cli(self) -> None:
        code = AUD.main(["--profile", str(PROFILE_PATH), "--validate-only"])
        self.assertEqual(code, 0)

    def test_invalid_profile_cli_exit_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            code = AUD.main(["--profile", str(bad), "--validate-only"])
            self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
