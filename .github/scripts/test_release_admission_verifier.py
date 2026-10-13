#!/usr/bin/env python3
"""Network-free contract tests for the shared release-admission verifier.

The fake transport answers only the read-only GitHub REST routes the verifier
is allowed to use, honours ``per_page``/``page`` so pagination is exercised for
real, and records every request. Each test names the v12 admission-diagnosis
acceptance case it covers.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_admission_verifier as rav  # noqa: E402

REPO = "szl-holdings/.github"
HEAD = "a" * 40
BASE = "b" * 40
HEAD_TREE = "c" * 40
BASE_TREE = "d" * 40
MG_HEAD = "e" * 40
OTHER = "f" * 40
GATE_RUN, PROV_RUN, EFFECT_RUN = 5001, 5002, 5003
OWNER = "stephenlutar2-hash"
POLICY = ".github/data/control_plane_effect_policy.json"
STORAGE = "https://productionresults.blob.core.windows.net/artifacts/"
SECRET = "tok-not-a-real-value-0123456789"


def digest(value: object) -> str:
    return rav.sha256_bytes(rav.canonical_bytes(value))


class Scenario:
    """A complete, admissible exact-head subject that tests then perturb."""

    def __init__(self, *, event: str = "pull_request", verdict: str = "ALLOW",
                 changed: tuple[str, ...] = (".github/workflows/sbom.yml",)) -> None:
        self.event = event
        self.head = MG_HEAD if event == "merge_group" else HEAD
        self.changed = list(changed)
        self.verdict = verdict
        self.commits = {HEAD: HEAD_TREE, MG_HEAD: HEAD_TREE, BASE: BASE_TREE}
        self.base_tip = BASE
        self.pull = {
            "number": 7, "state": "open", "draft": False, "body": "Rollback: revert",
            "head": {"sha": HEAD, "repo": {"full_name": REPO}},
            "base": {"ref": "main", "repo": {"full_name": REPO}},
        }
        self.compare = {"status": "ahead", "ahead_by": 1, "behind_by": 0,
                        "merge_base_commit": {"sha": BASE}}
        self.runs: list[dict] = []
        self.checks: list[dict] = []
        self.comments: list[dict] = []
        self.artifacts: dict[int, list[dict]] = {}
        self.blobs: dict[int, bytes] = {}
        self.page_total_drift = False
        self.short_page = False
        self.check_padding = 0
        self._ids = itertools.count(900000)
        gate_event = event
        provenance_event = "pull_request_target" if event == "pull_request" else "merge_group"
        self.add_run(GATE_RUN, rav.GATES_WORKFLOW, gate_event)
        for context in rav.GATE_CONTEXTS:
            self.add_check(context, GATE_RUN)
        self.add_run(PROV_RUN, rav.PROVENANCE_WORKFLOW, provenance_event)
        own, other = ("Exact-head organization provenance", "Exact merge-group provenance")
        if event == "merge_group":
            own, other = other, own
        self.add_check(own, PROV_RUN)
        self.add_check(other, PROV_RUN, conclusion="skipped")
        self.add_run(EFFECT_RUN, rav.EFFECT_WORKFLOW, event, created_at="2026-10-13T10:00:00Z")
        self.add_check(rav.EFFECT_CONTEXT, EFFECT_RUN)
        self.receipt = self.build_receipt()
        self.publish_receipt(EFFECT_RUN, self.receipt)

    # -- builders -----------------------------------------------------------
    def add_run(self, run_id: int, path: str, event: str, *, status: str = "completed",
                head: str | None = None, repo: str = REPO, attempt: int = 1,
                created_at: str = "2026-10-13T09:00:00Z") -> dict:
        run = {"id": run_id, "path": path, "event": event, "status": status,
               "conclusion": "success" if status == "completed" else None,
               "head_sha": head or self.head, "check_suite_id": run_id * 10,
               "run_attempt": attempt, "head_repository": {"full_name": repo},
               "created_at": created_at}
        self.runs.append(run)
        return run

    def add_check(self, name: str, run_id: int, *, conclusion: str | None = "success",
                  status: str = "completed", app: tuple[str, int] = rav.TRUSTED_CHECK_APP,
                  head: str | None = None) -> dict:
        check = {"id": next(self._ids), "name": name, "status": status,
                 "conclusion": conclusion, "head_sha": head or self.head,
                 "app": {"slug": app[0], "id": app[1]},
                 "check_suite": {"id": run_id * 10}}
        self.checks.append(check)
        return check

    def build_receipt(self, **overrides: object) -> dict:
        trust_root = sorted(set(self.changed) & rav.TRUST_ROOT_PATHS)
        verdict = self.verdict
        receipt = {
            "schema": rav.RECEIPT_SCHEMA,
            "base_revision": BASE,
            "head_revision": self.head,
            "merge_base": BASE,
            "base_tree": BASE_TREE,
            "head_tree": HEAD_TREE,
            "diff_sha256": "sha256:" + "1" * 64,
            "checker": {"path": ".github/scripts/control_plane_effect_gate.py",
                        "base_sha256": "sha256:" + "2" * 64,
                        "head_sha256": "sha256:" + ("2" if not trust_root else "3") * 64},
            "policy": {"path": POLICY, "authority_revision": self.head if trust_root else BASE,
                       "sha256": "sha256:" + "4" * 64, "schema": "szl.control-plane-effect-policy/v1",
                       "valid_from": "2026-08-30", "valid_until": "2026-11-30"},
            "changed_paths": sorted(self.changed),
            "changed_objects": [],
            "trust_root_changes": trust_root,
            "unbound_executable_changes": [],
            "analyses": [],
            "conflicts": [],
            "reason_codes": {"ALLOW": [], "DENY": ["WORKFLOW_DECLARATION_MISSING"],
                             "REVIEW_REQUIRED": ["CROSS_WORKFLOW_RESOURCE_CONFLICT",
                                                 "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"]}[verdict],
            "verdict": verdict,
            "claim": {"ALLOW": "VERIFIED_STATIC_EFFECT_BOUNDARY",
                      "DENY": "DENIED_STATIC_EFFECT_BOUNDARY",
                      "REVIEW_REQUIRED": "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"}[verdict],
            "claim_limit": "Bounded reviewed grammar only; no arbitrary-program formal proof.",
            "provider_calls_performed": False,
            "secret_values_requested": False,
            "secret_values_recorded": False,
        }
        receipt.update(overrides)
        receipt["decision_digest"] = digest(receipt)
        return receipt

    def publish_receipt(self, run_id: int, receipt: object, *, raw: bytes | None = None,
                        members: dict[str, bytes] | None = None, digest_override: str | None = None) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            files = members if members is not None else {
                "report.json": raw if raw is not None else rav.canonical_bytes(receipt),
                "status.txt": b"verdict=X\n",
            }
            for name, data in files.items():
                bundle.writestr(name, data)
        blob = buffer.getvalue()
        artifact_id = 70000 + run_id
        self.blobs[artifact_id] = blob
        self.artifacts[run_id] = [{
            "id": artifact_id, "name": f"control-plane-effect-{run_id}", "expired": False,
            "digest": digest_override or rav.sha256_bytes(blob),
            "workflow_run": {"id": run_id, "head_sha": self.head},
        }]

    def decision(self, *, login: str = OWNER, user_type: str = "User", action: str = "ACCEPT",
                 edited: bool = False, created_at: str = "2026-10-13T11:00:00Z",
                 **fields: str) -> dict:
        values = {
            "repository": REPO, "pull_request": "7", "base": BASE, "head": HEAD,
            "head_tree": HEAD_TREE, "diff_sha256": self.receipt["diff_sha256"],
            "cp_ebom_decision_digest": self.receipt["decision_digest"],
            "cp_ebom_run_id": str(EFFECT_RUN),
        }
        values.update(fields)
        body = "\n".join([f"{rav.DECISION_MARKER} {action}"]
                         + [f"{key}: {value}" for key, value in values.items() if value is not None]
                         + ["", "I inspected the complete trust-root diff and accept it."])
        comment = {"id": 3000 + len(self.comments), "body": body,
                   "user": {"login": login, "type": user_type},
                   "created_at": created_at,
                   "updated_at": "2026-10-13T12:00:00Z" if edited else created_at}
        self.comments.append(comment)
        return comment

    def subject(self, **overrides: object) -> rav.Subject:
        values = dict(repository=REPO, event=self.event, head_sha=self.head, base_ref="main",
                      base_sha=BASE, gate_run_id=GATE_RUN, pull_request=7, pr_head_sha=HEAD,
                      body_sha256=("9" * 64) if self.event == "pull_request" else None)
        values.update(overrides)
        return rav.Subject(**values)


class FakeGitHub:
    def __init__(self, scenario: Scenario) -> None:
        self.s = scenario
        self.calls: list[tuple[str, dict[str, str]]] = []

    @staticmethod
    def ok(value: object) -> rav.HttpResponse:
        return rav.HttpResponse(200, {}, json.dumps(value).encode("utf-8"))

    def page(self, items: list, query: dict, key: str | None) -> rav.HttpResponse:
        per_page = int(query.get("per_page", ["30"])[0])
        number = int(query.get("page", ["1"])[0])
        chunk = items[(number - 1) * per_page: number * per_page]
        if self.s.short_page and number == 1:
            chunk = chunk[:-1]
        if key is None:
            return self.ok(chunk)
        total = len(items) + (number if self.s.page_total_drift else 0)
        return self.ok({"total_count": total, key: chunk})

    def __call__(self, url: str, headers: dict[str, str]) -> rav.HttpResponse:
        self.calls.append((url, dict(headers)))
        if url.startswith(STORAGE):
            return rav.HttpResponse(200, {}, self.s.blobs[int(url.rsplit("/", 1)[1])])
        parts = urllib.parse.urlsplit(url)
        assert parts.netloc == "api.github.com", url
        route = parts.path.lstrip("/")
        query = urllib.parse.parse_qs(parts.query)
        prefix = f"repos/{REPO}/"
        assert route.startswith(prefix), route
        rest = route[len(prefix):]
        s = self.s
        if rest.startswith("git/commits/"):
            sha = rest.rsplit("/", 1)[1]
            if sha not in s.commits:
                return rav.HttpResponse(404, {}, b"{}")
            return self.ok({"sha": sha, "tree": {"sha": s.commits[sha]}})
        if rest == "pulls/7":
            return self.ok(s.pull)
        if rest == "git/ref/heads/main":
            return self.ok({"object": {"sha": s.base_tip}})
        if rest.startswith("compare/"):
            files = [{"filename": path, "status": "modified"} for path in s.changed]
            return self.ok({**s.compare, "files": files})
        if rest == f"commits/{s.head}/check-runs":
            assert query.get("filter") == ["latest"]
            padding = [{"id": 100 + index, "name": f"unrelated-{index}", "status": "completed",
                        "conclusion": "success", "head_sha": s.head,
                        "app": {"slug": "github-actions", "id": 15368},
                        "check_suite": {"id": 1}} for index in range(s.check_padding)]
            return self.page(padding + s.checks, query, "check_runs")
        if rest == "actions/runs":
            assert query.get("head_sha") == [s.head]
            return self.page(s.runs, query, "workflow_runs")
        if rest.startswith("actions/runs/") and rest.endswith("/artifacts"):
            return self.page(s.artifacts.get(int(rest.split("/")[2]), []), query, "artifacts")
        if rest.startswith("actions/artifacts/") and rest.endswith("/zip"):
            return rav.HttpResponse(302, {"Location": STORAGE + rest.split("/")[2]}, b"")
        if rest == "issues/7/comments":
            return self.page(s.comments, query, None)
        return rav.HttpResponse(404, {}, b"{}")


class VerifierCase(unittest.TestCase):
    def run_verifier(self, scenario: Scenario, *, phase: str = "attest", subject: rav.Subject | None = None,
                     transport: FakeGitHub | None = None) -> tuple[dict, FakeGitHub]:
        fake = transport or FakeGitHub(scenario)
        reader = rav.GitHubReader(REPO, SECRET, fake)
        result = rav.verify_with_wait(subject or scenario.subject(), reader, phase=phase,
                                      wait_seconds=0, poll_seconds=1, sleep=lambda _s: None)
        self.assertFalse(result["provider_writes_performed"])
        self.assertNotIn(SECRET, json.dumps(result))
        return result, fake

    def assertDecision(self, result: dict, decision: str, reason: str | None = None) -> None:
        self.assertEqual(result["decision"], decision, result["reasons"])
        if reason is not None:
            self.assertTrue(any(item.startswith(reason) for item in result["reasons"]) or result["basis"] == reason,
                            (reason, result["basis"], result["reasons"]))


class AcceptanceCaseTests(VerifierCase):
    # -- case 5 -----------------------------------------------------------------
    def test_case05_canonical_allow_with_exact_provenance_admits_only_its_exact_scope(self) -> None:
        scenario = Scenario()
        result, fake = self.run_verifier(scenario)
        self.assertDecision(result, "ADMIT")
        self.assertEqual(result["basis"], "CP_EBOM_ALLOW_EXACT_SCOPE")
        self.assertRegex(result["evidence_fingerprint"], r"^sha256:[0-9a-f]{64}$")
        contexts = [item["context"] for item in result["evidence"]["checks"]]
        self.assertEqual(contexts, list(rav.GATE_CONTEXTS) + [
            "Exact-head organization provenance", rav.EFFECT_CONTEXT])
        self.assertEqual(result["evidence"]["effect"]["decision_digest"], scenario.receipt["decision_digest"])
        for url, headers in fake.calls:
            self.assertEqual("Authorization" in headers, not url.startswith(STORAGE), url)
        # The same ALLOW receipt is not authority for any other subject, even
        # when that other commit exists.
        scenario.commits[OTHER] = OTHER
        for overrides, code in (
            ({"base_sha": OTHER}, "SUBJECT_DRIFT"),
            ({"head_sha": OTHER, "pr_head_sha": OTHER}, "SUBJECT_DRIFT"),
        ):
            with self.subTest(overrides=overrides):
                blocked, _ = self.run_verifier(scenario, subject=scenario.subject(**overrides))
                self.assertDecision(blocked, "BLOCK", code)
        for field, value in (("head_tree", OTHER), ("base_revision", OTHER), ("merge_base", OTHER)):
            with self.subTest(receipt_field=field):
                moved = Scenario()
                moved.publish_receipt(EFFECT_RUN, moved.build_receipt(**{field: value}))
                blocked, _ = self.run_verifier(moved)
                self.assertDecision(blocked, "BLOCK", "RECEIPT_SCOPE_MISMATCH")

    def test_case05_receipt_must_agree_with_github_compare(self) -> None:
        scenario = Scenario()
        scenario.publish_receipt(EFFECT_RUN, scenario.build_receipt(changed_paths=[]))
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "BLOCK", "RECEIPT_INCONSISTENT")
        # An ALLOW that hides a trust-root change GitHub reports cannot admit.
        hidden = Scenario(changed=(POLICY,))
        hidden.publish_receipt(EFFECT_RUN, hidden.build_receipt(trust_root_changes=[]))
        result, _ = self.run_verifier(hidden)
        self.assertDecision(result, "BLOCK", "RECEIPT_INCONSISTENT")
        lying = Scenario(changed=(POLICY,))
        lying.publish_receipt(EFFECT_RUN, lying.build_receipt(reason_codes=[]))
        result, _ = self.run_verifier(lying)
        self.assertDecision(result, "BLOCK", "RECEIPT_INCONSISTENT")

    # -- case 2 -----------------------------------------------------------------
    def test_case02_eight_green_gates_with_failed_or_missing_provenance_never_admit(self) -> None:
        failed = Scenario()
        next(c for c in failed.checks if c["name"] == "Exact-head organization provenance")["conclusion"] = "failure"
        result, _ = self.run_verifier(failed)
        self.assertDecision(result, "BLOCK", "EVIDENCE_NOT_SUCCESS")
        missing = Scenario()
        missing.checks = [c for c in missing.checks if c["name"] != "Exact-head organization provenance"]
        result, _ = self.run_verifier(missing)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        no_run = Scenario()
        no_run.runs = [r for r in no_run.runs if r["path"] != rav.PROVENANCE_WORKFLOW]
        result, _ = self.run_verifier(no_run)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        # A different successful check never substitutes for provenance.
        substitute = Scenario()
        check = next(c for c in substitute.checks if c["name"] == "Exact-head organization provenance")
        check["name"] = "gate/provenance-copy"
        result, _ = self.run_verifier(substitute)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        self.assertIsNone(result["evidence_fingerprint"])

    # -- case 3 -----------------------------------------------------------------
    def test_case03_effect_deny_blocks_with_any_job_conclusion_or_owner_decision(self) -> None:
        failed_job = Scenario(verdict="DENY")
        next(c for c in failed_job.checks if c["name"] == rav.EFFECT_CONTEXT)["conclusion"] = "failure"
        result, _ = self.run_verifier(failed_job)
        self.assertDecision(result, "BLOCK", "EVIDENCE_NOT_SUCCESS")
        green_job = Scenario(verdict="DENY")
        result, _ = self.run_verifier(green_job)
        self.assertDecision(result, "BLOCK", "CP_EBOM_DENY")
        green_job.decision()
        result, _ = self.run_verifier(green_job)
        self.assertDecision(result, "BLOCK", "CP_EBOM_DENY")

    # -- case 4 -----------------------------------------------------------------
    def test_case04_review_required_without_a_valid_exact_owner_decision_holds(self) -> None:
        base = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        result, _ = self.run_verifier(base)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_MISSING")
        self.assertEqual(result["receipt_verdict"], "REVIEW_REQUIRED")
        variants = {
            "wrong actor": dict(login="szl-automation"),
            "bot account": dict(user_type="Bot"),
            "edited record": dict(edited=True),
            "stale head": dict(head=OTHER),
            "stale base": dict(base=OTHER),
            "altered receipt digest": dict(cp_ebom_decision_digest="sha256:" + "0" * 64),
            "other effect run": dict(cp_ebom_run_id="1"),
            "other tree": dict(head_tree=OTHER),
            "other diff": dict(diff_sha256="sha256:" + "0" * 64),
            "missing field": dict(cp_ebom_run_id=None),
            "predates evidence": dict(created_at="2026-10-13T08:00:00Z"),
            "unknown action": dict(action="APPROVE"),
        }
        for label, overrides in variants.items():
            with self.subTest(label):
                scenario = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
                scenario.decision(**overrides)
                result, _ = self.run_verifier(scenario)
                self.assertDecision(result, "HOLD")
        copied = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        copied.decision()
        copied.pull["body"] = copied.comments.pop()["body"]  # self-asserted body text
        result, _ = self.run_verifier(copied)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_MISSING")
        revoked = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        revoked.decision()
        revoked.decision(action="REVOKE", created_at="2026-10-13T11:30:00Z")
        result, _ = self.run_verifier(revoked)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_REVOKED")

    def test_case04_altered_or_malformed_receipt_blocks(self) -> None:
        scenario = Scenario()
        scenario.publish_receipt(EFFECT_RUN, scenario.receipt, digest_override="sha256:" + "0" * 64)
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "BLOCK", "RECEIPT_TAMPERED")
        altered = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        forged = dict(altered.receipt, verdict="ALLOW", claim="VERIFIED_STATIC_EFFECT_BOUNDARY")
        altered.publish_receipt(EFFECT_RUN, forged)
        altered.decision()
        result, _ = self.run_verifier(altered)
        self.assertDecision(result, "BLOCK", "RECEIPT_TAMPERED")
        for label, members in (
            ("no report", {"status.txt": b"verdict=ALLOW\n"}),
            ("two reports", {"report.json": b"{}", "cp-ebom/../report.json": b"{}"}),
            ("duplicate key", {"report.json": b'{"verdict":"ALLOW","verdict":"DENY"}'}),
        ):
            with self.subTest(label):
                bad = Scenario()
                bad.publish_receipt(EFFECT_RUN, None, members=members)
                result, _ = self.run_verifier(bad)
                self.assertDecision(result, "BLOCK")
        expired = Scenario()
        expired.artifacts[EFFECT_RUN][0]["expired"] = True
        result, _ = self.run_verifier(expired)
        self.assertDecision(result, "BLOCK", "RECEIPT_UNAVAILABLE")
        missing = Scenario()
        missing.artifacts[EFFECT_RUN] = []
        result, _ = self.run_verifier(missing)
        self.assertDecision(result, "BLOCK", "RECEIPT_UNAVAILABLE")

    # -- case 6 -----------------------------------------------------------------
    def test_case06_review_required_with_exact_owner_decision_admits_without_relabeling(self) -> None:
        scenario = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        scenario.decision(login="szl-automation")  # ignored, not counted as authority
        accepted = scenario.decision()
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "ADMIT")
        self.assertEqual(result["basis"], "REVIEW_REQUIRED_OWNER_ACCEPTED")
        self.assertEqual(result["receipt_verdict"], "REVIEW_REQUIRED")
        self.assertEqual(result["evidence"]["effect"]["verdict"], "REVIEW_REQUIRED")
        self.assertEqual(result["evidence"]["owner_decision"]["comment_id"], accepted["id"])
        self.assertEqual(result["evidence"]["ignored_owner_decision_comments"]["untrusted_author"], 1)

    def test_case06_admission_producer_change_needs_the_owner_record_even_with_allow(self) -> None:
        scenario = Scenario(changed=(rav.GATES_WORKFLOW,))
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_MISSING")
        scenario.decision()
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "ADMIT")
        self.assertEqual(result["basis"], "PRODUCER_CHANGE_OWNER_ACCEPTED")

    # -- case 7 -----------------------------------------------------------------
    def test_case07_required_evidence_beyond_page_one_is_evaluated(self) -> None:
        scenario = Scenario()
        scenario.check_padding = 230
        result, fake = self.run_verifier(scenario)
        self.assertDecision(result, "ADMIT")
        pages = [url for url, _ in fake.calls if "/check-runs" in url]
        self.assertTrue(any("page=3" in url for url in pages), pages)
        failing = Scenario()
        failing.check_padding = 230
        failing.checks[-1]["conclusion"] = "cancelled"  # effect check, now on page 3
        result, _ = self.run_verifier(failing)
        self.assertDecision(result, "BLOCK", "EVIDENCE_NOT_SUCCESS")

    def test_case07_incomplete_or_shifting_pagination_fails_closed(self) -> None:
        for attribute, code in (("page_total_drift", "EVIDENCE_AMBIGUOUS"),
                                ("short_page", "EVIDENCE_INCOMPLETE")):
            with self.subTest(attribute):
                scenario = Scenario()
                scenario.check_padding = 150
                setattr(scenario, attribute, True)
                result, _ = self.run_verifier(scenario)
                self.assertDecision(result, "BLOCK", code)

    def test_case07_stale_duplicate_foreign_and_untrusted_same_name_checks_cannot_satisfy(self) -> None:
        stale = Scenario()
        stale.add_run(PROV_RUN + 100, rav.PROVENANCE_WORKFLOW, "pull_request_target")
        stale.add_check("Exact-head organization provenance", PROV_RUN + 100, conclusion="failure")
        result, _ = self.run_verifier(stale)
        self.assertDecision(result, "BLOCK", "EVIDENCE_NOT_SUCCESS")
        duplicate = Scenario()
        duplicate.add_check(rav.EFFECT_CONTEXT, EFFECT_RUN)
        result, _ = self.run_verifier(duplicate)
        self.assertDecision(result, "BLOCK", "EVIDENCE_AMBIGUOUS")
        foreign = Scenario()
        foreign.checks = [c for c in foreign.checks if c["name"] != "gate/lean"]
        foreign.add_run(6100, ".github/workflows/other.yml", "pull_request")
        foreign.add_check("gate/lean", 6100)
        foreign.add_check("gate/lean", GATE_RUN, head=OTHER)
        result, _ = self.run_verifier(foreign)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        untrusted = Scenario()
        untrusted.checks = [c for c in untrusted.checks if c["name"] != "gate/schema"]
        untrusted.add_check("gate/schema", GATE_RUN, app=("third-party-ci", 4242))
        result, _ = self.run_verifier(untrusted)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        shadowed = Scenario()
        shadowed.add_check("gate/schema", GATE_RUN, app=("third-party-ci", 4242), conclusion="failure")
        result, _ = self.run_verifier(shadowed)
        self.assertDecision(result, "ADMIT")
        schema = next(c for c in result["evidence"]["checks"] if c["context"] == "gate/schema")
        self.assertEqual(schema["ignored"]["untrusted_producer"], 1)

    def test_case07_gate_generation_must_be_the_attested_source_run(self) -> None:
        scenario = Scenario()
        scenario.add_run(GATE_RUN + 10, rav.GATES_WORKFLOW, "pull_request", status="in_progress")
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "BLOCK", "EVIDENCE_STALE")

    # -- case 8 -----------------------------------------------------------------
    def test_case08_pull_request_and_merge_group_use_their_own_provenance(self) -> None:
        pull = Scenario()
        own = next(c for c in pull.checks if c["name"] == "Exact-head organization provenance")
        own["conclusion"] = "skipped"
        next(c for c in pull.checks if c["name"] == "Exact merge-group provenance")["conclusion"] = "success"
        result, _ = self.run_verifier(pull)
        self.assertDecision(result, "BLOCK", "EVIDENCE_NOT_SUCCESS")

        group = Scenario(event="merge_group")
        result, _ = self.run_verifier(group)
        self.assertDecision(result, "ADMIT")
        provenance = next(c for c in result["evidence"]["checks"] if "provenance" in c["context"]
                          and c["context"] != "gate/provenance")
        self.assertEqual((provenance["context"], provenance["event"]),
                         ("Exact merge-group provenance", "merge_group"))
        # A pull_request_target provenance success on the queue head is not proof.
        wrong_event = Scenario(event="merge_group")
        for run in wrong_event.runs:
            if run["path"] == rav.PROVENANCE_WORKFLOW:
                run["event"] = "pull_request_target"
        result, _ = self.run_verifier(wrong_event)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")
        # A pull-request gate generation cannot attest a merge-group head.
        crossed = Scenario(event="merge_group")
        for run in crossed.runs:
            if run["path"] == rav.GATES_WORKFLOW:
                run["event"] = "pull_request"
        result, _ = self.run_verifier(crossed)
        self.assertDecision(result, "BLOCK", "EVIDENCE_MISSING")

    def test_case08_merge_group_trust_root_binds_the_owner_decision_by_tree_and_diff(self) -> None:
        group = Scenario(event="merge_group", verdict="REVIEW_REQUIRED", changed=(POLICY,))
        result, _ = self.run_verifier(group)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_MISSING")
        group.decision(cp_ebom_decision_digest="sha256:" + "5" * 64, cp_ebom_run_id="4999")
        result, _ = self.run_verifier(group)
        self.assertDecision(result, "ADMIT")
        self.assertEqual(result["basis"], "REVIEW_REQUIRED_OWNER_ACCEPTED")
        drifted = Scenario(event="merge_group", verdict="REVIEW_REQUIRED", changed=(POLICY,))
        drifted.decision(head_tree=OTHER)
        result, _ = self.run_verifier(drifted)
        self.assertDecision(result, "HOLD", "OWNER_DECISION_MISMATCH")

    # -- case 9 -----------------------------------------------------------------
    def test_case09_attest_and_enqueue_agree_and_any_evidence_drift_changes_or_blocks(self) -> None:
        scenario = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
        scenario.decision()
        attested, _ = self.run_verifier(scenario, phase="attest")
        enqueue, _ = self.run_verifier(scenario, phase="enqueue")
        self.assertDecision(attested, "ADMIT")
        self.assertEqual(attested["evidence_fingerprint"], enqueue["evidence_fingerprint"])

        def fingerprint(mutate) -> str | None:
            changed = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
            changed.decision()
            mutate(changed)
            result, _ = self.run_verifier(changed, phase="enqueue")
            return result["evidence_fingerprint"] if result["decision"] == "ADMIT" else None

        def new_effect_generation(s: Scenario) -> None:
            s.add_run(EFFECT_RUN + 50, rav.EFFECT_WORKFLOW, "pull_request", created_at="2026-10-13T10:30:00Z")
            s.add_check(rav.EFFECT_CONTEXT, EFFECT_RUN + 50)
            s.publish_receipt(EFFECT_RUN + 50, s.receipt)

        def second_decision(s: Scenario) -> None:
            s.decision(created_at="2026-10-13T11:45:00Z")

        def new_provenance_generation(s: Scenario) -> None:
            s.add_run(PROV_RUN + 50, rav.PROVENANCE_WORKFLOW, "pull_request_target")
            s.add_check("Exact-head organization provenance", PROV_RUN + 50)

        for label, mutate in (("effect rerun", new_effect_generation),
                              ("new owner record", second_decision),
                              ("provenance rerun", new_provenance_generation)):
            with self.subTest(label):
                self.assertNotEqual(fingerprint(mutate), attested["evidence_fingerprint"])
        for label, mutate, code in (
            ("head moved", lambda s: s.pull["head"].update(sha=OTHER), "SUBJECT_DRIFT"),
            ("returned to draft", lambda s: s.pull.update(draft=True), "SUBJECT_DRIFT"),
            ("closed", lambda s: s.pull.update(state="closed"), "SUBJECT_DRIFT"),
            ("base moved", lambda s: setattr(s, "base_tip", OTHER), "SUBJECT_DRIFT"),
            ("behind base", lambda s: s.compare.update(behind_by=1), "SUBJECT_NOT_UP_TO_DATE"),
            ("newer gate", lambda s: s.add_run(GATE_RUN + 9, rav.GATES_WORKFLOW, "pull_request"), "EVIDENCE_STALE"),
        ):
            with self.subTest(label):
                changed = Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,))
                changed.decision()
                mutate(changed)
                result, _ = self.run_verifier(changed, phase="enqueue")
                self.assertDecision(result, "BLOCK", code)

    # -- liveness and transport -------------------------------------------------
    def test_running_evidence_waits_then_fails_closed(self) -> None:
        scenario = Scenario()
        effect = next(c for c in scenario.checks if c["name"] == rav.EFFECT_CONTEXT)
        effect.update(status="in_progress", conclusion=None)
        result, _ = self.run_verifier(scenario)
        self.assertDecision(result, "BLOCK", "EVIDENCE_PENDING")
        polls = []

        def complete_after_two(_seconds: float) -> None:
            polls.append(_seconds)
            if len(polls) == 2:
                effect.update(status="completed", conclusion="success")

        clock = iter(range(0, 10_000, 5))
        reader = rav.GitHubReader(REPO, SECRET, FakeGitHub(scenario))
        result = rav.verify_with_wait(scenario.subject(), reader, phase="attest", wait_seconds=600,
                                      poll_seconds=30, sleep=complete_after_two, clock=lambda: next(clock))
        self.assertDecision(result, "ADMIT")
        self.assertEqual(len(polls), 2)

    def test_artifact_redirect_never_carries_the_token_and_must_be_allowlisted(self) -> None:
        scenario = Scenario()
        fake = FakeGitHub(scenario)
        original = fake.__call__

        def hostile(url: str, headers: dict[str, str]) -> rav.HttpResponse:
            if url.endswith("/zip"):
                return rav.HttpResponse(302, {"location": "https://collector.example.com/x"}, b"")
            return original(url, headers)

        reader = rav.GitHubReader(REPO, SECRET, hostile)
        result = rav.verify_with_wait(scenario.subject(), reader, phase="attest",
                                      wait_seconds=0, poll_seconds=1)
        self.assertDecision(result, "BLOCK", "RECEIPT_UNAVAILABLE")
        self.assertFalse(any("example.com" in url for url, _ in fake.calls))

    def test_subject_validation_fails_closed(self) -> None:
        scenario = Scenario()
        for overrides in ({"event": "push"}, {"head_sha": "abc"}, {"base_ref": "feature/x"},
                          {"gate_run_id": 0}, {"body_sha256": None}, {"pr_head_sha": OTHER},
                          {"repository": "szl-holdings"}):
            with self.subTest(overrides=overrides):
                result, _ = self.run_verifier(scenario, subject=scenario.subject(**overrides))
                self.assertDecision(result, "BLOCK", "SUBJECT_INVALID")


class CheckerCompatibilityTests(unittest.TestCase):
    """The verifier must recompute digests exactly as the checker emits them."""

    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "cp_ebom_checker", ROOT / ".github/scripts/control_plane_effect_gate.py")
        cls.checker = importlib.util.module_from_spec(spec)
        sys.modules["cp_ebom_checker"] = cls.checker
        spec.loader.exec_module(cls.checker)

    def test_canonical_encoding_matches_the_checker(self) -> None:
        sample = {"b": [1, "é", {"z": None, "a": True}], "a": "— \n", "n": 3}
        self.assertEqual(rav.canonical_bytes(sample), self.checker.canonical_bytes(sample))

    def test_checker_failure_receipt_digest_recomputes(self) -> None:
        receipt = self.checker.failure_receipt(HEAD, BASE, self.checker.GateError("X", "y"))
        body = {key: value for key, value in receipt.items() if key != "decision_digest"}
        self.assertEqual(rav.sha256_bytes(rav.canonical_bytes(body)), receipt["decision_digest"])
        self.assertEqual(rav.TRUST_ROOT_PATHS, self.checker.TRUST_ROOT_PATHS)


class RetainedReceiptTests(unittest.TestCase):
    """Case 1: the retained #894 DENY reproduces from its exact Git objects."""

    BASE_894 = "b17aa63ca0903e1acf7bfaff601868242967c0d3"
    HEAD_894 = "e3817af1c52c11479467f61d61702efa8e02600d"
    DIGEST_894 = "sha256:a022f02cd06b9a93031a41e7bb0edd399de28e9fdd3ff94349030492406484c4"

    def test_case01_retained_894_receipt_identity_and_ten_denials(self) -> None:
        git = shutil.which("git")
        objects = git and all(subprocess.run(
            [git, "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, check=False).returncode == 0 for sha in (self.BASE_894, self.HEAD_894))
        try:
            import yaml  # noqa: F401
            parser_ok = yaml.__version__ == "6.0.3"
        except ImportError:
            parser_ok = False
        shallow = git and subprocess.run([git, "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                                         capture_output=True, text=True, check=False).stdout.strip() != "false"
        if not objects or not parser_ok or shallow:
            self.skipTest("needs full history with the #894 objects and admitted PyYAML 6.0.3")
        checker = subprocess.run([git, "-C", str(ROOT), "show",
                                  f"{self.HEAD_894}:.github/scripts/control_plane_effect_gate.py"],
                                 capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "checker_894.py"
            script.write_bytes(checker)
            report = Path(directory) / "report.json"
            completed = subprocess.run(
                [sys.executable, "-I", str(script), "--repository-root", str(ROOT),
                 "--base", self.BASE_894, "--head", self.HEAD_894, "--report", str(report),
                 "--as-of", "2026-10-11"], capture_output=True, check=False, timeout=1800)
            receipt = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(receipt["decision_digest"], self.DIGEST_894)
        body = {key: value for key, value in receipt.items() if key != "decision_digest"}
        self.assertEqual(rav.sha256_bytes(rav.canonical_bytes(body)), self.DIGEST_894)
        self.assertEqual(receipt["verdict"], "DENY")
        self.assertEqual(len(receipt["analyses"]), 10)
        self.assertTrue(all(item["reason_codes"] == ["WORKFLOW_DECLARATION_MISSING"]
                            for item in receipt["analyses"]))


class CommandLineTests(unittest.TestCase):
    def run_main(self, scenario: Scenario, environ: dict[str, str]) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "admission.json")
            code = rav.main([
                "--repository", REPO, "--event", "pull_request", "--head-sha", HEAD,
                "--base-ref", "main", "--base-sha", BASE, "--gate-run-id", str(GATE_RUN),
                "--pull-request", "7", "--pr-head-sha", HEAD, "--body-sha256", "9" * 64,
                "--phase", "attest", "--output", output,
            ], transport=FakeGitHub(scenario), environ=environ)
            raw = Path(output).read_text(encoding="utf-8")
        self.assertNotIn(SECRET, raw)
        return code, json.loads(raw)

    def test_exit_codes_follow_the_decision_and_no_token_is_recorded(self) -> None:
        code, result = self.run_main(Scenario(), {"GH_TOKEN": SECRET})
        self.assertEqual((code, result["decision"]), (0, "ADMIT"))
        code, result = self.run_main(Scenario(verdict="REVIEW_REQUIRED", changed=(POLICY,)),
                                     {"GH_TOKEN": SECRET})
        self.assertEqual((code, result["decision"]), (3, "HOLD"))
        code, result = self.run_main(Scenario(verdict="DENY"), {"GH_TOKEN": SECRET})
        self.assertEqual((code, result["decision"]), (2, "BLOCK"))
        code, result = self.run_main(Scenario(), {})
        self.assertEqual((code, result["basis"]), (2, "READ_TOKEN_MISSING"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
