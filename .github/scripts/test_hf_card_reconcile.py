#!/usr/bin/env python3
"""Behavioral contracts for exact-plan Hub card reconciliation; no live writes."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SPEC = importlib.util.spec_from_file_location("hf_card_reconcile", Path(__file__).with_name("hf_card_reconcile.py"))
RECONCILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILE)
HEAD = "a" * 40
COMMIT = "b" * 40
SOURCE = "c" * 40
TOKEN = "test-credential-never-retain"


class CardReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = {"repo_id": "SZLHOLDINGS/yarqa", "kind": "spaces",
                      "license": "apache-2.0", "source_repo": "szl-holdings/yarqa", "body_file": "yarqa.md"}
        self.defaults = {"org": "SZLHOLDINGS", "require_stamp": True}
        self.cfg = {"schema": "szl.governance.hf_card_expectations/v1", "defaults": self.defaults, "assets": [self.asset]}
        self.config = self.root / "expectations.json"
        self.write_config()
        self.desired = "# Yarqa\n\n" + RECONCILE.stamp_block(self.asset, self.defaults)
        (self.root / "yarqa.md").write_bytes(self.desired.encode("utf-8"))
        self.card = "---\ntitle: Yarqa\ntags:\n  - szl\n---\n\n# Existing\n49 estates\n"

    def write_config(self):
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def plan(self, card=None, allow=True, asset=None):
        responses = [(json.dumps({"sha": HEAD}), 200), (card if card is not None else self.card, 200)]
        with patch.object(RECONCILE, "hub_request", side_effect=responses) as requests:
            result = RECONCILE.plan_asset(asset or self.asset, self.defaults, None, str(self.root), allow)
        self.assertIn("/raw/" + HEAD + "/README.md", requests.call_args_list[1].args[1])
        return result

    def run_main(self, extra=(), responses=(), token=None, source=SOURCE):
        output = self.root / "receipt.json"
        args = ["hf_card_reconcile.py", "--config", str(self.config), "--bodies-dir", str(self.root), "--out-json", str(output), *extra]
        env = {"GITHUB_SHA": source}
        if token:
            env["HF_CARD_WRITE_TOKEN"] = token
        with patch.object(RECONCILE.sys, "argv", args), patch.dict(RECONCILE.os.environ, env, clear=True), \
             patch.object(RECONCILE, "hub_request", side_effect=responses) as requests, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = RECONCILE.main()
        return code, json.loads(output.read_text(encoding="utf-8")), requests

    def identity(self, name="betterwithage", role="admin"):
        return json.dumps({"name": name, "orgs": [{"name": "SZLHOLDINGS", "roleInOrg": role}]}), 200

    def expected_plan(self, allow=False):
        extra = ["--allow-body-replace"] if allow else []
        code, receipt, _ = self.run_main(extra, [(json.dumps({"sha": HEAD}), 200), (self.card, 200)])
        self.assertEqual(code, 0)
        path = self.root / "expected-plan.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path, receipt

    def test_body_gate_previews_only_when_enabled_and_is_idempotent(self):
        without = self.plan(allow=False)
        self.assertNotIn("body<=yarqa.md", without["changes"])
        self.assertIn("# Existing", without["new_text"])
        first = self.plan()
        self.assertIn("body<=yarqa.md", first["changes"])
        second = self.plan(first["new_text"])
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["new_text"], first["new_text"])
        self.assertEqual(second["before_sha256"], second["after_sha256"])

    def test_constellation_body_and_unrelated_crlf_yaml_are_preserved_exactly(self):
        asset = dict(self.asset)
        asset.pop("body_file")
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline):
                fm = newline.join(["title: Existing", "description: |", "", "  Keep this prose", "tags:", "  - szl", ""])
                body = newline * 3 + "# Existing" + newline + "49 estates" + newline * 3
                card = "---" + newline + fm + "---" + newline + body
                result = self.plan(card, asset=asset)
                _, after_fm, _, after_body = RECONCILE.split_card(result["new_text"])
                self.assertTrue(after_fm.startswith(fm))
                self.assertTrue(after_body.startswith(body))
                self.assertEqual(result["bytes_before"], len(card.encode("utf-8")))
                self.assertNotIn("body<=yarqa.md", result["changes"])

    def test_rejects_block_and_duplicate_target_keys_without_corruption(self):
        for fm in ("license:\n  - mit\n", "license: |\n  apache-2.0\n", "license: [mit]\n", "license: mit\nlicense: bsd\n", '"license": mit\n'):
            with self.subTest(fm=fm), self.assertRaises(ValueError):
                RECONCILE.set_scalar(fm, "license", "apache-2.0")

    def test_double_quoted_description_is_a_real_noop(self):
        original = 'short_description: "A description." # preserved comment\r\n'
        self.assertEqual(RECONCILE.set_scalar(original, "short_description", "A description."), (original, False))

    def test_stamp_requires_the_complete_contract(self):
        self.assertFalse(RECONCILE.has_stamp("Governance of SZLHOLDINGS/yarqa", self.asset))
        self.assertTrue(RECONCILE.has_stamp(self.desired, self.asset))

    def test_configured_stamp_heading_is_idempotent(self):
        self.defaults["stamp_heading"] = "## Provenance and governance"
        asset = dict(self.asset)
        asset.pop("body_file")
        first = self.plan(asset=asset)
        self.assertIn("body+=governance_stamp", first["changes"])
        self.assertEqual(first["new_text"].count(self.defaults["stamp_heading"]), 1)
        second = self.plan(first["new_text"], asset=asset)
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["new_text"], first["new_text"])

    def test_invalid_selection_writes_failure_receipt_before_network(self):
        for only in (", ,", "SZLHOLDINGS/missing", "SZLHOLDINGS/yarqa,SZLHOLDINGS/missing"):
            with self.subTest(only=only):
                code, receipt, requests = self.run_main(["--only", only])
                self.assertEqual(code, 1)
                self.assertFalse(receipt["success"])
                self.assertEqual(receipt["receipt_state"], "UNSIGNED_HONEST")
                requests.assert_not_called()

    def test_invalid_config_and_body_paths_fail_before_network(self):
        variants = []
        for key, value in (("schema", "wrong"), ("assets", [])):
            item = copy.deepcopy(self.cfg)
            item[key] = value
            variants.append(item)
        item = copy.deepcopy(self.cfg)
        item["assets"].append(copy.deepcopy(self.asset))
        variants.append(item)
        for key, value in (("kind", "invalid"), ("repo_id", "other/yarqa"), ("body_file", "../outside.md")):
            item = copy.deepcopy(self.cfg)
            item["assets"][0][key] = value
            variants.append(item)
        for variant in variants:
            with self.subTest(config=variant):
                self.config.write_text(json.dumps(variant), encoding="utf-8")
                code, receipt, requests = self.run_main()
                self.assertEqual(code, 1)
                self.assertIn("error", receipt)
                requests.assert_not_called()

    def test_plan_does_not_attest_credentials(self):
        code, receipt, requests = self.run_main(["--allow-body-replace"], [(json.dumps({"sha": HEAD}), 200), (self.card, 200)])
        self.assertEqual(code, 0)
        self.assertNotIn("identity", receipt)
        self.assertEqual(receipt["source_revision"], SOURCE)
        self.assertEqual(len(receipt["assets"]), 1)
        self.assertEqual(receipt["assets"][0]["original_text"], self.card)
        self.assertTrue(all(call.args[0] == "GET" for call in requests.call_args_list))

    def test_401_preflight_retains_failure_without_credentials_or_writes(self):
        expected, _ = self.expected_plan()
        code, receipt, requests = self.run_main(["--apply", "--expected-plan", str(expected)], [(TOKEN, 401)], TOKEN)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["identity"]["http_status"], 401)
        self.assertNotIn(TOKEN, json.dumps(receipt))
        self.assertEqual(requests.call_count, 1)
        self.assertEqual(requests.call_args.args[1], "/api/whoami-v2")

    def test_wrong_owner_and_read_member_fail_preflight(self):
        expected, _ = self.expected_plan()
        for identity in (self.identity(name="someone_else"), self.identity(role="read")):
            with self.subTest(identity=identity):
                code, receipt, requests = self.run_main(["--apply", "--expected-plan", str(expected)], [identity], TOKEN)
                self.assertEqual(code, 1)
                self.assertEqual(receipt["identity"]["label"], "UNAVAILABLE")
                self.assertEqual(requests.call_count, 1)

    def test_missing_token_retains_failure_receipt(self):
        expected, _ = self.expected_plan()
        code, receipt, requests = self.run_main(["--apply", "--expected-plan", str(expected)])
        self.assertEqual(code, 1)
        self.assertIn("requires an HF token", receipt["error"])
        requests.assert_not_called()

    def test_apply_without_expected_plan_fails_before_config_or_network(self):
        with patch.object(RECONCILE, "load_config", side_effect=AssertionError("must not load config")) as load:
            code, receipt, requests = self.run_main(["--apply"], token=TOKEN)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["error"], "--apply requires --expected-plan")
        self.assertFalse(receipt["success"])
        self.assertEqual(receipt["assets"], [])
        self.assertNotIn("identity", receipt)
        load.assert_not_called()
        requests.assert_not_called()

    def test_main_applies_only_with_a_matching_generated_plan(self):
        expected, plan = self.expected_plan(allow=True)
        desired = plan["assets"][0]["new_text"]
        code, receipt, requests = self.run_main(
            ["--apply", "--allow-body-replace", "--expected-plan", str(expected)],
            [self.identity(), (json.dumps({"sha": HEAD}), 200), (self.card, 200),
             (json.dumps({"commitOid": COMMIT}), 200), (desired, 200), (json.dumps({"sha": COMMIT}), 200)], TOKEN)
        self.assertEqual(code, 0)
        self.assertTrue(receipt["success"])
        self.assertTrue(receipt["assets"][0]["main_verified"])
        self.assertEqual(sum(call.args[0] == "POST" for call in requests.call_args_list), 1)

    def test_exact_plan_rejects_source_config_body_and_hub_drift(self):
        code, original, _ = self.run_main(["--allow-body-replace"], [(json.dumps({"sha": HEAD}), 200), (self.card, 200)])
        self.assertEqual(code, 0)
        expected = self.root / "expected.json"
        expected.write_text(json.dumps(original), encoding="utf-8")
        for key, value in (("source_revision", "d" * 40), ("config_sha256", "changed"), ("body_files_sha256", {}), ("body_replace_allowed", False)):
            modified = copy.deepcopy(original)
            modified[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                RECONCILE.validate_expected_plan(modified, str(expected))
        for key, value in (("hub_revision", "e" * 40), ("before_sha256", "changed"), ("after_sha256", "changed"), ("new_text", "changed")):
            modified = copy.deepcopy(original)
            modified["assets"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                RECONCILE.validate_expected_plan(modified, str(expected))
        RECONCILE.validate_expected_plan(original, str(expected))
        code, receipt, requests = self.run_main(["--apply", "--allow-body-replace", "--expected-plan", str(expected)],
            [self.identity(), (json.dumps({"sha": "e" * 40}), 200), (self.card, 200)], TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("hub_revision", receipt["error"])
        self.assertTrue(all(call.args[0] == "GET" for call in requests.call_args_list))

    def test_direct_write_uses_parent_and_base64_and_verifies_main(self):
        row = self.plan()
        response = json.dumps({"commitOid": COMMIT, "commitUrl": "https://huggingface.co/commit/test"})
        with patch.object(RECONCILE, "hub_request", side_effect=[(response, 200), (row["new_text"], 200), (json.dumps({"sha": COMMIT}), 200)]) as requests:
            result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
        self.assertTrue(result["applied"])
        self.assertTrue(result["main_verified"])
        records = [json.loads(line) for line in requests.call_args_list[0].args[3].decode("utf-8").splitlines()]
        self.assertEqual(records[0]["value"]["parentCommit"], HEAD)
        self.assertEqual(records[1]["value"]["encoding"], "base64")
        self.assertEqual(base64.b64decode(records[1]["value"]["content"]).decode("utf-8"), row["new_text"])

    def test_403_fallback_retains_pr_identity_and_requires_later_main_readback(self):
        row = self.plan()
        url = "https://huggingface.co/spaces/SZLHOLDINGS/yarqa/discussions/1"
        response = json.dumps({"commitOid": COMMIT, "pullRequestUrl": url})
        with patch.object(RECONCILE, "hub_request", side_effect=[("denied", 403), (response, 201), (row["new_text"], 200)]) as requests:
            result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
        self.assertEqual([c.args[0] for c in requests.call_args_list], ["POST", "POST", "GET"])
        self.assertTrue(requests.call_args_list[1].args[1].endswith("?create_pr=1"))
        self.assertEqual(result["pull_request_url"], url)
        self.assertTrue(result["verified"])
        self.assertTrue(result["pending_main_readback"])
        self.assertFalse(result["main_verified"])

    def test_non_403_write_failure_is_terminal_and_records_no_success(self):
        for status in (0, 401, 409, 429, 500):
            row = self.plan()
            with self.subTest(status=status), patch.object(RECONCILE, "hub_request", return_value=("failed", status)) as requests:
                result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
                self.assertFalse(result["applied"])
                self.assertFalse(result["verified"])
                self.assertEqual(requests.call_count, 1)

    def test_commit_readback_or_main_revision_mismatch_fails_verification(self):
        for responses in ([('different', 200)], [(None, 200), (json.dumps({"sha": HEAD}), 200)]):
            row = self.plan()
            responses = [(row["new_text"] if text is None else text, status) for text, status in responses]
            with patch.object(RECONCILE, "hub_request", side_effect=[(json.dumps({"commitOid": COMMIT}), 200), *responses]):
                result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
            self.assertTrue(result["applied"])
            self.assertFalse(result["verified"])

    def test_noop_does_not_write_and_is_reported_explicitly(self):
        row = self.plan(self.plan()["new_text"])
        with patch.object(RECONCILE, "hub_request") as requests:
            result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
        requests.assert_not_called()
        self.assertFalse(result["applied"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["outcome"], "already_current")

    def test_malformed_main_readback_preserves_the_known_successful_commit(self):
        for main in ("not JSON", "[]", "null"):
            row = self.plan()
            with self.subTest(main=main), patch.object(RECONCILE, "hub_request", side_effect=[
                (json.dumps({"commitOid": COMMIT}), 200), (row["new_text"], 200), (main, 200)]):
                result = RECONCILE.apply_asset(row, TOKEN, "reconcile")
            self.assertTrue(result["applied"])
            self.assertEqual(result["commit_oid"], COMMIT)
            self.assertEqual(result["outcome"], "committed")
            self.assertFalse(result["verified"])
            self.assertFalse(result["main_verified"])

    def test_body_file_without_own_stamp_is_still_idempotent(self):
        (self.root / "yarqa.md").write_bytes(b"# Replacement\n")
        first = self.plan()
        second = self.plan(first["new_text"])
        self.assertEqual(second["new_text"], first["new_text"])
        self.assertEqual(second["changes"], [])

    def test_post_transport_failure_is_never_retried(self):
        for failure in (urllib.error.URLError("connection lost"), urllib.error.HTTPError("https://huggingface.co/test", 503, "unavailable", {}, io.BytesIO(b"failed"))):
            with self.subTest(failure=type(failure).__name__), patch.object(RECONCILE.urllib.request, "urlopen", side_effect=failure) as request, patch.object(RECONCILE.time, "sleep") as sleep:
                _, status = RECONCILE.hub_request("POST", "/test", TOKEN, b"{}")
                self.assertIn(status, (0, 503))
                self.assertEqual(request.call_count, 1)
                sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
