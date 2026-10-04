#!/usr/bin/env python3
from __future__ import annotations

import inspect
import pathlib
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import contextmanager
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hf_release_finalization_git as finalizer  # noqa: E402
from kernel_hub_git import KernelPublication, KernelSnapshot  # noqa: E402


class FakeTransport:
    def __init__(self, publication=None, snapshot=None):
        self.publication = publication
        self.snapshot_value = snapshot
        self.publish_calls = []
        self.snapshot_calls = []
        self.materialize_calls = []

    def publish(self, **kwargs):
        self.publish_calls.append(kwargs)
        return self.publication

    def snapshot(self, repo_id):
        self.snapshot_calls.append(repo_id)
        return self.snapshot_value

    @contextmanager
    def materialize_build(self, repo_id, revision):
        self.materialize_calls.append((repo_id, revision))
        yield pathlib.Path("materialized-kernel")


class FakeApi:
    def __init__(self, revision="a" * 40, error=None):
        self.revision = revision
        self.error = error

    def kernel_info(self, repo_id):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(sha=self.revision)


class KernelGitFinalizerTests(unittest.TestCase):
    def setUp(self):
        # Provider fixtures must explicitly supply the separately tested source gate.
        patcher = unittest.mock.patch("hf_release_sources.verify", return_value={"fixture": "SYNTHETIC"})
        self.source_guard = patcher.start()
        self.addCleanup(patcher.stop)

    def make_instance(self, *, publish=True, stub_selfcheck=True):
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        source = root / "energy" / "hf-kernels" / "example"
        source.mkdir(parents=True)
        (source / "README.md").write_text("card\n")
        (source / "contract.json").write_text("{}\n")
        publication = KernelPublication(
            repo_id="SZLHOLDINGS/example",
            before_revision="a" * 40,
            revision="b" * 40,
            changed=True,
            remote_file_count=3,
            build_variants_preserved=True,
            card_contract_byte_parity=True,
            build_tree_sha256="c" * 64,
            remote_url="https://huggingface.co/kernels/SZLHOLDINGS/example",
        )
        instance = object.__new__(finalizer.KernelGitFinalizer)
        instance.token = "token"
        instance.publish = publish
        instance.generation = "d" * 40
        instance.roots = {"energy": root / "energy"}
        instance.api = FakeApi()
        instance.kernel_transport = FakeTransport(publication=publication)
        instance.actions = []
        instance.results = {}
        if stub_selfcheck:
            instance._kernel_selfcheck = lambda repo_id, revision: {"ok": True}
        return tmp, instance

    def test_failed_source_guard_prevents_existing_kernel_publish(self):
        temporary, instance = self.make_instance()
        self.addCleanup(temporary.cleanup)
        self.source_guard.side_effect = RuntimeError("SYNTHETIC source moved")
        with self.assertRaisesRegex(RuntimeError, "source moved"):
            instance.finalize_kernel("SZLHOLDINGS/example", {"source_root": "energy", "source_dir": "hf-kernels/example"})
        self.assertEqual(instance.kernel_transport.publish_calls, [])

    def test_source_movement_after_publish_prevents_success_evidence(self):
        temporary, instance = self.make_instance()
        self.addCleanup(temporary.cleanup)
        self.source_guard.side_effect = [{}, RuntimeError("SYNTHETIC source moved after effect")]
        with self.assertRaisesRegex(RuntimeError, "after effect"):
            instance.finalize_kernel("SZLHOLDINGS/example", {"source_root": "energy", "source_dir": "hf-kernels/example"})
        self.assertEqual(len(instance.kernel_transport.publish_calls), 1)
        self.assertNotIn("kernels", instance.results)

    def test_kernel_publication_delegates_to_git_transport(self):
        tmp, instance = self.make_instance()
        try:
            instance.finalize_kernel(
                "SZLHOLDINGS/example",
                {"source_root": "energy", "source_dir": "hf-kernels/example"},
            )
            self.assertEqual(len(instance.kernel_transport.publish_calls), 1)
            result = instance.results["kernels"]["SZLHOLDINGS/example"]
            self.assertEqual(result["transport"], "authenticated-kernel-hub-git")
            self.assertEqual(result["revision"], "b" * 40)
            self.assertTrue(result["build_variants_preserved"])
            self.assertTrue(result["card_contract_byte_parity"])
        finally:
            tmp.cleanup()

    def test_empty_kernel_api_builds_fall_back_to_authenticated_git(self):
        tmp, instance = self.make_instance()
        instance.api = FakeApi(error=ValueError("min() iterable argument is empty"))
        instance.kernel_transport.snapshot_value = KernelSnapshot(
            repo_id="SZLHOLDINGS/example",
            revision="a" * 40,
            files=("README.md", "contract.json", "build/cpu/__init__.py"),
            build_tree_sha256="c" * 64,
            remote_url="https://huggingface.co/kernels/SZLHOLDINGS/example",
        )
        try:
            instance.finalize_kernel(
                "SZLHOLDINGS/example",
                {"source_root": "energy", "source_dir": "hf-kernels/example"},
            )
            call = instance.kernel_transport.publish_calls[0]
            self.assertEqual(call["metadata_revision"], "a" * 40)
            result = instance.results["kernels"]["SZLHOLDINGS/example"]
            self.assertEqual(
                result["metadata_revision_source"],
                "authenticated-kernel-hub-git-fallback",
            )
        finally:
            tmp.cleanup()

    def test_unrelated_kernel_api_value_error_still_fails_closed(self):
        tmp, instance = self.make_instance()
        instance.api = FakeApi(error=ValueError("malformed kernel metadata"))
        try:
            with self.assertRaisesRegex(ValueError, "malformed kernel metadata"):
                instance.finalize_kernel(
                    "SZLHOLDINGS/example",
                    {"source_root": "energy", "source_dir": "hf-kernels/example"},
                )
            self.assertFalse(instance.kernel_transport.publish_calls)
        finally:
            tmp.cleanup()

    def test_controller_selfcheck_falls_back_to_exact_git_build(self):
        tmp, instance = self.make_instance(stub_selfcheck=False)
        module = SimpleNamespace(selfcheck=lambda: {"ok": True, "source": "git"})
        fake_kernels = SimpleNamespace(
            get_kernel=unittest.mock.Mock(
                side_effect=ValueError("min() iterable argument is empty")
            ),
            get_local_kernel=unittest.mock.Mock(return_value=module),
        )
        try:
            with unittest.mock.patch.dict(sys.modules, {"kernels": fake_kernels}):
                instance.finalize_kernel(
                    "SZLHOLDINGS/example",
                    {"source_root": "energy", "source_dir": "hf-kernels/example"},
                )

            self.assertEqual(
                instance.kernel_transport.materialize_calls,
                [("SZLHOLDINGS/example", "b" * 40)],
            )
            fake_kernels.get_local_kernel.assert_called_once_with(
                pathlib.Path("materialized-kernel")
            )
            result = instance.results["kernels"]["SZLHOLDINGS/example"]
            self.assertEqual(
                result["selfcheck_transport"],
                "authenticated-kernel-hub-git-fallback",
            )
            self.assertEqual(result["selfcheck"], {"ok": True, "source": "git"})
        finally:
            tmp.cleanup()

    def test_controller_selfcheck_rejects_unrelated_value_error(self):
        tmp, instance = self.make_instance(stub_selfcheck=False)
        fake_kernels = SimpleNamespace(
            get_kernel=unittest.mock.Mock(
                side_effect=ValueError("malformed build metadata")
            ),
            get_local_kernel=unittest.mock.Mock(),
        )
        try:
            with unittest.mock.patch.dict(sys.modules, {"kernels": fake_kernels}):
                with self.assertRaisesRegex(ValueError, "malformed build metadata"):
                    instance.finalize_kernel(
                        "SZLHOLDINGS/example",
                        {"source_root": "energy", "source_dir": "hf-kernels/example"},
                    )
            self.assertFalse(instance.kernel_transport.materialize_calls)
        finally:
            tmp.cleanup()

    def test_selfcheck_fallback_is_revision_bound_and_metadata_api_free(self):
        tmp, instance = self.make_instance(stub_selfcheck=False)
        instance.api = unittest.mock.Mock()
        module = SimpleNamespace(selfcheck=lambda: {"ok": True})
        fake_kernels = SimpleNamespace(
            get_kernel=unittest.mock.Mock(
                side_effect=ValueError("min() iterable argument is empty")
            ),
            get_local_kernel=unittest.mock.Mock(return_value=module),
        )
        try:
            with unittest.mock.patch.dict(sys.modules, {"kernels": fake_kernels}):
                result = finalizer.KernelGitFinalizer._kernel_selfcheck(
                    instance,
                    "SZLHOLDINGS/example",
                    "e" * 40,
                )

            self.assertEqual(result, {"ok": True})
            self.assertEqual(instance.api.mock_calls, [])
            self.assertEqual(
                instance.kernel_transport.materialize_calls,
                [("SZLHOLDINGS/example", "e" * 40)],
            )
            fake_kernels.get_local_kernel.assert_called_once_with(
                pathlib.Path("materialized-kernel")
            )
        finally:
            tmp.cleanup()

    def test_pull_request_snapshot_is_read_only_and_fail_closed(self):
        tmp, instance = self.make_instance(publish=False)
        instance.kernel_transport = FakeTransport(
            snapshot=KernelSnapshot(
                repo_id="SZLHOLDINGS/example",
                revision="a" * 40,
                files=("README.md", "contract.json", "build/cpu/__init__.py"),
                build_tree_sha256="c" * 64,
                remote_url="https://huggingface.co/kernels/SZLHOLDINGS/example",
            )
        )
        try:
            instance.finalize_kernel(
                "SZLHOLDINGS/example",
                {"source_root": "energy", "source_dir": "hf-kernels/example"},
            )
            self.assertEqual(
                instance.kernel_transport.snapshot_calls,
                ["SZLHOLDINGS/example"],
            )
            self.assertFalse(instance.kernel_transport.publish_calls)
        finally:
            tmp.cleanup()

    def test_report_normalizes_immutable_revision_schema(self):
        instance = object.__new__(finalizer.KernelGitFinalizer)
        with (
            unittest.mock.patch.object(
                finalizer.retry.RetryingFinalizer,
                "report",
                return_value={
                    "schema": "old",
                    "results": {
                        "dataset": {"after_sha": "a" * 40},
                        "kernels": {"k": {"after_sha": "b" * 40}},
                    },
                    "boundaries": ["base boundary"],
                },
            ),
            unittest.mock.patch.object(
                finalizer.KernelGitFinalizer,
                "_runtime",
                return_value={"numpy": "2.2.6", "torch": "2.7.1+cpu"},
            ),
        ):
            report = instance.report()
        self.assertEqual(report["schema"], finalizer.REPORT_SCHEMA)
        self.assertEqual(report["results"]["dataset"]["revision"], "a" * 40)
        self.assertEqual(report["results"]["kernels"]["k"]["revision"], "b" * 40)
        self.assertIn("base boundary", report["boundaries"])
        self.assertIn(finalizer.legacy.PROVIDER_SCOPE_BOUNDARY, report["boundaries"])

    def test_active_kernel_method_contains_no_generic_kernel_repo_type(self):
        source = inspect.getsource(finalizer.KernelGitFinalizer.finalize_kernel)
        self.assertNotIn('repo_type="kernel"', source)
        self.assertNotIn("hf_hub_download", source)
        self.assertNotIn("upload_file", source)
        self.assertIn("kernel_transport.publish", source)

    def test_source_has_no_model_space_or_hardware_mutation(self):
        source = pathlib.Path(finalizer.__file__).read_text(encoding="utf-8")
        for forbidden in (
            'repo_type="model"',
            'repo_type="space"',
            "set_space_hardware",
            "request_space_hardware",
            "update_repo_settings",
            "train(",
            "merge_weights",
        ):
            self.assertNotIn(forbidden, source)

    def test_pr_verification_is_credentialless_and_read_only(self):
        workflows = HERE.parent / "workflows"
        publication = (workflows / "hf-release-finalization.yml").read_text(
            encoding="utf-8"
        )
        pull_request = (workflows / "hf-release-finalization-pr.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("pull_request:", publication)
        self.assertIn("workflow_dispatch:", publication)
        self.assertIn("group: hf-release-finalization-publication", publication)
        self.assertNotIn("issues: write", publication)
        self.assertNotIn("actions: write", publication)
        self.assertNotIn("gh workflow run hf-release-readiness", publication)
        self.assertIn(
            "HF Release Readiness Terminal is triggered by workflow_run",
            publication,
        )
        job_before_steps = publication.split("    steps:", 1)[0]
        self.assertNotIn("secrets.", job_before_steps)
        self.assertNotIn("GH_TOKEN", job_before_steps)
        finalize_step = publication.split(
            "      - name: Finalize and independently verify exact revisions", 1
        )[1].split("      - name:", 1)[0]
        self.assertIn("secrets.HF_ORG_TOKEN", finalize_step)
        self.assertIn("secrets.HF_TOKEN", finalize_step)
        self.assertNotIn("Persist deterministic publication issue", publication)
        self.assertNotIn("gh issue", publication)
        self.assertEqual(publication.count("HF_ORG_TOKEN: ${{"), 1)
        self.assertEqual(publication.count("HF_TOKEN: ${{"), 1)
        self.assertEqual(publication.count("GH_TOKEN: ${{"), 0)

        self.assertIn("pull_request:", pull_request)
        self.assertNotIn("secrets.", pull_request)
        self.assertNotIn("issues: write", pull_request)
        self.assertNotIn("actions: write", pull_request)
        self.assertIn("permissions:\n  contents: read", pull_request)


if __name__ == "__main__":
    unittest.main(verbosity=2)
