import json
import tempfile
import unittest
from enum import Enum
from pathlib import Path

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
                    "smoke": {"path": "/", "required_marker": "company-front-door"},
                }
            ),
            encoding="utf-8",
        )

    def test_contract_builds_exact_file_hashes(self):
        contract, files = deploy.load_contract(self.root, self.manifest)
        result = deploy.build_deployment(contract, files, "a" * 40, "2026-08-01T00:00:00Z")
        self.assertEqual(result["source"]["revision"], "a" * 40)
        self.assertEqual([row["path"] for row in result["files"]], [".gitattributes", "README.md", "index.html"])
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
        current = deploy.build_deployment(contract, files, "a" * 40, "2026-08-01T00:00:02Z")
        prior = deploy.build_deployment(contract, files, "a" * 40, "2026-08-01T00:00:01Z")

        self.assertFalse(deploy.deployment_matches(prior, current))
        self.assertTrue(deploy.deployment_matches(current, current))


if __name__ == "__main__":
    unittest.main()
