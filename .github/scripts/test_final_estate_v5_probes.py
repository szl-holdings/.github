#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import unittest
from typing import Any

from final_estate_reconciliation_v5 import issue_body
from final_estate_v5_core import PROBES, REPORT_MARKER, REPORT_SCHEMA, https_origin
from final_estate_v5_probes import safe_probe

HERE = pathlib.Path(__file__).resolve().parent


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        url: str,
        content_type: str,
        payload: Any = None,
        body: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self.headers = {"content-type": content_type}
        self._payload = payload
        self.content = body if body is not None else (
            json.dumps(payload, sort_keys=True).encode("utf-8")
            if payload is not None
            else b"ok"
        )

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class FakeSession:
    def __init__(self, *, head: FakeResponse, get: FakeResponse) -> None:
        self._head = head
        self._get = get
        self.headers: dict[str, str] = {}

    def head(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        return self._head

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        return self._get


class FinalEstateProbeV5Tests(unittest.TestCase):
    def test_get_only_api_accepts_observed_head_405(self) -> None:
        spec = PROBES["a11oy_livez"]
        session = FakeSession(
            head=FakeResponse(
                status_code=405,
                url=spec.url,
                content_type="application/json",
                payload={"detail": "Method Not Allowed"},
            ),
            get=FakeResponse(
                status_code=200,
                url=spec.url,
                content_type="application/json",
                payload={
                    "status": "LIVE",
                    "process": {"pid": 1},
                    "scope": "process liveness only",
                    "receipt_minted": False,
                },
            ),
        )
        gate = safe_probe("a11oy_livez", spec, None, session=session)
        self.assertTrue(gate.ok)
        self.assertFalse(gate.evidence["head_required"])

    def test_document_probe_requires_head_support(self) -> None:
        spec = PROBES["a11oy_product"]
        session = FakeSession(
            head=FakeResponse(
                status_code=405,
                url=spec.url,
                content_type="text/html",
                body=b"method not allowed",
            ),
            get=FakeResponse(
                status_code=200,
                url=spec.url,
                content_type="text/html; charset=utf-8",
                body=b"<html>ok</html>",
            ),
        )
        self.assertFalse(safe_probe("a11oy_product", spec, None, session=session).ok)

    def test_build_info_must_bind_current_protected_main(self) -> None:
        source_sha = "a" * 40
        spec = PROBES["a11oy_build_info"]
        payload = {
            "status": "OBSERVED",
            "service": "a11oy",
            "build": {"state": "OBSERVED", "revision": source_sha},
            "runtime": {"python": "3.12"},
            "receipt_minted": False,
        }
        session = FakeSession(
            head=FakeResponse(
                status_code=405,
                url=spec.url,
                content_type="application/json",
                payload={"detail": "Method Not Allowed"},
            ),
            get=FakeResponse(
                status_code=200,
                url=spec.url,
                content_type="application/json",
                payload=payload,
            ),
        )
        self.assertTrue(safe_probe("a11oy_build_info", spec, source_sha, session=session).ok)
        payload["build"]["revision"] = "b" * 40
        self.assertFalse(safe_probe("a11oy_build_info", spec, source_sha, session=session).ok)

    def test_readiness_query_url_has_valid_https_origin(self) -> None:
        self.assertIsNotNone(https_origin(PROBES["a11oy_readiness"].url))

    def test_real_3d_routes_replace_dead_holographic_filename(self) -> None:
        urls = {spec.url for spec in PROBES.values()}
        self.assertFalse(any(url.endswith("/holographic.html") for url in urls))
        self.assertIn("https://szlholdings-a11oy.hf.space/static/3d/estate.html", urls)
        self.assertIn("https://szlholdings-a11oy.hf.space/static/3d/brain.html", urls)

    def test_issue_body_is_machine_readable_and_marks_decommission(self) -> None:
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": "2026-07-22T00:00:00+00:00",
            "status": "NOT_VERIFIED",
            "operational_verified": False,
            "gates": [
                {"name": "example", "ok": False, "detail": "not ready", "evidence": {}}
            ],
            "summary": {"ok": 0, "error": 1, "total": 1},
            "boundaries": [],
            "excluded_lanes": [],
        }
        body = issue_body(report, "https://github.com/example/actions/runs/1")
        self.assertIn(REPORT_MARKER, body)
        self.assertIn("DECOMMISSIONED", body)
        self.assertIn('"schema": "szl.final-estate-reconciliation/v5"', body)

    def test_source_contains_no_replit_runtime_gate_or_runtime_mutations(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in HERE.glob("final_estate*v5*.py")
        )
        self.assertNotIn("validate_replit", source)
        self.assertNotIn("REPL_ID", source)
        for forbidden in (
            "delete_repo(",
            "create_repo(",
            "duplicate_repo(",
            "update_repo_settings(",
            "restart_space(",
            "upload_file(",
            "upload_folder(",
            "CommitOperationCopy",
        ):
            self.assertNotIn(forbidden, source)

    def test_workflow_security_boundary_is_split(self) -> None:
        workflows = HERE.parent / "workflows"
        privileged = (workflows / "final-estate-reconciliation-v5.yml").read_text(
            encoding="utf-8"
        )
        pull_request = (
            workflows / "final-estate-reconciliation-v5-pr.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("pull_request:", privileged)
        self.assertIn("issues: write", privileged)
        self.assertNotIn("secrets.", privileged)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", privileged)
        self.assertIn("pull_request:", pull_request)
        self.assertNotIn("secrets.", pull_request)
        self.assertNotIn("issues: write", pull_request)
        self.assertIn("permissions:\n  contents: read", pull_request)


if __name__ == "__main__":
    unittest.main(verbosity=2)
