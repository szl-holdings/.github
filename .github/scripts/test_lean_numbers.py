#!/usr/bin/env python3
"""Self-test for the canonical lutar-lean corpus counter.

``lean_numbers.py`` produces the authoritative declaration/axiom/sorry counts
the org's honesty surfaces cite. Its load-bearing safety contract is that it must
NOT emit a counter payload for a tree that has no ``Lutar/`` directory (a botched
clone / wrong path) — it returns exit 2 instead of silently reporting all-zeros
as if the corpus were empty. It must also count correctly so a refactor cannot
quietly under-count ``sorry`` occurrences (which would make proofs look more
complete than they are).

This runs fully offline with ``--repo-path`` (no ``--clone``) and pins:

  1. a path with no Lutar/ directory                           -> exit 2
  2. a real Lutar/ tree                                        -> exit 0 + counts
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "lean_numbers.py")

_spec = importlib.util.spec_from_file_location("lean_numbers", _MODULE_PATH)
assert _spec and _spec.loader
ln = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ln)

# A tiny but representative Lutar file: one theorem decl, one axiom, one real
# sorry, and one commented-out sorry (must NOT count as non-comment).
_LEAN = (
    "theorem foo : True := by trivial\n"
    "axiom bar : True\n"
    "theorem baz : True := by sorry\n"
    "-- this line mentions sorry but is a comment\n"
)


def _run(argv):
    saved_argv = sys.argv
    try:
        sys.argv = ["lean_numbers.py"] + argv
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return ln.main()
    finally:
        sys.argv = saved_argv


class TestLeanNumbersGuard(unittest.TestCase):
    def test_missing_lutar_dir_exit_2(self):
        """A checkout with no Lutar/ -> exit 2, never a silent all-zero payload
        that would imply the corpus is empty."""
        d = tempfile.mkdtemp(prefix="ln-test-empty-")
        try:
            self.assertEqual(_run(["--repo-path", d]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_counts_real_tree(self):
        d = tempfile.mkdtemp(prefix="ln-test-tree-")
        try:
            os.makedirs(os.path.join(d, "Lutar"))
            with open(os.path.join(d, "Lutar", "Foo.lean"), "w",
                      encoding="utf-8") as fh:
                fh.write(_LEAN)
            out = os.path.join(d, "out.json")
            rc = _run(["--repo-path", d, "--out", out])
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as fh:
                payload = json.load(fh)
            nums = payload["numbers"]
            self.assertEqual(nums["declarations"], 2)
            self.assertEqual(nums["axioms_unique"], 1)
            # raw counts the commented mention; non-comment must exclude it.
            self.assertEqual(nums["sorries_noncomment"], 1)
            self.assertGreaterEqual(nums["sorries_raw"],
                                    nums["sorries_noncomment"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
