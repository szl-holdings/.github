#!/usr/bin/env python3
"""Self-test for the org-wide user-visible codename sweep (Doctrine gate G5).

``codename_sweep.py`` is the CI companion to the shared ``szl_codename_gate``
scanner. It must FAIL (exit 1) when a banned codename (amaru/rosie/sentra/
jarvis) appears in user-visible text of a scanned file or a fetched URL, and
must stay green (exit 0) on clean surfaces and on internal-route-key-only uses.

A flaky/unreachable URL is, by deliberate design, a WARN (not a FAIL) so a
transient HF Space outage never flips the gate red on noise. This test pins that
documented branch too -- an unreachable surface must neither FAIL nor be counted
as a clean pass -- so a refactor can't silently turn it into a false RED.

FILE mode is network-free; the LIVE path is exercised with the shared scanner's
``scan_url`` stubbed (and ``time.sleep`` patched out), so the whole test runs
with NO network and NO token.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "codename_sweep.py")

_spec = importlib.util.spec_from_file_location("codename_sweep", _MODULE_PATH)
assert _spec and _spec.loader
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def _write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _run(argv):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return cs.main(argv)


class TestFileMode(unittest.TestCase):
    """FILE mode is network-free. ``--urls`` with no values => [] => no live
    sweep, so these exercise the real local scan path only."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="codename-sweep-test-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_visible_codename_file_fails(self):
        p = _write(self.d, "page.html",
                   "<html><body><h1>Ask rosie</h1></body></html>")
        self.assertEqual(_run([p, "--urls"]), 1)

    def test_internal_route_key_only_passes(self):
        p = _write(self.d, "page.html",
                   '<div id="rosie-panel" class="amaru"></div>'
                   '<script>var jarvis=1;</script>')
        self.assertEqual(_run([p, "--urls"]), 0)

    def test_clean_file_passes(self):
        p = _write(self.d, "clean.html",
                   "<html><body><h1>Ask the Operator</h1></body></html>")
        self.assertEqual(_run([p, "--urls"]), 0)


class TestLiveModeStubbed(unittest.TestCase):
    """LIVE path with the shared scanner stubbed -- no network, no token."""

    def setUp(self):
        self._orig = cs.G.scan_url

    def tearDown(self):
        cs.G.scan_url = self._orig

    def test_url_with_codename_fails(self):
        cs.G.scan_url = lambda url, timeout=30.0: ["rosie"]
        self.assertEqual(_run(["--urls", "https://example.test/"]), 1)

    def test_clean_url_passes(self):
        cs.G.scan_url = lambda url, timeout=30.0: []
        self.assertEqual(_run(["--urls", "https://example.test/"]), 0)

    def test_unreachable_url_warns_not_fail(self):
        """Deliberate design: an unreachable surface is a WARN, not a FAIL, so a
        flaky fetch never flips the gate red on noise."""
        def boom(url, timeout=30.0):
            raise OSError("HF 000")
        cs.G.scan_url = boom
        with mock.patch("time.sleep", lambda *_a, **_k: None):
            self.assertEqual(_run(["--urls", "https://example.test/"]), 0)

    def test_sweep_urls_counts_violations(self):
        cs.G.scan_url = lambda url, timeout=30.0: ["rosie", "amaru"]
        self.assertEqual(cs.sweep_urls(["https://a.test/"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
