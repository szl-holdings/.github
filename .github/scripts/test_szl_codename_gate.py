#!/usr/bin/env python3
"""Self-test for the shared user-visible codename gate (Doctrine gate G5).

``szl_codename_gate.py`` is the single source of truth for the G5 sweep used by
both the a11oy/killinchu apps and the CI companion ``codename_sweep.py``. It
must FAIL (exit 1) when a banned codename (amaru/rosie/sentra/jarvis) appears in
*user-visible* text, but must NOT flag the same token used only as an internal
route key (``id=`` / ``class=`` / ``data-*`` attributes or ``<script>`` bodies).

A silent weakening -- the visible-text extractor over-stripping, the banned
regex no longer matching, or the fail branch turning into a no-op -- would let a
codename reach users (or a false positive block honest internal code) while CI
stayed green. ``main()`` in FILE mode is fully network-free, so this test drives
the REAL scan path against temp files (no URLs passed) and also pins the core
helpers (scan_text / sanitize / html_visible_text / scan_html_visible) directly
so a refactor can't quietly stop catching a visible codename or start flagging
an internal key.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "szl_codename_gate.py")

_spec = importlib.util.spec_from_file_location("szl_codename_gate", _MODULE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _run_files(*paths):
    """Run gate.main() in FILE mode (no URLs => network-free); returns exit code."""
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return gate.main(list(paths))


class TestMainFileMode(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="szl-gate-test-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_visible_codename_in_html_fails(self):
        p = _write(self.d, "page.html",
                   "<html><body><h1>Ask rosie about it</h1></body></html>")
        self.assertEqual(_run_files(p), 1)

    def test_internal_route_key_only_passes(self):
        """A codename used only as id/class/data-* or inside <script> is an
        allowed internal key -> must NOT fail (false-positive safety)."""
        p = _write(self.d, "page.html",
                   '<html><body><div id="rosie-panel" class="amaru" '
                   'data-agent="sentra"></div>'
                   '<script>var jarvis = 1;</script></body></html>')
        self.assertEqual(_run_files(p), 0)

    def test_clean_html_passes(self):
        p = _write(self.d, "clean.html",
                   "<html><body><h1>Ask the Operator</h1></body></html>")
        self.assertEqual(_run_files(p), 0)

    def test_visible_codename_in_csv_fails(self):
        """Rendered-text columns of governed CSV are scanned as raw text."""
        p = _write(self.d, "surface.csv", "id,label\n1,rosie\n")
        self.assertEqual(_run_files(p), 1)

    def test_codename_in_visible_attr_fails(self):
        """A tooltip/alt cannot smuggle a codename past the gate."""
        p = _write(self.d, "tip.html", '<img alt="ask sentra" src="x.png">')
        self.assertEqual(_run_files(p), 1)


class TestCoreHelpers(unittest.TestCase):
    def test_scan_text_finds_each_token(self):
        for tok in gate.TOKENS:
            hits = [h.lower() for h in gate.scan_text("the %s agent" % tok)]
            self.assertIn(tok, hits)

    def test_scan_text_clean(self):
        self.assertEqual(gate.scan_text("YACHAY Operator CHAPAQ"), [])

    def test_sanitize_maps_to_public_roles(self):
        self.assertEqual(gate.sanitize("rosie"), "Operator")
        self.assertEqual(gate.sanitize("amaru"), "YACHAY")
        self.assertEqual(gate.sanitize("sentra"), "CHAPAQ")
        self.assertEqual(gate.sanitize("jarvis"), "Operator")

    def test_html_visible_strips_script_and_route_keys_keeps_visible(self):
        html = ('<div id="rosie">'
                '<script>amaru()</script>'
                '<img alt="sentra">'
                'Hello jarvis</div>')
        visible = gate.html_visible_text(html)
        self.assertNotIn("amaru", visible)   # inside <script> -> stripped
        self.assertNotIn("rosie", visible)   # id= route key -> stripped with tag
        self.assertIn("jarvis", visible)     # visible body text retained
        self.assertIn("sentra", visible)     # visible alt attr retained

    def test_scan_html_visible_distinguishes_visible_from_route_key(self):
        self.assertTrue(gate.scan_html_visible('<img alt="ask rosie">'))
        self.assertEqual(gate.scan_html_visible('<div id="rosie"></div>'), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
