#!/usr/bin/env python3
"""Behavioral contracts for exact-plan Hub card reconciliation; no live writes."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import urllib.error


SPEC = importlib.util.spec_from_file_location("hf_card_reconcile", Path(__file__).with_name("hf_card_reconcile.py"))
RECONCILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILE)
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "hf-card-reconcile.yml"
# The apply step is exercised with the runner's own bash; CI runs on ubuntu-latest.
BASH = shutil.which("bash") if os.name == "posix" else None
HEAD = "a" * 40
COMMIT = "b" * 40
SOURCE = "c" * 40
TOKEN = "test-credential-never-retain"
LABELS = "- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE"
RECEIPTS = "- Receipts remain UNSIGNED_HONEST until the DSSE lane signs"
COMPLETED = "governance_stamp~=completed_missing_markers"


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

    def run_main(self, extra=(), responses=(), token=None, source=SOURCE, env_extra=None):
        output = self.root / "receipt.json"
        args = ["hf_card_reconcile.py", "--config", str(self.config), "--bodies-dir", str(self.root), "--out-json", str(output), *extra]
        env = {"GITHUB_SHA": source, **(env_extra or {})}
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

    def test_space_short_description_length_boundaries(self):
        for description in ("a", "a" * 60):
            with self.subTest(valid_length=len(description)):
                self.asset["short_description"] = description
                self.write_config()
                _, selected, _ = RECONCILE.load_config(str(self.config), str(self.root), "")
                self.assertEqual(selected[0]["short_description"], description)
        for description in ("", "a" * 61, None, 60):
            with self.subTest(invalid_description=description):
                self.asset["short_description"] = description
                self.write_config()
                code, receipt, requests = self.run_main()
                self.assertEqual(code, 1)
                self.assertIn("1 to 60 characters", receipt["error"])
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

    def governed(self, repo="yarqa"):
        return {"repo_id": f"SZLHOLDINGS/{repo}", "kind": "spaces", "license": "apache-2.0",
                "source_repo": f"szl-holdings/{repo}"}

    def assert_noop_on_rerun(self, result, asset):
        again = self.plan(result["new_text"], asset=asset)
        self.assertEqual(again["label"], "MEASURED")
        self.assertEqual(again["changes"], [])
        self.assertEqual(again["new_text"], result["new_text"])
        self.assertEqual(again["before_sha256"], again["after_sha256"])
        self.assertNotIn("governance_markers_added", again)
        with patch.object(RECONCILE, "hub_request") as requests:
            applied = RECONCILE.apply_asset(again, TOKEN, "reconcile")
        requests.assert_not_called()
        self.assertEqual(applied["outcome"], "already_current")

    def test_partial_governance_section_is_completed_in_place_not_duplicated(self):
        asset = self.governed()
        source = "- Source of truth: [github.com/szl-holdings/yarqa](https://github.com/szl-holdings/yarqa)"
        cases = (
            ("Hub Space repository: SZLHOLDINGS/yarqa\n\n- Source authority: https://github.com/szl-holdings/yarqa\n",
             [LABELS, RECEIPTS], ""),
            ("Hub Space repository: SZLHOLDINGS/yarqa\n\n" + LABELS + "\n", [source, RECEIPTS], ""),
            ("Owner prose without any marker.\n", ["- Hub repository: `SZLHOLDINGS/yarqa`", source, LABELS, RECEIPTS], "\n"),
        )
        for section, missing, separator in cases:
            with self.subTest(section=section):
                card = "---\ntitle: Yarqa\nlicense: apache-2.0\n---\n\n# Yarqa\n\n## Governance\n\n" + section
                result = self.plan(card, asset=asset)
                self.assertEqual(result["changes"], [COMPLETED])
                self.assertEqual(result["governance_markers_added"], missing)
                self.assertEqual(result["new_text"], card + separator + "".join(line + "\n" for line in missing))
                self.assertEqual(result["new_text"].count("## Governance"), 1)
                self.assertTrue(RECONCILE.has_stamp(result["new_text"], asset, self.defaults))
                self.assert_noop_on_rerun(result, asset)

    def test_duplicate_governance_headings_fail_closed_before_any_write(self):
        asset = self.governed()
        complete = RECONCILE.stamp_block(asset, self.defaults)
        for body in ("## Governance\n\nfirst\n\n## Governance\n\nsecond\n",
                     complete + "\n## Governance ##\n\nAll markers present still fails closed.\n"):
            with self.subTest(body=body):
                card = "---\ntitle: Yarqa\n---\n\n" + body
                row = self.plan(card, asset=asset)
                self.assertEqual(row["label"], "UNAVAILABLE")
                self.assertIn("'## Governance' appears 2 times", row["detail"])
                self.assertNotIn("new_text", row)
                self.cfg["assets"] = [asset]
                self.write_config()
                code, receipt, requests = self.run_main([], [(json.dumps({"sha": HEAD}), 200), (card, 200)])
                self.assertEqual(code, 1)
                self.assertFalse(receipt["success"])
                self.assertIn("SZLHOLDINGS/yarqa: stamp heading '## Governance' appears 2 times", receipt["error"])
                self.assertTrue(all(call.args[0] == "GET" for call in requests.call_args_list))

    def test_fenced_heading_text_is_neither_a_section_nor_a_duplicate(self):
        asset = self.governed()
        card = ("---\ntitle: Yarqa\nlicense: apache-2.0\n---\n\n```markdown\n## Governance\n```\n\n"
                "## Governance\n\nHub Space repository: SZLHOLDINGS/yarqa\n"
                "- Source authority: https://github.com/szl-holdings/yarqa\n")
        result = self.plan(card, asset=asset)
        self.assertEqual(result["changes"], [COMPLETED])
        self.assertEqual(result["new_text"], card + LABELS + "\n" + RECEIPTS + "\n")
        self.assert_noop_on_rerun(result, asset)

    def test_mid_document_section_keeps_following_content_byte_identical(self):
        asset = self.governed()
        fm = "---\ntitle: Yarqa\nlicense: apache-2.0\nshort_description: Auditable plug-flow compartmentalization. Apache-2.0\n---\n"
        following = ("\n## For investors\n\nYarqa carries the SZL pattern beyond language models.\n\n"
                     "Doctrine v11 - nothing glows that did not earn it.")
        governance = ("## Governance\n\nHub Space repository: SZLHOLDINGS/yarqa\n\n"
                      "- Source authority: https://github.com/szl-holdings/yarqa\n"
                      "- Runtime boundary: a responding Space is not a production certificate.\n")
        nested = governance + ("\n### Boundary detail\n\n~~~text\n# a fenced comment, not a heading\n~~~\n\n"
                               "Subsection prose stays inside the section.\n")
        for section, insert in ((governance, LABELS + "\n" + RECEIPTS + "\n"),
                                (nested, "\n" + LABELS + "\n" + RECEIPTS + "\n")):
            with self.subTest(nested=section is nested):
                card = fm + "\n# Yarqa\n\n~~~text\ngit clone https://github.com/szl-holdings/yarqa.git\n~~~\n\n" + section + following
                result = self.plan(card, asset=asset)
                self.assertEqual(result["changes"], [COMPLETED])
                self.assertEqual(result["new_text"], card.replace(section + following, section + insert + following))
                self.assertTrue(result["new_text"].endswith(section + insert + following))
                self.assertEqual(RECONCILE.split_card(result["new_text"])[1], RECONCILE.split_card(card)[1])
                self.assertEqual(result["new_text"].count("## Governance"), 1)
                self.assert_noop_on_rerun(result, asset)

    def test_crlf_card_completion_keeps_crlf_bytes(self):
        asset = self.governed()
        card = "\r\n".join(["---", "title: Yarqa", "license: apache-2.0", "---", "", "# Yarqa", "",
                            "## Governance", "", "- Hub repository: `SZLHOLDINGS/yarqa`",
                            "- Source: https://github.com/szl-holdings/yarqa", "", "## Next", "", "tail", ""])
        result = self.plan(card, asset=asset)
        text = result["new_text"]
        self.assertEqual(result["changes"], [COMPLETED])
        self.assertEqual(text, card.replace("yarqa\r\n\r\n## Next", "yarqa\r\n" + LABELS + "\r\n" + RECEIPTS + "\r\n\r\n## Next"))
        self.assertEqual(text.count("\n"), text.count("\r\n"))
        self.assertTrue(text.endswith("tail\r\n"))
        self.assert_noop_on_rerun(result, asset)

    def test_constellation_like_card_keeps_prose_and_estate_claims_byte_identical(self):
        asset = self.governed("szl-constellation")
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline):
                card = newline.join([
                    "---", "title: SZL Constellation", "license: apache-2.0", "tags:", "  - szl", "---", "",
                    "# SZL Constellation - the living archive", "", "49 estates, unarchived as light.", "",
                    "[Canonical GitHub source](https://github.com/szl-holdings/szl-constellation) |", "",
                    "## Shader Fabric", "", "Measured in headless Edge: 49 estates, 0 dropped.", "",
                    "| State | Meaning |", "|---|---|", "| MEASURED | Measured evidence exists |", "",
                    "## Developer start", "", "~~~text", "python -m http.server 8000",
                    "# open http://localhost:8000/holo/demo.html", "~~~", "",
                    "## Governance", "", "Hub repository: SZLHOLDINGS/szl-constellation", "",
                    "- Source authority: https://github.com/szl-holdings/szl-constellation",
                    "- Evidence boundary: verification proves integrity and declared origin, not availability.", "",
                    "Doctrine v11 - nothing glows that did not earn it."])
                result = self.plan(card, asset=asset)
                text = result["new_text"]
                self.assertEqual(result["changes"], [COMPLETED])
                self.assertEqual(result["governance_markers_added"], [LABELS, RECEIPTS])
                self.assertEqual(text, card + newline + newline + LABELS + newline + RECEIPTS)
                self.assertTrue(text.startswith(card))
                self.assertFalse(text.endswith(newline))
                self.assertEqual(text.count("49 estates"), 2)
                self.assertEqual(text.count("## Governance"), 1)
                self.assertEqual(RECONCILE.split_card(text)[1], RECONCILE.split_card(card)[1])
                self.assert_noop_on_rerun(result, asset)

    def test_ambiguous_section_boundaries_fail_closed(self):
        asset = self.governed()
        for body, reason in (("## Governance\n\nSZLHOLDINGS/yarqa\n\n~~~text\nunterminated\n", "unclosed fenced code"),
                             ("## Governance\n\nSZLHOLDINGS/yarqa\n\nFooter\n---\n\nmore\n", "setext heading")):
            with self.subTest(reason=reason):
                row = self.plan("---\ntitle: Yarqa\n---\n\n" + body, asset=asset)
                self.assertEqual(row["label"], "UNAVAILABLE")
                self.assertIn(reason, row["detail"])
        complete = ("---\ntitle: Yarqa\nlicense: apache-2.0\n---\n\n" + RECONCILE.stamp_block(asset, self.defaults)
                    + "\nFooter\n---\n\n~~~text\nunterminated\n")
        row = self.plan(complete, asset=asset)
        self.assertEqual((row["label"], row["changes"], row["new_text"]), ("MEASURED", [], complete))

    def test_repository_expectation_keeps_owner_hub_bodies(self):
        config = Path(__file__).resolve().parents[1] / "config" / "hf_card_expectations.json"
        cfg, selected, hashes = RECONCILE.load_config(str(config), str(config.parent / "hf_cards"), "")
        self.assertEqual({a["repo_id"] for a in selected}, {"SZLHOLDINGS/yarqa", "SZLHOLDINGS/szl-constellation"})
        self.assertEqual(cfg["defaults"]["stamp_heading"], "## Governance")
        self.assertFalse([a["repo_id"] for a in selected if "body_file" in a])
        self.assertEqual(hashes["body_files_sha256"], {})

    def test_completion_plan_binds_apply_to_the_exact_completed_bytes(self):
        asset = self.governed()
        self.cfg["assets"] = [asset]
        self.write_config()
        self.card = ("---\ntitle: Yarqa\nlicense: apache-2.0\n---\n\n## Governance\n\nHub Space repository: SZLHOLDINGS/yarqa\n"
                     "- Source authority: https://github.com/szl-holdings/yarqa\n\n## Next\n")
        expected, plan = self.expected_plan()
        self.assertFalse(plan["body_replace_allowed"])
        self.assertEqual(plan["assets"][0]["changes"], [COMPLETED])
        desired = plan["assets"][0]["new_text"]
        code, receipt, requests = self.run_main(["--apply", "--expected-plan", str(expected)],
            [self.identity(), (json.dumps({"sha": HEAD}), 200), (self.card, 200),
             (json.dumps({"commitOid": COMMIT}), 200), (desired, 200), (json.dumps({"sha": COMMIT}), 200)], TOKEN)
        self.assertEqual(code, 0)
        self.assertTrue(receipt["assets"][0]["main_verified"])
        posts = [call for call in requests.call_args_list if call.args[0] == "POST"]
        self.assertEqual(len(posts), 1)
        records = [json.loads(line) for line in posts[0].args[3].decode("utf-8").splitlines()]
        self.assertEqual(records[0]["value"]["parentCommit"], HEAD)
        self.assertEqual(base64.b64decode(records[1]["value"]["content"]).decode("utf-8"), desired)

    # --- Trusted Publisher (OIDC) apply credentials -------------------------------------------

    def two_spaces(self):
        self.cfg["assets"] = [self.governed("yarqa"), self.governed("szl-constellation")]
        self.write_config()
        card = "---\ntitle: Card\nlicense: apache-2.0\n---\n\n# Card\n"
        return {"SZLHOLDINGS/yarqa": card, "SZLHOLDINGS/szl-constellation": card}

    def oidc_plan(self):
        cards = self.two_spaces()
        hub = FakeHub(cards)
        code, receipt, _ = self.run_main([], hub, env_extra=OIDC_ENV)
        self.assertEqual(code, 0, receipt.get("error"))
        self.assertTrue(all(used is None for _, _, used in hub.calls), "plans must read anonymously")
        self.assertNotIn("auth", receipt)
        self.assertNotIn("identity", receipt)
        path = self.root / "oidc-plan.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return cards, path

    def assert_no_credentials(self, receipt, *extra):
        text = json.dumps(receipt)
        for secret in (TOKEN, *OIDC.values(), *extra):
            self.assertNotIn(secret, text)

    def test_oidc_resource_and_variable_follow_the_declared_kind(self):
        for kind, resource in (("spaces", "spaces/SZLHOLDINGS/szl-constellation"),
                               ("datasets", "datasets/SZLHOLDINGS/szl-constellation"),
                               ("models", "SZLHOLDINGS/szl-constellation")):
            with self.subTest(kind=kind):
                asset = {"repo_id": "SZLHOLDINGS/szl-constellation", "kind": kind}
                self.assertEqual(RECONCILE.oidc_resource(asset), resource)
                [target] = RECONCILE.oidc_targets([asset])
                self.assertEqual(target["resource"], resource)
                self.assertEqual(target["env"], "HF_OIDC_TOKEN_" + re.sub(r"[/-]", "_", resource.upper()))
        colliding = [{"repo_id": "SZLHOLDINGS/szl-constellation", "kind": "spaces"},
                     {"repo_id": "SZLHOLDINGS/szl.constellation", "kind": "spaces"}]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            RECONCILE.oidc_targets(colliding)

    def test_list_oidc_targets_is_network_free_and_writes_no_receipt(self):
        self.two_spaces()
        output = self.root / "receipt.json"
        for only, expected in (("", [YARQA_ENV + "\tspaces/SZLHOLDINGS/yarqa\tSZLHOLDINGS/yarqa",
                                     CONSTELLATION_ENV + "\tspaces/SZLHOLDINGS/szl-constellation\tSZLHOLDINGS/szl-constellation"]),
                               ("SZLHOLDINGS/szl-constellation",
                                [CONSTELLATION_ENV + "\tspaces/SZLHOLDINGS/szl-constellation\tSZLHOLDINGS/szl-constellation"])):
            with self.subTest(only=only):
                args = ["hf_card_reconcile.py", "--config", str(self.config), "--bodies-dir", str(self.root),
                        "--out-json", str(output), "--list-oidc-targets", "--only", only]
                stdout = io.StringIO()
                with patch.object(RECONCILE.sys, "argv", args), patch.dict(RECONCILE.os.environ, {}, clear=True), \
                     patch.object(RECONCILE, "hub_request") as requests, redirect_stdout(stdout):
                    code = RECONCILE.main()
                self.assertEqual(code, 0)
                self.assertEqual(stdout.getvalue().splitlines(), expected)
                requests.assert_not_called()
                self.assertFalse(output.exists())

    def test_oidc_apply_binds_each_target_to_its_own_token_and_never_records_it(self):
        cards, expected = self.oidc_plan()
        hub = FakeHub(cards)
        code, receipt, _ = self.run_main(["--apply", "--auth", "oidc", "--expected-plan", str(expected)],
                                         hub, TOKEN, env_extra=OIDC_ENV)
        self.assertEqual(code, 0, receipt.get("error"))
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["auth"], {"mode": "oidc", "token_recorded": False, "targets": [
            {"repo_id": "SZLHOLDINGS/yarqa", "resource": "spaces/SZLHOLDINGS/yarqa"},
            {"repo_id": "SZLHOLDINGS/szl-constellation", "resource": "spaces/SZLHOLDINGS/szl-constellation"}]})
        identity = receipt["identity"]
        self.assertEqual((identity["mode"], identity["label"]), ("oidc", "MEASURED"))
        self.assertEqual([(t["resource"], t["check"], t["http_status"], t["whoami"]["label"]) for t in identity["targets"]],
                         [("spaces/SZLHOLDINGS/yarqa", "auth-check/write", 200, "REPORTED"),
                          ("spaces/SZLHOLDINGS/szl-constellation", "auth-check/write", 200, "REPORTED")])
        self.assertEqual([path for _, path, _ in hub.calls[:4]], [
            "/api/spaces/SZLHOLDINGS/yarqa/auth-check/write", "/api/whoami-v2",
            "/api/spaces/SZLHOLDINGS/szl-constellation/auth-check/write", "/api/whoami-v2"])
        for index, (method, path, used) in enumerate(hub.calls):
            with self.subTest(call=(method, path)):
                repo = FakeHub.repo_in(path) or FakeHub.repo_in(hub.calls[index - 1][1])
                self.assertEqual(used, OIDC[repo])
        self.assertEqual(sorted(path for method, path, _ in hub.calls if method == "POST"),
                         ["/api/spaces/SZLHOLDINGS/szl-constellation/commit/main", "/api/spaces/SZLHOLDINGS/yarqa/commit/main"])
        self.assertTrue(all(row["main_verified"] for row in receipt["assets"]))
        self.assert_no_credentials(receipt)

    def test_oidc_missing_or_malformed_target_token_fails_closed_before_network(self):
        _, expected = self.oidc_plan()
        yarqa = {YARQA_ENV: OIDC["SZLHOLDINGS/yarqa"]}
        for env, reason in (
                (yarqa, "missing: SZLHOLDINGS/szl-constellation (spaces/SZLHOLDINGS/szl-constellation via "
                        + CONSTELLATION_ENV + ")"),
                ({}, "missing: SZLHOLDINGS/yarqa (spaces/SZLHOLDINGS/yarqa via " + YARQA_ENV + "), SZLHOLDINGS/szl-constellation"),
                ({**yarqa, CONSTELLATION_ENV: "hf_jwt_one.a.b\nhf_jwt_two.c.d"}, "not a single Hub token: SZLHOLDINGS/szl-constellation"),
                ({**yarqa, CONSTELLATION_ENV: "not-a-hub-token"}, "not a single Hub token: SZLHOLDINGS/szl-constellation")):
            with self.subTest(reason=reason):
                code, receipt, requests = self.run_main(["--apply", "--auth", "oidc", "--expected-plan", str(expected)],
                                                        token=TOKEN, env_extra=env)
                self.assertEqual(code, 1)
                self.assertFalse(receipt["success"])
                self.assertIn(reason, receipt["error"])
                requests.assert_not_called()
                self.assertNotIn("identity", receipt)
                self.assertEqual(receipt["assets"], [])
                self.assertEqual(receipt["auth"]["mode"], "oidc")
                self.assertEqual([t["resource"] for t in receipt["auth"]["targets"]],
                                 ["spaces/SZLHOLDINGS/yarqa", "spaces/SZLHOLDINGS/szl-constellation"])
                self.assert_no_credentials(receipt, *env.values())

    def test_oidc_failed_write_check_blocks_every_target_before_reads_or_writes(self):
        cards, expected = self.oidc_plan()
        hub = FakeHub(cards, auth_status={"SZLHOLDINGS/szl-constellation": 403})
        code, receipt, _ = self.run_main(["--apply", "--auth", "oidc", "--expected-plan", str(expected)],
                                         hub, env_extra=OIDC_ENV)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["identity"]["label"], "UNAVAILABLE")
        self.assertEqual([(t["repo_id"], t["label"], t["http_status"]) for t in receipt["identity"]["targets"]],
                         [("SZLHOLDINGS/yarqa", "MEASURED", 200), ("SZLHOLDINGS/szl-constellation", "UNAVAILABLE", 403)])
        self.assertEqual(receipt["error"], "Trusted Publisher write check failed: SZLHOLDINGS/szl-constellation HTTP 403")
        self.assertEqual(receipt["assets"], [])
        self.assertEqual([(method, path) for method, path, _ in hub.calls], [
            ("GET", "/api/spaces/SZLHOLDINGS/yarqa/auth-check/write"), ("GET", "/api/whoami-v2"),
            ("GET", "/api/spaces/SZLHOLDINGS/szl-constellation/auth-check/write")])
        self.assertEqual([t["whoami"]["label"] for t in receipt["identity"]["targets"]], ["REPORTED", "UNAVAILABLE"])
        self.assert_no_credentials(receipt)

    def test_oidc_preflight_gates_on_write_check_not_owner_or_role(self):
        target = RECONCILE.oidc_targets([self.governed()])
        tokens = {"SZLHOLDINGS/yarqa": OIDC["SZLHOLDINGS/yarqa"]}
        for whoami in ((json.dumps({"type": "user", "name": "[OIDC]"}), 200), ("unauthorized", 401), ("[]", 200)):
            with self.subTest(whoami=whoami), patch.object(RECONCILE, "hub_request", side_effect=[("", 200), whoami]) as requests:
                result = RECONCILE.oidc_preflight(target, tokens)
                self.assertEqual(result["label"], "MEASURED")
                self.assertEqual(result["targets"][0]["whoami"]["label"], "REPORTED")
                self.assertEqual(result["targets"][0]["whoami"]["http_status"], whoami[1])
                self.assertEqual(requests.call_args_list[0].args[:3],
                                 ("GET", "/api/spaces/SZLHOLDINGS/yarqa/auth-check/write", OIDC["SZLHOLDINGS/yarqa"]))
        with patch.object(RECONCILE, "hub_request", side_effect=[("denied", 401), self.identity()]) as requests:
            result = RECONCILE.oidc_preflight(target, tokens)
        self.assertEqual(result["label"], "UNAVAILABLE")
        self.assertEqual(result["targets"][0]["whoami"],
                         {"label": "UNAVAILABLE", "detail": "not requested: write auth check failed"})
        self.assertEqual(requests.call_count, 1)

    def test_auth_oidc_is_apply_only(self):
        code, receipt, requests = self.run_main(["--auth", "oidc"], env_extra=OIDC_ENV)
        self.assertEqual(code, 1)
        self.assertIn("--auth oidc is only valid with --apply", receipt["error"])
        self.assertNotIn("auth", receipt)
        requests.assert_not_called()

    def test_token_mode_keeps_precedence_without_fallthrough_and_records_only_the_source_name(self):
        expected, _ = self.expected_plan()
        env = {"HF_ORG_TOKEN": "first-invalid-credential", "HF_TOKEN": "second-credential", **OIDC_ENV}
        for extra in ([], ["--auth", "token"]):
            with self.subTest(extra=extra):
                code, receipt, requests = self.run_main(["--apply", *extra, "--expected-plan", str(expected)],
                                                        [("unauthorized", 401)], env_extra=env)
                self.assertEqual(code, 1)
                self.assertEqual(requests.call_count, 1)
                self.assertEqual(requests.call_args.args[1:3], ("/api/whoami-v2", "first-invalid-credential"))
                self.assertEqual(receipt["auth"], {"mode": "token", "source": "HF_ORG_TOKEN", "token_recorded": False})
                self.assert_no_credentials(receipt, *env.values())

    def test_token_mode_success_uses_one_secret_for_every_target(self):
        cards, expected = self.oidc_plan()
        hub = FakeHub(cards, whoami=self.identity())
        code, receipt, _ = self.run_main(["--apply", "--auth", "token", "--expected-plan", str(expected)],
                                         hub, TOKEN, env_extra=OIDC_ENV)
        self.assertEqual(code, 0, receipt.get("error"))
        self.assertEqual(receipt["auth"], {"mode": "token", "source": "HF_CARD_WRITE_TOKEN", "token_recorded": False})
        self.assertEqual(receipt["identity"]["name"], "betterwithage")
        self.assertEqual({used for _, _, used in hub.calls}, {TOKEN})
        self.assertEqual(sum(method == "POST" for method, _, _ in hub.calls), 2)
        self.assert_no_credentials(receipt)

    def test_error_text_never_retains_any_present_credential(self):
        failure = ValueError(f"boom {OIDC['SZLHOLDINGS/yarqa']} {TOKEN}")
        for extra in (["--auth", "oidc"], ["--auth", "token"]):
            with self.subTest(extra=extra), patch.object(RECONCILE, "load_config", side_effect=failure):
                code, receipt, _ = self.run_main(["--apply", *extra, "--expected-plan", "unused.json"],
                                                 token=TOKEN, env_extra=OIDC_ENV)
                self.assertEqual(code, 1)
                self.assertEqual(receipt["error"], "boom [REDACTED] [REDACTED]")

    # --- Workflow contract (text-level; the suite stays standard-library only) ------------------

    @staticmethod
    def workflow_jobs(text):
        parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", text.split("\njobs:\n", 1)[1])
        return dict(zip(parts[1::2], parts[2::2]))

    @staticmethod
    def run_blocks(text):
        lines, blocks = text.splitlines(), []
        for i, line in enumerate(lines):
            match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
            if not match:
                continue
            indent, rest = len(match.group(1)), match.group(2)
            if rest and rest[0] not in "|>":
                blocks.append(rest)
                continue
            body = []
            for following in lines[i + 1:]:
                if following.strip() and len(following) - len(following.lstrip()) <= indent:
                    break
                body.append(following)
            blocks.append("\n".join(body))
        return blocks

    def test_workflow_grants_oidc_only_to_apply_and_keeps_secrets_out_of_plans(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        jobs = self.workflow_jobs(text)
        self.assertEqual(list(jobs), ["contract", "reconcile", "apply"])
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertEqual(code.count("id-token"), 1)
        self.assertIn("    permissions:\n      contents: read\n      actions: read\n      id-token: write\n", jobs["apply"])
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.apply == true", jobs["apply"])
        self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.apply != true", jobs["reconcile"])
        for name in ("contract", "reconcile"):
            self.assertNotIn("id-token", jobs[name])
            self.assertNotIn("secrets.", jobs[name])
        for name in ("reconcile", "apply"):
            self.assertIn("    needs: contract\n", jobs[name])
        self.assertRegex(text, r"\n      auth:\n        description: [^\n]+\n        type: choice\n"
                               r"        options:\n          - oidc\n          - token\n        default: oidc\n")
        secret_lines = [line.strip() for line in text.splitlines() if "secrets." in line]
        self.assertEqual(len(secret_lines), len(RECONCILE.TOKEN_KEYS))
        for line in secret_lines:
            self.assertRegex(line, r"^[A-Z0-9_]+: \$\{\{ inputs\.auth == 'token' && secrets\.[A-Z0-9_]+ \|\| '' \}\}$")
        uses = re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*(\S+)", text)
        self.assertTrue(uses)
        pins = {}
        for ref in uses:
            self.assertRegex(ref, r"^[^@\s]+@[0-9a-f]{40}$")
            action, sha = ref.split("@")
            pins.setdefault(action, set()).add(sha)
        # Every job runs the same revision of each action, so a merge cannot leave mixed pins.
        self.assertEqual({action: shas for action, shas in pins.items() if len(shas) > 1}, {})
        blocks = self.run_blocks(text)
        self.assertGreaterEqual(len(blocks), 10)
        for block in blocks:
            self.assertNotIn("${{", block)
        apply_step = next(block for block in blocks if "--list-oidc-targets" in block)
        for required in ('HF_OIDC_RESOURCE="$resource"', 'auth token 2>"$err" </dev/null',
                         '[[ "$value" =~ ^hf_[A-Za-z0-9._-]+$ ]]', 'echo "::add-mask::$value"',
                         'printf -v "$name"', 's/hf_[A-Za-z0-9._-]+/[REDACTED]/g',
                         "env -u HF_TOKEN -u HUGGING_FACE_HUB_TOKEN -u HF_OIDC_ID_TOKEN",
                         "-u HF_ENDPOINT -u HUGGINGFACE_CO_STAGING -u HF_DEBUG",
                         "HF_HUB_DISABLE_UPDATE_CHECK=1", '"${only_args[@]}" || rc=$?'):
            self.assertIn(required, apply_step)
        for forbidden in ("GITHUB_ENV", "GITHUB_OUTPUT\" <<", "tee "):
            self.assertNotIn(forbidden, apply_step)
        self.assertNotRegex(apply_step, r"(?m)^\s*rc=\$\?\s*$")

    def run_apply_step(self, shell, scenario, only, reconcile_rc=0):
        """Run the real apply step with a fake hf CLI and a stub reconciler; no network."""
        block = next(b for b in self.run_blocks(WORKFLOW.read_text(encoding="utf-8")) if "--list-oidc-targets" in b)
        work = Path(tempfile.mkdtemp(dir=self.root))
        runner_temp, stubs = work / "runner", work / "bin"
        (runner_temp / "hf-cli-venv" / "bin").mkdir(parents=True)
        stubs.mkdir()
        for path, text in ((work / "step.sh", textwrap.dedent(block) + "\n"),
                           (runner_temp / "hf-cli-venv" / "bin" / "hf", FAKE_HF),
                           (stubs / "python", STUB_PYTHON)):
            path.write_bytes(text.encode("utf-8"))
            path.chmod(0o755)
        output = work / "github_output"
        output.write_bytes(b"")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("HF_", "HUGGING"))}
        env.update(PATH=str(stubs) + os.pathsep + env.get("PATH", ""), RUNNER_TEMP=runner_temp.as_posix(),
                   GITHUB_OUTPUT=output.as_posix(), REPORT=(work / "report.json").as_posix(), ONLY=only,
                   ALLOW_BODY="", AUTH_MODE="oidc", REAL_PYTHON=sys.executable, STUB_LOG=(work / "log").as_posix(),
                   SCENARIO=scenario, RECONCILE_RC=str(reconcile_rc),
                   # Present in the step environment; none of them may reach the exchange.
                   HF_TOKEN="", HF_CARD_WRITE_TOKEN="", HF_OIDC_ID_TOKEN="eyJinherited.subject.token",
                   HF_ENDPOINT="https://hub.invalid", HUGGINGFACE_CO_STAGING="1", HF_DEBUG="1")
        proc = subprocess.run([*shell, (work / "step.sh").as_posix()], cwd=REPO_ROOT, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120)

        def read(name):
            path = work / name
            return path.read_bytes().decode("utf-8") if path.exists() else ""
        leftovers = sorted(p.name for p in runner_temp.iterdir() if p.name != "hf-cli-venv")
        return proc, read("github_output"), read("log.hf"), read("log.reconcile"), leftovers

    def test_apply_step_records_exit_code_and_scopes_each_exchange_under_the_runner_shell(self):
        if not BASH:
            self.skipTest("needs POSIX bash; runs in the contract job on ubuntu-latest")
        both = "SZLHOLDINGS/yarqa,SZLHOLDINGS/szl-constellation"
        yarqa, constellation = FAKE_TOKENS["yarqa"], FAKE_TOKENS["szl-constellation"]
        cases = (
            # scenario, only, reconciler rc, exit_code, tokens the reconciler receives, exchanges
            ("ok", both, 0, "0", {YARQA_ENV: yarqa, CONSTELLATION_ENV: constellation}, 2),
            ("ok", both, 1, "1", {YARQA_ENV: yarqa, CONSTELLATION_ENV: constellation}, 2),
            ("fail_constellation", both, 0, "1", {YARQA_ENV: yarqa, CONSTELLATION_ENV: "<unset>"}, 2),
            ("fail_constellation", both, 1, "1", {YARQA_ENV: yarqa, CONSTELLATION_ENV: "<unset>"}, 2),
            ("two_lines_yarqa", both, 1, "1", {YARQA_ENV: "<unset>", CONSTELLATION_ENV: constellation}, 2),
            ("ok", "SZLHOLDINGS/yarqa", 0, "0", {YARQA_ENV: yarqa, CONSTELLATION_ENV: "<unset>"}, 1),
        )
        # `bash -e {0}` is the runner default when a step sets no shell; the second is `shell: bash`.
        for shell in ((BASH, "-e"), (BASH, "--noprofile", "--norc", "-eo", "pipefail")):
            for scenario, only, reconcile_rc, exit_code, received, exchanges in cases:
                with self.subTest(shell=shell[1:], scenario=scenario, only=only, reconcile_rc=reconcile_rc):
                    proc, output, hf_log, reconcile_log, leftovers = self.run_apply_step(
                        shell, scenario, only, reconcile_rc)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(output, f"exit_code={exit_code}\n")
                    self.assertEqual(leftovers, [])
                    calls = hf_log.splitlines()
                    self.assertEqual(len(calls), exchanges, hf_log)
                    for call in calls:
                        self.assertRegex(call, r"^resource=spaces/SZLHOLDINGS/[a-z-]+ update_check=1 "
                                               r"args=auth token leaked=$")
                    self.assertEqual(dict(line.split("=", 1) for line in reconcile_log.splitlines()
                                          if line.startswith("HF_OIDC_TOKEN_")), received)
                    self.assertIn("--apply --auth oidc", reconcile_log)
                    masked = [line for line in proc.stdout.splitlines() if line.startswith("::add-mask::")]
                    self.assertEqual(masked, ["::add-mask::" + v for v in received.values() if v != "<unset>"])
                    logs = "\n".join(line for line in (proc.stdout + proc.stderr).splitlines()
                                     if not line.startswith("::add-mask::"))
                    for secret in (*FAKE_TOKENS.values(), "hf_jwt_leaked", "eyJ", "Set HF_DEBUG"):
                        self.assertNotIn(secret, logs)
                    if scenario == "fail_constellation":
                        self.assertIn("::error::UNAVAILABLE - trusted-publisher exchange failed for "
                                      "SZLHOLDINGS/szl-constellation (spaces/SZLHOLDINGS/szl-constellation)",
                                      proc.stdout)
                        self.assertEqual(proc.stderr.count("[REDACTED]"), 2)


FAKE_TOKENS = {"yarqa": "hf_jwt_fakeyarqa.claims.signature",
               "szl-constellation": "hf_jwt_fakeconstellation.claims.signature"}
# Stands in for `hf auth token`: records what the exchange would see and never calls the Hub.
FAKE_HF = r"""#!/usr/bin/env bash
set -u
leaked=""
for v in HF_TOKEN HUGGING_FACE_HUB_TOKEN HF_OIDC_ID_TOKEN HF_ENDPOINT HUGGINGFACE_CO_STAGING HF_DEBUG; do
  if [ "${!v+set}" = set ]; then leaked="$leaked$v,"; fi
done
name="${HF_OIDC_RESOURCE##*/}"
echo "resource=$HF_OIDC_RESOURCE update_check=${HF_HUB_DISABLE_UPDATE_CHECK-} args=$* leaked=$leaked" >> "$STUB_LOG.hf"
if [ "$SCENARIO" = fail_constellation ] && [ "$name" = szl-constellation ]; then
  echo "Error: invalid_grant for hf_jwt_leaked.a.b (subject eyJleaked.c.d)" >&2
  echo "Set HF_DEBUG=1 as environment variable for full traceback."
  exit 1
fi
if [ "$SCENARIO" = two_lines_yarqa ] && [ "$name" = yarqa ]; then
  printf 'hf_jwt_fakeyarqa.claims.signature\nhf_jwt_fakeyarqa.claims.signature\n'
  exit 0
fi
case "$name" in
  yarqa) echo "hf_jwt_fakeyarqa.claims.signature" ;;
  szl-constellation) echo "hf_jwt_fakeconstellation.claims.signature" ;;
  *) exit 1 ;;
esac
echo "hint: the token was printed to stdout" >&2
"""
# Stands in for `python`: target listing runs the real reconciler; the apply call only records its inputs.
STUB_PYTHON = r"""#!/usr/bin/env bash
case " $* " in
  *" --list-oidc-targets "*) exec "$REAL_PYTHON" "$@" ;;
esac
{
  for name in HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_YARQA HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_SZL_CONSTELLATION; do
    printf '%s=%s\n' "$name" "${!name-<unset>}"
  done
  printf 'argv=%s\n' "$*"
} > "$STUB_LOG.reconcile"
exit "$RECONCILE_RC"
"""
YARQA_ENV = "HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_YARQA"
CONSTELLATION_ENV = "HF_OIDC_TOKEN_SPACES_SZLHOLDINGS_SZL_CONSTELLATION"
OIDC = {"SZLHOLDINGS/yarqa": "hf_jwt_eyJyarqa.claims.signature",
        "SZLHOLDINGS/szl-constellation": "hf_jwt_eyJconstellation.claims.signature"}
OIDC_ENV = {YARQA_ENV: OIDC["SZLHOLDINGS/yarqa"], CONSTELLATION_ENV: OIDC["SZLHOLDINGS/szl-constellation"]}


class FakeHub:
    """Stateful Hub double: per-repo heads, parent-checked commits, and write auth checks."""
    API = re.compile(r"/api/(?:spaces|models|datasets)/(SZLHOLDINGS/[^/?]+)(/auth-check/write|/commit/main(?:\?create_pr=1)?)?")
    RAW = re.compile(r"/(?:spaces/|datasets/)?(SZLHOLDINGS/[^/]+)/raw/([0-9a-f]{40})/README\.md")

    def __init__(self, cards, auth_status=None, whoami=(json.dumps({"type": "user", "name": "[OIDC]"}), 200)):
        self.revisions = {repo: {HEAD: text} for repo, text in cards.items()}
        self.heads = {repo: HEAD for repo in cards}
        self.auth_status = auth_status or {}
        self.whoami = whoami
        self.calls = []

    @staticmethod
    def repo_in(path):
        match = re.search(r"SZLHOLDINGS/[A-Za-z0-9_.-]+", path)
        return match.group(0) if match else None

    def __call__(self, method, path, token, body=None, content_type=None):
        self.calls.append((method, path, token))
        if path == "/api/whoami-v2":
            return self.whoami
        raw = self.RAW.fullmatch(path)
        if raw:
            text = self.revisions[raw.group(1)].get(raw.group(2))
            return (text, 200) if text is not None else ("missing", 404)
        api = self.API.fullmatch(path)
        if not api:
            raise AssertionError(f"unexpected Hub path {path}")
        repo, suffix = api.group(1), api.group(2) or ""
        if suffix == "/auth-check/write":
            return "", self.auth_status.get(repo, 200)
        if suffix.startswith("/commit/main"):
            records = [json.loads(line) for line in body.decode("utf-8").splitlines()]
            if records[0]["value"]["parentCommit"] != self.heads[repo]:
                return "parent moved", 409
            commit = hashlib.sha1(repo.encode("utf-8")).hexdigest()
            self.revisions[repo][commit] = base64.b64decode(records[1]["value"]["content"]).decode("utf-8")
            self.heads[repo] = commit
            return json.dumps({"commitOid": commit}), 200
        return json.dumps({"sha": self.heads[repo]}), 200


if __name__ == "__main__":
    unittest.main()
