#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import unittest
import unittest.mock
import zipfile

import final_estate_v5_artifacts as artifact

SHA = "a" * 40


def report():
    return {"schema": "szl.hf-release-finalization/v2", "generation": SHA,
            "workflow_artifact_binding": {"repository": artifact.REPOSITORY, "run_id": "123", "run_attempt": "2", "source_sha": SHA}}


def archive(value=None, name=artifact.MEMBER, extra=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as stream:
        stream.writestr(name, json.dumps(value or report()))
        if extra:
            stream.writestr("extra.txt", "forbidden")
    body = output.getvalue()
    return body, hashlib.sha256(body).hexdigest()


def run():
    return {"id": 123, "run_attempt": 2, "head_sha": SHA, "head_branch": "main",
            "path": ".github/workflows/" + artifact.WORKFLOW,
            "repository": {"full_name": artifact.REPOSITORY}, "head_repository": {"full_name": artifact.REPOSITORY},
            "event": "push", "status": "completed", "conclusion": "success"}


class Client:
    def __init__(self):
        self.calls = []; self.run = run(); self.body, digest = archive()
        self.artifact = {"id": 456, "name": artifact.ARTIFACT, "expired": False, "digest": "sha256:" + digest,
                         "size_in_bytes": len(self.body), "workflow_run": {"id": 123, "head_sha": SHA}}

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path.endswith("/artifacts"):
            value = {"total_count": 1, "artifacts": [self.artifact]}
        elif path.endswith("/runs"):
            value = {"workflow_runs": [self.run]}
        else:
            value = self.run
        return unittest.mock.Mock(json=lambda: copy.deepcopy(value))


class ArtifactEvidenceTests(unittest.TestCase):
    def test_exact_successful_native_run_and_digest_bound_archive(self):
        client = Client()
        with unittest.mock.patch.dict(os.environ, {"GITHUB_SHA": SHA}), unittest.mock.patch.object(artifact, "download_archive", return_value=client.body):
            value, evidence = artifact.publication_evidence(client)
        self.assertEqual(value, report())
        self.assertEqual(evidence["run_attempt"], 2)
        self.assertTrue(all(call[0] == "GET" for call in client.calls))
        self.assertFalse(any("issues/301" in call[1] for call in client.calls))

    def test_latest_failed_incomplete_foreign_or_stale_run_never_downloads(self):
        for key, value in (("conclusion", "failure"), ("status", "in_progress"), ("head_sha", "b" * 40),
                           ("head_branch", "feature"), ("path", ".github/workflows/other.yml"), ("event", "pull_request"),
                           ("run_attempt", True), ("repository", {"full_name": "elsewhere/repo"})):
            client = Client(); client.run[key] = value
            with self.subTest(key=key), unittest.mock.patch.dict(os.environ, {"GITHUB_SHA": SHA}), unittest.mock.patch.object(artifact, "download_archive") as download, self.assertRaises(RuntimeError):
                artifact.publication_evidence(client)
            download.assert_not_called()

    def test_artifact_expiry_digest_and_native_source_are_mandatory(self):
        for key, value in (("expired", True), ("digest", None), ("size_in_bytes", True),
                           ("workflow_run", {"id": 99, "head_sha": SHA})):
            client = Client(); client.artifact[key] = value
            with self.subTest(key=key), unittest.mock.patch.dict(os.environ, {"GITHUB_SHA": SHA}), unittest.mock.patch.object(artifact, "download_archive") as download, self.assertRaises(RuntimeError):
                artifact.publication_evidence(client)
            download.assert_not_called()

    def test_prior_attempt_or_other_source_report_cannot_qualify(self):
        for key, value in (("run_attempt", "1"), ("source_sha", "b" * 40), ("repository", "elsewhere/repo")):
            payload = report(); payload["workflow_artifact_binding"][key] = value
            body, digest = archive(payload)
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "SOURCE_MISMATCH"):
                artifact.parse_archive(body, digest, 123, 2, SHA)

    def test_archive_digest_traversal_extra_member_and_size_fail(self):
        body, digest = archive()
        with self.assertRaisesRegex(RuntimeError, "DIGEST_MISMATCH"):
            artifact.parse_archive(body, "0" * 64, 123, 2, SHA)
        for kwargs in ({"name": "../" + artifact.MEMBER}, {"extra": True}):
            body, digest = archive(**kwargs)
            with self.assertRaisesRegex(RuntimeError, "ARCHIVE_SCOPE"):
                artifact.parse_archive(body, digest, 123, 2, SHA)
        body, digest = archive()
        with unittest.mock.patch.object(artifact, "MAX_RESPONSE_BYTES", 10), self.assertRaisesRegex(RuntimeError, "ARCHIVE_SCOPE"):
            artifact.parse_archive(body, digest, 123, 2, SHA)

    def test_changed_attempt_after_download_rejected(self):
        client = Client()
        def downloading(*args):
            client.run["run_attempt"] = 3
            return client.body
        with unittest.mock.patch.dict(os.environ, {"GITHUB_SHA": SHA}), unittest.mock.patch.object(artifact, "download_archive", side_effect=downloading), self.assertRaisesRegex(RuntimeError, "RUN_MOVED"):
            artifact.publication_evidence(client)

    def test_duplicate_or_nonfinite_report_json_rejects(self):
        for payload, reason in ((b'{"schema":1,"schema":2}', "DUPLICATE_JSON_KEY"),
                                (b'{"value":NaN}', "NONFINITE_JSON")):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as stream:
                stream.writestr(artifact.MEMBER, payload)
            body = output.getvalue()
            with self.subTest(reason=reason), self.assertRaisesRegex(RuntimeError, reason):
                artifact.parse_archive(body, hashlib.sha256(body).hexdigest(), 123, 2, SHA)

    def test_different_second_artifact_cannot_mix_observations(self):
        client = Client()
        with unittest.mock.patch.dict(os.environ, {"GITHUB_SHA": SHA}), unittest.mock.patch.object(artifact, "download_archive", return_value=client.body):
            artifact.publication_evidence(client)
            client.artifact["id"] = 457
            with self.assertRaisesRegex(RuntimeError, "OBSERVATION_MOVED"):
                artifact.publication_evidence(client)

    def test_finite_json_exponent_overflow_rejects_digest_valid_report(self):
        for exponent in (b"1e1000", b"-1e1000"):
            payload = json.dumps({**report(), "numeric_observation": 1.0}).encode()
            payload = payload.replace(b"1.0", exponent)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as stream:
                stream.writestr(artifact.MEMBER, payload)
            body = output.getvalue()
            with self.subTest(exponent=exponent), self.assertRaisesRegex(RuntimeError, "NONFINITE_JSON"):
                artifact.parse_archive(body, hashlib.sha256(body).hexdigest(), 123, 2, SHA)
        body, digest = archive({**report(), "numeric_observation": 1e308})
        self.assertEqual(artifact.parse_archive(body, digest, 123, 2, SHA)["numeric_observation"], 1e308)

    def test_signed_download_rejects_foreign_host_before_network(self):
        for target in ("http://fixture.blob.core.windows.net/file", "https://example.invalid/file",
                       "https://user:pass@fixture.blob.core.windows.net/file", "https://fixture.blob.core.windows.net:444/file"):
            client = unittest.mock.Mock()
            client.request.return_value.headers = {"Location": target}
            with self.subTest(target=target), unittest.mock.patch.object(artifact.requests, "Session") as session, self.assertRaisesRegex(RuntimeError, "TARGET_REJECTED"):
                artifact.download_archive(client, 456)
            session.assert_not_called()

    def test_signed_download_uses_separate_unauthenticated_no_redirect_session(self):
        client = unittest.mock.Mock()
        client.request.return_value.headers = {"Location": "https://fixture.blob.core.windows.net/file?synthetic=sas"}
        response = unittest.mock.Mock(status_code=200); response.iter_content.return_value = [b"zip"]
        session = unittest.mock.Mock(); session.get.return_value = response
        with unittest.mock.patch.object(artifact.requests, "Session", return_value=session):
            self.assertEqual(artifact.download_archive(client, 456), b"zip")
        self.assertFalse(session.trust_env)
        self.assertNotIn("headers", session.get.call_args.kwargs)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
