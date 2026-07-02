#!/usr/bin/env python3
"""Self-test for the honesty-overclaim sweep guard.

``overclaim_sweep.py`` fails the run when a governed Markdown surface (README,
PROVEN_FORMULAS, STATUS, ...) overclaims Λ-uniqueness or declares Conjecture 1
proven. Its grep regexes are kept byte-identical to the reusable guard's, so a
silent weakening (e.g. an over-broad SAFE qualifier, or the fail branch turning
into a no-op) would let an overclaim land green org-wide.

``--local`` mode is fully network-free, so this test exercises the REAL
``grep_overclaims`` / ``scan_local`` path against temp checkouts and pins:

  1. a governed surface with an overclaim                      -> exit 1
  2. the same sentence carrying a SAFE qualifier (conditional) -> exit 0
  3. a clean checkout                                          -> exit 0

It also directly pins ``grep_overclaims`` on all three overclaim categories
(A/B/C) so a future regex edit cannot quietly stop matching one, and a lockstep
test asserts rule C's regexes appear verbatim in the reusable guard's inline
python3 so the org sweep and the per-repo guard can never diverge on rule C.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "overclaim_sweep.py")

_spec = importlib.util.spec_from_file_location("overclaim_sweep", _MODULE_PATH)
assert _spec and _spec.loader
ocs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ocs)

# An unconditional Λ-uniqueness claim with NO safe qualifier (matches _A_RE).
_OVERCLAIM_A = "The aggregator Λ is uniquely determined by the axioms."
# A Conjecture-1-proven claim (matches _B_RE), no excluding qualifier.
_OVERCLAIM_B = "Conjecture 1 is proved by the construction in section 4."
# Same A-sentence made governance-safe with a conditional qualifier.
_SAFE_LINE = "Conditional on IA, Λ is uniquely determined (Theorem U, modulo ≈Λ)."
# A generic security/correctness overclaim absolute (matches _C_TRIGGER_RE) with
# no negation/qualifier -> must fire rule C.
_OVERCLAIM_C = "Our medical-record chain is tamper-proof and unbreakable."
# The honest form, soft-wrapped so the negation ("not") lands on the PREVIOUS
# line and the trigger word ("tamper-proof") on the next -> must NOT fire.
_SAFE_C_WRAP = "Refusals are tamper-evident, not\ntamper-proof — auditable rules."
# fire/no-fire matrix for rule C: (should_fire, text). Multi-line entries
# exercise the previous-line negation window; the honest negatives include bare
# "guarantee", bare "100%", and a "| Guarantee |" table header — all used
# honestly org-wide and therefore deliberately NOT triggers.
_GENERIC_MATRIX = [
    (True, "Our receipts are tamper-proof and unbreakable."),
    (True, "The system is 100% secure against all attacks."),
    (True, "Signatures are mathematically guaranteed to be unforgeable."),
    (True, "It is impossible to forge a valid receipt."),
    (True, "military-grade encryption keeps you 100% safe."),
    (True, "Our new design is\ntamper-proof by construction."),
    (False, "Receipts are tamper-evident, not tamper-proof."),
    (False, _SAFE_C_WRAP),
    (False, "Trust is never 100%; the ceiling is 0.97."),
    (False, "This is an integrity guarantee, NOT a safety guarantee."),
    (False, "The AP guarantee is preserved under partition."),
    (False, "split-conformal marginal-coverage guarantee (NOT Hoeffding)."),
    (False, "| Property | Guarantee | Maturity |"),
]


def _checkout(readme_text):
    d = tempfile.mkdtemp(prefix="ocs-test-")
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme_text + "\n")
    return d


def _run_local(root):
    """Run ``ocs.main()`` in --local mode (no network); returns exit code."""
    saved_argv = sys.argv
    try:
        sys.argv = ["overclaim_sweep.py", "--local", root,
                    "--allowlist", os.path.join(_HERE, "no-such-allowlist.json")]
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return ocs.main()
    finally:
        sys.argv = saved_argv


class TestOverclaimSweepGuard(unittest.TestCase):
    def test_lambda_uniqueness_caught(self):
        d = _checkout(_OVERCLAIM_A)
        try:
            self.assertEqual(_run_local(d), 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_conjecture1_proven_caught(self):
        d = _checkout(_OVERCLAIM_B)
        try:
            self.assertEqual(_run_local(d), 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_safe_qualifier_passes(self):
        """A conditional/Theorem-U-cited sentence is governance-safe -> exit 0.
        Guards against an over-eager regex flagging honest prose."""
        d = _checkout(_SAFE_LINE)
        try:
            self.assertEqual(_run_local(d), 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_clean_checkout_passes(self):
        d = _checkout("This project ships verifiable governance receipts.")
        try:
            self.assertEqual(_run_local(d), 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_grep_overclaims_matches_both_categories(self):
        """Pin the core matcher directly so a regex refactor can't silently stop
        catching either overclaim category."""
        hits_a = ocs.grep_overclaims(_OVERCLAIM_A)
        self.assertTrue(any(h["type"] == "lambda_uniqueness" for h in hits_a))
        hits_b = ocs.grep_overclaims(_OVERCLAIM_B)
        self.assertTrue(any(h["type"] == "conjecture1_proven" for h in hits_b))
        self.assertEqual(ocs.grep_overclaims(_SAFE_LINE), [])

    # ------------------------------------------------------------------ #
    # Rule C — generic security/correctness overclaim absolutes.
    # ------------------------------------------------------------------ #
    def test_generic_overclaim_caught(self):
        d = _checkout(_OVERCLAIM_C)
        try:
            self.assertEqual(_run_local(d), 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_generic_overclaim_wrapped_negation_passes(self):
        """A soft-wrapped honest negation ('tamper-EVIDENT, not' on the previous
        line, 'tamper-proof' on the next) must NOT fire — the exemption consults
        the previous line, so markdown wrapping cannot turn honest prose red."""
        d = _checkout(_SAFE_C_WRAP)
        try:
            self.assertEqual(_run_local(d), 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_generic_matrix(self):
        """Pin fire/no-fire across precise positives and honest negatives so a
        future regex edit cannot silently over- or under-match rule C."""
        for should_fire, s in _GENERIC_MATRIX:
            hits = ocs.grep_overclaims(s)
            fired = any(h["type"] == "generic_overclaim" for h in hits)
            self.assertEqual(fired, should_fire, f"rule C misfired on: {s!r}")

    def test_rule_c_patterns_locked_to_reusable_guard(self):
        """Lockstep: the compiled rule-C trigger/negation patterns must appear
        VERBATIM in reusable-overclaim-guard.yml's inline python3, so the org
        sweep and the per-repo guard can never silently diverge on rule C."""
        yml_path = os.path.join(_HERE, "..", "workflows",
                                "reusable-overclaim-guard.yml")
        with open(yml_path, "r", encoding="utf-8") as fh:
            yml = fh.read()
        self.assertIn(ocs._C_TRIGGER_RE.pattern, yml,
                      "rule-C TRIGGER regex drifted from the reusable guard")
        self.assertIn(ocs._C_NEGATION_RE.pattern, yml,
                      "rule-C NEGATION regex drifted from the reusable guard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
