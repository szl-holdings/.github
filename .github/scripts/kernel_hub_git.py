#!/usr/bin/env python3
"""Credential-safe Git transport for first-class Hugging Face Kernel repositories.

The generic ``huggingface_hub`` repository helpers currently accept model,
dataset, and Space repository types. First-class Kernel repositories therefore
use their native Git endpoint for card/contract publication while metadata is
bound independently through ``HfApi.kernel_info`` by the caller.

Only ``README.md`` and ``contract.json`` may change. The complete remote tree is
inventoried with ``git ls-tree`` without checking out kernel build blobs, and the
entire ``build/`` tree must be byte-identical before and after publication.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
ALLOWED_PATHS = frozenset({"README.md", "contract.json"})


@dataclass(frozen=True)
class KernelSnapshot:
    repo_id: str
    revision: str
    files: tuple[str, ...]
    build_tree_sha256: str
    remote_url: str


@dataclass(frozen=True)
class KernelPublication:
    repo_id: str
    before_revision: str
    revision: str
    changed: bool
    remote_file_count: int
    build_variants_preserved: bool
    card_contract_byte_parity: bool
    build_tree_sha256: str
    remote_url: str


class KernelGitError(RuntimeError):
    """Raised when the Kernel Hub Git contract fails closed."""


class KernelHubGitTransport:
    """Publish reviewed Kernel cards through authenticated Git only."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://huggingface.co/kernels",
        git_bin: str = "git",
        temp_root: str | os.PathLike[str] | None = None,
        username: str = "hf-user",
        timeout_seconds: int = 180,
    ) -> None:
        if not token:
            raise ValueError("a non-empty Kernel Hub token is required")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.git_bin = git_bin
        self.temp_root = Path(temp_root) if temp_root is not None else None
        self.username = username
        self.timeout_seconds = timeout_seconds

    def _redact(self, value: object) -> str:
        text = str(value)
        candidates = {
            self.token,
            urllib.parse.quote(self.token, safe=""),
            urllib.parse.quote_plus(self.token),
        }
        for candidate in sorted((item for item in candidates if item), key=len, reverse=True):
            text = text.replace(candidate, "[REDACTED]")
        return text

    def _repo_url(self, repo_id: str) -> str:
        if not REPO_ID.fullmatch(repo_id):
            raise ValueError(f"invalid Kernel repository id: {repo_id!r}")
        # Credentials are deliberately never embedded in this URL.
        return f"{self.base_url}/{repo_id}"

    @contextmanager
    def _auth_environment(self) -> Iterator[dict[str, str]]:
        root = tempfile.mkdtemp(prefix="szl-kernel-askpass-", dir=self.temp_root)
        askpass = Path(root) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' \"${SZL_HF_GIT_USERNAME:-hf-user}\" ;;\n"
            "  *Password*) printf '%s\\n' \"${SZL_HF_GIT_TOKEN:?missing token}\" ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        env = dict(os.environ)
        env.update(
            {
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "SZL_HF_GIT_TOKEN": self.token,
                "SZL_HF_GIT_USERNAME": self.username,
            }
        )
        try:
            yield env
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _git(
        self,
        args: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [self.git_bin, "-c", "protocol.file.allow=always", *args]
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KernelGitError(self._redact(f"Git transport failed: {exc}")) from exc
        if check and result.returncode != 0:
            detail = self._redact(
                f"Git command failed ({result.returncode}): {' '.join(command)}\n"
                f"stdout: {result.stdout[-2000:]}\n"
                f"stderr: {result.stderr[-2000:]}"
            )
            raise KernelGitError(detail)
        return result

    def _fetch_main(self, repo_id: str, root: Path) -> tuple[Path, dict[str, str]]:
        repo = root / "repo"
        repo.mkdir(parents=True, exist_ok=False)
        url = self._repo_url(repo_id)
        with self._auth_environment() as env:
            self._git(["init", "-q"], cwd=repo, env=env)
            self._git(["remote", "add", "origin", url], cwd=repo, env=env)
            self._git(
                [
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "--filter=blob:none",
                    "origin",
                    "refs/heads/main",
                ],
                cwd=repo,
                env=env,
            )
        return repo, env

    def _snapshot_from_repo(self, repo_id: str, repo: Path) -> KernelSnapshot:
        revision = self._git(["rev-parse", "FETCH_HEAD"], cwd=repo).stdout.strip().lower()
        if not SHA40.fullmatch(revision):
            raise KernelGitError(f"Kernel main lacks an immutable Git revision: {repo_id}@{revision!r}")
        files = tuple(
            line.strip()
            for line in self._git(
                ["ls-tree", "-r", "--full-tree", "--name-only", "FETCH_HEAD"],
                cwd=repo,
            ).stdout.splitlines()
            if line.strip()
        )
        build_tree = self._git(
            ["ls-tree", "-r", "--full-tree", "FETCH_HEAD", "--", "build"],
            cwd=repo,
        ).stdout
        return KernelSnapshot(
            repo_id=repo_id,
            revision=revision,
            files=files,
            build_tree_sha256=hashlib.sha256(build_tree.encode("utf-8")).hexdigest(),
            remote_url=self._repo_url(repo_id),
        )

    def snapshot(self, repo_id: str) -> KernelSnapshot:
        with tempfile.TemporaryDirectory(prefix="szl-kernel-snapshot-", dir=self.temp_root) as raw:
            repo, _ = self._fetch_main(repo_id, Path(raw))
            return self._snapshot_from_repo(repo_id, repo)

    def _sparse_checkout(self, repo_id: str, root: Path) -> Path:
        repo, _ = self._fetch_main(repo_id, root)
        with self._auth_environment() as env:
            self._git(["sparse-checkout", "init", "--no-cone"], cwd=repo, env=env)
            self._git(
                ["sparse-checkout", "set", "README.md", "contract.json"],
                cwd=repo,
                env=env,
            )
            self._git(["checkout", "-q", "-B", "main", "FETCH_HEAD"], cwd=repo, env=env)
        return repo

    @staticmethod
    def _changed_paths(status: str) -> set[str]:
        paths: set[str] = set()
        for line in status.splitlines():
            if not line:
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            paths.add(path.strip('"'))
        return paths

    def _read_main_files(self, repo_id: str, expected_revision: str) -> dict[str, bytes]:
        with tempfile.TemporaryDirectory(prefix="szl-kernel-readback-", dir=self.temp_root) as raw:
            repo, _ = self._fetch_main(repo_id, Path(raw))
            observed = self._git(["rev-parse", "FETCH_HEAD"], cwd=repo).stdout.strip().lower()
            if observed != expected_revision:
                raise KernelGitError(
                    f"Kernel main moved during readback: expected {expected_revision}, observed {observed}"
                )
            output: dict[str, bytes] = {}
            with self._auth_environment() as env:
                for path in sorted(ALLOWED_PATHS):
                    result = subprocess.run(
                        [self.git_bin, "-c", "protocol.file.allow=always", "show", f"FETCH_HEAD:{path}"],
                        cwd=repo,
                        env=env,
                        capture_output=True,
                        timeout=self.timeout_seconds,
                        check=False,
                    )
                    if result.returncode != 0:
                        raise KernelGitError(
                            self._redact(
                                f"Kernel readback failed for {repo_id}/{path}: "
                                f"{result.stderr.decode('utf-8', errors='replace')[-1000:]}"
                            )
                        )
                    output[path] = result.stdout
            return output

    def publish(
        self,
        *,
        repo_id: str,
        source_dir: str | os.PathLike[str],
        metadata_revision: str,
        metadata_revision_after: Callable[[], str] | None = None,
        generation: str = "manual",
    ) -> KernelPublication:
        source_root = Path(source_dir)
        source_bytes: dict[str, bytes] = {}
        for path in sorted(ALLOWED_PATHS):
            file_path = source_root / path
            if not file_path.is_file():
                raise KernelGitError(f"reviewed Kernel source is missing {file_path}")
            source_bytes[path] = file_path.read_bytes()

        before = self.snapshot(repo_id)
        expected_metadata = str(metadata_revision or "").strip().lower()
        if before.revision != expected_metadata:
            raise KernelGitError(
                "Kernel metadata/Git mismatch before publication: "
                f"metadata={expected_metadata!r}; git_main={before.revision!r}; repo={repo_id}"
            )
        if not any(path.startswith("build/") for path in before.files):
            raise KernelGitError(f"Kernel repository has no retained build variants: {repo_id}")
        if not ALLOWED_PATHS.issubset(before.files):
            raise KernelGitError(f"Kernel repository lacks card/contract paths: {repo_id}")

        with tempfile.TemporaryDirectory(prefix="szl-kernel-publish-", dir=self.temp_root) as raw:
            repo = self._sparse_checkout(repo_id, Path(raw))
            checkout_revision = self._git(["rev-parse", "HEAD"], cwd=repo).stdout.strip().lower()
            if checkout_revision != before.revision:
                raise KernelGitError(
                    f"sparse checkout revision mismatch: {checkout_revision} != {before.revision}"
                )
            for path, data in source_bytes.items():
                (repo / path).write_bytes(data)

            status = self._git(
                ["status", "--porcelain=v1", "--untracked-files=all"], cwd=repo
            ).stdout
            changed_paths = self._changed_paths(status)
            unexpected = changed_paths - ALLOWED_PATHS
            if unexpected:
                raise KernelGitError(
                    f"refusing non-card Kernel mutation: {sorted(unexpected)}"
                )
            changed = bool(changed_paths)
            if changed:
                with self._auth_environment() as env:
                    self._git(["config", "user.name", "szl-release-bot"], cwd=repo, env=env)
                    self._git(
                        [
                            "config",
                            "user.email",
                            "41898282+github-actions[bot]@users.noreply.github.com",
                        ],
                        cwd=repo,
                        env=env,
                    )
                    self._git(["add", "--", *sorted(ALLOWED_PATHS)], cwd=repo, env=env)
                    staged = set(
                        line.strip()
                        for line in self._git(
                            ["diff", "--cached", "--name-only"], cwd=repo, env=env
                        ).stdout.splitlines()
                        if line.strip()
                    )
                    if not staged or not staged.issubset(ALLOWED_PATHS):
                        raise KernelGitError(
                            f"staged Kernel mutation is outside the card contract: {sorted(staged)}"
                        )
                    self._git(
                        [
                            "commit",
                            "-q",
                            "-m",
                            f"release(card): publish reviewed Kernel contract {generation[:12]}",
                            "-m",
                            "Card/contract-only update; first-class build variants are preserved.",
                            "-m",
                            "Signed-off-by: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>",
                        ],
                        cwd=repo,
                        env=env,
                    )
                    self._git(["push", "--quiet", "origin", "HEAD:refs/heads/main"], cwd=repo, env=env)

        after = self.snapshot(repo_id)
        if before.build_tree_sha256 != after.build_tree_sha256:
            raise KernelGitError(
                f"Kernel build tree changed during card publication: {repo_id}"
            )
        if not any(path.startswith("build/") for path in after.files):
            raise KernelGitError(f"Kernel build variants disappeared: {repo_id}")
        if metadata_revision_after is not None:
            metadata_after = str(metadata_revision_after() or "").strip().lower()
            if metadata_after != after.revision:
                raise KernelGitError(
                    "Kernel metadata/Git mismatch after publication: "
                    f"metadata={metadata_after!r}; git_main={after.revision!r}; repo={repo_id}"
                )

        observed = self._read_main_files(repo_id, after.revision)
        parity = all(observed[path] == source_bytes[path] for path in ALLOWED_PATHS)
        if not parity:
            raise KernelGitError(f"Kernel card/contract readback differs from reviewed source: {repo_id}")

        return KernelPublication(
            repo_id=repo_id,
            before_revision=before.revision,
            revision=after.revision,
            changed=changed,
            remote_file_count=len(after.files),
            build_variants_preserved=True,
            card_contract_byte_parity=True,
            build_tree_sha256=after.build_tree_sha256,
            remote_url=after.remote_url,
        )
