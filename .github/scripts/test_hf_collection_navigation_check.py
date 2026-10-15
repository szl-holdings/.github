#!/usr/bin/env python3
"""Network-free contracts for the three-collection navigation observer.

Fixtures retain public identity fields from the October 15, 2026 detail reads.
They are test inputs, never fresh provider evidence or model-readiness proof.
"""

from __future__ import annotations

import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE.parent / "policies" / "hf-collection-navigation.v1.json"
SPEC = importlib.util.spec_from_file_location(
    "hf_collection_navigation_check", HERE / "hf_collection_navigation_check.py"
)
assert SPEC and SPEC.loader
check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check
SPEC.loader.exec_module(check)

OWNER = {"_id": "6a18de7657b5b7a615a55801", "name": "SZLHOLDINGS", "type": "org"}
BOUNDARIES = {
    "provider_writes": False,
    "promotion_allowed": False,
    "model_quality": "NOT_EVALUATED",
    "production_readiness": "NOT_EVALUATED",
    "legacy_start_here_reconciliation": "UNRESOLVED_SEPARATE_CONTRACT",
}
REQUIRED_WEIGHTS = {
    "SZLHOLDINGS/SZL-Khipu-1.5B",
    "SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent",
    "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
}
UNCLASSIFIED_KERNEL_MEMBERS = {
    "SZLHOLDINGS/szl-khipu",
    "SZLHOLDINGS/szl-khipu-kernels",
    "SZLHOLDINGS/szl-training-scripts",
    "SZLHOLDINGS/szl-nemo",
    "SZLHOLDINGS/a11oy-v19-substrate",
    "SZLHOLDINGS/szl-energy-attest",
    "SZLHOLDINGS/oac-clinical-transport-health-v1",
    "SZLHOLDINGS/oac-system-health-v1",
    "SZLHOLDINGS/szl-triage-linear-development-v1",
}
OBJECT_IDS = {
    "SZLHOLDINGS/SZL-Khipu-1.5B": "6a950ff36875c560e58f73a7",
    "SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent": "6a950ff36bd483e54ab48695",
    "SZLHOLDINGS/szl-receiptagent-qwen35-0.8b-v3": "6a950ff4b3753ae350180157",
    "SZLHOLDINGS/A11OY-MINI": "6a950ff5d2f6bb305efb2ac7",
    "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF": "6abef9ea6352ca4f975ae89e",
    "SZLHOLDINGS/szl-receiptagent-qwen35-0.8b-v2": "6abef9ead63a211549600e0c",
    "SZLHOLDINGS/szl-kernels": "6a9315c26e7478363792e331",
    "SZLHOLDINGS/szl-lambda-gate": "6a9315c2bd96f89579d83dcb",
    "SZLHOLDINGS/szl-governed-norm": "6a9315c2058268eb5f885778",
    "SZLHOLDINGS/szl-formulas": "6a9315c259d3614812a95a84",
    "SZLHOLDINGS/szl-block-kv": "6a9315c2a9e3d0a35f377e9b",
    "SZLHOLDINGS/szl-maskmod": "6a9315c24e08aae10ae77a47",
    "SZLHOLDINGS/szl-receipt-attn": "6a9315c37a697e5187583246",
    "SZLHOLDINGS/YARQA-ATTN": "6a9315c30cb0a33f2675e751",
    "SZLHOLDINGS/szl-ouroboros": "6a9315c36138e79e7ab1c17c",
    "SZLHOLDINGS/szl-invariants": "6a9315c3a72e0b7a200f60e4",
    "SZLHOLDINGS/szl-govsign": "6a9315c3058268eb5f885787",
    "SZLHOLDINGS/szl-provctl": "6a9315c3691c95149de426ca",
    "SZLHOLDINGS/szl-blocked": "6a9315c386947dfa9d5c0eef",
    "SZLHOLDINGS/governed-inference-meter": "6a9315c30ee93453d0002df9",
    "SZLHOLDINGS/a11oy-v19-substrate": "6a9315c36bd483e54a8ac4cd",
    "SZLHOLDINGS/szl-khipu-kernels": "6a9315c3ed327671e181e654",
    "SZLHOLDINGS/szl-training-scripts": "6abdb4b1303828e10c620e0d",
    "SZLHOLDINGS/szl-khipu": "6abdb4b14c81c77fde2cb033",
    "SZLHOLDINGS/szl-energy-attest": "6abdb4b2ca63fede2582e7fa",
    "SZLHOLDINGS/oac-clinical-transport-health-v1": "6abdb4b35967524534917e57",
    "SZLHOLDINGS/oac-system-health-v1": "6abdb4b3e87f12b28dfd24ee",
    "SZLHOLDINGS/szl-triage-linear-development-v1": "6abdb4b41aa8e65fc9b46df6",
    "SZLHOLDINGS/szl-nemo": "6abefa36ce6196fc0beba80a",
}


def load_policy() -> dict:
    return check.parse_json_bytes(POLICY_PATH.read_bytes())


def model_item(member_id: str) -> dict:
    return {
        "id": member_id,
        "_id": OBJECT_IDS.get(member_id, "000000000000000000000001"),
        "author": "SZLHOLDINGS",
        "authorData": copy.deepcopy(OWNER),
        "private": False,
        "type": "model",
        "repoType": "model",
    }


def snapshot_fixture(*, include_optional: bool = True) -> dict:
    """A reviewed-subset fixture; the real 23-member kernel set is tested below."""
    responses = []
    positions = {"khipu-family": 1, "model-showcase": 6, "software-kernels": 5}
    for target in load_policy()["targets"]:
        members = list(target["required_members"])
        if include_optional:
            members.extend(target["optional_members"])
        body = {
            "owner": copy.deepcopy(OWNER),
            "private": False,
            "slug": target["slug"],
            "title": target["title"],
            "description": target["description_exact"] or "Compact model-launch family with receipts.",
            "position": positions[target["id"]],
            "shareUrl": "https://hf.co/collections/" + target["slug"].rsplit("-", 1)[0],
            "items": [model_item(member_id) for member_id in members],
        }
        responses.append({
            "url": "https://huggingface.co/api/collections/" + target["slug"],
            "method": "GET",
            "status": 200,
            "received_at": "2026-10-15T12:00:00Z",
            "body_text": json.dumps(body, sort_keys=True),
        })
    return {"schema": "szl.hf.collection-navigation-snapshot/v1", "responses": responses}


def mutate_body(snapshot: dict, role: str, mutation) -> None:
    targets = load_policy()["targets"]
    slug = next(target["slug"] for target in targets if target["id"] == role)
    response = next(row for row in snapshot["responses"] if row["url"].endswith(slug))
    body = json.loads(response["body_text"])
    mutation(body)
    response["body_text"] = json.dumps(body, sort_keys=True)


class NavigationContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()

    def assert_boundaries(self, receipt: dict) -> None:
        boundaries = receipt["boundaries"]
        for key, expected in BOUNDARIES.items():
            self.assertEqual(boundaries[key], expected, key)
            if expected is False:
                self.assertIs(boundaries[key], False, key)

    def assert_attempt_identity(self, receipt: dict, mode: str, policy_digest) -> None:
        self.assertEqual(receipt["mode"], mode)
        self.assertEqual(receipt["evidence_scope"],
            "UNTRUSTED_LOCAL_SNAPSHOT_ONLY" if mode == "snapshot" else "THREE_PUBLIC_COLLECTION_DETAILS_ONLY")
        observed = datetime.fromisoformat(receipt["observed_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(observed.tzinfo)
        self.assertEqual(observed.utcoffset().total_seconds(), 0)
        self.assertEqual(receipt["policy_sha256"], policy_digest)
        self.assert_boundaries(receipt)

    def assert_hold(self, snapshot: dict) -> dict:
        receipt = check.check_snapshot(self.policy, snapshot, mode="snapshot")
        self.assertEqual(receipt["navigation_status"], "HOLD")
        self.assert_boundaries(receipt)
        findings = list(receipt.get("findings", []))
        for target in receipt.get("targets", []):
            findings.extend(target["findings"])
        self.assertTrue(findings)
        self.assertTrue(all(isinstance(finding.get("code"), str) for finding in findings))
        return receipt

    def test_committed_policy_preserves_independent_scope_and_maturity(self) -> None:
        validated = check.validate_policy(self.policy)
        self.assertIsInstance(validated, dict)
        targets = {target["id"]: target for target in self.policy["targets"]}
        self.assertEqual(set(targets), {"khipu-family", "model-showcase", "software-kernels"})
        family = targets["khipu-family"]
        self.assertEqual(set(family["required_members"]), REQUIRED_WEIGHTS)
        self.assertEqual(family["forbidden_members"], ["SZLHOLDINGS/szl-nemo"])
        self.assertEqual(family["classification"], "CANDIDATE_NAVIGATION")
        self.assertIsNone(family["description_exact"])
        showcase = targets["model-showcase"]
        self.assertEqual(showcase["required_members"] + showcase["optional_members"], [])
        self.assertEqual(showcase["classification"], "NO_MODEL_PROMOTED")
        self.assertEqual(showcase["description_exact"],
            "No model is promoted. See https://holdings.a-11-oy.com/frontier/ for public artifacts and their evidence. Lambda uniqueness remains Conjecture 1.")
        kernels = targets["software-kernels"]
        self.assertEqual(kernels["required_members"], ["SZLHOLDINGS/szl-kernels"])
        self.assertEqual(len(kernels["optional_members"]), 13)
        self.assertEqual(kernels["member_classifications"]["SZLHOLDINGS/szl-governed-norm"], "DEPRECATED_SOFTWARE")
        self.assertFalse(UNCLASSIFIED_KERNEL_MEMBERS & set(kernels["required_members"] + kernels["optional_members"]))
        for key, value in BOUNDARIES.items():
            self.assertEqual(self.policy[key], value)

    def test_optional_members_are_optional_without_requiring_deprecated_artifacts(self) -> None:
        for include_optional in (False, True):
            with self.subTest(include_optional=include_optional):
                receipt = check.check_snapshot(self.policy, snapshot_fixture(include_optional=include_optional))
                self.assertEqual(receipt["navigation_status"], "PASS")
                self.assertTrue(all(target["status"] == "PASS" for target in receipt["targets"]))
                self.assert_boundaries(receipt)

    def test_real_kernel_membership_remains_held_and_does_not_expand_policy(self) -> None:
        snapshot = snapshot_fixture()
        mutate_body(snapshot, "software-kernels", lambda body: body["items"].extend(
            model_item(member_id) for member_id in sorted(UNCLASSIFIED_KERNEL_MEMBERS)
        ))
        receipt = self.assert_hold(snapshot)
        targets = {target["id"]: target for target in receipt["targets"]}
        self.assertEqual(targets["khipu-family"]["status"], "PASS")
        self.assertEqual(targets["model-showcase"]["status"], "PASS")
        self.assertEqual(targets["software-kernels"]["status"], "HOLD")
        unclassified = {finding["member_id"] for finding in targets["software-kernels"]["findings"]
                        if finding["code"] == "UNCLASSIFIED_MEMBER"}
        self.assertEqual(unclassified, UNCLASSIFIED_KERNEL_MEMBERS)
        self.assertEqual(self.policy, load_policy())

    def test_missing_each_required_member_holds(self) -> None:
        cases = [("khipu-family", member_id) for member_id in REQUIRED_WEIGHTS]
        cases.append(("software-kernels", "SZLHOLDINGS/szl-kernels"))
        for role, missing in cases:
            with self.subTest(role=role, missing=missing):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, role, lambda body: body.update(items=[item for item in body["items"] if item["id"] != missing]))
                self.assert_hold(snapshot)

    def test_recipe_unknown_and_foreign_members_are_not_admitted(self) -> None:
        for role, member_id in (
            ("khipu-family", "SZLHOLDINGS/szl-nemo"),
            ("khipu-family", "SZLHOLDINGS/SZL-Khipu-1.5B-unreviewed"),
            ("khipu-family", "another-org/SZL-Khipu-1.5B"),
            ("software-kernels", "SZLHOLDINGS/SZL-Khipu-1.5B"),
            ("software-kernels", "SZLHOLDINGS/new-kernel"),
        ):
            with self.subTest(role=role, member_id=member_id):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, role, lambda body: body["items"].append(model_item(member_id)))
                self.assert_hold(snapshot)

    def test_showcase_membership_and_any_description_change_hold(self) -> None:
        mutations = [lambda body: body["items"].append(model_item("SZLHOLDINGS/SZL-Khipu-1.5B"))]
        for description in (
            "Models are promoted.", "No model is promoted. Fully production ready.",
            "No model is promoted.", "", None,
        ):
            mutations.append(lambda body, value=description: body.update(description=value))
        for index, mutation in enumerate(mutations):
            with self.subTest(case=index):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "model-showcase", mutation)
                self.assert_hold(snapshot)

    def test_software_description_cannot_claim_trained_weights(self) -> None:
        for description in ("Trained production kernels.", "Software kernels.", "", None):
            with self.subTest(description=description):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "software-kernels", lambda body: body.update(description=description))
                self.assert_hold(snapshot)

    def test_collection_identity_visibility_and_detail_shape_fail_closed(self) -> None:
        replacements = {
            "slug": ("SZLHOLDINGS/another-collection", None, 1),
            "title": ("Start Here", "Trained Models & Weights", None),
            "private": (True, 0, "false", None),
            "position": (True, -1, "1", None),
            "shareUrl": ("https://example.test/collections/foreign", None),
            "items": ({}, None, "[]"),
        }
        for field, values in replacements.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    snapshot = snapshot_fixture()
                    mutate_body(snapshot, "khipu-family", lambda body: body.update({field: value}))
                    self.assert_hold(snapshot)
        for field in ("owner", "private", "slug", "title", "items", "position", "shareUrl"):
            with self.subTest(missing=field):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body.pop(field))
                self.assert_hold(snapshot)

    def test_collection_owner_is_exact_not_inferred_from_title_or_slug(self) -> None:
        for field, value in (("name", "another-org"), ("type", "user"), ("_id", "0" * 24)):
            with self.subTest(field=field):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body["owner"].update({field: value}))
                self.assert_hold(snapshot)
        for value in ({}, None, "SZLHOLDINGS"):
            with self.subTest(owner=value):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body.update(owner=value))
                self.assert_hold(snapshot)

    def test_item_type_visibility_author_and_object_identity_are_strict(self) -> None:
        replacements = {
            "type": ("dataset", "space", "kernel", None),
            "repoType": ("dataset", "space", "kernel", None),
            "private": (True, 0, "false", None),
            "author": ("another-org", None, 0),
            "_id": ("", None, 17),
            "id": ("", None, 17),
            "authorData": ({}, None, "SZLHOLDINGS"),
        }
        for field, values in replacements.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    snapshot = snapshot_fixture()
                    mutate_body(snapshot, "khipu-family", lambda body: body["items"][0].update({field: value}))
                    self.assert_hold(snapshot)
        for field in replacements:
            with self.subTest(missing=field):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body["items"][0].pop(field))
                self.assert_hold(snapshot)
        for field, value in (("name", "another-org"), ("type", "user"), ("_id", "0" * 24)):
            with self.subTest(authorData=field):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body["items"][0]["authorData"].update({field: value}))
                self.assert_hold(snapshot)

    def test_duplicate_members_and_object_ids_hold(self) -> None:
        for object_only in (False, True):
            with self.subTest(object_only=object_only):
                snapshot = snapshot_fixture()
                def mutate(body):
                    if object_only:
                        body["items"][1]["_id"] = body["items"][0]["_id"]
                    else:
                        body["items"].append(copy.deepcopy(body["items"][0]))
                mutate_body(snapshot, "khipu-family", mutate)
                self.assert_hold(snapshot)

    def test_snapshot_response_identity_and_transport_failures_hold(self) -> None:
        for field, values in {
            "url": ("https://example.test/collections/target", "https://huggingface.co/api/collections?owner=SZLHOLDINGS", None),
            "method": ("POST", "DELETE", "get", None),
            "status": (201, 302, 401, 404, 500, True, "200", None),
            "received_at": ("", "yesterday", "2026-10-15T12:00:00+09:00", None),
            "body_text": ("{", "[]", "null", 3, None),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    snapshot = snapshot_fixture()
                    snapshot["responses"][0][field] = value
                    self.assert_hold(snapshot)
        for field in ("url", "method", "status", "received_at", "body_text"):
            with self.subTest(missing=field):
                snapshot = snapshot_fixture()
                snapshot["responses"][0].pop(field)
                self.assert_hold(snapshot)
        snapshot = snapshot_fixture()
        snapshot["responses"][0].pop("body_text")
        snapshot["responses"][0]["error"] = "HTTP_ERROR"
        self.assert_hold(snapshot)

    def test_snapshot_duplicate_missing_and_extra_responses_hold(self) -> None:
        for mutation in ("duplicate", "missing", "extra"):
            with self.subTest(mutation=mutation):
                snapshot = snapshot_fixture()
                if mutation == "duplicate":
                    snapshot["responses"][1] = copy.deepcopy(snapshot["responses"][0])
                elif mutation == "missing":
                    snapshot["responses"].pop()
                else:
                    snapshot["responses"].append(copy.deepcopy(snapshot["responses"][0]))
                self.assert_hold(snapshot)
        for snapshot in ({}, {"schema": "wrong", "responses": []}, {"schema": "szl.hf.collection-navigation-snapshot/v1", "responses": {}}, None, []):
            with self.subTest(snapshot=snapshot):
                self.assert_hold(snapshot)

    def test_duplicate_json_keys_are_rejected_in_snapshot_bodies(self) -> None:
        snapshot = snapshot_fixture()
        body = snapshot["responses"][0]["body_text"]
        snapshot["responses"][0]["body_text"] = body[:-1] + ', "private": false}'
        self.assert_hold(snapshot)

    def test_pagination_and_preview_hints_cannot_prove_complete_membership(self) -> None:
        for field, value in (
            ("next", "https://example.test/next"), ("nextPage", 2),
            ("cursor", "unread-items"), ("hasMore", True),
            ("totalItems", 7), ("numItems", 7), ("totalItems", True),
        ):
            with self.subTest(field=field, value=value):
                snapshot = snapshot_fixture()
                mutate_body(snapshot, "khipu-family", lambda body: body.update({field: value}))
                receipt = self.assert_hold(snapshot)
                target = next(row for row in receipt["targets"] if row["id"] == "khipu-family")
                self.assertIn("INCOMPLETE_DETAIL", {finding["code"] for finding in target["findings"]})
        snapshot = snapshot_fixture()
        mutate_body(snapshot, "khipu-family", lambda body: body.update(
            next=None, hasMore=False, totalItems=len(body["items"]), numItems=len(body["items"])
        ))
        self.assertEqual(check.check_snapshot(self.policy, snapshot)["navigation_status"], "PASS")

    def test_receipt_binds_raw_response_bytes_and_policy_without_claiming_freshness(self) -> None:
        snapshot = snapshot_fixture()
        snapshot["responses"][0]["body_text"] += "\n "
        receipt = check.check_snapshot(self.policy, snapshot, mode="snapshot")
        self.assertEqual(receipt["navigation_status"], "PASS")
        self.assertEqual(receipt["mode"], "snapshot")
        self.assertEqual(receipt["evidence_scope"], "UNTRUSTED_LOCAL_SNAPSHOT_ONLY")
        expected_policy = hashlib.sha256(json.dumps(
            self.policy, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertEqual(receipt["policy_sha256"], expected_policy)
        targets = {row["slug"]: row for row in receipt["targets"]}
        for response in snapshot["responses"]:
            slug = response["url"].split("/api/collections/", 1)[1]
            identity = targets[slug]["response"]
            for field in ("url", "method", "status", "received_at"):
                self.assertEqual(identity[field], response[field])
            raw = response["body_text"].encode("utf-8")
            self.assertEqual(identity["body_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(identity["body_bytes"], len(raw))
            self.assertNotIn("body_text", identity)
        self.assert_boundaries(receipt)

    def test_local_report_failure_keeps_safe_receipt_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot_fixture()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch("socket.socket", side_effect=AssertionError("unexpected network")):
                code = check.main(["--snapshot", str(snapshot_path), "--report", str(root / "missing-parent" / "receipt.json")])
        self.assertEqual(code, 2)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["navigation_status"], "HOLD")
        self.assert_boundaries(receipt)
        self.assertIn("REPORT_WRITE_ERROR", {finding["code"] for finding in receipt["findings"]})

    def test_invalid_policy_failure_retains_mode_and_null_digest(self) -> None:
        invalid_policy = copy.deepcopy(self.policy)
        invalid_policy["promotion_allowed"] = True
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy_path = root / "invalid-policy.json"
            policy_path.write_text(json.dumps(invalid_policy), encoding="utf-8")
            for mode, args in (
                ("snapshot", ["--snapshot", str(root / "unused-snapshot.json")]),
                ("live", ["--live"]),
            ):
                with self.subTest(mode=mode):
                    output = io.StringIO()
                    with mock.patch.object(check, "POLICY_PATH", policy_path), contextlib.redirect_stdout(output), mock.patch("socket.socket", side_effect=AssertionError("unexpected network")):
                        code = check.main(args)
                    self.assertEqual(code, 2)
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(receipt["navigation_status"], "HOLD")
                    self.assert_attempt_identity(receipt, mode, None)
                    self.assertIn("INVALID_POLICY", {finding["code"] for finding in receipt["findings"]})

    def test_local_io_failures_distinguish_loaded_and_unavailable_policy_identity(self) -> None:
        digest = hashlib.sha256(json.dumps(self.policy, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for policy_path, expected_digest in ((POLICY_PATH, digest), (root / "missing-policy.json", None)):
                with self.subTest(policy_loaded=expected_digest is not None):
                    output = io.StringIO()
                    with mock.patch.object(check, "POLICY_PATH", policy_path), contextlib.redirect_stdout(output), mock.patch("socket.socket", side_effect=AssertionError("unexpected network")):
                        code = check.main(["--snapshot", str(root / "missing-snapshot.json")])
                    self.assertEqual(code, 2)
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(receipt["navigation_status"], "HOLD")
                    self.assert_attempt_identity(receipt, "snapshot", expected_digest)
                    self.assertIn("LOCAL_IO_ERROR", {finding["code"] for finding in receipt["findings"]})
                    self.assertNotIn(str(root), output.getvalue())

    def test_snapshot_mode_is_network_free_and_does_not_mutate_inputs(self) -> None:
        snapshot = snapshot_fixture()
        before = copy.deepcopy(snapshot)
        policy_before = copy.deepcopy(self.policy)
        with mock.patch("socket.socket", side_effect=AssertionError("unexpected network")):
            receipt = check.check_snapshot(self.policy, snapshot, mode="snapshot")
        self.assertEqual(receipt["navigation_status"], "PASS")
        self.assert_boundaries(receipt)
        self.assertEqual(snapshot, before)
        self.assertEqual(self.policy, policy_before)

    def test_policy_boundary_or_scope_expansion_is_not_accepted(self) -> None:
        mutations = []
        for key in ("provider_writes", "promotion_allowed"):
            for value in (True, 0, "false", None):
                mutations.append((f"{key}-{value!r}", lambda policy, k=key, v=value: policy.update({k: v})))
        for key in ("model_quality", "production_readiness"):
            mutations.append((key, lambda policy, k=key: policy.update({k: "READY"})))
        mutations.extend([
            ("legacy-green", lambda policy: policy.update(legacy_start_here_reconciliation="PASS")),
            ("duplicate-target", lambda policy: policy["targets"].append(copy.deepcopy(policy["targets"][0]))),
            ("duplicate-role", lambda policy: policy["targets"][1].update(id="khipu-family")),
            ("missing-target", lambda policy: policy["targets"].pop()),
            ("foreign-owner", lambda policy: policy["owner"].update(name="another-org")),
            ("foreign-owner-id", lambda policy: policy["owner"].update(id="0" * 24)),
            ("user-owner", lambda policy: policy["owner"].update(type="user")),
            ("title-alias", lambda policy: policy["targets"][0].update(title="Trained Models & Weights")),
            ("slug-alias", lambda policy: policy["targets"][0].update(slug="SZLHOLDINGS/another-collection")),
            ("promoted-class", lambda policy: policy["targets"][0].update(classification="PRODUCTION")),
            ("missing-anchor", lambda policy: policy["targets"][0]["required_members"].pop()),
            ("remove-nemo-exclusion", lambda policy: policy["targets"][0].update(forbidden_members=[])),
            ("require-deprecated", lambda policy: policy["targets"][2]["required_members"].append("SZLHOLDINGS/szl-governed-norm")),
            ("permit-unknown", lambda policy: policy["targets"][2]["optional_members"].append("SZLHOLDINGS/new-kernel")),
            ("duplicate-member", lambda policy: policy["targets"][0]["optional_members"].append(policy["targets"][0]["required_members"][0])),
            ("promote-deprecated", lambda policy: policy["targets"][2]["member_classifications"].update({"SZLHOLDINGS/szl-governed-norm": "SOFTWARE"})),
            ("showcase-member", lambda policy: policy["targets"][1]["optional_members"].append("SZLHOLDINGS/SZL-Khipu-1.5B")),
            ("showcase-prose-change", lambda policy: policy["targets"][1].update(description_exact="No model is promoted.")),
        ])
        for name, mutation in mutations:
            with self.subTest(mutation=name):
                policy = copy.deepcopy(self.policy)
                mutation(policy)
                with self.assertRaises(check.ContractError) as caught:
                    check.validate_policy(policy)
                self.assertIsInstance(caught.exception.code, str)
        for policy in (None, [], {}, {"schema": "wrong"}):
            with self.subTest(policy=policy):
                with self.assertRaises(check.ContractError):
                    check.validate_policy(policy)


class JsonInputContracts(unittest.TestCase):
    def test_duplicate_keys_are_not_last_value_wins(self) -> None:
        for raw in (b'{"private": true, "private": false}', b'{"nested": {"id": 1, "id": 2}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(check.ContractError) as caught:
                    check.parse_json_bytes(raw)
                self.assertEqual(caught.exception.code, "JSON_DUPLICATE_KEY")

    def test_size_limit_applies_to_bytes_before_parsing(self) -> None:
        self.assertEqual(check.parse_json_bytes(b"{}", max_bytes=2), {})
        for raw in (b"{} ", '"\u03bb"'.encode("utf-8")):
            with self.subTest(raw=raw):
                with self.assertRaises(check.ContractError) as caught:
                    check.parse_json_bytes(raw, max_bytes=2)
                self.assertEqual(caught.exception.code, "INPUT_TOO_LARGE")

    def test_overlong_numeric_token_is_a_normalized_json_error(self) -> None:
        raw = b'{"value": ' + b"9" * 5000 + b"}"
        with self.assertRaises(check.ContractError) as caught:
            check.parse_json_bytes(raw)
        self.assertEqual(caught.exception.code, "INVALID_JSON")
        # ContractError subclasses ValueError: normalization must not swallow
        # the earlier, more specific duplicate-key rejection.
        with self.assertRaises(check.ContractError) as duplicate:
            check.parse_json_bytes(b'{"id": 1, "id": 2}')
        self.assertEqual(duplicate.exception.code, "JSON_DUPLICATE_KEY")

    def test_invalid_utf8_json_and_nonfinite_numbers_are_rejected(self) -> None:
        for raw in (
            b"\xff", b"{", b'{"x": NaN}', b'{"x": Infinity}', b'{"x": -Infinity}', b'{"x": 1e9999}',
            b"[" * 1200 + b"]" * 1200,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(check.ContractError):
                    check.parse_json_bytes(raw)


class FakeResponse:
    def __init__(self, url: str, raw: bytes, *, status: int = 200, read_error=None):
        self.url = url
        self.raw = raw
        self.status = status
        self.read_error = read_error
        self.offset = 0
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read1(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if self.read_error is not None:
            raise self.read_error
        chunk = self.raw[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("unexpected retry or additional request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class PublicReadTransportContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()
        fixture = snapshot_fixture()
        self.urls = [response["url"] for response in fixture["responses"]]
        self.responses = [FakeResponse(response["url"], response["body_text"].encode("utf-8"))
                          for response in fixture["responses"]]

    def fetch_with_fake_opener(self, responses):
        opener = FakeOpener(responses)
        with mock.patch.object(check.urllib.request, "build_opener", return_value=opener) as factory:
            with mock.patch.dict(os.environ, {
                "HF_TOKEN": "credential-canary-never-used",
                "HF_ORG_TOKEN": "credential-canary-never-used",
                "HF_ORG_TOKEN1": "credential-canary-never-used",
            }), mock.patch("socket.socket", side_effect=AssertionError("unexpected real network")):
                snapshot = check.fetch_live(self.policy)
        factory.assert_called_once()
        handlers = factory.call_args.args
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], check.NoRedirect)
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual([request.full_url for request, _ in opener.requests], self.urls)
        for request, timeout in opener.requests:
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(timeout, check.TIMEOUT_SECONDS)
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(set(headers), {"accept", "user-agent"})
            self.assertEqual(headers["accept"], "application/json")
        self.assertNotIn("credential-canary-never-used", json.dumps(snapshot))
        return snapshot

    def test_live_transport_is_exactly_three_fixed_unauthenticated_gets(self) -> None:
        snapshot = self.fetch_with_fake_opener(self.responses)
        receipt = check.check_snapshot(self.policy, snapshot, mode="live")
        self.assertEqual(receipt["navigation_status"], "PASS")
        self.assertEqual(receipt["evidence_scope"], "THREE_PUBLIC_COLLECTION_DETAILS_ONLY")
        self.assertEqual(receipt["boundaries"], BOUNDARIES)
        self.assertTrue(all(response.read_sizes for response in self.responses))

    def test_transport_failures_are_normalized_without_retries_or_raw_errors(self) -> None:
        canary = "raw-provider-error-canary"
        failures = [
            (urllib.error.HTTPError(self.urls[0], 503, canary, {"secret": canary}, None), "HTTP_ERROR"),
            (urllib.error.HTTPError(self.urls[0], 302, canary, {"Location": "https://example.test/"}, None), "REDIRECT_REJECTED"),
            (TimeoutError(canary), "TIMEOUT"),
            (urllib.error.URLError(canary), "NETWORK_ERROR"),
            (OSError(canary), "NETWORK_ERROR"),
            (FakeResponse("https://example.test/redirect", b"{}"), "REDIRECT_REJECTED"),
            (FakeResponse(self.urls[0], b"\xff"), "INVALID_JSON"),
            (FakeResponse(self.urls[0], b"x" * (check.MAX_BODY_BYTES + 1)), "INPUT_TOO_LARGE"),
            (FakeResponse(self.urls[0], b"", read_error=TimeoutError(canary)), "TIMEOUT"),
        ]
        for first, expected in failures:
            with self.subTest(expected=expected, failure=type(first).__name__):
                trailing = [FakeResponse(response.url, response.raw) for response in self.responses[1:]]
                snapshot = self.fetch_with_fake_opener([first, *trailing])
                self.assertEqual(snapshot["responses"][0]["error"], expected)
                self.assertNotIn("body_text", snapshot["responses"][0])
                receipt = check.check_snapshot(self.policy, snapshot, mode="live")
                self.assertEqual(receipt["navigation_status"], "HOLD")
                self.assertEqual(receipt["boundaries"], BOUNDARIES)
                self.assertNotIn(canary, json.dumps({"snapshot": snapshot, "receipt": receipt}))
                if isinstance(first, FakeResponse) and expected == "INPUT_TOO_LARGE":
                    self.assertEqual(first.offset, check.MAX_BODY_BYTES + 1)
                    self.assertTrue(all(0 < size <= 65536 for size in first.read_sizes))
                if isinstance(first, FakeResponse) and expected == "REDIRECT_REJECTED":
                    self.assertEqual(first.read_sizes, [])

    def test_deadline_expiration_stops_reading_and_remains_normalized(self) -> None:
        ticks = iter((0, check.TIMEOUT_SECONDS + 1))
        with mock.patch.object(check.time, "monotonic", side_effect=lambda: next(ticks, check.TIMEOUT_SECONDS + 1)):
            snapshot = self.fetch_with_fake_opener(self.responses)
        self.assertEqual(snapshot["responses"][0]["error"], "TIMEOUT")
        self.assertEqual(self.responses[0].read_sizes, [])
        receipt = check.check_snapshot(self.policy, snapshot, mode="live")
        self.assertEqual(receipt["navigation_status"], "HOLD")
        self.assertEqual(receipt["boundaries"], BOUNDARIES)

    def test_final_empty_read_cannot_pass_after_the_deadline(self) -> None:
        clock = [0]

        class SlowEOFResponse(FakeResponse):
            def read1(self, size):
                chunk = super().read1(size)
                if not chunk:
                    clock[0] = check.TIMEOUT_SECONDS + 1
                return chunk

        first = SlowEOFResponse(self.responses[0].url, self.responses[0].raw)
        with mock.patch.object(check.time, "monotonic", side_effect=lambda: clock[0]):
            snapshot = self.fetch_with_fake_opener([first, *self.responses[1:]])
        self.assertEqual(first.offset, len(first.raw))
        self.assertEqual(len(first.read_sizes), 2)
        self.assertEqual(snapshot["responses"][0]["error"], "TIMEOUT")
        self.assertNotIn("body_text", snapshot["responses"][0])
        receipt = check.check_snapshot(self.policy, snapshot, mode="live")
        self.assertEqual(receipt["navigation_status"], "HOLD")
        self.assertEqual(receipt["boundaries"], BOUNDARIES)

    def test_redirect_handler_never_follows_an_alternate_destination(self) -> None:
        request = check.urllib.request.Request(self.urls[0], method="GET")
        with self.assertRaises(check.ContractError) as caught:
            check.NoRedirect().redirect_request(request, None, 302, "raw-canary", {}, "https://example.test/redirect")
        self.assertEqual(caught.exception.code, "REDIRECT_REJECTED")


if __name__ == "__main__":
    unittest.main()
