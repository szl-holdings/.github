#!/usr/bin/env python3
"""Self-test for the HF module-drift guard's content-lineage cross-check.

The guard names the diverged side ("ahead") by last-commit DATE, but a timestamp
lies about lineage: a stale hand-edit can be NEWER by date yet DIVERGE from the
canonical shared module that the other side already matches (killinchu's
szl_be_hardening.py showed "ahead: huggingface" while GitHub already held the
canonical byte-identical to a11oy's). A future agent who trusted the date label
and backported HF->GitHub would have silently regressed the canonical and broken
the byte-identical-across-organs invariant.

This locks the lineage contract so a refactor can't quietly drop it:
  * the date-ahead side conflicting with the sibling canonical -> LINEAGE CONFLICT,
  * date-ahead AGREEING with canonical -> no false alarm,
  * no sibling canonical -> fall back to date-only (unchanged behaviour),
  * siblings disagreeing among themselves -> conflict (no single source of truth),
  * neither side matching canonical -> conflict (never pick a direction by date),
and an end-to-end compare()/fmt() check (network fully stubbed) that the
conflict actually surfaces in the run output. Runs with NO network.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_module_drift_check.py")

_spec = importlib.util.spec_from_file_location("hf_module_drift_check", _MODULE_PATH)
assert _spec and _spec.loader
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


class TestClassifyLineage(unittest.TestCase):
    def test_trap_date_says_hf_but_github_is_canonical(self):
        # The szl_be_hardening.py trap: HF is newer by DATE, but GitHub holds the
        # canonical shared module and the HF copy is a stale hand-edit.
        info = drift.classify_lineage(
            gh_sha="canon", hf_oid="stale", canonical_shas=["canon"],
            date_ahead="huggingface")
        self.assertEqual(info["canonical_state"], "resolved")
        self.assertTrue(info["github_matches_canonical"])
        self.assertFalse(info["hf_matches_canonical"])
        self.assertEqual(info["content_ahead"], "github")
        self.assertTrue(info["lineage_conflict"])

    def test_date_and_content_agree_no_conflict(self):
        # HF is newer by date AND holds the canonical content -> genuinely ahead.
        info = drift.classify_lineage(
            gh_sha="stale", hf_oid="canon", canonical_shas=["canon"],
            date_ahead="huggingface")
        self.assertEqual(info["content_ahead"], "huggingface")
        self.assertFalse(info["lineage_conflict"])

    def test_github_date_and_content_agree_no_conflict(self):
        info = drift.classify_lineage(
            gh_sha="canon", hf_oid="stale", canonical_shas=["canon"],
            date_ahead="github")
        self.assertEqual(info["content_ahead"], "github")
        self.assertFalse(info["lineage_conflict"])

    def test_no_sibling_canonical_is_date_only(self):
        info = drift.classify_lineage(
            gh_sha="a", hf_oid="b", canonical_shas=[], date_ahead="huggingface")
        self.assertEqual(info["canonical_state"], "none")
        self.assertIsNone(info["content_ahead"])
        self.assertFalse(info["lineage_conflict"])

    def test_siblings_disagree_is_conflict(self):
        info = drift.classify_lineage(
            gh_sha="a", hf_oid="b", canonical_shas=["x", "y"],
            date_ahead="github")
        self.assertEqual(info["canonical_state"], "sibling-divergent")
        self.assertTrue(info["lineage_conflict"])

    def test_neither_side_matches_canonical_is_conflict(self):
        info = drift.classify_lineage(
            gh_sha="a", hf_oid="b", canonical_shas=["canon"],
            date_ahead="github")
        self.assertEqual(info["content_ahead"], "neither")
        self.assertTrue(info["lineage_conflict"])

    def test_date_unknown_with_canonical_still_reads_content(self):
        # No reliable date ("unknown"/"?"): we can't conflict against a date we
        # don't have, but content_ahead must still be reported for the human.
        info = drift.classify_lineage(
            gh_sha="canon", hf_oid="stale", canonical_shas=["canon"],
            date_ahead="unknown")
        self.assertEqual(info["content_ahead"], "github")
        self.assertFalse(info["lineage_conflict"])

    def test_date_suffix_question_mark_is_normalised(self):
        # "huggingface?" (one-sided date) vs github-canonical is still a conflict.
        info = drift.classify_lineage(
            gh_sha="canon", hf_oid="stale", canonical_shas=["canon"],
            date_ahead="huggingface?")
        self.assertTrue(info["lineage_conflict"])


class TestComparePropagatesLineage(unittest.TestCase):
    """End-to-end: compare() must run the cross-check against a sibling and the
    conflict must reach the human-readable output. All network is stubbed."""

    def setUp(self):
        self._saved = {k: getattr(drift, k) for k in (
            "github_tree_remote", "github_tree_local", "hf_tree",
            "github_file_date", "hf_dir_dates", "parse_copy_sources", "_http")}

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(drift, k, v)

    def test_compare_flags_stale_hf_handedit(self):
        path = "szl_be_hardening.py"
        # This repo (killinchu): GitHub holds canonical, HF is a stale hand-edit.
        drift.parse_copy_sources = lambda _txt: [path]
        drift.github_tree_remote = lambda repo, ref="main": {
            "szl-holdings/killinchu": {path: "canon"},
            "szl-holdings/a11oy": {path: "canon"},  # sibling canonical
        }[repo]
        drift.hf_tree = lambda repo, ref="main": {path: {"oid": "stale", "lfs_oid": None, "size": 9}}
        # HF newer by DATE -> the misleading "ahead: huggingface".
        drift.github_file_date = lambda repo, p, ref="main": "2026-06-01T00:00:00Z"
        drift.hf_dir_dates = lambda repo, d, ref="main": {path: "2026-06-09T00:00:00Z"}

        args = argparse.Namespace(
            repo_root=".", github_repo="szl-holdings/killinchu",
            hf_repo="SZLHOLDINGS/killinchu", ref="main", allow=None,
            github_remote=True, report_out="", warn_only=False,
            siblings=["szl-holdings/a11oy"],
        )
        # github_remote path fetches a Dockerfile via _http; stub that too.
        drift._http = lambda *a, **k: (200, b"COPY szl_be_hardening.py /app/", None)
        report, errors, warns = drift.compare(args, allow={})

        self.assertEqual(len(errors), 1)
        e = errors[0]
        self.assertEqual(e["kind"], "drift")
        self.assertEqual(e["ahead"], "huggingface")            # date label unchanged
        self.assertEqual(e["content_ahead"], "github")          # content lineage
        self.assertTrue(e["lineage_conflict"])
        self.assertEqual(e.get("canonical_repos"), ["szl-holdings/a11oy"])

        rendered = drift.fmt(e)
        self.assertIn("LINEAGE CONFLICT", rendered)
        self.assertIn("md5-compare all 4 surfaces", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
