import json
import os
import tempfile
import types
import unittest
from enum import Enum
from pathlib import Path
from unittest import mock

import hf_static_space_deploy as deploy


class StaticSpaceDeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        for name, content in {
            ".gitattributes": "*.html text eol=lf\n",
            "README.md": "---\nsdk: static\n---\n",
            "index.html": '<body data-szl-surface="company-front-door"></body>\n',
        }.items():
            (self.root / "src" / name).write_text(content, encoding="utf-8")
        self.manifest = self.root / "manifest.json"
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, files=None):
        files = files or [
            {"source": "src/.gitattributes", "destination": ".gitattributes"},
            {"source": "src/README.md", "destination": "README.md"},
            {"source": "src/index.html", "destination": "index.html"},
        ]
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": deploy.SCHEMA,
                    "target": {
                        "repo_id": "SZLHOLDINGS/README",
                        "repo_type": "space",
                        "live_base_url": "https://example.hf.space",
                    },
                    "source_repository": "szl-holdings/.github",
                    "files": files,
                    "prune": True,
                    "allowed_deletions": [],
                    "smoke": {"path": "/", "required_marker": "company-front-door"},
                }
            ),
            encoding="utf-8",
        )

    def authority_env(self, source_sha="a" * 40, token="hf_test_token_redacted"):
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": source_sha,
            "GITHUB_WORKFLOW_REF": (
                "szl-holdings/.github/"
                ".github/workflows/hf-org-card-deploy.yml@refs/heads/main"
            ),
            "SZL_PUBLICATION_ENVIRONMENT": "production",
            "HF_TOKEN": token,
            "GITHUB_TOKEN": "ghp_test_token_redacted",
        }

    def test_contract_builds_exact_file_hashes(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        result = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )
        self.assertEqual(result["source"]["revision"], "a" * 40)
        self.assertEqual(
            [row["path"] for row in result["files"]],
            [".gitattributes", "README.md", "index.html"],
        )
        self.assertTrue(all(len(row["sha256"]) == 64 for row in result["files"]))

    def test_duplicate_destination_fails_closed(self):
        self.write_manifest(
            [
                {"source": "src/.gitattributes", "destination": ".gitattributes"},
                {"source": "src/README.md", "destination": "README.md"},
                {"source": "src/index.html", "destination": "index.html"},
                {"source": "src/README.md", "destination": "README.md"},
            ]
        )
        with self.assertRaisesRegex(deploy.ContractError, "duplicate destination"):
            deploy.load_contract(self.root, self.manifest)

    def test_traversal_destination_fails_closed(self):
        self.write_manifest(
            [
                {"source": "src/.gitattributes", "destination": ".gitattributes"},
                {"source": "src/README.md", "destination": "README.md"},
                {"source": "src/index.html", "destination": "../index.html"},
            ]
        )
        with self.assertRaisesRegex(deploy.ContractError, "unsafe destination"):
            deploy.load_contract(self.root, self.manifest)

    def test_windows_drive_relative_destination_fails_closed(self):
        self.write_manifest(
            [
                {"source": "src/.gitattributes", "destination": ".gitattributes"},
                {"source": "src/README.md", "destination": "README.md"},
                {"source": "src/index.html", "destination": "C:../escape"},
            ]
        )
        with self.assertRaisesRegex(deploy.ContractError, "unsafe destination"):
            deploy.load_contract(self.root, self.manifest)

    def test_deployment_path_is_reserved(self):
        self.write_manifest(
            [
                {"source": "src/.gitattributes", "destination": ".gitattributes"},
                {"source": "src/README.md", "destination": "README.md"},
                {"source": "src/index.html", "destination": "index.html"},
                {"source": "src/README.md", "destination": "deployment.json"},
            ]
        )
        with self.assertRaisesRegex(deploy.ContractError, "reserved destination"):
            deploy.load_contract(self.root, self.manifest)

    def test_space_stage_enum_is_normalized(self):
        class SpaceStage(Enum):
            RUNNING = "RUNNING"

        self.assertEqual(deploy.normalize_space_stage(SpaceStage.RUNNING), "RUNNING")
        self.assertEqual(deploy.normalize_space_stage("RUNNING"), "RUNNING")

    def test_same_revision_from_prior_attempt_is_rejected(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        current = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:02Z"
        )
        prior = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:01Z"
        )

        self.assertFalse(deploy.deployment_matches(prior, current))
        self.assertTrue(deploy.deployment_matches(current, current))

    def test_publish_authority_accepts_exact_protected_main_attempt(self):
        contract, _ = deploy.load_contract(self.root, self.manifest)
        deploy.assert_publish_authority(
            contract, "a" * 40, self.authority_env()
        )

    def test_publish_workflow_exports_exact_authority_environment(self):
        repo_root = Path(__file__).resolve().parents[2]
        workflow = (
            repo_root / ".github" / "workflows" / "hf-org-card-deploy.yml"
        ).read_text(encoding="utf-8")
        for required in (
            "environment: production",
            "GITHUB_TOKEN: ${{ github.token }}",
            "SZL_PUBLICATION_ENVIRONMENT: production",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)

    def test_publish_authority_rejects_branch_dispatch_and_rerun(self):
        contract, _ = deploy.load_contract(self.root, self.manifest)
        for name, value in {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/feature",
            "GITHUB_REF_PROTECTED": "false",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "b" * 40,
            "SZL_PUBLICATION_ENVIRONMENT": "staging",
        }.items():
            with self.subTest(name=name):
                environ = self.authority_env()
                environ[name] = value
                with self.assertRaisesRegex(
                    deploy.ContractError, "publication authority mismatch"
                ):
                    deploy.assert_publish_authority(contract, "a" * 40, environ)

    def test_every_served_file_requires_exact_origin_hash_and_size(self):
        _, files = deploy.load_contract(self.root, self.manifest)
        expected = {item.destination: item.source.read_bytes() for item in files}

        def exact_fetch(url, max_bytes=0):
            path = url.removeprefix("https://example.hf.space/")
            return 200, expected[path], url

        with mock.patch.object(deploy, "fetch", side_effect=exact_fetch):
            matches, rows = deploy.verify_served_files(
                "https://example.hf.space", files
            )
        self.assertTrue(matches)
        self.assertEqual(len(rows), len(files))
        self.assertTrue(all(row["matches"] for row in rows))

        def altered_fetch(url, max_bytes=0):
            path = url.removeprefix("https://example.hf.space/")
            data = expected[path]
            if path == "index.html":
                data += b"<!-- stale -->"
            return 200, data, url

        with mock.patch.object(deploy, "fetch", side_effect=altered_fetch):
            matches, rows = deploy.verify_served_files(
                "https://example.hf.space", files
            )
        self.assertFalse(matches)
        index_row = next(row for row in rows if row["path"] == "index.html")
        self.assertFalse(index_row["matches"])

    def test_hf_bootstrap_canonicalization_preserves_source_head_newline(self):
        source = (
            b"<!doctype html>\n<html lang=\"en\">\n<head>\n"
            b"  <meta charset=\"utf-8\">\n</head>\n</html>\n"
        )
        bootstrap = (
            b'<script>window.huggingface={variables:{'
            b'"SPACE_CREATOR_USER_ID":"69ec7d565e5561c3b16baba8"'
            b'}};</script>'
        )
        served = source.replace(b"<head>", b"<head>" + bootstrap, 1)

        self.assertEqual(deploy.canonicalize_hf_bootstrap(served), source)

    def test_served_file_redirect_or_fetch_error_fails_closed(self):
        _, files = deploy.load_contract(self.root, self.manifest)

        def unsafe_fetch(url, max_bytes=0):
            if url.endswith("README.md"):
                return 200, b"stale", "https://evil.example/README.md"
            raise TimeoutError("readback timeout")

        with mock.patch.object(deploy, "fetch", side_effect=unsafe_fetch):
            matches, rows = deploy.verify_served_files(
                "https://example.hf.space", files
            )
        self.assertFalse(matches)
        self.assertTrue(any(not row["same_origin"] for row in rows))
        self.assertTrue(any("error" in row for row in rows))

    def test_prune_aborts_on_unexpected_remote_path(self):
        contract, _ = deploy.load_contract(self.root, self.manifest)
        with self.assertRaisesRegex(deploy.ContractError, "unexpected remote paths"):
            deploy.planned_deletions(
                contract,
                {"README.md", "index.html", "unmanaged.txt"},
                {"README.md", "index.html"},
            )

    def test_prune_accepts_explicit_deletion(self):
        contract, _ = deploy.load_contract(self.root, self.manifest)
        contract["allowed_deletions"] = ["retired.txt"]
        self.assertEqual(
            deploy.planned_deletions(
                contract,
                {"README.md", "retired.txt"},
                {"README.md"},
            ),
            ["retired.txt"],
        )

    def test_prune_with_no_delta_deletes_nothing(self):
        contract, _ = deploy.load_contract(self.root, self.manifest)
        self.assertEqual(
            deploy.planned_deletions(
                contract,
                {"README.md", "deployment.json"},
                {"README.md", "deployment.json"},
            ),
            [],
        )

    def test_materialize_builds_manifest_mapped_preview_asset(self):
        (self.root / "src" / "hero.webp").write_bytes(b"RIFFmockWEBP")
        self.write_manifest(
            [
                {"source": "src/.gitattributes", "destination": ".gitattributes"},
                {"source": "src/README.md", "destination": "README.md"},
                {"source": "src/index.html", "destination": "index.html"},
                {"source": "src/hero.webp", "destination": "assets/hero.webp"},
            ]
        )
        contract, files = deploy.load_contract(self.root, self.manifest)
        deployment = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )
        preview = self.root / "preview"
        outputs = deploy.materialize(preview, files, deployment)
        self.assertIn(preview / "assets" / "hero.webp", outputs)
        self.assertEqual(
            (preview / "assets" / "hero.webp").read_bytes(), b"RIFFmockWEBP"
        )
        self.assertTrue((preview / "deployment.json").is_file())

    def test_materialize_refuses_nonempty_output_directory(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        deployment = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )
        preview = self.root / "nonempty-preview"
        preview.mkdir()
        (preview / "stale.txt").write_text("stale", encoding="utf-8")
        with self.assertRaisesRegex(deploy.ContractError, "must be empty"):
            deploy.materialize(preview, files, deployment)

    def test_materialize_rechecks_destination_containment(self):
        source = self.root / "src" / "README.md"
        unsafe = deploy.PublicationFile(
            source, "../escape", "0" * 64, source.stat().st_size
        )
        with self.assertRaisesRegex(deploy.ContractError, "escapes output root"):
            deploy.materialize(self.root / "contained-preview", [unsafe], {})

    def test_post_commit_timeout_preserves_remote_mutation_evidence(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        deployment = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )

        class FakeApi:
            def __init__(self, token):
                self.token = token

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(sha="b" * 40)

            def list_repo_files(self, **kwargs):
                return [".gitattributes", "README.md", "index.html", "deployment.json"]

            def create_commit(self, **kwargs):
                return types.SimpleNamespace(oid="c" * 40)

            def get_space_runtime(self, **kwargs):
                raise TimeoutError("readback timed out")

        fake_hub = types.SimpleNamespace(
            CommitOperationAdd=lambda **kwargs: kwargs,
            CommitOperationDelete=lambda **kwargs: kwargs,
            HfApi=FakeApi,
        )
        with (
            mock.patch.dict("sys.modules", {"huggingface_hub": fake_hub}),
            mock.patch.object(deploy.time, "monotonic", side_effect=[0.0, 0.0, 1.0]),
            mock.patch.object(deploy.time, "sleep"),
        ):
            with self.assertRaises(deploy.PublicationVerificationError) as caught:
                deploy.publish(
                    contract,
                    files,
                    deployment,
                    "hf_test_token_redacted",
                    "ghp_test_token_redacted",
                    1,
                    main_sha_lookup=lambda *_, **__: "a" * 40,
                )
        self.assertEqual(caught.exception.result["state"], "COMMIT_CREATED_UNVERIFIED")
        self.assertEqual(caught.exception.result["hf_commit"], "c" * 40)
        self.assertEqual(caught.exception.result["deleted_paths"], [])
        self.assertIn("readback timed out", str(caught.exception))

    def test_cross_origin_readback_cannot_verify_created_commit(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        deployment = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )

        class FakeApi:
            def __init__(self, token):
                self.token = token

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(sha="b" * 40)

            def list_repo_files(self, **kwargs):
                return [".gitattributes", "README.md", "index.html", "deployment.json"]

            def create_commit(self, **kwargs):
                return types.SimpleNamespace(oid="c" * 40)

            def get_space_runtime(self, **kwargs):
                return types.SimpleNamespace(stage="RUNNING")

        fake_hub = types.SimpleNamespace(
            CommitOperationAdd=lambda **kwargs: kwargs,
            CommitOperationDelete=lambda **kwargs: kwargs,
            HfApi=FakeApi,
        )
        responses = [
            (
                200,
                deploy.canonical_json(deployment),
                "https://evil.example/deployment.json",
            ),
            (200, b"company-front-door", "https://evil.example/"),
        ]
        with (
            mock.patch.dict("sys.modules", {"huggingface_hub": fake_hub}),
            mock.patch.object(deploy.time, "monotonic", side_effect=[0.0, 0.0, 1.0]),
            mock.patch.object(deploy.time, "sleep"),
            mock.patch.object(deploy, "fetch", side_effect=responses),
        ):
            with self.assertRaises(deploy.PublicationVerificationError) as caught:
                deploy.publish(
                    contract,
                    files,
                    deployment,
                    "hf_test_token_redacted",
                    "ghp_test_token_redacted",
                    1,
                    main_sha_lookup=lambda *_, **__: "a" * 40,
                )
        result = caught.exception.result
        self.assertEqual(result["state"], "COMMIT_CREATED_UNVERIFIED")
        self.assertEqual(result["hf_commit"], "c" * 40)
        self.assertFalse(result["manifest_same_origin"])
        self.assertFalse(result["smoke_same_origin"])
        self.assertIsNone(result["live_source_revision"])

    def test_malformed_live_source_preserves_created_commit_evidence(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        deployment = deploy.build_deployment(
            contract, files, "a" * 40, "2026-08-01T00:00:00Z"
        )

        class FakeApi:
            def __init__(self, token):
                self.token = token

            def repo_info(self, **kwargs):
                return types.SimpleNamespace(sha="b" * 40)

            def list_repo_files(self, **kwargs):
                return [".gitattributes", "README.md", "index.html", "deployment.json"]

            def create_commit(self, **kwargs):
                return types.SimpleNamespace(oid="c" * 40)

            def get_space_runtime(self, **kwargs):
                return types.SimpleNamespace(stage="RUNNING")

        fake_hub = types.SimpleNamespace(
            CommitOperationAdd=lambda **kwargs: kwargs,
            CommitOperationDelete=lambda **kwargs: kwargs,
            HfApi=FakeApi,
        )
        responses = [
            (200, b'{"source":null}', "https://example.hf.space/deployment.json"),
            (200, b"company-front-door", "https://example.hf.space/"),
        ]
        with (
            mock.patch.dict("sys.modules", {"huggingface_hub": fake_hub}),
            mock.patch.object(deploy.time, "monotonic", side_effect=[0.0, 0.0, 1.0]),
            mock.patch.object(deploy.time, "sleep"),
            mock.patch.object(deploy, "fetch", side_effect=responses),
        ):
            with self.assertRaises(deploy.PublicationVerificationError) as caught:
                deploy.publish(
                    contract,
                    files,
                    deployment,
                    "hf_test_token_redacted",
                    "ghp_test_token_redacted",
                    1,
                    main_sha_lookup=lambda *_, **__: "a" * 40,
                )
        result = caught.exception.result
        self.assertEqual(result["state"], "COMMIT_CREATED_UNVERIFIED")
        self.assertEqual(result["hf_commit"], "c" * 40)
        self.assertTrue(result["manifest_same_origin"])
        self.assertTrue(result["smoke_same_origin"])
        self.assertIsNone(result["live_source_revision"])

    def test_main_preserves_unverified_commit_state_in_report(self):
        report = self.root / "unverified-report.json"
        argv = [
            "hf_static_space_deploy.py",
            "--repo-root",
            str(self.root),
            "--manifest",
            str(self.manifest),
            "--source-sha",
            "a" * 40,
            "--publish",
            "--report",
            str(report),
        ]
        partial = {
            "state": "COMMIT_CREATED_UNVERIFIED",
            "hf_commit": "c" * 40,
            "deleted_paths": [],
        }
        with (
            mock.patch("sys.argv", argv),
            mock.patch.dict(os.environ, self.authority_env(), clear=True),
            mock.patch.object(deploy, "local_head_sha", return_value="a" * 40),
            mock.patch.object(
                deploy,
                "publish",
                side_effect=deploy.PublicationVerificationError("timeout", partial),
            ),
        ):
            self.assertEqual(deploy.main(), 1)
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "COMMIT_CREATED_UNVERIFIED")
        self.assertEqual(result["hf_commit"], "c" * 40)
        self.assertIn("timeout", result["error"])

    def test_publish_preflight_error_writes_failed_report(self):
        report = self.root / "report.json"
        argv = [
            "hf_static_space_deploy.py",
            "--repo-root",
            str(self.root),
            "--manifest",
            str(self.manifest),
            "--source-sha",
            "a" * 40,
            "--publish",
            "--report",
            str(report),
        ]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.dict(os.environ, self.authority_env(token=""), clear=True),
            mock.patch.object(deploy, "local_head_sha", return_value="a" * 40),
        ):
            self.assertEqual(deploy.main(), 1)
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "FAILED")
        self.assertIn("HF_TOKEN is required", result["error"])


if __name__ == "__main__":
    unittest.main()
