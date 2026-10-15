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
NEXT_STEP_MARKER = "      - name: Upload SARIF report artifact\n"
ACTIONLINT_STEP_MARKER = "      - name: Install actionlint 1.7.12 (hash-checked)\n"
ACTIONLINT_NEXT_STEP_MARKER = "      - name: Run actionlint\n"
ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
ZIZMOR_WHEEL_SHA256 = "73083efc7a65e5a58f4439dd781cdcb0394b05a3750e664c7f7e414589dc49b1"
DOWNLOAD_ARTIFACT = "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333"
UPLOAD_SARIF = "github/codeql-action/upload-sarif@24c54180a607b1449ed407dd24f251e4e9147c8d"

# zizmor 1.24.1 exit statuses, observed with the released binary: 0 clean,
# 11-14 highest finding severity (11 informational, 12 low, 13 medium, 14
# high), 1 audit error, 2 usage error, 3 no inputs collected. 10 is retired
# since zizmor 1.14 and other values are reserved. SARIF mode exits 0
# whatever it finds.
CLEAN, INFORMATIONAL, LOW, MEDIUM, HIGH = 0, 11, 12, 13, 14


def step_between(source: str, marker: str, next_marker: str) -> tuple[str, str]:
    """Return (step YAML, dedented run script) for the step starting at marker."""
    start = source.index(marker)
    end = source.index(next_marker, start)
    step = source[start:end]
    run_header = "        run: |\n"
    script = textwrap.dedent(step[step.index(run_header) + len(run_header):])
    return step, script


def zizmor_step(source: str) -> tuple[str, str]:
    """Return (step YAML, dedented run script) for the Run zizmor step."""
    return step_between(source, STEP_MARKER, NEXT_STEP_MARKER)


def job_block(source: str, job: str) -> str:
    """Return one top-level job's YAML text, up to the next job or end of file."""
    start = source.index(f"\n  {job}:\n") + 1
    following = re.search(r"^  [A-Za-z0-9_-]+:\n", source[start + 1:], re.M)
    return source[start:start + 1 + following.start()] if following else source[start:]


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
        artifact = self.source[self.source.index(NEXT_STEP_MARKER):]
        self.assertIn("if: always() && hashFiles('zizmor.sarif') != ''", artifact)
        self.assertIn("name: zizmor-sarif\n", artifact)
        self.assertIn("path: zizmor.sarif\n", artifact)
        upload = job_block(self.source, "sarif-upload")
        self.assertIn(
            "if: ${{ !cancelled() && needs.zizmor.outputs.sarif_artifact_id != '' }}", upload
        )
        self.assertIn("sarif_file: zizmor.sarif\n", upload)


class WorkflowTokenBoundaryTests(unittest.TestCase):
    """Only the two-step upload job can write; scanners and installers cannot."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = {name: job_block(cls.source, name) for name in ("actionlint", "zizmor", "sarif-upload")}

    def test_jobs_are_exactly_the_three_reviewed_jobs(self) -> None:
        jobs = self.source[self.source.index("\njobs:\n"):]
        self.assertEqual(
            re.findall(r"^  ([A-Za-z0-9_-]+):\n", jobs, re.M),
            ["actionlint", "zizmor", "sarif-upload"],
        )

    def test_only_the_upload_job_holds_a_write_grant(self) -> None:
        self.assertNotIn("write-all", self.source)
        self.assertEqual(re.findall(r"^ *[a-z-]+: write *$", self.source, re.M),
                         ["      security-events: write"])
        self.assertIn("permissions:\n  contents: read\n\njobs:", self.source)
        for name in ("actionlint", "zizmor"):
            with self.subTest(job=name):
                self.assertIn("    permissions:\n      contents: read\n    ", self.jobs[name])
                self.assertNotIn("write", self.jobs[name])
        self.assertIn(
            "    permissions:\n      contents: read\n      security-events: write\n    steps:\n",
            self.jobs["sarif-upload"],
        )

    def test_upload_job_is_exactly_the_pinned_download_then_upload(self) -> None:
        upload = self.jobs["sarif-upload"]
        self.assertEqual(
            re.findall(r"^      - ", upload, re.M), ["      - ", "      - "]
        )
        self.assertEqual(
            re.findall(r"^\s*uses: (\S+)", upload, re.M), [DOWNLOAD_ARTIFACT, UPLOAD_SARIF]
        )
        self.assertIn("    needs: zizmor\n", upload)
        for marker in ("run:", "env:", "token", "secrets", "${{ github", "checkout"):
            self.assertNotIn(marker, upload, marker)
        self.assertIn("        with:\n          name: zizmor-sarif\n\n", upload)
        self.assertTrue(upload.endswith(
            "        with:\n          sarif_file: zizmor.sarif\n          category: zizmor\n"
        ))

    def test_scanner_checkouts_do_not_persist_credentials(self) -> None:
        checkouts = re.findall(r"uses: actions/checkout@\S+[^\n]*\n((?:        .*\n)*)", self.source)
        self.assertEqual(len(checkouts), 2)
        for block in checkouts:
            self.assertEqual(block, "        with:\n          persist-credentials: false\n")

    def test_zizmor_token_is_only_in_the_read_only_scan_step(self) -> None:
        self.assertEqual(self.source.count("${{ github.token }}"), 1)
        step, _ = zizmor_step(self.source)
        self.assertIn("          GITHUB_TOKEN: ${{ github.token }}\n", step)

    def test_actionlint_is_the_hash_checked_release_binary(self) -> None:
        self.assertNotIn("rhysd/actionlint@", self.source)
        step, script = step_between(self.source, ACTIONLINT_STEP_MARKER, ACTIONLINT_NEXT_STEP_MARKER)
        self.assertIn(
            "https://github.com/rhysd/actionlint/releases/download/v1.7.12/"
            "actionlint_1.7.12_linux_amd64.tar.gz", script,
        )
        self.assertIn(f'echo "{ACTIONLINT_SHA256}  actionlint_1.7.12_linux_amd64.tar.gz"', script)
        self.assertLess(script.index("sha256sum --check --strict"), script.index("tar -xzf"))
        self.assertTrue(script.startswith("set -euo pipefail\n"))

    def test_zizmor_install_is_hash_locked_without_fallback(self) -> None:
        self.assertNotIn("placeholder", self.source)
        self.assertNotIn("2>/dev/null", self.source)
        self.assertEqual(self.source.count("pip install"), 1)
        self.assertIn(f"zizmor==1.24.1 --hash=sha256:{ZIZMOR_WHEEL_SHA256}", self.source)
        self.assertIn("--no-deps --only-binary=:all: --require-hashes -r", self.source)


class ActionlintInstallExecutionTests(unittest.TestCase):
    """Execute the real install body with an inert curl stub (no network)."""

    def run_install(self, payload: bytes) -> tuple[subprocess.CompletedProcess[str], Path]:
        bash = shutil.which("bash")
        if bash is None:
            raise RuntimeError("workflow-lint execution tests require bash")
        _, script = step_between(
            WORKFLOW.read_text(encoding="utf-8"), ACTIONLINT_STEP_MARKER, ACTIONLINT_NEXT_STEP_MARKER
        )
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        work = Path(directory.name)
        stub, runner_temp = work / "bin", work / "runner-temp"
        stub.mkdir()
        runner_temp.mkdir()
        (work / "payload").write_bytes(payload)
        # The stub writes fixed bytes to the -o target, as a tampered or
        # truncated download would.
        (stub / "curl").write_text(
            "#!/usr/bin/env bash\n"
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = -o ]; then out="$2"; shift; fi\n'
            "  shift\n"
            "done\n"
            'cp "$STUB_PAYLOAD" "$out"\n',
            encoding="utf-8", newline="\n",
        )
        (stub / "curl").chmod(0o755)
        environment = os.environ.copy()
        environment.update({
            "PATH": str(stub) + os.pathsep + environment["PATH"],
            "RUNNER_TEMP": str(runner_temp),
            "STUB_PAYLOAD": str(work / "payload"),
        })
        completed = subprocess.run(
            [bash, "-c", script], cwd=work, env=environment,
            text=True, capture_output=True, check=False,
        )
        return completed, runner_temp

    def test_tampered_download_fails_before_extraction(self) -> None:
        for payload in (b"", b"not the actionlint release archive\n"):
            with self.subTest(size=len(payload)):
                result, runner_temp = self.run_install(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((runner_temp / "actionlint").exists())


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
