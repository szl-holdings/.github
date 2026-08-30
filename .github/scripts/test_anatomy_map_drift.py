#!/usr/bin/env python3
"""Self-test for the SZL anatomy-map cross-surface drift guard.

``anatomy_map_drift.py`` fails the run when the single honest anatomy map
diverges across its three surfaces (a11oy /console, killinchu /elite, the
SZLHOLDINGS/anatomy HF Space) on the canonical locked-8 ladder
{F1,F4,F7,F11,F12,F18,F19,F22}, the Λ=Conjecture-1 honesty label, or the
shared capability ladder.

These fixtures drive the REAL ``evaluate()`` path network-free, with fixture
text trimmed from the actual surfaces, and pin that the guard:

  1. PASSES when all three surfaces are honest and in sync          (exit 0)
  2. FAILS when one surface swaps a locked formula id (F22 -> F23)  (exit 1)
  3. FAILS when one surface drops the Λ=Conjecture-1 label          (exit 1)
  4. FAILS when the capability ladder is edited on ONE side only    (exit 1)
  5. FAILS when the marker block is missing entirely                (exit 1)

It also pins the pure extractors so a future refactor can't quietly stop
matching the locked ladder, the Λ label, the capability list, or the markers
(which would turn the guard into an always-green no-op).
"""
from __future__ import annotations

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "anatomy_map_drift.py")
_spec = importlib.util.spec_from_file_location("anatomy_map_drift", _MODULE_PATH)
assert _spec and _spec.loader
amd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amd)


# --- The byte-shared marker block (trimmed, faithful to the real surfaces). --
def _block(*, putnam="0 REAL / 10 DEMO / 2 OPEN", ns_footer=True,
           locked="F1, F4, F7, F11, F12, F18, F19, F22",
           math_f="F1, F4, F7, F11, F12, F18, F19, F22 (locked-8)",
           lambda_label="\\u039b uniqueness = <b>Conjecture 1</b>",
           drop_math_cap=False, drop_lambda=False):
    caps = [
        "{k:'rag', n:'Agentic Lineage-Aware RAG', s:'LIVE', p:'prose', e:'szl_rag.py', f:'P3, P1'}",
        "{k:'khipu', n:'Khipu DAG + BFT consensus', s:'LIVE', p:'prose', e:'szl_khipu.py', f:'F4, F7, F22 (locked) \\u00b7 B2 quorum'}",
        "{k:'receipts', n:'Receipt store', s:'LIVE', p:'prose', e:'YAWAR bus', f:'F1, F18 (locked) \\u00b7 P1, P5'}",
    ]
    if not drop_math_cap:
        caps.append(
            "{k:'math', n:'Math \\u00b7 AP-12 generator + Putnam benchmark', s:'LIVE-GATED', "
            f"p:'Putnam 2025: {putnam} (doctrine v11). The locked-8 ladder and \\u039b=Conjecture 1 are unchanged.', "
            f"e:'/api/math', f:'{math_f}'}}")
    footer = ("+'Static honest snapshot \\u00b7 NS='+esc(NS)+' \\u00b7 no fabricated live pills.</div>';"
              if ns_footer else
              "+'Static honest snapshot \\u00b7no fabricated live pills.</div>';")
    block = (
        "/* anatomy-map-tab-patch :: SZL Anatomy \u2014 single honest map ::\n"
        "   8 LOCKED formulas {F1,F4,F7,F11,F12,F18,F19,F22}; \u039b = Conjecture 1. */\n"
        "(function(){\n"
        "  var NS=(window.__rd_ns||'a11oy');\n"
        "  var CAPS=[" + ",\n".join(caps) + "];\n"
        "  function render(host){ var h='';\n"
        "    h+='Honesty: <b>8 LOCKED</b> kernel-verified formulas {" + locked + "}; "
        + lambda_label + " (advisory, never a pass/fail oracle).';\n"
        "    " + footer + "\n"
        "  }\n"
        "  V.anatomymap={ title:'Anatomy Map' };\n"
        "})();\n"
        "/* end anatomy-map-tab-patch */"
    )
    if drop_lambda:
        # Simulate a surface that quietly relabels Λ as settled everywhere
        # (comment header, render label, and capability prose).
        block = block.replace("Conjecture 1", "settled (proven)")
    return block


# --- The HF static deck (trimmed, faithful to data.js + index.html). --------
def _hf(*, locked="'F1', 'F4', 'F7', 'F11', 'F12', 'F18', 'F19', 'F22'",
        lambda_label="Unconditional \u039b stays Conjecture 1."):
    return (
        "const KERNEL = { locked_sha:'c7c0ba17',\n"
        "  locked_proven: [" + locked + "],\n"
        "  cut2:'CUT-2 lambda_unique_of_separable. " + lambda_label + "' };\n"
        "/* index.html */\n"
        "<span class=vf-tier-locked>8 LOCKED-proven (kernel-verified)</span> "
        "{F1, F4, F7, F11, F12, F18, F19, F22} @ c7c0ba17.\n"
        "<strong>\u039b = Conjecture 1.</strong> Unconditional uniqueness stays open.\n"
    )


def _surfaces(a11oy=None, killinchu=None, hf=None):
    return [
        {"id": "a11oy-console", "extract": "marker_block",
         "text": a11oy if a11oy is not None else _block()},
        {"id": "killinchu-elite", "extract": "marker_block",
         "text": killinchu if killinchu is not None
         else _block(putnam="0 REAL / 11 DEMO / 1 OPEN", ns_footer=False)},
        {"id": "hf-anatomy", "extract": "invariant_scan",
         "text": hf if hf is not None else _hf()},
    ]


class TestExtractors(unittest.TestCase):
    def test_marker_block_found_and_bounded(self):
        b = amd.extract_marker_block("noise\n" + _block() + "\ntrailing")
        self.assertIsNotNone(b)
        self.assertTrue(b.startswith("anatomy-map-tab-patch ::"))
        self.assertTrue(b.rstrip().endswith("end anatomy-map-tab-patch"))

    def test_marker_block_absent(self):
        self.assertIsNone(amd.extract_marker_block("no markers here"))

    def test_locked_groups_canonical(self):
        groups = amd.parse_locked_groups(_block())
        self.assertTrue(groups)
        canon = tuple(sorted(amd.CANONICAL_LOCKED, key=lambda f: int(f[1:])))
        for g in groups:
            self.assertEqual(g, canon)

    def test_locked_groups_ignore_three_id_subset(self):
        # khipu's "F4, F7, F22 (locked)" must NOT be read as a locked-8 decl.
        groups = amd.parse_locked_groups(
            "f:'F4, F7, F22 (locked)' and 8 LOCKED {F1, F4, F7, F11, F12, F18, F19, F22}")
        self.assertEqual(len(groups), 1)

    def test_lambda_conjecture_detected_both_forms(self):
        self.assertTrue(amd.has_lambda_conjecture("\\u039b uniqueness = Conjecture 1"))
        self.assertTrue(amd.has_lambda_conjecture("\u039b = Conjecture 1"))
        self.assertTrue(amd.has_lambda_conjecture("Unconditional \u039b stays Conjecture 1"))
        self.assertFalse(amd.has_lambda_conjecture("locked formulas are proven"))

    def test_capabilities_parsed(self):
        caps = amd.parse_capabilities(_block())
        keys = [k for (k, _s, _f) in caps]
        self.assertEqual(keys, ["rag", "khipu", "receipts", "math"])


class TestEvaluate(unittest.TestCase):
    def test_passes_when_in_sync(self):
        report, code = amd.evaluate(_surfaces())
        self.assertEqual(code, 0, report["findings"])
        self.assertTrue(report["ok"])

    def test_fails_on_swapped_locked_id(self):
        # Mutate just the a11oy side: swap F22 -> F23 in the locked ladder.
        bad = _block(locked="F1, F4, F7, F11, F12, F18, F19, F23",
                     math_f="F1, F4, F7, F11, F12, F18, F19, F23 (locked-8)")
        report, code = amd.evaluate(_surfaces(a11oy=bad))
        self.assertEqual(code, 1)
        self.assertTrue(any("locked-formula set drift" in f for f in report["findings"]))
        self.assertTrue(any("disagrees ACROSS surfaces" in f for f in report["findings"]))

    def test_fails_on_missing_lambda_label(self):
        bad = _block(drop_lambda=True)
        report, code = amd.evaluate(_surfaces(killinchu=bad))
        self.assertEqual(code, 1)
        self.assertTrue(any("Λ = Conjecture 1" in f or "honesty label is" in f
                            for f in report["findings"]))

    def test_fails_on_capability_ladder_edit(self):
        # Drop the math capability on the killinchu side only.
        bad = _block(putnam="0 REAL / 11 DEMO / 1 OPEN", ns_footer=False,
                     drop_math_cap=True)
        report, code = amd.evaluate(_surfaces(killinchu=bad))
        self.assertEqual(code, 1)
        self.assertTrue(any("capability ladder drift" in f for f in report["findings"]))

    def test_fails_on_missing_block(self):
        report, code = amd.evaluate(_surfaces(a11oy="no anatomy block at all"))
        self.assertEqual(code, 1)
        self.assertTrue(any("marker block not found" in f for f in report["findings"]))

    def test_fails_on_hf_locked_drift(self):
        bad_hf = _hf(locked="'F1', 'F4', 'F7', 'F11', 'F12', 'F18', 'F19', 'F23'")
        report, code = amd.evaluate(_surfaces(hf=bad_hf))
        self.assertEqual(code, 1)
        self.assertTrue(any("hf-anatomy" in f and "locked-formula set drift" in f
                            for f in report["findings"]))

    def test_expected_variance_does_not_trip(self):
        # The documented NS-footer drop + the volatile Putnam DEMO/OPEN tally are
        # NOT part of the fingerprint -> must NOT cause a false red.
        report, code = amd.evaluate(_surfaces(
            a11oy=_block(putnam="0 REAL / 10 DEMO / 2 OPEN", ns_footer=True),
            killinchu=_block(putnam="0 REAL / 11 DEMO / 1 OPEN", ns_footer=False)))
        self.assertEqual(code, 0, report["findings"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
