#!/usr/bin/env python3
"""Self-test for the UDSBundle GHCR reference guard.

``bundle_ref_check.py`` catches the recurring bug where a public UDSBundle
points at an SZL-owned GHCR package/tag that was never published — an unreachable
OWNED ref is an ERROR and must fail the run. The severity logic (owned
unreachable -> error; external unreachable -> warn unless --fail-on-external)
and the org-sweep no-token guard are the load-bearing parts; a refactor could
quietly downgrade an owned miss to a warning (false green).

The GHCR network probe (``probe_ref``) is stubbed so this runs with NO network,
driving the REAL ``--local`` bundle parser + ``scan_text`` + ``assign_severity``
path, and pins:

  1. owned, unreachable ref                                    -> exit 1
  2. external, unreachable ref (default)                       -> exit 0 (warn)
  3. external, unreachable ref + --fail-on-external            -> exit 1
  4. every ref reachable                                       -> exit 0
  5. org-sweep (no --local) with no token                      -> exit 2
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "bundle_ref_check.py")

_spec = importlib.util.spec_from_file_location("bundle_ref_check", _MODULE_PATH)
assert _spec and _spec.loader
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)

_TOKEN_ENV = ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def _bundle(repository):
    return (
        "kind: UDSBundle\n"
        "metadata:\n"
        "  name: test-bundle\n"
        "  architecture: amd64\n"
        "packages:\n"
        "  - name: pkg1\n"
        f"    repository: {repository}\n"
        "    ref: 1.0.0\n"
    )


def _checkout(repository):
    d = tempfile.mkdtemp(prefix="brc-test-")
    with open(os.path.join(d, "uds-bundle.yaml"), "w", encoding="utf-8") as fh:
        fh.write(_bundle(repository))
    return d


def _probe(state, owned, http=404):
    return lambda repository, ref, arch, pat, timeout: {
        "state": state, "http": http, "resolved_tag": None, "owned": owned,
    }


def _run_local(root, *, probe, extra_argv=()):
    saved = brc.probe_ref
    saved_argv = sys.argv
    try:
        brc.probe_ref = probe
        sys.argv = ["bundle_ref_check.py", "--local", root,
                    "--allowlist", os.path.join(_HERE, "no-allow.json"),
                    *extra_argv]
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return brc.main()
    finally:
        brc.probe_ref = saved
        sys.argv = saved_argv


class TestBundleRefGuard(unittest.TestCase):
    def test_owned_unreachable_fails(self):
        d = _checkout("oci://ghcr.io/szl-holdings/foo")
        try:
            rc = _run_local(d, probe=_probe("unreachable", owned=True))
            self.assertEqual(rc, 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_external_unreachable_warns_only(self):
        """An unreachable EXTERNAL ref is a warning by default -> exit 0 (we
        cannot publish other people's images)."""
        d = _checkout("oci://ghcr.io/defenseunicorns/bar")
        try:
            rc = _run_local(d, probe=_probe("unreachable", owned=False))
            self.assertEqual(rc, 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_external_unreachable_with_flag_fails(self):
        d = _checkout("oci://ghcr.io/defenseunicorns/bar")
        try:
            rc = _run_local(d, probe=_probe("unreachable", owned=False),
                            extra_argv=("--fail-on-external",))
            self.assertEqual(rc, 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_all_reachable_passes(self):
        d = _checkout("oci://ghcr.io/szl-holdings/foo")
        try:
            rc = _run_local(d, probe=_probe("reachable", owned=True, http=200))
            self.assertEqual(rc, 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_org_sweep_without_token_exit_2(self):
        """Org-sweep mode with no token cannot list repos -> must abort (exit 2),
        never silently sweep nothing and report green."""
        saved_env = {k: os.environ.get(k) for k in _TOKEN_ENV}
        saved_argv = sys.argv
        try:
            for k in _TOKEN_ENV:
                os.environ.pop(k, None)
            sys.argv = ["bundle_ref_check.py",
                        "--allowlist", os.path.join(_HERE, "no-allow.json")]
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = brc.main()
            self.assertEqual(rc, 2)
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            sys.argv = saved_argv


if __name__ == "__main__":
    unittest.main(verbosity=2)
