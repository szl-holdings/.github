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
import json
import os
import shutil
import tempfile
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


class TestIndependentRefs(unittest.TestCase):
    """A GitHub PR SHA and an HF deployment revision are different namespaces."""

    def setUp(self):
        self._saved = {k: getattr(drift, k) for k in (
            "github_tree_remote", "hf_tree", "github_file_date",
            "hf_dir_dates", "parse_copy_sources", "gh_get")}

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(drift, key, value)

    def test_common_ref_remains_backwards_compatible(self):
        args = argparse.Namespace(ref="release")
        self.assertEqual(drift.effective_refs(args), ("release", "release"))

    def test_compare_routes_each_side_to_its_own_ref(self):
        path = "module.py"
        calls = []
        drift.parse_copy_sources = lambda _text: [path]
        drift.gh_get = lambda *a, **k: (200, b"COPY module.py /app/", None)

        def github_tree(repo, ref="main"):
            calls.append(("github-tree", ref))
            return {path: "same"}

        def hf_tree(repo, ref="main"):
            calls.append(("hf-tree", ref))
            return {path: {"oid": "same", "lfs_oid": None, "size": 1}}

        drift.github_tree_remote = github_tree
        drift.hf_tree = hf_tree
        drift.github_file_date = lambda repo, p, ref="main": None
        drift.hf_dir_dates = lambda repo, d, ref="main": {}
        args = argparse.Namespace(
            repo_root=".", github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy", ref="main",
            github_ref="github-pr-head", hf_ref="hf-live-revision",
            allow=None, github_remote=True, report_out="", warn_only=False,
            siblings=[],
        )

        report, errors, warns = drift.compare(args, allow={})

        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertIn(("github-tree", "github-pr-head"), calls)
        self.assertIn(("hf-tree", "hf-live-revision"), calls)
        self.assertEqual(report["github_ref"], "github-pr-head")
        self.assertEqual(report["hf_ref"], "hf-live-revision")

    def test_primary_pr_sha_is_not_reused_for_sibling_repositories(self):
        path = "module.py"
        calls = []
        drift.parse_copy_sources = lambda _text: [path]
        drift.gh_get = lambda *a, **k: (200, b"COPY module.py /app/", None)

        def github_tree(repo, ref="main"):
            calls.append((repo, ref))
            if repo == "szl-holdings/a11oy":
                return {path: "canonical"}
            return {path: "canonical"}

        drift.github_tree_remote = github_tree
        drift.hf_tree = lambda repo, ref="main": {
            path: {"oid": "stale", "lfs_oid": None, "size": 1}}
        drift.github_file_date = lambda repo, p, ref="main": "2026-07-12T00:00:00Z"
        drift.hf_dir_dates = lambda repo, d, ref="main": {
            path: "2026-07-11T00:00:00Z"}
        args = argparse.Namespace(
            repo_root=".", github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy", ref="main",
            github_ref="github-pr-head", hf_ref="hf-live-revision",
            allow=None, github_remote=True, report_out="", warn_only=False,
            siblings=["szl-holdings/killinchu"],
        )

        _report, errors, _warns = drift.compare(args, allow={})

        self.assertEqual(len(errors), 1)
        self.assertIn(("szl-holdings/a11oy", "github-pr-head"), calls)
        self.assertIn(("szl-holdings/killinchu", "main"), calls)
        self.assertNotIn(("szl-holdings/killinchu", "github-pr-head"), calls)


class TestTransientHTTPInconclusive(unittest.TestCase):
    """A persistent HF 429/5xx must go HONEST INCONCLUSIVE (report written,
    exit 0), never crash and never false-green. All network stubbed."""

    def setUp(self):
        self._saved = {k: getattr(drift, k) for k in (
            "github_tree_remote", "github_tree_local", "hf_tree",
            "github_file_date", "hf_dir_dates", "parse_copy_sources", "_http",
            "gh_get")}
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(drift, k, v)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _args(self):
        return argparse.Namespace(
            repo_root=".", github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy", ref="main", allow=None,
            github_remote=True, report_out=os.path.join(self._tmp, "r.json"),
            warn_only=False, registry="", siblings=[])

    def test_http_raises_transient_on_persistent_429(self):
        # _http must raise the distinct TransientHTTPError (not plain RuntimeError)
        # when 429 persists past the retry budget, so callers can go inconclusive.
        import urllib.error
        drift.time.sleep = lambda *_a, **_k: None  # no real backoff waits

        def always_429(url, *a, **k):
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        drift.urllib.request.urlopen = always_429
        with self.assertRaises(drift.TransientHTTPError) as ctx:
            drift._http("https://huggingface.co/api/spaces/x/tree/main", retries=2)
        self.assertEqual(ctx.exception.code, 429)

    def test_compare_transient_becomes_inconclusive_exit0(self):
        args = self._args()
        drift.parse_copy_sources = lambda _txt: ["mod.py"]
        drift.gh_get = lambda *a, **k: (200, b"COPY mod.py /app/", None)

        def hf_429(*a, **k):
            raise drift.TransientHTTPError(
                "https://huggingface.co/api/spaces/SZLHOLDINGS/a11oy/tree/main",
                429, 8)
        drift.hf_tree = hf_429
        drift.github_tree_remote = lambda repo, ref="main": {"mod.py": "abc"}

        # Mirror main()'s dispatch: compare() raises -> _emit_inconclusive.
        try:
            drift.compare(args)
            self.fail("expected TransientHTTPError")
        except drift.TransientHTTPError as e:
            rc = drift._emit_inconclusive(args, e)

        self.assertEqual(rc, 0)  # NEUTRAL exit -- gate not marked red
        with open(args.report_out) as fh:
            report = json.load(fh)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(report["reason"], "hf_api_429")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["findings"], [])

    def test_ok_report_carries_status_ok(self):
        args = self._args()
        drift.parse_copy_sources = lambda _txt: ["mod.py"]
        drift.gh_get = lambda *a, **k: (200, b"COPY mod.py /app/", None)
        drift.github_tree_remote = lambda repo, ref="main": {"mod.py": "same"}
        drift.hf_tree = lambda repo, ref="main": {
            "mod.py": {"oid": "same", "lfs_oid": None, "size": 1}}
        report, errors, warns = drift.compare(args)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
