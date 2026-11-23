#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Local stand-in for the a11oy command-centre journey.

The happy path returns a real completed answer and a receipt whose
``source_revision`` equals ``GET /api/build-info``. ``FIXTURE_GAP=omit-evidence-build-id``
keeps the UI and build-info revision and drops it from the receipt, which is
the same-build failure this harness is meant to catch.

This process never dials a production host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
BUILD_ID = "9467fa988ff63c919954adbd8e23e930412321b5"
ANSWER = (
    "The public status of this build is an observed command-centre turn "
    "with a persisted outcome receipt."
)
OPERATOR = "fixture-operator"
FORBIDDEN = "forbidden-fixture"
PAYMENT = "payment-fixture"
OPENAPI = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "command-centre.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "command-centre.js").read_text(encoding="utf-8")
STYLE = (ROOT / "command-centre.css").read_text(encoding="utf-8")


def gap_enabled() -> bool:
    return os.environ.get("FIXTURE_GAP", "").strip() == "omit-evidence-build-id"


def build_info() -> dict:
    return {
        "status": "OBSERVED",
        "service": "a11oy",
        "build": {
            "state": "OBSERVED",
            "revision": BUILD_ID,
            "revision_source": "env:SZL_GIT_SHA",
        },
        "runtime": {"python": "fixture", "platform": "local"},
        "receipt_minted": False,
    }


def health() -> dict:
    return {
        "ready": True,
        "model": "grok-4.7",
        "inference_verified": False,
        "blockers": [],
        "provider": "xai",
        "source_revision": BUILD_ID,
        "energy": {"label": "UNAVAILABLE", "joules": None},
    }


def _error(code: str, state: str) -> dict:
    return {"state": state, "code": code, "retry_safe": False}


def turn(body: bytes, token: str) -> tuple[int, dict]:
    if token == FORBIDDEN:
        return 403, _error("AUTH_FORBIDDEN", "DENIED")
    if token == PAYMENT:
        return 402, _error("PROVIDER_HTTP_402", "UNAVAILABLE")
    if token != OPERATOR:
        return 401, _error("AUTH_REQUIRED", "DENIED")
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 422, _error("INVALID_REQUEST", "DENIED")
    prompt = document.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return 422, _error("INVALID_REQUEST", "DENIED")
    request_id = str(uuid.uuid4())
    payload = {
        "schema": "a11oy.atelier.single-turn.receipt/v1",
        "phase": "OUTCOME",
        "state": "COMPLETED",
        "request_id": request_id,
        "client_request_id": document.get("client_request_id"),
        "provider": "xai",
        "model": document.get("model") or "grok-4.7",
    }
    if not gap_enabled():
        payload["source_revision"] = BUILD_ID
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return 200, {
        "state": "COMPLETED",
        "answer": ANSWER,
        "model": payload["model"],
        "request_id": request_id,
        "receipt": {
            "payload": payload,
            "digest": digest,
            "persisted": True,
            "signature_verified": True,
            "chain_scope": "SINGLE_PROCESS_RETAINED_METADATA_CHAIN",
        },
        "dsse": {
            "signed": True,
            "payloadType": "application/vnd.szl.atelier-turn+json",
            "payload": "fixture",
            "signatures": [{"sig": "fixture-not-a-production-signature"}],
        },
        "energy": {"label": "UNAVAILABLE", "joules": None},
        "retry_safe": False,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, document: dict) -> None:
        self._send(status, json.dumps(document).encode("utf-8"), "application/json")

    def _bearer(self) -> str:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return ""
        return header[len(prefix):].strip()

    def do_GET(self) -> None:  # noqa: N802
        self._route(b"")

    def do_HEAD(self) -> None:  # noqa: N802
        self._route(b"")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > 140_000:
            self._json(413, _error("REQUEST_TOO_LARGE", "DENIED"))
            return
        self._route(self.rfile.read(length))

    def _route(self, body: bytes) -> None:
        path = urlsplit(self.path).path
        if path == "/api/livez":
            self._json(200, {
                "status": "PROCESS_ALIVE",
                "fixture": "a11oy-release-harness",
                "production_ready": False,
                "receipt_minted": False,
            })
            return
        if path == "/api/build-info":
            self._json(200, build_info())
            return
        if path == "/api/a11oy/v1/atelier/health":
            self._json(200, health())
            return
        if path in {"/api/a11oy/openapi.json", "/openapi.json"}:
            self._json(200, OPENAPI)
            return
        if path == "/command-centre":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/command-centre/app.js":
            self._send(200, SCRIPT.encode("utf-8"), "text/javascript; charset=utf-8")
            return
        if path == "/command-centre/style.css":
            self._send(200, STYLE.encode("utf-8"), "text/css; charset=utf-8")
            return
        if path == "/api/a11oy/v1/atelier/turn" and self.command == "POST":
            status, document = turn(body, self._bearer())
            self._json(status, document)
            return
        self._json(404, {"status": "NOT_FOUND", "path": path})


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"a11oy fixture http://127.0.0.1:{port} gap={gap_enabled()}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    serve(args.port)


if __name__ == "__main__":
    main()
