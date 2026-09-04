#!/usr/bin/env python3
"""Fail-closed tests for the local-only Hugging Face candidate planner."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hf_candidate_plan as candidate_plan  # noqa: E402


def _git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
) -> str:
    """Run Git in one isolated fixture and return strict UTF-8 output."""
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    for variable in tuple(env):
        if variable.startswith("GIT_CONFIG_") and variable != "GIT_CONFIG_NOSYSTEM":
            env.pop(variable, None)
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
        env=env,
    )
    if completed.returncode:
        raise AssertionError(
            f"git {' '.join(args)} failed with {completed.returncode}: "
            f"{completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed.stdout.decode("utf-8").strip()


class GitPlanFixture:
    """Tiny committed repository used to prove object-only candidate planning."""

    def __init__(
        self,
        root: Path,
        *,
        dockerfile: bytes | str = "FROM python:3.12-slim\nCOPY app/ /app/\n",
        extra_files: dict[str, bytes | str] | None = None,
    ) -> None:
        self.root = root
        _git(root, "init", "--initial-branch=main")
        _git(root, "config", "user.name", "Candidate Plan Test")
        _git(root, "config", "user.email", "candidate-plan@example.invalid")
        _git(root, "config", "commit.gpgsign", "false")
        _git(root, "config", "core.autocrlf", "false")
        files: dict[str, bytes | str] = {
            "Dockerfile": dockerfile,
            "README.md": "---\nsdk: docker\n---\n# Fixture\n",
            "app/mod.py": "VALUE = 'base'\n",
        }
        files.update(extra_files or {})
        for path, data in files.items():
            self.write(path, data)
        self.base = self.commit("base")

    def write(self, path: str, data: bytes | str) -> None:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        destination.write_bytes(raw)

    def remove(self, path: str) -> None:
        destination = self.root / path
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    def restore_from_head(self, path: str) -> None:
        self.remove(path)
        _git(self.root, "checkout", "HEAD", "--", path)

    def commit(
        self,
        message: str,
        updates: dict[str, bytes | str | None] | None = None,
    ) -> str:
        for path, data in (updates or {}).items():
            if data is None:
                self.remove(path)
            else:
                self.write(path, data)
        _git(self.root, "add", "--all")
        _git(self.root, "commit", "--message", message)
        return _git(self.root, "rev-parse", "HEAD")

    def commit_symlink(self, path: str, target: str) -> str:
        oid = _git(
            self.root,
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=target.encode("utf-8"),
        )
        _git(
            self.root,
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{oid},{path}",
        )
        _git(self.root, "commit", "--message", "managed symlink")
        return _git(self.root, "rev-parse", "HEAD")

    def plan(self, candidate: str, *, baseline: str | None = None) -> dict:
        return candidate_plan.build_plan(
            self.root,
            "szl-holdings/fixture",
            baseline or self.base,
            candidate,
        )


class CandidatePlanTestCase(TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="szl-hf-candidate-plan-test-"
        )
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def fixture(self, **kwargs) -> GitPlanFixture:
        return GitPlanFixture(self.root, **kwargs)


class TestExactCandidatePlan(CandidatePlanTestCase):
    def test_exact_managed_change_and_digest_are_deterministic(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "managed change",
            {"app/mod.py": "VALUE = 'candidate'\n"},
        )

        first = fixture.plan(candidate)
        second = fixture.plan(candidate)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "changes")
        self.assertEqual(first["baseline_ref"], fixture.base)
        self.assertEqual(first["candidate_ref"], candidate)
        self.assertEqual(
            first["candidate"]["source_files"]["app/mod.py"],
            first["candidate"]["files"]["app/mod.py"]["oid"],
        )
        self.assertEqual(first["network_requests"], 0)
        self.assertFalse(first["allowlist_used"])
        self.assertEqual(first["delta_count"], 1)
        self.assertEqual(first["deltas"][0]["path"], "app/mod.py")
        self.assertEqual(first["deltas"][0]["kind"], "modified")
        self.assertTrue(first["deltas"][0]["baseline_managed"])
        self.assertTrue(first["deltas"][0]["candidate_managed"])

        canonical = dict(first)
        digest = canonical.pop("canonical_sha256")
        canonical_bytes = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(digest, hashlib.sha256(canonical_bytes).hexdigest())

    def test_directory_copy_recurses_through_git_tree(self) -> None:
        fixture = self.fixture(
            extra_files={
                "app/nested/worker.py": "WORKER = True\n",
                "app/nested/data.json": "{}\n",
            }
        )
        candidate = fixture.commit(
            "nested change",
            {"app/nested/worker.py": "WORKER = False\n"},
        )

        report = fixture.plan(candidate)

        self.assertEqual(report["delta_count"], 1)
        self.assertEqual(report["deltas"][0]["path"], "app/nested/worker.py")
        self.assertIn("app/nested/data.json", report["candidate"]["files"])
        self.assertEqual(
            report["candidate"]["files"]["app/nested/data.json"]["copy_source"],
            "app",
        )

    def test_planner_sources_equal_production_parser_sources(self) -> None:
        dockerfile = (
            "FROM python:3.12-slim\n"
            "COPY app/ settings.json /srv/\n"
            "COPY app/ /opt/app/\n"
        )

        strict = candidate_plan._strict_copy_sources(dockerfile)
        production = candidate_plan.publisher.parse_copy_sources(dockerfile)

        self.assertEqual(strict, production)
        self.assertEqual(strict, ["app/", "settings.json"])

    def test_unresolved_copy_source_fails_closed(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "unresolved source",
            {
                "Dockerfile": (
                    "FROM python:3.12-slim\nCOPY app/ /app/\nCOPY missing.py /app/\n"
                )
            },
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            r"COPY sources are unresolved: missing\.py",
        ):
            fixture.plan(candidate)

    def test_managed_payload_removal_fails_without_prune_proof(self) -> None:
        fixture = self.fixture(extra_files={"app/retired.py": "RETIRED = True\n"})
        candidate = fixture.commit(
            "remove managed payload",
            {"app/retired.py": None},
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "removes managed payload paths",
        ):
            fixture.plan(candidate)

    def test_non_ancestor_pair_fails_before_snapshot_comparison(self) -> None:
        fixture = self.fixture()
        child = fixture.commit("child", {"app/mod.py": "CHILD = True\n"})

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "candidate baseline is not an ancestor",
        ):
            fixture.plan(fixture.base, baseline=child)

    def test_invalid_or_symbolic_refs_are_rejected(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit("candidate", {"app/mod.py": "NEXT = True\n"})
        invalid_refs = (
            "HEAD",
            candidate.upper(),
            candidate[:-1],
            "z" * 40,
            "0" * 40,
        )

        for invalid in invalid_refs:
            with (
                self.subTest(ref=invalid),
                self.assertRaises(candidate_plan.CandidatePlanError),
            ):
                candidate_plan.build_plan(
                    fixture.root,
                    "szl-holdings/fixture",
                    fixture.base,
                    invalid,
                )


class TestDockerfileGrammar(CandidatePlanTestCase):
    def test_ambiguous_or_unsupported_copy_grammar_fails_closed(self) -> None:
        invalid_dockerfiles = {
            "json": 'FROM scratch\nCOPY ["app/mod.py", "/app/"]\n',
            "quoted": 'FROM scratch\nCOPY "app/mod.py" /app/\n',
            "glob": "FROM scratch\nCOPY app/*.py /app/\n",
            "add": "FROM scratch\nADD app/mod.py /app/\n",
            "flag": "FROM scratch\nCOPY --chown=1000 app/mod.py /app/\n",
            "unterminated": "FROM scratch\nCOPY app/mod.py \\",
            "escape-directive": (
                "# escape=`\nFROM scratch\nCOPY app/mod.py `\n /app/\n"
            ),
            "backtick": "FROM scratch\nCOPY app/mod.py /app/`\n",
            "heredoc": "FROM scratch\nCOPY <<EOF /payload.txt\nhello\nEOF\n",
        }

        for name, dockerfile in invalid_dockerfiles.items():
            with self.subTest(grammar=name):
                case_root = self.root / name
                case_root.mkdir()
                fixture = GitPlanFixture(case_root)
                candidate = fixture.commit(
                    f"invalid {name}",
                    {"Dockerfile": dockerfile},
                )
                with self.assertRaises(candidate_plan.CandidatePlanError):
                    fixture.plan(candidate)

    def test_non_utf8_dockerfile_fails_closed(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "non utf8 Dockerfile",
            {"Dockerfile": b"FROM scratch\nCOPY app/ /app/\n\xff"},
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "Dockerfile is not strict UTF-8",
        ):
            fixture.plan(candidate)


class TestEffectiveDockerignore(CandidatePlanTestCase):
    def test_direct_managed_path_newly_ignored_fails(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "ignore managed file",
            {".dockerignore": "app/mod.py\n"},
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "newly excludes managed COPY paths.*app/mod.py",
        ):
            fixture.plan(candidate)

    def test_ignored_parent_of_managed_path_fails(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "ignore managed parent",
            {".dockerignore": "app\n"},
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "newly excludes managed COPY paths.*app/mod.py",
        ):
            fixture.plan(candidate)

    def test_new_copy_of_preignored_path_fails(self) -> None:
        fixture = self.fixture(extra_files={".dockerignore": "secret.py\n"})
        candidate = fixture.commit(
            "copy a preignored path",
            {
                "Dockerfile": (
                    "FROM python:3.12-slim\nCOPY app/ /app/\nCOPY secret.py /app/\n"
                ),
                "secret.py": "SECRET = False\n",
            },
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "newly excludes managed COPY paths.*secret.py",
        ):
            fixture.plan(candidate)

    def test_specific_negation_keeps_managed_path_in_context(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "explicit managed negation",
            {".dockerignore": "app/*\n!app/mod.py\n"},
        )

        report = fixture.plan(candidate)

        self.assertEqual(report["candidate"]["docker_context_ignored_paths"], [])
        self.assertTrue(
            report["candidate"]["files"]["app/mod.py"]["docker_context_included"]
        )

    def test_dockerfile_specific_ignore_takes_precedence_over_root(self) -> None:
        fixture = self.fixture(extra_files={".dockerignore": "app/mod.py\n"})
        candidate = fixture.commit(
            "override root ignore",
            {"Dockerfile.dockerignore": "!app/mod.py\n"},
        )

        report = fixture.plan(candidate)

        self.assertEqual(
            report["candidate"]["effective_dockerignore"],
            "Dockerfile.dockerignore",
        )
        self.assertTrue(
            report["candidate"]["files"]["app/mod.py"]["docker_context_included"]
        )

    def test_newly_ignored_explicit_readme_copy_fails_before_overlay(self) -> None:
        fixture = self.fixture(
            dockerfile=(
                "FROM python:3.12-slim\n"
                "COPY app/ /app/\n"
                "COPY README.md /app/README.md\n"
            )
        )
        candidate = fixture.commit(
            "ignore copied readme",
            {".dockerignore": "README.md\n"},
        )

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "newly excludes managed COPY paths.*README.md",
        ):
            fixture.plan(candidate)

    def test_nested_dockerfile_is_mapped_to_hf_root_target(self) -> None:
        fixture = self.fixture(
            extra_files={
                "space/Dockerfile": "FROM scratch\nCOPY app/ /app/\n",
                "space/Dockerfile.dockerignore": "*.tmp\n",
            }
        )
        candidate = fixture.commit(
            "nested dockerfile payload",
            {"app/mod.py": "VALUE = 'nested'\n"},
        )

        report = candidate_plan.build_plan(
            fixture.root,
            "szl-holdings/fixture",
            fixture.base,
            candidate,
            dockerfile_path="space/Dockerfile",
        )

        self.assertIn("Dockerfile", report["candidate"]["files"])
        self.assertNotIn("space/Dockerfile", report["candidate"]["files"])
        self.assertEqual(
            report["candidate"]["files"]["Dockerfile"]["source_path"],
            "space/Dockerfile",
        )
        self.assertIn("space/Dockerfile", report["candidate"]["source_files"])
        self.assertIn(
            "space/Dockerfile.dockerignore", report["candidate"]["source_files"]
        )
        self.assertIn("README.md", report["candidate"]["source_files"])

    def test_normalized_lf_checkout_attributes_preserve_exact_blob_parity(self) -> None:
        fixture = self.fixture(extra_files={".gitattributes": "* text=auto eol=lf\n"})
        candidate = fixture.commit(
            "normalized LF candidate",
            {"app/mod.py": "VALUE = 'normalized'\n"},
        )
        fixture.restore_from_head("app/mod.py")

        report = fixture.plan(candidate)

        self.assertEqual(report["delta_count"], 1)

    def test_checkout_transformed_candidate_bytes_fail_exact_blob_parity(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "force CRLF checkout",
            {
                ".gitattributes": "*.py text eol=crlf\n",
                "app/mod.py": "VALUE = 'candidate'\n",
            },
        )
        fixture.restore_from_head("app/mod.py")

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "checkout bytes differ from the exact Git object.*app/mod.py",
        ):
            fixture.plan(candidate)

    def test_changed_checkout_transform_attributes_fail_for_unchanged_blob(
        self,
    ) -> None:
        fixture = self.fixture(extra_files={".gitattributes": "*.py text eol=crlf\n"})
        candidate = fixture.commit(
            "change checkout transform",
            {".gitattributes": "*.py text eol=lf\n"},
        )
        fixture.restore_from_head("app/mod.py")

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "changes checkout-transform attributes.*app/mod.py",
        ):
            fixture.plan(candidate)

    def test_generated_empty_ignore_has_no_checkout_source(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "ordinary candidate", {"app/mod.py": "NEXT = True\n"}
        )

        report = fixture.plan(candidate)

        self.assertNotIn(
            "(generated-empty-dockerignore)", report["candidate"]["source_files"]
        )
        self.assertNotIn("Dockerfile.dockerignore", report["candidate"]["source_files"])

    def test_reserved_readme_targets_fail_closed(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "ordinary candidate", {"app/mod.py": "NEXT = True\n"}
        )

        for readme_path in ("Dockerfile", "Dockerfile.dockerignore"):
            with (
                self.subTest(readme_path=readme_path),
                self.assertRaisesRegex(
                    candidate_plan.publisher.DeployContractError,
                    "reserved Hugging Face root target",
                ),
            ):
                candidate_plan.build_plan(
                    fixture.root,
                    "szl-holdings/fixture",
                    fixture.base,
                    candidate,
                    readme_path=readme_path,
                )

        report = candidate_plan.build_plan(
            fixture.root,
            "szl-holdings/fixture",
            fixture.base,
            candidate,
            include_readme=False,
            readme_path="Dockerfile",
        )
        self.assertFalse(report["include_readme"])

    def test_excluded_explicit_readme_is_not_a_publisher_source(self) -> None:
        fixture = self.fixture(
            dockerfile=(
                "FROM python:3.12-slim\n"
                "COPY app/ /app/\n"
                "COPY README.md /app/README.md\n"
            ),
            extra_files={".gitattributes": "README.md text eol=crlf\n"},
        )
        candidate = fixture.commit(
            "exclude transformed readme",
            {".gitattributes": "README.md text eol=lf\n"},
        )
        fixture.restore_from_head("README.md")

        report = candidate_plan.build_plan(
            fixture.root,
            "szl-holdings/fixture",
            fixture.base,
            candidate,
            include_readme=False,
        )

        self.assertNotIn("README.md", report["candidate"]["files"])
        self.assertNotIn("README.md", report["candidate"]["source_files"])


class TestObjectAndNetworkBoundaries(CandidatePlanTestCase):
    def test_managed_symlink_is_rejected_from_exact_git_tree(self) -> None:
        fixture = self.fixture()
        candidate = fixture.commit_symlink("app/mod.py", "target.py")

        with self.assertRaisesRegex(
            candidate_plan.CandidatePlanError,
            "managed path must be a regular Git blob.*app/mod.py.*mode=120000",
        ):
            fixture.plan(candidate)

    def test_successful_plan_never_calls_publisher_network_or_runtime_helpers(
        self,
    ) -> None:
        fixture = self.fixture()
        candidate = fixture.commit(
            "offline candidate",
            {"app/mod.py": "OFFLINE = True\n"},
        )
        blocked = (
            "_http",
            "hf_resolve",
            "hf_space_state",
            "restart_space",
            "hf_live_origin",
            "wait_for_expected_runtime",
            "probe_smoke_routes",
            "fetch_github_json",
        )

        with contextlib.ExitStack() as stack:
            sentinels = {
                name: stack.enter_context(
                    mock.patch.object(
                        candidate_plan.publisher,
                        name,
                        side_effect=AssertionError(f"network helper called: {name}"),
                    )
                )
                for name in blocked
            }
            urlopen = stack.enter_context(
                mock.patch.object(
                    candidate_plan.publisher.urllib.request,
                    "urlopen",
                    side_effect=AssertionError("urllib.request.urlopen called"),
                )
            )
            report = fixture.plan(candidate)

        self.assertEqual(report["network_requests"], 0)
        urlopen.assert_not_called()
        for sentinel in sentinels.values():
            sentinel.assert_not_called()


class TestReusableWorkflowContract(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_path = HERE.parent / "workflows" / "reusable-hf-candidate-plan.yml"
        cls.workflow = cls.workflow_path.read_text(encoding="utf-8")

    def _input_block(self, name: str) -> str:
        marker = f"      {name}:\n"
        self.assertIn(marker, self.workflow)
        start = self.workflow.index(marker) + len(marker)
        next_input = re.search(
            r"(?m)^      [a-z][a-z0-9-]*:\s*$", self.workflow[start:]
        )
        end = start + next_input.start() if next_input else len(self.workflow)
        return self.workflow[start:end]

    def test_workflow_call_has_exact_ref_and_path_inputs(self) -> None:
        self.assertIn("workflow_call:", self.workflow)
        for name in ("trusted-base-ref", "candidate-ref"):
            block = self._input_block(name)
            self.assertIn("required: true", block)
            self.assertIn("type: string", block)
        for name in (
            "dockerfile-path",
            "include-readme",
            "readme-path",
            "source-revision-file",
        ):
            self._input_block(name)

    def test_workflow_binds_current_same_repo_pull_request(self) -> None:
        for required in (
            "EVENT_NAME: ${{ github.event_name }}",
            "EVENT_BASE_REPO: ${{ github.event.pull_request.base.repo.full_name }}",
            "EVENT_HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}",
            "EVENT_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
            "EVENT_HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            '[ "${EVENT_NAME}" = "pull_request_target" ]',
            '[ "${EVENT_BASE_REPO}" = "${GH_REPO}" ]',
            '[ "${EVENT_HEAD_REPO}" = "${GH_REPO}" ]',
            '[ "${TRUSTED_BASE_REF}" = "${EVENT_BASE_SHA}" ]',
            '[ "${CANDIDATE_REF}" = "${EVENT_HEAD_SHA}" ]',
            '[ -z "${SOURCE_REVISION_FILE}" ]',
        ):
            self.assertIn(required, self.workflow)

    def test_workflow_revalidates_live_pair_before_plan_and_after_artifact(
        self,
    ) -> None:
        helper = "python3 tools/.github/scripts/hf_live_pr_pair.py"
        self.assertEqual(self.workflow.count(helper), 2)
        first_live = self.workflow.index(helper)
        planner = self.workflow.index(
            "python3 tools/.github/scripts/hf_candidate_plan.py"
        )
        upload = self.workflow.index("actions/upload-artifact@")
        final_live = self.workflow.rindex(helper)
        self.assertLess(first_live, planner)
        self.assertLess(planner, upload)
        self.assertLess(upload, final_live)
        self.assertEqual(
            self.workflow.rstrip().splitlines()[-1].strip(), f"run: {helper}"
        )
        for required in (
            "pull-requests: read",
            "GITHUB_API_URL: ${{ github.api_url }}",
            "GITHUB_TOKEN: ${{ github.token }}",
            "PR_NUMBER: ${{ github.event.pull_request.number }}",
            "EXPECTED_BASE_SHA: ${{ inputs.trusted-base-ref }}",
            "EXPECTED_HEAD_SHA: ${{ inputs.candidate-ref }}",
        ):
            self.assertIn(required, self.workflow)
        self.assertNotIn("--token", self.workflow.lower())

    def test_protected_authority_checkout_is_source_and_revision_bound(self) -> None:
        self.assertIn("repository: ${{ job.workflow_repository }}", self.workflow)
        self.assertIn("ref: ${{ job.workflow_sha }}", self.workflow)
        self.assertIn("TRUSTED_BASE_REF: ${{ inputs.trusted-base-ref }}", self.workflow)
        self.assertIn("CANDIDATE_REF: ${{ inputs.candidate-ref }}", self.workflow)
        self.assertIn('--trusted-base-ref "${TRUSTED_BASE_REF}"', self.workflow)
        self.assertIn('--candidate-ref "${CANDIDATE_REF}"', self.workflow)

    def test_workflow_has_no_provider_token_runtime_probe_or_candidate_execution(
        self,
    ) -> None:
        lowered = self.workflow.lower()
        for forbidden in (
            "secrets.",
            "hf_token",
            "hugging_face_hub",
            "huggingface.co",
            "api/spaces",
        ):
            self.assertNotIn(forbidden, lowered)
        self.assertNotRegex(
            lowered,
            r"(?:python(?:3)?|bash|sh)\s+caller[/\\]",
        )
        self.assertNotIn("working-directory: caller", lowered)
        self.assertIn("tools/.github/scripts/hf_candidate_plan.py", self.workflow)

    def test_all_actions_are_immutable_and_missing_report_fails_artifact_step(
        self,
    ) -> None:
        action_refs = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", self.workflow)
        self.assertGreaterEqual(len(action_refs), 3)
        for action_ref in action_refs:
            with self.subTest(action=action_ref):
                self.assertRegex(action_ref, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertIn("        if: always()\n", self.workflow)


class TestRemoteAddContextSemantics(CandidatePlanTestCase):
    def test_checksum_pinned_remote_add_is_external_to_context(self) -> None:
        checksum = "c" * 64
        dockerfile = (
            "FROM python:3.12-slim\n"
            f"ADD --checksum=sha256:{checksum} https://example.invalid/wheel.whl /wheels/wheel.whl\n"
            "COPY app/ /app/\n"
        )
        self.assertEqual(candidate_plan._strict_copy_sources(dockerfile), ["app/"])
        self.assertEqual(
            candidate_plan._strict_copy_sources(dockerfile),
            candidate_plan.publisher.parse_copy_sources(dockerfile),
        )
        fixture = self.fixture(dockerfile=dockerfile)
        candidate = fixture.commit(
            "managed change with remote add",
            {"app/mod.py": "VALUE = 'candidate'\n"},
        )
        report = fixture.plan(candidate)
        self.assertEqual(report["candidate"]["copy_sources"], ["app/"])
        self.assertEqual(report["delta_count"], 1)

    def test_unpinned_or_local_add_fails_closed(self) -> None:
        invalid = {
            "remote-unpinned": (
                "FROM scratch\n"
                "ADD https://example.invalid/archive.tgz /tmp/archive.tgz\n"
                "COPY app/ /app/\n"
            ),
            "local": "FROM scratch\nADD app/mod.py /app/mod.py\n",
        }
        for name, dockerfile in invalid.items():
            with self.subTest(name=name), self.assertRaises(
                candidate_plan.CandidatePlanError
            ):
                candidate_plan._strict_copy_sources(dockerfile)

if __name__ == "__main__":
    main(verbosity=2)
