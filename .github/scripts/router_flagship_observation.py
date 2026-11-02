#!/usr/bin/env python3
"""Anonymous scheduled observation; canonical owners retain all repair authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

SOURCE = "https://api.github.com/repos/szl-holdings/szl-router/commits/main"
SPACE = "https://huggingface.co/api/spaces/SZLHOLDINGS/llm-router-live"
CARD = "https://huggingface.co/api/spaces/SZLHOLDINGS/README"
ATTESTATION = "https://szlholdings-llm-router-live.hf.space/.well-known/szl-source.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 1_000_000


class Unavailable(ValueError):
    """Only fixed diagnostic codes may be included in the public report."""


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before, after = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if (after.scheme != "https" or after.netloc != before.netloc
                or after.username is not None or after.password is not None):
            raise Unavailable("REDIRECT_ORIGIN_CHANGED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_get(url):
    request = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json, text/plain", "Cache-Control": "no-cache",
        "User-Agent": "szl-router-public-observation/1",
    })
    with urllib.request.build_opener(SameOriginRedirect()).open(request, timeout=10) as response:
        if response.status != 200:
            raise Unavailable("PUBLIC_READ_NOT_OK")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Unavailable("RESPONSE_OVERSIZE")
    return raw


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Unavailable("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def json_object(get, url):
    def nonfinite(_):
        raise Unavailable("NONFINITE_JSON")
    value = json.loads(get(url), object_pairs_hook=object_pairs, parse_constant=nonfinite)
    if not isinstance(value, dict):
        raise Unavailable("JSON_OBJECT_REQUIRED")
    return value


def revision(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Unavailable("EXACT_REVISION_REQUIRED")
    return value


def observe(source_sha, expected_card, get=public_get):
    report = {
        "schema": "szl.router-flagship-public-observation/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "observer_source_sha": revision(source_sha), "status": "UNAVAILABLE",
        "provider_mutations_performed": False, "credentials_requested": False,
        "inference_readiness": "NOT_INFERRED", "atomic_snapshot": False,
        "findings": [], "observation": {},
    }
    try:
        source = json_object(get, SOURCE)
        info = json_object(get, SPACE)
        runtime = json_object(get, SPACE + "/runtime")
        attestation = json_object(get, ATTESTATION)
        card_info = json_object(get, CARD)
        source_revision = revision(source.get("sha"))
        hub_revision = revision(info.get("sha"))
        runtime_revision = revision(runtime.get("sha"))
        card_revision = revision(card_info.get("sha"))
        source_binding, deployment = attestation.get("source"), attestation.get("deployment")
        if not isinstance(source_binding, dict) or not isinstance(deployment, dict):
            raise Unavailable("SOURCE_BINDING_OBJECTS_REQUIRED")
        attested_source = revision(source_binding.get("commit"))
        attested_hub = revision(deployment.get("hf_revision"))
        if type(info.get("private")) is not bool or type(card_info.get("private")) is not bool:
            raise Unavailable("VISIBILITY_REQUIRED")
        if not isinstance(runtime.get("stage"), str):
            raise Unavailable("RUNTIME_STAGE_REQUIRED")
        raw_card = get("https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/"
                       + card_revision + "/README.md")
        checks = {
            "SPACE_NOT_PUBLIC": info["private"] is False and info.get("visibility", "public") == "public",
            "SPACE_NOT_RUNNING": runtime["stage"] == "RUNNING",
            "RUNTIME_REVISION_MISMATCH": hub_revision == runtime_revision == attested_hub,
            "SOURCE_BINDING_MISMATCH": attested_source == source_revision
                and source_binding.get("repository") == "szl-holdings/szl-router"
                and attestation.get("alignment_state") == "SOURCE_BOUND_DEPLOYMENT",
            "CARD_NOT_PUBLIC": card_info["private"] is False
                and card_info.get("visibility", "public") == "public",
            "CARD_BYTES_MISMATCH": raw_card == expected_card,
        }
        # A moving source or provider ref is indeterminate, not a stable drift verdict.
        if (revision(json_object(get, SOURCE).get("sha")) != source_revision
                or revision(json_object(get, SPACE).get("sha")) != hub_revision
                or revision(json_object(get, CARD).get("sha")) != card_revision):
            raise Unavailable("OBSERVED_REVISION_MOVED")
        report["observation"] = {
            "router_source_sha": source_revision, "space_sha": hub_revision,
            "runtime_sha": runtime_revision, "card_sha": card_revision,
            "expected_card_sha256": hashlib.sha256(expected_card).hexdigest(),
            "observed_card_sha256": hashlib.sha256(raw_card).hexdigest(),
        }
        report["findings"] = [code for code, passed in checks.items() if not passed]
        report["status"] = "DRIFT" if report["findings"] else "OBSERVED_MATCH"
    except Unavailable as exc:
        report["findings"] = [str(exc)]
    except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError):
        report["findings"] = ["PUBLIC_OBSERVATION_UNAVAILABLE"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    report = observe(args.source_sha, (root / "huggingface/org-card/README.md").read_bytes())
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["status"] == "OBSERVED_MATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
