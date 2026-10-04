#!/usr/bin/env python3
"""Run the existing terminal contracts with network/process effects denied.

This fixed PR-only entrypoint never runs the operational terminal CLI. The
audit hook lives for this process, including imports and worker threads.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


class ExternalEffectDenied(RuntimeError):
    pass


def deny_external(event, args):
    if (event.startswith("socket.") or event.startswith("subprocess.")
            or event in {"os.system", "os.posix_spawn", "os.exec", "os.fork", "os.forkpty"}):
        raise ExternalEffectDenied("OFFLINE_TERMINAL_TEST_EXTERNAL_EFFECT_DENIED")


def main():
    if len(sys.argv) != 1:
        raise RuntimeError("OFFLINE_TERMINAL_TEST_ARGUMENTS_REJECTED")
    for name in ("HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "SZL_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            raise RuntimeError("OFFLINE_TERMINAL_TEST_CREDENTIAL_REJECTED")
    sys.addaudithook(deny_external)
    # Real negative controls execute after hook installation, before source tests.
    import socket
    import subprocess
    for action in (
        lambda: socket.socket(),
        lambda: socket.getaddrinfo("example.invalid", 443),
        lambda: subprocess.run(["git", "--version"], check=True),
    ):
        try:
            action()
        except ExternalEffectDenied:
            continue
        raise RuntimeError("OFFLINE_TERMINAL_TEST_DENIAL_CONTROL_FAILED")
    path = Path(__file__).with_name("test_hf_release_readiness_terminal.py")
    sys.argv = [str(path)]
    runpy.run_path(str(path), run_name="__main__")


if __name__ == "__main__":
    main()
