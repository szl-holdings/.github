#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from kernel_hub_git import KernelGitError, KernelHubGitTransport


def git(*args: str, cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-c", "protocol.file.allow=always", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


class KernelHubGitTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.remotes = self.root / "kernels"
        self.remotes.mkdir()
        self.repo_id = "SZLHOLDINGS/example-kernel"
        self.remote = self.remotes / "SZLHOLDINGS" / "example-kernel"
        self.remote.parent.mkdir(parents=True)
        git("init", "--bare", "-q", str(self.remote))
        seed = self.root / "seed"
        git("init", "-q", str(seed))
        git("config", "user.name", "tester", cwd=seed)
        git("config", "user.email", "tester@example.com", cwd=seed)
        (seed / "build" / "torch27-cpu").mkdir(parents=True)
        (seed / "build" / "torch27-cpu" / "__init__.py").write_text("BUILD = 'immutable'\n")
        (seed / "README.md").write_text("old card\n")
        (seed / "contract.json").write_text('{"repo_id":"SZLHOLDINGS/example-kernel"}\n')
        git("add", ".", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        git("branch", "-M", "main", cwd=seed)
        git("remote", "add", "origin", self.remote.as_uri(), cwd=seed)
        git("push", "-q", "origin", "main", cwd=seed)
        git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.remote)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "README.md").write_text("new governed card\n")
        (self.source / "contract.json").write_text('{"repo_id":"SZLHOLDINGS/example-kernel","v":2}\n')
        self.transport = KernelHubGitTransport(
            token="top-secret-token",
            base_url=self.remotes.as_uri(),
            temp_root=self.root,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def head(self) -> str:
        return git("rev-parse", "refs/heads/main", cwd=self.remote).stdout.strip()

    def tree(self, revision: str, path: str) -> str:
        return git("ls-tree", "-r", revision, "--", path, cwd=self.remote).stdout

    def test_card_contract_publication_preserves_complete_build_tree(self) -> None:
        before = self.head()
        before_build = self.tree(before, "build")
        result = self.transport.publish(
            repo_id=self.repo_id,
            source_dir=self.source,
            metadata_revision=before,
            metadata_revision_after=self.head,
            generation="a" * 40,
        )
        self.assertTrue(result.changed)
        self.assertNotEqual(before, result.revision)
        self.assertEqual(before_build, self.tree(result.revision, "build"))
        self.assertTrue(result.build_variants_preserved)
        self.assertTrue(result.card_contract_byte_parity)
        self.assertNotIn("top-secret-token", result.remote_url)

    def test_noop_publication_creates_no_commit(self) -> None:
        first = self.transport.publish(
            repo_id=self.repo_id,
            source_dir=self.source,
            metadata_revision=self.head(),
            metadata_revision_after=self.head,
        )
        second = self.transport.publish(
            repo_id=self.repo_id,
            source_dir=self.source,
            metadata_revision=first.revision,
            metadata_revision_after=self.head,
        )
        self.assertFalse(second.changed)
        self.assertEqual(first.revision, second.revision)

    def test_metadata_git_mismatch_fails_before_mutation(self) -> None:
        before = self.head()
        with self.assertRaisesRegex(KernelGitError, "metadata/Git mismatch before"):
            self.transport.publish(
                repo_id=self.repo_id,
                source_dir=self.source,
                metadata_revision="0" * 40,
            )
        self.assertEqual(before, self.head())

    def test_missing_build_variants_fail_closed(self) -> None:
        work = self.root / "remove-build"
        git("clone", "-q", self.remote.as_uri(), str(work))
        git("config", "user.name", "tester", cwd=work)
        git("config", "user.email", "tester@example.com", cwd=work)
        git("rm", "-q", "-r", "build", cwd=work)
        git("commit", "-q", "-m", "remove build", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        with self.assertRaisesRegex(KernelGitError, "no retained build variants"):
            self.transport.publish(
                repo_id=self.repo_id,
                source_dir=self.source,
                metadata_revision=self.head(),
            )

    def test_rejected_push_redacts_token(self) -> None:
        hooks = self.remote / "hooks"
        hook = hooks / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            "echo 'rejecting token top-secret-token' >&2\n"
            "exit 1\n"
        )
        hook.chmod(0o755)
        with self.assertRaises(KernelGitError) as captured:
            self.transport.publish(
                repo_id=self.repo_id,
                source_dir=self.source,
                metadata_revision=self.head(),
            )
        self.assertNotIn("top-secret-token", str(captured.exception))
        self.assertIn("[REDACTED]", str(captured.exception))

    def test_sparse_checkout_contains_only_allowed_worktree_files(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as raw:
            repo = self.transport._sparse_checkout(self.repo_id, pathlib.Path(raw))
            visible = {
                str(path.relative_to(repo))
                for path in repo.rglob("*")
                if path.is_file() and ".git" not in path.parts
            }
        self.assertEqual(visible, {"README.md", "contract.json"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
