"""Network-free tests for the canonical A11oy release-variable binding."""

from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path
import unittest.mock

SCRIPT = Path(__file__).with_name("hf_release_variables.py")
SPEC = importlib.util.spec_from_file_location("hf_release_variables", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

SHA = "c" * 40


def manifest(**overrides):
    variables = {
        "SZL_SERVED_FRONTEND_SHA256": "a" * 64,
        "SZL_API_CONTRACT_SHA256": "b" * 64,
        "SZL_MODEL_IDENTITY": "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF@" + "d" * 40,
        "SZL_DEPLOYMENT_IDENTITY": f"SZLHOLDINGS/a11oy@{SHA}",
        "SZL_RELEASE_ID": "a11oy-" + SHA[:12],
        "SZL_RELEASE_COMMIT": SHA,
    }
    variables.update(overrides)
    return {"hf_repo": "SZLHOLDINGS/a11oy", "source_sha": SHA,
            "release_manifest": {"path": ".szl-release-manifest.json",
                                 "space_variables": variables}}


class ReleaseVariableTests(unittest.TestCase):
    def test_exact_set_admitted(self):
        self.assertEqual(len(MOD.planned_variables(manifest())), 6)

    def test_rejects_other_space_missing_or_extra(self):
        doc = manifest()
        doc["hf_repo"] = "SZLHOLDINGS/other"
        for bad in (doc, {"hf_repo": "SZLHOLDINGS/a11oy"}, manifest(SZL_EXTRA="x")):
            with self.subTest(bad=bad), self.assertRaises(MOD.ReleaseVariableError):
                MOD.planned_variables(bad)

    def test_rejects_malformed_or_unbound_values(self):
        for override in ({"SZL_SERVED_FRONTEND_SHA256": "UNKNOWN"},
                         {"SZL_MODEL_IDENTITY": "repo@main"},
                         {"SZL_RELEASE_COMMIT": "e" * 40},
                         {"SZL_DEPLOYMENT_IDENTITY": "SZLHOLDINGS/a11oy@" + "e" * 40}):
            with self.subTest(override=override), self.assertRaises(MOD.ReleaseVariableError):
                MOD.planned_variables(manifest(**override))

    def test_binds_only_differences_and_reads_back(self):
        variables = MOD.planned_variables(manifest())
        state = {name: types.SimpleNamespace(value=value) for name, value in variables.items()}
        state["SZL_RELEASE_COMMIT"] = types.SimpleNamespace(value="old")
        api = unittest.mock.Mock()

        def add(repo_id, key, value, description):
            state[key] = types.SimpleNamespace(value=value)

        api.get_space_variables.side_effect = lambda repo_id: dict(state)
        api.add_space_variable.side_effect = add
        self.assertEqual(MOD.bind(api, variables), ["SZL_RELEASE_COMMIT"])
        api.add_space_variable.assert_called_once()

    def test_readback_mismatch_fails(self):
        variables = MOD.planned_variables(manifest())
        api = unittest.mock.Mock()
        api.get_space_variables.return_value = {}
        with self.assertRaises(MOD.ReleaseVariableError):
            MOD.bind(api, variables)


if __name__ == "__main__":
    unittest.main(verbosity=2)
