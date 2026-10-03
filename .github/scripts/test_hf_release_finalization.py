#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import subprocess
import tempfile
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

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

    def test_dataset_finalization_is_read_only_and_requires_closed_index(self) -> None:
        source = inspect.getsource(finalizer.Finalizer.finalize_dataset)
        self.assertIn('root / "huggingface" / "README.md"', source)
        self.assertIn('root / "data"', source)
        self.assertIn("Dataset Viewer contract", source)
        self.assertIn("verify_closed_lake_index", source)
        self.assertIn("dataset-publication-authority", source)
        self.assertNotIn("upload_file", source)
        self.assertNotIn("upload_folder", source)
        self.assertNotIn("delete_patterns", source)
        self.assertEqual(source.count("require_dataset_head"), 2)
        self.assertLess(
            source.index('phase="pre-Viewer exact-head check"'),
            source.index("requests.get(VIEWER_URL"),
        )
        self.assertLess(
            source.index("requests.get(VIEWER_URL"),
            source.index('phase="post-Viewer exact-head check"'),
        )

    def test_no_model_or_training_target(self) -> None:
        source = (HERE / "hf_release_finalization.py").read_text(encoding="utf-8")
        self.assertNotIn('repo_type="model"', source)
        self.assertNotIn("train(", source)
        self.assertNotIn("merge_weights", source)
        self.assertNotIn("set_space_hardware", source)


class ClosedLakeIndexTests(unittest.TestCase):
    SOURCE_REVISION = "a" * 40
    PREDECESSOR_REVISION = "b" * 40
    DATASET_REVISION = "c" * 40

    def fixture(self) -> tuple[bytes, dict[str, bytes]]:
        payloads = {
            ".gitattributes": b"*.json text eol=lf\n",
            "README.md": b"---\nlicense: cc-by-4.0\n---\n",
        }
        entries = []
        for path, body in sorted(payloads.items()):
            infrastructure = path == ".gitattributes"
            entries.append(
                {
                    "path": path,
                    "bytes": len(body),
                    "sha256": finalizer.sha256_bytes(body),
                    "origin": (
                        "HF_REPOSITORY_INFRASTRUCTURE_AT_IMMUTABLE_REVISION"
                        if infrastructure
                        else "SOURCE_CONTROLLED"
                    ),
                    "binding_revision": (
                        self.PREDECESSOR_REVISION
                        if infrastructure
                        else self.SOURCE_REVISION
                    ),
                }
            )
        index = {
            "schema": finalizer.LAKE_INDEX_SCHEMA,
            "bindings": {
                "source_repository": finalizer.LAKE_SOURCE_REPOSITORY,
                "source_revision": self.SOURCE_REVISION,
                "hf_repository": finalizer.DATASET_ID,
                "hf_predecessor_revision": self.PREDECESSOR_REVISION,
            },
            "closure": {
                "status": "EXACT_POST_COMMIT_TREE_REQUIRED",
                "indexed_file_count": len(entries),
                "published_file_count_including_index": len(entries) + 1,
                "indexed_bytes": sum(entry["bytes"] for entry in entries),
                "entries_sha256": finalizer.sha256_bytes(
                    finalizer.canonical_json(entries)
                ),
                "origin_counts": {
                    "HF_REPOSITORY_INFRASTRUCTURE_AT_IMMUTABLE_REVISION": 1,
                    "SOURCE_CONTROLLED": 1,
                },
            },
            "self_reference": {
                "path": finalizer.LAKE_INDEX_PATH,
                "status": "EXCLUDED_TO_AVOID_HASH_FIXED_POINT",
                "reason": "fixture",
            },
            "khipu_receipt_counts": {},
            "khipu_receipt_file_counts": {},
            "total_khipu_receipts": 0,
            "files": entries,
        }
        return finalizer.canonical_json(index), payloads

    def verify(
        self,
        index_body: bytes,
        payloads: dict[str, bytes],
        *,
        remote_paths: list[str] | None = None,
        source_payloads: dict[str, bytes] | None = None,
        predecessor_payloads: dict[str, bytes] | None = None,
        verify_predecessor: object | None = None,
    ) -> dict[str, object]:
        paths = remote_paths or sorted([*payloads, finalizer.LAKE_INDEX_PATH])
        remote_sizes = {
            path: (
                len(index_body)
                if path == finalizer.LAKE_INDEX_PATH
                else len(payloads.get(path, b""))
            )
            for path in paths
        }

        def source_projection(revision: str) -> dict[str, bytes]:
            if revision != self.SOURCE_REVISION:
                raise RuntimeError("published source revision is not an ancestor")
            return source_payloads or {"README.md": payloads["README.md"]}

        if predecessor_payloads is None:
            predecessor_payloads = {".gitattributes": payloads[".gitattributes"]}

        return finalizer.verify_closed_lake_index(
            index_body=index_body,
            revision=self.DATASET_REVISION,
            remote_sizes=remote_sizes,
            source_payloads_for_revision=source_projection,
            verify_predecessor=verify_predecessor
            or (
                lambda revision, predecessor: self.assertEqual(
                    (revision, predecessor),
                    (self.DATASET_REVISION, self.PREDECESSOR_REVISION),
                )
            ),
            predecessor_sizes_for_revision=lambda _revision: {
                path: len(body) for path, body in predecessor_payloads.items()
            },
            read_path=lambda path, _expected_bytes: payloads[path],
            read_predecessor_path=lambda path, _revision, _expected_bytes: (
                predecessor_payloads[path]
            ),
        )

    def test_accepts_exact_closed_tree_and_verified_bytes(self) -> None:
        index_body, payloads = self.fixture()
        result = self.verify(index_body, payloads)
        self.assertEqual(result["revision"], self.DATASET_REVISION)
        self.assertEqual(result["source_revision"], self.SOURCE_REVISION)
        self.assertEqual(result["files_verified"], 3)
        self.assertEqual(result["predecessor_files_verified"], 1)

    def test_rejects_checked_source_index_schema(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        index["schema"] = "szl.lake.source-index/v2"
        with self.assertRaisesRegex(RuntimeError, "must use schema"):
            self.verify(finalizer.canonical_json(index), payloads)

    def test_rejects_unindexed_remote_path(self) -> None:
        index_body, payloads = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "tree is not closed"):
            self.verify(
                index_body,
                payloads,
                remote_paths=sorted(
                    [*payloads, finalizer.LAKE_INDEX_PATH, "unindexed.json"]
                ),
            )

    def test_rejects_payload_hash_mismatch(self) -> None:
        index_body, payloads = self.fixture()
        payloads["README.md"] = payloads["README.md"].replace(b"4.0", b"4.1")
        with self.assertRaisesRegex(RuntimeError, "does not match the index"):
            self.verify(
                index_body,
                payloads,
                source_payloads={
                    "README.md": b"---\nlicense: cc-by-4.0\n---\n",
                },
            )

    def test_rejects_non_exact_source_revision(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        index["bindings"]["source_revision"] = "main"
        with self.assertRaisesRegex(RuntimeError, "exact 40-character Git SHA"):
            self.verify(finalizer.canonical_json(index), payloads)

    def test_rejects_valid_but_unaccepted_source_revision(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        index["bindings"]["source_revision"] = "d" * 40
        index["files"][1]["binding_revision"] = "d" * 40
        index["closure"]["entries_sha256"] = finalizer.sha256_bytes(
            finalizer.canonical_json(index["files"])
        )
        with self.assertRaisesRegex(RuntimeError, "not an ancestor"):
            self.verify(finalizer.canonical_json(index), payloads)

    def test_rejects_source_bytes_that_differ_from_reviewed_checkout(self) -> None:
        index_body, payloads = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "reviewed checkout"):
            self.verify(
                index_body,
                payloads,
                source_payloads={"README.md": b"same path, different bytes"},
            )

    def test_rejects_wrong_immediate_predecessor(self) -> None:
        index_body, payloads = self.fixture()

        def reject(_revision: str, _predecessor: str) -> None:
            raise RuntimeError("not the immutable revision's direct parent")

        with self.assertRaisesRegex(RuntimeError, "direct parent"):
            self.verify(
                index_body,
                payloads,
                verify_predecessor=reject,
            )

    def test_rejects_missing_preserved_predecessor_path(self) -> None:
        index_body, payloads = self.fixture()
        with self.assertRaisesRegex(
            RuntimeError, "does not contain the preserved path"
        ):
            self.verify(
                index_body,
                payloads,
                predecessor_payloads={"old.bin": b"x"},
            )

    def test_rejects_changed_preserved_predecessor_bytes(self) -> None:
        index_body, payloads = self.fixture()
        predecessor = payloads[".gitattributes"].replace(b"json", b"yaml")
        self.assertEqual(len(predecessor), len(payloads[".gitattributes"]))
        with self.assertRaisesRegex(RuntimeError, "not preserved from its predecessor"):
            self.verify(
                index_body,
                payloads,
                predecessor_payloads={".gitattributes": predecessor},
            )

    def test_rejects_omitted_predecessor_only_path(self) -> None:
        index_body, payloads = self.fixture()
        with self.assertRaisesRegex(
            RuntimeError, "does not preserve the predecessor tree"
        ):
            self.verify(
                index_body,
                payloads,
                predecessor_payloads={
                    ".gitattributes": payloads[".gitattributes"],
                    "deleted-remote-only.bin": b"must be preserved",
                },
            )

    def test_rejects_inconsistent_receipt_counts(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        index["total_khipu_receipts"] = 1
        with self.assertRaisesRegex(RuntimeError, "total receipt count"):
            self.verify(finalizer.canonical_json(index), payloads)

    def test_rejects_boolean_receipt_count(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        index["total_khipu_receipts"] = False
        with self.assertRaisesRegex(RuntimeError, "non-negative integer"):
            self.verify(finalizer.canonical_json(index), payloads)

    def test_verifies_nonempty_ndjson_receipt_counts(self) -> None:
        index_body, payloads = self.fixture()
        index = finalizer.strict_json(index_body, label="fixture")
        receipt_path = "khipu/amaru_receipts.ndjson"
        receipt_body = b'{"id": 1}\n\n{"id": 2}\n'
        payloads[receipt_path] = receipt_body
        index["files"].append(
            {
                "path": receipt_path,
                "bytes": len(receipt_body),
                "sha256": finalizer.sha256_bytes(receipt_body),
                "origin": "SOURCE_CONTROLLED",
                "binding_revision": self.SOURCE_REVISION,
            }
        )
        index["files"].sort(key=lambda item: item["path"])
        index["closure"].update(
            {
                "indexed_file_count": len(index["files"]),
                "published_file_count_including_index": len(index["files"]) + 1,
                "indexed_bytes": sum(item["bytes"] for item in index["files"]),
                "entries_sha256": finalizer.sha256_bytes(
                    finalizer.canonical_json(index["files"])
                ),
                "origin_counts": {
                    "HF_REPOSITORY_INFRASTRUCTURE_AT_IMMUTABLE_REVISION": 1,
                    "SOURCE_CONTROLLED": 2,
                },
            }
        )
        index["khipu_receipt_counts"] = {"amaru": 2}
        index["khipu_receipt_file_counts"] = {receipt_path: 2}
        index["total_khipu_receipts"] = 2
        rendered = finalizer.canonical_json(index)
        result = self.verify(
            rendered,
            payloads,
            source_payloads={
                "README.md": payloads["README.md"],
                receipt_path: receipt_body,
            },
        )
        self.assertEqual(result["files_verified"], 4)

        for field, value in (
            ("khipu_receipt_counts", {"amaru": 3}),
            ("khipu_receipt_file_counts", {receipt_path: 3}),
            ("total_khipu_receipts", 3),
        ):
            corrupted = finalizer.strict_json(rendered, label="fixture")
            corrupted[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, "receipt.*count"):
                    self.verify(
                        finalizer.canonical_json(corrupted),
                        payloads,
                        source_payloads={
                            "README.md": payloads["README.md"],
                            receipt_path: receipt_body,
                        },
                    )

    def test_rejects_oversized_index_before_parsing(self) -> None:
        index_body, payloads = self.fixture()
        with (
            mock.patch.object(finalizer, "MAX_LAKE_INDEX_BYTES", len(index_body) - 1),
            self.assertRaisesRegex(RuntimeError, "index exceeds the safety bound"),
        ):
            self.verify(index_body, payloads)

    def test_rejects_aggregate_size_before_downloading(self) -> None:
        index_body, payloads = self.fixture()
        reads: list[str] = []
        paths = sorted([*payloads, finalizer.LAKE_INDEX_PATH])
        remote_sizes = {
            path: len(index_body)
            if path == finalizer.LAKE_INDEX_PATH
            else len(payloads[path])
            for path in paths
        }
        with (
            mock.patch.object(finalizer, "MAX_LAKE_TOTAL_BYTES", 1),
            self.assertRaisesRegex(RuntimeError, "aggregate safety bound"),
        ):
            finalizer.verify_closed_lake_index(
                index_body=index_body,
                revision=self.DATASET_REVISION,
                remote_sizes=remote_sizes,
                source_payloads_for_revision=lambda _revision: {
                    "README.md": payloads["README.md"]
                },
                verify_predecessor=lambda _revision, _predecessor: None,
                predecessor_sizes_for_revision=lambda _revision: {
                    ".gitattributes": len(payloads[".gitattributes"])
                },
                read_path=lambda path, _expected: reads.append(path) or payloads[path],
                read_predecessor_path=lambda path, _revision, _expected: payloads[path],
            )
        self.assertEqual(reads, [])

    def test_rejects_duplicate_json_keys(self) -> None:
        index_body, payloads = self.fixture()
        duplicate = index_body.replace(
            b"{\n",
            b'{\n  "schema": "szl.lake.index/v2",\n',
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate JSON key"):
            self.verify(duplicate, payloads)


class ImmutableBindingTests(unittest.TestCase):
    def test_immediate_predecessor_uses_exact_history_order(self) -> None:
        revision = "c" * 40
        predecessor = "b" * 40
        api = SimpleNamespace(
            list_repo_commits=mock.Mock(
                return_value=[
                    SimpleNamespace(commit_id=revision),
                    SimpleNamespace(commit_id=predecessor),
                ]
            )
        )
        finalizer.verify_immediate_hf_predecessor(
            api=api,
            revision=revision,
            predecessor_revision=predecessor,
        )
        api.list_repo_commits.assert_called_once_with(
            finalizer.DATASET_ID,
            repo_type="dataset",
            revision=revision,
        )

    def test_immediate_predecessor_rejects_incomplete_or_wrong_history(self) -> None:
        revision = "c" * 40
        predecessor = "b" * 40
        for commits in (
            [],
            [SimpleNamespace(commit_id=revision)],
            [
                SimpleNamespace(commit_id=revision),
                SimpleNamespace(commit_id="d" * 40),
            ],
        ):
            with self.subTest(commits=commits):
                api = SimpleNamespace(
                    list_repo_commits=lambda *_args, _commits=commits, **_kwargs: (
                        _commits
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "direct parent"):
                    finalizer.verify_immediate_hf_predecessor(
                        api=api,
                        revision=revision,
                        predecessor_revision=predecessor,
                    )

    def test_revision_cannot_be_its_own_predecessor(self) -> None:
        revision = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "own predecessor"):
            finalizer.verify_immediate_hf_predecessor(
                api=SimpleNamespace(list_repo_commits=lambda *_args, **_kwargs: []),
                revision=revision,
                predecessor_revision=revision,
            )

    def test_terminal_head_check_rejects_concurrent_publication(self) -> None:
        api = SimpleNamespace(
            dataset_info=lambda *_args, **_kwargs: SimpleNamespace(sha="d" * 40)
        )
        with self.assertRaisesRegex(RuntimeError, "head changed"):
            finalizer.require_dataset_head(
                api,
                "c" * 40,
                phase="test terminal check",
            )


class ImmutableMetadataTests(unittest.TestCase):
    @staticmethod
    def info(*siblings: object) -> object:
        return SimpleNamespace(siblings=list(siblings))

    @staticmethod
    def sibling(path: str, size: object) -> object:
        return SimpleNamespace(rfilename=path, size=size)

    def test_accepts_exact_bounded_metadata(self) -> None:
        sizes = finalizer.immutable_repo_file_sizes(
            self.info(
                self.sibling(finalizer.LAKE_INDEX_PATH, 10),
                self.sibling("data.bin", 20),
            )
        )
        self.assertEqual(sizes, {finalizer.LAKE_INDEX_PATH: 10, "data.bin": 20})

    def test_rejects_missing_empty_or_duplicate_metadata(self) -> None:
        for info, message in (
            (SimpleNamespace(siblings=None), "closed file list"),
            (self.info(), "closed file list"),
            (
                self.info(self.sibling("x", 1), self.sibling("x", 1)),
                "duplicate path",
            ),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    finalizer.immutable_repo_file_sizes(info)

    def test_rejects_invalid_metadata_sizes(self) -> None:
        for size in (None, "1", True, -1, finalizer.MAX_LAKE_FILE_BYTES + 1):
            with self.subTest(size=size):
                with self.assertRaisesRegex(RuntimeError, "invalid size"):
                    finalizer.immutable_repo_file_sizes(
                        self.info(self.sibling("data.bin", size))
                    )

    def test_rejects_index_and_aggregate_bounds(self) -> None:
        with (
            mock.patch.object(finalizer, "MAX_LAKE_INDEX_BYTES", 1),
            self.assertRaisesRegex(RuntimeError, "index exceeds"),
        ):
            finalizer.immutable_repo_file_sizes(
                self.info(self.sibling(finalizer.LAKE_INDEX_PATH, 2))
            )
        with (
            mock.patch.object(finalizer, "MAX_LAKE_TOTAL_BYTES", 1),
            self.assertRaisesRegex(RuntimeError, "aggregate safety bound"),
        ):
            finalizer.immutable_repo_file_sizes(self.info(self.sibling("data.bin", 2)))


class BoundedDownloadTests(unittest.TestCase):
    class Response:
        def __init__(self, *, chunks: list[bytes], content_length: str | None = None):
            self.chunks = chunks
            self.headers = {}
            if content_length is not None:
                self.headers["Content-Length"] = content_length
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, *, chunk_size: int):
            self.chunk_size = chunk_size
            yield from self.chunks

        def close(self) -> None:
            self.closed = True

    def controller(self) -> object:
        return finalizer.Finalizer(
            token="test-token-not-a-secret",
            publish=False,
            generation="a" * 40,
            lake_root=pathlib.Path("lake"),
            energy_root=pathlib.Path("energy"),
            lambda_root=pathlib.Path("lambda"),
        )

    def call(self, response: object, *, expected_bytes: int) -> bytes:
        with mock.patch.object(finalizer.requests, "get", return_value=response) as get:
            body = self.controller()._download_dataset_path(
                filename="path/file.bin",
                revision="c" * 40,
                expected_bytes=expected_bytes,
            )
        self.assertEqual(get.call_count, 1)
        return body

    def test_exact_streamed_body_passes_and_closes(self) -> None:
        response = self.Response(chunks=[b"ab", b"cd"], content_length="4")
        self.assertEqual(self.call(response, expected_bytes=4), b"abcd")
        self.assertTrue(response.closed)

    def test_oversized_content_length_fails_and_closes(self) -> None:
        response = self.Response(chunks=[], content_length="5")
        with self.assertRaisesRegex(RuntimeError, "exceeds the indexed size"):
            self.call(response, expected_bytes=4)
        self.assertTrue(response.closed)

    def test_oversized_chunk_fails_and_closes(self) -> None:
        response = self.Response(chunks=[b"abcde"])
        with self.assertRaisesRegex(RuntimeError, "exceeds the indexed size"):
            self.call(response, expected_bytes=4)
        self.assertTrue(response.closed)

    def test_truncated_body_fails_and_closes(self) -> None:
        response = self.Response(chunks=[b"abc"])
        with self.assertRaisesRegex(RuntimeError, "does not match metadata"):
            self.call(response, expected_bytes=4)
        self.assertTrue(response.closed)


class SourceProjectionTests(unittest.TestCase):
    def git(self, root: pathlib.Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def write_source(self, root: pathlib.Path, value: bytes) -> None:
        (root / "huggingface").mkdir(parents=True, exist_ok=True)
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "LICENSE").write_bytes(b"license\n")
        (root / "huggingface" / "README.md").write_bytes(b"card\n")
        (root / "data" / "x.json").write_bytes(value)
        payloads = {
            "LICENSE": b"license\n",
            "README.md": b"card\n",
            "x.json": value,
        }
        entries = [
            {
                "path": path,
                "bytes": len(body),
                "sha256": finalizer.sha256_bytes(body),
            }
            for path, body in sorted(payloads.items())
        ]
        index = {
            "schema": "szl.lake.source-index/v2",
            **finalizer.LAKE_METADATA,
            "contract": finalizer.LAKE_SOURCE_INDEX_CONTRACT,
            "indexed_file_count": len(entries),
            "indexed_bytes": sum(item["bytes"] for item in entries),
            "entries_sha256": finalizer.sha256_bytes(finalizer.canonical_json(entries)),
            "files": entries,
        }
        (root / "data" / "lake_index.json").write_bytes(finalizer.canonical_json(index))

    def repository(self) -> tuple[tempfile.TemporaryDirectory[str], pathlib.Path, str]:
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        self.git(root, "init", "--initial-branch=main")
        self.git(root, "config", "user.name", "Test")
        self.git(root, "config", "user.email", "test@example.invalid")
        self.write_source(root, b'{"value":"A"}\n')
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "source A")
        return temporary, root, self.git(root, "rev-parse", "HEAD")

    def test_projection_uses_bound_git_objects_not_dirty_worktree(self) -> None:
        temporary, root, source_revision = self.repository()
        with temporary:
            (root / "NOTES.md").write_text("unrelated\n", encoding="utf-8")
            self.git(root, "add", "NOTES.md")
            self.git(root, "commit", "-m", "unrelated")
            checkout_revision = self.git(root, "rev-parse", "HEAD")
            (root / "data" / "x.json").write_bytes(b'{"value":"DIRTY"}\n')
            payloads = finalizer.expected_lake_source_payloads(
                lake_root=root,
                source_revision=source_revision,
                checkout_revision=checkout_revision,
            )
            self.assertEqual(payloads["x.json"], b'{"value":"A"}\n')

    def test_projection_rejects_payload_drift_after_bound_revision(self) -> None:
        temporary, root, source_revision = self.repository()
        with temporary:
            self.write_source(root, b'{"value":"B"}\n')
            self.git(root, "add", "data")
            self.git(root, "commit", "-m", "source B")
            checkout_revision = self.git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(RuntimeError, "differs from the publication"):
                finalizer.expected_lake_source_payloads(
                    lake_root=root,
                    source_revision=source_revision,
                    checkout_revision=checkout_revision,
                )


if __name__ == "__main__":
    unittest.main()
