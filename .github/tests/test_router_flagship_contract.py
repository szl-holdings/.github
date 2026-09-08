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

    def test_portfolio_links_source_owned_router_asset_without_bundle_drift(self) -> None:
        manifest = MODULE.load_json(ROOT / "huggingface/org-card.manifest.json")
        sources = {row["source"] for row in manifest["files"]}
        self.assertNotIn("profile/assets/hf-card-router.svg", sources)

        card = (ROOT / "profile/README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(MODULE.HUB_ASSET_URL, card)

    def validate_with_profile_change(self, transform):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                "governance/router-flagship-v1.json", "profile/README.md",
                "huggingface/org-card/README.md", "docs/CANONICAL_FLEET.md",
                "huggingface/org-card/GOVERNANCE.md", MODULE.ASSET,
                "huggingface/org-card.manifest.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            profile = root / "profile/README.md"
            profile.write_text(transform(profile.read_text(encoding="utf-8")), encoding="utf-8")
            return MODULE.validate(root)

    def test_portfolio_cannot_drop_router_product_authority(self) -> None:
        result = self.validate_with_profile_change(lambda text: text.replace(MODULE.PRODUCT, "https://example.com"))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(f"GitHub profile missing {MODULE.PRODUCT}", result["failures"])

    def test_portfolio_cannot_drop_source_owned_router_art(self) -> None:
        result = self.validate_with_profile_change(lambda text: text.replace(MODULE.HUB_ASSET_URL, "https://example.com/route.svg"))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("GitHub profile does not link source-owned router art", result["failures"])


if __name__ == "__main__":
    unittest.main()
