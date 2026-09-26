#!/usr/bin/env python3
"""Unit tests for SZL Production Auditor v5 — fail-closed profile and redaction."""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITOR_PATH = ROOT / "szl_production_auditor_v5.py"
PROFILE_PATH = ROOT / "szl_production_readiness_profile_v5.json"
TIERS_CSV_PATH = ROOT / "SZL_PRODUCTION_REPOSITORY_TIERS_V5.csv"
SNAPSHOT_PATH = ROOT / "SZL_CURRENT_PRODUCTION_SNAPSHOT_V5.json"


def load_auditor():
    spec = importlib.util.spec_from_file_location("szl_production_auditor_v5", AUDITOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load auditor")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = load_auditor()


def snapshot_repository_refs(node) -> set[str]:
    """Collect the snapshot's structured repository references.

    Covered: every ``repository`` value, every ``szl-holdings/<name>`` string
    (for example ``target`` values), and the bare repository names used as keys
    of ``captured_ruleset_evidence``. Not covered: a bare repository name in
    free text, or a Hugging Face id. This is a partial guard, not a full scan.
    """
    refs: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "repository" and isinstance(value, str):
                refs.add(value)
            if key == "captured_ruleset_evidence" and isinstance(value, dict):
                refs.update(f"szl-holdings/{name}" for name in value)
            refs |= snapshot_repository_refs(value)
    elif isinstance(node, list):
        for value in node:
            refs |= snapshot_repository_refs(value)
    elif isinstance(node, str):
        for name in re.findall(r"szl-holdings/([A-Za-z0-9._-]+)", node):
            refs.add("szl-holdings/" + name.rstrip("."))
    return refs


class ProfileTests(unittest.TestCase):
    def test_canonical_profile_validates(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(AUD.validate_profile(profile), [])
        self.assertEqual(len(profile["gates"]), 17)
        self.assertEqual(len(profile["repositories"]), 71)
        self.assertEqual(profile["non_public_repositories_omitted"], 5)
        self.assertEqual(len(profile["release_rings"]), 5)

    def test_profile_counts_match_snapshot(self) -> None:
        # Profile and snapshot come from the same capture: 71 public rows plus
        # 5 non-public repositories recorded as a count only.
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        github = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))["github"]
        self.assertEqual(len(profile["repositories"]), github["public"])
        self.assertEqual(profile["non_public_repositories_omitted"], github["private"])
        self.assertEqual(len(profile["repositories"]) + profile["non_public_repositories_omitted"],
                         github["repositories"])

    def test_missing_keys_fail_closed(self) -> None:
        errors = AUD.validate_profile({"schema": "x"})
        self.assertTrue(any("missing keys" in e for e in errors))

    def test_non_public_count_required_and_well_formed(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        missing = dict(profile)
        del missing["non_public_repositories_omitted"]
        self.assertTrue(any("non_public_repositories_omitted" in e
                            for e in AUD.validate_profile(missing)))
        for bad in (-1, "5", True, None, 2.5):
            with self.subTest(value=bad):
                errors = AUD.validate_profile(dict(profile, non_public_repositories_omitted=bad))
                self.assertIn("non_public_repositories_omitted must be a non-negative integer",
                              errors)

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

    def test_snapshot_references_public_repositories_only(self) -> None:
        # Partial guard: see snapshot_repository_refs for what it covers.
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        public = {r["repository"] for r in profile["repositories"]
                  if r.get("visibility") == "public"}
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        refs = snapshot_repository_refs(snapshot)
        self.assertTrue(refs)
        # Count only: a failure message must not echo a repository name into
        # a public CI log.
        outside = len(refs - public)
        self.assertEqual(outside, 0,
                         f"{outside} snapshot repository reference(s) are not in the "
                         "public profile")

    def test_snapshot_reference_collector_covers_each_structured_form(self) -> None:
        cases = {
            "repository field": {"open_prs": [{"repository": "szl-holdings/example-internal"}]},
            "org-qualified string": {"ruleset_findings": [
                {"target": "szl-holdings/example-internal"}]},
            "ruleset evidence key": {"github": {"captured_ruleset_evidence": {
                "example-internal": {"captured_approvals": 0}}}},
        }
        for label, snapshot in cases.items():
            with self.subTest(form=label):
                self.assertIn("szl-holdings/example-internal", snapshot_repository_refs(snapshot))


class FakeHTTP:
    """Serves the org repo list in GitHub-style pages (per_page / page)."""

    def __init__(self, org_repos: list[dict]) -> None:
        self.org_repos = org_repos
        self.repo_pages: list[int] = []

    def json(self, url: str, token: str | None = None):
        if "/orgs/szl-holdings/repos" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            per_page = int(query.get("per_page", ["30"])[0])
            page = int(query.get("page", ["1"])[0])
            self.repo_pages.append(page)
            return self.org_repos[(page - 1) * per_page:page * per_page]
        if "/search/issues" in url:
            return {"total_count": 0}
        raise RuntimeError("offline test")


class InventoryDriftTests(unittest.TestCase):
    def _drift_findings(self, extra_public: int = 0, extra_non_public: int = 0) -> list[dict]:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        public = len(profile["repositories"]) + extra_public
        non_public = profile["non_public_repositories_omitted"] + extra_non_public
        live = [{"private": False, "name": f"public-{i}"} for i in range(public)]
        live += [{"private": True, "name": f"example-internal-{i}"} for i in range(non_public)]
        report = AUD.Report(profile)
        AUD.audit_github(profile, report, FakeHTTP(live))
        return [f for f in report.findings if f["title"] == "Repository inventory drift"]

    def test_recorded_non_public_repositories_are_not_drift(self) -> None:
        self.assertEqual(self._drift_findings(), [])

    def test_unclassified_public_repository_is_drift(self) -> None:
        self.assertEqual(len(self._drift_findings(extra_public=1)), 1)

    def test_unclassified_non_public_repository_is_drift_without_names(self) -> None:
        # The profile lists public repositories only, so a new or removed
        # non-public repository is found through the recorded count. The
        # finding reports counts, never a repository name.
        for delta in (1, -1):
            with self.subTest(extra_non_public=delta):
                findings = self._drift_findings(extra_non_public=delta)
                self.assertEqual(len(findings), 1)
                self.assertNotIn("example-internal", json.dumps(findings))

    def test_inventory_reads_every_page(self) -> None:
        # 126 repos over two pages; only 60 of the 71 public ones are on page 1,
        # so a single-page read would report drift that is not there.
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        public_total = len(profile["repositories"])
        live = ([{"private": False}] * 60 + [{"private": True}] * 40
                + [{"private": False}] * (public_total - 60) + [{"private": True}] * 15)
        profile["non_public_repositories_omitted"] = 55
        http = FakeHTTP(live)
        report = AUD.Report(profile)
        AUD.audit_github(profile, report, http)
        self.assertEqual(http.repo_pages, [1, 2])
        self.assertEqual([f for f in report.findings
                          if f["title"] == "Repository inventory drift"], [])
        inventory = [e for e in report.evidence
                     if e["control"] == "GitHub repository inventory"]
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["data"].get("count"), len(live))


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
