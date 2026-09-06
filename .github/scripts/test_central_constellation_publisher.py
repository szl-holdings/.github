#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contract for the central Constellation publisher."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-constellation-space.yml"


class CentralConstellationPublisherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_actions_are_immutable(self) -> None:
        uses = re.findall(r"^\s*uses:\s*(\S+)\s*(?:#.*)?$", self.text, re.MULTILINE)
        self.assertTrue(uses)
        self.assertEqual(
            [],
            [value for value in uses if not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", value)],
        )

    def test_central_source_and_fixed_destination_are_closed(self) -> None:
        required = (
            "repository: szl-holdings/szl-constellation",
            "ref: main",
            "SZLHOLDINGS/szl-constellation",
            "spaces/SZLHOLDINGS/szl-constellation",
            "source/tools/verify_constellation.py",
            "source/tools/run_publish_constellation.py",
            "git ls-remote https://github.com/szl-holdings/szl-constellation.git refs/heads/main",
            "os.environ['GITHUB_REPOSITORY'] = 'szl-holdings/szl-constellation'",
            "os.environ['GITHUB_SHA'] = os.environ['SOURCE_SHA']",
        )
        for marker in required:
            self.assertIn(marker, self.text, marker)
        self.assertNotIn("--allow-create", self.text)
        self.assertNotIn("force-push", self.text.lower())

    def test_credential_selection_is_bounded_and_secret_free(self) -> None:
        candidates = (
            "HF_ORG_TOKEN_CANDIDATE",
            "HF_ORG_TOKEN1_CANDIDATE",
            "HF_WRITE_TOKEN_CANDIDATE",
            "HF_TOKEN_CANDIDATE",
            "HUGGINGFACE_TOKEN_CANDIDATE",
            "HUGGING_FACE_HUB_TOKEN_CANDIDATE",
        )
        for candidate in candidates:
            self.assertEqual(1, self.text.count(candidate), candidate)
        self.assertEqual(1, self.text.count("acquire_hf_publisher_token.py"))
        self.assertIn('--token-file "$RUNNER_TEMP/constellation-hf-token"', self.text)
        self.assertIn('test "$(stat -c \'%a\' "$TOKEN_FILE")" = "600"', self.text)
        self.assertIn('HF_TOKEN="$(<"$TOKEN_FILE")"', self.text)
        self.assertNotIn("HF_TOKEN: ${{ secrets.HF_TOKEN }}", self.text)
        self.assertNotIn("echo $HF_TOKEN", self.text)
        self.assertNotIn("set -x", self.text)

    def test_publication_requires_full_source_and_live_evidence(self) -> None:
        required = (
            "python source/tools/verify_constellation.py",
            "python -m pytest -q",
            "python -m pip check",
            "test -z \"$(git -C source status --porcelain)\"",
            "constellation-deployment-receipt.json",
            "hf-publisher-credential.json",
            "retention-days: 90",
        )
        for marker in required:
            self.assertIn(marker, self.text, marker)

    def test_pull_requests_never_publish(self) -> None:
        self.assertIn("if: github.event_name == 'pull_request'", self.text)
        self.assertIn("if: github.event_name != 'pull_request'", self.text)
        self.assertIn("workflow_dispatch: {}", self.text)
        self.assertIn("schedule:", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
