#!/usr/bin/env python3
"""Network-free contracts for independent Hugging Face token selection."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "acquire_hf_publisher_token",
    _HERE / "acquire_hf_publisher_token.py",
)
assert _SPEC and _SPEC.loader
auth = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = auth
_SPEC.loader.exec_module(auth)


class PublisherCredentialSelectionTests(unittest.TestCase):
    @staticmethod
    def _result(source: str, access: str = "EXISTING_WRITE_CONFIRMED"):
        return auth.ValidationResult(
            source=source,
            identity_sha256="a" * 64,
            target_access=access,
        )

    def test_invalid_first_secret_cannot_mask_later_valid_secret(self) -> None:
        attempted: list[str] = []

        def validator(token: str, **kwargs):
            source = kwargs["source"]
            attempted.append(source)
            if source == "HF_ORG_TOKEN":
                raise RuntimeError("simulated inaccessible target")
            return self._result(source)

        token, selected, attempts = auth.select_credential(
            resource=None,
            target_repo="SZLHOLDINGS/nexus",
            target_type="space",
            allow_create=False,
            environment={
                "HF_ORG_TOKEN_CANDIDATE": "hf_invalid_first",
                "HF_ORG_TOKEN1_CANDIDATE": "hf_valid_second",
            },
            validator=validator,
        )

        self.assertEqual("hf_valid_second", token)
        self.assertEqual("HF_ORG_TOKEN1", selected.source)
        self.assertEqual(["HF_ORG_TOKEN", "HF_ORG_TOKEN1"], attempted)
        self.assertFalse(attempts[0].valid)
        self.assertTrue(attempts[1].valid)

    def test_target_creation_is_not_authorized_for_nexus(self) -> None:
        seen: list[bool] = []

        def validator(_token: str, **kwargs):
            seen.append(kwargs["allow_create"])
            raise RuntimeError("target unavailable")

        with self.assertRaises(auth.CredentialSelectionError):
            auth.select_credential(
                resource=None,
                target_repo="SZLHOLDINGS/nexus",
                target_type="space",
                allow_create=False,
                environment={"HF_TOKEN_CANDIDATE": "hf_candidate"},
                validator=validator,
            )

        self.assertEqual([False], seen)

    def test_report_and_console_fields_cannot_contain_token_bytes(self) -> None:
        token = "hf_secret_material"
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "credential.json"
            selected = self._result("HF_ORG_TOKEN1")
            auth._write_report(
                report,
                target_repo="SZLHOLDINGS/nexus",
                target_type="space",
                resource=None,
                selected=selected,
                attempts=[
                    auth.Attempt(
                        source=selected.source,
                        present=True,
                        valid=True,
                        target_access=selected.target_access,
                    )
                ],
            )
            raw = report.read_text(encoding="utf-8")
            payload = json.loads(raw)

        self.assertNotIn(token, raw)
        self.assertFalse(payload["token_persisted"])
        self.assertFalse(payload["token_logged"])

    def test_github_environment_receives_only_selected_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            github_env = Path(directory) / "github.env"
            auth._append_github_environment(
                github_env,
                "hf_valid_second",
                "HF_ORG_TOKEN1",
            )
            text = github_env.read_text(encoding="utf-8")

        self.assertEqual(
            "HF_TOKEN=hf_valid_second\nHF_TOKEN_SOURCE=HF_ORG_TOKEN1\n",
            text,
        )
        self.assertNotIn("hf_invalid_first", text)


class NexusWorkflowCredentialContractTests(unittest.TestCase):
    def test_workflow_validates_each_secret_independently(self) -> None:
        workflow = (_HERE.parent / "workflows" / "publish-nexus-space.yml").read_text(
            encoding="utf-8"
        )

        for variable in (
            "HF_ORG_TOKEN_CANDIDATE",
            "HF_ORG_TOKEN1_CANDIDATE",
            "HF_WRITE_TOKEN_CANDIDATE",
            "HF_TOKEN_CANDIDATE",
        ):
            self.assertEqual(2, workflow.count(variable), variable)
        self.assertIn("acquire_hf_publisher_token.py", workflow)
        self.assertIn('--github-env "$GITHUB_ENV"', workflow)
        self.assertIn("--target-type space", workflow)
        self.assertNotIn(
            "secrets.HF_ORG_TOKEN || secrets.HF_ORG_TOKEN1",
            workflow,
        )

    def test_selected_token_is_never_printed_or_redeclared(self) -> None:
        workflow = (_HERE.parent / "workflows" / "publish-nexus-space.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("echo $HF_TOKEN", workflow)
        self.assertNotIn("echo ${HF_TOKEN", workflow)
        self.assertEqual(0, workflow.count("HF_TOKEN: ${{"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
