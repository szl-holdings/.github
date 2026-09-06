#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline source-identity regressions against the actual alignment validator."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import estate_alignment_contract as alignment

REPOSITORY = "szl-holdings/a11oy"
REVISION = "a" * 40
ROW = {"repo_id": "SZLHOLDINGS/a11oy", "deployment_source": REPOSITORY}
ENVELOPES = (None, "build", "source", "deployment", "runtime")
FIELDS = ("repository", "source_repository")
ROOT = Path(__file__).resolve().parents[2]


def envelope(name: str | None, key: str, value: object) -> dict:
    field = {key: value}
    return field if name is None else {name: field}


class ExplicitSourceIdentityTests(unittest.TestCase):
    def bind(self, payload: dict) -> tuple[dict, list[str]]:
        calls: list[str] = []

        def fetch(url: str, **kwargs: object) -> bytes:
            calls.append(url)
            self.assertEqual(kwargs["required_origin"], "https://szlholdings-a11oy.hf.space")
            self.assertNotIn("token", kwargs)
            return json.dumps(payload).encode("utf-8")

        return alignment.runtime_source_binding(ROW, REVISION, fetch=fetch), calls

    def test_absence_remains_distinct_from_a_reported_repository(self) -> None:
        payload = {"source_revision": REVISION, "runtime": {"stage": "RUNNING"}}
        self.assertIsNone(alignment.reported_source_repository(payload))
        result, calls = self.bind(payload)
        self.assertTrue(result["matched"])
        self.assertIsNone(result["observed_source"])
        self.assertEqual(result["source_evidence"], "contract-bound-origin")
        self.assertEqual(len(calls), alignment.RUNTIME_OBSERVATIONS)

    def test_valid_fields_in_every_supported_envelope(self) -> None:
        for name in ENVELOPES:
            for key in FIELDS:
                with self.subTest(name=name, key=key):
                    payload = {"source_revision": REVISION, **envelope(name, key, REPOSITORY)}
                    result, _ = self.bind(payload)
                    self.assertTrue(result["matched"])
                    self.assertEqual(result["observed_source"], REPOSITORY)
                    self.assertEqual(result["source_evidence"], "reported")

    def test_foreign_repository_is_rejected_in_every_envelope(self) -> None:
        for name in ENVELOPES:
            for key in FIELDS:
                with self.subTest(name=name, key=key):
                    payload = {"source_revision": REVISION, **envelope(name, key, "other-org/other-repo")}
                    with self.assertRaises(alignment.AlignmentError):
                        alignment.reported_source_repository(payload)
                    result, calls = self.bind(payload)
                    self.assertFalse(result["matched"])
                    self.assertEqual(len(calls), 1)
                    self.assertIn("invalid source repository", result["attempts"][0]["observations"][0]["error"])

    def test_explicit_null_empty_and_wrong_types_are_not_absence(self) -> None:
        for value in (None, "", " ", False, 0, [], {}, [REPOSITORY]):
            for name in ENVELOPES:
                for key in FIELDS:
                    with self.subTest(value=value, name=name, key=key):
                        payload = envelope(name, key, value)
                        with self.assertRaises(alignment.AlignmentError):
                            alignment.reported_source_repository(payload)

    def test_malformed_strings_cannot_be_normalized_to_origin_evidence(self) -> None:
        for value in ("https://github.com/" + REPOSITORY, REPOSITORY + " ", " " + REPOSITORY,
                      "szl-holdings/", REPOSITORY + "\n", REPOSITORY + "?token=sentinel",
                      REPOSITORY + ":", REPOSITORY + ":bad?token=sentinel"):
            with self.subTest(value=value), self.assertRaises(alignment.AlignmentError):
                alignment.reported_source_repository({"repository": value})

    def test_valid_outer_identity_cannot_hide_invalid_nested_identity(self) -> None:
        for name in ENVELOPES[1:]:
            for key in FIELDS:
                with self.subTest(name=name, key=key):
                    result, calls = self.bind({"source_revision": REVISION,
                                              "repository": REPOSITORY,
                                              **envelope(name, key, "other-org/other-repo")})
                    self.assertFalse(result["matched"])
                    self.assertEqual(len(calls), 1)

    def test_valid_nested_identity_cannot_hide_invalid_outer_identity(self) -> None:
        result, calls = self.bind({"source_revision": REVISION, "repository": None,
                                  "build": {"source_repository": REPOSITORY}})
        self.assertFalse(result["matched"])
        self.assertEqual(len(calls), 1)

    def test_distinct_valid_repository_claims_conflict(self) -> None:
        payload = {"source_revision": REVISION, "repository": REPOSITORY,
                   "deployment": {"source_repository": "szl-holdings/killinchu"}}
        with self.assertRaisesRegex(alignment.AlignmentError, "conflicting"):
            alignment.reported_source_repository(payload)
        self.assertFalse(self.bind(payload)[0]["matched"])

    def test_consistent_repeated_claims_preserve_compatibility(self) -> None:
        payload = {"repository": REPOSITORY, "source_repository": REPOSITORY,
                   "build": {"repository": REPOSITORY}}
        self.assertEqual(alignment.reported_source_repository(payload), REPOSITORY)
        self.assertEqual(alignment.reported_source_repository(
            {"repository": "szl-holdings/a11oy:verticals/counsel"}), REPOSITORY)

    def test_wrong_but_valid_owner_repository_does_not_match(self) -> None:
        result, _ = self.bind({"source_revision": REVISION, "repository": "szl-holdings/killinchu"})
        self.assertFalse(result["matched"])
        self.assertEqual(result["source_evidence"], "conflicting")

    def test_invalid_second_observation_cannot_fall_back_to_success(self) -> None:
        calls: list[str] = []

        def fetch(url: str, **kwargs: object) -> bytes:
            calls.append(url)
            value = REPOSITORY if len(calls) == 1 else "other-org/other-repo"
            return json.dumps({"source_revision": REVISION, "repository": value}).encode()

        result = alignment.runtime_source_binding(ROW, REVISION, fetch=fetch)
        self.assertFalse(result["matched"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("/api/build-info?" in url for url in calls))
        self.assertEqual(result["attempts"][0]["observations"][0]["observed_source"], REPOSITORY)

    def test_untrusted_values_are_not_reflected_into_retained_errors(self) -> None:
        sentinel = "foreign/private-name?credential=DO_NOT_RECORD"
        result, _ = self.bind({"source_revision": REVISION, "repository": sentinel})
        self.assertFalse(result["matched"])
        self.assertNotIn(sentinel, json.dumps(result))
        self.assertNotIn("DO_NOT_RECORD", json.dumps(result))


class CheckedOutReceiptIdentityTests(unittest.TestCase):
    def test_event_merge_sha_cannot_replace_checked_out_commit(self) -> None:
        result = subprocess.CompletedProcess(["git"], 0, stdout=REVISION + "\n")
        with patch.dict(alignment.os.environ, {"GITHUB_SHA": "b" * 40}), patch.object(
            alignment.subprocess, "run", return_value=result
        ) as run:
            receipt = alignment.build_receipt(ROOT, live=False)
        self.assertEqual(receipt["source_revision"], REVISION)
        self.assertEqual(receipt["state"], "ALIGNED")
        run.assert_called_once_with(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD^{commit}"],
            capture_output=True, text=True, check=True, timeout=10,
        )

    def test_actual_git_checkout_is_read_not_environment_hint(self) -> None:
        expected = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        with patch.dict(alignment.os.environ, {"GITHUB_SHA": "b" * 40}):
            self.assertEqual(alignment.checked_out_revision(ROOT), expected)

    def test_git_failure_retains_failed_receipt_without_error_values(self) -> None:
        error = subprocess.CalledProcessError(1, ["git"], stderr="DO_NOT_RECORD")
        with patch.object(alignment.subprocess, "run", side_effect=error):
            receipt = alignment.build_receipt(ROOT, live=False)
        self.assertEqual(receipt["state"], "DIVERGENT")
        self.assertEqual(receipt["source_revision"], "UNAVAILABLE")
        self.assertIn("checked-out Git source identity unavailable", receipt["failures"])
        self.assertNotIn("DO_NOT_RECORD", json.dumps(receipt))

    def test_invalid_commit_output_is_not_an_identity(self) -> None:
        for value in ("main", "", "a" * 39, "A" * 40, REVISION + "\n" + REVISION):
            result = subprocess.CompletedProcess(["git"], 0, stdout=value)
            with self.subTest(value=value), patch.object(
                alignment.subprocess, "run", return_value=result
            ), self.assertRaises(alignment.AlignmentError):
                alignment.checked_out_revision(ROOT)

    def test_git_timeout_is_bounded_and_does_not_use_event_fallback(self) -> None:
        with patch.dict(alignment.os.environ, {"GITHUB_SHA": REVISION}), patch.object(
            alignment.subprocess, "run", side_effect=subprocess.TimeoutExpired(["git"], 10)
        ), self.assertRaisesRegex(alignment.AlignmentError, "unavailable"):
            alignment.checked_out_revision(ROOT)

    def test_missing_git_cannot_become_a_source_claim(self) -> None:
        with patch.object(alignment.subprocess, "run", side_effect=FileNotFoundError("DO_NOT_RECORD")):
            receipt = alignment.build_receipt(ROOT, live=False)
        self.assertEqual(receipt["state"], "DIVERGENT")
        self.assertEqual(receipt["source_revision"], "UNAVAILABLE")
        self.assertNotIn("DO_NOT_RECORD", json.dumps(receipt))


if __name__ == "__main__":
    unittest.main(verbosity=2)
