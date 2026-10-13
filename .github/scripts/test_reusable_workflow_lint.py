#!/usr/bin/env python3
"""Scanner-exit contract for the reusable workflow-lint zizmor step.

The real ``Run zizmor`` step body is executed with an inert ``zizmor`` stub on
PATH. The stub prints a fixed report and exits with a chosen status, so these
tests need no network, no token and no real scanner. They prove that a scanner
failure fails the step, that findings fail it only at or above the configured
severity, and that a clean scan passes.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-workflow-lint.yml"
STEP_MARKER = "      - name: Run zizmor\n"
NEXT_STEP_MARKER = "      - name: Upload SARIF to code-scanning\n"

# zizmor 1.24.1 exit statuses, observed with the released binary: 0 clean,
# 11-14 highest finding severity (11 informational, 12 low, 13 medium, 14
# high), 1 audit error, 2 usage error, 3 no inputs collected. 10 is retired
# since zizmor 1.14 and other values are reserved. SARIF mode exits 0
# whatever it finds.
CLEAN, INFORMATIONAL, LOW, MEDIUM, HIGH = 0, 11, 12, 13, 14


def zizmor_step(source: str) -> tuple[str, str]:
    """Return (step YAML, dedented run script) for the Run zizmor step."""
    start = source.index(STEP_MARKER)
    end = source.index(NEXT_STEP_MARKER, start)
    step = source[start:end]
    run_header = "        run: |\n"
    script = textwrap.dedent(step[step.index(run_header) + len(run_header):])
    return step, script


class ZizmorStepSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.step, cls.script = zizmor_step(cls.source)

    def test_scanner_exit_is_never_discarded(self) -> None:
        for marker in ("|| true", "|| :", "continue-on-error", "set +e", "! grep", "tee "):
            self.assertNotIn(marker, self.step, marker)
        self.assertNotIn("continue-on-error", self.source)
        self.assertTrue(self.script.startswith("set -euo pipefail\n"))

    def test_both_scanner_runs_record_their_own_status(self) -> None:
        self.assertIn(
            "zizmor --format=sarif .github/workflows > zizmor.sarif || sarif_status=$?",
            self.script,
        )
        self.assertIn(
            "zizmor --format=plain .github/workflows || plain_status=$?",
            self.script,
        )
        self.assertEqual(len(re.findall(r"^\s*zizmor ", self.script, re.M)), 2)

    def test_findings_are_still_uploaded_when_the_step_fails(self) -> None:
        upload = self.source[self.source.index(NEXT_STEP_MARKER):]
        self.assertIn("if: always() && hashFiles('zizmor.sarif') != ''", upload)
        self.assertIn("sarif_file: zizmor.sarif", upload)


class ZizmorStepExecutionTests(unittest.TestCase):
    """Execute the real step body with an inert zizmor stub."""

    @classmethod
    def setUpClass(cls) -> None:
        # Resolve bash from PATH explicitly so a Windows host never picks up a
        # different launcher through the CreateProcess search order.
        cls.bash = shutil.which("bash")
        if cls.bash is None:
            raise RuntimeError("workflow-lint execution tests require bash")
        _, cls.script = zizmor_step(WORKFLOW.read_text(encoding="utf-8"))

    def run_step(
        self,
        *,
        plain: int,
        sarif: int = 0,
        fail_on_warn: str = "false",
        write_sarif: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            stub = work / "bin"
            stub.mkdir()
            (work / ".github/workflows").mkdir(parents=True)
            (stub / "zizmor").write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$STUB_CALLS"\n'
                'case "$1" in\n'
                '  --format=sarif)\n'
                '    if [ "$STUB_WRITE_SARIF" = true ]; then\n'
                "      printf '%s\\n' '{\"version\":\"2.1.0\",\"runs\":[]}'\n"
                "    fi\n"
                '    exit "$STUB_SARIF_STATUS";;\n'
                '  --format=plain)\n'
                "    printf '%s\\n' 'inert zizmor stub report'\n"
                '    exit "$STUB_PLAIN_STATUS";;\n'
                "esac\n"
                'echo "unexpected zizmor arguments: $*" >&2\n'
                "exit 64\n",
                encoding="utf-8", newline="\n",
            )
            (stub / "zizmor").chmod(0o755)
            environment = os.environ.copy()
            for name in ("GH_TOKEN", "GITHUB_TOKEN", "ZIZMOR_GITHUB_TOKEN"):
                environment.pop(name, None)
            environment.update({
                "PATH": str(stub) + os.pathsep + environment["PATH"],
                "GITHUB_TOKEN": "inert-token-not-a-credential",
                "FAIL_ON_WARN": fail_on_warn,
                "STUB_SARIF_STATUS": str(sarif),
                "STUB_PLAIN_STATUS": str(plain),
                "STUB_WRITE_SARIF": "true" if write_sarif else "false",
                "STUB_CALLS": str(work / "calls.txt"),
            })
            completed = subprocess.run(
                [self.bash, "-c", self.script], cwd=work, env=environment,
                text=True, capture_output=True, check=False,
            )
            calls_path = work / "calls.txt"
            calls = (calls_path.read_text(encoding="utf-8").splitlines()
                     if calls_path.exists() else [])
            return completed, calls

    def assert_passes(self, **arguments: object) -> None:
        result, calls = self.run_step(**arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("::error::", result.stdout)
        self.assertEqual(
            calls,
            ["--format=sarif .github/workflows", "--format=plain .github/workflows"],
        )

    def assert_fails(self, expected_message: str, **arguments: object) -> None:
        result, _ = self.run_step(**arguments)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected_message, result.stdout)
        self.assertNotIn("zizmor passed", result.stdout)

    def test_clean_scan_passes_in_both_modes(self) -> None:
        for mode in ("false", "true"):
            with self.subTest(fail_on_warn=mode):
                self.assert_passes(plain=CLEAN, fail_on_warn=mode)

    def test_high_findings_fail_in_both_modes(self) -> None:
        for mode in ("false", "true"):
            with self.subTest(fail_on_warn=mode):
                self.assert_fails("at or above the failure threshold (exit 14",
                                  plain=HIGH, fail_on_warn=mode)

    def test_medium_findings_fail_only_when_warnings_are_failures(self) -> None:
        self.assert_passes(plain=MEDIUM, fail_on_warn="false")
        self.assert_fails("at or above the failure threshold (exit 13, threshold 13)",
                          plain=MEDIUM, fail_on_warn="true")

    def test_findings_below_medium_pass_in_both_modes(self) -> None:
        for status in (INFORMATIONAL, LOW):
            for mode in ("false", "true"):
                with self.subTest(status=status, fail_on_warn=mode):
                    self.assert_passes(plain=status, fail_on_warn=mode)

    def test_plain_scanner_failure_fails_even_when_warnings_are_tolerated(self) -> None:
        # 1 audit error, 2 usage error, 3 no inputs collected, 10 retired,
        # 126/127 missing or unrunnable binary, 137 killed, 255 unknown.
        for status in (1, 2, 3, 9, 10, 15, 126, 127, 137, 255):
            with self.subTest(status=status):
                self.assert_fails(f"zizmor --format=plain exited {status}: the scanner failed",
                                  plain=status)

    def test_sarif_scanner_failure_fails_even_when_the_plain_run_is_clean(self) -> None:
        for status in (1, 2, 3, 127):
            with self.subTest(status=status):
                self.assert_fails(f"zizmor --format=sarif exited {status}: the scanner failed",
                                  plain=CLEAN, sarif=status)

    def test_sarif_finding_status_is_not_a_scanner_failure(self) -> None:
        # If a later zizmor applies finding exit codes to SARIF output, the
        # verdict still comes from the plain run's severity.
        self.assert_passes(plain=MEDIUM, sarif=MEDIUM, fail_on_warn="false")
        self.assert_fails("at or above the failure threshold (exit 14",
                          plain=HIGH, sarif=HIGH)

    def test_missing_sarif_report_fails(self) -> None:
        self.assert_fails("wrote no SARIF report", plain=CLEAN, write_sarif=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
