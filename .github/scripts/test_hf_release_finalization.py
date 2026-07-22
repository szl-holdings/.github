#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

finalizer = importlib.import_module("hf_release_finalization")


class ReleaseFinalizationContractTests(unittest.TestCase):
    def test_exact_release_targets(self) -> None:
        self.assertEqual(finalizer.DATASET_ID, "SZLHOLDINGS/szl-lake")
        self.assertEqual(
            set(finalizer.KERNEL_SPECS),
            {
                "SZLHOLDINGS/governed-inference-meter",
                "SZLHOLDINGS/szl-governed-norm",
            },
        )

    def test_kernel_publication_is_card_and_contract_only(self) -> None:
        source = inspect.getsource(finalizer.Finalizer.finalize_kernel)
        self.assertIn('repo_type="kernel"', source)
        self.assertIn('((card, "README.md"), (contract, "contract.json"))', source)
        self.assertNotIn("upload_folder", source)
        self.assertNotIn("delete_repo", source)
        self.assertNotIn("update_repo_settings", source)
        self.assertNotIn("build-and-upload", source)

    def test_dataset_publication_uses_reviewed_card_and_data_directory(self) -> None:
        source = inspect.getsource(finalizer.Finalizer.finalize_dataset)
        self.assertIn('root / "huggingface" / "README.md"', source)
        self.assertIn('root / "data"', source)
        self.assertIn("Dataset Viewer contract", source)
        self.assertNotIn("delete_patterns", source)

    def test_no_model_or_training_target(self) -> None:
        source = (HERE / "hf_release_finalization.py").read_text(encoding="utf-8")
        self.assertNotIn('repo_type="model"', source)
        self.assertNotIn("train(", source)
        self.assertNotIn("merge_weights", source)
        self.assertNotIn("set_space_hardware", source)


if __name__ == "__main__":
    unittest.main()
