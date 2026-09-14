# SPDX-License-Identifier: Apache-2.0
"""Offline adversarial artifact admission tests; no production or provider calls."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("receipt_guard", ROOT / ".github/scripts/frontier_receipt_check.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
SHA = "a" * 40
NOW = datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)
REPO = "szl-holdings/fixture"


@pytest.fixture(autouse=True)
def no_network():
    with mock.patch.object(socket, "socket", side_effect=AssertionError("LIVE_NETWORK_FORBIDDEN")):
        yield


def fixture():
    return {"schema": "szl.frontier-issue-operator/v1", "status": "OBSERVATION_COMPLETE",
        "mode": "PUBLIC_OBSERVATION", "organization": "szl-holdings", "source_revision": SHA,
        "started_at": "2026-09-14T01:59:00Z", "finished_at": "2026-09-14T02:00:00+00:00",
        "token_value_recorded": False, "coverage": dict(m.COVERAGE), "pull_requests": [], "issues": [],
        "promotion": {"state": "NOT_REQUESTED"}, "command_center": "NOT_REQUESTED", "error_code": None,
        "summary": {"observed_pull_requests": 0, "observed_issues": 0, "merged_pull_requests": 0,
            "closed_exact_duplicates": 0, "changed_issue_labels": 0, "pull_request_errors": 0,
            "issue_errors": 0, "observation_failed": False, "classification_counts": {}}}


def populated():
    value = fixture()
    value["pull_requests"] = [{"repository": REPO, "number": 7, "action": "BLOCKED", "head_sha": "b" * 40,
        "blockers": ["draft"], "checks": {"passed": 2, "failed": 0, "active": 0},
        "url": f"https://github.com/{REPO}/pull/7"}]
    value["issues"] = [{"repository": REPO, "number": 8, "action": "CLASSIFICATION_PROPOSED",
        "classification": "estate:backlog", "possible_duplicate_of": None,
        "url": f"https://github.com/{REPO}/issues/8"}]
    value["summary"].update(observed_pull_requests=1, observed_issues=1,
                            classification_counts={"estate:backlog": 1})
    return value


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode()


def metadata(repo):
    return {"full_name": repo, "id": 19, "private": False, "visibility": "public", "archived": False}


def put(value, path, replacement):
    cursor = value
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement


@pytest.mark.parametrize("value", [fixture(), populated()])
def test_valid_bounded_projection(value):
    parsed, repositories = m.validate(raw(value), SHA, now=NOW)
    assert parsed == value
    assert repositories == ([REPO] if value["issues"] else [])


@pytest.mark.parametrize("path,replacement", [
    (("schema",), "another"), (("organization",), "other"), (("source_revision",), "c" * 40),
    (("token_value_recorded",), 0), (("mode",), "APPLY_ALL"), (("status",), "ALL_OPERATIONAL"),
    (("coverage", "complete_organization"), True), (("coverage", "complete_organization"), 0),
    (("coverage", "scope"), "whole-estate"), (("coverage", "private_repositories"), 0),
    (("coverage", "security_alerts"), "CLEAR"), (("coverage", "atomic_snapshot"), True),
    (("error_code",), "opaque-test-secret"), (("error_code",), []),
    (("command_center",), "http://fixture.invalid/opaque-test-secret"),
    (("promotion", "state"), "MERGED"), (("promotion", "state"), "QUEUED_EXACT_HEAD_OBSERVED"),
    (("summary", "merged_pull_requests"), 1), (("summary", "closed_exact_duplicates"), 1),
    (("summary", "changed_issue_labels"), 1), (("summary", "observed_issues"), 0),
    (("summary", "observed_pull_requests"), True), (("summary", "issue_errors"), -1),
    (("summary", "observation_failed"), 0), (("summary", "classification_counts"), {}),
    (("pull_requests", 0, "number"), True), (("pull_requests", 0, "repository"), "someone/fixture"),
    (("pull_requests", 0, "repository"), "szl-holdings/.."),
    (("pull_requests", 0, "head_sha"), "main"), (("pull_requests", 0, "blockers"), ["opaque-test-secret"]),
    (("pull_requests", 0, "checks", "passed"), True), (("pull_requests", 0, "action"), "MERGED"),
    (("pull_requests", 0, "url"), "https://fixture.invalid/opaque-test-secret"),
    (("issues", 0, "classification"), "opaque-test-secret"), (("issues", 0, "classification"), {}),
    (("issues", 0, "possible_duplicate_of"), 8), (("issues", 0, "possible_duplicate_of"), True),
    (("issues", 0, "action"), "CLOSED_EXACT_DUPLICATE"),
    (("started_at",), "2026-09-14T02:00:01Z"), (("finished_at",), "2026-09-14T04:00:00Z"),
    (("started_at",), "2026-09-14T01:00:00Z"), (("finished_at",), "2026-09-14T02:00:00"),
    (("finished_at",), "2026-09-40T02:00:00Z"), (("finished_at",), 0),
])
def test_invalid_projection_stops_without_reflecting_input(path, replacement):
    value = populated()
    put(value, path, replacement)
    with pytest.raises(m.ReceiptError) as caught:
        m.validate(raw(value), SHA, now=NOW)
    assert str(caught.value) == "PUBLIC_RECEIPT_NOT_VERIFIED"


@pytest.mark.parametrize("path", [(), ("summary",), ("coverage",), ("promotion",),
                                  ("pull_requests", 0), ("pull_requests", 0, "checks"), ("issues", 0)])
def test_unknown_fields_are_never_published(path):
    value = populated()
    cursor = value
    for key in path:
        cursor = cursor[key]
    cursor["opaque-test-secret"] = "must-not-publish"
    with pytest.raises(m.ReceiptError):
        m.validate(raw(value), SHA, now=NOW)


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[]',
    b'{"a":"\xff"}', b'', b'{', b' ' * (m.MAX_BYTES + 1), b'[' * 1100])
def test_strict_bounded_decoder(payload):
    with pytest.raises(m.ReceiptError):
        m.decode(payload)


@pytest.mark.parametrize("field", ["issues", "pull_requests"])
def test_duplicate_rows_are_not_additional_coverage(field):
    value = populated()
    value[field].append(copy.deepcopy(value[field][0]))
    with pytest.raises(m.ReceiptError):
        m.validate(raw(value), SHA, now=NOW)


@pytest.mark.parametrize("state", sorted(m.PROMOTIONS - {"NOT_REQUESTED"}))
def test_queue_states_remain_observations_not_completion(state):
    value = fixture()
    value["mode"] = "EXACT_QUEUE"
    value["promotion"] = {"state": state}
    if state in m.UNCERTAIN:
        value["status"] = "PARTIAL_FAILURE"
    parsed, _ = m.validate(raw(value), SHA, now=NOW)
    assert parsed["summary"]["merged_pull_requests"] == 0


def test_unknown_send_can_remain_partial():
    value = fixture()
    value.update(mode="EXACT_QUEUE", status="PARTIAL_FAILURE",
        promotion={"state": "QUEUE_WRITE_OUTCOME_UNKNOWN", "send": "ERROR"})
    m.validate(raw(value), SHA, now=NOW)
    value["status"] = "OBSERVATION_COMPLETE"
    with pytest.raises(m.ReceiptError):
        m.validate(raw(value), SHA, now=NOW)


def test_withheld_rows_retain_error_and_cannot_be_all_clear():
    value = fixture()
    value["summary"]["issue_errors"] = 1
    value["status"] = "PARTIAL_FAILURE"
    m.validate(raw(value), SHA, now=NOW)
    value["status"] = "OBSERVATION_COMPLETE"
    with pytest.raises(m.ReceiptError):
        m.validate(raw(value), SHA, now=NOW)


def test_missing_credential_disposition_is_not_an_observation_pass():
    value = fixture()
    value.update(mode="EXACT_QUEUE", status="BLOCKED_MANAGED_PREREQUISITE")
    value["summary"]["observation_failed"] = True
    m.validate(raw(value), SHA, now=NOW)


def test_stale_receipt_does_not_refresh_clock():
    with pytest.raises(m.ReceiptError):
        m.validate(raw(fixture()), SHA, now=NOW + timedelta(hours=2))


def test_exclusive_stage_preserves_exact_bytes_and_one_visibility_read(tmp_path):
    source, output = tmp_path / "raw.json", tmp_path / "approved"
    payload = raw(populated())
    source.write_bytes(payload)
    reader = mock.Mock(side_effect=metadata)
    result = m.stage(source, output, SHA, reader, now=NOW)
    assert source.read_bytes() == (output / "frontier-issue-operator.json").read_bytes() == payload
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["operational_qualification"] is False
    reader.assert_called_once_with(REPO)
    with pytest.raises(m.ReceiptError):
        m.stage(source, output, SHA, reader, now=NOW)
    reader.assert_called_once()


@pytest.mark.parametrize("change", [lambda x: x.update(private=True), lambda x: x.update(private=0),
    lambda x: x.update(visibility="internal"), lambda x: x.pop("visibility"), lambda x: x.update(id=True),
    lambda x: x.update(full_name="szl-holdings/other"), lambda x: x.pop("archived")])
def test_independent_visibility_failure_withholds_artifact(tmp_path, change):
    source, output = tmp_path / "raw.json", tmp_path / "approved"
    source.write_bytes(raw(populated()))
    info = metadata(REPO)
    change(info)
    with pytest.raises(m.ReceiptError):
        m.stage(source, output, SHA, lambda _: info, now=NOW)
    assert not output.exists()


def test_invalid_schema_precedes_any_provider_read_or_output(tmp_path):
    source, output = tmp_path / "raw.json", tmp_path / "approved"
    value = fixture()
    value["secret"] = "synthetic"
    source.write_bytes(raw(value))
    reader = mock.Mock()
    with pytest.raises(m.ReceiptError):
        m.stage(source, output, SHA, reader, now=NOW)
    reader.assert_not_called()
    assert not output.exists()


def test_provider_denial_preserves_original_and_emits_no_artifact(tmp_path):
    source, output = tmp_path / "raw.json", tmp_path / "approved"
    payload = raw(populated())
    source.write_bytes(payload)
    with mock.patch.object(m, "validate", wraps=m.validate), pytest.raises(RuntimeError):
        m.stage(source, output, SHA, mock.Mock(side_effect=RuntimeError("synthetic-private-detail")), now=NOW)
    assert source.read_bytes() == payload and not output.exists()


def test_failed_fsync_cannot_return_stage_success(tmp_path):
    source, output = tmp_path / "raw.json", tmp_path / "approved"
    source.write_bytes(raw(fixture()))
    with mock.patch.object(m.os, "fsync", side_effect=OSError("synthetic")), pytest.raises(OSError):
        m.stage(source, output, SHA, metadata, now=NOW)
    assert source.exists() and output.exists()  # preserve uncertainty; never delete/retry


def test_symlink_input_is_refused(tmp_path):
    source, target = tmp_path / "raw.json", tmp_path / "target.json"
    target.write_bytes(raw(fixture()))
    source.symlink_to(target)
    with pytest.raises(m.ReceiptError):
        m.stage(source, tmp_path / "approved", SHA, metadata, now=NOW)


def test_cli_failure_uses_only_fixed_public_diagnostic(monkeypatch):
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        assert m.main() == 1
    assert json.loads(stream.getvalue()) == {"state": "PUBLIC_RECEIPT_NOT_VERIFIED", "upload_authorized": False}


@pytest.mark.parametrize("name", ["frontier-issue-operator.yml", "frontier-issue-operator-contract.yml"])
def test_workflows_use_complete_locked_isolated_test_environment(name):
    text = (ROOT / ".github/workflows" / name).read_text()
    assert '--require-hashes --only-binary=:all:' in text
    assert 'requirements/frontier-observer-tests.lock' in text
    assert 'python -I -m venv' in text and ' -I -m pip check' in text
    assert ' -I -O -m pytest' in text and 'PYTEST_DISABLE_PLUGIN_AUTOLOAD' in text
    assert 'tests/test_frontier_receipt_check.py' in text
    assert 'python-version: "3.12.14"' in text


def test_upload_is_gated_and_reads_staged_bytes_not_unvalidated_report():
    text = (ROOT / '.github/workflows/frontier-issue-operator.yml').read_text()
    before, after = text.split('      - name: Upload public observation receipt\n', 1)
    assert 'id: verify_receipt' in before
    assert "steps.verify_receipt.outcome == 'success'" in after
    assert 'path: ${{ runner.temp }}/frontier-verified-receipt/frontier-issue-operator.json' in after
    assert 'path: ${{ env.REPORT_PATH }}' not in after
    operate = text.split('  operate:', 1)[1]
    assert 'pip install' not in operate and 'pytest' not in operate
    assert 'secrets.' not in before.split('  operate:', 1)[0]
    contract = (ROOT / '.github/workflows/frontier-issue-operator-contract.yml').read_text()
    assert '  merge_group:\n    types: [checks_requested]' in contract


@pytest.mark.skipif(not (ROOT / '.github/scripts/frontier_issue_operator.py').is_file(), reason='Exact native producer is qualified by hosted CI')
def test_native_producer_roundtrip_and_known_error_codes(monkeypatch):
    spec = importlib.util.spec_from_file_location('receipt_native_producer', ROOT / '.github/scripts/frontier_issue_operator.py')
    assert spec and spec.loader
    producer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = producer
    spec.loader.exec_module(producer)
    monkeypatch.setenv('GITHUB_SHA', SHA)
    monkeypatch.setattr(producer, 'utc_now', lambda: NOW.isoformat())
    assert set(producer.DIAGNOSTIC_CODES.values()) <= m.ERROR_CODES
    assert set(producer.LABELS) == m.LABELS
    assert producer.PUBLIC_BLOCKERS <= m.BLOCKERS
    for apply in (False, True):
        for fatal in (False, True):
            report = producer.build_report(NOW.isoformat(), [], [], apply=apply, fatal=fatal)
            m.validate(raw(report), SHA, now=NOW)
    pull = producer.PullRequestState(repository=REPO, number=7, title='PRIVATE_FIXTURE_TITLE', url='INVALID_FIXTURE_URL')
    pull.public_verified, pull.head_sha, pull.action = True, SHA, 'BLOCKED'
    pull.blockers = ['draft']
    issue = producer.IssueState(repository=REPO, number=8, title='PRIVATE_FIXTURE_TITLE', url='INVALID_FIXTURE_URL',
                               updated_at=NOW.isoformat(), classification='estate:backlog')
    issue.public_verified, issue.action = True, 'CLASSIFICATION_PROPOSED'
    report = producer.build_report(NOW.isoformat(), [pull], [issue], apply=False)
    assert 'PRIVATE_FIXTURE_TITLE' not in raw(report).decode()
    m.validate(raw(report), SHA, now=NOW)
