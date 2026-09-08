from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/router_flagship_contract.py"
SPEC = importlib.util.spec_from_file_location("router_flagship_contract", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RouterFlagshipContractTests(unittest.TestCase):
    def test_real_contract_passes(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual("PASS", result["status"], result["failures"])
        self.assertEqual("szl-holdings/szl-router", result["source"])
        self.assertEqual("SZLHOLDINGS/llm-router-live", result["space"])
        self.assertFalse(result["credential_values_recorded"])

    def test_policy_is_strict_json(self) -> None:
        policy = MODULE.load_json(ROOT / "governance/router-flagship-v1.json")
        self.assertEqual("szl.router-flagship/v1", policy["schema"])
        self.assertEqual("INFERENCE_FLAGSHIP", policy["program"]["class"])
        self.assertFalse(
            policy["authority_chain"]["hugging_face_mirror"][
                "credential_bearing_gateway"
            ]
        )
        self.assertFalse(policy["publication"]["target_creation_allowed"])
        self.assertFalse(policy["authority_boundary"]["router_can_self_authorize"])

    def test_duplicate_policy_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaises(MODULE.ContractError):
                MODULE.load_json(path)

    def test_router_asset_is_script_free(self) -> None:
        svg = (ROOT / "profile/assets/hf-card-router.svg").read_text(
            encoding="utf-8"
        )
        self.assertIn("INFERENCE FLAGSHIP", svg)
        self.assertIn("szl-holdings/szl-router", svg)
        self.assertIn("SZLHOLDINGS/llm-router-live", svg)
        self.assertNotIn("<script", svg.casefold())
        self.assertNotIn("javascript:", svg.casefold())

    def test_hub_card_renders_source_owned_router_asset_without_bundle_drift(self) -> None:
        manifest = MODULE.load_json(ROOT / "huggingface/org-card.manifest.json")
        sources = {row["source"] for row in manifest["files"]}
        self.assertNotIn("profile/assets/hf-card-router.svg", sources)

        markers = manifest["runtime_transforms"]["README.md"]["required_markers"]
        for marker in (
            "Inference flagship",
            "SZL Router",
            "One inference flagship",
            MODULE.HUB_ASSET_URL,
        ):
            self.assertIn(marker, markers)

        card = (ROOT / "huggingface/org-card/README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(MODULE.HUB_ASSET_URL, card)


if __name__ == "__main__":
    unittest.main()
