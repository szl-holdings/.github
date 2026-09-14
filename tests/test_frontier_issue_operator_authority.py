# SPDX-License-Identifier: Apache-2.0
"""Offline positive/negative proof for public projection and exact-head admission."""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("frontier_authority_under_test", ROOT / ".github/scripts/frontier_issue_operator.py")
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)
REPO, HEAD, BASE, SOURCE = "szl-holdings/example", "a" * 40, "b" * 40, "c" * 40


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("these fixtures must never use live networking")
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)


def metadata(repo=REPO, archived=False):
    return {"full_name": repo, "visibility": "public", "private": False,
        "archived": archived, "default_branch": "main"}


def active_rules():
    return [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "required_signatures"},
        {"type": "merge_queue", "parameters": {"merge_method": "SQUASH"}},
        {"type": "pull_request", "parameters": {"required_review_thread_resolution": True,
            "required_approving_review_count": 0, "require_code_owner_review": False, "require_last_push_approval": False}},
        {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
            "required_status_checks": [{"context": "tests", "integration_id": 15368}]}}]


def pull():
    return {"number": 7, "node_id": "PR_fixture", "state": "open", "draft": False, "merged": False, "mergeable": True, "mergeable_state": "clean", "labels": [],
        "base": {"ref": "main", "sha": BASE, "repo": {"full_name": REPO}},
        "head": {"sha": HEAD, "repo": {"full_name": REPO}}}


def grant():
    now = datetime.now(timezone.utc)
    return {"id": "fixture-approval", "repository": REPO, "pr_number": 7,
        "head_sha": HEAD, "base_sha": BASE, "not_before": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rules_sha256": m.rules_digest(active_rules())}


def context(monkeypatch):
    for key, value in {"GITHUB_SHA": SOURCE, "GITHUB_REPOSITORY": m.CONTROLLER_REPO,
            "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true", "GITHUB_RUN_ID": "12345",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": f"{m.CONTROLLER_REPO}/.github/workflows/frontier-issue-operator.yml@refs/heads/main"}.items():
        monkeypatch.setenv(key, value)


class FixtureAPI(m.GitHub):
    """Simulated API only; real parser, paging, authorization and queue logic run."""
    def __init__(self):
        super().__init__("synthetic-not-a-provider-secret", apply=True)
        self.calls = []
        self.mutations = []
        self.rules = active_rules()
        self.grant = grant()
        self.target = metadata()
        self.candidate = pull()
        self.signature = True
        self.source = SOURCE
        self.queue_entry = None
        self.queue_readback_error = False
        self.send_error = False
        self.reflect_new_head = False
        self.check_app = 15368
        self.check_conclusion = "success"
        self.review_decision = None
        self.unresolved = False
        self.reviews_result = []

    def request(self, method, path, payload=None, *, expected=(200,)):
        self.calls.append((method, path))
        if method == "POST" and path == m.GRAPHQL:
            query = payload["query"]
            if query == m.THREAD_QUERY:
                value = {"repository": {"pullRequest": {"reviewThreads": {
                    "nodes": [{"isResolved": not self.unresolved}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
            elif query == m.QUEUE_QUERY:
                if self.queue_readback_error and self.mutations:
                    raise m.GitHubError("synthetic readback failure")
                value = {"repository": {"pullRequest": {"id": "PR_fixture", "state": "OPEN", "isDraft": False,
                    "headRefOid": "d" * 40 if self.reflect_new_head and self.mutations else HEAD,
                    "baseRefOid": BASE, "reviewDecision": self.review_decision, "mergeQueueEntry": self.queue_entry}}}
            elif query == m.QUEUE_MUTATION:
                self.mutations.append(copy.deepcopy(payload["variables"]["input"]))
                self.queue_entry = {"id": "MQE_fixture", "pullRequest": {"id": "PR_fixture", "headRefOid": HEAD}}
                if self.send_error:
                    raise m.GitHubError("ambiguous send fixture")
                value = {"enqueuePullRequest": {"mergeQueueEntry": self.queue_entry}}
            else:
                raise AssertionError("unexpected GraphQL operation")
            return {"data": value}, {}, 200
        assert method == "GET", "no REST mutation is part of queue admission"
        if path == f"/repos/{m.CONTROLLER_REPO}/branches/main":
            value = {"protected": True, "commit": {"sha": self.source}}
        elif path == f"/repos/{m.CONTROLLER_REPO}/actions/runs/12345":
            value = {"id": 12345, "head_sha": SOURCE, "head_branch": "main", "event": "workflow_dispatch",
                "run_attempt": 1, "status": "in_progress", "path": ".github/workflows/frontier-issue-operator.yml"}
        elif path == f"/repos/{m.CONTROLLER_REPO}/contents/{m.AUTHORIZATION_PATH}?ref={SOURCE}":
            raw = json.dumps({"schema": m.AUTHORIZATION_SCHEMA, "authorizations": [self.grant]}).encode()
            value = {"type": "file", "path": m.AUTHORIZATION_PATH, "encoding": "base64", "size": len(raw),
                "content": base64.b64encode(raw).decode(),
                "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
        elif path == f"/repos/{REPO}":
            value = self.target
        elif path == f"/repos/{REPO}/branches/main":
            value = {"protected": True, "commit": {"sha": BASE}}
        elif path.startswith(f"/repos/{REPO}/rules/branches/main?"):
            value = self.rules
        elif path == f"/repos/{REPO}/pulls/7":
            value = self.candidate
        elif path == f"/repos/{REPO}/commits/{HEAD}":
            value = {"sha": HEAD, "commit": {"verification": {"verified": self.signature}}}
        elif path.startswith(f"/repos/{REPO}/commits/{HEAD}/check-runs?"):
            value = {"total_count": 1, "check_runs": [{"id": 1, "head_sha": HEAD, "name": "tests",
                "status": "completed", "conclusion": self.check_conclusion, "app": {"id": self.check_app}}]}
        elif path.startswith(f"/repos/{REPO}/commits/{HEAD}/status?"):
            value = {"sha": HEAD, "total_count": 0, "statuses": []}
        elif path.startswith(f"/repos/{REPO}/pulls/7/reviews?"):
            value = self.reviews_result
        else:
            raise AssertionError("fixture endpoint not declared: " + path)
        return copy.deepcopy(value), {}, 200


def execute(api):
    stages = []
    outcome = m.execute_authorized_queue(api, "fixture-approval", m.QUEUE_ACKNOWLEDGEMENT, stages.append)
    return outcome, stages


def test_positive_complete_manual_dispatch_enqueues_one_exact_head(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    outcome, stages = execute(api)
    assert outcome == {"state": "QUEUED_EXACT_HEAD_OBSERVED"}
    assert stages == [{"state": "QUEUE_WRITE_ATTEMPTED_READBACK_REQUIRED"}]
    assert api.mutations == [{"pullRequestId": "PR_fixture", "expectedHeadOid": HEAD, "jump": False}]
    assert api._queue_permit is None and api._queue_input is None
    assert not any(method in {"PATCH", "PUT", "DELETE"} for method, _ in api.calls)
    assert sum(path == f"/repos/{REPO}/pulls/7" for _, path in api.calls) == 2


def test_first_queue_response_is_not_a_completion_certificate(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.queue_readback_error = True
    outcome, _ = execute(api)
    assert outcome["state"] == "QUEUE_WRITE_OUTCOME_UNKNOWN"
    assert len(api.mutations) == 1


def test_ambiguous_send_reconciles_without_retry(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.send_error = True
    outcome, _ = execute(api)
    assert outcome["state"] == "QUEUED_EXACT_HEAD_OBSERVED"
    assert len(api.mutations) == 1


def test_changed_head_after_send_is_unknown_not_success(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.reflect_new_head = True
    assert execute(api)[0]["state"] == "QUEUE_WRITE_OUTCOME_UNKNOWN"
    assert len(api.mutations) == 1


def test_already_queued_exact_head_does_not_send_again(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.queue_entry = {"id": "fixture", "pullRequest": {"id": "PR_fixture", "headRefOid": HEAD}}
    outcome, stages = execute(api)
    assert outcome["state"] == "ALREADY_QUEUED_EXACT_HEAD"
    assert stages == [] and api.mutations == []


@pytest.mark.parametrize("field,value", [("GITHUB_EVENT_NAME", "schedule"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_SHA", "main"), ("GITHUB_REF_PROTECTED", "false"),
    ("GITHUB_REPOSITORY", "someone/fork"), ("GITHUB_RUN_ID", "../12345"), ("GITHUB_WORKFLOW_REF", "wrong")])
def test_wrong_execution_authority_refuses_before_mutation(monkeypatch, field, value):
    context(monkeypatch)
    monkeypatch.setenv(field, value)
    api = FixtureAPI()
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


@pytest.mark.parametrize("field,value", [("draft", True), ("draft", None), ("state", "closed"),
    ("mergeable", None), ("mergeable_state", "behind"), ("merged", True),
    ("labels", [{"name": "HOLD: needs evidence"}]), ("labels", None)])
def test_unready_or_held_candidate_does_not_enqueue(monkeypatch, field, value):
    context(monkeypatch)
    api = FixtureAPI()
    api.candidate[field] = value
    # Avoid sleeping in the old mergeability polling path in this pure fixture.
    with mock.patch.object(m.time, "sleep"), pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


@pytest.mark.parametrize("field,value", [("private", True), ("visibility", "private"),
    ("visibility", "internal"), ("archived", True), ("archived", None), ("full_name", "szl-holdings/other")])
def test_private_unknown_or_archived_target_never_enqueues(monkeypatch, field, value):
    context(monkeypatch)
    api = FixtureAPI()
    api.target[field] = value
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


@pytest.mark.parametrize("field,value", [("signature", False), ("signature", "true"), ("check_app", 99999),
    ("check_conclusion", "skipped"), ("check_conclusion", "neutral"), ("check_conclusion", "failure"),
    ("review_decision", "CHANGES_REQUESTED"), ("review_decision", "REVIEW_REQUIRED"), ("unresolved", True)])
def test_signature_required_checks_and_reviews_fail_closed(monkeypatch, field, value):
    context(monkeypatch)
    api = FixtureAPI()
    setattr(api, field, value)
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


@pytest.mark.parametrize("kind", ["pull_request", "required_status_checks", "required_signatures", "merge_queue", "deletion", "non_fast_forward"])
def test_removing_any_required_protection_is_not_accepted(monkeypatch, kind):
    context(monkeypatch)
    api = FixtureAPI()
    api.rules = [row for row in api.rules if row["type"] != kind]
    api.grant["rules_sha256"] = m.rules_digest(api.rules)
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def test_review_count_nonzero_cannot_pass_with_null_decision(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.rules[4]["parameters"]["required_approving_review_count"] = 1
    api.grant["rules_sha256"] = m.rules_digest(api.rules)
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def test_wrong_acknowledgement_or_empty_grant_never_sends(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    with pytest.raises(m.GitHubError):
        m.execute_authorized_queue(api, "fixture-approval", "yes", lambda x: None)
    with pytest.raises(m.GitHubError):
        m.validate_authorizations({"schema": m.AUTHORIZATION_SCHEMA, "authorizations": []}, "fixture-approval", datetime.now(timezone.utc))
    assert api.calls == [] and api.mutations == []


@pytest.mark.parametrize("change", [lambda r: r.update(head_sha="main"), lambda r: r.update(pr_number=True),
    lambda r: r.update(repository="szl-holdings/../escape"), lambda r: r.update(rules_sha256="a"),
    lambda r: r.update(expires_at=r["not_before"]), lambda r: r.update(extra="not allowed"),
    lambda r: r.update(expires_at="2030-01-01T00:00:00Z"), lambda r: r.update(not_before="2026-09-13T00:00:00+00:00")])
def test_bad_authorizations_fail_closed(change):
    row = grant()
    change(row)
    with pytest.raises(m.GitHubError):
        m.validate_authorizations({"schema": m.AUTHORIZATION_SCHEMA, "authorizations": [row]}, row["id"], datetime.now(timezone.utc))


def test_duplicate_authorization_identity_is_ambiguous():
    row = grant()
    with pytest.raises(m.GitHubError):
        m.validate_authorizations({"schema": m.AUTHORIZATION_SCHEMA, "authorizations": [row, row]}, row["id"], datetime.now(timezone.utc))


def test_controller_source_movement_stops_before_send(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    old_preflight = m.promotion_preflight
    def moving(*args):
        result = old_preflight(*args)
        api.source = "d" * 40
        return result
    with mock.patch.object(m, "promotion_preflight", side_effect=moving), pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def test_error_evidence_must_persist_before_possible_write(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    with pytest.raises(OSError):
        m.execute_authorized_queue(api, "fixture-approval", m.QUEUE_ACKNOWLEDGEMENT,
            mock.Mock(side_effect=OSError("synthetic disk full")))
    assert api.mutations == []


@pytest.mark.parametrize("method,path,payload", [("PUT", f"/repos/{REPO}/pulls/7/merge", {"sha": HEAD}),
    ("PATCH", f"/repos/{REPO}/issues/7", {"state": "closed"}),
    ("PATCH", f"/repos/{REPO}/issues/7", {"labels": []}),
    ("POST", f"/repos/{REPO}/labels", {"name": "label"}),
    ("DELETE", f"/repos/{REPO}/git/refs/heads/main", None),
    ("POST", m.GRAPHQL, {"query": "mutation { arbitraryWrite }", "variables": {}}),
    ("POST", m.GRAPHQL, {"query": m.QUEUE_MUTATION, "variables": {"input": {"pullRequestId": "PR_x", "expectedHeadOid": HEAD}}}),
    ("PATCH", f"/repos/{m.CONTROLLER_REPO}/issues/585", {"body": "replace human body"})])
def test_transport_blocks_all_ungranted_effects_even_with_apply(method, path, payload):
    api = m.GitHub("synthetic", apply=True)
    with mock.patch.object(m.urllib.request, "build_opener") as network, pytest.raises(m.GitHubError):
        api.request(method, path, payload)
    network.assert_not_called()


def test_direct_enqueue_without_a_preflight_permit_is_refused():
    api = m.GitHub("synthetic", apply=True)
    with mock.patch.object(api, "graphql") as network, pytest.raises(m.GitHubError):
        api.enqueue_exact("PR_fixture", HEAD)
    network.assert_not_called()


def test_exact_permit_binds_the_only_transport_mutation():
    api = m.GitHub("synthetic", apply=True)
    api._queue_permit = ("PR_fixture", HEAD)
    fake = mock.MagicMock()
    fake.status, fake.headers = 200, {}
    fake.read.return_value = b'{"data":{"enqueuePullRequest":{}}}'
    with mock.patch.object(m.urllib.request, "build_opener") as network:
        network.return_value.open.return_value.__enter__.return_value = fake
        api.enqueue_exact("PR_fixture", HEAD)
    request = network.return_value.open.call_args.args[0]
    sent = json.loads(request.data)
    assert request.full_url == m.GRAPHQL and request.method == "POST"
    assert sent["query"] == m.QUEUE_MUTATION
    assert sent["variables"]["input"]["expectedHeadOid"] == HEAD
    assert sent["variables"]["input"]["jump"] is False
    assert api._queue_input is None


def test_public_projection_drops_private_names_and_all_free_text():
    secret = "opaque-secret-without-a-recognizable-prefix"
    private = m.PullRequestState("szl-holdings/private-fixture-name", 7, secret, "https://exfil.invalid", error=secret)
    public = m.PullRequestState(REPO, 8, secret, "https://exfil.invalid", head_sha=HEAD,
        action="BLOCKED", error=secret, public_verified=True)
    public.checks.passed = [secret]
    public.changes_requested_by = [secret]
    public.blockers = [secret]
    issue = m.IssueState(REPO, 9, secret, "https://exfil.invalid", secret, "estate:p0", public_verified=True)
    report = m.build_report(m.utc_now(), [private, public], [issue], apply=False)
    body = m.command_center_body(org=m.DEFAULT_ORG, apply=False, pulls=[private, public], issues=[issue])
    text = json.dumps(report) + body
    assert secret not in text and "private-fixture-name" not in text and "exfil.invalid" not in text
    assert report["summary"]["observed_pull_requests"] == 1
    assert report["coverage"]["complete_organization"] is False
    assert report["coverage"]["security_alerts"] == "NOT_OBSERVED"


def test_visibility_change_drops_identity_before_publication():
    api = mock.Mock()
    api.repository.return_value = {"full_name": REPO, "visibility": "private", "private": True}
    row = m.PullRequestState(REPO, 7, "sensitive", "", public_verified=True)
    m.refresh_public_scope(api, [row])
    assert m.public_row(row) is None and row.action == "ERROR"


def test_body_case_whitespace_and_json_framing_remain_distinct():
    body = 'The case-sensitive Python code and literal path matter: FileName/Example.'
    assert m.issue_fingerprint("Title", body) != m.issue_fingerprint("Title", body.lower())
    assert m.issue_fingerprint("Title", body) != m.issue_fingerprint("Title", body + " ")
    assert m.issue_fingerprint("x\ny", body) != m.issue_fingerprint("x", "y\n" + body)


def test_request_error_has_no_reflective_path_or_token():
    api = m.GitHub("opaque-fixture-secret", apply=False)
    fake = mock.MagicMock()
    fake.status, fake.headers = 201, {}
    fake.read.return_value = b'{}'
    with mock.patch.object(m.urllib.request, "build_opener") as network:
        network.return_value.open.return_value.__enter__.return_value = fake
        with pytest.raises(m.GitHubError) as caught:
            api.request("GET", "/repos/x/opaque-fixture-secret")
    assert "opaque-fixture-secret" not in str(caught.value)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_duplicate_or_nonfinite_json_is_refused(raw):
    with pytest.raises(ValueError):
        m.strict_json(raw)


def test_atomic_report_keeps_previous_bytes_on_failure(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("old", encoding="utf-8")
    with mock.patch.object(m.os, "replace", side_effect=OSError("synthetic")), pytest.raises(OSError):
        m.write_report(path, {"state": "fixture"})
    assert path.read_text() == "old"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["report.json"]


def test_main_ordinary_observation_never_invokes_any_mutator(tmp_path):
    api = mock.create_autospec(m.GitHub, instance=True)
    api.search.return_value = []
    with mock.patch.object(m, "GitHub", return_value=api):
        assert m.main(["--report", str(tmp_path / "r.json")]) == 0
    assert all("is:public" in call.args[0] for call in api.search.call_args_list)
    api.enqueue_exact.assert_not_called()
    api.merge.assert_not_called()
    api.close_duplicate.assert_not_called()
    api.set_classification.assert_not_called()
    api.publish_command_center.assert_not_called()


def test_main_queue_unknown_is_persisted_and_nonzero(tmp_path):
    api = mock.create_autospec(m.GitHub, instance=True)
    api.search.return_value = []
    path = tmp_path / "r.json"
    with mock.patch.dict(os.environ, {"SZL_ORG_TOKEN": "synthetic"}), \
         mock.patch.object(m, "GitHub", return_value=api), \
         mock.patch.object(m, "dispatch_authorization", return_value=(SOURCE, grant())), \
         mock.patch.object(m, "execute_authorized_queue", return_value={"state": "QUEUE_WRITE_OUTCOME_UNKNOWN"}):
        assert m.main(["--apply", "--report", str(path)]) == 1
    value = json.loads(path.read_text())
    assert value["status"] == "PARTIAL_FAILURE"
    assert value["promotion"]["state"] == "QUEUE_WRITE_OUTCOME_UNKNOWN"


def test_workflow_isolation_manual_default_and_empty_authority():
    text = (ROOT / ".github/workflows/frontier-issue-operator.yml").read_text()
    before, operate = text.split("  operate:", 1)
    assert "needs: validate" in operate
    assert "pip install" not in operate and "pytest" not in operate
    assert "secrets." not in before
    assert "default: false" in text and "default: true" not in text
    assert "github.event_name == 'workflow_dispatch' && inputs.apply" in text
    assert "SZL_ORG_ADMIN_TOKEN" not in text and "ORG_ADMIN_TOKEN" not in text
    assert "--from-dispatch-event" in text
    assert "${{ inputs.authorization_id }}" not in text
    assert "${{ inputs.acknowledgement }}" not in text
    assert "ref: ${{ github.sha }}" in operate
    policy = m.strict_json((ROOT / "config/estate-pr-authorizations.json").read_bytes())
    assert set(policy) == {"schema", "authorizations"}
    assert policy["schema"] == m.AUTHORIZATION_SCHEMA
    assert isinstance(policy["authorizations"], list)
    # Empty is the shipped default, not an invariant forbidding future reviewed
    # grants. Validate each admitted grant's shape independently of wall clock.
    for row in policy["authorizations"]:
        assert m.validate_authorizations(policy, row["id"], m.timestamp(row["not_before"])) == row


@pytest.mark.parametrize("change", [lambda api: api.candidate.update(number=8),
    lambda api: api.candidate.update(node_id="PR_other"),
    lambda api: api.candidate["head"].update(sha="e" * 40),
    lambda api: api.candidate["base"].update(sha="e" * 40),
    lambda api: api.candidate["head"]["repo"].update(full_name="szl-holdings/other"),
    lambda api: api.candidate["base"]["repo"].update(full_name="szl-holdings/other")])
def test_wrong_identity_vector_is_not_enqueued(monkeypatch, change):
    context(monkeypatch)
    api = FixtureAPI()
    change(api)
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def test_rules_movement_between_complete_preflights_is_refused(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    original = m.promotion_preflight
    def moving(*args):
        result = original(*args)
        api.rules[0]["different"] = True
        return result
    with mock.patch.object(m, "promotion_preflight", side_effect=moving), pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def test_queue_readback_binds_nested_pull_request_not_merge_group_commit(monkeypatch):
    context(monkeypatch)
    api = FixtureAPI()
    api.queue_entry = {"id": "existing", "headCommit": {"oid": "f" * 40},
        "pullRequest": {"id": "PR_fixture", "headRefOid": HEAD}}
    assert execute(api)[0]["state"] == "ALREADY_QUEUED_EXACT_HEAD"
    api.queue_entry["pullRequest"]["headRefOid"] = "e" * 40
    with pytest.raises(m.GitHubError):
        execute(api)
    assert api.mutations == []


def writer_fixture():
    api = m.GitHub("repository-scoped-fixture", apply=False)
    api.repository = mock.Mock(side_effect=lambda repo: metadata(repo))
    issue = {"number": 585, "title": m.COMMAND_CENTER_TITLE, "state": "open",
        "user": {"login": "stephenlutar2-hash"}, "body": m.COMMAND_CENTER_MARKER + "\nold machine body"}
    calls = []
    def request(method, path, payload=None, **kwargs):
        calls.append((method, path, payload))
        if method == "PATCH":
            issue.update(payload)
        return copy.deepcopy(issue), {}, 200
    api.request = mock.Mock(side_effect=request)
    return api, issue, calls


def test_machine_publisher_updates_only_fixed_body_then_reads_back():
    api, issue, calls = writer_fixture()
    secret = "raw-title-and-error-must-never-be-published"
    row = m.PullRequestState(REPO, 7, secret, "https://other.invalid", action="BLOCKED", public_verified=True)
    with mock.patch.object(m, "protected_source", return_value=SOURCE):
        url = api.publish_command_center([row], [])
    assert url.endswith("/.github/issues/585")
    writes = [row for row in calls if row[0] != "GET"]
    assert len(writes) == 1
    assert writes[0][0:2] == ("PATCH", "/repos/szl-holdings/.github/issues/585")
    assert set(writes[0][2]) == {"body"}
    assert calls[-1][0] == "GET" and secret not in issue["body"]
    assert api._report_body is None


@pytest.mark.parametrize("field,value", [("number", 999), ("state", "closed"),
    ("title", "human-authored issue"), ("body", "human content without machine marker"),
    ("user", {"login": "other"}), ("pull_request", {})])
def test_machine_publisher_refuses_changed_ownership(field, value):
    api, issue, calls = writer_fixture()
    issue[field] = value
    with mock.patch.object(m, "protected_source", return_value=SOURCE), pytest.raises(m.GitHubError):
        api.publish_command_center([], [])
    assert not any(row[0] != "GET" for row in calls)


def test_machine_publisher_drops_newly_private_rows():
    api, issue, calls = writer_fixture()
    api.repository.side_effect = lambda repo: metadata(repo) if repo == m.CONTROLLER_REPO else {"private": True}
    row = m.PullRequestState(REPO, 7, "raw", "", action="BLOCKED", public_verified=True)
    with mock.patch.object(m, "protected_source", return_value=SOURCE):
        api.publish_command_center([row], [])
    assert REPO not in issue["body"] and row.public_verified is False


def test_machine_publisher_requires_exact_protected_source_before_write():
    api, issue, calls = writer_fixture()
    with mock.patch.object(m, "protected_source", side_effect=[SOURCE, "d" * 40]), pytest.raises(m.GitHubError):
        api.publish_command_center([], [])
    assert not any(row[0] != "GET" for row in calls)


def test_allowlisted_report_write_cannot_change_title_labels_or_state():
    api = m.GitHub("fixture", apply=False)
    api._report_body = "safe generated body"
    with mock.patch.object(m.urllib.request, "build_opener") as network, pytest.raises(m.GitHubError):
        api.request("PATCH", "/repos/szl-holdings/.github/issues/585", {"body": api._report_body, "state": "closed"})
    network.assert_not_called()


def test_dispatch_event_reader_uses_bounded_exact_inputs(tmp_path, monkeypatch):
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"inputs": {"apply": "true", "authorization_id": "fixture-approval",
        "acknowledgement": m.QUEUE_ACKNOWLEDGEMENT}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    assert m.read_dispatch_inputs() == ("fixture-approval", m.QUEUE_ACKNOWLEDGEMENT)


@pytest.mark.parametrize("change", [lambda x: x.update(apply=False), lambda x: x.update(apply=1),
    lambda x: x.update(authorization_id="--unexpected-opaque-secret"), lambda x: x.update(acknowledgement="yes"),
    lambda x: x.update(extra="unknown"), lambda x: x.update(authorization_id="a" * 65)])
def test_invalid_dispatch_inputs_do_not_reflect_values(tmp_path, monkeypatch, change):
    inputs = {"apply": "true", "authorization_id": "fixture-approval", "acknowledgement": m.QUEUE_ACKNOWLEDGEMENT}
    change(inputs)
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"inputs": inputs}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    with pytest.raises(m.GitHubError) as caught:
        m.read_dispatch_inputs()
    assert "opaque-secret" not in str(caught.value)


def test_error_code_is_a_positive_allowlist_not_raw_exception():
    assert m.diagnostic_code(m.GitHubError("exact candidate signature is not verified")) == "SIGNATURE_UNVERIFIED"
    assert m.diagnostic_code(RuntimeError("opaque-secret-information")) == "OPERATOR_PRECONDITION_OR_OBSERVATION_FAILED"
