#!/usr/bin/env python3
"""Unit tests for SZL Production Auditor v5 — fail-closed profile and redaction."""
from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITOR_PATH = ROOT / "szl_production_auditor_v5.py"
PROFILE_PATH = ROOT / "szl_production_readiness_profile_v5.json"
TIERS_CSV_PATH = ROOT / "SZL_PRODUCTION_REPOSITORY_TIERS_V5.csv"


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
        self.assertEqual(len(profile["repositories"]), 71)
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

    def test_non_public_repository_rejected_without_echoing_name(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        extra = dict(profile["repositories"][0], repository="szl-holdings/example-internal",
                     visibility="private")
        profile["repositories"] = profile["repositories"] + [extra]
        errors = AUD.validate_profile(profile)
        self.assertTrue(any("is not public" in e for e in errors))
        self.assertFalse(any("example-internal" in e for e in errors))

    def test_tiers_csv_is_public_only_and_matches_profile(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        with TIERS_CSV_PATH.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({r["visibility"] for r in rows}, {"public"})
        self.assertEqual([r["repository"] for r in rows],
                         [r["repository"] for r in profile["repositories"]])


class FakeHTTP:
    def __init__(self, org_repos: list[dict]) -> None:
        self.org_repos = org_repos

    def json(self, url: str, token: str | None = None):
        if "/orgs/szl-holdings/repos" in url:
            return self.org_repos
        if "/search/issues" in url:
            return {"total_count": 0}
        raise RuntimeError("offline test")


class InventoryDriftTests(unittest.TestCase):
    def _drift_findings(self, extra_public: int) -> list[dict]:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        live = [{"private": False} for _ in range(len(profile["repositories"]) + extra_public)]
        live += [{"private": True} for _ in range(3)]
        report = AUD.Report(profile)
        AUD.audit_github(profile, report, FakeHTTP(live))
        return [f for f in report.findings if f["title"] == "Repository inventory drift"]

    def test_private_repositories_do_not_count_as_drift(self) -> None:
        self.assertEqual(self._drift_findings(extra_public=0), [])

    def test_unclassified_public_repository_is_drift(self) -> None:
        self.assertEqual(len(self._drift_findings(extra_public=1)), 1)


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
