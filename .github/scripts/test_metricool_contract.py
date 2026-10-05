#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic, offline regression tests; never contacts or changes a provider."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("metricool_contract.py")
SPEC = importlib.util.spec_from_file_location("metricool_contract", MODULE_PATH)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)

NOW = "2026-10-05T12:00:00Z"
RECENT = "2026-10-05T11:59:00Z"
FUTURE = "2026-10-05T12:05:00Z"
SOURCE = "a" * 40
OTHER_SOURCE = "b" * 40
ARTIFACT = "c" * 64
OTHER_ARTIFACT = "d" * 64
ENVIRON = {"METRICOOL_BRAND_ID": "synthetic-brand-a", "METRICOOL_TIMEZONE": "America/New_York"}


def example_claim(category="release"):
    kinds = {
        "thesis": [], "architecture": ["source"],
        "release": ["source", "artifact", "runtime"],
        "security": ["source", "artifact", "runtime", "security"],
        "model": ["source", "artifact", "evaluation"],
        "research": ["source", "evaluation"],
    }[category]
    evidence = []
    for kind in kinds:
        entry = {
            "kind": kind, "sourceRevision": SOURCE, "result": "PASS",
            "observedAt": RECENT,
            "ref": f"https://github.com/szl-holdings/sample/blob/{SOURCE}/fixture-{kind}.json",
        }
        if kind != "source":
            entry["artifactSha256"] = ARTIFACT
        evidence.append(entry)
    return {
        "text": "Synthetic contract fixture; not a product or scientific assertion.",
        "category": category,
        "classification": "DECLARED" if category == "thesis" else "REPORTED",
        "sourceRevision": SOURCE, "currentSourceRevision": SOURCE,
        "sourceObservedAt": RECENT, "evidence": evidence,
        "knownLimits": ["SAMPLE test records, not authenticated release evidence."],
    }


def example_request():
    claim = example_claim()
    return {
        "brand": {"id": "synthetic-brand-a", "timezone": "America/New_York",
                  "observedAt": RECENT, "connectedNetworks": ["twitter", "linkedin"]},
        "provider": "twitter", "operation": "review-draft", "claim": claim,
        "scheduledAt": FUTURE, "payload": {"text": claim["text"], "media": []},
        "planner": {"complete": True, "intentKeys": [], "observedAt": RECENT},
    }


def example_receipt(state="DRAFT"):
    published = state == "PUBLISHED"
    return {
        "receiptVersion": 1, "generatedAt": NOW,
        "sourceRepository": "https://github.com/szl-holdings/sample",
        "sourceRevision": SOURCE, "evidenceRefs": [f"https://github.com/szl-holdings/sample/commit/{SOURCE}"] if published else [],
        "claimClassification": "SAMPLE", "contentSha256": "e" * 64,
        "metricoolBrandRef": "synthetic-brand-a", "provider": "twitter",
        "scheduledAt": "2026-10-05T11:50:00Z",
        "metricoolPostUuid": "synthetic-planner-post" if state in {"SCHEDULED", "PUBLISHED"} else None,
        "providerPostId": "synthetic-provider-post" if published else None,
        "state": state, "publishedAt": RECENT if published else None,
        "observedAt": NOW,
        "verificationStatus": "PROVIDER_CONFIRMED" if published else "NOT_VERIFIED",
        "failureReason": None, "knownLimits": ["SAMPLE fixture; provider confirmation is not authenticated by schema validation."],
    }


class ConfigSchemaTests(unittest.TestCase):
    def setUp(self):
        self.config = contract.read_json(ROOT / "config/metricool-control-plane.json")

    def test_actual_schema_is_draft_2020_12_and_validates_config(self):
        schema = contract.read_json(ROOT / "config/schemas/metricool-control-plane.schema.json")
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(self.config)
        contract.validate_schema(self.config, "config")

    def test_config_is_closed_against_unknown_secret_fields(self):
        for path in ((), ("policy",), ("brandSelection",)):
            value = copy.deepcopy(self.config)
            target = value
            for name in path:
                target = target[name]
            target["unreviewedField"] = "synthetic-only"
            with self.subTest(path=path), self.assertRaises(ValidationError):
                contract.validate_schema(value, "config")

    def test_policy_cannot_enable_publication_updates_or_disable_authorization(self):
        for key, value in (("automaticPublicationEnabled", True),
                           ("conditionalUpdatesEnabled", True),
                           ("independentAuthorizationRequired", False),
                           ("maxEvidenceAgeSeconds", 301)):
            config = copy.deepcopy(self.config)
            config["policy"][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                contract.validate_schema(config, "config")

    def test_network_and_authority_scope_is_committed_not_provider_discovery(self):
        for field, value in (("authorizedNetworks", ["twitter", "linkedin", "instagram"]),
                             ("canonicalAuthority", ["metricool"]),
                             ("allowedCapabilities", ["publish-now"])):
            config = copy.deepcopy(self.config)
            config[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                contract.validate_schema(config, "config")

    def test_schemas_have_no_external_reference_dependencies(self):
        def visit(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#"))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        for relative in ("config/schemas/metricool-control-plane.schema.json",
                         "schemas/metricool-publication-receipt.schema.json"):
            visit(contract.read_json(ROOT / relative))


class InputParsingTests(unittest.TestCase):
    def test_malformed_duplicate_and_nonfinite_json_rejected(self):
        for text in ('{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}',
                     '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}', '{'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "fixture.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    contract.read_json(path)

    def test_oversized_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text('"' + "x" * 2_000_000 + '"', encoding="utf-8")
            with self.assertRaises(ValueError):
                contract.read_json(path)

    def test_size_limit_applies_to_consumed_bytes_not_stale_path_metadata(self):
        """A competing writer can grow or replace an input after a stat check."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text('"' + "x" * 2_000_000 + '"', encoding="utf-8")
            with patch.object(Path, "stat", return_value=SimpleNamespace(st_size=2)):
                with self.assertRaises(ValueError):
                    contract.read_json(path)

    def test_timezone_required(self):
        for value in (None, 123, "2026-10-05T12:00:00", "not-a-time"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.timestamp(value)


class ClaimTests(unittest.TestCase):
    def check_claim(self, claim):
        result = contract.validate_public_claim(claim, now=contract.timestamp(NOW))
        self.assertIs(result["allowed_to_publish"], False)
        return result

    def test_supported_categories_validate_only_supplied_record_consistency(self):
        for category in contract.CATEGORIES:
            with self.subTest(category=category):
                result = self.check_claim(example_claim(category))
                self.assertTrue(result["preflight_passed"], result)
                self.assertEqual(result["classification"], "DECLARED")

    def test_unknown_unqualified_and_simulated_technical_labels_block(self):
        for label in ("LIVE", "CERTIFIED", "UNKNOWN", "UNAVAILABLE", "BLOCKED", "SAMPLE", "SIMULATED", "ROADMAP"):
            claim = example_claim()
            claim["classification"] = label
            with self.subTest(label=label):
                self.assertFalse(self.check_claim(claim)["preflight_passed"])

    def test_manual_or_unsupported_claim_categories_block(self):
        for category in ("compliance", "funding", "customers", "revenue", "unregistered-category"):
            claim = example_claim()
            claim["category"] = category
            with self.subTest(category=category):
                self.assertIn("MANUAL_SUBSTANTIATION_REQUIRED", self.check_claim(claim)["reasons"])

    def test_source_must_be_exact_and_current(self):
        for source, current in ((SOURCE[:8], SOURCE), (SOURCE.upper(), SOURCE), (SOURCE, OTHER_SOURCE)):
            claim = example_claim()
            claim["sourceRevision"], claim["currentSourceRevision"] = source, current
            with self.subTest(source=source, current=current):
                self.assertIn("SOURCE_MOVED_OR_UNPINNED", self.check_claim(claim)["reasons"])

    def test_source_and_evidence_readbacks_reject_stale_and_future(self):
        for observed in ("2026-10-05T11:54:59Z", "2026-10-05T12:00:01Z"):
            for field in ("source", "evidence"):
                claim = example_claim()
                if field == "source":
                    claim["sourceObservedAt"] = observed
                else:
                    claim["evidence"][0]["observedAt"] = observed
                with self.subTest(observed=observed, field=field):
                    self.assertFalse(self.check_claim(claim)["preflight_passed"])

    def test_artifact_identity_must_match_across_source_evidence(self):
        for field, value in (("sourceRevision", OTHER_SOURCE), ("artifactSha256", OTHER_ARTIFACT),
                             ("artifactSha256", "unbound"), ("result", "FAIL")):
            claim = example_claim()
            claim["evidence"][-1][field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(self.check_claim(claim)["preflight_passed"])

    def test_evidence_missing_duplicate_unknown_or_excessive_blocks(self):
        for mutation in ("missing", "duplicate", "unknown", "excessive"):
            claim = example_claim()
            if mutation == "missing":
                claim["evidence"].pop()
            elif mutation == "duplicate":
                claim["evidence"].append(copy.deepcopy(claim["evidence"][0]))
            elif mutation == "unknown":
                claim["evidence"][0]["kind"] = "provider-brand-connected"
            else:
                claim["evidence"] = claim["evidence"] * 34
            with self.subTest(mutation=mutation):
                self.assertFalse(self.check_claim(claim)["preflight_passed"])

    def test_unsafe_or_unapproved_evidence_references_block(self):
        for ref in ("http://github.com/sample", "https://example.invalid/sample", "file:///fixture",
                    "https://github.com@evil.invalid/sample", "https://user:fake@github.com/sample",
                    "https://github.com/sample?secret=synthetic", "https://github.com/sample#unbound"):
            claim = example_claim()
            claim["evidence"][0]["ref"] = ref
            with self.subTest(ref=ref):
                self.assertIn("EVIDENCE_MISMATCH", self.check_claim(claim)["reasons"])

    def test_known_limits_required_and_malformed_claims_block(self):
        for limits in ([], None, [" "], "none"):
            claim = example_claim()
            claim["knownLimits"] = limits
            with self.subTest(limits=limits):
                self.assertFalse(self.check_claim(claim)["preflight_passed"])
        for claim in ({}, [], None):
            with self.subTest(claim=claim):
                self.assertIn("MALFORMED_CLAIM", self.check_claim(claim)["reasons"])


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.config = contract.read_json(ROOT / "config/metricool-control-plane.json")

    def check_request(self, request, environ=None):
        result = contract.preflight(self.config, request, ENVIRON if environ is None else environ, now=NOW)
        self.assertIs(result["allowed_to_publish"], False)
        self.assertEqual(result["provider_writes"], 0)
        return result

    def test_valid_review_draft_is_not_publication_authority(self):
        result = self.check_request(example_request())
        self.assertTrue(result["preflight_passed"], result)
        self.assertEqual(result["state"], "DECLARED")

    def test_no_provider_network_or_process_side_effects(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")), \
             patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process forbidden")):
            result = self.check_request(example_request())
        self.assertTrue(result["preflight_passed"], result)

    def test_missing_explicit_brand_timezone_never_falls_back(self):
        for environ in ({}, {"METRICOOL_BRAND_ID": "synthetic-brand-a"},
                        {"METRICOOL_BRAND_ID": "synthetic-brand-a", "METRICOOL_TIMEZONE": "UTC"}):
            with self.subTest(environ=environ):
                self.assertFalse(self.check_request(example_request(), environ)["preflight_passed"])

    def test_wrong_brand_timezone_or_unapproved_network_blocks(self):
        for mutation in ("brand", "zone", "new-network", "disconnected"):
            request = example_request()
            if mutation == "brand":
                request["brand"]["id"] = "synthetic-unused-brand"
            elif mutation == "zone":
                request["brand"]["timezone"] = "UTC"
            elif mutation == "new-network":
                request["provider"] = "instagram"
                request["brand"]["connectedNetworks"].append("instagram")
            else:
                request["brand"]["connectedNetworks"] = []
            with self.subTest(mutation=mutation):
                self.assertFalse(self.check_request(request)["preflight_passed"])

    def test_all_provider_mutations_block_even_with_claimed_capabilities(self):
        for operation in ("create-scheduled-post", "update-scheduled-post", "publish-now", "send-post-for-review", "delete", "schedule"):
            request = example_request()
            request["operation"] = operation
            request["capabilities"] = {"conditionalUpdate": True, "finalEvidenceHook": True}
            request["expectedRevision"] = "synthetic-revision"
            with self.subTest(operation=operation):
                self.assertIn("PROVIDER_MUTATION_NOT_IMPLEMENTED", self.check_request(request)["reasons"])

    def test_brand_and_planner_stale_or_future_readback_blocks(self):
        for field in ("brand", "planner"):
            for observed in ("2026-10-05T11:54:59Z", "2026-10-05T12:00:01Z"):
                request = example_request()
                request[field]["observedAt"] = observed
                with self.subTest(field=field, observed=observed):
                    self.assertFalse(self.check_request(request)["preflight_passed"])

    def test_planner_missing_coverage_is_not_empty_planner(self):
        for complete in (False, None, 1, "true"):
            request = example_request()
            request["planner"]["complete"] = complete
            with self.subTest(complete=complete):
                self.assertIn("PLANNER_INCOMPLETE_OR_STALE", self.check_request(request)["reasons"])

    def test_schedule_must_be_future_and_timezone_qualified(self):
        for scheduled in (NOW, "2026-10-05T11:59:00Z", "2026-10-05T12:05:00", "invalid"):
            request = example_request()
            request["scheduledAt"] = scheduled
            with self.subTest(scheduled=scheduled):
                self.assertFalse(self.check_request(request)["preflight_passed"])

    def test_payload_content_matches_evaluated_claim(self):
        request = example_request()
        request["payload"]["text"] = "Different synthetic text"
        self.assertIn("CONTENT_CLAIM_MISMATCH", self.check_request(request)["reasons"])

    def test_duplicate_intent_is_held_not_reported_as_scheduled(self):
        request = example_request()
        key = contract.idempotency_key(ENVIRON["METRICOOL_BRAND_ID"], request["provider"],
                                       request["payload"], request["scheduledAt"], SOURCE)
        request["planner"]["intentKeys"] = [key]
        result = self.check_request(request)
        self.assertIn("DUPLICATE_INTENT", result["reasons"])
        self.assertEqual(result["state"], "BLOCKED")

    def test_malformed_request_denies_without_echoing_input(self):
        for request in ({}, [], None, {"private": "synthetic-sensitive-marker"}):
            with self.subTest(request=request):
                result = self.check_request(request)
                self.assertIn("MALFORMED_REQUEST", result["reasons"])
                self.assertNotIn("synthetic-sensitive-marker", json.dumps(result))


class IdempotencyTests(unittest.TestCase):
    def test_bind_account_network_media_time_source_and_content(self):
        payload = {"text": "Synthetic fixture", "media": [], "disclosure": "SAMPLE"}
        baseline = contract.idempotency_key("synthetic-brand-a", "twitter", payload, FUTURE, SOURCE)
        variants = [
            ("synthetic-brand-b", "twitter", payload, FUTURE, SOURCE),
            ("synthetic-brand-a", "linkedin", payload, FUTURE, SOURCE),
            ("synthetic-brand-a", "twitter", {**payload, "media": ["synthetic-media-id"]}, FUTURE, SOURCE),
            ("synthetic-brand-a", "twitter", payload, "2026-10-05T12:05:01Z", SOURCE),
            ("synthetic-brand-a", "twitter", payload, FUTURE, OTHER_SOURCE),
            ("synthetic-brand-a", "twitter", {**payload, "text": "Changed fixture"}, FUTURE, SOURCE),
            ("synthetic-brand-a", "twitter", {**payload, "disclosure": "Changed limit"}, FUTURE, SOURCE),
        ]
        hashes = {contract.idempotency_key(*variant) for variant in variants}
        self.assertNotIn(baseline, hashes)
        self.assertEqual(len(hashes), len(variants))

    def test_equivalent_utc_instant_and_object_order_normalize(self):
        first = contract.idempotency_key("synthetic-brand-a", "twitter", {"text": "a\r\nb", "media": []}, FUTURE, SOURCE)
        second = contract.idempotency_key("synthetic-brand-a", "twitter", {"media": [], "text": "a\nb"}, "2026-10-05T08:05:00-04:00", SOURCE)
        self.assertEqual(first, second)

    def test_nonfinite_payload_and_unpinned_revision_reject(self):
        with self.assertRaises(ValueError):
            contract.idempotency_key("synthetic-brand-a", "twitter", {"text": "sample", "value": float("nan")}, FUTURE, SOURCE)
        with self.assertRaises(ValueError):
            contract.idempotency_key("synthetic-brand-a", "twitter", {"text": "sample"}, FUTURE, "main")


class ReceiptSchemaTests(unittest.TestCase):
    def test_actual_schema_uses_draft_2020_12_and_validates_fixtures(self):
        schema = contract.read_json(ROOT / "schemas/metricool-publication-receipt.schema.json")
        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        for state in ("DRAFT", "SCHEDULED", "PUBLISHED", "BLOCKED", "UNKNOWN", "UNAVAILABLE"):
            with self.subTest(state=state):
                contract.validate_schema(example_receipt(state), "receipt")

    def test_published_requires_provider_id_evidence_time_and_confirmation(self):
        for field, value in (("providerPostId", None), ("providerPostId", " "),
                             ("evidenceRefs", []), ("publishedAt", None),
                             ("publishedAt", "not-a-time"), ("verificationStatus", "NOT_VERIFIED")):
            receipt = example_receipt("PUBLISHED")
            receipt[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                contract.validate_schema(receipt, "receipt")

    def test_scheduled_does_not_count_as_provider_confirmed_publication(self):
        for field, value in (("publishedAt", RECENT), ("verificationStatus", "PROVIDER_CONFIRMED")):
            receipt = example_receipt("SCHEDULED")
            receipt[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                contract.validate_schema(receipt, "receipt")

    def test_unknown_properties_labels_networks_and_bad_formats_reject(self):
        for field, value in (("credential", "synthetic-only"), ("claimClassification", "LIVE"),
                             ("provider", "instagram"), ("sourceRevision", "main"),
                             ("contentSha256", "short"), ("generatedAt", "2026-10-05")):
            receipt = example_receipt()
            receipt[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                contract.validate_schema(receipt, "receipt")


class CommandLineTests(unittest.TestCase):
    def test_malformed_urls_fail_full_claim_and_preflight(self):
        for url in ("https://github.com:99999/path", "https://github.com:8443/path",
                    "https://git\nhub.com/path", "https://github.com/a\\b",
                    "https://github.com/a b"):
            request = example_request()
            for item in request["claim"]["evidence"]:
                item["ref"] = url
            with self.subTest(url=url):
                self.assertFalse(contract.validate_public_claim(request["claim"],
                    now=contract.timestamp(NOW))["preflight_passed"])
                result = contract.preflight(contract.read_json(ROOT / "config/metricool-control-plane.json"),
                                            request, ENVIRON, now=NOW)
                self.assertFalse(result["preflight_passed"])
                self.assertFalse(result["allowed_to_publish"])

    def test_impossible_dates_and_offsets_fail_without_optional_format_extras(self):
        for date in ("2026-10-05T12:00:00+00:99", "2026-10-05T12:00:00+24:00",
                     "2026-02-30T12:00:00Z", "2026-10-05 12:00:00Z"):
            with self.subTest(date=date), self.assertRaises(ValueError):
                contract.timestamp(date)
            receipt = example_receipt()
            receipt["generatedAt"] = date
            with self.subTest(receipt=date), self.assertRaises(ValidationError):
                contract.validate_schema(receipt, "receipt")
            request = example_request()
            request["brand"]["observedAt"] = date
            self.assertFalse(contract.preflight(
                contract.read_json(ROOT / "config/metricool-control-plane.json"), request,
                ENVIRON, now=NOW)["preflight_passed"])

    def test_real_cli_config_smoke_has_no_publication_effect(self):
        result = subprocess.run([sys.executable, "-B", str(MODULE_PATH)],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertIs(output["config_valid"], True)
        self.assertIs(output["allowed_to_publish"], False)
        self.assertEqual(output["provider_writes"], 0)
        self.assertEqual(result.stderr, "")

    def test_real_cli_malformed_input_is_blocked_without_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text('{"synthetic-private-marker":', encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(MODULE_PATH), "--request", str(path)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("synthetic-private-marker", result.stdout + result.stderr)
        self.assertNotIn(directory, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["state"], "BLOCKED")
        self.assertIs(output["allowed_to_publish"], False)
        self.assertEqual(output["provider_writes"], 0)

    def test_missing_dependency_error_is_redacted_and_fails_closed(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(MODULE_PATH)]), \
             patch.object(contract, "validate_schema", side_effect=ImportError("synthetic-private-marker")), \
             redirect_stdout(output):
            code = contract.main()
        self.assertEqual(code, 2)
        self.assertNotIn("synthetic-private-marker", output.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual(result["reason"], "INVALID_CONTRACT_OR_DEPENDENCY")
        self.assertIs(result["allowed_to_publish"], False)
        self.assertEqual(result["provider_writes"], 0)


if __name__ == "__main__":
    unittest.main()
