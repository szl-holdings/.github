#!/usr/bin/env python3
"""Regression tests for evidence shape and bounded public collection; no Hub writes."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import unittest.mock

SPEC = importlib.util.spec_from_file_location("hf_model_evidence_audit", Path(__file__).with_name("hf_model_evidence_audit.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

RECORD = {"name": "example", "results": [{"task": {"type": "text-generation"},
          "dataset": {"type": "org/held-out"}, "metrics": [{"type": "accuracy", "value": 0.5}]}]}


def model_info(paths=None, card=None):
    return {"id": "SZLHOLDINGS/example", "sha": "a" * 40, "private": False,
            "cardData": {"license": "apache-2.0", **(card or {})},
            "siblings": [{"rfilename": path} for path in (paths or ["README.md", "model.safetensors"])]}


def evaluate(info=None, text="Measured artifact.", documents=None):
    return audit.evaluate_model(info or model_info(), text, require_structured_eval_for_weights=True,
                                result_documents=documents)


class ModelEvidenceAuditTests(unittest.TestCase):
    def test_sharded_bin_weights_are_enforced(self):
        paths = ["README.md", "weights/pytorch_model-00001-of-00002.bin",
                 "weights/pytorch_model-00002-of-00002.bin", "pytorch_model.bin.index.json", "training_args.bin"]
        result = evaluate(model_info(paths))
        self.assertEqual(len(result["weight_files"]), 2)
        self.assertEqual(result["unsafe_executable_files"], ["training_args.bin"])
        self.assertIn("WEIGHTS_WITHOUT_STRUCTURED_EVALUATION", {x["code"] for x in result["violations"]})

    def test_known_artifacts_and_case_insensitive_shards(self):
        self.assertEqual(audit.weight_files(["pytorch_model-1-of-2.BIN", "adapter_model.safetensors", "m.gguf",
                                           "m.onnx", "weights.npz", "optimizer.bin"]),
                         ["adapter_model.safetensors", "m.gguf", "m.onnx", "pytorch_model-1-of-2.BIN"])

    def test_empty_markers_or_result_filenames_cannot_qualify(self):
        for card in ({"model-index": []}, {"model-index": [{"name": "example", "results": []}]},
                     {"eval_results": None}, {"model-index": [{"name": "example", "results": [{"task": {"type": "generation"}}]}]}):
            with self.subTest(card=card):
                result = evaluate(model_info(card=card), "model-index:\neval_results:", {"results.json": "{}"})
                self.assertFalse(result["structured_evaluation"]["present"])
                self.assertEqual(result["release_static_evidence"], "INCOMPLETE")

    def test_malformed_or_empty_json_yaml_are_not_evidence(self):
        for path, text in (("results.json", ""), ("results.json", "not JSON"), ("eval_results.json", "[]"),
                           ("model-index.yaml", "model-index:"), ("model-index.yml", "["),
                           ("model-index.yaml", "!!python/object/apply:os.system ['echo invalid']"),
                           ("results.json", None)):
            with self.subTest(path=path, text=text):
                result = evaluate(documents={path: text})
                self.assertFalse(result["structured_evaluation"]["present"])
                self.assertEqual(len(result["structured_evaluation"]["invalid_documents"]), 1)

    def test_legacy_model_index_and_evalresult_are_parsed(self):
        documents = {"model-index.yaml": "model-index:\n" + audit.yaml.safe_dump([RECORD]),
                     "eval_results.json": json.dumps({"eval_results": [{"task_type": "classification",
                                         "dataset_type": "org/holdout", "metric_type": "accuracy", "metric_value": 0.75}]})}
        result = evaluate(documents=documents)
        self.assertTrue(result["structured_evaluation"]["present"])
        self.assertEqual(result["structured_evaluation"]["record_count"], 2)
        self.assertEqual(result["release_static_evidence"], "PRESENT")
        self.assertEqual(result["violations"], [])

    def test_legacy_result_needs_dataset_task_metric_and_finite_score(self):
        for missing in ("task", "dataset", "metrics"):
            record = copy.deepcopy(RECORD)
            del record["results"][0][missing]
            self.assertFalse(evaluate(model_info(card={"model-index": [record]}))["structured_evaluation"]["present"])
        for score in (True, None, "0.9", float("nan"), float("inf"), -float("inf")):
            record = copy.deepcopy(RECORD)
            record["results"][0]["metrics"][0]["value"] = score
            self.assertFalse(evaluate(model_info(card={"model-index": [record]}))["structured_evaluation"]["present"])

    def test_current_eval_results_yaml_valid_record(self):
        text = "- dataset:\n    id: org/benchmark\n    task_id: held_out\n  value: 0.412\n"
        result = evaluate(documents={".eval_results/held-out.yaml": text})
        self.assertEqual(result["structured_evaluation"]["record_count"], 1)
        self.assertEqual(result["structured_evaluation"]["records"][0]["verification"], "NOT_VERIFIED_BY_THIS_AUDIT")
        self.assertEqual(result["release_static_evidence"], "PRESENT")

    def test_current_results_require_dataset_id_task_and_numeric_score(self):
        valid = {"dataset": {"id": "org/benchmark", "task_id": "test"}, "value": 0.0}
        malformed = [{}, {"dataset": {"id": "org/benchmark"}, "value": 0.1},
                     {"dataset": {"task_id": "test"}, "value": 0.1}]
        for score in (True, "1.0", None, float("nan"), float("inf")):
            malformed.append({**valid, "value": score})
        malformed.extend([{**valid, "source": {}}, {**valid, "verifyToken": 123}, {**valid, "date": False}])
        for item in malformed:
            self.assertFalse(evaluate(documents={".eval_results/test.yaml": audit.yaml.safe_dump([item])})["structured_evaluation"]["present"])

    def test_claim_negation_is_local_even_within_same_sentence(self):
        examples = ["The old baseline is not SOTA. This release is state of the art.",
                    "The baseline is not SOTA but this release is state of the art.",
                    "No SOTA claim is made. A fully trained model."]
        for text in examples:
            self.assertEqual(len(audit.unqualified_claims(text)), 1)
        self.assertEqual(audit.unqualified_claims("Not state of the art and no SOTA claim is made."), [])
        self.assertEqual(audit.unqualified_claims("We do not claim this is SOTA. Frontier-class is not proven."), [])
        self.assertEqual(audit.unqualified_claims("Not\nstate of the art. This is fully\ntrained."), ["fully trained"])

    def test_valid_scores_do_not_certify_unqualified_frontier_claim(self):
        result = evaluate(model_info(card={"model-index": [RECORD]}), "This release is SOTA.")
        self.assertIn("UNQUALIFIED_FRONTIER_CLAIM", {x["code"] for x in result["violations"]})
        self.assertEqual(result["release_static_evidence"], "INCOMPLETE")

    def test_npz_and_kernels_keep_their_own_contract(self):
        numeric = evaluate(model_info(["README.md", "vectors.npz"]))
        self.assertEqual(numeric["artifact_kind"], "numeric_fixture_or_embedding_table")
        self.assertEqual(numeric["weight_files"], [])
        self.assertEqual(numeric["numeric_archive_files"], ["vectors.npz"])
        self.assertEqual(numeric["violations"], [])
        self.assertIn("OWN_CONTRACT_REVIEW_REQUIRED", {x["code"] for x in numeric["warnings"]})
        kernel = evaluate(model_info(["README.md", "kernel.py"], {"library_name": "kernels"}))
        self.assertEqual(kernel["artifact_kind"], "kernel_software")

    def test_collection_reads_current_then_pinned_info_and_result_bytes(self):
        info = model_info(["README.md", "model.safetensors", ".eval_results/test.yaml"])
        with (unittest.mock.patch.object(audit, "_get_json", side_effect=[[info], info, info]) as metadata,
              unittest.mock.patch.object(audit, "_get_text", side_effect=["Measured.", "- dataset: {id: org/benchmark, task_id: test}\n  value: 0.5"]) as content):
            models = audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)
        self.assertEqual(len(models), 1)
        self.assertIn("/revision/" + "a" * 40, metadata.call_args_list[2].args[0])
        self.assertTrue(all("/resolve/" + "a" * 40 + "/" in call.args[0] for call in content.call_args_list))

    def test_collection_excludes_private_and_rejects_duplicates(self):
        info = model_info(["README.md"])
        private = {"id": "SZLHOLDINGS/private", "private": True}
        with (unittest.mock.patch.object(audit, "_get_json", side_effect=[[private, info], info, info]),
              unittest.mock.patch.object(audit, "_get_text", return_value="Measured.")):
            self.assertEqual(len(audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)), 1)
        with (unittest.mock.patch.object(audit, "_get_json", side_effect=[[info, info], info, info]),
              unittest.mock.patch.object(audit, "_get_text", return_value="Measured."), self.assertRaises(audit.AuditIncomplete)):
            audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)

    def test_missing_or_changed_immutable_identity_is_incomplete(self):
        for changed in ({**model_info(), "sha": "b" * 40}, {**model_info(), "id": "SZLHOLDINGS/other"}):
            with (unittest.mock.patch.object(audit, "_get_json", side_effect=[[model_info()], model_info(), changed]),
                  self.assertRaises(audit.AuditIncomplete)):
                audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)
        with (unittest.mock.patch.object(audit, "_get_json", side_effect=[[model_info()], {**model_info(), "sha": ""}]),
              self.assertRaises(audit.AuditIncomplete)):
            audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)

    def test_bounded_listing_coverage_and_paths_fail_closed(self):
        with (unittest.mock.patch.object(audit, "_get_json", return_value=[model_info()] * 1000), self.assertRaises(audit.AuditIncomplete)):
            audit.collect_models("SZLHOLDINGS", require_structured_eval_for_weights=True)
        with self.assertRaises(audit.AuditIncomplete):
            audit.build_report("SZLHOLDINGS", [], minimum_models=40, require_structured_eval_for_weights=True)
        with self.assertRaises(audit.AuditIncomplete):
            evaluate(model_info(["../results.json"]))

    def test_missing_or_malformed_pinned_file_inventory_is_incomplete(self):
        for siblings in (None, {}, "model.safetensors", [None], [{}], [{"rfilename": 42}], [{"rfilename": ""}]):
            with self.subTest(siblings=siblings):
                info = model_info()
                if siblings is None:
                    del info["siblings"]
                else:
                    info["siblings"] = siblings
                with self.assertRaises(audit.AuditIncomplete):
                    evaluate(info)
        empty = model_info()
        empty["siblings"] = []
        self.assertEqual(evaluate(empty)["weight_files"], [])

    def test_network_failure_writes_incomplete_report_and_exits_two(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            markdown = Path(directory) / "report.md"
            with unittest.mock.patch.object(audit, "collect_models", side_effect=OSError("offline")):
                code = audit.main(["--report", str(report), "--markdown", str(markdown), "--enforce"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(report.read_text())["status"], "INCOMPLETE")
            self.assertIn("offline", markdown.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
