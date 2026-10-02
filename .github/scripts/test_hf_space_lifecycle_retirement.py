#!/usr/bin/env python3
"""Fail if the superseded August 31 Space publisher is wired back in."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "huggingface" / "archive" / "hf-space-lifecycle-policy-2026-08-31.json"


class RetirementContract(unittest.TestCase):
    def test_historical_policy_is_preserved_exactly(self) -> None:
        # Git normalizes line endings on checkout; bind the committed LF blob.
        source = ARCHIVE.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            "f4e6d68427fd240d682b9f01a41adace5859abebe12ec5b27eabc11abb46f4fd",
        )
        policy = json.loads(source)
        self.assertEqual(policy["schema"], "szl.hf.space-lifecycle-policy.v2")
        self.assertEqual(policy["authority"]["run_id"], "33352706604")
        self.assertEqual(len(policy["targets"]), 46)

    def test_superseded_writer_is_not_live(self) -> None:
        retired_paths = (
            ROOT / ".github" / "data" / "hf-space-lifecycle-policy.json",
            ROOT / ".github" / "scripts" / "hf_space_lifecycle_reconcile.py",
            WORKFLOWS / "hf-space-lifecycle-reconcile.yml",
            WORKFLOWS / "hf-space-lifecycle-reconcile.yaml",
        )
        for path in retired_paths:
            self.assertFalse(path.exists(), path)
        for workflow in WORKFLOWS.iterdir():
            if workflow.suffix not in {".yml", ".yaml"}:
                continue
            source = workflow.read_text(encoding="utf-8")
            self.assertNotIn("hf_space_lifecycle_reconcile.py", source, workflow)
            self.assertNotIn(
                ".github/data/hf-space-lifecycle-policy.json", source, workflow
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
