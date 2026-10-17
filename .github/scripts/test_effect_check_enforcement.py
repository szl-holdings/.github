#!/usr/bin/env python3
"""Owner-decision binding for the required effect check.

These tests do not edit branch protection, pull-request history, or the
historical green run on szl-holdings/.github#938.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("effect_check_enforcement.py")
SPEC = importlib.util.spec_from_file_location("effect_check_enforcement", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
enforcement = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = enforcement
SPEC.loader.exec_module(enforcement)

HEAD = "ab" * 20
OTHER_HEAD = "11" * 20
BASE = "cd" * 20
TREE = "ef" * 20
DIFF = "sha256:" + ("12" * 32)
DIGEST = "sha256:" + ("34" * 32)
RUN_ID = "39004646145"
RUN_CREATED = "2026-10-17T05:00:00Z"
COMMENT_AT = "2026-10-17T05:10:00Z"


def _receipt(verdict: str, claim: str) -> dict:
    return {
        "verdict": verdict,
        "claim": claim,
        "base_revision": BASE,
        "head_revision": HEAD,
        "head_tree": TREE,
        "diff_sha256": DIFF,
        "decision_digest": DIGEST,
    }


def _accept(head: str = HEAD, author: str = "stephenlutar2-hash",
            account_type: str = "User", created: str = COMMENT_AT,
            updated: str | None = None) -> dict:
    body = "\n".join((
        "SZL-Admission-Owner-Decision: ACCEPT",
        "repository: szl-holdings/.github",
        "pull_request: 938",
        f"base: {BASE}",
        f"head: {head}",
        f"head_tree: {TREE}",
        f"diff_sha256: {DIFF}",
        f"cp_ebom_decision_digest: {DIGEST}",
        f"cp_ebom_run_id: {RUN_ID}",
        "",
        "Reviewed the trust-root diff.",
    ))
    return {
        "id": 50,
        "body": body,
        "created_at": created,
        "updated_at": created if updated is None else updated,
        "user": {"login": author, "type": account_type},
    }


class EffectCheckEnforcementTests(unittest.TestCase):
    def test_review_required_is_not_an_analyzer_pass(self):
        self.assertEqual(enforcement.check_decision(3, "REVIEW_REQUIRED"), "FAIL")

    def test_deny_still_fails_and_allow_still_passes(self):
        self.assertEqual(enforcement.check_decision(2, "DENY"), "FAIL")
        self.assertEqual(enforcement.check_decision(0, "ALLOW"), "PASS")

    def test_disagreement_is_not_rewritten_into_allow(self):
        self.assertEqual(enforcement.check_decision(0, "REVIEW_REQUIRED"), "DISAGREE")
        self.assertEqual(enforcement.check_decision(3, "ALLOW"), "DISAGREE")
        self.assertEqual(enforcement.check_decision(3, "DENY"), "DISAGREE")
        self.assertEqual(enforcement.check_decision(1, "ALLOW"), "DISAGREE")

    def _run(self, verdict: str, claim: str, exit_code: int, comments: list[dict],
             *, event: str = "pull_request", pr_head: str = "", receipt_head: str = ""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "report.json"
            status = root / "status.txt"
            comment_path = root / "comments.json"
            payload = _receipt(verdict, claim)
            if receipt_head:
                payload["head_revision"] = receipt_head
            receipt_path.write_text(json.dumps(payload), encoding="utf-8")
            comment_path.write_text(json.dumps(comments), encoding="utf-8")
            try:
                code = enforcement.enforce(
                    exit_code,
                    receipt_path,
                    status,
                    comments_path=comment_path,
                    repository="szl-holdings/.github",
                    pull_request=938,
                    run_id=RUN_ID,
                    run_created_at=RUN_CREATED,
                    event=event,
                    pr_head_sha=pr_head,
                )
            except SystemExit as exc:
                code = exc.code
            return code, status.read_text(encoding="utf-8")

    def test_missing_owner_decision_fails_and_keeps_the_verdict(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [])
        self.assertEqual(code, 3)
        self.assertIn("verdict=REVIEW_REQUIRED", text)
        self.assertIn("decision=FAIL", text)
        self.assertIn("owner=HOLD", text)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_edited_owner_decision_fails(self):
        comment = _accept(updated="2026-10-17T05:11:00Z")
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [comment])
        self.assertEqual(code, 3)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_stale_head_owner_decision_fails(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3,
            [_accept(head=OTHER_HEAD)])
        self.assertEqual(code, 3)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_wrong_owner_decision_fails(self):
        for author, account_type in (("someone", "User"), ("stephenlutar2-hash", "Bot")):
            code, text = self._run(
                "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3,
                [_accept(author=author, account_type=account_type)])
            self.assertEqual(code, 3, msg=f"{author}:{account_type}")
            self.assertIn("OWNER_DECISION_MISSING", text)

    def test_exact_owner_decision_passes_without_relabeling_the_receipt(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [_accept()])
        self.assertEqual(code, 0)
        self.assertIn("verdict=REVIEW_REQUIRED", text)
        self.assertIn("decision=PASS", text)
        self.assertIn("owner=ADMIT", text)
        self.assertNotIn("verdict=ALLOW", text)

    def test_plain_green_light_text_is_not_an_owner_decision(self):
        comment = _accept()
        comment["body"] = "Green light "
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [comment])
        self.assertEqual(code, 3)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_deny_fails_even_with_an_exact_owner_decision(self):
        code, text = self._run(
            "DENY", "DENIED_STATIC_EFFECT_BOUNDARY", 2, [_accept()])
        self.assertEqual(code, 2)
        self.assertIn("verdict=DENY", text)
        self.assertIn("decision=FAIL", text)

    def test_allow_receipt_passes_without_an_owner_decision(self):
        code, text = self._run("ALLOW", "NO_EFFECT", 0, [])
        self.assertEqual(code, 0)
        self.assertIn("decision=PASS", text)
        self.assertIn("owner=NOT_REQUIRED", text)

    def test_exit_and_verdict_disagreement_does_not_pass(self):
        pairs = ((0, "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"),
                 (0, "DENY", "DENIED_STATIC_EFFECT_BOUNDARY"),
                 (3, "ALLOW", "NO_EFFECT"),
                 (3, "DENY", "DENIED_STATIC_EFFECT_BOUNDARY"),
                 (2, "ALLOW", "NO_EFFECT"),
                 (2, "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"),
                 (1, "ALLOW", "NO_EFFECT"))
        for exit_code, verdict, claim in pairs:
            with self.subTest(exit_code=exit_code, verdict=verdict):
                code, text = self._run(verdict, claim, exit_code, [_accept()])
                self.assertNotEqual(code, 0)
                self.assertIn("decision=DISAGREE", text)
                self.assertNotIn("decision=PASS", text)

    def test_missing_and_malformed_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.txt"
            missing = root / "absent.json"
            with self.assertRaises(SystemExit) as raised:
                enforcement.main(["--exit-code", "0", "--receipt", str(missing), "--status", str(status)])
            self.assertEqual(raised.exception.code, 1)
            text = status.read_text(encoding="utf-8")
            self.assertIn("verdict=MISSING", text)
            self.assertIn("decision=FAIL", text)
            for label, body in (("broken", "{"), ("array", "[]"), ("blank", "")):
                with self.subTest(label):
                    receipt = root / "report.json"
                    receipt.write_text(body, encoding="utf-8")
                    with self.assertRaises(SystemExit) as malformed:
                        enforcement.main([
                            "--exit-code", "3", "--receipt", str(receipt), "--status", str(status),
                        ])
                    self.assertEqual(malformed.exception.code, 1)
                    written = status.read_text(encoding="utf-8")
                    self.assertIn("verdict=MALFORMED", written)
                    self.assertIn("decision=FAIL", written)

    def test_receipt_owner_field_does_not_manufacture_a_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "report.json"
            status = root / "status.txt"
            body = _receipt("REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED")
            body["owner_decision"] = "ACCEPT"
            receipt.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                enforcement.enforce(
                    3,
                    receipt,
                    status,
                    repository="szl-holdings/.github",
                    pull_request=938,
                    run_id=RUN_ID,
                    run_created_at=RUN_CREATED,
                )
            self.assertEqual(raised.exception.code, 3)
            text = status.read_text(encoding="utf-8")
            self.assertIn("verdict=REVIEW_REQUIRED", text)
            self.assertIn("decision=FAIL", text)
            self.assertIn("OWNER_DECISION_MISSING", text)

    def test_queue_ref_names_only_a_main_pull_request(self):
        sha = "ab" * 20
        self.assertEqual(
            enforcement.queue_pull_request(f"refs/heads/gh-readonly-queue/main/pr-938-{sha}"),
            938,
        )
        self.assertEqual(
            enforcement.queue_pull_request(f"gh-readonly-queue/main/pr-7-{sha}"),
            7,
        )
        self.assertIsNone(enforcement.queue_pull_request("refs/heads/main"))
        self.assertIsNone(enforcement.queue_pull_request(
            f"refs/heads/gh-readonly-queue/release/pr-938-{sha}"))
        self.assertIsNone(enforcement.queue_pull_request(
            "refs/heads/gh-readonly-queue/main/pr-938-short"))

    def test_merge_group_accepts_the_pull_request_head(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [_accept()],
            event="merge_group", pr_head=HEAD, receipt_head="ee" * 20)
        self.assertEqual(code, 0)
        self.assertIn("verdict=REVIEW_REQUIRED", text)
        self.assertIn("decision=PASS", text)
        self.assertIn("owner=ADMIT", text)
        self.assertNotIn("verdict=ALLOW", text)

    def test_merge_group_rejects_a_decision_for_the_group_commit(self):
        group_head = "ee" * 20
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3,
            [_accept(head=group_head)],
            event="merge_group", pr_head=HEAD, receipt_head=group_head)
        self.assertEqual(code, 3)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_merge_group_without_the_pull_request_head_fails(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [_accept()],
            event="merge_group", receipt_head="ee" * 20)
        self.assertEqual(code, 3)
        self.assertIn("OWNER_DECISION_MISSING", text)

    def test_direct_push_has_no_owner_decision_subject(self):
        code, text = self._run(
            "REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", 3, [_accept()],
            event="push")
        self.assertEqual(code, 3)
        self.assertIn("SUBJECT_INVALID", text)

    def test_fetch_does_not_require_an_exit_code(self):
        keys = (
            "GITHUB_EVENT_NAME", "GITHUB_REF", "PR_NUMBER", "GH_TOKEN",
            "GITHUB_REPOSITORY", "GITHUB_RUN_ID",
        )
        saved = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["GITHUB_EVENT_NAME"] = "push"
            os.environ["GITHUB_REF"] = "refs/heads/main"
            for key in keys[2:]:
                os.environ.pop(key, None)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                comments = root / "comments.json"
                created = root / "created"
                subject = root / "subject.json"
                code = enforcement.main([
                    "--fetch-comments",
                    "--comments", str(comments),
                    "--run-created-path", str(created),
                    "--subject", str(subject),
                ])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(comments.read_text(encoding="utf-8")), [])
                loaded = json.loads(subject.read_text(encoding="utf-8"))
                self.assertEqual(loaded["event"], "push")
                self.assertEqual(loaded["pull_request"], 0)
                self.assertEqual(loaded["pr_head_sha"], "")
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_malformed_queue_ref_fails_before_a_token_read(self):
        keys = ("GITHUB_EVENT_NAME", "GITHUB_REF", "GH_TOKEN")
        saved = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["GITHUB_EVENT_NAME"] = "merge_group"
            os.environ["GITHUB_REF"] = "refs/heads/gh-readonly-queue/main/pr-not-a-queue"
            os.environ["GH_TOKEN"] = "present-but-must-not-be-required"
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaises(SystemExit) as caught:
                    enforcement.fetch_comments(
                        root / "comments.json", root / "created", root / "subject.json")
            self.assertIn("merge-group ref", str(caught.exception))
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
