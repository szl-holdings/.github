#!/usr/bin/env python3
"""Observe three public HF collections without credentials or provider writes.

This proposed navigation contract is independent of the legacy two-title
publisher. PASS describes only the named collections' public metadata, never
model quality, production readiness, promotion, or a taxonomy migration.
Snapshot inputs are untrusted local observations, not fresh provider evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_POLICY_BYTES = 128 * 1024
MAX_ITEMS = 128
TIMEOUT_SECONDS = 10
OWNER = {"name": "SZLHOLDINGS", "type": "org", "id": "6a18de7657b5b7a615a55801"}
BOUNDARIES = {
    "provider_writes": False,
    "promotion_allowed": False,
    "model_quality": "NOT_EVALUATED",
    "production_readiness": "NOT_EVALUATED",
    "legacy_start_here_reconciliation": "UNRESOLVED_SEPARATE_CONTRACT",
}
POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "hf-collection-navigation.v1.json"
BASE_URL = "https://huggingface.co/api/collections/"
TARGET_IDENTITIES = {
    "khipu-family": ("SZLHOLDINGS/khipu-and-receiptagent-models-6a950ff26e805e8ff7f30400", "Khipu & ReceiptAgent Models", "CANDIDATE_NAVIGATION"),
    "model-showcase": ("SZLHOLDINGS/szl-flagship-models-6a9315c1c853da528726dd8d", "SZL Flagship Models", "NO_MODEL_PROMOTED"),
    "software-kernels": ("SZLHOLDINGS/szl-kernels-software-6a9315c19d509bb9214d3e64", "SZL Kernels (SOFTWARE)", "SOFTWARE_NAVIGATION"),
}
WEIGHT_ANCHORS = {"SZL-Khipu-1.5B", "SZL-Forge-1.5B-ReceiptAgent", "SZL-Khipu-1.5B-GGUF"}
WEIGHT_OPTIONAL = {"szl-receiptagent-qwen35-0.8b-v2", "szl-receiptagent-qwen35-0.8b-v3", "A11OY-MINI"}
SOFTWARE_OPTIONAL = {
    "szl-lambda-gate", "szl-governed-norm", "szl-formulas", "szl-invariants",
    "szl-blocked", "szl-govsign", "szl-provctl", "szl-ouroboros", "szl-maskmod",
    "szl-block-kv", "governed-inference-meter", "szl-receipt-attn", "YARQA-ATTN",
}
SHOWCASE_DESCRIPTION = "No model is promoted. See https://holdings.a-11-oy.com/frontier/ for public artifacts and their evidence. Lambda uniqueness remains Conjecture 1."
SOFTWARE_DESCRIPTION = "Software kernels. Not LoRA-trained models. Source on GitHub; Hub is the mirror."
REPO_ID = re.compile(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
OBJECT_ID = re.compile(r"[0-9a-f]{24}\Z")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
TRANSPORT_ERRORS = {"HTTP_ERROR", "REDIRECT_REJECTED", "NETWORK_ERROR", "TIMEOUT", "INPUT_TOO_LARGE", "INVALID_JSON"}


class ContractError(ValueError):
    """A safe, fixed diagnostic code; never embed remote bodies or headers."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def parse_json_bytes(raw: bytes, max_bytes: int = MAX_BODY_BYTES):
    require(type(raw) is bytes, "INVALID_JSON")
    require(len(raw) <= max_bytes, "INPUT_TOO_LARGE")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "JSON_DUPLICATE_KEY")
            obj[key] = value
        return obj

    def reject_constant(_value):
        raise ContractError("INVALID_JSON")

    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant)
        pending = [(obj, 0)]
        visited = 0
        while pending:
            value, depth = pending.pop()
            visited += 1
            require(depth <= 32 and visited <= 100000, "INVALID_JSON")
            if type(value) is dict:
                pending.extend((child, depth + 1) for child in value.values())
            elif type(value) is list:
                pending.extend((child, depth + 1) for child in value)
            elif type(value) is float:
                require(math.isfinite(value), "INVALID_JSON")
        return obj
    except ContractError:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise ContractError("INVALID_JSON") from None


def owned(names):
    return {"SZLHOLDINGS/" + name for name in names}


def validate_policy(obj) -> dict:
    """Validate the reviewed fixed scope, not a general provider policy engine."""
    root_keys = {"schema", "owner", "targets", *BOUNDARIES}
    target_keys = {"id", "slug", "title", "classification", "required_members", "optional_members", "forbidden_members", "description_exact", "member_classifications", "source_refs"}
    require(type(obj) is dict and set(obj) == root_keys, "INVALID_POLICY")
    require(obj["schema"] == "szl.hf.collection-navigation-policy/v1", "INVALID_POLICY")
    require(type(obj["owner"]) is dict and obj["owner"] == OWNER, "INVALID_POLICY")
    for key, expected in BOUNDARIES.items():
        require(type(obj[key]) is type(expected) and obj[key] == expected, "INVALID_POLICY")
    targets = obj["targets"]
    require(type(targets) is list and len(targets) == 3, "INVALID_POLICY")
    seen = set()
    for target in targets:
        require(type(target) is dict and set(target) == target_keys, "INVALID_POLICY")
        role = target["id"]
        require(type(role) is str and role in TARGET_IDENTITIES and role not in seen, "INVALID_POLICY")
        seen.add(role)
        require(tuple(target[k] for k in ("slug", "title", "classification")) == TARGET_IDENTITIES[role], "INVALID_POLICY")
        sets = {}
        for key in ("required_members", "optional_members", "forbidden_members"):
            values = target[key]
            require(type(values) is list and len(values) <= MAX_ITEMS, "INVALID_POLICY")
            require(all(type(v) is str and REPO_ID.fullmatch(v) for v in values), "INVALID_POLICY")
            require(len(set(values)) == len(values), "INVALID_POLICY")
            sets[key] = set(values)
        required, optional, forbidden = (sets[k] for k in ("required_members", "optional_members", "forbidden_members"))
        require(not (required & optional or (required | optional) & forbidden), "INVALID_POLICY")
        if role == "khipu-family":
            expected = (owned(WEIGHT_ANCHORS), owned(WEIGHT_OPTIONAL), owned({"szl-nemo"}), None)
            classes = {member: "CANDIDATE_NAVIGATION" for member in required | optional}
        elif role == "software-kernels":
            expected = (owned({"szl-kernels"}), owned(SOFTWARE_OPTIONAL), set(), SOFTWARE_DESCRIPTION)
            classes = {member: "SOFTWARE" for member in required | optional}
            classes["SZLHOLDINGS/szl-governed-norm"] = "DEPRECATED_SOFTWARE"
        else:
            expected = (set(), set(), set(), SHOWCASE_DESCRIPTION)
            classes = {}
        require((required, optional, forbidden, target["description_exact"]) == expected, "INVALID_POLICY")
        require(type(target["member_classifications"]) is dict and target["member_classifications"] == classes, "INVALID_POLICY")
        refs = target["source_refs"]
        require(type(refs) is list and 1 <= len(refs) <= 16, "INVALID_POLICY")
        require(all(type(ref) is str and re.fullmatch(r"[A-Za-z0-9_./-]+:[1-9][0-9]{0,5}", ref) for ref in refs), "INVALID_POLICY")
    return obj


def valid_owner(obj) -> bool:
    return type(obj) is dict and all(obj.get(k) == v for k, v in {"name": OWNER["name"], "type": OWNER["type"], "_id": OWNER["id"]}.items())


def utc_timestamp(value) -> bool:
    if type(value) is not str or not UTC_TIMESTAMP.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def inspect_collection(target, body) -> tuple[list, list]:
    findings = []
    members = []
    if type(body) is not dict:
        return [{"code": "INVALID_DETAIL"}], members
    if not (valid_owner(body.get("owner")) and body.get("private") is False
            and body.get("slug") == target["slug"] and body.get("title") == target["title"]):
        findings.append({"code": "COLLECTION_IDENTITY_MISMATCH"})
    position = body.get("position")
    if not (type(position) is int and position >= 0
            and body.get("shareUrl") == "https://hf.co/collections/" + target["slug"].rsplit("-", 1)[0]):
        findings.append({"code": "INCOMPLETE_DETAIL"})
    description = body.get("description")
    if type(description) is not str or len(description) > 8192:
        findings.append({"code": "INVALID_DESCRIPTION"})
    elif target["description_exact"] is not None and description != target["description_exact"]:
        findings.append({"code": "DESCRIPTION_MISMATCH"})
    items = body.get("items")
    if type(items) is not list or len(items) > MAX_ITEMS:
        return findings + [{"code": "INVALID_ITEMS"}], members
    # A preview or paginated partial result must never stand in for full membership.
    for key in ("next", "nextPage", "cursor", "hasMore"):
        if key in body and body[key] is not None and body[key] is not False:
            findings.append({"code": "INCOMPLETE_DETAIL"})
    for key in ("totalItems", "numItems"):
        if key in body and (type(body[key]) is not int or body[key] != len(items)):
            findings.append({"code": "INCOMPLETE_DETAIL"})
    seen, object_ids = set(), set()
    for item in items:
        if type(item) is not dict:
            findings.append({"code": "INVALID_MEMBER"})
            continue
        member, item_id = item.get("id"), item.get("_id")
        if not (type(member) is str and REPO_ID.fullmatch(member)
                and type(item_id) is str and OBJECT_ID.fullmatch(item_id)
                and item.get("author") == OWNER["name"] and valid_owner(item.get("authorData"))
                and item.get("private") is False and item.get("type") == "model" and item.get("repoType") == "model"):
            findings.append({"code": "MEMBER_IDENTITY_MISMATCH"})
            continue
        if member in seen or item_id in object_ids:
            findings.append({"code": "DUPLICATE_MEMBER", "member_id": member})
        seen.add(member)
        object_ids.add(item_id)
        members.append({"id": member, "object_id": item_id, "classification": target["member_classifications"].get(member, "UNCLASSIFIED")})
        if member in target["forbidden_members"]:
            findings.append({"code": "FORBIDDEN_MEMBER", "member_id": member})
        elif member not in target["member_classifications"]:
            findings.append({"code": "UNCLASSIFIED_MEMBER", "member_id": member})
    for member in sorted(set(target["required_members"]) - seen):
        findings.append({"code": "REQUIRED_MEMBER_MISSING", "member_id": member})
    return findings, members


def receipt_metadata(mode, policy=None) -> dict:
    return {
        "schema": "szl.hf.collection-navigation-receipt/v1", "mode": mode,
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_scope": "THREE_PUBLIC_COLLECTION_DETAILS_ONLY" if mode == "live" else "UNTRUSTED_LOCAL_SNAPSHOT_ONLY",
        "policy_sha256": None if policy is None else hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def check_snapshot(policy, snapshot, mode="snapshot") -> dict:
    validate_policy(policy)
    require(mode in ("snapshot", "live"), "INVALID_MODE")
    receipt = {
        **receipt_metadata(mode, policy),
        "boundaries": dict(BOUNDARIES), "navigation_status": "HOLD", "findings": [], "targets": [],
    }
    valid_snapshot = type(snapshot) is dict and set(snapshot) == {"schema", "responses"} and snapshot.get("schema") == "szl.hf.collection-navigation-snapshot/v1"
    responses = snapshot.get("responses") if valid_snapshot else None
    if type(responses) is not list or len(responses) != 3:
        receipt["findings"].append({"code": "INVALID_SNAPSHOT"})
        responses = responses if type(responses) is list and len(responses) <= 4 else []
    allowed_urls = {BASE_URL + t["slug"] for t in policy["targets"]}
    indexed = {}
    for response in responses:
        if type(response) is not dict or type(response.get("url")) is not str or response["url"] not in allowed_urls:
            receipt["findings"].append({"code": "UNEXPECTED_RESPONSE"})
            continue
        indexed.setdefault(response["url"], []).append(response)
    for target in policy["targets"]:
        url = BASE_URL + target["slug"]
        row = {"id": target["id"], "slug": target["slug"], "classification": target["classification"], "status": "HOLD", "findings": [], "members": []}
        receipt["targets"].append(row)
        matches = indexed.get(url, [])
        if len(matches) != 1:
            row["findings"].append({"code": "RESPONSE_MISSING" if not matches else "DUPLICATE_RESPONSE"})
            continue
        response = matches[0]
        expected_keys = {"url", "method", "status", "received_at", "error" if "error" in response else "body_text"}
        status = response.get("status")
        response_ok = (set(response) == expected_keys and response.get("method") == "GET"
                       and type(status) is int and (status == 0 or 100 <= status <= 599)
                       and utc_timestamp(response.get("received_at")))
        if not response_ok:
            row["findings"].append({"code": "INVALID_RESPONSE_IDENTITY"})
            continue
        identity = {k: response[k] for k in ("url", "method", "status", "received_at")}
        row["response"] = identity
        if "error" in response:
            code = response["error"]
            row["findings"].append({"code": code if type(code) is str and code in TRANSPORT_ERRORS else "INVALID_TRANSPORT_ERROR"})
            continue
        if status != 200 or type(response.get("body_text")) is not str:
            row["findings"].append({"code": "INVALID_RESPONSE"})
            continue
        try:
            raw = response["body_text"].encode("utf-8")
            identity.update(body_bytes=len(raw), body_sha256=hashlib.sha256(raw).hexdigest())
            body = parse_json_bytes(raw)
            row["findings"], row["members"] = inspect_collection(target, body)
        except UnicodeError:
            row["findings"].append({"code": "INVALID_JSON"})
        except ContractError as exc:
            row["findings"].append({"code": exc.code})
        if not row["findings"]:
            row["status"] = "PASS"
    if not receipt["findings"] and all(row["status"] == "PASS" for row in receipt["targets"]):
        receipt["navigation_status"] = "PASS"
    return receipt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ContractError("REDIRECT_REJECTED")


def fetch_live(policy) -> dict:
    """Three fixed GETs, socket timeout and deadline admission checks.

    This does not promise hard wall-clock cancellation of DNS or a blocked I/O
    call; a response read after its deadline is rejected, including final EOF.
    No credentials, SDK cache, retries, or redirects are used.
    """
    validate_policy(policy)
    opener = urllib.request.build_opener(NoRedirect())
    responses = []
    for target in policy["targets"]:
        url = BASE_URL + target["slug"]
        row = {"url": url, "method": "GET", "status": 0, "received_at": ""}
        request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "szl-collection-navigation-observer/1"})
        try:
            deadline = time.monotonic() + TIMEOUT_SECONDS
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                row["status"] = response.status
                require(response.geturl() == url, "REDIRECT_REJECTED")
                require(response.status == 200, "HTTP_ERROR")
                raw = bytearray()
                while True:
                    require(time.monotonic() <= deadline, "TIMEOUT")
                    chunk = response.read1(min(65536, MAX_BODY_BYTES + 1 - len(raw)))
                    require(time.monotonic() <= deadline, "TIMEOUT")
                    raw.extend(chunk)
                    require(len(raw) <= MAX_BODY_BYTES, "INPUT_TOO_LARGE")
                    if not chunk:
                        break
                row["body_text"] = bytes(raw).decode("utf-8")
        except urllib.error.HTTPError as exc:
            row["status"] = exc.code
            row["error"] = "REDIRECT_REJECTED" if 300 <= exc.code <= 399 else "HTTP_ERROR"
        except (TimeoutError, socket.timeout):
            row["error"] = "TIMEOUT"
        except (urllib.error.URLError, OSError):
            row["error"] = "NETWORK_ERROR"
        except UnicodeError:
            row["error"] = "INVALID_JSON"
        except ContractError as exc:
            row["error"] = exc.code
        row["received_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        responses.append(row)
    return {"schema": "szl.hf.collection-navigation-snapshot/v1", "responses": responses}


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    require(len(raw) <= limit, "INPUT_TOO_LARGE")
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Read exactly three fixed public collection details with GET")
    mode.add_argument("--snapshot", type=Path, help="Validate a local observation; does not contact the provider")
    parser.add_argument("--report", type=Path, help="Write the safe receipt to this local file")
    args = parser.parse_args(argv)
    selected_mode = "live" if args.live else "snapshot"
    policy = None
    try:
        policy = validate_policy(parse_json_bytes(read_bounded(POLICY_PATH, MAX_POLICY_BYTES), MAX_POLICY_BYTES))
        snapshot = fetch_live(policy) if args.live else parse_json_bytes(read_bounded(args.snapshot, MAX_SNAPSHOT_BYTES), MAX_SNAPSHOT_BYTES)
        receipt = check_snapshot(policy, snapshot, mode=selected_mode)
    except (ContractError, OSError) as exc:
        receipt = {**receipt_metadata(selected_mode, policy), "navigation_status": "HOLD", "boundaries": dict(BOUNDARIES), "findings": [{"code": exc.code if isinstance(exc, ContractError) else "LOCAL_IO_ERROR"}], "targets": []}
    output = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.report:
        try:
            args.report.write_text(output, encoding="utf-8")
        except OSError:
            receipt["navigation_status"] = "HOLD"
            receipt["findings"].append({"code": "REPORT_WRITE_ERROR"})
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 2
    print(output, end="")
    return 0 if receipt["navigation_status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
