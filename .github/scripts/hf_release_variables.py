#!/usr/bin/env python3
"""Bind the canonical A11oy publisher-generated release values to Space variables.

Reads only the deploy manifest written by hf_deploy_from_dockerfile.py in the
same job (``release_manifest.space_variables``), validates every name and value
against a fixed allowlist and format, and sets only the variables whose current
value differs. Values are non-secret content hashes, immutable ids, and the
exact source SHA; secrets are never read or printed. Runs after publication,
the same placement as the SZL_GIT_SHA source binding (a11oy #3770).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

CANONICAL_SPACE = "SZLHOLDINGS/a11oy"
_SHA256 = re.compile(r"^(?!0{64}$)[0-9a-f]{64}$")
_SHA40 = re.compile(r"^(?!0{40}$)[0-9a-f]{40}$")
_IMMUTABLE_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}@"
    r"(?:sha256:(?!0{64}$)[0-9a-f]{64}|(?!0{40}$)[0-9a-f]{40})$"
)
_RELEASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}-[0-9a-f]{12}$")
FORMATS = {
    "SZL_SERVED_FRONTEND_SHA256": _SHA256,
    "SZL_API_CONTRACT_SHA256": _SHA256,
    "SZL_MODEL_IDENTITY": _IMMUTABLE_ID,
    "SZL_DEPLOYMENT_IDENTITY": _IMMUTABLE_ID,
    "SZL_RELEASE_ID": _RELEASE_ID,
    "SZL_RELEASE_COMMIT": _SHA40,
}
DESCRIPTION = "Publisher-generated release manifest binding (a11oy #3770)"


class ReleaseVariableError(ValueError):
    pass


def planned_variables(manifest: dict) -> dict[str, str]:
    if not isinstance(manifest, dict) or manifest.get("hf_repo") != CANONICAL_SPACE:
        raise ReleaseVariableError("manifest is not the canonical A11oy publication")
    release = manifest.get("release_manifest")
    if not isinstance(release, dict):
        raise ReleaseVariableError("manifest has no publisher-generated release manifest")
    variables = release.get("space_variables")
    if not isinstance(variables, dict) or set(variables) != set(FORMATS):
        raise ReleaseVariableError("release variables are not the exact admitted set")
    for name, value in variables.items():
        if type(value) is not str or not FORMATS[name].fullmatch(value):
            raise ReleaseVariableError(f"release variable {name} is malformed")
    source_sha = manifest.get("source_sha")
    if variables["SZL_RELEASE_COMMIT"] != source_sha:
        raise ReleaseVariableError("release commit differs from the published source SHA")
    if variables["SZL_DEPLOYMENT_IDENTITY"] != f"{CANONICAL_SPACE}@{source_sha}":
        raise ReleaseVariableError("deployment identity differs from the published source")
    return dict(variables)


def bind(api, variables: dict[str, str]) -> list[str]:
    current = api.get_space_variables(repo_id=CANONICAL_SPACE)
    changed = []
    for name in sorted(variables):
        observed = current.get(name) if hasattr(current, "get") else None
        observed = getattr(observed, "value", observed)
        if observed != variables[name]:
            changed.append(name)
    for name in changed:
        api.add_space_variable(repo_id=CANONICAL_SPACE, key=name,
                               value=variables[name], description=DESCRIPTION)
    readback = api.get_space_variables(repo_id=CANONICAL_SPACE)
    for name, value in variables.items():
        observed = readback.get(name) if hasattr(readback, "get") else None
        if getattr(observed, "value", observed) != value:
            raise ReleaseVariableError(f"release variable {name} readback mismatch")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.manifest, encoding="utf-8") as fh:
            variables = planned_variables(json.load(fh))
        if not os.environ.get("HF_TOKEN"):
            raise ReleaseVariableError("HF_TOKEN is not configured")
        from huggingface_hub import HfApi  # lazy: tests need no network
        changed = bind(HfApi(token=os.environ["HF_TOKEN"]), variables)
    except (OSError, ValueError) as exc:
        print(f"::error title=HF release variables::{exc}")
        return 2
    report = {"schema": "szl.hf-release-variables/v1", "repo_id": CANONICAL_SPACE,
              "variables": variables, "changed": changed}
    with open(args.output, "x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("release variables bound: " + (", ".join(changed) if changed else "(unchanged)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
