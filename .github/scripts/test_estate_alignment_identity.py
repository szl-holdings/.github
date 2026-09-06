#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline source-identity regressions against the actual alignment validator."""
from __future__ import annotations

import json
import unittest

import estate_alignment_contract as alignment

REPOSITORY = "szl-holdings/a11oy"
REVISION = "a" * 40
ROW = {"repo_id": "SZLHOLDINGS/a11oy", "deployment_source": REPOSITORY}
ENVELOPES = (None, "build", "source", "deployment", "runtime")
FIELDS = ("repository", "source_repository")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
