#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only protected-main preflight. No Hugging Face credential is consumed."""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Mapping
import urllib.error
import urllib.request

REPOSITORY = "szl-holdings/.github"
BRANCH_URL = "https://api.github.com/repos/szl-holdings/.github/branches/main"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class SourceBoundaryError(RuntimeError):
    """Errors use fixed codes; never echo credentials, provider bodies or env."""


def verify_context(env: Mapping[str, str], checkout: str, branch: Any = None) -> str:
    if env.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise SourceBoundaryError("REPOSITORY_REJECTED")
    if env.get("GITHUB_REF") != "refs/heads/main" or env.get("GITHUB_REF_PROTECTED") != "true":
        raise SourceBoundaryError("PROTECTED_REF_REQUIRED")
    if env.get("GITHUB_EVENT_NAME") not in {"push", "schedule", "workflow_dispatch"}:
        raise SourceBoundaryError("EVENT_REJECTED")
    if env.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and env.get("HF_INVENTORY_PUBLISH_INPUT") != "true":
        raise SourceBoundaryError("EXPLICIT_PUBLICATION_REQUIRED")
    source = env.get("GITHUB_SHA", "")
    if not SHA40.fullmatch(source) or source == "0" * 40 or checkout != source:
        raise SourceBoundaryError("SOURCE_IDENTITY_REJECTED")
    if branch is not None:
        if not isinstance(branch, dict) or branch.get("name") != "main" or branch.get("protected") is not True:
            raise SourceBoundaryError("PROTECTED_BRANCH_READBACK_REJECTED")
        commit = branch.get("commit")
        if not isinstance(commit, dict) or commit.get("sha") != source:
            raise SourceBoundaryError("SOURCE_MOVED")
    return source


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceBoundaryError("GITHUB_REDIRECT_REJECTED")


def read_main(token: str) -> dict[str, Any]:
    if not token or any(c in token for c in "\r\n"):
        raise SourceBoundaryError("GITHUB_READ_CREDENTIAL_REQUIRED")
    request = urllib.request.Request(BRANCH_URL, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "szl-hf-inventory-source-preflight/1",
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise SourceBoundaryError("GITHUB_STATUS_REJECTED")
            body = response.read(65537)
        if len(body) > 65536:
            raise SourceBoundaryError("GITHUB_RESPONSE_BOUND_EXCEEDED")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise SourceBoundaryError("GITHUB_RESPONSE_SHAPE_REJECTED")
        return result
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise SourceBoundaryError("GITHUB_READBACK_FAILED") from None


def main() -> int:
    try:
        checkout = subprocess.check_output(["git", "rev-parse", "--verify", "HEAD^{commit}"], text=True, timeout=10).strip()
        verify_context(os.environ, checkout)
        source = verify_context(os.environ, checkout, read_main(os.environ.get("GITHUB_TOKEN", "")))
    except (SourceBoundaryError, subprocess.SubprocessError, OSError) as error:
        code = str(error) if isinstance(error, SourceBoundaryError) else "SOURCE_PREFLIGHT_FAILED"
        print(json.dumps({"state": "BLOCKED", "error_code": code}))
        return 2
    print(json.dumps({"state": "PROTECTED_SOURCE_MATCH", "source_revision": source}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
