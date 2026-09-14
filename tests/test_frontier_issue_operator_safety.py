# SPDX-License-Identifier: Apache-2.0
"""Offline incomplete-evidence and archived-target regressions; no live mutations."""
from __future__ import annotations

import importlib.util
import json
import sys
import socket
from pathlib import Path
from unittest import mock
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'operator_safety_under_test', ROOT / '.github/scripts/frontier_issue_operator.py')
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)
REPO = 'szl-holdings/example'
SHA = 'a' * 40


@pytest.fixture(autouse=True)
def refuse_live_network(monkeypatch):
    """A regression must never make a real provider request, even on old code."""
    def denied(*args, **kwargs):
        raise AssertionError("Live network is forbidden in these fixture tests")
    monkeypatch.setattr(m.urllib.request, "urlopen", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def check(i, conclusion='success'):
    return {'id': i, 'name': f'check-{i}', 'status': 'completed', 'conclusion': conclusion}


def review(i, state='COMMENTED'):
    return {'id': i, 'user': {'login': 'reviewer'}, 'state': state}


def response(payload):
    return payload, {}, 200


def api():
    return m.GitHub('fixture-token-not-a-credential', apply=False)


def test_check_page_two_failure_is_not_hidden():
    client = api()
    client.request = mock.Mock(side_effect=[
        response({'total_count': 101, 'check_runs': [check(i) for i in range(1, 101)]}),
        response({'total_count': 101, 'check_runs': [check(101, 'failure')]}),
        response({'sha': SHA, 'total_count': 0, 'statuses': []}),
    ])
    observed = client.checks(REPO, SHA)
    assert observed.count == 101
    assert observed.failed == ['check-101']
    assert 'page=2' in client.request.call_args_list[1].args[1]


def test_status_page_two_pending_is_not_hidden():
    client = api()
    statuses = [{'id': i, 'context': f'status-{i}', 'state': 'success'} for i in range(1, 101)]
    client.request = mock.Mock(side_effect=[
        response({'total_count': 0, 'check_runs': []}),
        response({'sha': SHA, 'total_count': 101, 'statuses': statuses}),
        response({'sha': SHA, 'total_count': 101, 'statuses': [
            {'id': 101, 'context': 'security-pending', 'state': 'pending'}]}),
    ])
    observed = client.checks(REPO, SHA)
    assert observed.active == ['security-pending']
    assert observed.count == 101


@pytest.mark.parametrize('payload', [None, [], {}, {'total_count': True, 'check_runs': []},
    {'total_count': 1, 'check_runs': []}, {'total_count': 0, 'check_runs': [check(1)]},
    {'total_count': 1, 'check_runs': [None]}])
def test_bad_check_collection_is_not_empty_success(payload):
    client = api()
    client.request = mock.Mock(return_value=response(payload))
    with pytest.raises(m.GitHubError):
        client.checks(REPO, SHA)


def test_duplicate_or_moving_check_pages_fail_closed():
    for last in ({'total_count': 102, 'check_runs': [check(101)]},
                 {'total_count': 101, 'check_runs': [check(1)]}):
        client = api()
        client.request = mock.Mock(side_effect=[
            response({'total_count': 101, 'check_runs': [check(i) for i in range(1, 101)]}),
            response(last),
        ])
        with pytest.raises(m.GitHubError):
            client.checks(REPO, SHA)


def test_nonterminal_check_with_success_conclusion_never_passes():
    row = check(1)
    row['status'] = 'unexpected'
    client = api()
    client.request = mock.Mock(side_effect=[response({'total_count': 1, 'check_runs': [row]}),
        response({'sha': SHA, 'total_count': 0, 'statuses': []})])
    observed = client.checks(REPO, SHA)
    assert observed.failed
    assert not observed.passed


def test_combined_status_for_another_sha_fails_closed():
    client = api()
    client.request = mock.Mock(side_effect=[response({'total_count': 0, 'check_runs': []}),
        response({'sha': 'b' * 40, 'total_count': 0, 'statuses': []})])
    with pytest.raises(m.GitHubError):
        client.checks(REPO, SHA)


def test_second_review_page_retains_change_request():
    client = api()
    client.request = mock.Mock(side_effect=[response([review(i) for i in range(1, 101)]),
        response([review(101, 'CHANGES_REQUESTED')])])
    assert client.reviews(REPO, 7) == ['reviewer']
    assert 'page=2' in client.request.call_args_list[1].args[1]


@pytest.mark.parametrize('value', [None, {}, [None], [{'state': 'APPROVED'}]])
def test_malformed_review_response_is_not_no_review(value):
    client = api()
    client.request = mock.Mock(return_value=response(value))
    with pytest.raises(m.GitHubError):
        client.reviews(REPO, 7)


def test_comment_review_does_not_clear_request_on_previous_page():
    client = api()
    client.request = mock.Mock(side_effect=[response([review(1, 'CHANGES_REQUESTED')] +
        [review(i) for i in range(2, 101)]), response([review(101)])])
    assert client.reviews(REPO, 7) == ['reviewer']


def threads(nodes, more=False, cursor=None):
    return {'repository': {'pullRequest': {'reviewThreads': {'nodes': nodes,
        'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}}


@pytest.mark.parametrize('payload', [{}, {'repository': None}, {'repository': {'pullRequest': None}},
    threads([{}]), threads([{'isResolved': 'false'}]), threads([], more='false')])
def test_missing_thread_evidence_is_not_zero_unresolved(payload):
    client = api()
    client.graphql = mock.Mock(return_value=payload)
    with pytest.raises(m.GitHubError):
        client.unresolved_threads(REPO, 7)


def test_unresolved_thread_on_second_page_blocks():
    client = api()
    client.graphql = mock.Mock(side_effect=[threads([{'isResolved': True}], True, 'next'),
        threads([{'isResolved': False}])])
    assert client.unresolved_threads(REPO, 7) == 1


def test_repeated_thread_cursor_fails_instead_of_looping():
    client = api()
    client.graphql = mock.Mock(side_effect=[threads([], True, 'again'), threads([], True, 'again'),
        AssertionError('Unbounded cursor replay')])
    with pytest.raises(m.GitHubError):
        client.unresolved_threads(REPO, 7)


def issue(number=1):
    return {'repository_url': 'https://api.github.com/repos/' + REPO,
        'number': number, 'title': 'Fixture issue', 'body': 'Same long fixture report for preserving independently stored discussion evidence.',
        'html_url': f'https://github.com/{REPO}/issues/{number}',
        'updated_at': '2026-09-13T00:00:00Z', 'labels': []}


def test_archived_issues_are_read_only_and_metadata_is_cached():
    client = mock.create_autospec(m.GitHub, instance=True)
    client.apply = True
    client.search.return_value = [issue(1), issue(2)]
    client.repository.return_value = {'archived': True, 'full_name': REPO, 'visibility': 'public', 'private': False}
    observed = m.reconcile_issues(client, 'szl-holdings', limit=10)
    assert all(row.action == 'READ_ONLY_ARCHIVED' for row in observed)
    client.repository.assert_called_once_with(REPO)
    client.close_duplicate.assert_not_called()
    client.set_classification.assert_not_called()


def test_unknown_archival_state_prevents_issue_writes():
    client = mock.create_autospec(m.GitHub, instance=True)
    client.apply = True
    client.search.return_value = [issue()]
    client.repository.return_value = {}
    observed = m.reconcile_issues(client, 'szl-holdings', limit=10)
    assert observed[0].action == 'ERROR'
    client.close_duplicate.assert_not_called()
    client.set_classification.assert_not_called()


def test_archive_and_unknown_archive_prevent_pr_merge():
    for metadata, action in (({'archived': True, 'full_name': REPO, 'visibility': 'public', 'private': False}, 'READ_ONLY_ARCHIVED'), ({}, 'ERROR')):
        client = mock.create_autospec(m.GitHub, instance=True)
        client.apply = True
        client.repository.return_value = metadata
        observed = m.evaluate_pr(client, issue())
        assert observed.action == action
        client.pull.assert_not_called()
        client.merge.assert_not_called()


def test_item_errors_are_counted_in_command_center():
    failed = m.IssueState(REPO, 1, 'fixture', 'https://github.com/' + REPO, '',
        'estate:backlog', action='ERROR', error='fixture failure')
    text = m.command_center_body(org='szl-holdings', apply=True, pulls=[], issues=[failed])
    assert '- Operator errors: **1**' in text


def test_item_error_is_nonzero_and_not_complete(tmp_path):
    failed = m.IssueState(REPO, 1, 'fixture', 'https://github.com/' + REPO, '',
        'estate:backlog', action='ERROR', error='fixture failure')
    output = tmp_path / 'report.json'
    client = mock.create_autospec(m.GitHub, instance=True)
    client.apply = False
    client.search.return_value = []
    with mock.patch.object(m, 'GitHub', return_value=client), \
         mock.patch.object(m, 'reconcile_issues', return_value=[failed]):
        assert m.main(['--report', str(output)]) == 1
    report = json.loads(output.read_text())
    assert report['status'] == 'PARTIAL_FAILURE'
    assert report['summary']['issue_errors'] == 1


@pytest.mark.parametrize('target', [
    'https://outside.invalid/repos/x/y', 'http://api.github.com/repos/x/y',
    '//outside.invalid/repos/x/y', 'https://api.github.com@outside.invalid/repos/x/y',
    'https://user:password@api.github.com/repos/x/y', 'https://api.github.com:444/repos/x/y',
    '/repos/x/../y', '/repos/x/%2e%2e/y', '/repos/x/y#fragment', '/repos/x/y\n',
])
def test_credentialed_transport_refuses_noncanonical_targets_before_network(target):
    client = api()
    with mock.patch.object(m.urllib.request, 'build_opener') as opener, \
         mock.patch.object(m.urllib.request, 'urlopen') as old_transport:
        with pytest.raises(m.GitHubError):
            client.request('GET', target)
    opener.assert_not_called()
    old_transport.assert_not_called()


def test_transport_refuses_redirects_and_does_not_echo_provider_body():
    client = api()
    failure = urllib.error.HTTPError('https://api.github.com/repos/x/y', 302,
        'fixture-token-not-a-credential', {'Location': 'https://outside.invalid'}, None)
    with mock.patch.object(m.urllib.request, 'build_opener') as factory:
        factory.return_value.open.side_effect = failure
        with pytest.raises(m.GitHubError) as caught:
            client.request('GET', '/repos/x/y')
    assert 'fixture-token' not in str(caught.value)
    assert any(isinstance(handler, m.NoRedirect) for handler in factory.call_args.args)


def test_transport_bounds_json_reads():
    client = api()
    fake = mock.MagicMock()
    fake.status = 200
    fake.headers = {}
    fake.read.return_value = b' ' * (m.MAX_API_BYTES + 1)
    with mock.patch.object(m.urllib.request, 'build_opener') as factory:
        factory.return_value.open.return_value.__enter__.return_value = fake
        with pytest.raises(m.GitHubError):
            client.request('GET', '/repos/x/y')
    fake.read.assert_called_once_with(m.MAX_API_BYTES + 1)


def test_search_uses_fixed_page_size_at_non_multiple_limit():
    client = api()
    client.request = mock.Mock(side_effect=[
        response({'total_count': 150, 'incomplete_results': False,
                  'items': [{'id': i} for i in range(1, 101)]}),
        response({'total_count': 150, 'incomplete_results': False,
                  'items': [{'id': i} for i in range(101, 151)]})])
    assert len(client.search('fixture', limit=150)) == 150
    assert 'per_page=100&page=2' in client.request.call_args_list[1].args[1]


@pytest.mark.parametrize('payload', [None, {},
    {'total_count': 0, 'incomplete_results': True, 'items': []},
    {'total_count': 101, 'incomplete_results': False, 'items': []},
    {'total_count': 1, 'incomplete_results': False, 'items': []}])
def test_incomplete_search_does_not_become_empty_success(payload):
    client = api()
    client.request = mock.Mock(return_value=response(payload))
    with pytest.raises(m.GitHubError):
        client.search('fixture', limit=100)


def test_graphql_does_not_echo_error_details():
    client = api()
    client.request = mock.Mock(return_value=response({'errors': [{'message': 'PRIVATE_TOKEN_DETAIL'}]}))
    with pytest.raises(m.GitHubError) as caught:
        client.graphql('query {}', {})
    assert 'PRIVATE_TOKEN_DETAIL' not in str(caught.value)


def test_workflow_scopes_org_token_to_execution_step_only():
    workflow = (ROOT / '.github/workflows/frontier-issue-operator.yml').read_text()
    job_header, steps = workflow.split('    steps:', 1)
    assert 'SZL_ORG_TOKEN' not in job_header
    assert steps.count('SZL_ORG_TOKEN:') == 1
    execution = steps.split('- name: Execute bounded organization reconciliation', 1)[1].split('      - name:', 1)[0]
    assert 'SZL_ORG_TOKEN:' in execution
    contracts = steps.split('- name: Run network-free operator contracts', 1)[1].split('      - name:', 1)[0]
    assert 'secrets.' not in contracts
    assert 'test_frontier_issue_operator_safety.py' in contracts


def test_empty_success_keeps_zero_exit_and_complete(tmp_path):
    output = tmp_path / 'report.json'
    client = mock.create_autospec(m.GitHub, instance=True)
    client.apply = False
    client.search.return_value = []
    with mock.patch.object(m, 'GitHub', return_value=client), mock.patch.object(m, 'reconcile_issues', return_value=[]):
        assert m.main(['--report', str(output)]) == 0
    assert json.loads(output.read_text())['status'] == 'OBSERVATION_COMPLETE'


def test_canonical_transport_keeps_auth_only_on_admitted_request():
    client = api()
    fake = mock.MagicMock()
    fake.status, fake.headers = 200, {}
    fake.read.return_value = b'{"result":true}'
    with mock.patch.object(m.urllib.request, 'build_opener') as factory:
        factory.return_value.open.return_value.__enter__.return_value = fake
        payload, _, status = client.request('GET', '/repos/szl-holdings/example')
    request = factory.return_value.open.call_args.args[0]
    assert request.full_url == 'https://api.github.com/repos/szl-holdings/example'
    assert request.get_header('Authorization') == 'Bearer fixture-token-not-a-credential'
    assert payload == {'result': True}
    assert status == 200
