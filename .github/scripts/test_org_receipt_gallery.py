"""Offline publication input/render parity, not a runtime or model qualification."""
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gallery_contract", ROOT / "hf-card/receipt_gallery.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
class PublishedReceiptViewTests(unittest.TestCase):
    def test_source_receipts_and_generated_view_are_exact(self):
        source = ROOT / "huggingface/org-card"
        result = module.load_gallery(source / "receipt-manifest.json")
        self.assertEqual(len(result["records"]), 11)
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(module.render_gallery(result), (source / "evidence.html").read_text(encoding="utf-8"))
if __name__ == "__main__":
    unittest.main()
