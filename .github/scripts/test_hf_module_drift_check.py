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


if __name__ == "__main__":
    unittest.main(verbosity=2)
