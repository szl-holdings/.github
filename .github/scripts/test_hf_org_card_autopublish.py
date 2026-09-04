import io
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

import hf_org_card_autopublish as publisher
import hf_space_visibility as visibility


class OrgCardAutopublishTests(unittest.TestCase):
    def authority_env(self, source_sha="a" * 40):
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
            "GITHUB_TOKEN": "github-token-redacted",
            "HF_TOKEN": "hf-token-redacted",
        }

    def public_report(self, changed=False):
        return visibility.VisibilityReport(
            schema="szl.hf-space-visibility/v1",
            repo_id="SZLHOLDINGS/README",
            requested_visibility="public",
            authenticated_visibility="public",
            unauthenticated_status=200,
            unauthenticated_visibility="public",
            unauthenticated_readable=True,
            changed=changed,
        )

    def test_exact_protected_main_authority_is_accepted(self):
        publisher.assert_authority("a" * 40, self.authority_env())

    def test_branch_dispatch_rerun_and_missing_tokens_are_rejected(self):
        mutations = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/feature",
            "GITHUB_REF_PROTECTED": "false",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_WORKFLOW_REF": "wrong/workflow@refs/heads/main",
            "GITHUB_TOKEN": "",
            "HF_TOKEN": "",
        }
        for name, value in mutations.items():
            with self.subTest(name=name):
                environment = self.authority_env()
                environment[name] = value
                with self.assertRaisesRegex(
                    publisher.AuthorityError,
                    "authority mismatch",
                ):
                    publisher.assert_authority("a" * 40, environment)

    def test_manifest_cannot_select_another_hub_target(self):
        contract = {
            "source_repository": "szl-holdings/.github",
            "target": {
                "repo_id": "OTHER/README",
                "repo_type": "space",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(publisher.deploy, "assert_local_source"),
                mock.patch.object(
                    publisher.deploy,
                    "load_contract",
                    return_value=(contract, []),
                ),
            ):
                with self.assertRaisesRegex(
                    publisher.AuthorityError,
                    "fixed organization-card target",
                ):
                    publisher.publish_org_card(
                        repo_root=root,
                        manifest_path=root / "manifest.json",
                        source_sha="a" * 40,
                        wait_seconds=10,
                        environ=self.authority_env(),
                    )

    def test_publication_restores_visibility_and_verifies_readback(self):
        contract = {
            "source_repository": "szl-holdings/.github",
            "target": {
                "repo_id": "SZLHOLDINGS/README",
                "repo_type": "space",
            },
        }
        files = [mock.sentinel.file]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(publisher.deploy, "assert_local_source"),
                mock.patch.object(
                    publisher.deploy,
                    "load_contract",
                    return_value=(contract, files),
                ),
                mock.patch.object(
                    publisher.deploy,
                    "build_deployment",
                    return_value={"source": {"revision": "a" * 40}},
                ),
                mock.patch.object(
                    publisher.visibility,
                    "ensure_public_space",
                    side_effect=[self.public_report(True), self.public_report(False)],
                ) as ensure_public,
                mock.patch.object(
                    publisher.deploy,
                    "publish",
                    return_value={"state": "VERIFIED", "hf_commit": "b" * 40},
                ) as publish,
            ):
                result = publisher.publish_org_card(
                    repo_root=root,
                    manifest_path=root / "manifest.json",
                    source_sha="a" * 40,
                    wait_seconds=10,
                    environ=self.authority_env(),
                )

        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(result["target"], "SZLHOLDINGS/README")
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(ensure_public.call_count, 2)
        self.assertTrue(ensure_public.call_args_list[1].kwargs["check_only"])
        publish.assert_called_once()

    def test_production_manifest_preserves_unmanaged_remote_files(self):
        repo_root = Path(__file__).resolve().parents[2]
        contract, _ = publisher.deploy.load_contract(
            repo_root,
            repo_root / "huggingface" / "org-card.manifest.json",
        )
        self.assertFalse(contract["prune"])
        self.assertEqual(contract.get("allowed_deletions"), [])

    def test_report_redacts_provider_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            stream = io.StringIO()
            with mock.patch("sys.stdout", stream):
                publisher.write_report(
                    path,
                    {"error": "Bearer secret-provider-token", "state": "FAILED"},
                )
            payload = path.read_text(encoding="utf-8")
        self.assertNotIn("secret-provider-token", payload)
        self.assertIn("[REDACTED]", payload)


if __name__ == "__main__":
    unittest.main()
