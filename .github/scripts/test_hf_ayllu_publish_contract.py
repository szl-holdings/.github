"""Network-free invocation and executable-workflow checks for Ayllu publication."""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name('hf_ayllu_publish_contract.py')
SPEC = importlib.util.spec_from_file_location('ayllu_contract', SCRIPT)
assert SPEC and SPEC.loader
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)

# Derived from szl-holdings/ayllu .hf-space.json at e9a48b261348b0b08e36810ba10aa67952972090.
ROUTES = ['/healthz', '/', '/counsel', '/psyche', '/health', '/readyz',
          '/api/v1/ayllu/roster', '/api/v1/ayllu/manifest',
          '/api/v1/counsel/allodial', '/api/v1/psyche/health']

def publication():
    return dict(WORKFLOW_REPOSITORY='szl-holdings/.github', WORKFLOW_SHA='1'*40,
        CALLER_REPOSITORY='szl-holdings/ayllu',
        CALLER_WORKFLOW_REF='szl-holdings/ayllu/.github/workflows/hf-space.yml@refs/heads/main',
        EVENT_SHA='2'*40, EVENT_REF='refs/heads/main', EVENT_NAME='push',
        CONTRACT_ONLY='false', HF_REPO='SZLHOLDINGS/ayllu', DEPLOY_REF='2'*40,
        REQUIRE_TIP='true', DOCKERFILE='Dockerfile', SOURCE_REVISION_FILE='',
        SOURCE_VARIABLE='', SOURCE_PROBE='', INCLUDE_README='true',
        SMOKE_PATHS=json.dumps(ROUTES), PRUNE='true', RESTART='false', WAIT_RUNNING='900')

class AylluAdmission(unittest.TestCase):
    def test_current_push_and_dispatch_contract(self):
        for event in ('push', 'workflow_dispatch'):
            with self.subTest(event=event):
                env = publication(); env['EVENT_NAME'] = event
                self.assertEqual(CONTRACT.validate(env), 'CANONICAL_AYLLU_PUBLICATION')

    def test_retarget_replay_and_effect_changes_are_rejected(self):
        changes = dict(WORKFLOW_REPOSITORY='attacker/.github', WORKFLOW_SHA='main',
            CALLER_REPOSITORY='szl-holdings/a11oy',
            CALLER_WORKFLOW_REF='szl-holdings/ayllu/.github/workflows/other.yml@refs/heads/main',
            EVENT_SHA='main', EVENT_REF='refs/heads/feature', EVENT_NAME='pull_request',
            CONTRACT_ONLY='maybe', HF_REPO='SZLHOLDINGS/a11oy', DEPLOY_REF='3'*40,
            REQUIRE_TIP='false', DOCKERFILE='other/Dockerfile', SOURCE_REVISION_FILE='NEW',
            SOURCE_VARIABLE='NEW', SOURCE_PROBE='/api/build-info', INCLUDE_README='false',
            PRUNE='false', RESTART='true', WAIT_RUNNING='1200')
        for field, value in changes.items():
            with self.subTest(field=field):
                env = publication(); env[field] = value
                with self.assertRaisesRegex(ValueError, field): CONTRACT.validate(env)

    def test_every_publication_input_is_required(self):
        for field in publication():
            with self.subTest(field=field):
                env = publication(); del env[field]
                with self.assertRaises(ValueError): CONTRACT.validate(env)

    def test_smoke_subset_reorder_retarget_and_malformed_json_are_rejected(self):
        for routes in ['bad-json', '{}', 'null', '[]', json.dumps(ROUTES[:-1]),
                       json.dumps(ROUTES[::-1]), json.dumps(ROUTES+['https://attacker.example'])]:
            with self.subTest(routes=routes):
                env = publication(); env['SMOKE_PATHS'] = routes
                with self.assertRaisesRegex(ValueError, 'SMOKE_PATHS'): CONTRACT.validate(env)

    def test_readonly_witness_is_exact_source_and_org_local(self):
        env = publication()
        env.update(CALLER_REPOSITORY='szl-holdings/.github', EVENT_SHA='1'*40,
                   CONTRACT_ONLY='true', HF_REPO='', DEPLOY_REF='main', REQUIRE_TIP='false',
                   PRUNE='false', SMOKE_PATHS='["/"]',
                   CALLER_WORKFLOW_REF='szl-holdings/.github/.github/workflows/reusable-hf-deploy-ayllu-source-witness.yml@refs/heads/main')
        self.assertEqual(CONTRACT.validate(env), 'READ_ONLY_AYLLU_EXACT_SOURCE_CONTRACT')
        for field, value in [('EVENT_SHA', '2'*40), ('CALLER_REPOSITORY', 'szl-holdings/ayllu'),
                             ('EVENT_NAME', 'pull_request'), ('HF_REPO', 'SZLHOLDINGS/ayllu'),
                             ('CALLER_WORKFLOW_REF', 'attacker/workflow@refs/heads/main'),
                             ('EVENT_REF', 'refs/tags/release'), ('PRUNE', 'true'),
                             ('RESTART', 'true'), ('SOURCE_VARIABLE', 'UNREVIEWED')]:
            with self.subTest(field=field):
                altered = dict(env); altered[field] = value
                with self.assertRaisesRegex(ValueError, field): CONTRACT.validate(altered)

class WorkflowBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/reusable-hf-deploy-ayllu.yml').read_text()

    def test_writer_dependency_lock_and_credential_separation(self):
        invocation, writer = self.workflow.split('  hf-deploy:', 1)
        self.assertNotIn('${{ secrets.HF_TOKEN }}', invocation)
        self.assertIn('needs: invocation', writer)
        self.assertIn('if: ${{ inputs.contract-only == false }}', writer)
        self.assertIn('group: hf-deploy-SZLHOLDINGS/ayllu', invocation)
        self.assertIn('cancel-in-progress: false', invocation)
        self.assertIn('repository: szl-holdings/ayllu', writer)
        self.assertIn('ref: ${{ github.sha }}', writer)
        self.assertIn('CALLER_WORKFLOW_REF: ${{ github.workflow_ref }}', invocation)

    def test_exact_publication_and_readback_arguments(self):
        from_source = self.workflow.split('- name: Deploy Dockerfile-derived files to the Space',1)[1]
        deploy, after = from_source.split('- name: Verify exact running commit, bytes, and smoke routes',1)
        for arg in ['--github-repo szl-holdings/ayllu','--hf-repo SZLHOLDINGS/ayllu',
                    '--ref "$SOURCE_SHA"', '--source-sha "$SOURCE_SHA"',
                    '--dockerfile-path Dockerfile', '--include-readme true',
                    '--require-default-branch-tip', '--prune']:
            self.assertIn(arg, deploy)
        match = re.search(r"--smoke-paths '([^']+)'", deploy)
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match.group(1)), ROUTES)
        self.assertIn('--attest', after)
        self.assertIn('--manifest hf-deploy-manifest.json', after)
        self.assertIn('--hf-repo SZLHOLDINGS/ayllu', after)
        self.assertNotIn('hf_space_source_binding.py', self.workflow)
        self.assertNotIn('--restart-space', self.workflow)

    def test_immutable_runtime_and_artifact_contract(self):
        self.assertIn('python-version: "3.12.14"', self.workflow)
        self.assertIn('--require-hashes --only-binary=:all:', self.workflow)
        self.assertIn('-r tools/requirements/hf-publisher.lock', self.workflow)
        self.assertIn('name: hf-deploy-evidence\n', self.workflow)
        self.assertIn('if-no-files-found: error', self.workflow)
        actions = re.findall(r'uses: ([^\s]+)', self.workflow)
        self.assertTrue(actions)
        for action in actions:
            with self.subTest(action=action): self.assertRegex(action, r'@[0-9a-f]{40}$')

if __name__ == '__main__': unittest.main()
