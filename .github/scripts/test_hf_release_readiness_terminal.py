#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import contextmanager
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

terminal = importlib.import_module("hf_release_readiness_terminal")
from kernel_hub_git import KernelSnapshot


class FakeKernelTransport:
    def __init__(self, *, snapshot: KernelSnapshot, repo: pathlib.Path) -> None:
        self.snapshot_value = snapshot
        self.repo = repo
        self.snapshot_calls: list[str] = []
        self.materialize_calls: list[tuple[str, str]] = []

    def snapshot(self, repo_id: str) -> KernelSnapshot:
        self.snapshot_calls.append(repo_id)
        return self.snapshot_value

    @contextmanager
    def materialize_build(self, repo_id: str, revision: str):
        self.materialize_calls.append((repo_id, revision))
        yield self.repo


class TerminalReleaseReadinessTests(unittest.TestCase):
    def test_schema_is_the_readiness_contract(self) -> None:
        self.assertEqual(terminal.REPORT_SCHEMA, "szl.hf-release-readiness/v1")
        self.assertEqual(
            terminal.PRERELEASE_SCHEMA,
            "szl.hf-release-readiness/v1-prerelease",
        )

    def test_generation_must_be_immutable(self) -> None:
        verifier = terminal.TerminalReadiness(
            token="test-token",
            generation="a" * 40,
        )
        self.assertEqual(verifier.generation, "a" * 40)
        with self.assertRaisesRegex(RuntimeError, "immutable revision"):
            terminal.TerminalReadiness(token="test-token", generation="main")

    def test_failed_upstream_is_terminal(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "UPSTREAM_WORKFLOW": "HF Release Finalization — Supported Kernel Git",
                "UPSTREAM_CONCLUSION": "failure",
                "UPSTREAM_RUN_URL": "https://github.com/example/actions/runs/1",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "did not succeed"):
                terminal._require_successful_upstream()
        with patch.dict(
            os.environ,
            {
                "UPSTREAM_WORKFLOW": "HF Release Finalization — Supported Kernel Git",
                "UPSTREAM_CONCLUSION": "success",
            },
            clear=False,
        ):
            terminal._require_successful_upstream()

    def test_selfcheck_parser_requires_positive_evidence(self) -> None:
        self.assertTrue(terminal._selfcheck_passed(True))
        self.assertTrue(terminal._selfcheck_passed({"ok": True}))
        self.assertTrue(
            terminal._selfcheck_passed({"checks": {"a": True, "b": True}})
        )
        self.assertFalse(terminal._selfcheck_passed(False))
        self.assertFalse(terminal._selfcheck_passed({"ok": False}))
        self.assertFalse(
            terminal._selfcheck_passed({"checks": {"a": True, "b": False}})
        )
        self.assertFalse(terminal._selfcheck_passed({"checks": {}}))

    def test_kernel_verification_uses_one_exact_git_revision(self) -> None:
        repo_id = "SZLHOLDINGS/example"
        revision = "b" * 40
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            transport = FakeKernelTransport(
                snapshot=KernelSnapshot(
                    repo_id=repo_id,
                    revision=revision,
                    files=("README.md", "contract.json", "build/cpu/__init__.py"),
                    build_tree_sha256="c" * 64,
                    remote_url="https://huggingface.co/kernels/SZLHOLDINGS/example",
                ),
                repo=repo,
            )
            verifier = terminal.TerminalReadiness(
                token="test-token",
                generation="a" * 40,
                kernel_transport=transport,
            )
            get_local_kernel = unittest.mock.Mock(
                return_value=SimpleNamespace(selfcheck=lambda: {"ok": True})
            )
            with unittest.mock.patch.dict(
                sys.modules,
                {"kernels": SimpleNamespace(get_local_kernel=get_local_kernel)},
            ):
                verifier.verify_kernel(repo_id)

        self.assertEqual(transport.snapshot_calls, [repo_id, repo_id])
        self.assertEqual(transport.materialize_calls, [(repo_id, revision)])
        get_local_kernel.assert_called_once_with(repo, backend="cpu")
        result = verifier.results["kernels"][repo_id]
        self.assertEqual(result["revision"], revision)
        self.assertEqual(
            result["transport"],
            "exact-revision-authenticated-kernel-hub-git-local",
        )

    def test_issue_body_contains_machine_readable_readiness_report(self) -> None:
        report = {
            "schema": terminal.REPORT_SCHEMA,
            "generation": "a" * 40,
            "generated_at": "2026-07-26T00:00:00+00:00",
            "publish": True,
            "results": {"dataset": {"revision": "b" * 40}},
            "summary": {"ok": 1, "warning": 0, "error": 0, "dry_run": 0},
        }
        body = terminal.issue_body(
            report,
            "https://github.com/szl-holdings/.github/actions/runs/1",
        )
        self.assertIn(terminal.ISSUE_MARKER, body)
        self.assertIn("# Hugging Face release readiness", body)
        start = body.index("```json") + len("```json")
        end = body.index("```", start)
        parsed = json.loads(body[start:end].strip())
        self.assertEqual(parsed["schema"], terminal.REPORT_SCHEMA)
        self.assertEqual(parsed["generation"], "a" * 40)

    def test_source_uses_no_unsupported_kernel_helper_or_hf_mutation(self) -> None:
        source = (HERE / "hf_release_readiness_terminal.py").read_text(
            encoding="utf-8"
        )
        forbidden = (
            'repo_type="kernel"',
            "repo_type='kernel'",
            "upload_file(",
            "upload_folder(",
            "create_repo(",
            "delete_repo(",
            "duplicate_repo(",
            "restart_space(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn('repo_type="dataset"', source)
        self.assertIn("materialize_build(repo_id, revision)", source)
        self.assertNotIn("/api/kernels/", source)

    def test_report_shape_matches_final_estate_reconciler(self) -> None:
        report = {
            "schema": terminal.REPORT_SCHEMA,
            "generation": "a" * 40,
            "publish": True,
            "summary": {"ok": 3, "warning": 0, "error": 0, "dry_run": 0},
            "results": {
                "dataset": {
                    "revision": "b" * 40,
                    "remote_file_count": 7,
                    "viewer_http_status": 200,
                    "metadata_stable": True,
                },
                "kernels": {
                    repo_id: {
                        "revision": "c" * 40,
                        "remote_file_count": 10,
                        "build_variants_present": True,
                        "metadata_stable": True,
                        "selfcheck": {"ok": True},
                    }
                    for repo_id in terminal.KERNEL_IDS
                },
            },
        }
        dataset = report["results"]["dataset"]
        kernels = report["results"]["kernels"]
        self.assertEqual(report["schema"], "szl.hf-release-readiness/v1")
        self.assertEqual(dataset["viewer_http_status"], 200)
        self.assertGreater(dataset["remote_file_count"], 0)
        self.assertTrue(dataset["metadata_stable"])
        self.assertEqual(set(kernels), set(terminal.KERNEL_IDS))
        self.assertTrue(
            all(
                terminal.SHA40.fullmatch(value["revision"])
                for value in kernels.values()
            )
        )
        self.assertTrue(
            all(
                terminal._selfcheck_passed(value["selfcheck"])
                for value in kernels.values()
            )
        )

    def test_release_chain_has_one_readiness_owner_and_ordered_workflows(self) -> None:
        legacy_paths = (
            ROOT / ".github/workflows/hf-release-readiness.yml",
            ROOT / ".github/scripts/hf_release_readiness_verify.py",
            ROOT / ".github/scripts/test_hf_release_readiness_verify.py",
        )
        for path in legacy_paths:
            self.assertFalse(path.exists(), f"legacy readiness owner remains: {path}")

        finalization = (
            ROOT / ".github/workflows/hf-release-finalization.yml"
        ).read_text(encoding="utf-8")
        readiness = (
            ROOT / ".github/workflows/hf-release-readiness-terminal.yml"
        ).read_text(encoding="utf-8")
        readiness_pr = (
            ROOT / ".github/workflows/hf-release-readiness-terminal-pr.yml"
        ).read_text(encoding="utf-8")
        reconciliation = (
            ROOT / ".github/workflows/final-estate-reconciliation-v5.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("schedule:", finalization)
        self.assertNotIn("gh workflow run hf-release-readiness", finalization)
        self.assertIn("workflow_run:", readiness)
        self.assertIn("HF Release Finalization — Supported Kernel Git", readiness)
        self.assertNotIn("pull_request:", readiness)
        self.assertNotIn("secrets.", readiness_pr)
        self.assertIn("permissions:\n  contents: read", readiness_pr)
        self.assertIn("workflow_run:", reconciliation)
        self.assertIn("HF Release Readiness Terminal", reconciliation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
