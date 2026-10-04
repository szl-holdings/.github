#!/usr/bin/env python3
"""Read the existing finalizer's exact successful run artifact; never issue #301."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import time
from urllib.parse import urlsplit
import zipfile

import requests

from final_estate_v5_core import MAX_RESPONSE_BYTES, SHA40, bounded_content

REPOSITORY = "szl-holdings/.github"
WORKFLOW = "hf-release-finalization.yml"
ARTIFACT = "hf-release-finalization-supported"
MEMBER = "hf-release-finalization-latest.json"


def positive(value):
    if type(value) is not int or not 0 < value < 2**53:
        raise RuntimeError("PUBLICATION_NATIVE_ID_INVALID")
    return value


def validate_run(value, source):
    if (not isinstance(value, dict) or value.get("head_sha") != source
            or value.get("head_branch") != "main" or value.get("path") != ".github/workflows/" + WORKFLOW
            or value.get("repository", {}).get("full_name") != REPOSITORY
            or value.get("head_repository", {}).get("full_name") != REPOSITORY
            or value.get("status") != "completed" or value.get("conclusion") != "success"
            or value.get("event") not in {"push", "schedule", "repository_dispatch", "workflow_dispatch"}):
        raise RuntimeError("PUBLICATION_RUN_UNQUALIFIED")
    return positive(value.get("id")), positive(value.get("run_attempt"))


def parse_archive(body, digest, run_id, attempt, source):
    if hashlib.sha256(body).hexdigest() != digest:
        raise RuntimeError("PUBLICATION_ARTIFACT_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        infos = archive.infolist()
        if (len(infos) != 1 or infos[0].filename != MEMBER or infos[0].flag_bits & 1
                or stat.S_ISLNK(infos[0].external_attr >> 16)
                or not 0 < infos[0].file_size <= MAX_RESPONSE_BYTES):
            raise RuntimeError("PUBLICATION_ARCHIVE_SCOPE_INVALID")
        with archive.open(infos[0]) as stream:
            content = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(content) > MAX_RESPONSE_BYTES:
            raise RuntimeError("PUBLICATION_REPORT_TOO_LARGE")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise RuntimeError("PUBLICATION_DUPLICATE_JSON_KEY")
            out[key] = value
        return out
    def nonfinite(_):
        raise RuntimeError("PUBLICATION_NONFINITE_JSON")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise RuntimeError("PUBLICATION_NONFINITE_JSON")
        return parsed
    report = json.loads(content, object_pairs_hook=pairs, parse_constant=nonfinite,
                        parse_float=finite_float)
    expected = {"repository": REPOSITORY, "run_id": str(run_id), "run_attempt": str(attempt), "source_sha": source}
    if (not isinstance(report, dict) or report.get("generation") != source
            or report.get("workflow_artifact_binding") != expected
            or report.get("schema") != "szl.hf-release-finalization/v2"):
        raise RuntimeError("PUBLICATION_ARTIFACT_SOURCE_MISMATCH")
    return report


def download_archive(client, artifact_id):
    redirect = client.request("GET", f"/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip", expected=(302,))
    target = redirect.headers.get("Location", "")
    url = urlsplit(target)
    if (url.scheme != "https" or url.username or url.password or url.port not in {None, 443}
            or not url.hostname or not url.hostname.endswith((".blob.core.windows.net", ".actions.githubusercontent.com"))):
        raise RuntimeError("PUBLICATION_DOWNLOAD_TARGET_REJECTED")
    # The GitHub bearer token is never forwarded to the signed artifact host.
    session = requests.Session(); session.trust_env = False
    try:
        response = session.get(target, allow_redirects=False, stream=True, timeout=(10, 20))
        if response.status_code != 200:
            response.close()
            raise RuntimeError("PUBLICATION_DOWNLOAD_UNAVAILABLE")
        return bounded_content(response, deadline=time.monotonic() + 60)
    except requests.RequestException:
        raise RuntimeError("PUBLICATION_DOWNLOAD_UNAVAILABLE") from None
    finally:
        session.close()


def publication_evidence(client):
    source = os.environ.get("GITHUB_SHA", "")
    if SHA40.fullmatch(source) is None or source == "0" * 40:
        raise RuntimeError("PUBLICATION_SOURCE_INVALID")
    path = f"/repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs"
    listing = client.request("GET", path, params={"branch": "main", "per_page": 1}).json()
    runs = listing.get("workflow_runs") if isinstance(listing, dict) else None
    if not isinstance(runs, list) or len(runs) != 1:
        raise RuntimeError("PUBLICATION_LATEST_RUN_UNAVAILABLE")
    run_id, attempt = validate_run(runs[0], source)
    artifact_listing = client.request("GET", f"/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts", params={"per_page": 100}).json()
    artifacts = artifact_listing.get("artifacts") if isinstance(artifact_listing, dict) else None
    if (not isinstance(artifacts, list) or len(artifacts) > 100
            or type(artifact_listing.get("total_count")) is not int
            or artifact_listing.get("total_count") != len(artifacts)):
        raise RuntimeError("PUBLICATION_ARTIFACT_LIST_INCOMPLETE")
    candidates = [a for a in artifacts if isinstance(a, dict) and a.get("name") == ARTIFACT]
    if len(candidates) != 1:
        raise RuntimeError("PUBLICATION_ARTIFACT_AMBIGUOUS_OR_MISSING")
    artifact = candidates[0]; artifact_id = positive(artifact.get("id"))
    binding = artifact.get("workflow_run")
    digest = artifact.get("digest", "")
    if (artifact.get("expired") is not False or not isinstance(binding, dict)
            or binding.get("id") != run_id or binding.get("head_sha") != source
            or not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or not 0 < positive(artifact.get("size_in_bytes")) <= MAX_RESPONSE_BYTES):
        raise RuntimeError("PUBLICATION_ARTIFACT_UNQUALIFIED")
    body = download_archive(client, artifact_id)
    report = parse_archive(body, digest[7:], run_id, attempt, source)
    current = client.request("GET", f"/repos/{REPOSITORY}/actions/runs/{run_id}").json()
    if validate_run(current, source) != (run_id, attempt):
        raise RuntimeError("PUBLICATION_RUN_MOVED")
    evidence = {"run_id": run_id, "run_attempt": attempt, "artifact_id": artifact_id, "artifact_sha256": digest[7:], "source_sha": source,
                "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"}
    previous = getattr(client, "publication_observation", None)
    if previous is not None and previous != evidence:
        raise RuntimeError("PUBLICATION_OBSERVATION_MOVED")
    client.publication_observation = evidence
    return report, evidence
