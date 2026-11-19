#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Status and OpenAPI schema checks for the a11oy critical-journey API.

A missing spec, or a spec that does not document a route, is UNKNOWN.
UNKNOWN does not pass the schema and does not fail the run. A status
mismatch, or a body that contradicts a schema the spec actually declares,
fails the run. Production hosts are refused before the first request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Callable, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "canary"))

import compare  # noqa: E402

ROUTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.json")
OpenResult = tuple[int, dict, bytes]


class SchemaMismatch(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_routes(path: str = ROUTES_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def validate(schema: dict, value) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise SchemaMismatch("expected object")
        for key in schema.get("required", []):
            if key not in value:
                raise SchemaMismatch(f"missing required property {key}")
        properties = schema.get("properties") or {}
        for key, child in properties.items():
            if key in value:
                validate(child, value[key])
        return
    if expected == "string":
        if not isinstance(value, str):
            raise SchemaMismatch("expected string")
        return
    if expected == "boolean":
        if not isinstance(value, bool):
            raise SchemaMismatch("expected boolean")
        return
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaMismatch("expected integer")
        return
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaMismatch("expected number")
        return
    if expected == "array":
        if not isinstance(value, list):
            raise SchemaMismatch("expected array")
        return
    raise SchemaMismatch(f"unsupported schema type {expected!r}")


def response_schema(spec: dict, path: str, method: str, status: int) -> Optional[dict]:
    path_item = (spec.get("paths") or {}).get(path)
    if not isinstance(path_item, dict):
        return None
    operation = path_item.get(method.lower())
    if not isinstance(operation, dict):
        return None
    response = (operation.get("responses") or {}).get(str(status))
    if not isinstance(response, dict):
        return None
    content = (response.get("content") or {}).get("application/json") or {}
    schema = content.get("schema")
    return schema if isinstance(schema, dict) else None


def urllib_opener(method: str, url: str, headers: dict, body: Optional[bytes]) -> OpenResult:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read(1_048_576)
            return int(response.status), dict(response.headers.items()), payload
    except urllib.error.HTTPError as exc:
        payload = exc.read(1_048_576)
        return int(exc.code), dict(exc.headers.items()), payload


def _json_body(payload: bytes, headers: dict):
    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = value
            break
    if "json" not in content_type.lower():
        return None
    return json.loads(payload.decode("utf-8"))


def _auth_headers(auth: str) -> dict:
    headers = {"Accept": "application/json"}
    if auth == "none":
        return headers
    prefix = "bearer:"
    if not auth.startswith(prefix) or not auth[len(prefix):]:
        raise compare.Refusal(f"unsupported auth marker {auth}")
    headers["Authorization"] = f"Bearer {auth[len(prefix):]}"
    return headers


def run_checks(
    base_url: str,
    *,
    staging: bool,
    target_class: Optional[str],
    opener: Callable[..., OpenResult],
    document: Optional[dict] = None,
) -> dict:
    compare.allow_target(base_url, staging=staging, target_class=target_class)
    document = document if document is not None else load_routes()
    base = base_url.rstrip("/")
    live_status, live_headers, live_body = opener("GET", base + "/api/livez", {"Accept": "application/json"}, None)
    live_json = None
    if live_status == 200:
        try:
            live_json = _json_body(live_body, live_headers)
        except json.JSONDecodeError:
            live_json = None
    is_fixture = isinstance(live_json, dict) and live_json.get("fixture") == "a11oy-release-harness"

    spec = None
    spec_state = "UNKNOWN"
    spec_status, spec_headers, spec_body = opener(
        "GET", base + "/api/a11oy/openapi.json", {"Accept": "application/json"}, None
    )
    if spec_status == 200:
        try:
            candidate = _json_body(spec_body, spec_headers)
        except json.JSONDecodeError:
            candidate = None
        if isinstance(candidate, dict) and str(candidate.get("openapi", "")).startswith("3."):
            spec = candidate
            spec_state = "PRESENT"
        else:
            spec_state = "UNKNOWN"
    results = []
    failed = False
    for route in document["routes"]:
        profile = route.get("profile", "public")
        if profile == "fixture-auth" and not is_fixture:
            results.append({
                "id": route["id"],
                "status_result": "UNKNOWN",
                "schema_result": "UNKNOWN",
                "detail": "fixture auth probe skipped; live credential denial was not provoked",
            })
            continue
        headers = _auth_headers(route.get("auth", "none"))
        body = None
        if "body" in route:
            body = json.dumps(route["body"]).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, response_headers, payload = opener(
            route["method"], base + route["path"], headers, body
        )
        expected = route["expect"]
        status_result = "PASS" if status in expected else "FAIL"
        if status_result == "FAIL":
            failed = True
        schema_result = "UNKNOWN"
        detail = f"HTTP {status}, expected {expected}"
        if spec is None:
            schema_result = "UNKNOWN"
            detail += "; OpenAPI UNKNOWN"
        elif route["path"] not in (spec.get("paths") or {}):
            schema_result = "UNKNOWN"
            detail += "; path absent from OpenAPI"
        else:
            schema = response_schema(spec, route["path"], route["method"], status)
            if schema is None:
                schema_result = "UNKNOWN"
                detail += "; response schema absent"
            else:
                try:
                    parsed = _json_body(payload, response_headers)
                    validate(schema, parsed)
                    schema_result = "PASS"
                    detail += "; schema matched"
                except (SchemaMismatch, json.JSONDecodeError) as exc:
                    schema_result = "FAIL"
                    failed = True
                    detail += f"; schema mismatch: {exc}"
        results.append({
            "id": route["id"],
            "status_result": status_result,
            "schema_result": schema_result,
            "detail": detail,
        })
    return {
        "fixture": is_fixture,
        "openapi": spec_state,
        "failed": failed,
        "results": results,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--staging", action="store_true")
    parser.add_argument("--target-class", choices=("staging",))
    args = parser.parse_args(argv)
    try:
        report = run_checks(
            args.base_url,
            staging=args.staging,
            target_class=args.target_class,
            opener=urllib_opener,
        )
    except compare.Refusal as exc:
        print(f"refusing: {exc.reason}", flush=True)
        return 2
    print(f"openapi={report['openapi']} fixture={report['fixture']}")
    for row in report["results"]:
        print(
            f"{row['id']} status={row['status_result']} schema={row['schema_result']} {row['detail']}"
        )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
