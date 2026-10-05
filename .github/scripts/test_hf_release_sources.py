#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import unittest.mock

import hf_release_sources as sources

SHA = "a" * 40
ENV = {"REVIEWED_SOURCE_SHA": SHA, "GITHUB_SHA": SHA, "GITHUB_REF": "refs/heads/main",
       "GITHUB_REPOSITORY": "szl-holdings/.github", "GITHUB_EVENT_NAME": "push"}


class SourceBindingTests(unittest.TestCase):
    def test_foreign_repository_rejected_before_network(self):
        with unittest.mock.patch.object(sources.requests, "Session") as session, self.assertRaisesRegex(RuntimeError, "REPOSITORY_REJECTED"):
            sources.protected_main("elsewhere")
        session.assert_not_called()

    def metadata(self, value, status=200):
        response = unittest.mock.MagicMock(status_code=status)
        response.iter_content.return_value = [json.dumps(value).encode()]
        session = unittest.mock.Mock(); session.get.return_value = response
        return session

    def test_exact_protected_source_get_has_no_redirect_or_ambient_credentials(self):
        session = self.metadata({"name": "main", "protected": True, "commit": {"sha": SHA}})
        with unittest.mock.patch.dict(os.environ, {}, clear=True), unittest.mock.patch.object(sources.requests, "Session", return_value=session):
            self.assertEqual(sources.protected_main("szl-lake"), SHA)
        self.assertFalse(session.trust_env)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertNotIn("Authorization", session.get.call_args.kwargs["headers"])
        self.assertEqual(session.get.call_args.args[0], "https://api.github.com/repos/szl-holdings/szl-lake/branches/main")

    def test_unprotected_malformed_or_redirected_metadata_fails(self):
        cases = [(False, SHA, 200), (1, SHA, 200), (True, "0" * 40, 200), (True, SHA, 302)]
        for protected, revision, status in cases:
            session = self.metadata({"name": "main", "protected": protected, "commit": {"sha": revision}}, status)
            with self.subTest(protected=protected, status=status), unittest.mock.patch.object(sources.requests, "Session", return_value=session), self.assertRaises(RuntimeError):
                sources.protected_main("szl-lake")

    def test_controller_mismatch_or_moved_main_rejects(self):
        for actual, remote in (("b" * 40, SHA), (SHA, "b" * 40)):
            with unittest.mock.patch.dict(os.environ, ENV, clear=True), unittest.mock.patch.object(sources, "git", return_value=actual), unittest.mock.patch.object(sources, "protected_main", return_value=remote), self.assertRaises(RuntimeError):
                sources.controller_source(operational=True)

    def test_untrusted_operational_event_rejects_even_equal_sha(self):
        with unittest.mock.patch.dict(os.environ, {**ENV, "GITHUB_EVENT_NAME": "pull_request"}, clear=True), unittest.mock.patch.object(sources, "git", return_value=SHA), unittest.mock.patch.object(sources, "protected_main") as remote, self.assertRaisesRegex(RuntimeError, "MAIN_MOVED"):
            sources.controller_source(operational=True)
        remote.assert_not_called()

    def test_changed_controller_bytes_reject_before_remote_observation(self):
        def command(*args, **kwargs):
            if args[0] == "diff":
                raise RuntimeError("SOURCE_GIT_OPERATION_FAILED")
            return SHA
        with unittest.mock.patch.dict(os.environ, ENV, clear=True), unittest.mock.patch.object(sources, "git", side_effect=command), unittest.mock.patch.object(sources, "protected_main") as remote, self.assertRaisesRegex(RuntimeError, "GIT_OPERATION_FAILED"):
            sources.controller_source(operational=True)
        remote.assert_not_called()

    def test_git_transport_drops_credentials_config_and_hooks(self):
        result = unittest.mock.Mock(returncode=0, stdout=SHA)
        with unittest.mock.patch.dict(os.environ, {"HF_TOKEN": "SYNTHETIC", "GITHUB_TOKEN": "SYNTHETIC", "GIT_CONFIG_COUNT": "1"}), unittest.mock.patch.object(sources.subprocess, "run", return_value=result) as run:
            self.assertEqual(sources.git("rev-parse", "HEAD"), SHA)
        invocation = run.call_args
        self.assertNotIn("HF_TOKEN", invocation.kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", invocation.kwargs["env"])
        self.assertNotIn("GIT_CONFIG_COUNT", invocation.kwargs["env"])
        self.assertIn("core.hooksPath=/dev/null", invocation.args[0])
        self.assertIn("protocol.file.allow=never", invocation.args[0])
        self.assertEqual(invocation.kwargs["timeout"], 180)

    def fixture(self):
        Path("reports").mkdir()
        for slug in sources.SOURCES:
            (Path("release-sources") / slug).mkdir(parents=True)
        sources.STATE.write_text(json.dumps({"schema": "szl.hf-release-source-binding/v1", "controller": SHA, "sources": {s: SHA for s in sources.SOURCES}}))

    def test_all_fixed_source_heads_and_ancestries_reverified(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            self.fixture()
            def git(*args, **kwargs):
                return SHA if args[0] == "rev-parse" else ""
            with unittest.mock.patch.object(sources, "controller_source", return_value=SHA), unittest.mock.patch.object(sources, "git", side_effect=git) as commands, unittest.mock.patch.object(sources, "protected_main", return_value=SHA) as remote:
                value = sources.verify(operational=True)
            self.assertEqual(set(value["sources"]), set(sources.SOURCES))
            self.assertEqual(remote.call_count, 3)
            self.assertEqual(sum(c.args[:2] == ("merge-base", "--is-ancestor") for c in commands.call_args_list), 3)

    def test_dirty_or_moved_source_fails_before_acknowledgement(self):
        for dirty, observed in ((" M README.md", SHA), ("", "b" * 40)):
            with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
                self.fixture()
                def git(*args, **kwargs):
                    return SHA if args[0] == "rev-parse" else dirty
                with unittest.mock.patch.object(sources, "controller_source", return_value=SHA), unittest.mock.patch.object(sources, "git", side_effect=git), unittest.mock.patch.object(sources, "protected_main", return_value=observed), self.assertRaisesRegex(RuntimeError, "MOVED_OR_DIRTY"):
                    sources.verify(operational=True)

    def test_symlink_or_unknown_binding_rejected(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            self.fixture()
            value = json.loads(sources.STATE.read_text()); value["surprise"] = True
            sources.STATE.write_text(json.dumps(value))
            with unittest.mock.patch.object(sources, "controller_source", return_value=SHA), self.assertRaisesRegex(RuntimeError, "BINDING_INVALID"):
                sources.verify()
            sources.STATE.unlink(); sources.STATE.symlink_to("missing")
            with unittest.mock.patch.object(sources, "controller_source", return_value=SHA), self.assertRaisesRegex(RuntimeError, "BINDING_INVALID"):
                sources.verify()

    def test_failed_acquisition_never_writes_binding_or_outputs(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            with unittest.mock.patch.object(sources, "controller_source", return_value=SHA), unittest.mock.patch.object(sources, "protected_main", side_effect=[SHA, "b" * 40]), unittest.mock.patch.object(sources, "git", return_value=SHA), self.assertRaisesRegex(RuntimeError, "MOVED_DURING_ACQUISITION"):
                sources.prepare()
            self.assertFalse(sources.STATE.exists())

    def test_owner_contract_commands_are_fixed_and_drop_publisher_credentials(self):
        with unittest.mock.patch.dict(os.environ, {"HF_TOKEN": "SYNTHETIC", "GITHUB_TOKEN": "SYNTHETIC"}), unittest.mock.patch.object(sources, "verify") as verified, unittest.mock.patch.object(sources.subprocess, "run") as child:
            sources.contracts(operational=True)
        self.assertEqual(verified.call_count, 2)
        self.assertEqual(child.call_count, 5)
        for call in child.call_args_list:
            self.assertNotIn("HF_TOKEN", call.kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", call.kwargs["env"])
            self.assertEqual(call.kwargs["timeout"], 300)
        commands = [c.args[0] for c in child.call_args_list]
        self.assertIn("--check-index", commands[2])
        self.assertFalse(any("--publish" in c for c in commands))

    def test_failed_owner_contract_does_not_produce_successful_readback(self):
        with unittest.mock.patch.object(sources, "verify") as verified, unittest.mock.patch.object(sources.subprocess, "run", side_effect=RuntimeError("SYNTHETIC contract failed")), self.assertRaises(RuntimeError):
            sources.contracts(operational=True)
        self.assertEqual(verified.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
