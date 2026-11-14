from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
import unittest.mock as mock
import urllib.request

import router_flagship_observation as observation


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.responses = {
            observation.SOURCE: {"sha": "a" * 40},
            observation.SPACE: {"sha": "b" * 40, "private": False},
            observation.SPACE + "/runtime": {"sha": "b" * 40, "stage": "RUNNING"},
            observation.CARD: {"sha": "c" * 40, "private": False},
            observation.ATTESTATION: {
                "source": {"commit": "a" * 40, "repository": "szl-holdings/szl-router"},
                "deployment": {"hf_revision": "b" * 40},
                "alignment_state": "SOURCE_BOUND_DEPLOYMENT",
            },
            "https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/"
            + "c" * 40 + "/README.md": b"exact canonical card\n",
        }
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        value = self.responses[url]
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    def observe(self, get=None):
        return observation.observe("d" * 40, b"exact canonical card\n", get or self.get)

    def test_matching_fixed_public_reads_do_not_certify_inference(self):
        report = self.observe()
        self.assertEqual(report["status"], "OBSERVED_MATCH")
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(report["inference_readiness"], "NOT_INFERRED")
        self.assertFalse(report["credentials_requested"])
        self.assertFalse(report["provider_mutations_performed"])
        self.assertEqual(report["observation"]["space_sha"], "b" * 40)

    def test_observable_drift_never_becomes_a_match(self):
        cases = [
            (observation.SPACE, "private", True, "SPACE_NOT_PUBLIC"),
            (observation.SPACE, "visibility", "protected", "SPACE_NOT_PUBLIC"),
            (observation.SPACE + "/runtime", "stage", "PAUSED", "SPACE_NOT_RUNNING"),
            (observation.SPACE + "/runtime", "sha", "e" * 40, "RUNTIME_REVISION_MISMATCH"),
            (observation.ATTESTATION, "alignment_state", "STALE", "SOURCE_BINDING_MISMATCH"),
            (observation.CARD, "private", True, "CARD_NOT_PUBLIC"),
        ]
        original = copy.deepcopy(self.responses)
        for url, key, value, expected in cases:
            with self.subTest(expected=expected, value=value):
                self.responses = copy.deepcopy(original)
                self.responses[url][key] = value
                report = self.observe()
                self.assertEqual(report["status"], "DRIFT")
                self.assertIn(expected, report["findings"])

    def test_card_is_compared_at_the_observed_immutable_revision(self):
        url = next(url for url in self.responses if "/resolve/" in url)
        self.responses[url] = b"stale card"
        self.assertEqual(self.observe()["findings"], ["CARD_BYTES_MISMATCH"])
        self.assertIn(url, self.calls)
        self.assertNotIn("/resolve/main/", " ".join(self.calls))

    def test_source_repository_and_revision_must_match(self):
        original = copy.deepcopy(self.responses[observation.ATTESTATION]["source"])
        for key, value in [("commit", "e" * 40), ("repository", "other/router")]:
            with self.subTest(key=key):
                self.responses[observation.ATTESTATION]["source"] = copy.deepcopy(original)
                self.responses[observation.ATTESTATION]["source"][key] = value
                self.assertIn("SOURCE_BINDING_MISMATCH", self.observe()["findings"])

    def test_moving_refs_are_unavailable_not_stable_drift(self):
        for target in [observation.SOURCE, observation.SPACE, observation.CARD]:
            with self.subTest(target=target):
                calls = []

                def moving(url):
                    calls.append(url)
                    if url == target and calls.count(url) == 2:
                        return json.dumps({"sha": "f" * 40}).encode()
                    return self.get(url)

                report = self.observe(moving)
                self.assertEqual(report["status"], "UNAVAILABLE")
                self.assertEqual(report["findings"], ["OBSERVED_REVISION_MOVED"])

    def test_missing_or_malformed_provider_evidence_cannot_pass(self):
        original = copy.deepcopy(self.responses)
        cases = [
            (observation.SPACE, {"sha": "short", "private": False}),
            (observation.SPACE, {"sha": "b" * 40, "private": "false"}),
            (observation.ATTESTATION, {"source": [], "deployment": {}}),
            (observation.SPACE + "/runtime", {"sha": "b" * 40}),
            (observation.CARD, []),
            (observation.CARD, b'{"sha":"x","sha":"y"}'),
            (observation.CARD, b'{"sha":NaN}'),
            (observation.CARD, b'not json'),
        ]
        for url, value in cases:
            with self.subTest(url=url, value=value):
                self.responses = copy.deepcopy(original)
                self.responses[url] = value
                self.assertEqual(self.observe()["status"], "UNAVAILABLE")

    def test_read_failure_never_leaks_provider_body_or_retries_writes(self):
        def failed(_):
            raise OSError("untrusted response with credential-like data")
        report = self.observe(failed)
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(report["findings"], ["PUBLIC_OBSERVATION_UNAVAILABLE"])
        self.assertNotIn("credential-like", json.dumps(report))

    def test_transport_uses_bounded_anonymous_get(self):
        with mock.patch.object(observation.urllib.request, "build_opener") as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.status, response.read.return_value = 200, b"{}"
            self.assertEqual(observation.public_get(observation.SPACE), b"{}")
            args, kwargs = build.return_value.open.call_args
            self.assertEqual(args[0].get_method(), "GET")
            self.assertNotIn("authorization", {key.lower() for key in args[0].headers})
            self.assertEqual(kwargs["timeout"], 10)
            response.read.assert_called_once_with(observation.MAX_BYTES + 1)
            response.read.return_value = b"x" * (observation.MAX_BYTES + 1)
            with self.assertRaisesRegex(observation.Unavailable, "RESPONSE_OVERSIZE"):
                observation.public_get(observation.SPACE)

    def test_redirects_cannot_change_origin_or_transport(self):
        handler = observation.SameOriginRedirect()
        request = urllib.request.Request(observation.SPACE)
        for url in ["https://other.example/path", "http://huggingface.co/path",
                    "https://user@huggingface.co/path"]:
            with self.subTest(url=url), self.assertRaises(observation.Unavailable):
                handler.redirect_request(request, None, 302, "redirect", {}, url)
        redirected = handler.redirect_request(
            request, None, 302, "redirect", {}, "https://huggingface.co/api/resolve-cache/spaces/id"
        )
        self.assertEqual(redirected.get_method(), "GET")

    def test_scheduled_workflow_has_no_repair_authority(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/enforce-llm-router-flagship-card.yml").read_text()
        self.assertIn('cron: "17 8 * * *"', workflow)
        self.assertIn("if: ${{ false }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("contents: read", workflow)
        for forbidden in ["secrets.", "HF_TOKEN", "--apply", "contents: write", "id-token:",
                          "environment: production", "scripts/enforce_llm_router_flagship_card.py"]:
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
