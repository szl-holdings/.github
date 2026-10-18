"""Network-free admission tests for the dedicated seismic Space publisher."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("hf_seismic_publish_contract.py")
SPEC = importlib.util.spec_from_file_location("hf_seismic_publish_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def publication() -> dict[str, str]:
    return {
        "WORKFLOW_REPOSITORY": "szl-holdings/.github",
        "WORKFLOW_SHA": "1" * 40,
        "CALLER_REPOSITORY": "szl-holdings/szl-seismic-review",
        "EVENT_SHA": "2" * 40,
        "EVENT_REF": "refs/heads/main",
        "EVENT_NAME": "workflow_dispatch",
        "CONTRACT_ONLY": "false",
        "HF_REPO": "SZLHOLDINGS/szl-seismic-review",
        "DEPLOY_REF": "2" * 40,
        "REQUIRE_TIP": "true",
        "DOCKERFILE": "Dockerfile",
        "SOURCE_REVISION_FILE": "SOURCE_REVISION",
        "SOURCE_VARIABLE": "SZL_SOURCE_REVISION",
        "SOURCE_PROBE": "/api/build-info",
        "INCLUDE_README": "true",
        "SMOKE_PATHS": json.dumps(CONTRACT.SMOKE_PATHS),
        "PRUNE": "false",
        "RESTART": "false",
        "WAIT_RUNNING": "600",
    }


class SeismicPublisherAdmission(unittest.TestCase):
    def test_exact_publication_and_source_witness(self) -> None:
        env = publication()
        self.assertEqual(CONTRACT.validate(env), "CANONICAL_SEISMIC_PUBLICATION")

        witness = publication()
        witness.update(
            CALLER_REPOSITORY="szl-holdings/.github",
            EVENT_SHA=witness["WORKFLOW_SHA"],
            EVENT_NAME="push",
            CONTRACT_ONLY="true",
            HF_REPO="",
            DEPLOY_REF="main",
            REQUIRE_TIP="false",
            SOURCE_REVISION_FILE="",
            SOURCE_VARIABLE="",
            SOURCE_PROBE="",
        )
        self.assertEqual(
            CONTRACT.validate(witness), "READ_ONLY_SEISMIC_EXACT_SOURCE_CONTRACT"
        )
        witness["EVENT_SHA"] = "3" * 40
        with self.assertRaisesRegex(ValueError, "EVENT_SHA"):
            CONTRACT.validate(witness)

    def test_retarget_stale_source_and_effect_inputs_fail_closed(self) -> None:
        mutations = {
            "WORKFLOW_REPOSITORY": "attacker/.github",
            "WORKFLOW_SHA": "branch-name",
            "CALLER_REPOSITORY": "szl-holdings/a11oy",
            "EVENT_SHA": "main",
            "EVENT_REF": "refs/heads/feature",
            "EVENT_NAME": "push",
            "CONTRACT_ONLY": "maybe",
            "HF_REPO": "SZLHOLDINGS/other",
            "DEPLOY_REF": "3" * 40,
            "REQUIRE_TIP": "false",
            "DOCKERFILE": "other/Dockerfile",
            "SOURCE_REVISION_FILE": "OTHER_REVISION",
            "SOURCE_VARIABLE": "OTHER_SOURCE",
            "SOURCE_PROBE": "/api/other",
            "INCLUDE_README": "false",
            "PRUNE": "true",
            "RESTART": "true",
            "WAIT_RUNNING": "1200",
            "SMOKE_PATHS": json.dumps(CONTRACT.SMOKE_PATHS[:-1]),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                env = publication()
                env[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    CONTRACT.validate(env)

    def test_invalid_smoke_json_and_missing_inputs_fail_closed(self) -> None:
        for paths in ("not-json", "{}", "[]", '["/"]'):
            with self.subTest(paths=paths):
                env = publication()
                env["SMOKE_PATHS"] = paths
                with self.assertRaisesRegex(ValueError, "SMOKE_PATHS"):
                    CONTRACT.validate(env)
        env = publication()
        del env["HF_REPO"]
        with self.assertRaisesRegex(ValueError, "HF_REPO"):
            CONTRACT.validate(env)


if __name__ == "__main__":
    unittest.main()
