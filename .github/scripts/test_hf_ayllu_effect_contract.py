"""Exact Ayllu source closure; fixtures never contact GitHub or Hugging Face."""
import copy
import importlib.util
import json
import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import control_plane_effect_gate as gate


class AylluEffectContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / gate.DEFAULT_POLICY_PATH).read_text())
        cls.source = (ROOT / gate.AYLLU_PUBLISHER).read_text()
        cls.witness = (ROOT / gate.AYLLU_WITNESS).read_text()

    def bound(self, path=None, source=None, changed_dependencies=None, declaration=None):
        path = path or gate.AYLLU_PUBLISHER
        source = source if source is not None else self.source
        analysis = gate.analyze_workflow_source(source, path=path)
        dependencies = {p: (ROOT/p).read_bytes() for p in analysis['dependencies'] if (ROOT/p).is_file()}
        dependencies.update(changed_dependencies or {})
        decl = declaration or self.policy['workflow_declarations'][path]
        return gate.bind_declaration(path, source.encode(), analysis, decl, dependencies)

    def test_publisher_declares_only_exact_commit_prune_artifact_and_telemetry(self):
        result = self.bound()
        self.assertEqual(result['verdict'], 'ALLOW', result['reason_codes'])
        self.assertEqual(result['external_write_sites'], 4)
        writes = {(e['sink'],e['resource']) for e in result['effects'] if e['access']=='external-write'}
        self.assertEqual(writes, {
            ('sdk.repository.create_commit','huggingface:space:SZLHOLDINGS/ayllu'),
            ('hf.space.files.prune','huggingface:space:SZLHOLDINGS/ayllu:copy-derived-files'),
            ('github.artifact.upload','github:repository:szl-holdings/ayllu:artifact:hf-deploy-evidence'),
            ('runner.guard.telemetry','stepsecurity:monitor:szl-holdings/ayllu'),
        })
        self.assertEqual({d['path'] for d in result['dependencies']}, gate.AYLLU_TOOLS)

    def test_read_only_witness_has_only_two_contents_reads(self):
        result=self.bound(gate.AYLLU_WITNESS,self.witness)
        self.assertEqual(result['verdict'],'ALLOW',result['reason_codes'])
        self.assertEqual(result['external_write_sites'],0)
        self.assertEqual(len(result['effects']),2)
        self.assertEqual({e['sink'] for e in result['effects']},{'github.contents.checkout'})
        self.assertEqual(result['credential_names'],['GITHUB_TOKEN'])

    def test_changed_workflow_never_receives_the_exact_source_exception(self):
        changes = [
            ('repository: szl-holdings/ayllu','repository: attacker/ayllu'),
            ('--hf-repo SZLHOLDINGS/ayllu','--hf-repo SZLHOLDINGS/other'),
            ('ref: ${{ job.workflow_sha }}','ref: main'),
            ('hf-deploy-SZLHOLDINGS/ayllu','hf-deploy-SZLHOLDINGS/other'),
            ('--require-default-branch-tip','--restart-space'),
            ('if: ${{ inputs.contract-only == false }}','if: ${{ always() }}'),
            ('--attest','--restart-space'),
            ('name: hf-deploy-evidence','name: other-evidence'),
            ('--prune','--dry-run'),
            ('# Sole reusable publisher','# Unreviewed source'),
        ]
        for old,new in changes:
            with self.subTest(old=old):
                self.assertIn(old,self.source)
                result=self.bound(source=self.source.replace(old,new,1))
                self.assertEqual(result['verdict'],'DENY')
                self.assertIn('WORKFLOW_DIGEST_MISMATCH',result['reason_codes'])
                self.assertIn('UNREVIEWABLE_EFFECT_BOUNDARY',result['reason_codes'])

    def test_every_source_dependency_is_bound_and_helper_change_cannot_hide_restart(self):
        for path in gate.AYLLU_TOOLS:
            with self.subTest(path=path):
                data=(ROOT/path).read_bytes()+b'\n# unreviewed\n'
                result=self.bound(changed_dependencies={path:data})
                self.assertEqual(result['verdict'],'DENY')
                self.assertTrue({'REVIEWED_UNKNOWN_PIN_MISMATCH','UNREVIEWABLE_EFFECT_BOUNDARY'} & set(result['reason_codes']))
                if path==gate.AYLLU_DEPLOY_HELPER:
                    self.assertIn('UNDECLARED_EFFECT',result['reason_codes'])
                    self.assertIn('UNREVIEWABLE_EFFECT_BOUNDARY',result['reason_codes'])

    def test_read_only_witness_cannot_select_publication_or_another_callee(self):
        for old,new in [('contract-only: true','contract-only: false'),
                        ('HF_TOKEN: ${{ github.token }}','HF_TOKEN: ${{ secrets.HF_TOKEN }}'),
                        ('reusable-hf-deploy-ayllu.yml','reusable-hf-deploy.yml')]:
            with self.subTest(old=old):
                result=self.bound(gate.AYLLU_WITNESS,self.witness.replace(old,new))
                self.assertEqual(result['verdict'],'DENY')
                self.assertIn('UNREVIEWABLE_EFFECT_BOUNDARY',result['reason_codes'])
        result=self.bound(gate.AYLLU_WITNESS,self.witness,{gate.AYLLU_PUBLISHER:self.source.encode()+b'\n'})
        self.assertEqual(result['verdict'],'DENY')

    def test_missing_prune_declaration_is_denied(self):
        decl=copy.deepcopy(self.policy['workflow_declarations'][gate.AYLLU_PUBLISHER])
        decl['effects']=[e for e in decl['effects'] if e['sink']!='hf.space.files.prune']
        result=self.bound(declaration=decl)
        self.assertIn('UNDECLARED_EFFECT',result['reason_codes'])

    def test_exact_cli_reaches_only_deploy_or_attest_never_restart(self):
        spec=importlib.util.spec_from_file_location('ayllu_deployer',ROOT/gate.AYLLU_DEPLOY_HELPER)
        deployer=importlib.util.module_from_spec(spec);spec.loader.exec_module(deployer)
        workflow,_=gate.parse_workflow_yaml(self.source)
        blocks=[step['run'] for step in workflow['jobs']['hf-deploy']['steps']
                if gate.AYLLU_DEPLOY_HELPER in step.get('run','')]
        self.assertEqual(len(blocks),2)
        for block,expected in zip(blocks,('deploy','attest')):
            words=shlex.split(block.replace('\\\n',' '))
            args=words[words.index('tools/'+gate.AYLLU_DEPLOY_HELPER)+1:]
            with self.subTest(mode=expected), patch.object(deployer,'deploy',return_value=0) as deploy, \
                 patch.object(deployer,'attest',return_value=0) as attest, \
                 patch.object(deployer,'restart_from_manifest',side_effect=AssertionError('restart')), \
                 patch.object(deployer,'restart_space',side_effect=AssertionError('restart')):
                args=[x.replace('${WAIT_RUNNING}','900').replace('$SOURCE_SHA','a'*40) for x in args]
                self.assertEqual(deployer.main(args),0)
                self.assertEqual(deploy.call_count,expected=='deploy')
                self.assertEqual(attest.call_count,expected=='attest')


if __name__=='__main__':
    unittest.main()
