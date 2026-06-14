#!/usr/bin/env python3
"""Self-test for the HF module-drift allowlist auto-pruner.

``hf_module_drift_prune.py`` removes an ``accepted_divergences`` entry ONLY once
the two sides are proven byte-identical, NEVER touches ignore_paths /
ignore_extensions, and is FAIL-CLOSED -- if it cannot reach a side it removes
nothing. A regression that removed a still-divergent entry would re-open the
drift hole the guard exists to catch; a regression that pruned on an unreachable
side would silently launder a transient outage into a permanent suppression.

Network is fully stubbed (the GitHub/HF tree fetchers are injected), so this
runs with NO network.
"""
from __future__ import annotations

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_module_drift_prune.py")

_spec = importlib.util.spec_from_file_location("hf_module_drift_prune", _MODULE_PATH)
assert _spec and _spec.loader
prune = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prune)


def _hf(oid=None, lfs_oid=None, size=10):
    return {"oid": oid, "lfs_oid": lfs_oid, "size": size}


class TestClassifyEntries(unittest.TestCase):
    def test_byte_identical_is_removed(self):
        accepted = {"mod.py": "known drift"}
        gh = {"mod.py": "aaa"}
        hf = {"mod.py": _hf(oid="aaa")}
        remove, keep = prune.classify_entries(accepted, gh, hf)
        self.assertEqual(remove, ["mod.py"])
        self.assertEqual(keep, {})

    def test_still_divergent_is_kept(self):
        accepted = {"mod.py": "known drift"}
        gh = {"mod.py": "aaa"}
        hf = {"mod.py": _hf(oid="bbb")}
        remove, keep = prune.classify_entries(accepted, gh, hf)
        self.assertEqual(remove, [])
        self.assertIn("mod.py", keep)

    def test_missing_on_a_side_is_kept(self):
        accepted = {"a.py": "x", "b.py": "y"}
        gh = {"a.py": "aaa"}            # b.py missing on GitHub
        hf = {"b.py": _hf(oid="bbb")}   # a.py missing on HF
        remove, keep = prune.classify_entries(accepted, gh, hf)
        self.assertEqual(remove, [])
        self.assertEqual(set(keep), {"a.py", "b.py"})

    def test_lfs_on_hf_is_kept(self):
        accepted = {"big.bin": "drift"}
        gh = {"big.bin": "aaa"}
        hf = {"big.bin": _hf(oid="aaa", lfs_oid="sha256:deadbeef")}
        remove, keep = prune.classify_entries(accepted, gh, hf)
        self.assertEqual(remove, [])
        self.assertIn("big.bin", keep)

    def test_mixed_removes_only_reconciled(self):
        accepted = {"keep.py": "still", "drop.py": "done"}
        gh = {"keep.py": "111", "drop.py": "222"}
        hf = {"keep.py": _hf(oid="999"), "drop.py": _hf(oid="222")}
        remove, keep = prune.classify_entries(accepted, gh, hf)
        self.assertEqual(remove, ["drop.py"])
        self.assertEqual(set(keep), {"keep.py"})


class TestPruneAllowlist(unittest.TestCase):
    def _allow(self):
        return {
            "_comment": "do not lose me",
            "ignore_paths": ["console/assets/**"],
            "ignore_extensions": [".png", ".map"],
            "accepted_divergences": {"a.py": "r1", "b.py": "r2"},
        }

    def test_removes_only_named_accepted_entries(self):
        out = prune.prune_allowlist(self._allow(), ["a.py"])
        self.assertEqual(out["accepted_divergences"], {"b.py": "r2"})

    def test_leaves_ignore_sections_untouched(self):
        src = self._allow()
        out = prune.prune_allowlist(src, ["a.py", "b.py"])
        self.assertEqual(out["ignore_paths"], src["ignore_paths"])
        self.assertEqual(out["ignore_extensions"], src["ignore_extensions"])
        self.assertEqual(out["_comment"], src["_comment"])
        self.assertEqual(out["accepted_divergences"], {})

    def test_preserves_key_order(self):
        out = prune.prune_allowlist(self._allow(), ["a.py"])
        self.assertEqual(list(out.keys()),
                         ["_comment", "ignore_paths", "ignore_extensions",
                          "accepted_divergences"])

    def test_does_not_mutate_input(self):
        src = self._allow()
        prune.prune_allowlist(src, ["a.py"])
        self.assertEqual(set(src["accepted_divergences"]), {"a.py", "b.py"})


class TestPlanRepoFailClosed(unittest.TestCase):
    _ALLOW = {"accepted_divergences": {"mod.py": "drift"}}

    def test_github_unreachable_prunes_nothing(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 403")

        plan = prune.plan_repo(
            "szl-holdings/a11oy", "SZLHOLDINGS/a11oy", "main", self._ALLOW,
            fetch_gh=boom, fetch_hf=lambda *a, **k: {"mod.py": _hf(oid="x")})
        self.assertEqual(plan["removed"], [])
        self.assertIsNone(plan["new_allow"])
        self.assertIn("GitHub side unreachable", plan["skipped"])

    def test_hf_unreachable_prunes_nothing(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 429")

        plan = prune.plan_repo(
            "szl-holdings/a11oy", "SZLHOLDINGS/a11oy", "main", self._ALLOW,
            fetch_gh=lambda *a, **k: {"mod.py": "x"}, fetch_hf=boom)
        self.assertEqual(plan["removed"], [])
        self.assertIsNone(plan["new_allow"])
        self.assertIn("HF side unreachable", plan["skipped"])

    def test_empty_allowlist_no_network_no_prune(self):
        called = {"n": 0}

        def counter(*a, **k):
            called["n"] += 1
            return {}

        plan = prune.plan_repo(
            "szl-holdings/a11oy", "SZLHOLDINGS/a11oy", "main",
            {"accepted_divergences": {}},
            fetch_gh=counter, fetch_hf=counter)
        self.assertEqual(plan["removed"], [])
        self.assertEqual(called["n"], 0)  # never reached out to either side

    def test_reachable_and_identical_produces_new_allow(self):
        allow = {
            "ignore_paths": ["x/**"],
            "accepted_divergences": {"mod.py": "drift"},
        }
        plan = prune.plan_repo(
            "szl-holdings/a11oy", "SZLHOLDINGS/a11oy", "main", allow,
            fetch_gh=lambda *a, **k: {"mod.py": "same"},
            fetch_hf=lambda *a, **k: {"mod.py": _hf(oid="same")})
        self.assertEqual(plan["removed"], ["mod.py"])
        self.assertEqual(plan["new_allow"]["accepted_divergences"], {})
        self.assertEqual(plan["new_allow"]["ignore_paths"], ["x/**"])


class TestSerialize(unittest.TestCase):
    def test_round_trips_and_trailing_newline(self):
        import json
        allow = {"accepted_divergences": {"a.py": "r"}}
        text = prune.serialize_allow(allow)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), allow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
