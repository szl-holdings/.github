#!/usr/bin/env python3
"""Self-test for the reusable HF deployer's Dockerfile-COPY derivation.

The deployer REPLACES a hand-maintained file allowlist with a derivation from the
caller Dockerfile's own COPY sources, so the derivation IS the correctness
contract. These locks pin the parts that have already burned us:

  * `COPY --from=<stage>` must NOT contribute deploy files (build-stage
    artifacts are not repo source-of-truth files);
  * a bare `COPY . <dest>` whole-context copy must be SKIPPED, not silently
    expanded into a whole-repo mirror (the curated Space deploy is per-file);
  * a dotdir source like `.compliance/x` must survive parsing -- an earlier
    `lstrip("./")` collapsed it to `compliance/x` and dropped 5 killinchu files;
  * directory / glob / explicit-file COPY sources must each expand to the right
    concrete tracked file set, and a missing source must be reported, not pushed.

Runs with NO network (derivation + expansion are pure stdlib).
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_deploy_from_dockerfile.py")

_spec = importlib.util.spec_from_file_location("hf_deploy_from_dockerfile", _MODULE_PATH)
assert _spec and _spec.loader
dep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dep)


class TestParseCopySources(unittest.TestCase):
    def test_basic_per_file_copy(self):
        df = "FROM python:3.12\nCOPY serve.py /app/serve.py\nCOPY src /app/src\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_skips_from_stage_copy(self):
        df = (
            "FROM node AS build\n"
            "RUN echo hi\n"
            "FROM python:3.12\n"
            "COPY --from=build /out/bundle.js /app/static/bundle.js\n"
            "COPY serve.py /app/serve.py\n"
        )
        # The --from artifact must NOT appear; only the real repo source does.
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])

    def test_skips_bare_whole_context(self):
        df = "FROM python:3.12\nCOPY . /app\nCOPY serve.py /app/serve.py\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])

    def test_skips_dot_slash_whole_context(self):
        df = "FROM python:3.12\nCOPY ./ /app\n"
        self.assertEqual(dep.parse_copy_sources(df), [])

    def test_dotdir_source_preserved(self):
        # The killinchu trap: leading-dot dir must NOT be stripped to a non-dot dir.
        df = "FROM python:3.12\nCOPY .compliance/policy.json /app/.compliance/policy.json\n"
        self.assertEqual(dep.parse_copy_sources(df), [".compliance/policy.json"])

    def test_leading_dot_slash_stripped_but_dotdir_kept(self):
        df = (
            "FROM python:3.12\n"
            "COPY ./serve.py /app/serve.py\n"
            "COPY .well-known/x /app/.well-known/x\n"
        )
        self.assertEqual(
            dep.parse_copy_sources(df), ["serve.py", ".well-known/x"]
        )

    def test_line_continuation_and_multi_source(self):
        df = "FROM python:3.12\nCOPY a.py b.py \\\n     c.py /app/\n"
        self.assertEqual(dep.parse_copy_sources(df), ["a.py", "b.py", "c.py"])

    def test_json_array_form(self):
        df = 'FROM python:3.12\nCOPY ["serve.py", "src", "/app/"]\n'
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_chown_flag_dropped_source_kept(self):
        df = "FROM python:3.12\nCOPY --chown=1000:1000 serve.py /app/serve.py\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])

    def test_dedup_preserves_order(self):
        df = (
            "FROM python:3.12\n"
            "COPY serve.py /app/serve.py\n"
            "COPY src /app/src\n"
            "COPY serve.py /app/serve.py\n"
        )
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py", "src"])

    def test_comments_ignored(self):
        df = "FROM python:3.12\n# COPY ghost.py /app/ghost.py\nCOPY serve.py /app/\n"
        self.assertEqual(dep.parse_copy_sources(df), ["serve.py"])


class TestExpandSources(unittest.TestCase):
    def setUp(self):
        self.tree = {
            "serve.py": "h1",
            "src/a.py": "h2",
            "src/sub/b.py": "h3",
            "static/app.css": "h4",
            "static/img/logo.png": "h5",
            "knowledge.json": "h6",
        }

    def test_explicit_file(self):
        targets, unresolved = dep.expand_sources(["serve.py"], self.tree)
        self.assertEqual(targets, {"serve.py": "serve.py"})
        self.assertEqual(unresolved, [])

    def test_directory_expands_recursively(self):
        targets, unresolved = dep.expand_sources(["src"], self.tree)
        self.assertEqual(
            set(targets), {"src/a.py", "src/sub/b.py"}
        )
        self.assertEqual(unresolved, [])
        # copy_source recorded for prune scoping
        self.assertEqual(targets["src/a.py"], "src")

    def test_trailing_slash_directory(self):
        targets, _ = dep.expand_sources(["static/"], self.tree)
        self.assertEqual(
            set(targets), {"static/app.css", "static/img/logo.png"}
        )

    def test_glob_source(self):
        # NOTE: glob expansion uses fnmatch, whose `*` is NOT `/`-aware (unlike
        # Docker's Go filepath.Match), so `src/*.py` also matches nested files.
        # This is intentionally over-inclusive (still a strict subset of tracked
        # repo files); the real Dockerfiles use dir/file COPY, not globs.
        targets, unresolved = dep.expand_sources(["src/*.py"], self.tree)
        self.assertEqual(set(targets), {"src/a.py", "src/sub/b.py"})
        self.assertEqual(unresolved, [])

    def test_top_level_glob(self):
        targets, unresolved = dep.expand_sources(["*.json"], self.tree)
        self.assertEqual(set(targets), {"knowledge.json"})
        self.assertEqual(unresolved, [])

    def test_unresolved_source_reported_not_pushed(self):
        targets, unresolved = dep.expand_sources(["missing/thing.py"], self.tree)
        self.assertEqual(targets, {})
        self.assertEqual(unresolved, ["missing/thing.py"])


class TestDeriveReadmePolicy(unittest.TestCase):
    def _derive(self, dockerfile, files, *, include_readme, readme_path="README.md"):
        with tempfile.TemporaryDirectory() as repo_root:
            for rel, content in {"Dockerfile": dockerfile, **files}.items():
                path = os.path.join(repo_root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(content.encode("utf-8"))
            args = types.SimpleNamespace(
                repo_root=repo_root,
                dockerfile_path="Dockerfile",
                include_readme=include_readme,
                readme_path=readme_path,
                github_repo="szl-holdings/example",
                hf_repo="SZLHOLDINGS/example",
                ref="main",
            )
            return dep.derive(args)

    def test_include_readme_false_filters_explicit_copy(self):
        manifest, files = self._derive(
            "FROM scratch\n"
            "COPY README.md /app/README.md\n"
            "COPY serve.py /app/serve.py\n",
            {"README.md": "# GitHub-only README\n", "serve.py": "pass\n"},
            include_readme=False,
            readme_path="./README.md",
        )

        self.assertEqual(set(files), {"serve.py"})
        self.assertEqual(manifest["files_resolved"], 1)
        self.assertIsNone(manifest["readme"])

    def test_include_readme_false_keeps_unrelated_nested_readme(self):
        manifest, files = self._derive(
            "FROM scratch\n"
            "COPY README.md /app/README.md\n"
            "COPY docs /app/docs\n",
            {
                "README.md": "# Space-card-owned README\n",
                "docs/README.md": "# App documentation\n",
            },
            include_readme=False,
        )

        self.assertEqual(set(files), {"docs/README.md"})
        self.assertEqual(manifest["files_resolved"], 1)

    def test_include_readme_true_merges_derived_entry_as_readme(self):
        readme = "---\nsdk: docker\napp_port: 7860\n---\n# Space card\n"
        manifest, files = self._derive(
            "FROM scratch\nCOPY README.md /app/README.md\n",
            {"README.md": readme},
            include_readme=True,
        )

        self.assertEqual(set(files), {"README.md"})
        self.assertEqual(files["README.md"]["copy_source"], "(readme)")
        self.assertEqual(files["README.md"]["sha256"], dep.sha256(readme.encode()))
        self.assertEqual(manifest["readme"], "README.md")


class TestContentIdentity(unittest.TestCase):
    def test_git_blob_sha1_matches_git(self):
        # `printf '' | git hash-object --stdin` == e69de29... (empty blob)
        self.assertEqual(
            dep.git_blob_sha1(b""),
            "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        )

    def test_git_blob_sha1_hello(self):
        # `printf 'hello' | git hash-object --stdin`
        self.assertEqual(
            dep.git_blob_sha1(b"hello"),
            "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0",
        )

    def test_sha256_known(self):
        self.assertEqual(
            dep.sha256(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
