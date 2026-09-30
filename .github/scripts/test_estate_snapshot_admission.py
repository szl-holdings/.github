"""Boundary tests for untrusted CSV admission; no attachment code is executed."""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from unittest import TestCase, main, mock

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "estate_snapshot_admission.py"
SPEC = importlib.util.spec_from_file_location("estate_admission", SCRIPT)
admission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admission)

class AdmissionTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = [self.root / f"{name}.csv" for name in ("snapshot", "consolidation", "dependencies")]
        self.headers = [admission.SNAPSHOT, admission.CONSOLIDATION, admission.DEPENDENCIES]
        self.snap = [dict(zip(admission.SNAPSHOT, (name, archived, "2026-09-29", "Python", "1", "NOASSERTION", "café")))
                     for name, archived in (("alpha", "False"), (".github", "False"), ("old", "True"))]
        self.cons = [dict(repo=r["repo"], proposed_tier="service/library", pushed=r["pushed"],
                          language=r["language"], open_issues="2", license=r["license"],
                          **{key: "True" for key in admission.FILES}) for r in self.snap[:2]]
        self.deps = [dict(ecosystem="python", package="pytest", repo=name, spec=spec)
                     for name, spec in (("alpha", ""), (".github", ">=9"))]
        self.write_all()

    def write(self, index, rows, header=None):
        with self.paths[index].open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=header or self.headers[index])
            writer.writeheader()
            writer.writerows(rows)

    def write_all(self):
        for i, rows in enumerate((self.snap, self.cons, self.deps)):
            self.write(i, rows)

    def proposed(self):
        return admission.proposal(*self.paths)

    def cli(self, output):
        argv = [value for name, path in zip(("snapshot", "consolidation", "dependencies", "output"),
                                            [*self.paths, output]) for value in (f"--{name}", str(path))]
        with contextlib.redirect_stdout(io.StringIO()) as capture:
            code = admission.main(argv)
        return code, json.loads(capture.getvalue())

    def test_byte_hash_bom_case_sensitive_license_and_proposal_limits(self):
        result = self.proposed()
        for name, path in zip(("snapshot", "consolidation", "dependencies"), self.paths):
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(result["inputs"][name]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result["inputs"][name]["bytes"], len(raw))
        repo = next(r for r in result["repositories"] if r["repo"] == "alpha")
        self.assertEqual(repo["license_metadata"], "NOASSERTION")
        self.assertTrue(repo["files"]["LICENSE"])
        self.assertIsNone(repo["canonical_source"]["sha"])
        self.assertFalse(result["production_authorization"])
        self.assertFalse(result["automatic_promotion_authorized"])

    def test_metadata_skew_and_empty_spec_are_preserved(self):
        result = self.proposed()
        self.assertEqual(len(result["metadata_skew"]), 2)
        self.assertEqual(result["metadata_skew"][0]["field"], "open_issues")
        self.assertEqual(result["unpinned_declarations"], [self.deps[0]])
        self.assertEqual(result["counts"]["spec_drift_packages"], {"python": 1})
        self.assertEqual(result["spec_drift"][0]["specs"], ["", ">=9"])
        self.deps[0]["spec"] = " \t"
        self.write(2, self.deps)
        self.assertEqual(self.proposed()["unpinned_declarations"], [self.deps[0]])

    def test_membership_missing_extra_and_case_alias_reject(self):
        for rows in (self.cons[:1], self.cons + [dict(self.cons[0], repo="old")],
                     [dict(self.cons[0], repo="Alpha"), self.cons[1]]):
            with self.subTest(rows=rows):
                self.write(1, rows)
                with self.assertRaises(ValueError):
                    self.proposed()

    def test_duplicate_repo_case_alias_reject(self):
        for index, rows in ((0, self.snap), (1, self.cons)):
            with self.subTest(index=index):
                self.write_all()
                self.write(index, rows + [dict(rows[0], repo="Alpha")])
                with self.assertRaises(ValueError):
                    self.proposed()

    def test_malformed_header_row_and_boolean_reject(self):
        for field, value, index in (("archived", "false", 0), ("LICENSE", "yes", 1),
                                    ("proposed_tier", "approved", 1), ("open_issues", "-1", 0)):
            with self.subTest(field=field):
                self.write_all()
                rows = [dict(r) for r in (self.snap if index == 0 else self.cons)]
                rows[0][field] = value
                self.write(index, rows)
                with self.assertRaises(ValueError):
                    self.proposed()
        for raw in (b"repo,archived\nalpha,False\n", b",".join(k.encode() for k in admission.SNAPSHOT) + b"\nalpha,False\n",
                    b",".join(k.encode() for k in admission.SNAPSHOT).replace(b"license", b"LICENSE") + b"\n"):
            self.write_all()
            self.paths[0].write_bytes(raw)
            with self.assertRaises(ValueError):
                self.proposed()

    def test_dependency_orphan_duplicate_and_empty_package_reject(self):
        for rows in (self.deps + [self.deps[0]], [dict(self.deps[0], repo="old")],
                     [dict(self.deps[0], repo="unknown")], [dict(self.deps[0], package=" ")],
                     [dict(self.deps[0], ecosystem="shell")]):
            with self.subTest(rows=rows):
                self.write(2, rows)
                with self.assertRaises(ValueError):
                    self.proposed()

    def test_cli_creates_once_and_rejection_never_creates_artifact(self):
        output = self.root / "proposal.json"
        code, summary = self.cli(output)
        self.assertEqual(code, 0)
        original = output.read_bytes()
        self.assertEqual(summary["proposal_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.cli(output)[0], 2)
        self.assertEqual(output.read_bytes(), original)
        self.paths[0].write_bytes(b"bad header\n")
        rejected = self.root / "rejected.json"
        code, summary = self.cli(rejected)
        self.assertEqual((code, summary["status"], summary["production_authorization"]), (2, "REJECTED", False))
        self.assertFalse(rejected.exists())

    def test_nul_size_field_row_and_empty_csv_boundaries(self):
        raw = self.paths[0].read_bytes()
        self.write(0, [dict(self.snap[0], description="x" * 16385)])
        long_field = self.paths[0].read_bytes()
        empty = b",".join(k.encode() for k in admission.SNAPSHOT) + b"\n"
        for content, bound, message in ((raw + b"\0", None, "NUL"), (raw, ("MAX_BYTES", len(raw)-1), "size"),
                                         (long_field, None, "field larger"), (raw, ("MAX_ROWS", 1), "count"),
                                         (empty, None, "empty CSV")):
            with self.subTest(bound=bound, message=message):
                self.paths[0].write_bytes(content)
                context = mock.patch.object(admission, *bound) if bound else contextlib.nullcontext()
                with context, self.assertRaisesRegex((ValueError, csv.Error), message):
                    self.proposed()

if __name__ == "__main__":
    main()
