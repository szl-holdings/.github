#!/usr/bin/env python3
"""Network-free tests for the lockfile scan and coverage pager.

The scheduled org sweep (lockfile-registry-check.yml) does more than fail red on
a coverage gap: it PAGES a human via ntfy when a repo NEWLY enters the
coverage-gap state, and stays silent on a standing gap (no spam) and when
coverage is clean. That rising-edge + dedup logic now lives in pure helpers in
lockfile_registry_check.py instead of inline in the workflow YAML, precisely so
it can be locked here.

This test pins, with no network access:
  * the actual reusable Bash step rejects case-varied and JSON-escaped hosts
    in committed blobs, and cannot replace source evidence with worktree bytes.
  * compute_new_gaps() fires on a NEW gap, is silent on a STANDING gap, silent
    when all coverage is OK, and never crashes on a malformed/empty report.
  * the gap-state round-trip (--write-gap-state / --read-gap-state) is the dedup
    baseline and is read from its OWN file, INDEPENDENT of the scan report — so a
    failed report commit can never resurrect a standing gap into a re-alert.
  * the --new-gaps CLI contract the workflow `eval`s stays shell-eval-safe.

A future refactor that silently breaks the pager (stops firing on a real gap, or
starts spamming a standing one) makes one of these assertions fail.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "lockfile_registry_check.py")

sys.path.insert(0, HERE)
import lockfile_registry_check as lf  # noqa: E402


def _report(*gap_repos, ok_repos=()):
    """A minimal coverage report: each name in gap_repos is a GAP, each in
    ok_repos is OK."""
    coverage = []
    for r in gap_repos:
        coverage.append({
            "repo": r,
            "status": "GAP",
            "gaps": [f"missing caller workflow .github/workflows/lockfile-registry.yml"],
        })
    for r in ok_repos:
        coverage.append({"repo": r, "status": "OK", "gaps": []})
    return {"schema": "szl.lockfile_registry/v1", "coverage": coverage}


class ComputeNewGaps(unittest.TestCase):
    def test_silent_when_all_ok(self):
        new, lines = lf.compute_new_gaps(_report(ok_repos=["a", "b"]), "")
        self.assertEqual(new, [])
        self.assertEqual(lines, [])

    def test_fires_on_new_gap(self):
        new, lines = lf.compute_new_gaps(_report("widget", ok_repos=["a"]), "")
        self.assertEqual(new, ["widget"])
        self.assertTrue(any(l.startswith("widget: ") for l in lines))

    def test_silent_on_standing_gap(self):
        # widget was already alerted last sweep -> no NEW gap, but it still shows
        # up in the human-readable description of current gaps.
        new, lines = lf.compute_new_gaps(_report("widget"), "widget")
        self.assertEqual(new, [])
        self.assertTrue(any("widget" in l for l in lines))

    def test_only_the_newly_added_repo_fires(self):
        new, _ = lf.compute_new_gaps(_report("widget", "gadget"), "widget")
        self.assertEqual(new, ["gadget"])

    def test_resolved_gap_can_realert_if_it_recurs(self):
        # prev had widget; it is OK now -> nothing new. State should drop it.
        new, _ = lf.compute_new_gaps(_report(ok_repos=["widget"]), "widget")
        self.assertEqual(new, [])
        # later it recurs and the baseline (now empty) lets it page again.
        new2, _ = lf.compute_new_gaps(_report("widget"), "")
        self.assertEqual(new2, ["widget"])

    def test_malformed_report_is_safe(self):
        for bad in ({}, {"coverage": None}, {"coverage": ["junk", 5]}, {"coverage": [{}]}):
            new, lines = lf.compute_new_gaps(bad, "")
            self.assertEqual(new, [])
            self.assertEqual(lines, [])

    def test_prev_accepts_iterable_or_csv(self):
        rpt = _report("widget", "gadget")
        self.assertEqual(lf.compute_new_gaps(rpt, "widget")[0], ["gadget"])
        self.assertEqual(lf.compute_new_gaps(rpt, ["widget"])[0], ["gadget"])


class _CLI:
    """Run lockfile_registry_check.py in a subprocess; return stdout (stripped)."""
    @staticmethod
    def run(*args):
        p = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, timeout=30,
        )
        assert p.returncode == 0, f"exit {p.returncode}: {p.stderr}"
        return p.stdout.strip()


class GapStateRoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.report = os.path.join(self.dir, "report.json")
        self.state = os.path.join(self.dir, "state.json")

    def _write_report(self, *gaps, ok=()):
        with open(self.report, "w") as fh:
            json.dump(_report(*gaps, ok_repos=ok), fh)

    def test_read_missing_state_is_empty(self):
        self.assertEqual(_CLI.run("--read-gap-state", self.state), "")

    def test_write_then_read_roundtrip(self):
        self._write_report("widget", "gadget")
        out = _CLI.run("--write-gap-state", self.state, "--report", self.report)
        self.assertEqual(out, "gadget,widget")  # sorted CSV
        self.assertEqual(_CLI.run("--read-gap-state", self.state), "gadget,widget")
        with open(self.state) as fh:
            st = json.load(fh)
        self.assertEqual(st["schema"], "szl.lockfile_gap_state/v1")
        self.assertEqual(st["alerted_gap_repos"], ["gadget", "widget"])

    def test_baseline_is_independent_of_the_report(self):
        # The dedup baseline (#1200) must come from the STATE file, not the report.
        # Persist a clean state, then point the report at a fresh gap: read-gap-state
        # must still reflect the state file, proving a stale/failed report commit
        # cannot corrupt the dedup memory.
        self._write_report(ok=["widget"])
        _CLI.run("--write-gap-state", self.state, "--report", self.report)
        self.assertEqual(_CLI.run("--read-gap-state", self.state), "")
        # report now shows a gap, but the committed baseline is unchanged.
        self._write_report("widget")
        self.assertEqual(_CLI.run("--read-gap-state", self.state), "")

    def test_new_gaps_cli_is_eval_safe_and_correct(self):
        self._write_report("widget", "gadget")
        out = _CLI.run("--new-gaps", "--report", self.report, "--prev", "widget")
        lines = dict(l.split("=", 1) for l in out.splitlines())
        self.assertIn("NEW_GAPS", lines)
        self.assertIn("GAP_DESC", lines)
        # eval the emitted assignments the way the workflow does (bash); the
        # shlex-quoted RHS must round-trip safely.
        got = subprocess.run(
            ["bash", "-c", f'eval "{out}"; printf "%s" "$NEW_GAPS"'],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, "gadget")  # widget was standing, gadget new

    def test_new_gaps_silent_when_clean(self):
        self._write_report(ok=["widget"])
        out = _CLI.run("--new-gaps", "--report", self.report, "--prev", "")
        lines = dict(l.split("=", 1) for l in out.splitlines())
        self.assertEqual(lines["NEW_GAPS"], "''")  # shlex.quote("") == "''"


class ReusableWorkflowScan(unittest.TestCase):
    """Execute the actual reusable Bash step on committed offline fixtures."""

    @classmethod
    def setUpClass(cls):
        workflow = Path(HERE).parent / "workflows/reusable-lockfile-registry-check.yml"
        lines = workflow.read_text(encoding="utf-8").splitlines()
        starts = [i for i, line in enumerate(lines) if line == "        run: |"]
        if len(starts) != 1:
            raise AssertionError("Expected one literal scan step in the reusable workflow")
        block = []
        for line in lines[starts[0] + 1:]:
            if line and not line.startswith("          "):
                break
            block.append(line)
        cls.scan = textwrap.dedent("\n".join(block))
        if not cls.scan.strip():
            raise AssertionError("The reusable scan step must not be empty")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lockfile-workflow-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Offline Fixture", "-c",
             "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", *args],
            cwd=self.root, check=True, capture_output=True, text=True, timeout=10,
        )

    def commit(self, files):
        for path, content in files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "-qm", "offline fixture")

    def run_scan(self):
        return subprocess.run(
            ["bash", "-c", self.scan], cwd=self.root, capture_output=True,
            text=True, timeout=10, env={**os.environ, "LC_ALL": "C"},
        )

    def test_public_registry_is_clean_in_every_supported_format(self):
        self.commit({"nested/" + name: "https://registry.npmjs.org/example.tgz"
                     for name in lf.LOCKFILE_NAMES})
        result = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanning 4 lockfile(s)", result.stdout)

    def test_internal_hosts_reject_regardless_of_case_or_lockfile_format(self):
        for host in ("package-firewall.replit.local", "Package-Firewall.RePlIt.LoCaL",
                     "PACKAGE-FIREWALL.REPLIT.LOCAL"):
            for name in lf.LOCKFILE_NAMES:
                with self.subTest(host=host, lockfile=name):
                    # Each revision contains one distinct poisoned committed blob.
                    for path in self.root.glob("nested/*"):
                        path.unlink()
                    self.commit({"nested/" + name: "https://" + host + "/npm/example.tgz"})
                    result = self.run_scan()
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("::error file=nested/" + name, result.stdout)

    def test_sparse_checkout_cannot_hide_a_committed_poisoned_lockfile(self):
        self.commit({"nested/package-lock.json": "https://mirror.RePlIt.LoCaL/npm/a.tgz"})
        (self.root / "nested/package-lock.json").unlink()
        result = self.run_scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_json_string_decoding_matches_the_org_scanner(self):
        encoded_host = "".join("\\u%04x" % ord(char) for char in "mirror.replit.local")
        cases = [
            (r'{"resolved":"https://mirror.\u0072eplit.local/a"}', True),
            (r'{"resolved":"https://mirror.\u0052ePlIt.LoCaL/a"}', True),
            (r'{"resolved":"https:\/\/mirror\u002ereplit\u002elocal/a"}', True),
            ('{"resolved":"https://' + encoded_host + '/a"}', True),
            (r'{"resolved":"https://mirror.replit.local/a","resolved":"https://registry.npmjs.org/a"}', True),
            (r'{"resolved":"https://mirror.replit.local/\q"}', True),
            ('{"resolved":"https://mirror.replit.local/a', True),
            (r'{"resolved":"https://mirror.\\u0072eplit.local/a"}', False),
            (r'{"resolved":"https:\/\/registry.\u006epmjs.org/a"}', False),
            (r'{"description":"literal\\backslash and \"quoted\" text","resolved":"https://registry.npmjs.org/a"}', False),
            ('{"description":"Unicode café","resolved":"https://registry.npmjs.org/a"}', False),
        ]
        for content, blocked in cases:
            with self.subTest(content=content):
                self.assertEqual(bool(lf.scan_text(content)), blocked)
                self.commit({"package-lock.json": content})
                result = self.run_scan()
                self.assertEqual(result.returncode, int(blocked), result.stdout + result.stderr)

    def test_scanner_runtime_failure_is_not_a_clean_result(self):
        self.commit({"package-lock.json": "https://registry.npmjs.org/a.tgz"})
        result = subprocess.run(
            ["bash", "-c", "python3() { return 23; }\n" + self.scan],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertNotIn("✓ No lockfile", result.stdout)

    def test_clean_worktree_cannot_replace_the_committed_evidence(self):
        self.commit({"package-lock.json": "https://mirror.replit.local/npm/a.tgz"})
        (self.root / "package-lock.json").write_text("https://registry.npmjs.org/a.tgz")
        self.assertEqual(self.run_scan().returncode, 1)

    def test_untracked_lockfile_is_not_committed_evidence(self):
        self.commit({"package-lock.json": "https://registry.npmjs.org/a.tgz"})
        (self.root / "yarn.lock").write_text("https://mirror.replit.local/npm/a.tgz")
        result = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanning 1 lockfile(s)", result.stdout)

    def test_unusual_path_is_not_split_or_executed(self):
        path = "a space\n$(false)/package-lock.json"
        self.commit({path: "https://mirror.replit.local/npm/a.tgz"})
        self.assertEqual(self.run_scan().returncode, 1)

    def test_missing_commit_fails_closed(self):
        result = self.run_scan()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("No lockfiles found", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
