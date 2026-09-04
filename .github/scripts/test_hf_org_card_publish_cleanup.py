import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import hf_org_card_publish_cleanup as cleanup


class FakeApi:
    def __init__(self, *, token, files=None, before="a" * 40):
        self.token = token
        self.files = set(files or ())
        self.head = before
        self.before = before
        self.calls = []

    def repo_info(self, *, repo_id, repo_type):
        self.calls.append(("repo_info", repo_id, repo_type))
        return types.SimpleNamespace(sha=self.head)

    def list_repo_files(self, *, repo_id, repo_type, revision=None):
        self.calls.append(("list_repo_files", repo_id, repo_type, revision))
        return sorted(self.files)

    def create_commit(
        self,
        *,
        repo_id,
        repo_type,
        operations,
        commit_message,
        parent_commit,
    ):
        self.calls.append(
            (
                "create_commit",
                repo_id,
                repo_type,
                tuple(operations),
                commit_message,
                parent_commit,
            )
        )
        if parent_commit != self.head:
            raise AssertionError("parent drift")
        self.files.difference_update(operations)
        self.head = "b" * 40
        return types.SimpleNamespace(oid=self.head)


class OrgCardPublishCleanupTests(unittest.TestCase):
    def authority_env(self, source_sha="c" * 40):
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_SHA": source_sha,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": (
                "szl-holdings/.github/"
                ".github/workflows/hf-org-card-autopublish.yml@refs/heads/main"
            ),
            "HF_TOKEN": "hf-test-token-redacted",
        }

    def test_exact_protected_main_authority_is_accepted(self):
        cleanup.assert_authority("c" * 40, self.authority_env())

    def test_branch_dispatch_rerun_and_missing_token_are_rejected(self):
        mutations = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/feature",
            "GITHUB_REF_PROTECTED": "false",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_WORKFLOW_REF": "wrong/workflow@refs/heads/main",
            "HF_TOKEN": "",
        }
        for name, value in mutations.items():
            with self.subTest(name=name):
                environment = self.authority_env()
                environment[name] = value
                with self.assertRaisesRegex(cleanup.CleanupError, "authority mismatch"):
                    cleanup.assert_authority("c" * 40, environment)

    def test_cleanup_deletes_only_reviewed_paths_and_verifies_head(self):
        files = {
            "README.md",
            "index.html",
            "GOVERNANCE.md",
            "MODELS.txt",
            "SEVEN_SPACES.md",
            "SPACE_PROVENANCE_FRONTIER.json",
            "seven-spaces.yaml",
            "assets/estate-command-system.svg",
        }
        api = FakeApi(token="hf-test-token-redacted", files=files)
        report = cleanup.cleanup_legacy_paths(
            source_sha="c" * 40,
            token="hf-test-token-redacted",
            environ=self.authority_env(),
            wait_seconds=3,
            api_factory=lambda **_: api,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(report.state, "VERIFIED")
        self.assertEqual(report.deleted_paths, cleanup.LEGACY_PATHS)
        self.assertEqual(report.after_head, "b" * 40)
        self.assertIn("README.md", api.files)
        self.assertIn("index.html", api.files)
        self.assertIn("assets/estate-command-system.svg", api.files)
        self.assertFalse(set(cleanup.LEGACY_PATHS) & api.files)
        commit_call = next(call for call in api.calls if call[0] == "create_commit")
        self.assertEqual(commit_call[1], "SZLHOLDINGS/README")
        self.assertEqual(commit_call[3], cleanup.LEGACY_PATHS)

    def test_already_clean_is_idempotent_and_does_not_commit(self):
        api = FakeApi(
            token="hf-test-token-redacted",
            files={"README.md", "index.html"},
        )
        report = cleanup.cleanup_legacy_paths(
            source_sha="c" * 40,
            token="hf-test-token-redacted",
            environ=self.authority_env(),
            wait_seconds=3,
            api_factory=lambda **_: api,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(report.state, "ALREADY_CLEAN")
        self.assertEqual(report.deleted_paths, ())
        self.assertFalse(any(call[0] == "create_commit" for call in api.calls))

    def test_explicit_token_must_match_authorized_environment(self):
        api = FakeApi(token="different", files={"README.md"})
        with self.assertRaisesRegex(cleanup.CleanupError, "explicit token"):
            cleanup.cleanup_legacy_paths(
                source_sha="c" * 40,
                token="different",
                environ=self.authority_env(),
                wait_seconds=3,
                api_factory=lambda **_: api,
            )

    def test_invalid_provider_head_fails_before_mutation(self):
        api = FakeApi(token="hf-test-token-redacted", files={"GOVERNANCE.md"}, before="bad")
        with self.assertRaisesRegex(cleanup.CleanupError, "invalid pre-cleanup head"):
            cleanup.cleanup_legacy_paths(
                source_sha="c" * 40,
                token="hf-test-token-redacted",
                environ=self.authority_env(),
                wait_seconds=3,
                api_factory=lambda **_: api,
            )
        self.assertFalse(any(call[0] == "create_commit" for call in api.calls))

    def test_failure_report_redacts_provider_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            stream = io.StringIO()
            with (
                mock.patch.dict(
                    "os.environ",
                    {"HF_TOKEN": "hf_1234567890secretvalue"},
                    clear=False,
                ),
                mock.patch.object(
                    cleanup,
                    "cleanup_legacy_paths",
                    side_effect=cleanup.CleanupError(
                        "Bearer hf_1234567890secretvalue was rejected"
                    ),
                ),
                mock.patch("sys.stdout", stream),
            ):
                result = cleanup.main(
                    [
                        "--source-sha",
                        "c" * 40,
                        "--report",
                        str(path),
                    ]
                )
            payload = path.read_text(encoding="utf-8")

        self.assertEqual(result, 1)
        self.assertNotIn("hf_1234567890secretvalue", payload)
        self.assertIn("[REDACTED]", payload)


if __name__ == "__main__":
    unittest.main()
