#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Network-free boundary controls, not live convergence evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.github/scripts/frontier_payload_readonly.py'
SPEC = importlib.util.spec_from_file_location('frontier_readonly_fixture', SOURCE)
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)
WORKFLOW = ROOT / '.github/workflows/frontier-payload-convergence.yml'


def step(document, name):
    marker = '      - name: ' + name + '\n'
    assert document.count(marker) == 1
    return document.split(marker, 1)[1].split('\n      - name:', 1)[0]


class WorkflowBoundaryTests(unittest.TestCase):
    def test_native_job_is_real_readonly_verification(self):
        source = WORKFLOW.read_text()
        self.assertIn('REPORT_PATH: /tmp/szl-frontier-payload-convergence-v2.json', source)
        self.assertIn('SUMMARY_PATH: /tmp/szl-frontier-payload-convergence-v2.md', source)
        self.assertNotIn('permissions: read-all', source)
        for forbidden in ('secrets.', 'github.token', 'actions: write', 'issues: write', 'gh issue comment', 'huggingface_hub', 'frontier_payload_convergence.py "'):
            self.assertNotIn(forbidden, source)
        self.assertEqual(source.count('default: false'), 2)
        self.assertNotIn('default: true', source)
        self.assertIn('python -I -P .github/scripts/test_frontier_payload_readonly.py', source)
        command = step(source, 'Execute bounded read-only verification')
        self.assertIn('python -I -P .github/scripts/frontier_payload_readonly.py', command)
        self.assertIn('--report "$REPORT_PATH" --summary "$SUMMARY_PATH"', command)
        self.assertNotIn('--apply', command)
        self.assertNotIn('--dispatch-controls', command)
        self.assertIn('exit "$code"', command)
        self.assertNotIn('exit 0', command)
        enforcement = step(source, 'Enforce public verification result')
        self.assertIn('if: always()', enforcement)
        self.assertIn('test -n "$code"', enforcement)
        self.assertIn('exit "$code"', enforcement)
        upload = step(source, 'Upload immutable convergence evidence')
        self.assertIn('if-no-files-found: error', upload)
        self.assertIn('retention-days: 90', upload)
        self.assertIn('name: frontier-payload-readonly-verification', upload)

    def test_explicit_operations_are_rejected_before_any_observation(self):
        source = WORKFLOW.read_text()
        block = step(source, 'Reject unqualified operational requests')
        script = '\n'.join(line[10:] for line in block.split('        run: |\n', 1)[1].splitlines() if line.startswith('          '))
        self.assertLess(source.index('Reject unqualified operational requests'), source.index('Execute bounded read-only verification'))
        for apply, dispatch, expected in [('false','false',0),('true','false',2),('false','true',2),('true','true',2)]:
            with self.subTest(apply=apply, dispatch=dispatch):
                result = subprocess.run(['bash','-c',script], env={'PATH':os.environ.get('PATH',''),'INPUT_APPLY':apply,'INPUT_DISPATCH':dispatch}, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected)
                if expected:
                    self.assertIn('OPERATIONAL_EFFECTS_HELD', result.stdout)

    def test_source_closure_does_not_load_mutation_controller(self):
        self.assertNotIn('frontier_payload.controls', sys.modules)
        self.assertNotIn('frontier_payload.operator', sys.modules)
        self.assertNotIn('huggingface_hub', sys.modules)


class TransportBoundaryTests(unittest.TestCase):
    def test_out_of_scope_url_is_rejected_before_transport(self):
        urls = [
            'http://127.0.0.1/', 'https://huggingface.co/api/spaces/private',
            'https://api.github.com/repos/szl-holdings/a11oy/actions/workflows/hf-sync.yml/dispatches',
            'https://huggingface.co/spaces/SZLHOLDINGS/vessels/raw/main/README.md',
            verify.KILLINCHU_SOURCE_PREFIX + 'main' + verify.KILLINCHU_SOURCE_SUFFIX,
            verify.KILLINCHU_SOURCE_PREFIX + 'd' * 40 + '/other.md',
        ]
        with unittest.mock.patch.object(verify.OPENER, 'open', side_effect=AssertionError('transport invoked')):
            for url in urls:
                with self.subTest(url=url):
                    result = verify.request_public(url, deadline=time.monotonic()+1)
                    self.assertIsNone(result['status'])
                    self.assertEqual(result['body'], b'')

    def test_native_redirect_handler_refuses_cross_scope_hop(self):
        self.assertIsNone(verify.NoRedirect().redirect_request(None,None,302,'',{},'https://unrelated.invalid'))

    def test_only_a_commit_pinned_consolidation_source_is_admitted(self):
        pinned = verify.immutable_source_url('d' * 40)
        self.assertTrue(verify._immutable_source_target(pinned))
        self.assertFalse(verify._immutable_source_target(pinned + '?ref=main'))
        self.assertFalse(verify._immutable_source_target(
            verify.KILLINCHU_SOURCE_PREFIX + 'main' + verify.KILLINCHU_SOURCE_SUFFIX
        ))

    def test_vessels_alias_observes_only_exact_same_origin_location(self):
        for location, expected in [('/elite/maritime', None), ('https://other.invalid/', 'HTTP_REDIRECT_HELD')]:
            with self.subTest(location=location):
                failure = verify.urllib.error.HTTPError(verify.VESSELS_ALIAS_URL, 308, 'Permanent Redirect', {'Location': location}, None)
                with unittest.mock.patch.object(verify.OPENER, 'open', side_effect=failure) as opened:
                    result = verify.request_public(verify.VESSELS_ALIAS_URL, deadline=time.monotonic()+1)
                self.assertEqual(opened.call_count, 1)
                self.assertEqual(result['status'], 308)
                self.assertEqual(result['location'], location)
                self.assertEqual(result['error'], expected)
                self.assertEqual(result['body'], b'')

    def test_native_total_request_timer_stops_a_stalled_read(self):
        def stall(*args, **kwargs):
            time.sleep(1)
            raise AssertionError('timer did not interrupt')
        started = time.monotonic()
        with unittest.mock.patch.object(verify, 'REQUEST_SECONDS', 0.025), unittest.mock.patch.object(verify.OPENER, 'open', side_effect=stall):
            result = verify.request_public(next(iter(verify.PUBLIC_URLS)), deadline=started+0.25)
        self.assertLess(time.monotonic()-started, 0.5)
        self.assertIsNone(result['status'])
        self.assertEqual(result['body'], b'')


class ReadbackContractTests(unittest.TestCase):
    def fixture_read(self, url, *, deadline):
        if url in verify.METADATA_URLS.values():
            repo = next(k for k, value in verify.METADATA_URLS.items() if value == url)
            body = json.dumps(verify.CONFIG.REPOSITORY_METADATA[repo]).encode()
        elif url == verify.MAIN_URL:
            body = json.dumps({"sha": "c" * 40}).encode()
        elif url == verify.KILLINCHU_MAIN_URL:
            body = json.dumps({"sha": "d" * 40}).encode()
        elif url == verify.immutable_source_url('d' * 40):
            body = ('# Vessels consolidation\nSole public Hugging Face runtime: '
                    '`SZLHOLDINGS/killinchu`\nVessels is not a standalone product\n'
                    'The replacement `/vessels` route is reachable\n').encode()
        elif url == verify.VESSELS_ALIAS_URL:
            return {"status": 308, "body": b'', "error": None, "location": "/elite/maritime", "elapsed_ms": 1}
        elif url == verify.MARITIME_URL:
            body = b'<title>killinchu Maritime Intel</title>'
        elif url == verify.KILLINCHU_BUILD_URL:
            body = json.dumps({
                'status': 'OBSERVED', 'service': 'killinchu',
                'build': {'state': 'OBSERVED', 'revision': 'd' * 40},
                'receipt_minted_on_request': False,
            }).encode()
        else:
            contract = next(item for item in verify.PROBES if item.url == url)
            if contract.json_contract == 'livez': body = json.dumps({
                'status': 'PROCESS_ALIVE', 'process': {'pid': 1},
                'scope': 'process liveness only; no dependency readiness asserted',
                'production_ready': False, 'receipt_minted': False,
            }).encode()
            elif contract.json_contract == 'readyz': body = json.dumps({
                'status': 'READY', 'ready': True,
                'components': {
                    'khipu': {'state': 'READY', 'blocking': False, 'chain_intact': True, 'durable': True},
                    'boot_preflight': {'state': 'DEGRADED', 'blocking': False},
                },
                'blocking_components': [], 'receipt_minted': False,
            }).encode()
            elif contract.json_contract == 'controller': body = b'{"organ":"a11oy","locked_formula_count":8}'
            elif contract.json_contract == 'build-info': body = json.dumps({"git_sha": "c" * 40}).encode()
            else: body = '\n'.join(contract.required_literals).encode()
        return {"status": 200, "body": body, "error": None, "elapsed_ms": 1}

    def test_process_liveness_does_not_substitute_for_readiness(self):
        livez = next(item for item in verify.PROBES if item.json_contract == 'livez')
        readyz = next(item for item in verify.PROBES if item.json_contract == 'readyz')

        def checked(contract, mutate):
            observation = self.fixture_read(contract.url, deadline=time.monotonic()+1)
            payload = json.loads(observation['body'])
            mutate(payload)
            observation['body'] = json.dumps(payload).encode()
            with unittest.mock.patch.object(verify, 'request_public', return_value=observation):
                return verify._probe(contract, deadline=time.monotonic()+1)

        self.assertTrue(checked(livez, lambda payload: None)['verified'])
        self.assertFalse(checked(livez, lambda payload: payload.update(production_ready=True))['verified'])
        self.assertFalse(checked(livez, lambda payload: payload.update(scope='full production readiness'))['verified'])
        self.assertTrue(checked(readyz, lambda payload: None)['verified'])
        self.assertFalse(checked(readyz, lambda payload: payload.update(ready=False))['verified'])
        self.assertFalse(checked(readyz, lambda payload: payload['components']['khipu'].update(durable=False))['verified'])

    def test_complete_actual_report_uses_fixed_public_reads_only(self):
        with unittest.mock.patch.object(verify, 'request_public', side_effect=self.fixture_read) as reads:
            report = verify.collect_report(deadline=time.monotonic()+10)
        self.assertEqual(reads.call_count, 19)
        self.assertEqual(report['schema'], 'szl.frontier-payload-readonly/v2')
        self.assertEqual(report['status'], 'READ_ONLY_VERIFIED')
        self.assertEqual(report['operational_effects'], 'HELD')
        self.assertFalse(report['credentials_used'])
        self.assertTrue(report['public_estate']['revision_matches'])
        self.assertTrue(report['maritime_consolidation']['verified'])
        self.assertEqual(report['maritime_consolidation']['legacy_space_retirement'], 'UNOBSERVED')
        self.assertTrue(report['maritime_consolidation']['revision_matches'])
        self.assertEqual(len(report['public_estate']['checks']), 10)
        self.assertTrue(all(not row['dispatched'] for row in report['workflow_controls']))
        self.assertTrue(all(row['state']=='UNOBSERVED' for row in report['private_spaces']))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'report.json'; summary = Path(tmp)/'summary.md'
            verify.write_report(output, summary, report)
            self.assertLess(output.stat().st_size, verify.REPORT_LIMIT)
            self.assertIn('Operational effects: **HELD**', summary.read_text())

    def test_source_route_revision_metadata_and_probe_failures_remain_nonzero(self):
        cases = [
            'main-moved', 'zero-sha', 'short-sha', 'metadata-drift',
            'killinchu-main-moved', 'killinchu-source-mismatch',
            'vessels-alias-mismatch', 'maritime-route-unavailable',
            'killinchu-build-mismatch',
        ] + [item.name for item in verify.PROBES]
        for defect in cases:
            with self.subTest(defect=defect):
                killinchu_main_reads = 0
                def read(url, *, deadline):
                    nonlocal killinchu_main_reads
                    value = self.fixture_read(url, deadline=deadline)
                    if url == verify.MAIN_URL and defect in ('main-moved','zero-sha','short-sha'):
                        value['body'] = json.dumps({'sha':{'main-moved':'d'*40,'zero-sha':'0'*40,'short-sha':'c'*7}[defect]}).encode()
                    elif url == verify.KILLINCHU_MAIN_URL:
                        killinchu_main_reads += 1
                        if defect == 'killinchu-main-moved' and killinchu_main_reads == 2:
                            value['body'] = json.dumps({'sha': 'e' * 40}).encode()
                    elif url == verify.immutable_source_url('d' * 40) and defect == 'killinchu-source-mismatch':
                        value['body'] = b'not the consolidation source'
                    elif url == verify.VESSELS_ALIAS_URL and defect == 'vessels-alias-mismatch':
                        value['location'] = 'https://other.invalid/'
                    elif url == verify.MARITIME_URL and defect == 'maritime-route-unavailable':
                        value.update(status=503, body=b'private-provider-body-canary', error='HTTP_STATUS')
                    elif url == verify.KILLINCHU_BUILD_URL and defect == 'killinchu-build-mismatch':
                        payload = json.loads(value['body']); payload['build']['revision'] = 'e' * 40
                        value['body'] = json.dumps(payload).encode()
                    elif url in verify.METADATA_URLS.values() and defect == 'metadata-drift': value['body'] = b'{}'
                    elif any(item.url == url and item.name == defect for item in verify.PROBES):
                        value.update(status=503, body=b'private-provider-body-canary', error='HTTP_STATUS')
                    return value
                with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.object(verify, 'request_public', side_effect=read):
                    output = Path(tmp)/'report.json'
                    self.assertEqual(verify.main(['--report',str(output),'--summary',str(Path(tmp)/'summary.md')]), 1)
                    report = json.loads(output.read_text())
                self.assertEqual(report['status'], 'NOT_YET_CONVERGED')
                self.assertNotIn('private-provider-body-canary', json.dumps(report))

    def test_mutation_flags_are_rejected_before_any_read(self):
        with unittest.mock.patch.object(verify, 'request_public', side_effect=AssertionError('read before argument rejection')):
            for flag in ('--apply','--dispatch-controls'):
                with self.subTest(flag=flag), self.assertRaises(SystemExit) as result:
                    verify.main(['--report','unused.json','--summary','unused.md',flag])
                self.assertEqual(result.exception.code, 2)

    def test_read_response_bound_headers_and_redirect_denial(self):
        class Response:
            status = 200
            def __init__(self, body, url): self.body, self.url = body, url
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return self.url
            def read(self, count):
                self.last_count = count
                return self.body[:count]
        url = next(iter(verify.PUBLIC_URLS))
        cases = [(b'ok', url, None), (b'x'*(verify.MAX_BYTES+1), url, 'RESPONSE_TOO_LARGE'), (b'ok', 'https://other.invalid/', 'HTTP_REDIRECT_HELD')]
        for body, result_url, error in cases:
            response = Response(body, result_url)
            with self.subTest(error=error), unittest.mock.patch.object(verify.OPENER,'open',return_value=response) as opened:
                result = verify.request_public(url, deadline=time.monotonic()+1)
                req = opened.call_args.args[0]
                self.assertEqual(req.get_method(), 'GET')
                self.assertIsNone(req.get_header('Authorization'))
                self.assertEqual(result['error'], error)
                if error: self.assertEqual(result['body'], b'')
                else: self.assertEqual(response.last_count, verify.MAX_BYTES+1)

    def test_exception_text_is_not_reported_or_retried(self):
        with unittest.mock.patch.object(verify.OPENER, 'open', side_effect=RuntimeError('private-canary')) as opened:
            result = verify.request_public(verify.MAIN_URL, deadline=time.monotonic()+1)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(result['error'], 'PUBLIC_READ_FAILED')
        self.assertNotIn('private-canary', str(result))


if __name__ == '__main__':
    unittest.main()
