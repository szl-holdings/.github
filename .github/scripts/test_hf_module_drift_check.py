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
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
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


class TestTrustedDeploymentLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "hf-deployment-lock.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, **overrides):
        payload = {
            "schema": 1,
            "github_repo": "szl-holdings/a11oy",
            "github_source_sha": "1" * 40,
            "hf_repo": "SZLHOLDINGS/a11oy",
            "hf_commit_sha": "2" * 40,
        }
        payload.update(overrides)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def test_loads_exact_immutable_pair(self):
        self._write()
        lock = drift.load_deployment_lock(self.path)
        self.assertEqual(lock["github_source_sha"], "1" * 40)
        self.assertEqual(lock["hf_commit_sha"], "2" * 40)

    def test_rejects_mutable_or_short_revision(self):
        self._write(github_source_sha="main")
        with self.assertRaisesRegex(ValueError, "40-character"):
            drift.load_deployment_lock(self.path)


class TestCandidateManagedDelta(unittest.TestCase):
    BASE = "a" * 40
    HEAD = "b" * 40

    def setUp(self):
        self._saved = {
            "github_tree_remote": drift.github_tree_remote,
            "fetch_github_file": drift.fetch_github_file,
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(drift, key, value)

    def test_reports_managed_changes_without_treating_them_as_live_drift(self):
        trees = {
            self.BASE: {
                "Dockerfile": "df-old",
                "mod.py": "mod-old",
                "oldonly.py": "oldonly",
            },
            self.HEAD: {
                "Dockerfile": "df-new",
                "mod.py": "mod-new",
                "new.py": "new",
            },
        }
        dockerfiles = {
            self.BASE: (
                b"COPY mod.py /app/\n"
                b"COPY oldonly.py /app/\n"
                b"COPY missing.txt /app/\n"),
            self.HEAD: (
                b"COPY mod.py /app/\n"
                b"COPY new.py /app/\n"
                b"COPY missing.txt /app/\n"),
        }
        drift.github_tree_remote = lambda _repo, ref="main": trees[ref]
        drift.fetch_github_file = lambda _repo, ref, _path: dockerfiles[ref]

        report = drift.candidate_managed_delta(
            "szl-holdings/a11oy", self.BASE, self.HEAD)

        self.assertEqual(report["status"], "changes")
        self.assertEqual(report["new_unresolved_sources"], [])
        self.assertEqual(
            {(entry["path"], entry["kind"]) for entry in report["deltas"]},
            {
                ("Dockerfile", "modified"),
                ("mod.py", "modified"),
                ("new.py", "managed-added"),
                ("oldonly.py", "managed-removed"),
            },
        )

    def test_new_unresolved_copy_source_is_invalid(self):
        tree = {"Dockerfile": "df", "mod.py": "mod"}
        drift.github_tree_remote = lambda _repo, ref="main": tree
        drift.fetch_github_file = lambda _repo, ref, _path: (
            b"COPY mod.py /app/\n" if ref == self.BASE else
            b"COPY mod.py missing-new.py /app/\n")

        report = drift.candidate_managed_delta(
            "szl-holdings/a11oy", self.BASE, self.HEAD)

        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["new_unresolved_sources"], ["missing-new.py"])


class TestHFMetadataConsistency(unittest.TestCase):
    STALE = "a" * 40
    CURRENT = "b" * 40

    def setUp(self):
        self._http = drift._http
        self.calls = []

    def tearDown(self):
        drift._http = self._http

    @staticmethod
    def _payload(head, runtime=None, stage="RUNNING"):
        return json.dumps({
            "sha": head,
            "runtime": {"sha": runtime or head, "stage": stage},
        }).encode("utf-8")

    def _install_responses(self, responses):
        queue = list(responses)

        def fake_http(url, headers=None, want_headers=False, **_kwargs):
            self.calls.append({
                "url": url,
                "headers": dict(headers or {}),
                "want_headers": want_headers,
            })
            response = queue.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        drift._http = fake_http

    def test_stale_then_current_is_cdn_inconsistent_not_selected(self):
        self._install_responses([
            (200, self._payload(self.STALE), {"X-Cache": "HIT"}),
            (200, self._payload(self.CURRENT), {"X-Cache": "MISS"}),
        ])

        state = drift.hf_space_state("SZLHOLDINGS/a11oy")

        self.assertEqual(state["observation_status"], "cdn-inconsistent")
        self.assertIsNone(state["head_sha"])
        self.assertIsNone(state["runtime_sha"])
        self.assertEqual(len(state["observations"]), 2)
        self.assertNotEqual(self.calls[0]["url"], self.calls[1]["url"])
        for call in self.calls:
            self.assertTrue(call["want_headers"])
            self.assertEqual(
                call["headers"]["Cache-Control"],
                "no-cache, no-store, max-age=0",
            )
            self.assertEqual(call["headers"]["Pragma"], "no-cache")

    def test_persistent_stale_is_stable_observation_not_freshness_claim(self):
        response = (200, self._payload(self.STALE), {"Age": "180"})
        self._install_responses([response, response])

        state = drift.hf_space_state("SZLHOLDINGS/a11oy")

        self.assertEqual(state["observation_status"], "stable")
        self.assertEqual(state["head_sha"], self.STALE)
        self.assertEqual(state["runtime_sha"], self.STALE)
        self.assertEqual(state["observations"][0]["response_cache"]["age"], "180")

    def test_stable_split_head_and_runtime_preserves_both_exact_values(self):
        response = (
            200,
            self._payload(self.CURRENT, runtime=self.STALE),
            {"CF-Cache-Status": "DYNAMIC"},
        )
        self._install_responses([response, response])

        state = drift.hf_space_state("SZLHOLDINGS/a11oy")

        self.assertEqual(state["observation_status"], "stable")
        self.assertEqual(state["head_sha"], self.CURRENT)
        self.assertEqual(state["runtime_sha"], self.STALE)

    def test_transient_http_returns_unavailable_with_partial_evidence(self):
        self._install_responses([
            (200, self._payload(self.CURRENT), {"X-Cache": "MISS"}),
            drift.TransientHTTPError("https://huggingface.invalid", 503, 8),
        ])

        state = drift.hf_space_state("SZLHOLDINGS/a11oy")

        self.assertEqual(state["observation_status"], "unavailable")
        self.assertIsNone(state["head_sha"])
        self.assertEqual(state["observation_count"], 2)
        self.assertEqual(state["observations"][0]["status"], "observed")
        self.assertEqual(state["observations"][1]["status"], "transient-http")
        self.assertEqual(state["observations"][1]["http_status"], 503)


class TestTrustedBaselineCompare(unittest.TestCase):
    LOCKED_GH = "1" * 40
    TRUSTED_BASE = "3" * 40
    LOCKED_HF = "2" * 40

    def setUp(self):
        self._saved = {key: getattr(drift, key) for key in (
            "github_ref_is_ancestor", "hf_space_state", "compare",
            "candidate_managed_delta",
        )}
        self.tmp = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.tmp, "lock.json")
        with open(self.lock_path, "w", encoding="utf-8") as fh:
            json.dump({
                "schema": 1,
                "github_repo": "szl-holdings/a11oy",
                "github_source_sha": self.LOCKED_GH,
                "hf_repo": "SZLHOLDINGS/a11oy",
                "hf_commit_sha": self.LOCKED_HF,
            }, fh)

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(drift, key, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _args(self, candidate_ref=""):
        return argparse.Namespace(
            deployment_lock=self.lock_path,
            trusted_base_ref=self.TRUSTED_BASE,
            candidate_ref=candidate_ref,
            github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy",
            dockerfile_path="Dockerfile",
            repo_root=".", ref="main", github_ref="", hf_ref="",
            github_remote=False, allow=None, siblings=[],
        )

    def _stub_clean_pair(self, live_state=None):
        calls = {}
        drift.github_ref_is_ancestor = lambda *_a, **_k: (True, "ahead")
        if live_state is None:
            live_state = {
                "head_sha": self.LOCKED_HF,
                "runtime_sha": self.LOCKED_HF,
                "runtime_stage": "RUNNING",
            }
        live_state = dict(live_state)
        live_state.setdefault("observation_status", "stable")
        live_state.setdefault("observation_count", 2)
        live_state.setdefault("required_observation_count", 2)
        live_state.setdefault("observations", [
            {
                "ordinal": 1,
                "status": "observed",
                "head_sha": live_state.get("head_sha"),
                "runtime_sha": live_state.get("runtime_sha"),
                "runtime_stage": live_state.get("runtime_stage"),
            },
            {
                "ordinal": 2,
                "status": "observed",
                "head_sha": live_state.get("head_sha"),
                "runtime_sha": live_state.get("runtime_sha"),
                "runtime_stage": live_state.get("runtime_stage"),
            },
        ])
        drift.hf_space_state = lambda *_a, **_k: live_state

        def compare(args, allow=None, include_dockerfile=False):
            calls["refs"] = (args.github_ref, args.hf_ref)
            calls["remote"] = args.github_remote
            calls["allow"] = allow
            calls["include_dockerfile"] = include_dockerfile
            return ({"findings": []}, [], [])

        drift.compare = compare
        return calls

    def test_compares_locked_pair_without_allowlist_or_candidate_live_equality(self):
        calls = self._stub_clean_pair()
        report, errors, warns, candidate = drift.trusted_baseline_compare(
            self._args())

        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertIsNone(candidate)
        self.assertEqual(calls["refs"], (self.LOCKED_GH, self.LOCKED_HF))
        self.assertTrue(calls["remote"])
        self.assertEqual(calls["allow"], {})
        self.assertTrue(calls["include_dockerfile"])
        self.assertFalse(report["allowlist_used"])

    def test_live_hf_revision_mismatch_fails_closed(self):
        self._stub_clean_pair({
            "head_sha": "9" * 40,
            "runtime_sha": self.LOCKED_HF,
            "runtime_stage": "RUNNING",
        })
        _report, errors, _warns, _candidate = drift.trusted_baseline_compare(
            self._args())
        self.assertIn("live-hf-head-mismatch", {e["kind"] for e in errors})

    def test_persistent_stale_head_and_runtime_fail_exact_lock(self):
        self._stub_clean_pair({
            "head_sha": "9" * 40,
            "runtime_sha": "9" * 40,
            "runtime_stage": "RUNNING",
        })
        _report, errors, _warns, _candidate = drift.trusted_baseline_compare(
            self._args())
        kinds = {error["kind"] for error in errors}
        self.assertIn("live-hf-head-mismatch", kinds)
        self.assertIn("live-hf-runtime-mismatch", kinds)

    def test_split_head_runtime_has_distinct_fail_closed_error(self):
        self._stub_clean_pair({
            "head_sha": self.LOCKED_HF,
            "runtime_sha": "9" * 40,
            "runtime_stage": "RUNNING",
        })
        _report, errors, _warns, _candidate = drift.trusted_baseline_compare(
            self._args())
        kinds = {error["kind"] for error in errors}
        self.assertIn("live-hf-head-runtime-split", kinds)
        self.assertIn("live-hf-runtime-mismatch", kinds)

    def test_cdn_inconsistency_never_greens_mixed_observations(self):
        self._stub_clean_pair({
            "head_sha": None,
            "runtime_sha": None,
            "runtime_stage": None,
            "observation_status": "cdn-inconsistent",
            "observation_count": 2,
            "observations": [
                {"ordinal": 1, "head_sha": "9" * 40},
                {"ordinal": 2, "head_sha": self.LOCKED_HF},
            ],
        })
        _report, errors, _warns, _candidate = drift.trusted_baseline_compare(
            self._args())
        kinds = {error["kind"] for error in errors}
        self.assertEqual(kinds, {"live-hf-cdn-inconsistent"})

    def test_transient_metadata_failure_is_explicit_error(self):
        self._stub_clean_pair({
            "head_sha": None,
            "runtime_sha": None,
            "runtime_stage": None,
            "observation_status": "unavailable",
            "observation_count": 2,
            "observations": [
                {"ordinal": 1, "status": "observed"},
                {"ordinal": 2, "status": "transient-http", "http_status": 503},
            ],
        })
        _report, errors, _warns, _candidate = drift.trusted_baseline_compare(
            self._args())
        self.assertEqual(
            {error["kind"] for error in errors},
            {"live-hf-metadata-unavailable"},
        )

    def test_new_candidate_unresolved_source_fails_without_deployment(self):
        self._stub_clean_pair()
        drift.candidate_managed_delta = lambda *_a, **_k: {
            "status": "invalid",
            "new_unresolved_sources": ["missing.py"],
        }
        _report, errors, _warns, candidate = drift.trusted_baseline_compare(
            self._args(candidate_ref="4" * 40))
        self.assertEqual(candidate["status"], "invalid")
        self.assertIn(
            "candidate-unresolved-copy-source", {e["kind"] for e in errors})

    def test_baseline_rejected_copy_source_is_not_ok(self):
        self._stub_clean_pair()
        drift.candidate_managed_delta = lambda *_a, **_k: {
            "status": "invalid",
            "new_unresolved_sources": [],
            "baseline_rejected_copy_sources": ["../secret"],
            "candidate_rejected_copy_sources": [],
        }
        report, errors, _warns, candidate = drift.trusted_baseline_compare(
            self._args(candidate_ref="4" * 40))
        self.assertEqual(candidate["status"], "invalid")
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(
            [(entry["kind"], entry["path"]) for entry in errors],
            [("rejected-copy-source", "../secret")],
        )


class TestReusableWorkflowTrustedBaselineContract(unittest.TestCase):
    def test_workflow_reads_lock_from_base_and_never_passes_candidate_as_hf_ref(self):
        workflow_path = os.path.join(
            _HERE, "..", "workflows", "reusable-hf-module-drift-check.yml")
        with open(workflow_path, encoding="utf-8") as fh:
            workflow = fh.read()

        self.assertIn("if: inputs.mode == 'trusted-baseline'", workflow)
        self.assertIn("ref: ${{ inputs.trusted-base-ref }}", workflow)
        self.assertIn('--deployment-lock "trusted-base/${LOCK_PATH}"', workflow)
        self.assertIn('--candidate-ref "${CANDIDATE_REF}"', workflow)
        self.assertNotIn('--hf-ref "${CANDIDATE_REF}"', workflow)
        # The one allowlist flag belongs to legacy direct mode only.
        self.assertEqual(workflow.count("--allow "), 1)


class TestLFSContentIdentity(unittest.TestCase):
    """HF LFS is a storage representation, not evidence of content drift."""

    def setUp(self):
        self._saved = {key: getattr(drift, key) for key in (
            "github_tree_remote", "hf_tree", "github_file_sha256_remote",
            "gh_get",
        )}
        self._tmp = tempfile.mkdtemp()
        self.path = "ledger.jsonl"
        self.data = b'{"receipt":"measured"}\n' * 4096
        with open(os.path.join(self._tmp, "Dockerfile"), "w") as fh:
            fh.write("COPY ledger.jsonl /app/ledger.jsonl\n")
        with open(os.path.join(self._tmp, self.path), "wb") as fh:
            fh.write(self.data)
        self.lfs_sha256 = drift.hashlib.sha256(self.data).hexdigest()

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(drift, key, value)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _args(self, github_remote=False):
        return argparse.Namespace(
            repo_root=self._tmp,
            github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy",
            ref="main",
            github_ref="github-pr-head",
            hf_ref="hf-candidate",
            allow=None,
            github_remote=github_remote,
            report_out="",
            warn_only=False,
            siblings=[],
        )

    def test_local_lfs_sha256_match_is_in_sync(self):
        drift.hf_tree = lambda *_a, **_k: {
            self.path: {
                "oid": "lfs-pointer-blob",
                "lfs_oid": self.lfs_sha256,
                "size": len(self.data),
            }
        }

        report, errors, warns = drift.compare(self._args(), allow={})

        self.assertEqual(report["status"], "ok")
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])

    def test_local_lfs_sha256_mismatch_fails_closed(self):
        drift.hf_tree = lambda *_a, **_k: {
            self.path: {
                "oid": "lfs-pointer-blob",
                "lfs_oid": "0" * 64,
                "size": len(self.data),
            }
        }

        _report, errors, _warns = drift.compare(self._args(), allow={})

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["kind"], "lfs-drift")
        self.assertEqual(errors[0]["github_sha256"], self.lfs_sha256)

    def test_remote_lfs_uses_github_ref_and_matching_sha256(self):
        calls = []
        git_blob = drift.git_blob_sha1(self.data)
        drift.gh_get = lambda *_a, **_k: (
            200, b"COPY ledger.jsonl /app/ledger.jsonl\n", None)
        drift.github_tree_remote = lambda _repo, ref="main": {self.path: git_blob}
        drift.hf_tree = lambda *_a, **_k: {
            self.path: {
                "oid": "lfs-pointer-blob",
                "lfs_oid": self.lfs_sha256,
                "size": len(self.data),
            }
        }

        def remote_sha(repo, path, ref="main"):
            calls.append((repo, path, ref))
            return self.lfs_sha256

        drift.github_file_sha256_remote = remote_sha
        report, errors, warns = drift.compare(
            self._args(github_remote=True), allow={})

        self.assertEqual(report["status"], "ok")
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertEqual(
            calls,
            [("szl-holdings/a11oy", self.path, "github-pr-head")],
        )

    def test_oversized_remote_lfs_comparison_fails_closed_without_download(self):
        git_blob = drift.git_blob_sha1(self.data)
        drift.gh_get = lambda *_a, **_k: (
            200, b"COPY ledger.jsonl /app/ledger.jsonl\n", None)
        drift.github_tree_remote = lambda _repo, ref="main": {self.path: git_blob}
        drift.hf_tree = lambda *_a, **_k: {
            self.path: {
                "oid": "lfs-pointer-blob",
                "lfs_oid": self.lfs_sha256,
                "size": drift.MAX_REMOTE_LFS_COMPARE_BYTES + 1,
            }
        }
        drift.github_file_sha256_remote = lambda *_a, **_k: self.fail(
            "oversized registry artifact must not be downloaded")

        _report, errors, _warns = drift.compare(
            self._args(github_remote=True), allow={})

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["kind"], "lfs-unverified")


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

    def test_retry_after_selects_the_reset_delay(self):
        """A 429 Retry-After is the delay. This does not call Hugging Face."""
        import urllib.error
        delays = []
        original_sleep = drift.time.sleep
        original_open = drift.urllib.request.urlopen
        drift.time.sleep = delays.append

        def always_429(url, *args, **kwargs):
            raise urllib.error.HTTPError(
                url, 429, "Too Many Requests", {"Retry-After": "0"}, None)

        drift.urllib.request.urlopen = always_429
        try:
            with self.assertRaises(drift.TransientHTTPError) as ctx:
                drift._http(
                    "https://huggingface.co/api/spaces/x/tree/main", retries=1)
        finally:
            drift.time.sleep = original_sleep
            drift.urllib.request.urlopen = original_open
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(len(delays), 1)
        # Retry-After 0 plus jitter stays below the 2s exponential fallback.
        self.assertGreaterEqual(delays[0], 0)
        self.assertLess(delays[0], 2.0)

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
        # This fixture does not contact Hugging Face. Exit 0 is the neutral
        # gate result for an unverified comparison.
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                drift.compare(args)
            self.fail("expected TransientHTTPError")
        except drift.TransientHTTPError as e:
            with contextlib.redirect_stdout(output):
                rc = drift._emit_inconclusive(args, e)
        output = output.getvalue()

        self.assertEqual(rc, 0)  # NEUTRAL exit -- gate not marked red
        with open(args.report_out) as fh:
            report = json.load(fh)
        self.assertEqual(report["status"], "inconclusive")
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(report["reason"], "hf_api_429")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["findings"], [])
        self.assertIn("NOT a verified in-sync pass", output)

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


class TestRegistryInconclusiveHonesty(unittest.TestCase):
    """Registry mode must never give an inconclusive sweep a terminal OK."""

    def setUp(self):
        self._saved = {key: getattr(drift, key) for key in (
            "gh_get", "fetch_remote_allow", "compare")}
        self._tmp = tempfile.mkdtemp()
        self.registry = os.path.join(self._tmp, "registry.json")
        self.report = os.path.join(self._tmp, "report.json")
        with open(self.registry, "w") as fh:
            json.dump({"spaces": [{
                "github": "szl-holdings/a11oy",
                "hf": "SZLHOLDINGS/a11oy",
            }]}, fh)

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(drift, key, value)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _args(self):
        return argparse.Namespace(
            registry=self.registry,
            report_out=self.report,
            repo_root=".",
            ref="main",
            warn_only=False,
        )

    def _run(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = drift.run_registry(self._args())
        with open(self.report) as fh:
            report = json.load(fh)
        return rc, report, output.getvalue()

    def test_inconclusive_only_sweep_ends_inconclusive_not_ok(self):
        drift.gh_get = lambda *_a, **_k: (200, b"FROM python:3.12", None)
        drift.fetch_remote_allow = lambda *_a, **_k: {}

        def transient_compare(*_a, **_k):
            raise drift.TransientHTTPError(
                "https://huggingface.co/api/spaces/SZLHOLDINGS/a11oy/tree/main",
                429,
                8,
            )

        drift.compare = transient_compare

        rc, report, output = self._run()

        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(len(report["pairs_inconclusive"]), 1)
        self.assertIn("\nINCONCLUSIVE:", output)
        self.assertNotIn("\nOK:", output)

    def test_transient_dockerfile_preflight_is_inconclusive_not_skipped(self):
        def transient_preflight(*_a, **_k):
            raise drift.TransientHTTPError(
                "https://raw.githubusercontent.com/szl-holdings/a11oy/main/Dockerfile",
                503,
                8,
            )

        drift.gh_get = transient_preflight
        drift.fetch_remote_allow = lambda *_a, **_k: self.fail(
            "allowlist fetch must not run after an inconclusive preflight")
        drift.compare = lambda *_a, **_k: self.fail(
            "compare must not run after an inconclusive preflight")

        rc, report, output = self._run()

        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(report["pairs_skipped"], [])
        self.assertEqual(len(report["pairs_inconclusive"]), 1)
        self.assertEqual(
            report["pairs_inconclusive"][0]["reason"],
            "dockerfile-preflight-api-unavailable",
        )
        self.assertEqual(report["pairs"][0]["status"], "inconclusive")
        self.assertEqual(report["pairs"][0]["findings"][0]["path"], "Dockerfile")
        self.assertIn("Dockerfile preflight unavailable", output)
        self.assertIn("\nINCONCLUSIVE:", output)
        self.assertNotIn("\nOK:", output)

    def test_nontransient_dockerfile_preflight_keeps_legacy_skip_policy(self):
        def nontransient_preflight(*_a, **_k):
            raise RuntimeError("permanent read failure")

        drift.gh_get = nontransient_preflight
        drift.fetch_remote_allow = lambda *_a, **_k: self.fail(
            "allowlist fetch must not run after a skipped preflight")
        drift.compare = lambda *_a, **_k: self.fail(
            "compare must not run after a skipped preflight")

        rc, report, output = self._run()

        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["pairs_inconclusive"], [])
        self.assertEqual(
            report["pairs_skipped"],
            [{
                "github": "szl-holdings/a11oy",
                "hf": "SZLHOLDINGS/a11oy",
                "reason": "dockerfile-unreachable",
            }],
        )
        self.assertIn("could not reach Dockerfile", output)
        self.assertIn("\nOK:", output)
        self.assertNotIn("\nINCONCLUSIVE:", output)


class TestRemoteAddContextSemantics(unittest.TestCase):
    def test_remote_add_is_not_repository_managed(self):
        checksum = "b" * 64
        dockerfile = (
            "FROM scratch\n"
            f"ADD --checksum=sha256:{checksum} https://example.invalid/archive.tgz /tmp/archive.tgz\n"
            "COPY module.py /app/module.py\n"
        )
        self.assertEqual(drift.parse_copy_sources(dockerfile), ["module.py"])

    def test_local_add_remains_repository_managed(self):
        self.assertEqual(
            drift.parse_copy_sources("FROM scratch\nADD local.tgz /tmp/local.tgz\n"),
            ["local.tgz"],
        )


def _character_class_strip(source: str) -> str:
    """Historical main behavior at add3ae2b. Not the repair."""
    return source.strip().lstrip("./") or source.strip()


class TestCopySourceNormalization(unittest.TestCase):
    """Literal './' prefixes only. Unsafe input is omitted, not rewritten."""

    def test_dotted_repository_paths_keep_their_dot(self):
        dotted = (
            ".github/scripts/publish_readiness_verdict.py",
            ".well-known/security.txt",
        )
        for path in dotted:
            self.assertNotEqual(_character_class_strip(path), path)
            self.assertEqual(drift.normalize_copy_source(path), path)
            self.assertEqual(
                drift.parse_copy_sources(f"COPY {path} /app/kept\n"),
                [path],
            )

    def test_literal_and_repeated_dot_slash_prefixes(self):
        self.assertEqual(drift.normalize_copy_source("./Dockerfile"), "Dockerfile")
        self.assertEqual(drift.normalize_copy_source("./././Dockerfile"), "Dockerfile")
        self.assertEqual(
            drift.normalize_copy_source("  ./.github/scripts/publish_readiness_verdict.py  "),
            ".github/scripts/publish_readiness_verdict.py",
        )
        self.assertEqual(
            drift.normalize_copy_source("././.well-known/security.txt"),
            ".well-known/security.txt",
        )
        self.assertEqual(
            drift.parse_copy_sources("COPY ././app.py /app/app.py\n"),
            ["app.py"],
        )

    def test_normal_paths_and_empty_input(self):
        self.assertEqual(drift.normalize_copy_source("serve.py"), "serve.py")
        self.assertEqual(drift.normalize_copy_source("dir/file.py"), "dir/file.py")
        self.assertIsNone(drift.normalize_copy_source("."))
        self.assertEqual(drift.unsupported_context_roots("COPY . /dest\n"), ["."])
        self.assertEqual(drift.unsupported_context_roots("COPY ./ /dest\n"), ["./"])
        self.assertEqual(
            drift.unsupported_context_roots("COPY ././ /dest\n"), ["././"])
        self.assertEqual(drift.rejected_copy_sources("COPY . /dest\n"), [])
        self.assertEqual(drift.rejected_copy_sources("COPY ./ /dest\n"), [])
        self.assertEqual(drift.rejected_copy_sources("COPY ././ /dest\n"), [])
        self.assertEqual(drift.normalize_copy_source("foo/./bar"), "foo/./bar")
        self.assertEqual(drift.normalize_copy_source(".../hidden"), ".../hidden")
        self.assertIsNone(drift.normalize_copy_source(".."))
        self.assertIsNone(drift.normalize_copy_source(""))
        self.assertIsNone(drift.normalize_copy_source("   "))
        self.assertIsNone(drift.normalize_copy_source("./"))
        self.assertIsNone(drift.normalize_copy_source("././"))
        self.assertEqual(drift.parse_copy_sources("COPY ./ /dest\n"), [])
        self.assertEqual(drift.parse_copy_sources("COPY ././ /dest\n"), [])
        self.assertEqual(
            drift.parse_copy_sources("COPY .../hidden /dest\n"),
            [".../hidden"],
        )

    def test_absolute_and_traversal_inputs_are_rejected(self):
        rejected = (
            "/etc/passwd",
            "//etc/passwd",
            "../secret",
            "./../secret",
            "././../etc/passwd",
            "foo/../../etc/passwd",
            "C:/Windows",
            ".\\github\\x",
            "foo\\..\\secret",
            None,
        )
        for raw in rejected:
            self.assertIsNone(drift.normalize_copy_source(raw), repr(raw))
            if isinstance(raw, str):
                self.assertEqual(
                    drift.parse_copy_sources(f"COPY {raw} /dest\n"),
                    [],
                    repr(raw),
                )
        dockerfile = "\n".join((
            "FROM scratch",
            "COPY /etc/passwd /tmp/passwd",
            "COPY ../secret /tmp/secret",
            "COPY ./../secret /tmp/secret2",
            "COPY foo/../../etc/passwd /tmp/passwd2",
            "COPY ././ /app/empty",
            "COPY .github/scripts/publish_readiness_verdict.py /app/a",
            "COPY .well-known/security.txt /app/b",
            "COPY serve.py /app/serve.py",
        ))
        parsed = drift.parse_copy_sources(dockerfile)
        self.assertEqual(
            parsed,
            [
                ".github/scripts/publish_readiness_verdict.py",
                ".well-known/security.txt",
                "serve.py",
            ],
        )
        self.assertNotIn("etc/passwd", parsed)
        self.assertNotIn("secret", parsed)
        self.assertNotIn("././", drift.rejected_copy_sources(dockerfile))
        self.assertEqual(drift.unsupported_context_roots(dockerfile), ["././"])
        self.assertNotIn("passwd", parsed)


class TestRejectedCopyCoverage(unittest.TestCase):
    """Omitting an unsafe COPY source must not become complete coverage."""

    def setUp(self):
        self._saved = {
            name: getattr(drift, name)
            for name in (
                "_http",
                "github_tree_remote",
                "hf_tree",
                "fetch_github_file",
                "github_file_date",
                "hf_dir_dates",
            )
        }

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(drift, name, value)

    def _compare(self, dockerfile, tree, allow=None):
        drift._http = lambda *args, **kwargs: (200, dockerfile, None)
        drift.github_tree_remote = lambda repo, ref="main": dict(tree)
        drift.hf_tree = lambda repo, ref="main": {
            name: {"oid": sha, "lfs_oid": None, "size": 1}
            for name, sha in tree.items()
            if name != "Dockerfile"
        }
        drift.github_file_date = lambda *args, **kwargs: None
        drift.hf_dir_dates = lambda *args, **kwargs: {}
        args = argparse.Namespace(
            repo_root=".",
            github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy",
            ref="main",
            github_ref=None,
            hf_ref=None,
            allow="",
            github_remote=True,
            report_out="",
            warn_only=False,
            siblings=[],
            dockerfile_path="Dockerfile",
        )
        return drift.compare(args, allow={} if allow is None else allow)

    def test_mixed_safe_and_unsafe_sources_are_incomplete(self):
        report, errors, warns = self._compare(
            b"COPY serve.py /app/serve.py\nCOPY ../secret /tmp/secret\n",
            {"Dockerfile": "df", "serve.py": "same"},
        )
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(report["status"], "drift")
        self.assertEqual(report["rejected_copy_sources"], ["../secret"])
        self.assertEqual(report["files_compared"], 1)
        self.assertEqual(
            [(entry["kind"], entry["path"]) for entry in errors],
            [("rejected-copy-source", "../secret")],
        )
        self.assertNotIn("secret", [entry["path"] for entry in errors])
        self.assertEqual(warns, [])

    def test_reproduced_parent_and_dot_sources_are_not_ok(self):
        parent, parent_errors, _parent_warns = self._compare(
            b"COPY ../secret /dest\n",
            {"Dockerfile": "df"},
            allow={"accepted_divergences": {"../secret": "backlog"}},
        )
        self.assertEqual(parent["status"], "drift")
        self.assertEqual(parent["files_compared"], 0)
        self.assertEqual(parent["copy_sources"], 0)
        self.assertEqual(
            [(entry["kind"], entry["path"], entry["severity"])
             for entry in parent_errors],
            [("rejected-copy-source", "../secret", "error")],
        )
        mixed, mixed_errors, _mixed_warns = self._compare(
            b"COPY ../secret serve.py /dest\n",
            {"Dockerfile": "df", "serve.py": "same"},
        )
        self.assertEqual(mixed["status"], "drift")
        self.assertEqual(mixed["files_compared"], 1)
        self.assertEqual(mixed["copy_sources"], 1)
        self.assertEqual(
            [(entry["kind"], entry["path"]) for entry in mixed_errors],
            [("rejected-copy-source", "../secret")],
        )
        for spelling, dockerfile in (
            (".", b"COPY . /dest\n"),
            ("./", b"COPY ./ /dest\n"),
        ):
            rooted, rooted_errors, rooted_warns = self._compare(
                dockerfile,
                {"Dockerfile": "df", "serve.py": "different-from-hf"},
                allow={"accepted_divergences": {spelling: "backlog"}},
            )
            self.assertEqual(rooted["status"], "drift", spelling)
            self.assertEqual(rooted["files_compared"], 0, spelling)
            self.assertEqual(rooted["copy_sources"], 0, spelling)
            self.assertEqual(rooted["rejected_copy_sources"], [], spelling)
            self.assertEqual(rooted["unsupported_context_roots"], [spelling])
            self.assertEqual(
                [(entry["kind"], entry["path"], entry["severity"])
                 for entry in rooted_errors],
                [("context-root-unsupported", spelling, "error")],
            )
            self.assertEqual(rooted_warns, [])
            kinds = [entry["kind"] for entry in rooted["findings"]]
            self.assertNotIn("missing-both", kinds)
            self.assertNotIn("rejected-copy-source", kinds)
            details = " ".join(entry.get("detail", "") for entry in rooted["findings"])
            self.assertNotIn("traversal", details)
            self.assertNotIn("..", details)
        kept, kept_errors, _kept_warns = self._compare(
            b"COPY .github/scripts/publish_readiness_verdict.py /a\n"
            b"COPY .well-known/security.txt /b\n",
            {
                "Dockerfile": "df",
                ".github/scripts/publish_readiness_verdict.py": "g",
                ".well-known/security.txt": "w",
            },
        )
        self.assertEqual(kept["status"], "ok")
        self.assertEqual(kept["files_compared"], 2)
        self.assertEqual(kept["rejected_copy_sources"], [])
        self.assertEqual(kept_errors, [])

    def test_all_unsafe_sources_are_incomplete(self):
        report, errors, warns = self._compare(
            b"COPY ../secret /tmp/secret\nCOPY /etc/passwd /tmp/passwd\n",
            {"Dockerfile": "df"},
        )
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(report["status"], "drift")
        self.assertEqual(report["copy_sources"], 0)
        self.assertEqual(report["files_compared"], 0)
        self.assertEqual(
            report["rejected_copy_sources"],
            ["../secret", "/etc/passwd"],
        )
        self.assertEqual(
            [(entry["kind"], entry["path"]) for entry in errors],
            [
                ("rejected-copy-source", "../secret"),
                ("rejected-copy-source", "/etc/passwd"),
            ],
        )
        self.assertNotIn("secret", report["rejected_copy_sources"])
        self.assertNotIn("etc/passwd", report["rejected_copy_sources"])
        self.assertEqual(warns, [])

    def _delta(self, base_dockerfile, head_dockerfile, tree):
        base = "a" * 40
        head = "b" * 40
        trees = {base: dict(tree), head: dict(tree)}
        dockerfiles = {base: base_dockerfile, head: head_dockerfile}
        drift.github_tree_remote = lambda repo, ref="main": trees[ref]
        drift.fetch_github_file = lambda repo, ref, path: dockerfiles[ref]
        return drift.candidate_managed_delta("szl-holdings/a11oy", base, head)

    def test_candidate_mixed_sources_are_not_no_changes(self):
        report = self._delta(
            b"COPY serve.py /app/serve.py\n",
            b"COPY serve.py /app/serve.py\nCOPY ../secret /tmp/secret\n",
            {"Dockerfile": "df", "serve.py": "same"},
        )
        self.assertNotEqual(report["status"], "no-changes")
        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["candidate_copy_sources"], ["serve.py"])
        self.assertEqual(report["candidate_rejected_copy_sources"], ["../secret"])
        self.assertEqual(report["baseline_rejected_copy_sources"], [])
        self.assertEqual(report["new_unresolved_sources"], [])
        self.assertEqual(report["delta_count"], 0)

    def test_candidate_all_unsafe_sources_are_not_no_changes(self):
        report = self._delta(
            b"COPY /etc/passwd /tmp/passwd\n",
            b"COPY ../secret /tmp/secret\n",
            {"Dockerfile": "df"},
        )
        self.assertNotEqual(report["status"], "no-changes")
        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["candidate_copy_sources"], [])
        self.assertEqual(report["baseline_copy_sources"], [])
        self.assertEqual(report["baseline_rejected_copy_sources"], ["/etc/passwd"])
        self.assertEqual(report["candidate_rejected_copy_sources"], ["../secret"])
        self.assertEqual(report["delta_count"], 0)
        self.assertEqual(report["new_unresolved_sources"], [])

    def test_context_root_spellings_are_equivalent_and_invalid(self):
        for spelling, dockerfile in (
            (".", b"COPY . /app\n"),
            ("./", b"COPY ./ /app\n"),
        ):
            report = self._delta(
                b"COPY serve.py /app/serve.py\n",
                dockerfile,
                {"Dockerfile": "df", "serve.py": "same"},
            )
            self.assertEqual(report["status"], "invalid", spelling)
            self.assertEqual(
                report["candidate_unsupported_context_roots"], [spelling])
            self.assertEqual(report["baseline_unsupported_context_roots"], [])
            self.assertEqual(report["candidate_rejected_copy_sources"], [])
            self.assertEqual(report["new_unresolved_sources"], [])
        baseline_root = self._delta(
            b"COPY ./ /app\n",
            b"COPY serve.py /app/serve.py\n",
            {"Dockerfile": "df", "serve.py": "same"},
        )
        self.assertEqual(baseline_root["status"], "invalid")
        self.assertEqual(
            baseline_root["baseline_unsupported_context_roots"], ["./"])
        self.assertEqual(baseline_root["candidate_rejected_copy_sources"], [])



def _drift_process_status():
    try:
        code = drift.main()
    except SystemExit as exc:
        code = exc.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def _drift_exit_probe(argv):
    """Run one stubbed caller and return the process status from main()."""
    import json
    import urllib.parse
    import urllib.request

    if len(argv) != 1:
        return 97
    case = argv[0]
    gh_repo = "fixture-owner/fixture-repo"
    hf_repo = "fixture-owner/fixture-space"
    source = "a" * 40
    candidate = "b" * 40
    live = "c" * 40
    base = "d" * 40
    safe = "FROM scratch\nCOPY serve.py /app/serve.py\n"
    traversal = "FROM scratch\nCOPY ../secret /app/secret\n"
    mixed = "FROM scratch\nCOPY serve.py /app/serve.py\nCOPY ../secret /app/secret\n"
    all_rejected = "FROM scratch\nCOPY ../secret /etc/passwd /app/\n"
    dot = "FROM scratch\nCOPY . /app\n"
    dot_slash = "FROM scratch\nCOPY ./ /app\n"
    dotted = (
        "FROM scratch\n"
        "COPY .github /app/.github\n"
        "COPY .well-known /app/.well-known\n"
        "COPY ./.github /app/.github-again\n"
    )
    single = {
        "single-traversal": traversal,
        "single-mixed": mixed,
        "single-all-rejected": all_rejected,
        "single-dot": dot,
        "single-dot-slash": dot_slash,
        "single-dotted": dotted,
    }
    registry = {
        "registry-traversal": traversal,
        "registry-mixed": mixed,
        "registry-all-rejected": all_rejected,
        "registry-dot": dot,
        "registry-dot-slash": dot_slash,
        "registry-dotted": dotted,
    }
    trusted = {
        "trusted-invalid": traversal,
        "trusted-mixed": mixed,
        "trusted-all-rejected": all_rejected,
        "trusted-dot": dot,
        "trusted-dot-slash": dot_slash,
    }

    def block_network():
        def blocked(*_args, **_kwargs):
            raise RuntimeError("network blocked")

        urllib.request.urlopen = blocked
        drift._http = blocked
        drift.github_file_date = lambda *_args, **_kwargs: None
        drift.hf_dir_dates = lambda *_args, **_kwargs: {}

    def memory_blobs(dockerfile):
        blobs = {
            "Dockerfile": dockerfile.encode("utf-8"),
            "serve.py": b'print("serve")\n',
            ".github/CODEOWNERS": b"* @fixture\n",
            ".well-known/health": b"ok\n",
            ".dockerignore": b"*\n",
        }
        shas = {path: drift.git_blob_sha1(data) for path, data in blobs.items()}
        return blobs, shas

    def write_repo(root, dockerfile):
        blobs, _shas = memory_blobs(dockerfile)
        for rel, data in blobs.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)

    with tempfile.TemporaryDirectory(prefix="szl-drift-exit-") as tmp:
        block_network()
        allow = os.path.join(tmp, "allow.json")
        with open(allow, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("{}\n")
        if case in single:
            repo = os.path.join(tmp, "repo")
            write_repo(repo, single[case])

            def hf_tree(_repo, ref="main"):
                files = drift.github_tree_local(repo)
                return {
                    path: {"oid": sha, "lfs_oid": None, "size": 1}
                    for path, sha in files.items()
                }

            drift.hf_tree = hf_tree
            sys.argv = [
                "hf_module_drift_check.py",
                "--repo-root", repo,
                "--github-repo", gh_repo,
                "--hf-repo", hf_repo,
                "--allow", allow,
                "--warn-only",
            ]
            return _drift_process_status()
        if case in registry:
            blobs, shas = memory_blobs(registry[case])

            def gh_get(url, want_headers=False):
                parsed = urllib.parse.urlparse(url)
                path = urllib.parse.unquote(parsed.path)
                status, body = 404, b""
                if parsed.netloc == "raw.githubusercontent.com":
                    parts = path.strip("/").split("/")
                    rel = "/".join(parts[3:]) if len(parts) >= 4 else ""
                    if rel in blobs:
                        status, body = 200, blobs[rel]
                    elif rel != ".github/hf-module-drift-allow.json":
                        raise RuntimeError("network blocked: " + url)
                elif parsed.netloc == "api.github.com" and "/git/trees/" in path:
                    payload = {
                        "truncated": False,
                        "tree": [
                            {"path": rel, "type": "blob", "sha": sha}
                            for rel, sha in shas.items()
                        ],
                    }
                    status, body = 200, json.dumps(payload).encode("utf-8")
                else:
                    raise RuntimeError("network blocked: " + url)
                return status, body, {} if want_headers else None

            drift.gh_get = gh_get
            drift.hf_tree = lambda _repo, ref="main": {
                rel: {"oid": sha, "lfs_oid": None, "size": len(blobs[rel])}
                for rel, sha in shas.items()
            }
            registry_path = os.path.join(tmp, "registry.json")
            with open(registry_path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    {
                        "spaces": [{
                            "github": gh_repo,
                            "hf": hf_repo,
                            "ref": source,
                            "github_ref": source,
                            "hf_ref": live,
                        }]
                    },
                    handle,
                )
            sys.argv = [
                "hf_module_drift_check.py",
                "--registry", registry_path,
                "--ref", source,
                "--allow", allow,
                "--warn-only",
            ]
            return _drift_process_status()
        if case == "trusted-dotted":
            candidate_df = dotted
        elif case in trusted:
            candidate_df = trusted[case]
        elif case == "trusted-warn-only":
            candidate_df = None
        else:
            return 97
        if case != "trusted-warn-only":
            trees = {}
            blobs_by_ref = {}
            for ref, dockerfile in ((source, safe if case != "trusted-dotted" else dotted),
                                    (candidate, candidate_df)):
                blobs, shas = memory_blobs(dockerfile)
                trees[ref] = shas
                blobs_by_ref[ref] = blobs
            drift.fetch_github_file = (
                lambda _repo, ref, path: blobs_by_ref[ref][path]
            )
            drift.github_tree_remote = lambda _repo, ref="main": dict(trees[ref])
            drift.hf_tree = lambda _repo, ref="main": {
                path: {
                    "oid": sha,
                    "lfs_oid": None,
                    "size": len(blobs_by_ref[source][path]),
                }
                for path, sha in trees[source].items()
            }
            drift.github_ref_is_ancestor = lambda *_args, **_kwargs: (True, "ahead")

            def hf_space_state(_repo, observation_count=2):
                return {
                    "head_sha": live,
                    "runtime_sha": live,
                    "runtime_stage": "RUNNING",
                    "observation_status": "stable",
                    "observation_count": observation_count,
                    "required_observation_count": observation_count,
                    "observations": [{}, {}],
                }

            drift.hf_space_state = hf_space_state
        lock_path = os.path.join(tmp, "lock.json")
        with open(lock_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "schema": 1,
                    "github_repo": gh_repo,
                    "github_source_sha": source,
                    "hf_repo": hf_repo,
                    "hf_commit_sha": live,
                },
                handle,
            )
        sys.argv = [
            "hf_module_drift_check.py",
            "--github-repo", gh_repo,
            "--hf-repo", hf_repo,
            "--deployment-lock", lock_path,
            "--trusted-base-ref", base,
            "--candidate-ref", candidate,
            "--ref", source,
            "--allow", allow,
        ]
        if case == "trusted-warn-only":
            sys.argv.append("--warn-only")
        return _drift_process_status()


class TestContractProcessExit(unittest.TestCase):
    """Process status is the contract. A drift label alone is not."""

    def _run(self, case):
        env = os.environ.copy()
        env["SZL_DRIFT_EXIT_PROBE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, os.path.abspath(__file__), case],
            cwd=_HERE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    def test_warn_only_contract_failures_exit_nonzero(self):
        expected = {
            "single-traversal": 1,
            "single-mixed": 1,
            "single-all-rejected": 1,
            "single-dot": 1,
            "single-dot-slash": 1,
            "single-dotted": 0,
            "registry-traversal": 1,
            "registry-mixed": 1,
            "registry-all-rejected": 1,
            "registry-dot": 1,
            "registry-dot-slash": 1,
            "registry-dotted": 0,
            "trusted-invalid": 1,
            "trusted-mixed": 1,
            "trusted-all-rejected": 1,
            "trusted-dot": 1,
            "trusted-dot-slash": 1,
            "trusted-dotted": 0,
            "trusted-warn-only": 2,
        }
        context_cases = {
            "single-dot",
            "single-dot-slash",
            "registry-dot",
            "registry-dot-slash",
            "trusted-dot",
            "trusted-dot-slash",
        }
        for case, code in expected.items():
            with self.subTest(case=case):
                completed = self._run(case)
                self.assertEqual(
                    completed.returncode,
                    code,
                    completed.stdout + "\n" + completed.stderr,
                )
                if code == 1:
                    self.assertIn("\nFAIL:", "\n" + completed.stdout)
                    self.assertNotIn("\nOK:", "\n" + completed.stdout)
                elif code == 0:
                    self.assertIn("\nOK:", "\n" + completed.stdout)
                    self.assertNotIn("\nFAIL:", "\n" + completed.stdout)
                    self.assertNotIn("context-root-unsupported", completed.stdout)
                    self.assertNotIn("rejected-copy-source", completed.stdout)
                else:
                    self.assertIn("forbidden", completed.stderr)
                if case in context_cases:
                    self.assertIn("context-root-unsupported", completed.stdout)
                    self.assertNotIn("missing-both", completed.stdout)
                    self.assertNotIn("traversal", completed.stdout.lower())



if __name__ == "__main__":
    if os.environ.get("SZL_DRIFT_EXIT_PROBE") == "1":
        raise SystemExit(_drift_exit_probe(sys.argv[1:]))
    unittest.main(verbosity=2)
