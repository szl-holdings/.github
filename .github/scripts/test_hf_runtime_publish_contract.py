"""Network-free admission tests for the canonical A11oy publisher invocation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("hf_runtime_publish_contract.py")
SPEC = importlib.util.spec_from_file_location("hf_runtime_publish_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def publication(**overrides: str) -> dict[str, str]:
    env = {
        "WORKFLOW_REPOSITORY": "szl-holdings/.github",
        "WORKFLOW_SHA": "1" * 40,
        "CALLER_REPOSITORY": "szl-holdings/a11oy",
        "EVENT_SHA": "2" * 40,
        "EVENT_REF": "refs/heads/main",
        "EVENT_NAME": "workflow_dispatch",
        "CONTRACT_ONLY": "false",
        "RUNTIME_IDENTITY": "true",
        "HF_REPO": "SZLHOLDINGS/a11oy",
        "DEPLOY_REF": "2" * 40,
        "REQUIRE_TIP": "true",
        "DOCKERFILE": "Dockerfile",
        "SOURCE_REVISION_FILE": "",
        "SOURCE_VARIABLE": "SZL_GIT_SHA",
        "SOURCE_PROBE": "/api/build-info",
        "INCLUDE_README": "true",
        "PRUNE": "true",
        "RESTART": "false",
        "WAIT_RUNNING": "1200",
    }
    env.update(overrides)
    return env


RELEASE = {
    "RELEASE_MANIFEST_FILE": ".szl-release-manifest.json",
    "RELEASE_SERVED_ARTIFACT": "console/index.html",
    "RELEASE_API_CONTRACT": "docs/api-contract.md",
    "RELEASE_MODEL_IDENTITY_ARGS": "A11OY_ALLOY_GGUF_REPO@A11OY_ALLOY_GGUF_REV",
}


class RuntimePublishContractTests(unittest.TestCase):
    def test_canonical_publication_without_release_manifest(self) -> None:
        self.assertEqual(CONTRACT.validate(publication()), "CANONICAL_A11OY_PUBLICATION")

    def test_canonical_publication_with_release_manifest(self) -> None:
        self.assertEqual(CONTRACT.validate(publication(**RELEASE)), "CANONICAL_A11OY_PUBLICATION")

    def test_release_inputs_require_the_manifest_file(self) -> None:
        for name in ("RELEASE_SERVED_ARTIFACT", "RELEASE_API_CONTRACT", "RELEASE_MODEL_IDENTITY_ARGS"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                CONTRACT.validate(publication(**{name: RELEASE[name]}))

    def test_release_manifest_inputs_are_bounded(self) -> None:
        bad = (
            {"RELEASE_MANIFEST_FILE": "release-manifest.json"},
            {"RELEASE_SERVED_ARTIFACT": "../etc/passwd"},
            {"RELEASE_SERVED_ARTIFACT": ""},
            {"RELEASE_API_CONTRACT": "/abs/path"},
            {"RELEASE_MODEL_IDENTITY_ARGS": "repo@rev"},
            {"RELEASE_MODEL_IDENTITY_ARGS": "ONLY_ONE"},
        )
        for override in bad:
            with self.subTest(override=override), self.assertRaises(ValueError):
                CONTRACT.validate(publication(**{**RELEASE, **override}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
