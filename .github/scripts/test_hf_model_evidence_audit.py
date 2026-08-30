#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

audit = importlib.import_module("hf_model_evidence_audit")


def model_info(*, paths: list[str], card: dict | None = None, sha: str | None = None):
    return {
        "id": "SZLHOLDINGS/example",
        "sha": sha or "a" * 40,
        "library_name": "transformers",
        "pipeline_tag": "text-generation",
        "cardData": {"license": "apache-2.0", **(card or {})},
        "siblings": [{"rfilename": path} for path in paths],
    }


class ModelEvidenceAuditTests(unittest.TestCase):
    def test_weights_exclude_trainer_metadata(self) -> None:
        paths = ["adapter_model.safetensors", "training_args.bin", "weights/model.gguf"]
        self.assertEqual(
            audit.weight_files(paths),
            ["adapter_model.safetensors", "weights/model.gguf"],
        )
        self.assertEqual(audit.unsafe_executable_files(paths), ["training_args.bin"])

    def test_negated_frontier_statement_is_not_an_overclaim(self) -> None:
        text = "This artifact is not state of the art and no SOTA claim is made."
        self.assertEqual(audit.unqualified_claims(text), [])
        self.assertEqual(audit.unqualified_claims("A fully trained frontier-class model."), ["frontier-class", "fully trained"])

    def test_weighted_artifact_without_structured_eval_fails_when_required(self) -> None:
        result = audit.evaluate_model(
            model_info(paths=["README.md", "model.safetensors"]),
            "---\nlicense: apache-2.0\n---\nA model.",
            require_structured_eval_for_weights=True,
        )
        self.assertEqual(result["release_static_evidence"], "INCOMPLETE")
        self.assertIn(
            "WEIGHTS_WITHOUT_STRUCTURED_EVALUATION",
            {item["code"] for item in result["violations"]},
        )

    def test_structured_eval_and_safe_weights_meet_static_evidence_only(self) -> None:
        result = audit.evaluate_model(
            model_info(
                paths=["README.md", "model.safetensors"],
                card={"model-index": [{"name": "example", "results": [{"task": {"type": "text-generation"}}]}]},
            ),
            "---\nlicense: apache-2.0\nmodel-index:\n- name: example\n---\nMeasured model.",
            require_structured_eval_for_weights=True,
        )
        self.assertEqual(result["release_static_evidence"], "PRESENT")
        self.assertEqual(result["violations"], [])

    def test_unqualified_claim_without_results_fails(self) -> None:
        result = audit.evaluate_model(
            model_info(paths=["README.md"]),
            "A state-of-the-art system.",
            require_structured_eval_for_weights=False,
        )
        self.assertIn("UNBOUND_FRONTIER_CLAIM", {item["code"] for item in result["violations"]})

    def test_coverage_collapse_is_incomplete(self) -> None:
        with self.assertRaises(audit.AuditIncomplete):
            audit.build_report(
                "SZLHOLDINGS",
                [],
                require_structured_eval_for_weights=True,
                minimum_models=40,
            )

    def test_collection_excludes_private_entries(self) -> None:
        listing = [
            {"id": "SZLHOLDINGS/private", "private": True},
            {"id": "SZLHOLDINGS/public", "private": False},
        ]
        detail = model_info(paths=["README.md"])
        detail["id"] = "SZLHOLDINGS/public"
        with (
            mock.patch.object(audit, "_get_json", side_effect=[listing, detail]),
            mock.patch.object(audit, "_get_text", return_value="Public card."),
        ):
            models = audit.collect_models(
                "SZLHOLDINGS",
                "token",
                require_structured_eval_for_weights=False,
            )
        self.assertEqual([item["id"] for item in models], ["SZLHOLDINGS/public"])

    def test_collection_rejects_duplicate_ids(self) -> None:
        listing = [
            {"id": "SZLHOLDINGS/repeated", "private": False},
            {"id": "SZLHOLDINGS/repeated", "private": False},
        ]
        detail = model_info(paths=["README.md"])
        detail["id"] = "SZLHOLDINGS/repeated"
        with (
            mock.patch.object(audit, "_get_json", side_effect=[listing, detail]),
            mock.patch.object(audit, "_get_text", return_value="Public card."),
            self.assertRaises(audit.AuditIncomplete),
        ):
            audit.collect_models(
                "SZLHOLDINGS",
                None,
                require_structured_eval_for_weights=False,
            )

    def test_collection_rejects_listing_ceiling(self) -> None:
        listing = [
            {"id": f"SZLHOLDINGS/model-{index}", "private": False}
            for index in range(1000)
        ]
        with (
            mock.patch.object(audit, "_get_json", return_value=listing),
            self.assertRaises(audit.AuditIncomplete),
        ):
            audit.collect_models(
                "SZLHOLDINGS",
                None,
                require_structured_eval_for_weights=False,
            )

    def test_network_failure_writes_incomplete_report_and_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = pathlib.Path(directory) / "report.json"
            markdown = pathlib.Path(directory) / "report.md"
            with mock.patch.object(audit, "collect_models", side_effect=OSError("offline")):
                code = audit.main(["--report", str(report), "--markdown", str(markdown), "--enforce"])
            self.assertEqual(code, 2)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "INCOMPLETE")
            self.assertIn("offline", payload["error"])
            self.assertIn("INCOMPLETE", markdown.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
