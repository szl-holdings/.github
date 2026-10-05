#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline Metricool contract preflight; never schedules, signs, or authorizes.

Evidence is supplied by a caller, not independently fetched or authenticated here.
Even a passing preflight cannot authorize a provider operation. A future writer
needs trusted fresh readbacks, independently verified authority, a durable atomic
reservation, and delivery-time enforcement. No such writer is introduced here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
LABELS = frozenset({"MEASURED", "REPORTED", "DECLARED", "SIMULATED", "SAMPLE",
                    "MODELED", "ROADMAP", "UNKNOWN", "UNAVAILABLE", "BLOCKED"})
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
                     r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z")
CATEGORIES = {"thesis": set(), "architecture": {"source"},
              "release": {"source", "artifact", "runtime"},
              "security": {"source", "artifact", "runtime", "security"},
              "model": {"source", "artifact", "evaluation"},
              "research": {"source", "evaluation"}}
# These require separate legal/financial/human substantiation, not this gate.
MANUAL_ONLY = {"compliance", "funding", "customers", "revenue"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("non-finite JSON value")


def read_json(path):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("input exceeds bounded contract size")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                      parse_constant=_nonfinite)


def validate_schema(value, schema_name):
    from jsonschema import Draft202012Validator, FormatChecker
    allowed = {"config": "config/schemas/metricool-control-plane.schema.json",
               "receipt": "schemas/metricool-publication-receipt.schema.json"}
    schema = read_json(ROOT / allowed[schema_name])
    Draft202012Validator.check_schema(schema)
    # Schemas have no external references. No caller-controlled schema URL.
    checker = FormatChecker()
    # jsonschema's optional format extras are not guaranteed to be installed.
    # Explicit local checks prevent a missing extra silently accepting bad dates.
    @checker.checks("date-time", raises=(ValueError, TypeError, OverflowError))
    def check_datetime(value):
        if not isinstance(value, str):
            return True  # JSON Schema's type keyword handles non-strings.
        timestamp(value)
        return True

    @checker.checks("uri", raises=(ValueError, TypeError))
    def check_uri(value):
        if not isinstance(value, str):
            return True
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname) and url.port in (None, 443)
                and not url.username and not url.password
                and not any(c.isspace() or ord(c) < 32 or c == "\\" for c in value))

    Draft202012Validator(schema, format_checker=checker).validate(value)


def timestamp(value):
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise ValueError("timestamp must be a timezone-qualified string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


def normalized_content(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("nonempty content required")
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def content_digest(text):
    return hashlib.sha256(normalized_content(text).encode("utf-8")).hexdigest()


def idempotency_key(brand, provider, payload, scheduled_at, revision):
    """Account-scoped intent digest, NOT an atomic deduplication mechanism.

    Includes ALL provider payload fields (media, disclosures, poll, etc.). It is
    intentionally conservative: changed provider metadata creates a new intent
    requiring review. Exact UTC instants avoid DST/time-bucket collisions.
    """
    if not isinstance(brand, str) or not brand or provider not in {"twitter", "linkedin"}:
        raise ValueError("explicit account and approved provider required")
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        raise ValueError("exact source revision required")
    if not isinstance(payload, dict):
        raise ValueError("provider payload must be an object")
    clean = dict(payload)
    clean["text"] = normalized_content(payload.get("text"))
    envelope = [brand, provider, clean, timestamp(scheduled_at).isoformat(), revision]
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _fresh(observed_at, now, max_age):
    age = (now - timestamp(observed_at)).total_seconds()
    return 0 <= age <= max_age


def _public_ref(value):
    if not isinstance(value, str) or any(
            c.isspace() or ord(c) < 32 or c == "\\" for c in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in {
            "github.com", "huggingface.co", "a-11-oy.com", "a11oy.net"}
            and url.port in (None, 443) and not url.username and not url.password
            and not url.query and not url.fragment)
    except ValueError:
        return False


def validate_public_claim(claim, *, now, max_age=300):
    """Validate caller-declared evidence consistency, not its authenticity."""
    reasons = []
    try:
        content_digest(claim["text"])
        category = claim["category"]
        label = claim["classification"]
        if label not in LABELS:
            reasons.append("UNKNOWN_CLASSIFICATION")
        if category in MANUAL_ONLY or category not in CATEGORIES:
            reasons.append("MANUAL_SUBSTANTIATION_REQUIRED")
        if label in {"UNKNOWN", "UNAVAILABLE", "BLOCKED"}:
            reasons.append("CLAIM_UNQUALIFIED")
        revision = claim["sourceRevision"]
        if not SHA.fullmatch(revision) or revision != claim["currentSourceRevision"]:
            reasons.append("SOURCE_MOVED_OR_UNPINNED")
        if not _fresh(claim["sourceObservedAt"], now, max_age):
            reasons.append("SOURCE_READBACK_STALE")
        refs = claim["evidence"]
        if not isinstance(refs, list) or len(refs) > 100:
            raise ValueError("bounded evidence list required")
        seen = set()
        artifact_digest = None
        for entry in refs:
            kind = entry["kind"]
            if kind in seen or kind not in {"source", "artifact", "runtime", "security", "evaluation"}:
                reasons.append("DUPLICATE_OR_UNKNOWN_EVIDENCE_KIND")
            seen.add(kind)
            if (entry["sourceRevision"] != revision or entry["result"] != "PASS"
                    or not _public_ref(entry["ref"])):
                reasons.append("EVIDENCE_MISMATCH")
            if not _fresh(entry["observedAt"], now, max_age):
                reasons.append("EVIDENCE_STALE")
            if kind in {"artifact", "runtime", "evaluation", "security"}:
                digest = entry["artifactSha256"]
                if not DIGEST.fullmatch(digest):
                    reasons.append("ARTIFACT_UNBOUND")
                if artifact_digest is not None and artifact_digest != digest:
                    reasons.append("ARTIFACT_MISMATCH")
                artifact_digest = digest
        if not CATEGORIES.get(category, set()).issubset(seen):
            reasons.append("EVIDENCE_MISSING")
        if category != "thesis" and label not in {"MEASURED", "REPORTED"}:
            reasons.append("TECHNICAL_CLAIM_REQUIRES_EVIDENCE")
        if not isinstance(claim["knownLimits"], list) or not claim["knownLimits"] or not all(
                isinstance(x, str) and x.strip() for x in claim["knownLimits"]):
            reasons.append("KNOWN_LIMITS_REQUIRED")
    except (KeyError, TypeError, ValueError, OverflowError):
        reasons.append("MALFORMED_CLAIM")
    return {"classification": "DECLARED" if not reasons else "BLOCKED",
            "preflight_passed": not reasons, "allowed_to_publish": False,
            "reasons": sorted(set(reasons)),
            "known_limits": ["Caller-supplied evidence is not authenticated here.",
                             "No semantic truth, human approval or provider authority is established."]}


def preflight(config, request, environ, *, now):
    validate_schema(config, "config")
    reasons = []
    try:
        now = timestamp(now)
        brand_id = environ.get(config["brandSelection"]["brandIdSource"])
        zone = environ.get(config["brandSelection"]["timezoneSource"])
        if not isinstance(brand_id, str) or not brand_id.strip() or zone != "America/New_York":
            reasons.append("EXPLICIT_BRAND_AND_TIMEZONE_REQUIRED")
        brand = request["brand"]
        if (str(brand["id"]) != brand_id or brand["timezone"] != zone
                or not _fresh(brand["observedAt"], now, config["policy"]["maxEvidenceAgeSeconds"])):
            reasons.append("BRAND_READBACK_MISMATCH_OR_STALE")
        network = request["provider"]
        if network not in config["authorizedNetworks"]:
            reasons.append("NETWORK_NOT_AUTHORIZED")
        if not isinstance(brand["connectedNetworks"], list) or network not in brand["connectedNetworks"]:
            reasons.append("NETWORK_NOT_CONNECTED")
        operation = request["operation"]
        if operation != "review-draft":
            # Neither conditional updates nor atomic delivery-time evidence holds
            # have been demonstrated by the connected API. Do not pretend so.
            reasons.append("PROVIDER_MUTATION_NOT_IMPLEMENTED")
        claim_result = validate_public_claim(request["claim"], now=now,
                                             max_age=config["policy"]["maxEvidenceAgeSeconds"])
        reasons.extend(claim_result["reasons"])
        if timestamp(request["scheduledAt"]) <= now:
            reasons.append("SCHEDULE_NOT_FUTURE")
        if content_digest(request["payload"]["text"]) != content_digest(request["claim"]["text"]):
            reasons.append("CONTENT_CLAIM_MISMATCH")
        digest = idempotency_key(brand_id, network, request["payload"],
                                 request["scheduledAt"], request["claim"]["sourceRevision"])
        planner = request["planner"]
        if (planner["complete"] is not True or not isinstance(planner["intentKeys"], list)
                or not _fresh(planner["observedAt"], now, config["policy"]["maxEvidenceAgeSeconds"])):
            reasons.append("PLANNER_INCOMPLETE_OR_STALE")
        if digest in planner["intentKeys"]:
            reasons.append("DUPLICATE_INTENT")
    except (KeyError, TypeError, ValueError, OverflowError):
        reasons.append("MALFORMED_REQUEST")
    return {"schema": "szl.metricool-preflight/v1", "evidenceClass": "DECLARED",
            "state": "BLOCKED" if reasons else "DECLARED",
            "preflight_passed": not reasons, "allowed_to_publish": False,
            "provider_writes": 0, "reasons": sorted(set(reasons)),
            "knownLimits": ["Offline supplied-record validation only; no independent authority.",
                            "Automatic scheduling and updates are disabled.",
                            "Intent hashes do not provide atomic or provider-side idempotency."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/metricool-control-plane.json")
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    try:
        config = read_json(args.config)
        validate_schema(config, "config")
        if args.request:
            result = preflight(config, read_json(args.request), os.environ,
                               now=datetime.now(timezone.utc).isoformat())
        else:
            result = {"evidenceClass": "MEASURED", "config_valid": True,
                      "allowed_to_publish": False, "provider_writes": 0}
    except Exception:
        # Do not echo a possibly sensitive input, environment, or exception body.
        print(json.dumps({"state": "BLOCKED", "reason": "INVALID_CONTRACT_OR_DEPENDENCY",
                          "allowed_to_publish": False, "provider_writes": 0}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 2 if result.get("state") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
