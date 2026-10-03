#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for the Living Constellation operator."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "hf_living_constellation_operator.py"
SPEC = importlib.util.spec_from_file_location("hf_living_constellation_operator", MODULE_PATH)
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = operator
SPEC.loader.exec_module(operator)


def test_stage_normalization_and_boundaries() -> None:
    assert operator.normalize_stage("running") == "RUNNING"
    assert operator.normalize_stage("build-error") == "BUILD_ERROR"
    assert "RUNNING" in operator.HEALTHY_STAGES
    assert "PAUSED" in operator.RESTART_ELIGIBLE_STAGES
    assert "BUILDING" in operator.TRANSITIONAL_STAGES
    assert operator.HEALTHY_STAGES.isdisjoint(operator.RESTART_ELIGIBLE_STAGES)


def test_parse_space_keeps_only_canonical_org_identity() -> None:
    row = {
        "id": "SZLHOLDINGS/Lyte-Lattice",
        "private": False,
        "sdk": "docker",
        "runtime": {"stage": "RUNNING"},
    }
    parsed = operator.parse_space(row)
    assert parsed is not None
    assert parsed.repo_id == "SZLHOLDINGS/Lyte-Lattice"
    assert parsed.slug == "Lyte-Lattice"
    assert parsed.stage == "RUNNING"
    assert parsed.host_candidates[-1] == "https://szlholdings-lyte-lattice.hf.space/"
    assert operator.parse_space({**row, "id": "another-org/Lyte-Lattice"}) is None


def test_static_space_prefers_static_host_without_removing_dynamic_fallback() -> None:
    hosts = operator.host_candidates("SZLHOLDINGS/proof", "static", {})
    assert hosts == (
        "https://szlholdings-proof.static.hf.space/",
        "https://szlholdings-proof.hf.space/",
    )


def test_restart_uses_only_restart_endpoint_and_no_payload() -> None:
    with mock.patch.object(operator, "_request", return_value=(200, b"{}", {})) as request:
        assert operator.restart_space("SZLHOLDINGS/lyte", "hf_secret") == 200
    request.assert_called_once_with(
        "POST",
        "https://huggingface.co/api/spaces/SZLHOLDINGS/lyte/restart",
        token="hf_secret",
    )


def test_operate_one_does_not_restart_healthy_runtime() -> None:
    space = operator.Space(
        repo_id="SZLHOLDINGS/lyte",
        slug="lyte",
        sdk="docker",
        stage="RUNNING",
        private=False,
        host_candidates=("https://szlholdings-lyte.hf.space/",),
    )
    with mock.patch.object(operator, "restart_space") as restart, mock.patch.object(
        operator, "probe_runtime", return_value=(space.host_candidates[0], 200, [])
    ):
        result = operator.operate_one(space, token="hf_secret", repair=True, wait_seconds=30)
    restart.assert_not_called()
    assert result.operational is True
    assert result.state == "OPERATIONAL"


def test_operate_one_restarts_only_eligible_runtime() -> None:
    space = operator.Space(
        repo_id="SZLHOLDINGS/lyte",
        slug="lyte",
        sdk="docker",
        stage="PAUSED",
        private=False,
        host_candidates=("https://szlholdings-lyte.hf.space/",),
    )
    with mock.patch.object(operator, "restart_space", return_value=200) as restart, mock.patch.object(
        operator, "wait_for_terminal", return_value=("RUNNING", space.host_candidates, 2)
    ), mock.patch.object(
        operator, "probe_runtime", return_value=(space.host_candidates[0], 200, [])
    ):
        result = operator.operate_one(space, token="hf_secret", repair=True, wait_seconds=30)
    restart.assert_called_once_with(space.repo_id, "hf_secret")
    assert result.restart_attempted is True
    assert result.operational is True


def test_report_redacts_token_shapes_and_records_no_token_value() -> None:
    payload = {"error": "request failed with hf_abcdefghijklmnopqrstuvwxyz", "token_value_recorded": False}
    safe = operator.redact(payload)
    assert safe["error"].endswith("[REDACTED]")
    assert "hf_" not in json.dumps(safe)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "report.json"
        operator.write_report(path, payload)
        text = path.read_text(encoding="utf-8")
        assert "hf_" not in text
        assert '"token_value_recorded": false' in text


def test_token_precedence_is_explicit() -> None:
    with mock.patch.dict(
        os.environ,
        {"HF_TOKEN": "secondary", "HF_ORG_TOKEN": "primary"},
        clear=True,
    ):
        assert operator.token_from_environment() == ("primary", "HF_ORG_TOKEN")


def test_source_contains_no_hardware_or_repository_mutation_endpoint() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "/hardware",
        "request_space_hardware",
        "duplicate_space",
        "create_repo",
        "delete_repo",
        "upload_file",
        "create_commit",
        "change_discussion_status",
    )
    for fragment in forbidden:
        assert fragment not in text


def test_provider_app_starting_stage_is_transitional() -> None:
    assert "RUNNING_APP_STARTING" in operator.TRANSITIONAL_STAGES
    assert "RUNNING_CONTAINER_STARTING" in operator.TRANSITIONAL_STAGES
    assert "UNAVAILABLE" not in operator.RESTART_ELIGIBLE_STAGES
    assert "UNKNOWN" not in operator.RESTART_ELIGIBLE_STAGES


def test_static_space_is_probed_without_restart() -> None:
    space = operator.Space(
        repo_id="SZLHOLDINGS/proof",
        slug="proof",
        sdk="static",
        stage="UNAVAILABLE",
        private=False,
        host_candidates=("https://szlholdings-proof.static.hf.space/",),
    )
    detail = operator.Space(
        repo_id=space.repo_id,
        slug=space.slug,
        sdk="static",
        stage="RUNNING",
        private=False,
        host_candidates=space.host_candidates,
    )
    with mock.patch.object(operator, "fetch_space", return_value=detail), mock.patch.object(
        operator, "restart_space"
    ) as restart, mock.patch.object(
        operator, "probe_runtime", return_value=(space.host_candidates[0], 200, [])
    ):
        result = operator.operate_one(space, token="hf_secret", repair=True, wait_seconds=30)
    restart.assert_not_called()
    assert result.operational is True
    assert result.state == "OPERATIONAL"


def test_unknown_inventory_stage_resolves_detail_before_mutation() -> None:
    space = operator.Space(
        repo_id="SZLHOLDINGS/lyte",
        slug="lyte",
        sdk="docker",
        stage="UNAVAILABLE",
        private=False,
        host_candidates=("https://szlholdings-lyte.hf.space/",),
    )
    detail = operator.Space(
        repo_id=space.repo_id,
        slug=space.slug,
        sdk="docker",
        stage="RUNNING",
        private=False,
        host_candidates=space.host_candidates,
    )
    with mock.patch.object(operator, "fetch_space", return_value=detail) as fetch, mock.patch.object(
        operator, "restart_space"
    ) as restart, mock.patch.object(
        operator, "probe_runtime", return_value=(space.host_candidates[0], 200, [])
    ):
        result = operator.operate_one(space, token="hf_secret", repair=True, wait_seconds=30)
    fetch.assert_called_once_with(space.repo_id, "hf_secret")
    restart.assert_not_called()
    assert result.operational is True


def test_running_app_starting_waits_instead_of_restarting() -> None:
    space = operator.Space(
        repo_id="SZLHOLDINGS/lyte",
        slug="lyte",
        sdk="docker",
        stage="RUNNING_APP_STARTING",
        private=False,
        host_candidates=("https://szlholdings-lyte.hf.space/",),
    )
    with mock.patch.object(operator, "restart_space") as restart, mock.patch.object(
        operator, "wait_for_terminal", return_value=("RUNNING", space.host_candidates, 5)
    ) as wait, mock.patch.object(
        operator, "probe_runtime", return_value=(space.host_candidates[0], 200, [])
    ):
        result = operator.operate_one(space, token="hf_secret", repair=True, wait_seconds=540)
    restart.assert_not_called()
    wait.assert_called_once()
    assert result.polls == 5
    assert result.operational is True


def test_gdw_readiness_requires_a_valid_ready_response() -> None:
    host = "https://szlholdings-gdw-frontier.hf.space/"
    ready_url = host + "readyz"
    cases = (
        (200, b'{"status":"ready","service":"gdw"}', "application/json", True),
        (200, b'{"status":"not_ready","service":"gdw"}', "application/json", False),
        (200, b'{"status":"ready","service":"other"}', "application/json", False),
        (200, b"<html>login</html>", "text/html", False),
        (200, b"not JSON", "application/json", False),
        (401, b'{"detail":"authentication required"}', "application/json", False),
    )
    for status, body, content_type, expected in cases:
        with mock.patch.object(
            operator,
            "_request",
            return_value=(status, body, {"Content-Type": content_type}),
        ) as request:
            url, observed_status, blockers = operator.probe_runtime(
                (host,), repo_id="SZLHOLDINGS/gdw-frontier"
            )
        request.assert_called_once_with("GET", ready_url, timeout=25.0)
        assert (url is not None and observed_status == 200) is expected
        assert bool(blockers) is (not expected)


def test_gdw_probe_is_selected_by_canonical_space_identity() -> None:
    host = "https://szlholdings-gdw-frontier.hf.space/"
    space = operator.Space(
        repo_id="SZLHOLDINGS/gdw-frontier",
        slug="gdw-frontier",
        sdk="docker",
        stage="RUNNING",
        private=False,
        host_candidates=(host,),
    )
    with mock.patch.object(
        operator,
        "_request",
        return_value=(
            200,
            b'{"status":"ready","service":"gdw"}',
            {"Content-Type": "application/json"},
        ),
    ) as request:
        result = operator.operate_one(space, token=None, repair=False, wait_seconds=30)
    request.assert_called_once_with("GET", host + "readyz", timeout=25.0)
    assert result.operational is True
    assert result.runtime_url == host + "readyz"

    with mock.patch.object(
        operator,
        "_request",
        return_value=(
            200,
            b'{"status":"ready","service":"gdw"}',
            {"Content-Type": "application/json"},
        ),
    ) as request:
        url, _, blockers = operator.probe_runtime((host,), repo_id="SZLHOLDINGS/other")
    request.assert_called_once_with("GET", host, timeout=25.0)
    assert url is None
    assert blockers


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
