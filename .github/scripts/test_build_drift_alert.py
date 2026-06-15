#!/usr/bin/env python3
"""Self-test for the code-security-drift alert message builder.

Task #745 added a scheduled-only ntfy alert to ``code-security-drift.yml`` whose
message-building logic lived only inside inline bash/jq. A future edit could
silently produce an empty or malformed alert and we'd only find out during a
real incident. ``build_drift_alert.py`` extracted that logic; this stdlib
``unittest`` (no pytest, no network) locks its contract:

  exit 1 + report.errors  -> names the offending repo(s) + the re-attach fix hint
  exit 2 / missing report  -> says "COULD NOT COMPLETE"
  neither case drops its ``\\n\\n`` separators (the bug a prior revision had)

Stdlib only, so CI needs only a github-owned ``actions/setup-python`` to run it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "build_drift_alert.py")

_spec = importlib.util.spec_from_file_location("build_drift_alert", _MODULE_PATH)
assert _spec and _spec.loader
bda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bda)


def _write(tmp, name, content):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


class TestDriftMessage(unittest.TestCase):
    """exit 1 + a real report -> names the offending repo(s) + fix hint."""

    SAMPLE_ERRORS = [
        "szl-holdings/platform: NOT enforced under canonical config 252588 "
        "(attached elsewhere: 251743)",
        "szl-holdings/freshly-created: new repo with NO code-security config "
        "attached",
    ]

    def _report(self):
        return {"errors": list(self.SAMPLE_ERRORS), "warnings": []}

    def test_drift_text_names_each_offending_repo(self):
        text = bda.build_text(1, self._report())
        for err in self.SAMPLE_ERRORS:
            self.assertIn(err, text)
        # Both repo names must survive the join.
        self.assertIn("szl-holdings/platform", text)
        self.assertIn("szl-holdings/freshly-created", text)

    def test_drift_text_has_head_separator_and_fix_hint(self):
        text = bda.build_text(1, self._report())
        # Headline, blank line, then the errors, then a blank line, then Fix.
        self.assertIn(
            "Code-security config drift detected in szl-holdings "
            "(config 252588).\n\n",
            text,
        )
        self.assertIn("\n\nFix: re-attach config 252588", text)
        self.assertIn("code_security_allowlist.json", text)

    def test_drift_errors_joined_with_newline(self):
        text = bda.build_text(1, self._report())
        self.assertIn(
            self.SAMPLE_ERRORS[0] + "\n" + self.SAMPLE_ERRORS[1], text
        )

    def test_drift_text_is_not_empty(self):
        # The whole point: a drift alert must never be blank.
        text = bda.build_text(1, self._report())
        self.assertTrue(text.strip())
        self.assertGreater(len(text), 80)


class TestCouldNotCompleteMessage(unittest.TestCase):
    """exit 2 / missing report -> says COULD NOT COMPLETE, keeps \\n\\n."""

    def test_exit_2_says_could_not_complete(self):
        text = bda.build_text(2, None)
        self.assertIn("COULD NOT COMPLETE", text)
        self.assertIn("exit 2", text)
        self.assertIn("SZL_GITHUB_TOKEN", text)

    def test_exit_1_with_missing_report_falls_back(self):
        # exit 1 but no usable report -> could-not-complete, NOT an empty drift.
        text = bda.build_text(1, None)
        self.assertIn("COULD NOT COMPLETE", text)
        self.assertIn("exit 1", text)

    def test_detail_separated_by_double_newline(self):
        # This is the regression the task calls out: command substitution once
        # stripped the trailing newlines and glued the detail onto the sentence.
        drift_output = (
            "INFO: walking org repos\n"
            "  ERROR: GitHub API 403 while reading defaults\n"
            "  ERROR: token lacks admin:org scope\n"
        )
        text = bda.build_text(2, None, drift_output)
        self.assertIn("coverage cannot be confirmed.\n\n", text)
        # The grepped+stripped detail lines follow the blank line.
        self.assertIn(
            "\n\nERROR: GitHub API 403 while reading defaults\n"
            "ERROR: token lacks admin:org scope",
            text,
        )

    def test_no_detail_means_no_trailing_separator(self):
        text = bda.build_text(2, None, "no matching lines here\n")
        self.assertTrue(text.endswith("coverage cannot be confirmed."))
        self.assertNotIn("coverage cannot be confirmed.\n\n", text)

    def test_detail_grep_keeps_last_five_lines_left_stripped(self):
        lines = "".join(f"   error number {i}\n" for i in range(1, 9))
        text = bda.build_text(2, None, lines)
        # tail -n 5 -> errors 4..8, and leading whitespace stripped.
        self.assertIn("error number 4\nerror number 8".split("\n")[0], text)
        self.assertIn("error number 8", text)
        self.assertNotIn("error number 3", text)
        self.assertNotIn("   error number", text)  # left-strip applied


class TestPayload(unittest.TestCase):
    """The emitted payload is valid JSON, prefixed, and newline-preserving."""

    def test_payload_is_valid_json_with_prefix(self):
        payload = bda.build_payload(1, {"errors": ["szl-holdings/x: drift"]})
        # Round-trip through JSON exactly as the relay receives it.
        wire = json.dumps(payload, ensure_ascii=False)
        back = json.loads(wire)
        self.assertTrue(back["text"].startswith("\U0001F6A8 [szl-holdings] "))
        self.assertIn("szl-holdings/x: drift", back["text"])
        # Newlines must survive the JSON encode/decode.
        self.assertIn("\n\n", back["text"])

    def test_emit_text_matches_build_text(self):
        report = {"errors": ["szl-holdings/y: drift"]}
        self.assertEqual(
            bda.build_payload(1, report)["text"],
            bda.PREFIX + bda.build_text(1, report),
        )


class TestCli(unittest.TestCase):
    """End-to-end through main() reading real files (still network-free)."""

    def test_main_payload_from_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rpt = _write(tmp, "report.json",
                         json.dumps({"errors": ["szl-holdings/z: drift"]}))
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = bda.main(["--exit-code", "1", "--report", rpt])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("szl-holdings/z: drift", payload["text"])
            self.assertTrue(payload["text"].startswith("\U0001F6A8"))

    def test_main_could_not_complete_when_report_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = _write(tmp, "out.txt", "  ERROR: boom auth\n")
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = bda.main([
                    "--exit-code", "2",
                    "--report", os.path.join(tmp, "nope.json"),
                    "--drift-output", out,
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("COULD NOT COMPLETE", payload["text"])
            self.assertIn("\n\nERROR: boom auth", payload["text"])

    def test_main_unparseable_report_does_not_emit_empty_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            rpt = _write(tmp, "bad.json", "{ this is not json")
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = bda.main(["--exit-code", "1", "--report", rpt])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("COULD NOT COMPLETE", payload["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
