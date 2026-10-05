#!/usr/bin/env python3
"""Acquire the three existing public source owners at observed protected-main SHAs.

No Hugging Face credential is read. This replaces mutable cross-repository checkout
actions with explicit source observations, fixed Git targets and final readback.
It does not claim an atomic lease over independently protected repositories.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import requests

SOURCES = {
    "lake": ("szl-lake", "9c3819e3eb65af862aa0234db7e595c4e423932a"),
    "energy": ("szl-energy-attest", "14c1d8fdbb19dbd69f4dfc365d7f74d515bc4bdb"),
    "lambda-gate": ("szl-lambda-gate", "8b95ca47571fda65a52b0b6189677ec089a6e503"),
}
SHA = re.compile(r"[0-9a-f]{40}")
STATE = Path("reports/hf-release-source-binding.json")


def revision(value):
    if not isinstance(value, str) or SHA.fullmatch(value) is None or value == "0" * 40:
        raise RuntimeError("SOURCE_REVISION_INVALID")
    return value


def protected_main(repository):
    if repository not in {".github", *(value[0] for value in SOURCES.values())}:
        raise RuntimeError("SOURCE_REPOSITORY_REJECTED")
    session = requests.Session()
    session.trust_env = False
    try:
        headers = {"Accept": "application/vnd.github+json", "Cache-Control": "no-cache"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        deadline = time.monotonic() + 60
        response = session.get(
            f"https://api.github.com/repos/szl-holdings/{repository}/branches/main",
            headers=headers,
            timeout=(10, 20), allow_redirects=False, stream=True,
        )
        with response:
            if response.status_code != 200:
                raise RuntimeError("SOURCE_METADATA_UNAVAILABLE")
            chunks = []; size = 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 131072 or time.monotonic() > deadline:
                    raise RuntimeError("SOURCE_METADATA_TOO_LARGE")
                chunks.append(chunk)
        if time.monotonic() > deadline:
            raise RuntimeError("SOURCE_METADATA_DEADLINE")
        value = json.loads(b"".join(chunks))
        if value.get("name") != "main" or value.get("protected") is not True:
            raise RuntimeError("SOURCE_MAIN_NOT_PROTECTED")
        return revision(value["commit"]["sha"])
    finally:
        session.close()


def git(*arguments, cwd=None):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"})
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
         "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", *arguments],
        cwd=cwd, env=env, check=False, capture_output=True, text=True, timeout=180,
    )
    if result.returncode:
        raise RuntimeError("SOURCE_GIT_OPERATION_FAILED")
    return result.stdout.strip()


def controller_source(*, operational):
    expected = revision(os.environ.get("REVIEWED_SOURCE_SHA"))
    if git("rev-parse", "HEAD") != expected or os.environ.get("GITHUB_REPOSITORY") != "szl-holdings/.github":
        raise RuntimeError("CONTROLLER_SOURCE_MISMATCH")
    git("diff", "--quiet", "HEAD", "--", ".github/scripts", ".github/workflows")
    if operational and (os.environ.get("GITHUB_REF") != "refs/heads/main"
                        or os.environ.get("GITHUB_SHA") != expected
                        or os.environ.get("GITHUB_EVENT_NAME") not in {"push", "schedule", "repository_dispatch", "workflow_dispatch"}
                        or protected_main(".github") != expected):
        raise RuntimeError("CONTROLLER_MAIN_MOVED")
    return expected


def prepare(*, operational=False):
    source = controller_source(operational=operational)
    root = Path("release-sources")
    root.mkdir(mode=0o700, exist_ok=False)
    records = {}
    for slug, (repository, ancestor) in SOURCES.items():
        expected = protected_main(repository)
        destination = root / slug
        destination.mkdir(mode=0o700)
        git("init", "-q", cwd=destination)
        git("remote", "add", "origin", f"https://github.com/szl-holdings/{repository}.git", cwd=destination)
        git("fetch", "--no-tags", "origin", expected, cwd=destination)
        git("checkout", "--detach", expected, cwd=destination)
        git("merge-base", "--is-ancestor", ancestor, expected, cwd=destination)
        if revision(git("rev-parse", "HEAD", cwd=destination)) != expected or protected_main(repository) != expected:
            raise RuntimeError("SOURCE_MOVED_DURING_ACQUISITION")
        records[slug] = expected
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"schema": "szl.hf-release-source-binding/v1", "controller": source, "sources": records}, sort_keys=True) + "\n")
    verify(operational=operational)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            for slug, key in (("lake", "lake_sha"), ("energy", "energy_sha"), ("lambda-gate", "lambda_sha")):
                stream.write(f"{key}={records[slug]}\n")


def verify(*, operational=False):
    source = controller_source(operational=operational)
    if STATE.is_symlink() or STATE.stat().st_size > 4096:
        raise RuntimeError("SOURCE_BINDING_INVALID")
    value = json.loads(STATE.read_bytes())
    if (set(value) != {"schema", "controller", "sources"}
            or value["schema"] != "szl.hf-release-source-binding/v1"
            or value["controller"] != source or set(value["sources"]) != set(SOURCES)):
        raise RuntimeError("SOURCE_BINDING_INVALID")
    for slug, (repository, ancestor) in SOURCES.items():
        expected = revision(value["sources"][slug]); destination = Path("release-sources") / slug
        if destination.is_symlink() or not destination.is_dir():
            raise RuntimeError("SOURCE_CHECKOUT_INVALID")
        if (revision(git("rev-parse", "HEAD", cwd=destination)) != expected
                or git("status", "--porcelain", "--untracked-files=all", cwd=destination)
                or protected_main(repository) != expected):
            raise RuntimeError("SOURCE_MOVED_OR_DIRTY")
        git("merge-base", "--is-ancestor", ancestor, expected, cwd=destination)
    return value


def contracts(*, operational=False):
    """Run the same fixed owner tests without forwarding publisher credentials."""
    verify(operational=operational)
    root = Path("release-sources")
    commands = (
        ("lake", [str(root / "lake" / "scripts" / "test_hf_dataset_contract.py")], str(root / "lake" / "scripts")),
        ("lake", [str(root / "lake" / "scripts" / "test_publish_hf_dataset.py")], str(root / "lake" / "scripts")),
        ("lake", [str(root / "lake" / "scripts" / "publish_hf_dataset.py"), "--check-index"], str(root / "lake" / "scripts")),
        ("energy", ["-m", "pytest", "-p", "no:cacheprovider", "-q", str(root / "energy" / "tests" / "test_hf_kernel_contract.py")], str(root / "energy")),
        ("lambda-gate", ["-m", "pytest", "-p", "no:cacheprovider", "-q", str(root / "lambda-gate" / "tests" / "test_hf_governed_norm_contract.py")], str(root / "lambda-gate" / "torch-ext") + os.pathsep + str(root / "lambda-gate")),
    )
    for _owner, arguments, pythonpath in commands:
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}}
        env.update({"PYTHONPATH": pythonpath, "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
        subprocess.run([sys.executable, *arguments], env=env, check=True, timeout=300)
    verify(operational=operational)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "verify", "contracts"))
    parser.add_argument("--operational", action="store_true")
    args = parser.parse_args()
    {"prepare": prepare, "verify": verify, "contracts": contracts}[args.operation](operational=args.operational)


if __name__ == "__main__":
    main()
