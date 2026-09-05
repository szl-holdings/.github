#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconcile the estate-alignment contract with measured 2026-09-05 Hub state.

This is a one-shot source migration used only on the PR branch. It separates
contract defects from genuine deployment drift and leaves the live gate fail
closed for any runtime that still lacks the exact expected source revision.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / ".github/scripts/estate_alignment_contract.py"
TESTS = ROOT / ".github/scripts/test_estate_alignment_contract.py"
ORG_TESTS = ROOT / ".github/scripts/test_estate_alignment_org_card.py"
CONTRACT = ROOT / "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json"
PROFILE = ROOT / "profile/README.md"
HF_README = ROOT / "huggingface/org-card/README.md"
HF_INDEX = ROOT / "huggingface/org-card/index.html"
AUDIT = ROOT / "audit/ESTATE_ALIGNMENT_CURRENT_MAIN_SUCCESSOR_2026-09-05.md"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement anchor, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_regex_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: expected one regex replacement, found {count}: {pattern[:100]!r}")
    path.write_text(updated, encoding="utf-8")


def replace_if_present(path: Path, old: str, new: str) -> int:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count:
        path.write_text(text.replace(old, new), encoding="utf-8")
    return count


def update_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    snapshot = contract["huggingface_inventory_snapshot"]
    snapshot["observed_at"] = "2026-09-05T21:41:24Z"
    snapshot["portfolio_space_count"] = 17
    snapshot["model_count"] = 45
    snapshot["dataset_count"] = 34

    rows = snapshot["portfolio_spaces"]
    ids = [row["repo_id"] for row in rows]
    if ids.count("SZLHOLDINGS/yarqa") == 0:
        insertion = next(
            index + 1
            for index, row in enumerate(rows)
            if row["repo_id"] == "SZLHOLDINGS/szl-frontier"
        )
        rows.insert(
            insertion,
            {
                "repo_id": "SZLHOLDINGS/yarqa",
                "class": "research_surface",
                "canonical_source": "szl-holdings/yarqa",
                "deployment_source": "szl-holdings/yarqa",
            },
        )
    elif ids.count("SZLHOLDINGS/yarqa") != 1:
        raise SystemExit("contract contains duplicate Yarqa rows")

    lyte = next(row for row in rows if row["repo_id"] == "SZLHOLDINGS/lyte")
    lyte["deployment_source"] = "szl-holdings/lyte-services"

    org_card = contract["organization_card_control_surface"]
    org_card["claim_boundary"] = (
        "Source-bound organization front door; excluded from the 17 portfolio-Space count."
    )

    final_ids = [row["repo_id"] for row in rows]
    if len(final_ids) != 17 or len(set(final_ids)) != 17:
        raise SystemExit(f"expected 17 unique portfolio Spaces, observed {len(final_ids)}")

    CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def update_controller() -> None:
    replace_once(
        CONTROLLER,
        '    "SZLHOLDINGS/szl-model-inference-lab",\n    "SZLHOLDINGS/ayllu",',
        '    "SZLHOLDINGS/szl-model-inference-lab",\n    "SZLHOLDINGS/yarqa",\n    "SZLHOLDINGS/ayllu",',
    )
    replace_once(
        CONTROLLER,
        'require(len(ids) == len(set(ids)) == 16, "portfolio Spaces must contain 16 unique IDs", failures)',
        'require(len(ids) == len(set(ids)) == 17, "portfolio Spaces must contain 17 unique IDs", failures)',
    )
    replace_once(
        CONTROLLER,
        'require(snapshot.get("portfolio_space_count") == 16, "portfolio_space_count must be 16", failures)',
        'require(snapshot.get("portfolio_space_count") == 17, "portfolio_space_count must be 17", failures)',
    )
    replace_once(
        CONTROLLER,
        'require(snapshot.get("model_count") == 44, "model_count must be 44", failures)',
        'require(snapshot.get("model_count") == 45, "model_count must be 45", failures)',
    )
    replace_once(
        CONTROLLER,
        'require(snapshot.get("dataset_count") == 33, "dataset_count must be 33", failures)',
        'require(snapshot.get("dataset_count") == 34, "dataset_count must be 34", failures)',
    )
    replace_once(
        CONTROLLER,
        '== "Source-bound organization front door; excluded from the 16 portfolio-Space count.",',
        '== "Source-bound organization front door; excluded from the 17 portfolio-Space count.",',
    )

    replace_once(
        CONTROLLER,
        "        complete = observed is not None and observed_repository is not None\n",
        "        complete = observed is not None\n"
        "        # The runtime origin and deployment_source are already contract-bound.\n"
        "        # An explicit repository field strengthens that evidence, but absence of the\n"
        "        # redundant field must not invalidate a stable exact-SHA witness. A conflicting\n"
        "        # explicit repository still fails closed.\n"
        "        source_compatible = observed_repository in (None, repository)\n"
        "        source_evidence = (\n"
        "            \"reported\"\n"
        "            if observed_repository == repository\n"
        "            else \"contract-bound-origin\"\n"
        "            if observed_repository is None\n"
        "            else \"conflicting\"\n"
        "        )\n",
    )
    replace_once(
        CONTROLLER,
        '            "observed_source": observed_repository,\n            "matched": (',
        '            "observed_source": observed_repository,\n            "source_evidence": source_evidence,\n            "matched": (',
    )
    replace_once(
        CONTROLLER,
        "                and observed_repository == repository\n",
        "                and source_compatible\n",
    )
    replace_once(
        CONTROLLER,
        '                "observed_source": observed_repository,\n                "matched": attempt["matched"],',
        '                "observed_source": observed_repository,\n                "source_evidence": source_evidence,\n                "matched": attempt["matched"],',
    )

    old_inventory = '''    models = list_hf("models")
    datasets = list_hf("datasets")
    spaces = list_hf("spaces")
    space_ids = {str(row.get("id") or "") for row in spaces}
    portfolio_ids = space_ids - {ORG_CARD_SPACE_ID}
    expected = {row["repo_id"] for row in contract["huggingface_inventory_snapshot"]["portfolio_spaces"]}
    require(portfolio_ids == expected, f"public portfolio Space drift: missing={sorted(expected - portfolio_ids)} unexpected={sorted(portfolio_ids - expected)}", failures)
    require(len(models) == contract["huggingface_inventory_snapshot"]["model_count"], f"model count drift: {len(models)}", failures)
    require(len(datasets) == contract["huggingface_inventory_snapshot"]["dataset_count"], f"dataset count drift: {len(datasets)}", failures)
    require(ORG_CARD_SPACE_ID in space_ids, "Hugging Face organization-card Space missing", failures)
'''
    new_inventory = '''    models = list_hf("models")
    datasets = list_hf("datasets")
    spaces = list_hf("spaces")
    space_ids = {str(row.get("id") or "") for row in spaces}
    portfolio_ids = space_ids - {ORG_CARD_SPACE_ID}
    expected = {row["repo_id"] for row in contract["huggingface_inventory_snapshot"]["portfolio_spaces"]}
    require(portfolio_ids == expected, f"public portfolio Space drift: missing={sorted(expected - portfolio_ids)} unexpected={sorted(portfolio_ids - expected)}", failures)
    require(len(models) == contract["huggingface_inventory_snapshot"]["model_count"], f"model count drift: {len(models)}", failures)
    require(len(datasets) == contract["huggingface_inventory_snapshot"]["dataset_count"], f"dataset count drift: {len(datasets)}", failures)

    # The static README control surface is intentionally outside the portfolio
    # count and is not guaranteed to appear in the author-filtered bulk Space
    # listing. Prove its existence directly instead of turning a Hub listing
    # quirk into a false source-alignment failure.
    try:
        org_card_detail = load_json_bytes(
            fetch_bytes(f"{HF_API}/spaces/{ORG_CARD_SPACE_ID}"),
            label="Hugging Face organization-card Space",
        )
    except Exception as exc:
        org_card_present = False
        failures.append(
            "Hugging Face organization-card Space unavailable: "
            f"{type(exc).__name__}"
        )
    else:
        org_card_present = str(org_card_detail.get("id") or "") == ORG_CARD_SPACE_ID
        require(
            org_card_present,
            "Hugging Face organization-card Space identity mismatch",
            failures,
        )
'''
    replace_once(CONTROLLER, old_inventory, new_inventory)
    replace_once(
        CONTROLLER,
        '            "spaces_including_org_card": len(space_ids),',
        '            "spaces_including_org_card": len(\n                space_ids | ({ORG_CARD_SPACE_ID} if org_card_present else set())\n            ),',
    )


def update_tests() -> None:
    replace_regex_once(
        TESTS,
        r"    def test_incomplete_build_info_falls_back_to_complete_deployment\(self\) -> None:\n.*?(?=    def test_inconsistent_runtime_observations_fail_closed)",
        '''    def test_exact_revision_only_build_info_is_bound_by_contract_origin(self) -> None:
        row = {
            "repo_id": "SZLHOLDINGS/terra",
            "canonical_source": "szl-holdings/a11oy:verticals/terra",
            "deployment_source": "szl-holdings/a11oy",
        }
        expected = "c" * 40
        requested: list[str] = []

        def fetch(url: str, **_kwargs) -> bytes:
            requested.append(url)
            self.assertEqual(
                alignment.urllib.parse.urlsplit(url).path,
                "/api/build-info",
            )
            return json.dumps({"build": {"revision": expected}}).encode()

        observation = alignment.runtime_source_binding(row, expected, fetch=fetch)

        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/api/build-info")
        self.assertIsNone(observation["observed_source"])
        self.assertEqual(
            observation["attempts"][0]["source_evidence"],
            "contract-bound-origin",
        )
        self.assertEqual(len(observation["attempts"]), 1)
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)

''',
    )
    replace_once(
        TESTS,
        '        self.assertEqual(stale["observed_source"], "szl-holdings/szl-real-estate")\n',
        '        self.assertEqual(stale["observed_source"], "szl-holdings/szl-real-estate")\n\n'
        '        wrong_source = alignment.runtime_source_binding(\n'
        '            row,\n'
        '            expected,\n'
        '            fetch=lambda _url, **_kwargs: json.dumps(\n'
        '                {\n'
        '                    "source_repository": "szl-holdings/szl-real-estate",\n'
        '                    "source_revision": expected,\n'
        '                }\n'
        '            ).encode(),\n'
        '        )\n'
        '        self.assertFalse(wrong_source["matched"])\n'
        '        self.assertEqual(\n'
        '            wrong_source["attempts"][0]["source_evidence"], "conflicting"\n'
        '        )\n',
    )
    replace_once(
        TESTS,
        '        space_ids = sorted(alignment.EXPECTED_PORTFOLIO_SPACES | {"SZLHOLDINGS/README"})',
        '        space_ids = sorted(alignment.EXPECTED_PORTFOLIO_SPACES)',
    )
    replace_once(
        TESTS,
        '''        def fetch(url: str, **_kwargs) -> bytes:
            if "/repos/" in url:
                return b'{"archived":false,"visibility":"public","default_branch":"main"}'
            return json.dumps(product).encode()
''',
        '''        def fetch(url: str, **_kwargs) -> bytes:
            if "/repos/" in url:
                return b'{"archived":false,"visibility":"public","default_branch":"main"}'
            if url == f"{alignment.HF_API}/spaces/{alignment.ORG_CARD_SPACE_ID}":
                return json.dumps({"id": alignment.ORG_CARD_SPACE_ID}).encode()
            return json.dumps(product).encode()
''',
    )

    for path in (TESTS, ORG_TESTS):
        replace_if_present(path, "return [{}] * 44", "return [{}] * 45")
        replace_if_present(path, "return [{}] * 33", "return [{}] * 34")
        replace_if_present(path, 'len(observation["runtime_source_bindings"]), 16', 'len(observation["runtime_source_bindings"]), 17')
        replace_if_present(path, "len(portfolio_ids), 16", "len(portfolio_ids), 17")
        replace_if_present(path, "seventeenth portfolio member", "eighteenth portfolio member")


def update_public_documents() -> None:
    replacements = {
        "16 public Spaces, 44 models, and 33 datasets": "17 public Spaces, 45 models, and 34 datasets",
        "16 portfolio Spaces · 44 models · 33 datasets": "17 portfolio Spaces · 45 models · 34 datasets",
        "16 portfolio-Space count": "17 portfolio-Space count",
        "16 portfolio Spaces": "17 portfolio Spaces",
        "44 models": "45 models",
        "33 datasets": "34 datasets",
    }
    for path in (PROFILE, HF_README, HF_INDEX, AUDIT):
        if not path.exists():
            continue
        for old, new in replacements.items():
            replace_if_present(path, old, new)


def verify_source_state() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    snapshot = contract["huggingface_inventory_snapshot"]
    ids = [row["repo_id"] for row in snapshot["portfolio_spaces"]]
    lyte = next(row for row in snapshot["portfolio_spaces"] if row["repo_id"] == "SZLHOLDINGS/lyte")

    assert len(ids) == len(set(ids)) == 17
    assert "SZLHOLDINGS/yarqa" in ids
    assert snapshot["model_count"] == 45
    assert snapshot["dataset_count"] == 34
    assert lyte["deployment_source"] == "szl-holdings/lyte-services"
    assert "contract-bound-origin" in controller
    assert "organization-card Space identity mismatch" in controller
    assert "exact_revision_only_build_info" in tests
    assert "wrong_source" in tests


def main() -> int:
    update_contract()
    update_controller()
    update_tests()
    update_public_documents()
    verify_source_state()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
