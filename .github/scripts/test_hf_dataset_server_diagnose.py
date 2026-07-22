#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

diagnostic = importlib.import_module("hf_dataset_server_diagnose")


class Response:
    status_code = 500
    text = '{"error":"busy"}'
    headers = {"Content-Type": "application/json", "Retry-After": "5", "Secret": "no"}

    @staticmethod
    def json():
        return {"error": "busy"}


class Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


class DatasetServerDiagnosticTests(unittest.TestCase):
    def test_exact_endpoint_set(self) -> None:
        urls = diagnostic.endpoint_urls()
        self.assertEqual(
            set(urls),
            {"is_valid", "splits", "info", "parquet", "size", "first_rows"},
        )
        self.assertIn("dataset=SZLHOLDINGS%2Fszl-lake", urls["is_valid"])
        self.assertIn("config=receipts", urls["info"])
        self.assertIn("split=train", urls["first_rows"])

    def test_endpoint_query_is_read_only_and_bounded(self) -> None:
        session = Session()
        output = diagnostic.query_dataset_server(session)
        self.assertEqual(set(output), set(diagnostic.endpoint_urls()))
        self.assertEqual(len(session.calls), 6)
        self.assertTrue(all(call[1]["timeout"] == 90 for call in session.calls))
        self.assertTrue(all(item["http_status"] == 500 for item in output.values()))
        self.assertTrue(all("Secret" not in item["headers"] for item in output.values()))

    def test_exact_required_lake_file_set(self) -> None:
        self.assertEqual(len(diagnostic.PARQUET_FILES), 5)
        self.assertIn("README.md", diagnostic.REQUIRED_FILES)
        self.assertIn("khipu/EMPTY_CHAIN_MANIFEST.json", diagnostic.REQUIRED_FILES)

    def test_source_contains_no_hub_mutation(self) -> None:
        source = (HERE / "hf_dataset_server_diagnose.py").read_text(encoding="utf-8")
        for forbidden in (
            "upload_file(",
            "upload_folder(",
            "create_repo(",
            "delete_repo(",
            "update_repo_settings(",
            "restart_space(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("hf_hub_download(", source)
        self.assertIn("pq.ParquetFile", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
