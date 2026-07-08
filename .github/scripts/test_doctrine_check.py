#!/usr/bin/env python3
"""Self-test for the line-wrap-tolerant SZL doctrine check.

`doctrine_check.py` is the testable port of the org-wide honesty gate. Its whole
reason to exist is that the previous inline-bash gate was LINE-BASED: a cosmetic
reflow that split an honest sentence across two lines (trigger on one line,
qualifier on the next) produced a FALSE-POSITIVE doctrine failure org-wide (the
`szl_kc_atlas.py` incident that needed a11oy PR #768 just to re-flow text).

This network-free self-test PINS the contract so a future refactor can neither
(a) reintroduce the line-based fragility, nor (b) weaken an invariant into a
false-green no-op. Following the org convention (test_overclaim_sweep.py etc.),
it drives the REAL scan_local() path against synthetic fixtures.

Contract pinned:
  1. A genuine UNQUALIFIED overclaim  -> FAIL (gate is substantive).
  2. The SAME honest sentence, but soft-wrapped so the qualifier lands on an
     ADJACENT line (the exact break that took down the org)  -> PASS.
  3. A clean tree  -> PASS.
  4. The verified-L2 (a11oy/killinchu) repo-scoped banner exemption still works
     AND still fails a bare L2 claim on a non-verified repo.
  5. `COPY . .` Dockerfile invariant still fires.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "doctrine_check.py")
_spec = importlib.util.spec_from_file_location("doctrine_check", _MODULE_PATH)
assert _spec and _spec.loader
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)


def _write(root: str, rel: str, text: str) -> None:
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def _invs(root: str, repo: str = ""):
    return {v[0] for v in dc.scan_local(root, repo=repo)}


class DoctrineWrapTolerance(unittest.TestCase):

    def test_unqualified_lambda_theorem_overclaim_fails(self):
        """A bare 'Λ is a proven theorem' with NO qualifier anywhere -> Inv2 fail."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "claim.md",
                   "The aggregator Λ is a proven theorem and always will be.\n"
                   "This paragraph says nothing else about it.\n")
            self.assertIn("Inv2", _invs(d),
                          "an unqualified Λ-theorem overclaim must still FAIL")

    def test_softwrapped_honest_sentence_passes(self):
        """THE REGRESSION: honest sentence wrapped so the qualifier lands on the
        NEXT line. The old line-based grep FALSE-POSITIVED here and broke the org.
        The window-scoped check must PASS it."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "szl_kc_atlas.py",
                   "# no bare 'Λ...theorem' claim without the qualifier: it is\n"
                   "# not asserted as a proven theorem here; Λ remains\n"
                   "# Conjecture 1 (never a theorem, advisory only).\n")
            self.assertNotIn("Inv2", _invs(d),
                             "a soft-wrapped honest Λ sentence must PASS — a "
                             "cosmetic reflow must never break the org again")

    def test_orpo_negative_training_data_exempt(self):
        """INV2 training-data exemption: the ORPO generator and the box run-doc
        intentionally embed the banned 'Λ ... proven theorem' string as the
        REJECTED half of contrastive preference pairs. These negative-training
        fixtures must be exempt from INV2 (only)."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "training/build_orpo.py",
                   '# ORPO rejected/accepted preference-pair generator\n'
                   'REJECTED = "Yes, Λ-uniqueness is a fully proven theorem."\n'
                   'ACCEPTED = "No. Λ = Conjecture 1, never a theorem."\n')
            _write(d, "training/box/RUN_ON_BOX.md",
                   'Smoke test the refusal:\n'
                   'ollama run szl-sovereign-qwen "Is Lambda a theorem?"\n')
            self.assertNotIn("Inv2", _invs(d, repo="szl-holdings/a11oy"),
                             "intentional ORPO negative-training data must be "
                             "exempt from INV2")

    def test_negative_control_overclaim_outside_training_still_fails(self):
        """NEGATIVE CONTROL: the SAME bare overclaim in a non-training file must
        still FAIL — the exemption is path-scoped, it does NOT weaken INV2."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "serve_notes.md",
                   "Yes, Λ-uniqueness is a fully proven theorem.\nEnd.\n")
            self.assertIn("Inv2", _invs(d, repo="szl-holdings/a11oy"),
                          "a real overclaim outside training/ must still FAIL")

    def test_training_exemption_is_tight_not_whole_dir(self):
        """The allowlist is tight: an overclaim in a training/ file that is NOT
        an ORPO negative-data generator (e.g. build_seed.py) still FAILS, so the
        exemption cannot be abused to hide overclaims anywhere under training/."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "training/build_seed.py",
                   'X = "Λ is a proven theorem, full stop."\n')
            self.assertIn("Inv2", _invs(d, repo="szl-holdings/a11oy"),
                          "non-ORPO training files are NOT exempt from INV2")

    def test_inline_honest_sentence_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "ok.md",
                   "Λ = Conjecture 1, never a theorem (advisory only).\n")
            self.assertNotIn("Inv2", _invs(d))

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md", "# A11oy\nHonest labels. Doctrine v11 LOCKED.\n")
            self.assertEqual(_invs(d), set())

    def test_doctrine_version_drift_wrapped_qualifier_passes(self):
        """Inv1: a v12 mention that is ADDITIVE/roadmap must pass even when the
        'additive' qualifier is wrapped onto an adjacent line."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "notes.md",
                   "We discuss doctrine v12 here as a purely\n"
                   "proposed, additive roadmap item — not promoted.\n")
            self.assertNotIn("Inv1", _invs(d))

    def test_doctrine_version_drift_unqualified_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.md", "We are now on doctrine v12 in production.\n"
                                "Full stop.\n")
            self.assertIn("Inv1", _invs(d))

    def test_slsa_l3_claim_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "x.md", "This image has achieved SLSA L3 in production.\nWe are proud of it.\n")
            self.assertIn("Inv3-L3", _invs(d))

    def test_slsa_l2_verified_repo_banner_passes(self):
        """a11oy/killinchu may carry the honest 'SLSA L1 + L2' banner."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "footer.md", "Posture: SLSA L1 + L2 (roadmap).\n")
            self.assertNotIn("Inv3-L2", _invs(d, repo="szl-holdings/a11oy"))

    def test_slsa_l2_nonverified_repo_bare_claim_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "footer.md", "This repo is SLSA L2.\nDone.\n")
            self.assertIn("Inv3-L2", _invs(d, repo="szl-holdings/some-lib"))

    def test_banned_compliance_claim_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "compliance.md", "We are FedRAMP High authorized.\nToday.\n")
            self.assertIn("Inv5", _invs(d))

    def test_banned_compliance_negated_wrapped_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "compliance.md",
                   "We are NOT pursuing FedRAMP High; it is\n"
                   "explicitly out of scope for this release.\n")
            self.assertNotIn("Inv5", _invs(d))

    def test_dockerfile_copy_dot_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "Dockerfile", "FROM scratch\nCOPY . .\n")
            self.assertIn("Inv6", _invs(d))

    def test_main_exit_codes(self):
        """The exit-code contract: 0 clean, 1 on violation (mirrors org guards)."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "README.md", "Doctrine v11 LOCKED. Λ = Conjecture 1.\n")
            self.assertEqual(dc.main(["--local", d]), 0)
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.md", "Λ is a proven theorem.\nEnd.\n")
            self.assertEqual(dc.main(["--local", d]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
