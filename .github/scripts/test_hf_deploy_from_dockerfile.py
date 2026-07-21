#!/usr/bin/env python3
"""Self-test for the reusable HF deployer's Dockerfile-COPY derivation.

The deployer REPLACES a hand-maintained file allowlist with a derivation from the
caller Dockerfile's own COPY sources, so the derivation IS the correctness
contract. These locks pin the parts that have already burned us:

  * `COPY --from=<stage>` must NOT contribute deploy files (build-stage
    artifacts are not repo source-of-truth files);
  * a bare `COPY . <dest>` whole-context copy must FAIL CLOSED;
  * a dotdir source like `.compliance/x` must survive parsing -- an earlier
    `lstrip("./")` collapsed it to `compliance/x` and dropped 5 killinchu files;
  * directory / glob / explicit-file COPY sources must each expand to the right
    concrete tracked file set, and a missing source must be reported, not pushed.

Runs with NO network (derivation + expansion are pure stdlib).
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_deploy_from_dockerfile.py")

_spec = importlib.util.spec_from_file_location("hf_deploy_from_dockerfile", _MODULE_PATH)
assert _spec and _spec.loader
dep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dep)


class TestParseCopySources(unittest.TestCase):
    def test_basic_per_file_copy(self):
        df = "FROM python:3.12\nCOPY serve.py /app/serve.py\nCOPY src /app/src\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_skips_from_stage_copy(self):
        df = (
            "FROM node AS build\n"
            "RUN echo hi\n"
            "FROM python:3.12\n"
            "COPY --from=build /out/bundle.js /app/static/bundle.js\n"
            "COPY serve.py /app/serve.py\n"
        )
        # The --from artifact must NOT appear; only the real repo source does.
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])

    def test_rejects_bare_whole_context(self):
        df = "FROM python:3.12\nCOPY . /app\nCOPY serve.py /app/serve.py\n"
        with self.assertRaisesRegex(dep.DeployContractError, "explicit curated"):
            dep.parse_copy_sources(df)

    def test_rejects_dot_slash_whole_context(self):
        df = "FROM python:3.12\nCOPY ./ /app\n"
        with self.assertRaises(dep.DeployContractError):
            dep.parse_copy_sources(df)

    def test_rejects_json_form_whole_context(self):
        df = 'FROM python:3.12\nCOPY [".", "/app"]\n'
        with self.assertRaises(dep.DeployContractError):
            dep.parse_copy_sources(df)

    def test_rejects_malformed_json_form(self):
        df = 'FROM python:3.12\nCOPY ["serve.py", "/app/"\n'
        with self.assertRaisesRegex(dep.DeployContractError, "malformed JSON"):
            dep.parse_copy_sources(df)

    def test_dotdir_source_preserved(self):
        # The killinchu trap: leading-dot dir must NOT be stripped to a non-dot dir.
        df = "FROM python:3.12\nCOPY .compliance/policy.json /app/.compliance/policy.json\n"
        self.assertEqual(dep.parse_copy_sources(df), [".compliance/policy.json"])

    def test_leading_dot_slash_stripped_but_dotdir_kept(self):
        df = (
            "FROM python:3.12\n"
            "COPY ./serve.py /app/serve.py\n"
            "COPY .well-known/x /app/.well-known/x\n"
        )
        self.assertEqual(
            dep.parse_copy_sources(df), ["serve.py", ".well-known/x"]
        )

    def test_line_continuation_and_multi_source(self):
        df = "FROM python:3.12\nCOPY a.py b.py \\\n     c.py /app/\n"
        self.assertEqual(dep.parse_copy_sources(df), ["a.py", "b.py", "c.py"])

    def test_json_array_form(self):
        df = 'FROM python:3.12\nCOPY ["serve.py", "src", "/app/"]\n'
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_chown_flag_dropped_source_kept(self):
        df = "FROM python:3.12\nCOPY --chown=1000:1000 serve.py /app/serve.py\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])

    def test_dedup_preserves_order(self):
        df = (
            "FROM python:3.12\n"
            "COPY serve.py /app/serve.py\n"
            "COPY src /app/src\n"
            "COPY serve.py /app/serve.py\n"
        )
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_comments_ignored(self):
        df = "FROM python:3.12\n# COPY ghost.py /app/ghost.py\nCOPY serve.py /app/\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])


class TestExpandSources(unittest.TestCase):
    def setUp(self):
        self.tree = {
            "serve.py": "h1",
            "src/a.py": "h2",
            "src/sub/b.py": "h3",
            "static/app.css": "h4",
            "static/img/logo.png": "h5",
            "knowledge.json": "h6",
        }

    def test_explicit_file(self):
        targets, unresolved = dep.expand_sources(["serve.py"], self.tree)
        self.assertEqual(targets, {"serve.py": "serve.py"})
        self.assertEqual(unresolved, [])

    def test_directory_expands_recursively(self):
        targets, unresolved = dep.expand_sources(["src"], self.tree)
        self.assertEqual(
            set(targets), {"src/a.py", "src/sub/b.py"}
        )
        self.assertEqual(unresolved, [])
        # copy_source recorded for prune scoping
        self.assertEqual(targets["src/a.py"], "src")

    def test_trailing_slash_directory(self):
        targets, _ = dep.expand_sources(["static/"], self.tree)
        self.assertEqual(
            set(targets), {"static/app.css", "static/img/logo.png"}
        )

    def test_glob_source(self):
        # NOTE: glob expansion uses fnmatch, whose `*` is NOT `/`-aware (unlike
        # Docker's Go filepath.Match), so `src/*.py` also matches nested files.
        # This is intentionally over-inclusive (still a strict subset of tracked
        # repo files); the real Dockerfiles use dir/file COPY, not globs.
        targets, unresolved = dep.expand_sources(["src/*.py"], self.tree)
        self.assertEqual(set(targets), {"src/a.py", "src/sub/b.py"})
        self.assertEqual(unresolved, [])

    def test_top_level_glob(self):
        targets, unresolved = dep.expand_sources(["*.json"], self.tree)
        self.assertEqual(set(targets), {"knowledge.json"})
        self.assertEqual(unresolved, [])

    def test_unresolved_source_reported_not_pushed(self):
        targets, unresolved = dep.expand_sources(["missing/thing.py"], self.tree)
        self.assertEqual(targets, {})
        self.assertEqual(unresolved, ["missing/thing.py"])


class TestDeriveReadmePolicy(unittest.TestCase):
    def _derive(
        self, dockerfile, files, *, include_readme, readme_path="README.md",
        dockerfile_path="Dockerfile", smoke_paths=None,
    ):
        with tempfile.TemporaryDirectory() as repo_root:
            for rel, content in {dockerfile_path: dockerfile, **files}.items():
                path = os.path.join(repo_root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(content.encode("utf-8"))
            args = types.SimpleNamespace(
                repo_root=repo_root,
                dockerfile_path=dockerfile_path,
                include_readme=include_readme,
                readme_path=readme_path,
                github_repo="szl-holdings/example",
                hf_repo="SZLHOLDINGS/example",
                ref="main",
                smoke_paths=smoke_paths,
            )
            return dep.derive(args)

    def test_include_readme_false_filters_explicit_copy(self):
        manifest, files = self._derive(
            "FROM scratch\n"
            "COPY README.md /app/README.md\n"
            "COPY serve.py /app/serve.py\n",
            {"README.md": "# GitHub-only README\n", "serve.py": "pass\n"},
            include_readme=False,
            readme_path="./README.md",
        )

        self.assertEqual(set(files), {"Dockerfile", "serve.py"})
        self.assertEqual(manifest["files_resolved"], 1)
        self.assertIsNone(manifest["readme"])
        self.assertEqual(files["Dockerfile"]["source_path"], "Dockerfile")

    def test_include_readme_false_keeps_unrelated_nested_readme(self):
        manifest, files = self._derive(
            "FROM scratch\n"
            "COPY README.md /app/README.md\n"
            "COPY docs /app/docs\n",
            {
                "README.md": "# Space-card-owned README\n",
                "docs/README.md": "# App documentation\n",
            },
            include_readme=False,
        )

        self.assertEqual(set(files), {"Dockerfile", "docs/README.md"})
        self.assertEqual(manifest["files_resolved"], 1)

    def test_include_readme_true_merges_derived_entry_as_readme(self):
        readme = "---\nsdk: docker\napp_port: 7860\n---\n# Space card\n"
        manifest, files = self._derive(
            "FROM scratch\nCOPY README.md /app/README.md\n",
            {"README.md": readme},
            include_readme=True,
        )

        self.assertEqual(set(files), {"Dockerfile", "README.md"})
        self.assertEqual(files["README.md"]["copy_source"], "(readme)")
        self.assertEqual(files["README.md"]["sha256"], dep.sha256(readme.encode()))
        self.assertEqual(manifest["readme"], "README.md")

    def test_nested_yarqa_dockerfile_maps_to_hf_root_and_hashes_source(self):
        dockerfile = "FROM scratch\nCOPY space/app.py /app/app.py\n"
        manifest, files = self._derive(
            dockerfile,
            {"space/app.py": "print('yarqa')\n"},
            include_readme=False,
            dockerfile_path="space/Dockerfile",
        )

        self.assertEqual(manifest["dockerfile"], "space/Dockerfile")
        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(manifest["dockerfile_target"], "Dockerfile")
        self.assertEqual(files["Dockerfile"]["source_path"], "space/Dockerfile")
        self.assertEqual(files["Dockerfile"]["copy_source"], "(dockerfile)")
        self.assertEqual(
            files["Dockerfile"]["sha256"], dep.sha256(dockerfile.encode())
        )

    def test_unresolved_copy_source_fails_closed(self):
        with self.assertRaisesRegex(dep.DeployContractError, "not found"):
            self._derive(
                "FROM scratch\nCOPY missing.py /app/missing.py\n",
                {},
                include_readme=False,
            )

    def test_manifest_smoke_paths_default_to_root(self):
        manifest, _ = self._derive(
            "FROM scratch\nCOPY app.py /app/app.py\n",
            {"app.py": "pass\n"},
            include_readme=False,
        )
        self.assertEqual(manifest["smoke_paths"], ["/"])

    def test_manifest_records_valid_declared_smoke_paths(self):
        manifest, _ = self._derive(
            "FROM scratch\nCOPY app.py /app/app.py\n",
            {"app.py": "pass\n"},
            include_readme=False,
            smoke_paths='["/", "/openapi.json", "/health?deep=1"]',
        )
        self.assertEqual(
            manifest["smoke_paths"], ["/", "/openapi.json", "/health?deep=1"]
        )


class TestSourcePathMapping(unittest.TestCase):
    def test_reads_declared_source_path_not_hf_target_path(self):
        with tempfile.TemporaryDirectory() as repo_root:
            nested = os.path.join(repo_root, "space", "Dockerfile")
            os.makedirs(os.path.dirname(nested), exist_ok=True)
            with open(nested, "wb") as fh:
                fh.write(b"FROM scratch\n")

            data = dep.read_source_bytes(
                repo_root, "Dockerfile", {"source_path": "space/Dockerfile"}
            )
            self.assertEqual(data, b"FROM scratch\n")

    def test_add_operation_uses_mapped_source_bytes_for_hf_target(self):
        captured = []

        def operation(**kwargs):
            captured.append(kwargs)
            return kwargs

        with tempfile.TemporaryDirectory() as repo_root:
            nested = os.path.join(repo_root, "space", "Dockerfile")
            os.makedirs(os.path.dirname(nested), exist_ok=True)
            data = b"FROM python:3.12\n"
            with open(nested, "wb") as fh:
                fh.write(data)
            files = {
                "Dockerfile": {
                    "source_path": "space/Dockerfile",
                    "sha256": dep.sha256(data),
                }
            }
            operations = dep.build_add_operations(repo_root, files, operation)

        self.assertEqual(operations, captured)
        self.assertEqual(captured[0]["path_in_repo"], "Dockerfile")
        self.assertEqual(captured[0]["path_or_fileobj"], data)

    def test_rejects_source_path_escape(self):
        with tempfile.TemporaryDirectory() as repo_root:
            with self.assertRaises(dep.DeployContractError):
                dep.read_source_bytes(
                    repo_root, "Dockerfile", {"source_path": "../Dockerfile"}
                )


class TestSmokePathPolicy(unittest.TestCase):
    def test_default_and_deduplication(self):
        self.assertEqual(dep.normalize_smoke_paths(), ["/"])
        self.assertEqual(
            dep.normalize_smoke_paths('["/", "/health", "/health"]'),
            ["/", "/health"],
        )

    def test_rejects_external_absolute_and_scheme_relative_urls(self):
        bad = [
            '["https://example.com/"]',
            '["http://example.com/"]',
            '["//example.com/"]',
            '["relative"]',
            '["/ok#fragment"]',
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(dep.DeployContractError):
                    dep.normalize_smoke_paths(value)

    def test_live_origin_is_derived_only_from_repo_id(self):
        self.assertEqual(
            dep.hf_live_origin("SZLHOLDINGS/a11oy"),
            "https://szlholdings-a11oy.hf.space",
        )
        with self.assertRaises(dep.DeployContractError):
            dep.hf_live_origin("https://evil.example/space")


class TestRuntimeIdentity(unittest.TestCase):
    def test_space_api_state_returns_stage_and_exact_sha(self):
        oid = "a" * 40
        payload = json.dumps({"sha": oid, "runtime": {"stage": "RUNNING"}}).encode()
        with mock.patch.object(dep, "_http", return_value=(200, payload)):
            self.assertEqual(
                dep.hf_space_state("SZLHOLDINGS/a11oy"), ("RUNNING", oid)
            )

    def test_space_api_non_200_is_not_an_unknown_success(self):
        with mock.patch.object(dep, "_http", return_value=(503, b"")):
            with self.assertRaises(RuntimeError):
                dep.hf_space_state("SZLHOLDINGS/a11oy")

    def test_exact_running_commit_passes(self):
        oid = "a" * 40
        with mock.patch.object(dep, "hf_space_state", return_value=("RUNNING", oid)):
            self.assertTrue(dep.wait_for_expected_runtime("SZLHOLDINGS/a11oy", oid, 0))

    def test_running_old_commit_fails_at_timeout(self):
        oid = "a" * 40
        with mock.patch.object(dep, "hf_space_state", return_value=("RUNNING", "b" * 40)):
            self.assertFalse(dep.wait_for_expected_runtime("SZLHOLDINGS/a11oy", oid, 0))

    def test_app_starting_is_not_accepted_as_running(self):
        oid = "a" * 40
        with mock.patch.object(
            dep, "hf_space_state", return_value=("RUNNING_APP_STARTING", oid)
        ):
            self.assertFalse(dep.wait_for_expected_runtime("SZLHOLDINGS/a11oy", oid, 0))

    def test_positive_timeout_expires_fail_closed(self):
        oid = "a" * 40
        with (
            mock.patch.object(dep, "hf_space_state", return_value=("BUILDING", oid)),
            mock.patch.object(dep.time, "monotonic", side_effect=[0.0, 2.0]),
            mock.patch.object(dep.time, "sleep") as sleep,
        ):
            self.assertFalse(
                dep.wait_for_expected_runtime(
                    "SZLHOLDINGS/a11oy", oid, timeout=1, poll_interval=0.1
                )
            )
        sleep.assert_not_called()

    def test_terminal_state_for_expected_commit_fails_immediately(self):
        oid = "a" * 40
        with mock.patch.object(
            dep, "hf_space_state", return_value=("BUILD_ERROR", oid)
        ):
            self.assertFalse(dep.wait_for_expected_runtime("SZLHOLDINGS/a11oy", oid, 600))


class TestLiveRouteProbe(unittest.TestCase):
    def test_retries_then_requires_exact_200_with_nonempty_body(self):
        with (
            mock.patch.object(
                dep, "_http", side_effect=[(503, b"not ready"), (200, b"ready")]
            ) as http,
            mock.patch.object(dep.time, "sleep") as sleep,
        ):
            failures = dep.probe_smoke_routes(
                "SZLHOLDINGS/a11oy", ["/health"], retries=2, delay=0
            )
        self.assertEqual(failures, [])
        self.assertEqual(http.call_count, 2)
        self.assertFalse(http.call_args.kwargs["follow_redirects"])
        sleep.assert_called_once_with(0.0)

    def test_redirect_is_not_accepted(self):
        with mock.patch.object(dep, "_http", return_value=(302, b"redirect")):
            failures = dep.probe_smoke_routes(
                "SZLHOLDINGS/a11oy", ["/"], retries=1
            )
        self.assertEqual(failures[0][1], 302)

    def test_empty_200_body_is_not_accepted(self):
        with mock.patch.object(dep, "_http", return_value=(200, b"")):
            failures = dep.probe_smoke_routes(
                "SZLHOLDINGS/a11oy", ["/"], retries=1
            )
        self.assertEqual(failures[0][1], 200)


class TestImmutableAttestation(unittest.TestCase):
    def _args(self, manifest_path):
        return types.SimpleNamespace(
            manifest=manifest_path,
            hf_repo="",
            ref="main",
            wait_running=0,
            smoke_retries=2,
        )

    def test_fetches_files_at_hf_commit_oid_and_probes_manifest_routes(self):
        oid = "a" * 40
        body = b"deployed"
        manifest = {
            "hf_repo": "SZLHOLDINGS/a11oy",
            "hf_commit_oid": oid,
            "smoke_paths": ["/", "/openapi.json"],
            "files": {"app.py": {"sha256": dep.sha256(body)}},
        }
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump(manifest, fh)
            manifest_path = fh.name
        self.addCleanup(lambda: os.unlink(manifest_path))

        with (
            mock.patch.object(dep, "wait_for_expected_runtime", return_value=True) as runtime,
            mock.patch.object(dep, "hf_resolve", return_value=(200, body)) as resolve,
            mock.patch.object(dep, "probe_smoke_routes", return_value=[]) as probe,
        ):
            self.assertEqual(dep.attest(self._args(manifest_path)), 0)
        runtime.assert_called_once_with("SZLHOLDINGS/a11oy", oid, 0)
        resolve.assert_called_once_with("SZLHOLDINGS/a11oy", "app.py", oid)
        probe.assert_called_once_with(
            "SZLHOLDINGS/a11oy", ["/", "/openapi.json"], retries=2
        )

    def test_missing_commit_oid_fails_before_network(self):
        manifest = {
            "hf_repo": "SZLHOLDINGS/a11oy",
            "files": {"app.py": {"sha256": dep.sha256(b"x")}},
        }
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            json.dump(manifest, fh)
            manifest_path = fh.name
        self.addCleanup(lambda: os.unlink(manifest_path))

        with mock.patch.object(dep, "wait_for_expected_runtime") as runtime:
            self.assertEqual(dep.attest(self._args(manifest_path)), 2)
        runtime.assert_not_called()


class TestReusableWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(_HERE, "..", "workflows", "reusable-hf-deploy.yml")
        with open(path, encoding="utf-8") as fh:
            cls.workflow = fh.read()

    def test_shared_deployer_checkout_is_exact_reusable_revision(self):
        # The reusable workflow must checkout ITS OWN reviewed revision --
        # github.job_workflow_sha is the documented context for that; the
        # job.workflow_* forms do not exist and resolve empty.
        self.assertIn("repository: szl-holdings/.github", self.workflow)
        self.assertIn("ref: ${{ github.job_workflow_sha }}", self.workflow)
        self.assertNotIn("${{ job.workflow_repository }}", self.workflow)
        self.assertNotIn("${{ job.workflow_sha }}", self.workflow)
        self.assertNotIn("ref: main", self.workflow)
        self.assertNotIn("repository: szl-holdings/.github\n          ref: main", self.workflow)

    def test_shell_consumes_inputs_through_environment(self):
        for unsafe in (
            '--github-repo "${{ github.repository }}"',
            '--hf-repo "${{ steps.hf.outputs.hf_repo }}"',
            '--ref "${{ inputs.ref }}"',
            '--dockerfile-path "${{ inputs.dockerfile-path }}"',
            '--include-readme "${{ inputs.include-readme }}"',
            "${{ inputs.prune && '--prune' || '' }}",
            '--wait-running "${{ inputs.wait-running }}"',
        ):
            self.assertNotIn(unsafe, self.workflow)
        for safe in (
            'DEPLOY_REF: ${{ inputs.ref }}',
            'DOCKERFILE_PATH: ${{ inputs.dockerfile-path }}',
            'SMOKE_PATHS: ${{ inputs.smoke-paths }}',
            '--smoke-paths "${SMOKE_PATHS}"',
            '--wait-running "${WAIT_RUNNING}"',
        ):
            self.assertIn(safe, self.workflow)

    def test_attestation_does_not_override_immutable_manifest_ref(self):
        attest_block = self.workflow.split("--attest", 1)[1]
        self.assertNotIn("--ref", attest_block)


class TestContentIdentity(unittest.TestCase):
    def test_git_blob_sha1_matches_git(self):
        # `printf '' | git hash-object --stdin` == e69de29... (empty blob)
        self.assertEqual(
            dep.git_blob_sha1(b""),
            "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        )

    def test_git_blob_sha1_hello(self):
        # `printf 'hello' | git hash-object --stdin`
        self.assertEqual(
            dep.git_blob_sha1(b"hello"),
            "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0",
        )

    def test_sha256_known(self):
        self.assertEqual(
            dep.sha256(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
