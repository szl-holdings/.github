#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.path.join(HERE, "hf_source_bound_baseline.py")
SPEC = importlib.util.spec_from_file_location("hf_source_bound_baseline", MODULE_PATH)
assert SPEC and SPEC.loader
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)
drift = baseline.drift


class SourceProbeTests(unittest.TestCase):
    def setUp(self):
        self.saved_fetch = baseline._fetch_json_no_redirect

    def tearDown(self):
        baseline._fetch_json_no_redirect = self.saved_fetch

    def test_probe_path_and_space_origin_are_same_host_only(self):
        self.assertEqual(
            baseline.require_probe_path("/api/build-info?view=summary"),
            "/api/build-info?view=summary",
        )
        self.assertEqual(
            baseline.space_origin("SZLHOLDINGS/a11oy"),
            "https://szlholdings-a11oy.hf.space",
        )
        for value in (
            "https://evil.example/api/build-info",
            "//evil.example/api/build-info",
            "relative/path",
            "/api/build-info#fragment",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                baseline.require_probe_path(value)

    def test_two_cache_bypassed_exact_read_only_observations_are_stable(self):
        source = "a" * 40
        calls = []

        def fetch(url):
            calls.append(url)
            return (
                200,
                {
                    "status": "OBSERVED",
                    "build": {"state": "OBSERVED", "revision": source},
                    "receipt_minted": False,
                },
                {"content-type": "application/json"},
            )

        baseline._fetch_json_no_redirect = fetch
        state = baseline.source_probe_state(
            "SZLHOLDINGS/a11oy", "/api/build-info", observation_count=2
        )
        self.assertEqual(state["observation_status"], "stable")
        self.assertEqual(state["source_revision"], source)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])
        self.assertTrue(all("cache_bust=" in url for url in calls))

    def test_mixed_or_receipt_minting_observations_never_green(self):
        values = iter(("a" * 40, "b" * 40))

        def mixed(_url):
            return (
                200,
                {
                    "build": {"state": "OBSERVED", "revision": next(values)},
                    "receipt_minted": False,
                },
                {"content-type": "application/json"},
            )

        baseline._fetch_json_no_redirect = mixed
        state = baseline.source_probe_state("SZLHOLDINGS/a11oy", "/api/build-info")
        self.assertEqual(state["observation_status"], "inconsistent")
        self.assertIsNone(state["source_revision"])

        def minting(_url):
            return (
                200,
                {
                    "build": {"state": "OBSERVED", "revision": "a" * 40},
                    "receipt_minted": True,
                },
                {"content-type": "application/json"},
            )

        baseline._fetch_json_no_redirect = minting
        state = baseline.source_probe_state("SZLHOLDINGS/a11oy", "/api/build-info")
        self.assertEqual(state["observation_status"], "inconsistent")


class SourceBoundBaselineTests(unittest.TestCase):
    SOURCE = "1" * 40
    LIVE = "2" * 40
    BASE = "3" * 40
    HEAD = "4" * 40

    def setUp(self):
        self.saved = {
            "hf_space_state": drift.hf_space_state,
            "github_ref_is_ancestor": drift.github_ref_is_ancestor,
            "compare": drift.compare,
            "candidate_managed_delta": drift.candidate_managed_delta,
            "source_probe_state": baseline.source_probe_state,
        }

    def tearDown(self):
        for key, value in self.saved.items():
            if key == "source_probe_state":
                baseline.source_probe_state = value
            else:
                setattr(drift, key, value)

    def args(self, candidate=True):
        return argparse.Namespace(
            github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy",
            trusted_base_ref=self.BASE,
            candidate_ref=self.HEAD if candidate else "",
            dockerfile_path="Dockerfile",
            source_probe_path="/api/build-info",
            ref="main",
            repo_root=".",
            github_ref="",
            hf_ref="",
            github_remote=True,
            allow="",
            siblings=[],
        )

    def install_clean(self):
        calls = {}
        drift.hf_space_state = lambda _repo: {
            "observation_status": "stable",
            "observation_count": 2,
            "required_observation_count": 2,
            "head_sha": self.LIVE,
            "runtime_sha": self.LIVE,
            "runtime_stage": "RUNNING",
            "observations": [],
        }
        baseline.source_probe_state = lambda _repo, _path: {
            "observation_status": "stable",
            "observation_count": 2,
            "required_observation_count": 2,
            "source_revision": self.SOURCE,
            "observations": [],
        }
        drift.github_ref_is_ancestor = lambda *_args: (True, "ahead")

        def compare(args, allow=None, include_dockerfile=False):
            calls["refs"] = (args.github_ref, args.hf_ref)
            calls["allow"] = allow
            calls["include_dockerfile"] = include_dockerfile
            return (
                {
                    "schema": 1,
                    "status": "ok",
                    "github_repo": args.github_repo,
                    "hf_repo": args.hf_repo,
                    "ref": args.ref,
                    "github_ref": args.github_ref,
                    "hf_ref": args.hf_ref,
                    "dockerfile_path": args.dockerfile_path,
                    "copy_sources": 5,
                    "files_compared": 10,
                    "findings": [],
                },
                [],
                [],
            )

        drift.compare = compare
        drift.candidate_managed_delta = lambda *_args: {
            "status": "changes",
            "new_unresolved_sources": [],
            "delta_count": 1,
            "deltas": [{"path": "serve.py", "kind": "modified"}],
            "baseline_ref": self.SOURCE,
            "candidate_ref": self.HEAD,
        }
        return calls

    def test_clean_pair_uses_observed_source_and_live_hf_revisions(self):
        calls = self.install_clean()
        report, errors, warns, candidate = baseline.source_bound_baseline_compare(
            self.args()
        )
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertEqual(calls["refs"], (self.SOURCE, self.LIVE))
        self.assertEqual(calls["allow"], {})
        self.assertTrue(calls["include_dockerfile"])
        self.assertEqual(report["mode"], "source-bound-live-baseline")
        self.assertEqual(report["observed_source_sha"], self.SOURCE)
        self.assertFalse(report["allowlist_used"])
        self.assertEqual(candidate["baseline_ref"], self.SOURCE)

    def test_split_runtime_or_unstable_probe_fails_closed_without_compare(self):
        self.install_clean()
        drift.hf_space_state = lambda _repo: {
            "observation_status": "stable",
            "head_sha": self.LIVE,
            "runtime_sha": "9" * 40,
            "runtime_stage": "RUNNING",
            "observations": [],
        }
        drift.compare = lambda *_args, **_kwargs: self.fail("compare must not run")
        _report, errors, _warns, _candidate = baseline.source_bound_baseline_compare(
            self.args(candidate=False)
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("live-hf-head-runtime-split", kinds)

        self.install_clean()
        baseline.source_probe_state = lambda _repo, _path: {
            "observation_status": "inconsistent",
            "source_revision": None,
            "observations": [],
        }
        drift.compare = lambda *_args, **_kwargs: self.fail("compare must not run")
        _report, errors, _warns, _candidate = baseline.source_bound_baseline_compare(
            self.args(candidate=False)
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("source-probe-not-stable", kinds)
        self.assertIn("observed-source-not-immutable", kinds)

    def test_nonancestor_source_and_new_unresolved_candidate_fail(self):
        self.install_clean()
        drift.github_ref_is_ancestor = lambda *_args: (False, "diverged")
        report, errors, _warns, _candidate = baseline.source_bound_baseline_compare(
            self.args(candidate=False)
        )
        self.assertEqual(report["status"], "drift")
        self.assertIn("observed-source-not-ancestor", {item["kind"] for item in errors})

        self.install_clean()
        drift.candidate_managed_delta = lambda *_args: {
            "status": "invalid",
            "new_unresolved_sources": ["missing.py"],
            "delta_count": 0,
            "deltas": [],
            "baseline_ref": self.SOURCE,
            "candidate_ref": self.HEAD,
        }
        _report, errors, _warns, _candidate = baseline.source_bound_baseline_compare(
            self.args()
        )
        self.assertIn(
            "candidate-unresolved-copy-source", {item["kind"] for item in errors}
        )

    def test_source_bound_module_contains_no_mutation_or_warn_only(self):
        with open(MODULE_PATH, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in (
            "upload_file",
            "upload_folder",
            "add_space_variable",
            "restart_space",
            "request_space_hardware",
            "--warn-only",
        ):
            self.assertNotIn(forbidden, source)


class ReusableWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(HERE, "..", "workflows", "reusable-hf-module-drift-check.yml")
        with open(path, encoding="utf-8") as handle:
            cls.workflow = handle.read()

    def test_source_bound_mode_is_read_only_and_lock_independent(self):
        self.assertIn("source-bound-baseline", self.workflow)
        self.assertIn("source-probe-path:", self.workflow)
        self.assertIn("hf_source_bound_baseline.py", self.workflow)
        source_step = self.workflow.split(
            "Verify source-bound immutable live baseline and report candidate plan", 1
        )[1]
        self.assertNotIn("deployment-lock", source_step)
        self.assertNotIn("secrets.", self.workflow)
        self.assertIn("permissions:\n  contents: read", self.workflow)

    def test_source_bound_inputs_enter_shell_through_environment(self):
        for safe in (
            "SOURCE_PROBE_PATH: ${{ inputs.source-probe-path }}",
            '--source-probe-path "${SOURCE_PROBE_PATH}"',
            "TRUSTED_BASE_REF: ${{ inputs.trusted-base-ref }}",
            "CANDIDATE_REF: ${{ inputs.candidate-ref }}",
        ):
            self.assertIn(safe, self.workflow)
        self.assertNotIn(
            '--source-probe-path "${{ inputs.source-probe-path }}"', self.workflow
        )

    def test_exact_reusable_revision_tools_and_reports_are_preserved(self):
        self.assertIn("ref: ${{ job.workflow_sha }}", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertIn("hf-module-drift-report.out.json", self.workflow)
        self.assertIn("hf-managed-candidate-plan.out.json", self.workflow)
        self.assertIn("retention-days: 90", self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
