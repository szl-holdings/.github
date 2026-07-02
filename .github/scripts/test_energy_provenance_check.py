#!/usr/bin/env python3
"""Self-test for the org-wide energy-provenance honesty guard.

``energy_provenance_check.py`` fails the run when committed receipt / attestation
DATA (JSON / JSONL / DSSE payloads) violates the doctrine's load-bearing promise
**measured-or-UNAVAILABLE** — a joule is a real measurement or it is honestly
absent, NEVER fabricated. Two narrow, key-based invariants:

  E1  {joules, measured}     : a numeric ``joules`` REQUIRES ``measured == true``.
  E2  {measured_joules,label}: a numeric ``measured_joules`` must NOT carry a
                               ``label`` starting "UNAVAILABLE".

``--local`` mode is fully network-free, so this test drives the REAL
``check_obj`` / ``scan_text`` / ``scan_local`` / ``main`` path against temp
checkouts and pins:

  1. a clean checkout (measured joules, honest UNAVAILABLE)      -> exit 0
  2. a fabricated joule (numeric joules, measured:false)         -> exit 1
  3. a numeric measured_joules under an UNAVAILABLE label         -> exit 1
  4. a fabricated joule hidden in a base64 DSSE payload           -> exit 1
  5. a fabricated joule on ONE line of a .jsonl ledger           -> exit 1
  6. an allowlisted tamper-demo fixture                          -> exit 0

It also pins ``check_obj`` directly on the E1/E2 edge cases (0-joule is still a
fabrication; a bool ``joules`` is not numeric; ``joules`` without ``measured``
is deliberately NOT flagged; an honest ``measured:true`` / null-joule / MEASURED
label are silent) so a future logic weakening cannot quietly turn the guard into
an always-green no-op.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "energy_provenance_check.py")
_spec = importlib.util.spec_from_file_location("energy_provenance_check", _MODULE_PATH)
assert _spec and _spec.loader
epc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(epc)

_NONEXISTENT_ALLOWLIST = os.path.join(tempfile.gettempdir(), "epc_no_such_allowlist.json")


def _run_local(root, allowlist=_NONEXISTENT_ALLOWLIST):
    """Run main() in --local mode over ``root``; return (exit_code, stdout)."""
    buf = io.StringIO()
    argv = ["energy_provenance_check.py", "--local", root, "--allowlist", allowlist]
    import sys
    old = sys.argv
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(buf):
            rc = epc.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def _write(root, name, obj_or_text):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if isinstance(obj_or_text, str):
            fh.write(obj_or_text)
        else:
            fh.write(json.dumps(obj_or_text))
    return path


# --------------------------------------------------------------------------- #
# check_obj — the single source of truth for E1 / E2 (pin the edges directly).
# --------------------------------------------------------------------------- #
class TestInvariantEngine(unittest.TestCase):
    def _viol(self, obj):
        out = []
        epc.check_obj(obj, "$", out)
        return out

    # --- E1 {joules, measured} --- #
    def test_e1_fabricated_joule_fires(self):
        v = self._viol({"joules": 100.0, "measured": False})
        self.assertTrue(any(r == "E1" for (_, r, _) in v), v)

    def test_e1_zero_joule_is_still_a_fabrication(self):
        v = self._viol({"joules": 0, "measured": False})
        self.assertTrue(any(r == "E1" for (_, r, _) in v), v)

    def test_e1_measured_true_is_silent(self):
        self.assertEqual(self._viol({"joules": 41.8, "measured": True}), [])

    def test_e1_null_joule_unmeasured_is_silent(self):
        self.assertEqual(self._viol({"joules": None, "measured": False}), [])

    def test_e1_unavailable_string_is_silent(self):
        self.assertEqual(self._viol({"joules": "UNAVAILABLE", "measured": False}), [])

    def test_e1_requires_both_keys(self):
        # joules without a measured key is ambiguous -> deliberately NOT flagged.
        self.assertEqual(self._viol({"joules": 12.3}), [])

    def test_e1_bool_joule_is_not_numeric(self):
        # True is not a joule measurement; must not be treated as numeric.
        self.assertEqual(self._viol({"joules": True, "measured": False}), [])

    def test_e1_nested_is_found(self):
        v = self._viol({"receipt": {"energy": {"joules": 5, "measured": False}}})
        self.assertTrue(any(r == "E1" for (_, r, _) in v), v)

    # --- E2 {measured_joules, label} --- #
    def test_e2_figure_under_unavailable_label_fires(self):
        v = self._viol({"measured_joules": 5.5, "label": "UNAVAILABLE (no exporter)"})
        self.assertTrue(any(r == "E2" for (_, r, _) in v), v)

    def test_e2_honest_unavailable_is_silent(self):
        self.assertEqual(self._viol({"measured_joules": None, "label": "UNAVAILABLE"}), [])

    def test_e2_measured_label_is_silent(self):
        self.assertEqual(self._viol({"measured_joules": 12.3, "label": "MEASURED-NVML"}), [])

    # --- DSSE base64 payload recursion --- #
    def test_dsse_payload_recursion_fires(self):
        inner = {"e": {"joules": 9.9, "measured": False}}
        payload = base64.b64encode(json.dumps(inner).encode()).decode()
        v = self._viol({"payloadType": "application/vnd.szl.receipt+json",
                        "payload": payload})
        self.assertTrue(any(r == "E1" for (_, r, _) in v), v)
        self.assertTrue(any("payload~b64" in loc for (loc, _, _) in v), v)


# --------------------------------------------------------------------------- #
# main() --local — end-to-end exit-code contract.
# --------------------------------------------------------------------------- #
class TestLocalMode(unittest.TestCase):
    def test_clean_checkout_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "measured.json", {"joules": 41.8, "measured": True})
            _write(d, "unmeasured.json", {"joules": None, "measured": False})
            _write(d, "e2.json", {"measured_joules": None, "label": "UNAVAILABLE"})
            rc, _ = _run_local(d)
            self.assertEqual(rc, 0)

    def test_fabricated_joule_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.json", {"joules": 100.0, "measured": False})
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("E1", out)

    def test_unavailable_label_conflict_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.json", {"measured_joules": 5.5, "label": "UNAVAILABLE"})
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("E2", out)

    def test_dsse_payload_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            inner = {"e": {"joules": 9.9, "measured": False}}
            payload = base64.b64encode(json.dumps(inner).encode()).decode()
            _write(d, "dsse.json",
                   {"payloadType": "app/vnd.dsse+json", "payload": payload})
            rc, _ = _run_local(d)
            self.assertEqual(rc, 1)

    def test_jsonl_line_level_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "ledger.jsonl",
                   '{"joules": 1.0, "measured": true}\n'
                   '{"joules": 2.0, "measured": false}\n')
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("L2", out)

    def test_allowlisted_tamper_demo_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "fixtures/tamper_demo.json",
                   {"joules": 100.0, "measured": False})
            allow = os.path.join(d, "allow.json")
            with open(allow, "w", encoding="utf-8") as fh:
                json.dump({"ignore_paths": ["fixtures/tamper_demo.json"]}, fh)
            rc, _ = _run_local(d, allowlist=allow)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
