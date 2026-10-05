#!/usr/bin/env python3
"""Offline faults for dataset-card admission; no credentials or provider calls."""
import ast
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("hf_dataset_card_admission.py")
SPEC = importlib.util.spec_from_file_location("hf_dataset_card_admission", SCRIPT)
ADMISSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADMISSION)
REPO_ROOT = Path(__file__).resolve().parents[2]


class DatasetCardAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = REPO_ROOT / "huggingface" / "dataset-cards"
        shutil.copytree(source, self.root / "huggingface" / "dataset-cards")
        self.path = self.root / ADMISSION.MANIFEST_PATH
        self.manifest = json.loads(self.path.read_bytes())

    def write_manifest(self, manifest=None):
        self.path.write_text(json.dumps(manifest or self.manifest, indent=2) + "\n", encoding="utf-8")

    def target(self, repo_id="SZLHOLDINGS/test-results"):
        return next(item for item in self.manifest["targets"] if item["repo_id"] == repo_id)

    def reject(self):
        with self.assertRaises((ADMISSION.AdmissionError, OSError, ValueError, RecursionError)):
            ADMISSION.validate(self.root)

    def test_exact_two_cards_restore_baselines_and_preserve_complete_manifests(self):
        report = ADMISSION.validate(self.root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual({item["repo_id"]: item["retained_non_readme_files"] for item in report["targets"]},
                         {"SZLHOLDINGS/test-results": 14, "SZLHOLDINGS/SZLHOLDINGS": 6})
        self.assertTrue(all(item["baseline_hash_restored"] for item in report["targets"]))
        self.assertIs(report["effects_allowed"], False)
        self.assertEqual(report["provider_publication"], "NOT_ATTEMPTED")
        self.assertEqual(report["authority_status"], "PENDING_PROTECTED_OWNER_MERGE")

    def test_effect_and_authority_states_never_pass(self):
        original = copy.deepcopy(self.manifest)
        for key, values in {
            "effects_allowed": [True, 0, "false", None],
            "authority_status": ["ADMITTED", "READY", False],
            "provider_publication": ["PUBLISHED", "READY", False],
            "scope": ["publish", False],
            "proposal_governance_base": ["main", "d" * 40, False],
            "proposed_source_repository": ["szl-holdings/hatun-mcp", None],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.manifest = copy.deepcopy(original)
                    self.manifest[key] = value
                    self.write_manifest()
                    self.reject()

    def test_target_membership_types_and_immutable_refs_fail_closed(self):
        original = copy.deepcopy(self.manifest)
        variants = [[], original["targets"][:1], original["targets"] + original["targets"][:1],
                    [original["targets"][0], original["targets"][0]], {}, None]
        for value in variants:
            with self.subTest(targets=value):
                self.manifest = copy.deepcopy(original)
                self.manifest["targets"] = value
                self.write_manifest()
                self.reject()
        for key, values in {
            "repo_type": ["space", "model", "datasets", False],
            "repo_id": ["OTHER/test-results", "SZLHOLDINGS/README", None, []],
            "observed_hub_revision": ["main", "4d5de7b", "a" * 40, False],
            "change": ["replace-body", None],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.manifest = copy.deepcopy(original)
                    self.target()[key] = value
                    self.write_manifest()
                    self.reject()

    def test_extra_or_missing_fields_are_not_ignored(self):
        original = copy.deepcopy(self.manifest)
        for mutate in [lambda m: m.update(upload=True), lambda m: m.pop("effects_allowed"),
                       lambda m: m["targets"][0].update(token="fixture-value"),
                       lambda m: m["targets"][0].pop("observed_readme")]:
            self.manifest = copy.deepcopy(original)
            mutate(self.manifest)
            self.write_manifest()
            self.reject()

    def test_json_duplicates_nonfinite_and_wrong_root_are_refused(self):
        for raw in ['{"schema":1,"schema":2}', '{"schema":NaN}', '[1,2]',
                    '{"value":Infinity}', '{"value":-Infinity}', '{']:
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                self.reject()

    def test_baseline_and_candidate_hash_or_boolean_size_drift_is_refused(self):
        original = copy.deepcopy(self.manifest)
        for field, value in [("sha256", "a" * 64), ("git_blob_oid", "a" * 40),
                             ("size_bytes", True), ("path", "status.json")]:
            self.manifest = copy.deepcopy(original)
            self.target()["observed_readme"][field] = value
            self.write_manifest()
            self.reject()
        for field, value in [("candidate_sha256", "a" * 64), ("candidate_sha256", False),
                             ("candidate_size_bytes", True), ("candidate_size_bytes", 1)]:
            self.manifest = copy.deepcopy(original)
            self.target()[field] = value
            self.write_manifest()
            self.reject()

    def test_wrong_paths_cannot_select_other_local_files(self):
        original = copy.deepcopy(self.manifest)
        for value in ["../README.md", "/README.md", "C:/Users/example/README.md",
                      "huggingface\\dataset-cards\\README.md", "README.md", "./README.md"]:
            with self.subTest(path=value):
                self.manifest = copy.deepcopy(original)
                self.target()["candidate_path"] = value
                self.write_manifest()
                self.reject()

    def test_rehashed_extra_prose_or_yaml_still_fails_baseline_restoration(self):
        target = self.target()
        card = self.root / target["candidate_path"]
        original = card.read_bytes()
        for changed in [original + b"\nREADY\n", original.replace(b"train", b"test", 1),
                        original.replace(b"harness_runs.jsonl", b"PROMOTION_READINESS_AUDIT.json", 1),
                        original.replace(b"license: apache-2.0", b"license: mit", 1)]:
            with self.subTest(card=ADMISSION.sha256(changed)):
                card.write_bytes(changed)
                target["candidate_sha256"] = ADMISSION.sha256(changed)
                target["candidate_size_bytes"] = len(changed)
                self.write_manifest()
                self.reject()

    def test_viewer_flag_must_be_first_front_matter_insertion(self):
        target = self.target("SZLHOLDINGS/SZLHOLDINGS")
        card = self.root / target["candidate_path"]
        original = card.read_bytes()
        changed = original.replace(b"viewer: false\n", b"", 1) + b"---\nviewer: false\n"
        card.write_bytes(changed)
        target["candidate_sha256"] = ADMISSION.sha256(changed)
        target["candidate_size_bytes"] = len(changed)
        self.write_manifest()
        self.reject()

    def test_rehashed_dropped_added_or_changed_preserved_files_still_fail(self):
        original = copy.deepcopy(self.manifest)
        for mutate in [lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0])),
                       lambda rows: rows[0].update(git_blob_oid="a" * 40),
                       lambda rows: rows[0].update(size_bytes=True),
                       lambda rows: rows[0].update(path="../elsewhere"),
                       lambda rows: rows[0].update(path="README.md")]:
            self.manifest = copy.deepcopy(original)
            target = self.target()
            mutate(target["retained_files"])
            target["retained_files_sha256"] = ADMISSION.sha256(ADMISSION.canonical(target["retained_files"]))
            self.write_manifest()
            self.reject()

    def test_missing_and_oversized_inputs_are_not_success(self):
        card = self.root / self.target()["candidate_path"]
        original = card.read_bytes()
        card.unlink()
        self.reject()
        card.write_bytes(b"x" * (ADMISSION.MAX_CARD_BYTES + 1))
        self.reject()
        card.write_bytes(original)
        self.path.write_bytes(b" " * (ADMISSION.MAX_MANIFEST_BYTES + 1))
        self.reject()

    def test_symlink_input_is_refused_when_platform_allows_fixture(self):
        card = self.root / self.target()["candidate_path"]
        original = card.read_bytes()
        alternative = self.root / "retained-card.md"
        alternative.write_bytes(original)
        card.unlink()
        try:
            card.symlink_to(alternative)
        except OSError:
            self.skipTest("platform did not permit a local symlink fixture")
        self.reject()

    def test_cli_reports_pass_or_typed_blocked_without_creating_receipts(self):
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        output = io.StringIO()
        with redirect_stdout(output):
            code = ADMISSION.main(["--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "PASS")
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()))
        self.path.write_text("broken", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            code = ADMISSION.main(["--root", str(self.root)])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"], "DATASET_CARD_ADMISSION_INVALID")
        self.assertIs(result["effects_allowed"], False)

    def test_large_integer_parse_failure_has_typed_blocked_cli_result(self):
        self.path.write_bytes(b'{"value":' + b'1' * 5000 + b'}')
        self.assertLess(self.path.stat().st_size, ADMISSION.MAX_MANIFEST_BYTES)
        output = io.StringIO()
        with redirect_stdout(output):
            code = ADMISSION.main(["--root", str(self.root)])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"], "DATASET_CARD_ADMISSION_INVALID")
        self.assertIs(result["effects_allowed"], False)

    def test_validator_imports_only_offline_standard_library_and_has_no_apply_switch(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(item.name for item in node.names)
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertLessEqual(modules, {"argparse", "hashlib", "json", "pathlib", "re", "stat", "sys"})
        self.assertNotIn("--apply", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
