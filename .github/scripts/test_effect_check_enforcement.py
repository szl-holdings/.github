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
from unittest import mock
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
    def test_review_required_still_fails_when_comment_api_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"verdict": "REVIEW_REQUIRED"}))
            with mock.patch.object(enforcement, "fetch_comments", side_effect=SystemExit("API unavailable")) as fetch:
                with self.assertRaises(SystemExit):
                    enforcement.main([
                        "--fetch-comments", "--exit-code", "3", "--receipt", str(receipt),
                        "--comments", str(root / "comments"), "--run-created-path", str(root / "created"),
                        "--subject", str(root / "subject"),
                    ])
                fetch.assert_called_once()

    def test_agreeing_allow_and_deny_do_not_fetch_comments(self):
        for verdict, exit_code in (("ALLOW", 0), ("DENY", 2)):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt = root / "receipt.json"
                receipt.write_text(json.dumps({"verdict": verdict}))
                with mock.patch.object(enforcement, "fetch_comments", side_effect=SystemExit("API unavailable")) as fetch:
                    self.assertEqual(enforcement.main([
                        "--fetch-comments", "--exit-code", str(exit_code), "--receipt", str(receipt),
                        "--comments", str(root / "comments"), "--run-created-path", str(root / "created"),
                        "--subject", str(root / "subject"),
                    ]), 0)
                    fetch.assert_not_called()
                self.assertEqual(json.loads((root / "comments").read_text()), [])

    def test_fetch_receipt_disagreement_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"verdict": "ALLOW"}))
            with mock.patch.object(enforcement, "fetch_comments", return_value=0) as fetch:
                with self.assertRaises(SystemExit):
                    enforcement.main([
                        "--fetch-comments", "--exit-code", "3", "--receipt", str(receipt),
                        "--comments", str(root / "comments"), "--run-created-path", str(root / "created"),
                        "--subject", str(root / "subject"),
                    ])
                fetch.assert_not_called()

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

    def test_read_only_comment_policy_does_not_allow_write_permissions_or_extra_secrets(self):
        # Even re-pinning the workflow source cannot widen the read-only token.
        root = Path(__file__).resolve().parents[2]
        gate_path = root / ".github/scripts/control_plane_effect_gate.py"
        spec = importlib.util.spec_from_file_location("effect_policy_test_gate", gate_path)
        gate = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = gate
        spec.loader.exec_module(gate)
        path = ".github/workflows/control-plane-effect-gate.yml"
        source = (root / path).read_text()
        policy = json.loads((root / ".github/data/control_plane_effect_policy.json").read_text())
        declaration = policy["workflow_declarations"][path]
        self.assertEqual(declaration["credentials"], ["GITHUB_TOKEN"])
        mutations = (
            (source.replace("issues: read", "issues: write", 1), "GITHUB_WRITE_PERMISSION_PRESENT"),
            (source.replace("GH_TOKEN: ${{ github.token }}", "GH_TOKEN: ${{ secrets.EXTRA_TOKEN }}", 1),
             "CREDENTIAL_BINDING_MISMATCH"),
        )
        for changed, reason in mutations:
            with self.subTest(reason=reason):
                self.assertNotEqual(changed, source)
                raw = gate.analyze_workflow_source(changed, path=path)
                blobs = {name: (root / name).read_bytes() for name in raw["dependencies"]}
                repinned = {**declaration, "source_sha256": gate.sha256_bytes(changed.encode())}
                result = gate.bind_declaration(path, changed.encode(), raw, repinned, blobs)
                self.assertEqual(result["verdict"], "DENY")
                self.assertIn(reason, result["reason_codes"])

    def _fetch_pages(self, directory, responses):
        root = Path(directory)
        with mock.patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "pull_request", "PR_NUMBER": "938",
            "GH_TOKEN": "fake-test-token", "GITHUB_REPOSITORY": "szl-holdings/.github",
            "GITHUB_RUN_ID": RUN_ID,
        }, clear=True), mock.patch.object(enforcement, "_github_get", side_effect=responses) as get:
            enforcement.fetch_comments(root / "comments", root / "created", root / "subject")
            return json.loads((root / "comments").read_text()), get.call_args_list

    def test_short_comment_page_with_next_link_fails_closed(self):
        # An incomplete first page must never hide a later owner revocation.
        link = '<https://api.github.com/repos/szl-holdings/.github/issues/938/comments?per_page=100&page=2>; rel="next"'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SystemExit, "incomplete"):
                self._fetch_pages(directory, [([_accept()], link), ({"created_at": RUN_CREATED}, "")])
            self.assertFalse((Path(directory) / "comments").exists())

    def test_later_page_revocation_is_preserved(self):
        link = '<https://api.github.com/repos/szl-holdings/.github/issues/938/comments?per_page=100&page=2>; rel="next"'
        revoked = _accept()
        revoked["id"] = 200
        revoked["body"] = revoked["body"].replace("ACCEPT", "REVOKE")
        with tempfile.TemporaryDirectory() as directory:
            comments, calls = self._fetch_pages(directory, [
                ([{**_accept(), "id": index + 1} for index in range(100)], link),
                ([revoked], ""), ({"created_at": RUN_CREATED}, ""),
            ])
            self.assertEqual(len(comments), 101)
            self.assertIn("page=2", calls[1].args[0])
            owner, reasons = enforcement.bind_owner_decision(
                _receipt("REVIEW_REQUIRED", "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"), comments,
                repository="szl-holdings/.github", pull_request=938,
                run_id=RUN_ID, run_created_at=RUN_CREATED,
            )
            self.assertEqual(owner, "HOLD")
            self.assertIn("OWNER_DECISION_REVOKED", reasons)

    def test_comment_next_link_cannot_change_subject_or_skip_pages(self):
        for target in (
            "https://api.github.com/repos/other/repo/issues/938/comments?per_page=100&page=2",
            "https://api.github.com/repos/szl-holdings/.github/issues/939/comments?per_page=100&page=2",
            "https://api.github.com/repos/szl-holdings/.github/issues/938/comments?per_page=100&page=3",
            "https://api.github.com/repos/szl-holdings/.github/issues/938/comments?per_page=100&page=1",
            "https://api.github.com/repos/szl-holdings/.github/issues/938/comments?per_page=100&page=2&since=2027-01-01",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                link = f'<{target}>; rel="next"'
                with self.assertRaisesRegex(SystemExit, "pagination"):
                    self._fetch_pages(directory, [([_accept()] * 100, link), ([], ""), ({"created_at": RUN_CREATED}, "")])
                self.assertFalse((Path(directory) / "comments").exists())

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
