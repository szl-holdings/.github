#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
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
            "fetch_github_file": drift.fetch_github_file,
            "github_tree_remote": drift.github_tree_remote,
            "hf_tree": drift.hf_tree,
            "github_file_date": drift.github_file_date,
            "hf_dir_dates": drift.hf_dir_dates,
            "_http": drift._http,
        }

    def tearDown(self):
        for key, value in self.saved.items():
            if key == "source_probe_state":
                baseline.source_probe_state = value
            else:
                setattr(drift, key, value)

    def args(self, candidate=True, expected_source_ref=""):
        return argparse.Namespace(
            github_repo="szl-holdings/a11oy",
            hf_repo="SZLHOLDINGS/a11oy",
            trusted_base_ref=self.BASE,
            candidate_ref=self.HEAD if candidate else "",
            expected_source_ref=expected_source_ref,
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
        self.assertIsNone(report["expected_source_ref"])
        self.assertEqual(
            report["source_binding_policy"], "ancestor-or-exact-candidate"
        )
        self.assertTrue(report["source_binding_valid"])
        self.assertFalse(report["allowlist_used"])
        self.assertEqual(candidate["baseline_ref"], self.SOURCE)

    def test_exact_expected_source_succeeds_without_ancestry_fallback(self):
        calls = self.install_clean()
        drift.github_ref_is_ancestor = lambda *_args: self.fail(
            "exact expected-source mode must not use ancestry"
        )

        report, errors, warns, candidate = baseline.source_bound_baseline_compare(
            self.args(expected_source_ref=self.SOURCE)
        )

        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertEqual(calls["refs"], (self.SOURCE, self.LIVE))
        self.assertEqual(report["expected_source_ref"], self.SOURCE)
        self.assertEqual(report["source_binding_policy"], "exact-expected-source")
        self.assertTrue(report["source_binding_valid"])
        self.assertEqual(
            report["observed_source_ancestry_status"], "exact-expected-source"
        )
        self.assertEqual(candidate["baseline_ref"], self.SOURCE)

    def test_stale_ancestor_fails_exact_mode_without_compare_or_candidate_delta(self):
        self.install_clean()
        drift.github_ref_is_ancestor = lambda *_args: self.fail(
            "exact expected-source mode must not fall back to ancestry"
        )
        drift.compare = lambda *_args, **_kwargs: self.fail("compare must not run")
        drift.candidate_managed_delta = lambda *_args: self.fail(
            "candidate delta must not run for an invalid source binding"
        )

        report, errors, warns, candidate = baseline.source_bound_baseline_compare(
            self.args(expected_source_ref=self.BASE)
        )

        self.assertEqual(warns, [])
        self.assertIsNone(candidate)
        self.assertEqual(report["status"], "drift")
        self.assertEqual(report["expected_source_ref"], self.BASE)
        self.assertFalse(report["source_binding_valid"])
        self.assertEqual(
            report["observed_source_ancestry_status"], "expected-source-mismatch"
        )
        exact_errors = [
            item for item in errors if item["kind"] == "observed-source-not-exact"
        ]
        self.assertEqual(len(exact_errors), 1)
        self.assertEqual(exact_errors[0]["observed_source_sha"], self.SOURCE)
        self.assertEqual(exact_errors[0]["expected_source_ref"], self.BASE)

    def test_malformed_expected_source_fails_before_any_network_observation(self):
        drift.hf_space_state = lambda *_args: self.fail("HF must not be queried")
        baseline.source_probe_state = lambda *_args: self.fail(
            "source probe must not be queried"
        )
        drift.github_ref_is_ancestor = lambda *_args: self.fail(
            "GitHub ancestry must not be queried"
        )

        with self.assertRaisesRegex(ValueError, "expected protected source GitHub SHA"):
            baseline.source_bound_baseline_compare(
                self.args(expected_source_ref="main")
            )

    def test_exact_deployed_candidate_is_a_valid_source_bound_baseline(self):
        calls = self.install_clean()
        baseline.source_probe_state = lambda _repo, _path: {
            "observation_status": "stable",
            "observation_count": 2,
            "required_observation_count": 2,
            "source_revision": self.HEAD,
            "observations": [],
        }
        drift.github_ref_is_ancestor = lambda *_args: self.fail(
            "exact candidate must not require ancestry against the PR base"
        )
        drift.candidate_managed_delta = (
            lambda _repo, baseline_ref, candidate_ref, _dockerfile: {
                "status": "no-changes",
                "new_unresolved_sources": [],
                "delta_count": 0,
                "deltas": [],
                "baseline_ref": baseline_ref,
                "candidate_ref": candidate_ref,
            }
        )

        report, errors, warns, candidate = baseline.source_bound_baseline_compare(
            self.args()
        )

        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertEqual(calls["refs"], (self.HEAD, self.LIVE))
        self.assertEqual(report["observed_source_ancestry_status"], "exact-candidate")
        self.assertEqual(candidate["status"], "no-changes")
        self.assertEqual(candidate["baseline_ref"], self.HEAD)

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
            self.args()
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

    def test_rejected_candidate_copy_source_is_not_ok(self):
        self.install_clean()
        drift.candidate_managed_delta = lambda *_args: {
            "status": "invalid",
            "new_unresolved_sources": [],
            "candidate_rejected_copy_sources": ["../secret"],
            "baseline_rejected_copy_sources": [],
            "delta_count": 0,
            "deltas": [],
            "baseline_ref": self.SOURCE,
            "candidate_ref": self.HEAD,
        }
        report, errors, _warns, candidate = baseline.source_bound_baseline_compare(
            self.args()
        )
        self.assertEqual(candidate["status"], "invalid")
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(
            [(item["kind"], item["path"]) for item in errors],
            [("rejected-copy-source", "../secret")],
        )

    def test_rejected_baseline_copy_source_is_not_ok(self):
        self.install_clean()
        drift.candidate_managed_delta = lambda *_args: {
            "status": "invalid",
            "new_unresolved_sources": [],
            "candidate_rejected_copy_sources": [],
            "baseline_rejected_copy_sources": ["./"],
            "delta_count": 0,
            "deltas": [],
            "baseline_ref": self.SOURCE,
            "candidate_ref": self.HEAD,
        }
        report, errors, _warns, candidate = baseline.source_bound_baseline_compare(
            self.args()
        )
        self.assertEqual(candidate["status"], "invalid")
        self.assertNotEqual(report["status"], "ok")
        self.assertEqual(
            [(item["kind"], item["path"]) for item in errors],
            [("rejected-copy-source", "./")],
        )
    def _install_real_plan(self, source_sha, candidate_sha, live_sha, source_df, candidate_df):
        blobs = {}
        trees = {}

        def add(ref, dockerfile):
            raw = {
                "Dockerfile": dockerfile.encode("utf-8"),
                "serve.py": b'print("serve")\n',
                ".github/CODEOWNERS": b"* @fixture\n",
                ".well-known/health": b"ok\n",
            }
            trees[ref] = {
                path: drift.git_blob_sha1(data) for path, data in raw.items()
            }
            blobs[ref] = raw

        add(source_sha, source_df)
        add(candidate_sha, candidate_df)
        drift.fetch_github_file = lambda _repo, ref, path: blobs[ref][path]
        drift.github_tree_remote = lambda _repo, ref="main": dict(trees[ref])
        drift.hf_tree = lambda _repo, ref="main": {
            path: {"oid": sha, "lfs_oid": None, "size": len(blobs[source_sha][path])}
            for path, sha in trees[source_sha].items()
        }
        drift.github_file_date = lambda *_args, **_kwargs: None
        drift.hf_dir_dates = lambda *_args, **_kwargs: {}
        drift._http = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("network blocked")
        )
        drift.hf_space_state = lambda _repo: {
            "observation_status": "stable",
            "observation_count": 2,
            "required_observation_count": 2,
            "head_sha": live_sha,
            "runtime_sha": live_sha,
            "runtime_stage": "RUNNING",
            "observations": [],
        }
        baseline.source_probe_state = lambda _repo, _path: {
            "observation_status": "stable",
            "observation_count": 2,
            "required_observation_count": 2,
            "source_revision": source_sha,
            "observations": [],
        }
        drift.github_ref_is_ancestor = lambda *_args: (True, "ahead")
        drift.compare = self.saved["compare"]
        drift.candidate_managed_delta = self.saved["candidate_managed_delta"]

    def test_omitted_unsafe_candidate_is_not_an_ok_plan(self):
        source = "a" * 40
        candidate = "b" * 40
        live = "c" * 40
        safe = "FROM scratch\nCOPY serve.py /app/serve.py\n"
        self._install_real_plan(
            source,
            candidate,
            live,
            safe,
            "FROM scratch\nCOPY ../secret /app/secret\n",
        )
        args = self.args()
        args.trusted_base_ref = "d" * 40
        args.candidate_ref = candidate
        args.expected_source_ref = source
        report, errors, _warns, plan = baseline.source_bound_baseline_compare(args)
        self.assertEqual(plan["status"], "invalid")
        self.assertEqual(plan["candidate_rejected_copy_sources"], ["../secret"])
        self.assertNotEqual(report["status"], "ok")
        self.assertIn("rejected-copy-source", {item["kind"] for item in errors})

    def test_context_roots_and_dotted_controls_keep_their_kinds(self):
        source = "a" * 40
        candidate = "b" * 40
        live = "c" * 40
        safe = "FROM scratch\nCOPY serve.py /app/serve.py\n"
        dotted = (
            "FROM scratch\n"
            "COPY .github /app/.github\n"
            "COPY .well-known /app/.well-known\n"
            "COPY ./.github /app/.github-again\n"
        )
        for spelling, dockerfile in (
            (".", "FROM scratch\nCOPY . /app\n"),
            ("./", "FROM scratch\nCOPY ./ /app\n"),
        ):
            self._install_real_plan(source, candidate, live, safe, dockerfile)
            args = self.args()
            args.trusted_base_ref = "d" * 40
            args.candidate_ref = candidate
            args.expected_source_ref = source
            report, errors, _warns, plan = baseline.source_bound_baseline_compare(args)
            self.assertEqual(plan["status"], "invalid", spelling)
            self.assertEqual(
                plan["candidate_unsupported_context_roots"], [spelling], spelling
            )
            self.assertEqual(plan["candidate_rejected_copy_sources"], [], spelling)
            self.assertNotEqual(report["status"], "ok", spelling)
            self.assertIn(
                "context-root-unsupported", {item["kind"] for item in errors}, spelling
            )
            self.assertNotIn(
                "missing-both", {item["kind"] for item in errors}, spelling
            )
        self._install_real_plan(source, candidate, live, dotted, dotted)
        args = self.args()
        args.trusted_base_ref = "d" * 40
        args.candidate_ref = candidate
        args.expected_source_ref = source
        report, errors, _warns, plan = baseline.source_bound_baseline_compare(args)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(plan["status"], "no-changes")
        self.assertEqual(plan["candidate_unsupported_context_roots"], [])
        self.assertEqual(plan["candidate_rejected_copy_sources"], [])

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
            "EXPECTED_SOURCE_REF: ${{ inputs.expected-source-ref }}",
            '--expected-source-ref "${EXPECTED_SOURCE_REF}"',
        ):
            self.assertIn(safe, self.workflow)
        self.assertNotIn(
            '--source-probe-path "${{ inputs.source-probe-path }}"', self.workflow
        )
        self.assertNotIn(
            '--expected-source-ref "${{ inputs.expected-source-ref }}"',
            self.workflow,
        )
        self.assertIn("expected-source-ref:", self.workflow)
        self.assertIn(
            "expected-source-ref must be an exact lowercase 40-character SHA",
            self.workflow,
        )

    def test_exact_reusable_revision_tools_and_reports_are_preserved(self):
        self.assertIn("ref: ${{ job.workflow_sha }}", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertIn("hf-module-drift-report.out.json", self.workflow)
        self.assertIn("hf-managed-candidate-plan.out.json", self.workflow)
        self.assertIn("retention-days: 90", self.workflow)



def _source_bound_process_status():
    try:
        code = baseline.main()
    except SystemExit as exc:
        code = exc.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def _source_bound_exit_probe(argv):
    """Run source-bound main() with network stubs and return its status."""
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
    cases = {
        "invalid": "FROM scratch\nCOPY ../secret /app/secret\n",
        "mixed": "FROM scratch\nCOPY serve.py /app/serve.py\nCOPY ../secret /app/secret\n",
        "all-rejected": "FROM scratch\nCOPY ../secret /etc/passwd /app/\n",
        "dot": "FROM scratch\nCOPY . /app\n",
        "dot-slash": "FROM scratch\nCOPY ./ /app\n",
        "dotted": (
            "FROM scratch\n"
            "COPY .github /app/.github\n"
            "COPY .well-known /app/.well-known\n"
            "COPY ./.github /app/.github-again\n"
        ),
    }
    if case not in cases:
        return 97
    baseline_df = cases["dotted"] if case == "dotted" else safe

    def blobs_for(dockerfile):
        blobs = {
            "Dockerfile": dockerfile.encode("utf-8"),
            "serve.py": b'print("serve")\n',
            ".github/CODEOWNERS": b"* @fixture\n",
            ".well-known/health": b"ok\n",
            ".dockerignore": b"*\n",
        }
        shas = {path: drift.git_blob_sha1(data) for path, data in blobs.items()}
        return blobs, shas

    trees = {}
    blobs_by_ref = {}
    for ref, dockerfile in ((source, baseline_df), (candidate, cases[case])):
        blobs, shas = blobs_for(dockerfile)
        trees[ref] = shas
        blobs_by_ref[ref] = blobs

    def blocked(*_args, **_kwargs):
        raise RuntimeError("network blocked")

    urllib.request.urlopen = blocked
    drift._http = blocked
    drift.github_file_date = lambda *_args, **_kwargs: None
    drift.hf_dir_dates = lambda *_args, **_kwargs: {}
    drift.fetch_github_file = lambda _repo, ref, path: blobs_by_ref[ref][path]
    drift.github_tree_remote = lambda _repo, ref="main": dict(trees[ref])
    drift.hf_tree = lambda _repo, ref="main": {
        path: {"oid": sha, "lfs_oid": None, "size": len(blobs_by_ref[source][path])}
        for path, sha in trees[source].items()
    }
    drift.github_ref_is_ancestor = lambda *_args, **_kwargs: (True, "ahead")
    drift.hf_space_state = lambda _repo, observation_count=2: {
        "head_sha": live,
        "runtime_sha": live,
        "runtime_stage": "RUNNING",
        "observation_status": "stable",
        "observation_count": observation_count,
        "required_observation_count": observation_count,
        "observations": [{}, {}],
    }
    baseline.source_probe_state = lambda _repo, _path, observation_count=2: {
        "observation_status": "stable",
        "observation_count": observation_count,
        "required_observation_count": observation_count,
        "source_revision": source,
        "observations": [],
    }
    sys.argv = [
        "hf_source_bound_baseline.py",
        "--github-repo", gh_repo,
        "--hf-repo", hf_repo,
        "--trusted-base-ref", base,
        "--candidate-ref", candidate,
        "--expected-source-ref", source,
        "--source-probe-path", "/api/build-info",
    ]
    return _source_bound_process_status()


class TestSourceBoundProcessExit(unittest.TestCase):
    """The source-bound caller must fail closed without a warn-only flag."""

    def _run(self, case):
        env = os.environ.copy()
        env["SZL_SOURCE_BOUND_EXIT_PROBE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, os.path.abspath(__file__), case],
            cwd=HERE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    def test_invalid_plans_and_context_roots_exit_nonzero(self):
        expected = {
            "invalid": 1,
            "mixed": 1,
            "all-rejected": 1,
            "dot": 1,
            "dot-slash": 1,
            "dotted": 0,
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
                else:
                    self.assertIn("\nOK:", "\n" + completed.stdout)
                    self.assertNotIn("\nFAIL:", "\n" + completed.stdout)
                    self.assertNotIn("context-root-unsupported", completed.stdout)
                    self.assertNotIn("rejected-copy-source", completed.stdout)
                if case in {"dot", "dot-slash"}:
                    self.assertIn("context-root-unsupported", completed.stdout)
                    self.assertNotIn("missing-both", completed.stdout)
                    self.assertNotIn("traversal", completed.stdout.lower())


if __name__ == "__main__":
    if os.environ.get("SZL_SOURCE_BOUND_EXIT_PROBE") == "1":
        raise SystemExit(_source_bound_exit_probe(sys.argv[1:]))
    unittest.main(verbosity=2)
