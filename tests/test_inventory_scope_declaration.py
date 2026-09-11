#!/usr/bin/env python3
"""Same-scope inventory declaration must not mix predicates."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "estate" / "inventory-scope-declaration-2026-09-11.json"


def test_declaration_exists_and_is_hold() -> None:
    payload = json.loads(DOC.read_text(encoding="utf-8"))
    assert payload["schema"] == "szl.public-inventory-scope-declaration/v1"
    assert payload["disposition"] == "HOLD"
    assert payload["production_authorization"] is False
    assert payload["automatic_promotion_authorized"] is False
    assert payload["item_level_membership_enumeration"] == "UNAVAILABLE"


def test_membership_and_inventory_counts_are_not_the_same_predicate() -> None:
    payload = json.loads(DOC.read_text(encoding="utf-8"))
    membership = payload["predicates"]["membership_v1"]["counts"]
    inventory = payload["predicates"]["inventory_v3"]["counts"]
    assert membership != {k: inventory[k] for k in ("models", "datasets", "spaces")}
    assert payload["predicates"]["membership_v1"]["comparable_to"] == []
    assert payload["predicates"]["inventory_v3"]["comparable_to"] == []


def test_july_report_is_historical_and_incomparable() -> None:
    payload = json.loads(DOC.read_text(encoding="utf-8"))
    report = payload["predicates"]["estate_upgrade_report_2026_07_22"]
    assert report["counts"]["kernels"] == 10
    assert report["comparable_to"] == []
    assert report["counts"]["kernels"] != payload["kernel_kind"]["listed_count"]


def test_kernel_kind_list_is_scoped_and_not_a_membership_count() -> None:
    payload = json.loads(DOC.read_text(encoding="utf-8"))
    kind = payload["kernel_kind"]
    assert kind["scope"]["id"] == "hf-public-author-kernels/v1"
    assert kind["listed_count"] == 14
    assert len(kind["listed"]) == 14
    assert kind["count_for_membership_v1"] is None
    assert kind["production_relevant_projections_verified"] is False
    assert "SZLHOLDINGS/szl-kernels" in kind["listed"]
    assert "SZLHOLDINGS/szl-khipu-kernels" in kind["model_search_only_not_in_kernels_api"]
    assert kind["listed_count"] != payload["predicates"]["membership_v1"]["counts"]["models"]


def test_forbidden_mix_rules_are_explicit() -> None:
    payload = json.loads(DOC.read_text(encoding="utf-8"))
    forbidden = " ".join(payload["forbidden"])
    assert "46/35/21" in forbidden
    assert "44/30/48" in forbidden
    assert "14" in forbidden
