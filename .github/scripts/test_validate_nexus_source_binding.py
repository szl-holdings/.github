# Copyright 2026 SZL Holdings - SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "validate_nexus_source_binding",
    _HERE / "validate_nexus_source_binding.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load validate_nexus_source_binding.py")
binding = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = binding
_SPEC.loader.exec_module(binding)


class NexusSourceBindingTests(unittest.TestCase):
    def test_plain_copy_is_admitted(self) -> None:
        result = binding.inspect_dockerfile_text(
            "FROM node:24\nCOPY SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n"
        )
        self.assertEqual(2, result.line)
        self.assertEqual((), result.options)
        self.assertEqual("./SOURCE_GITHUB_SHA", result.destination)

    def test_reviewed_chown_copy_is_admitted(self) -> None:
        result = binding.inspect_dockerfile_text(
            "COPY --chown=node:node SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n"
        )
        self.assertEqual(("--chown=node:node",), result.options)

    def test_reviewed_options_and_continuation_are_admitted(self) -> None:
        result = binding.inspect_dockerfile_text(
            "copy --chown=node:node \\\n"
            "  --chmod=0444 SOURCE_GITHUB_SHA /app/SOURCE_GITHUB_SHA\n"
        )
        self.assertEqual(("--chown=node:node", "--chmod=0444"), result.options)
        self.assertEqual("/app/SOURCE_GITHUB_SHA", result.destination)

    def test_directory_destination_is_admitted(self) -> None:
        result = binding.inspect_dockerfile_text(
            "COPY --link SOURCE_GITHUB_SHA .\n"
        )
        self.assertEqual(("--link",), result.options)
        self.assertEqual(".", result.destination)

    def test_commented_copy_is_not_evidence(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "no exact"):
            binding.inspect_dockerfile_text(
                "# COPY SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\nFROM node:24\n"
            )

    def test_add_and_bulk_copy_are_not_evidence(self) -> None:
        for text in (
            "ADD SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n",
            "COPY . .\n",
        ):
            with self.subTest(text=text), self.assertRaises(binding.SourceBindingError):
                binding.inspect_dockerfile_text(text)

    def test_build_stage_copy_is_denied(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "--from"):
            binding.inspect_dockerfile_text(
                "COPY --from=builder SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n"
            )

    def test_wildcard_and_multiple_sources_are_denied(self) -> None:
        for text in (
            "COPY SOURCE_GITHUB_* ./SOURCE_GITHUB_SHA\n",
            "COPY SOURCE_GITHUB_SHA package.json /app/\n",
        ):
            with self.subTest(text=text), self.assertRaises(binding.SourceBindingError):
                binding.inspect_dockerfile_text(text)

    def test_unreviewed_option_is_denied(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "unreviewed"):
            binding.inspect_dockerfile_text(
                "COPY --exclude=SOURCE_GITHUB_SHA SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n"
            )

    def test_wrong_destination_is_denied(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "destination"):
            binding.inspect_dockerfile_text(
                "COPY SOURCE_GITHUB_SHA /app/revision.txt\n"
            )

    def test_duplicate_bindings_are_denied(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "exactly one"):
            binding.inspect_dockerfile_text(
                "COPY SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n"
                "COPY --chown=node:node SOURCE_GITHUB_SHA /app/SOURCE_GITHUB_SHA\n"
            )

    def test_json_form_is_denied_fail_closed(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "JSON-form"):
            binding.inspect_dockerfile_text(
                'COPY ["SOURCE_GITHUB_SHA", "./SOURCE_GITHUB_SHA"]\n'
            )

    def test_unterminated_continuation_is_denied(self) -> None:
        with self.assertRaisesRegex(binding.SourceBindingError, "unterminated"):
            binding.inspect_dockerfile_text(
                "COPY --chown=node:node SOURCE_GITHUB_SHA \\"
            )

    def test_oversized_dockerfile_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dockerfile = Path(directory) / "Dockerfile"
            dockerfile.write_bytes(b"#" * (binding.MAX_DOCKERFILE_BYTES + 1))
            with self.assertRaisesRegex(binding.SourceBindingError, "size bound"):
                binding.inspect_dockerfile(dockerfile)

    def test_cli_refuses_to_overwrite_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dockerfile = root / "Dockerfile"
            report = root / "binding.json"
            dockerfile.write_text(
                "COPY SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n",
                encoding="utf-8",
            )
            report.write_text("preserve\n", encoding="utf-8")
            self.assertEqual(
                1,
                binding.main([str(dockerfile), "--report", str(report)]),
            )
            self.assertEqual("preserve\n", report.read_text(encoding="utf-8"))

    def test_cli_writes_a_sanitized_success_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dockerfile = root / "Dockerfile"
            report = root / "evidence" / "binding.json"
            dockerfile.write_text(
                "COPY --chown=node:node SOURCE_GITHUB_SHA ./SOURCE_GITHUB_SHA\n",
                encoding="utf-8",
            )
            self.assertEqual(
                0,
                binding.main([str(dockerfile), "--report", str(report)]),
            )
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(binding.SCHEMA, payload["schema"])
        self.assertTrue(payload["binding"])
        self.assertEqual("SOURCE_GITHUB_SHA", payload["source"])
        self.assertNotIn("token", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
