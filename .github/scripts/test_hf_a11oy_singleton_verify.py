#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import subprocess
import tempfile
import textwrap
from unittest import mock
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

verifier = importlib.import_module("hf_a11oy_singleton_verify")


class A11oySingletonVerifierContractTests(unittest.TestCase):
    def test_exact_absence_set_and_one_canonical_space(self) -> None:
        self.assertEqual(verifier.CANONICAL_SPACE, "SZLHOLDINGS/a11oy")
        self.assertEqual(
            verifier.HISTORICAL_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )

    def test_verifier_has_no_clone_creation_adoption_or_deletion_path(self) -> None:
        source = (SCRIPT_DIR / "hf_a11oy_singleton_verify.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "duplicate_repo(",
            "duplicate_space(",
            "create_repo(",
            "CommitOperationCopy",
            "canonical-content-adoption",
            "select-newest-a11oy-source",
            "delete_repo(",
            "update_repo_settings",
            "clone-refresh",
            "last_modified_epoch",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("clone-absence", source)
        self.assertIn("canonical-route", source)
        self.assertIn("collection-remove-stale-clone", source)

    def test_critical_routes_bind_build_identity_and_brain(self) -> None:
        paths = [path for path, _ in verifier.IMPORTANT_ROUTES]
        self.assertIn("/api/build-info", paths)
        self.assertIn("/api/a11oy/v1/brain/capabilities", paths)
        self.assertIn("/api/a11oy/readyz", paths)
        self.assertIn("/holographic", paths)
        self.assertEqual(len(paths), len(set(paths)))

    def test_recursive_revision_match(self) -> None:
        expected = "a" * 40
        payload = {"build": {"revision": expected}, "other": [1, 2]}
        self.assertTrue(verifier.contains_value(payload, expected))
        self.assertFalse(verifier.contains_value(payload, "b" * 40))

    def test_collections_listing_stays_below_hub_limit_edge(self) -> None:
        source = (SCRIPT_DIR / "hf_a11oy_singleton_verify.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            source.count("self.api.list_collections(owner=ORG, limit=99)"),
            2,
        )
        self.assertNotIn("self.api.list_collections(owner=ORG, limit=100)", source)

    def test_workflow_invokes_only_post_migration_verifier(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("hf_a11oy_singleton_verify.py", workflow)
        self.assertIn("Verify one canonical A11oy Space", workflow)
        self.assertIn("hf_module_drift_check.py", workflow)
        self.assertNotIn("hf_estate_canonicalize.py", workflow)
        self.assertNotIn("hf_estate_single_canonical_v2.py", workflow)
        self.assertNotIn("select newest", workflow.lower())
        self.assertNotIn("delete all clones", workflow.lower())
        self.assertNotIn("duplicate_repo(", workflow)

    def test_historical_clone_publishers_are_removed(self) -> None:
        for filename in (
            "hf_estate_upgrade.py",
            "hf_estate_canonicalize.py",
            "test_hf_estate_canonicalize.py",
            "hf_estate_single_canonical_v2.py",
            "test_hf_estate_single_canonical_v2.py",
        ):
            self.assertFalse((SCRIPT_DIR / filename).exists(), filename)


class CurrentRunReportTests(unittest.TestCase):
    def _run_finalizer(self, candidate=None, code="0"):
        workflow = (SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml").read_text()
        step = workflow.split("- name: Finalize evidence for this run attempt only", 1)[1]
        program = textwrap.dedent(step.split("python - <<'PY'\n", 1)[1].split("          PY", 1)[0])
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            historical = root / "reports/hf-estate-upgrade-latest.json"
            historical.parent.mkdir()
            historical.write_text('{"historical": "must never be republished"}')
            original = historical.read_bytes()
            target = root / "runner-temp/current-100-2.json"
            if candidate is not None:
                target.parent.mkdir()
                target.write_text(json.dumps(candidate))
            output = root / "github-output"
            environment = {
                "REPORT_PATH": str(target), "GITHUB_SHA": "a" * 40,
                "A11OY_EXPECTED_GITHUB_SHA": "b" * 40,
                "GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_OUTPUT": str(output), "ESTATE_EXIT_CODE": code,
            }
            result = subprocess.run([sys.executable, "-I", "-B", "-c", program],
                                    cwd=root, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(historical.read_bytes(), original)
            return json.loads(target.read_text()), output.read_text()

    def _current(self):
        return {
            "schema": "szl.hf-a11oy-singleton-report/v1", "generation": "a" * 40,
            "expected_github_source_sha": "b" * 40, "summary": {"error": 0},
            "canonical_flagship_space": {"sha": "c" * 40},
        }

    def test_failed_prerequisite_cannot_republish_checked_in_history(self):
        report, output = self._run_finalizer(code="")
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["summary"]["error"], 1)
        self.assertEqual(report["actions"], [])
        self.assertNotIn("historical", report)
        self.assertNotIn("canonical_flagship_space", report)
        self.assertEqual(output, "current=false\n")

    def test_foreign_generation_or_source_is_rejected(self):
        for field in ("generation", "expected_github_source_sha"):
            with self.subTest(field=field):
                candidate = self._current()
                candidate[field] = "d" * 40
                report, output = self._run_finalizer(candidate)
                self.assertEqual(report["status"], "UNVERIFIED")
                self.assertEqual(output, "current=false\n")

    def test_failed_verifier_does_not_certify_partial_report(self):
        report, output = self._run_finalizer(self._current(), code="2")
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(output, "current=false\n")

    def test_current_failure_diagnostics_are_retained_without_passing(self):
        candidate = self._current()
        candidate["summary"] = {"error": 1, "ok": 2}
        candidate["actions"] = [{"action": "canonical-route", "status": "error",
                                 "detail": "source mismatch"}]
        report, output = self._run_finalizer(candidate, code="2")
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["actions"], candidate["actions"])
        self.assertEqual(report["summary"], candidate["summary"])
        self.assertEqual(report["canonical_flagship_space"], candidate["canonical_flagship_space"])
        self.assertEqual(output, "current=false\n")

    def test_successful_current_report_preserves_measured_fields(self):
        report, output = self._run_finalizer(self._current())
        self.assertEqual(report["canonical_flagship_space"], {"sha": "c" * 40})
        self.assertEqual(report["summary"]["error"], 0)
        self.assertEqual(report["workflow_context"], {
            "run_id": "100", "run_attempt": "2", "verifier_exit_code": "0"})
        self.assertEqual(output, "current=true\n")

    def test_error_bearing_or_malformed_report_is_not_success(self):
        for candidate in ([], None, {**self._current(), "summary": {"error": 1}},
                          {**self._current(), "summary": {"error": False}}):
            with self.subTest(candidate=candidate):
                report, output = self._run_finalizer(candidate)
                self.assertEqual(report["status"], "UNVERIFIED")
                self.assertEqual(output, "current=false\n")

    def test_explicit_report_output_never_writes_checked_in_snapshot(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            historical = root / "reports/hf-estate-upgrade-latest.json"
            historical.parent.mkdir()
            historical.write_text("historical")
            target = root / "run-100-2/report.json"
            with mock.patch.dict(os.environ, {"A11OY_EXPECTED_GITHUB_SHA": "b" * 40}):
                instance = verifier.CanonicalA11oyVerifier("unit-test", "a" * 40, False, target)
            # Only local persistence runs. No provider method is invoked.
            instance.persist_report(self._current())
            self.assertEqual(json.loads(target.read_text()), self._current())
            self.assertEqual(historical.read_text(), "historical")

    def test_workflow_consumers_and_completion_use_current_attempt(self):
        workflow = (SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml").read_text()
        self.assertIn("${{ runner.temp }}/hf-canonical-a11oy-${{ github.run_id }}-${{ github.run_attempt }}.json", workflow)
        self.assertNotIn("reports/hf-estate-upgrade-latest.json", workflow)
        self.assertIn('--report-out "$REPORT_PATH"', workflow)
        self.assertIn("${{ env.REPORT_PATH }}", workflow)
        self.assertIn('cat "$REPORT_PATH"', workflow)
        self.assertIn("steps.report.outputs.current", workflow)
        self.assertIn('code="${{ steps.estate.outputs.exit_code }}"', workflow)


if __name__ == "__main__":
    unittest.main()

