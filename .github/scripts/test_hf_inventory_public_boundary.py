#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline adversarial projection tests; never contact a provider."""
import copy
import json
import unittest

from hf_inventory_public_boundary import public_report


class PublicInventoryBoundaryTests(unittest.TestCase):
    def report(self):
        return {
            "generation": "a" * 40,
            "generated_at": "2026-10-04T15:00:00Z",
            "assets": {"models": [{"id": "SZLHOLDINGS/public-model", "sha": "b" * 40, "private": False, "downloads": 42, "likes": 3}]},
            "summary": {"ok": 99, "error": 7, "warning": 4, "dry_run": 23},
        }

    def test_projection_counts_public_rows_only(self):
        report = self.report()
        report["assets"]["models"].extend([{"id": "SECRET", "private": True}, {"id": "UNKNOWN"}, {"id": "ZERO", "private": 0}])
        output = public_report(report)
        self.assertEqual(output["counts"]["models"], 1)
        self.assertEqual(output["summary"], {"public_assets_observed": 1, "categories_observed": 1, "categories_unknown": 3})
        self.assertIsNone(output["counts"]["datasets"])

    def test_private_changes_do_not_change_public_projection(self):
        original = self.report()
        changed = copy.deepcopy(original)
        changed["assets"]["models"].append({"id": "PRIVATE-SENTINEL", "private": True})
        changed["summary"] = {"ok": 88888, "error": 5555, "warning": 777, "dry_run": 123}
        changed["actions"] = [{"detail": "PRIVATE-SENTINEL"}]
        changed["buckets"] = [{"id": "PRIVATE-SENTINEL"}]
        changed["collections"] = [{"note": "PRIVATE-SENTINEL"}]
        changed["sha256"] = "PRIVATE-SENTINEL"
        self.assertEqual(public_report(original), public_report(changed))

    def test_unknown_category_is_not_empty_success(self):
        output = public_report({"assets": {"models": []}, "counts": {"models": None}})
        self.assertIsNone(output["counts"]["models"])
        self.assertEqual(output["coverage"]["models"], "UNKNOWN")
        self.assertNotIn("models", output["assets"])

    def test_empty_observed_public_category_is_zero(self):
        output = public_report({"assets": {"models": []}})
        self.assertEqual(output["counts"]["models"], 0)
        self.assertEqual(output["coverage"]["models"], "OBSERVED_PUBLIC_ONLY")

    def test_error_names_and_generation_cannot_carry_private_values(self):
        report = self.report()
        report.update(error_class="PRIVATE-SENTINEL", fatal="PRIVATE-SENTINEL", generation="PRIVATE-SENTINEL", generated_at="PRIVATE-SENTINEL")
        output = public_report(report)
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(output))
        self.assertEqual(output["error_class"], "INVENTORY_FAILED")
        self.assertIsNone(output["generation"])

    def test_typed_fields_do_not_forward_nested_private_objects(self):
        report = self.report()
        row = report["assets"]["models"][0]
        for key in ("sha", "sdk", "downloads", "likes", "last_modified"):
            row[key] = {"private_id": "PRIVATE-SENTINEL"}
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(public_report(report)))

    def test_boolean_and_negative_counts_are_not_numbers(self):
        for value in (True, False, -1, 1.5, 2**54, "42"):
            with self.subTest(value=value):
                report = self.report()
                report["assets"]["models"][0]["likes"] = value
                self.assertIsNone(public_report(report)["assets"]["models"][0]["likes"])

    def test_unbound_source_is_null(self):
        for value in ("0" * 40, "a" * 39, "a" * 41, "A" * 40, None, ["a" * 40]):
            with self.subTest(value=value):
                self.assertIsNone(public_report({"generation": value})["generation"])

    def test_foreign_and_malformed_public_ids_fail_closed(self):
        for identity in ("other/model", "SZLHOLDINGS/../private", "SZLHOLDINGS/a\n", {}, None):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(ValueError, "PUBLIC_ASSET_ID_REJECTED"):
                    public_report({"assets": {"models": [{"id": identity, "private": False}]}})

    def test_duplicate_public_ids_fail_closed_but_kinds_are_separate(self):
        row = {"id": "SZLHOLDINGS/a", "private": False}
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            public_report({"assets": {"models": [row, row]}})
        self.assertEqual(public_report({"assets": {"models": [row], "kernels": [row]}})["summary"]["public_assets_observed"], 2)

    def test_shape_and_row_bounds(self):
        for report in ([], {"assets": []}, {"counts": []}, {"assets": {"models": {}}}, {"assets": {"models": [None]}}, {"assets": {"models": [{}] * 10001}}):
            with self.subTest(report_type=type(report).__name__), self.assertRaises(ValueError):
                public_report(report)

    def test_canonical_unknown_visibility_is_withheld(self):
        for visibility in (True, None, 0, "false"):
            self.assertIsNone(public_report({"canonical_a11oy": {"repo_id": "SZLHOLDINGS/a11oy", "private": visibility}})["canonical_a11oy"])

    def test_canonical_metadata_is_typed_and_bounded(self):
        row = {"repo_id": "SZLHOLDINGS/a11oy", "private": False, "stage": {"private": "PRIVATE-SENTINEL"}, "sdk": "PRIVATE-SENTINEL", "file_count": True, "sha": {"private": "PRIVATE-SENTINEL"}}
        result = public_report({"canonical_a11oy": row})["canonical_a11oy"]
        self.assertEqual(result["stage"], "UNKNOWN")
        self.assertIsNone(result["file_count"])
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(result))

    def test_timestamps_require_timezone_and_normalize(self):
        report = self.report()
        report["generated_at"] = "2026-10-04T11:00:00-04:00"
        self.assertEqual(public_report(report)["generated_at"], "2026-10-04T15:00:00+00:00")
        for value in ("2026-10-04T15:00:00", "invalid", "a" * 41):
            report["generated_at"] = value
            self.assertIsNone(public_report(report)["generated_at"])


if __name__ == "__main__":
    unittest.main()
