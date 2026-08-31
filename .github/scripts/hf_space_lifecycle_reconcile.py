#!/usr/bin/env python3
"""Plan or apply one fail-closed Hugging Face Space publication transition.

The protected JSON policy enumerates every Space admitted by an immutable,
authenticated inventory receipt. A plan is read-only. An apply must repeat the
exact policy digest and exact provider state from a prior plan, prove that the
checkout is still protected ``main``, and may call one supported Hub mutator:
``HfApi.update_repo_settings(..., private=False)`` for one named Space.

This controller cannot hide, archive, create, delete, rename, upload, restart,
pause, resize, or change storage, variables, or secrets. Runtime convergence is
reported but intentionally belongs to a separate reviewed controller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


POLICY_SCHEMA = "szl.hf.space-lifecycle-policy.v2"
RECEIPT_SCHEMA = "szl.hf.space-lifecycle-receipt.v2"
ORGANIZATION = "SZLHOLDINGS"
CONTROL_REPOSITORY = "szl-holdings/.github"
AUTHORITY_RUN_ID = "33352706604"
AUTHORITY_SOURCE_REVISION = "ab1e0669b4ac5715e4e26fdbb529db70e6affc33"
AUTHORITY_ARTIFACT_ID = "9744148627"
AUTHORITY_ARTIFACT_DIGEST = (
    "sha256:baac9ac6941a491887d3f28bf6533e2f61000b8722fb2e10dfcdae1b59a2a435"
)
EXACT_REVISION = re.compile(r"[0-9a-f]{40}")
EXACT_SHA256 = re.compile(r"[0-9a-f]{64}")
ALLOWED_ACCESS_TOKEN_ROLES = frozenset({"fineGrained", "write"})
ALLOWED_REPO_IDS = frozenset(
    {
        "SZLHOLDINGS/README",
        "SZLHOLDINGS/a11oy",
        "SZLHOLDINGS/a11oy-factory",
        "SZLHOLDINGS/anatomy",
        "SZLHOLDINGS/ayllu",
        "SZLHOLDINGS/cosmos",
        "SZLHOLDINGS/counsel",
        "SZLHOLDINGS/david-leads",
        "SZLHOLDINGS/energy-attest-holo",
        "SZLHOLDINGS/energy-attested-runs",
        "SZLHOLDINGS/evidence-studio",
        "SZLHOLDINGS/experiments",
        "SZLHOLDINGS/governed-agent-bench",
        "SZLHOLDINGS/governed-norm-holo",
        "SZLHOLDINGS/governed-receipt-verifier",
        "SZLHOLDINGS/guardrail-receipt",
        "SZLHOLDINGS/hatun-mcp",
        "SZLHOLDINGS/holographic",
        "SZLHOLDINGS/immune",
        "SZLHOLDINGS/immune-lattice",
        "SZLHOLDINGS/khipu-lab",
        "SZLHOLDINGS/killinchu",
        "SZLHOLDINGS/lambda-gate-holo",
        "SZLHOLDINGS/llm-router-live",
        "SZLHOLDINGS/lyte-services",
        "SZLHOLDINGS/nexus",
        "SZLHOLDINGS/prove-it",
        "SZLHOLDINGS/receipt-chain-live",
        "SZLHOLDINGS/sda",
        "SZLHOLDINGS/second-brain",
        "SZLHOLDINGS/szl-atelier",
        "SZLHOLDINGS/szl-blocked-live",
        "SZLHOLDINGS/szl-command-lab",
        "SZLHOLDINGS/szl-estate-live",
        "SZLHOLDINGS/szl-experiments",
        "SZLHOLDINGS/szl-forge-lab",
        "SZLHOLDINGS/szl-govsign-live",
        "SZLHOLDINGS/szl-kernels-live",
        "SZLHOLDINGS/szl-khipu",
        "SZLHOLDINGS/szl-model-inference-lab",
        "SZLHOLDINGS/szl-provctl-live",
        "SZLHOLDINGS/szl-quant-live",
        "SZLHOLDINGS/szl-real-estate",
        "SZLHOLDINGS/szl-sovereign-os",
        "SZLHOLDINGS/terra-assurance",
        "SZLHOLDINGS/yarqa",
    }
)


class LifecycleError(RuntimeError):
    """The requested action is unsafe, stale, unauthorized, or unverifiable."""


@dataclass(frozen=True)
class SpaceState:
    repo_id: str
    visibility: str
    runtime_stage: str
    revision: str
    sdk: str


@dataclass(frozen=True)
class DesiredState:
    repo_id: str
    visibility: str
    runtime_stage: str
    role: str


@dataclass(frozen=True)
class Transition:
    name: str
    method: str
    reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def policy_digest(policy: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(policy)).hexdigest()


def normalize_stage(value: Any) -> str:
    raw = getattr(value, "value", value)
    stage = str(raw or "").strip().upper()
    if "." in stage:
        stage = stage.rsplit(".", 1)[-1]
    if not stage:
        raise LifecycleError("Hugging Face runtime response omitted stage")
    return stage


def normalize_revision(value: Any) -> str:
    revision = str(value or "").strip().lower()
    if not EXACT_REVISION.fullmatch(revision):
        raise LifecycleError(
            f"Hugging Face Space revision is not an exact 40-hex SHA: {revision!r}"
        )
    return revision


def normalize_policy_sha256(value: Any) -> str:
    digest = str(value or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest.split(":", 1)[1]
    if not EXACT_SHA256.fullmatch(digest):
        raise LifecycleError("policy digest must be an exact 64-hex SHA-256")
    return digest


def load_policy(path: Path) -> tuple[dict[str, Any], dict[str, DesiredState]]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"cannot read lifecycle policy: {exc}") from exc
    if not isinstance(policy, dict):
        raise LifecycleError("lifecycle policy root must be a JSON object")
    if set(policy) != {
        "schema",
        "organization",
        "authority",
        "token_authority",
        "targets",
        "boundaries",
    }:
        raise LifecycleError("lifecycle policy has missing or unknown top-level keys")
    if policy.get("schema") != POLICY_SCHEMA:
        raise LifecycleError(f"unexpected lifecycle policy schema: {policy.get('schema')!r}")
    if policy.get("organization") != ORGANIZATION:
        raise LifecycleError("lifecycle policy organization is not SZLHOLDINGS")

    authority = policy.get("authority")
    if not isinstance(authority, dict) or set(authority) != {
        "repository",
        "workflow",
        "run_id",
        "source_revision",
        "artifact_id",
        "artifact_name",
        "artifact_digest",
        "generated_at",
        "inventory_issue",
        "decision_issue",
        "selection_rule",
    }:
        raise LifecycleError("lifecycle authority has missing or unknown keys")
    expected_authority = {
        "repository": CONTROL_REPOSITORY,
        "workflow": ".github/workflows/hf-official-estate-inventory.yml",
        "run_id": AUTHORITY_RUN_ID,
        "source_revision": AUTHORITY_SOURCE_REVISION,
        "artifact_id": AUTHORITY_ARTIFACT_ID,
        "artifact_name": f"hf-official-estate-inventory-{AUTHORITY_RUN_ID}",
        "artifact_digest": AUTHORITY_ARTIFACT_DIGEST,
        "inventory_issue": 263,
        "decision_issue": 511,
    }
    for key, expected in expected_authority.items():
        if authority.get(key) != expected:
            raise LifecycleError(f"lifecycle authority {key} must remain {expected!r}")
    if not str(authority.get("generated_at") or "").strip():
        raise LifecycleError("lifecycle authority generated_at is empty")
    if not str(authority.get("selection_rule") or "").strip():
        raise LifecycleError("lifecycle authority selection_rule is empty")

    token_authority = policy.get("token_authority")
    expected_token_authority = {
        "namespace": ORGANIZATION,
        "required_org_role": "admin",
        "allowed_access_token_roles": ["fineGrained", "write"],
    }
    if token_authority != expected_token_authority:
        raise LifecycleError("lifecycle token authority changed")

    raw_targets = policy.get("targets")
    if not isinstance(raw_targets, list):
        raise LifecycleError("lifecycle policy targets must be a list")
    targets: dict[str, DesiredState] = {}
    for raw in raw_targets:
        if not isinstance(raw, dict) or set(raw) != {
            "repo_id",
            "desired_visibility",
            "desired_runtime_stage",
            "role",
        }:
            raise LifecycleError("lifecycle target has missing or unknown keys")
        repo_id = str(raw.get("repo_id") or "")
        visibility = str(raw.get("desired_visibility") or "")
        runtime_stage = normalize_stage(raw.get("desired_runtime_stage"))
        role = str(raw.get("role") or "").strip()
        if repo_id not in ALLOWED_REPO_IDS:
            raise LifecycleError(f"policy contains non-allowlisted target: {repo_id!r}")
        if repo_id in targets:
            raise LifecycleError(f"policy contains duplicate target: {repo_id}")
        if visibility != "public":
            raise LifecycleError(f"policy may only retain public visibility: {repo_id}")
        if runtime_stage != "RUNNING":
            raise LifecycleError(f"desired runtime must remain RUNNING: {repo_id}")
        if not role:
            raise LifecycleError(f"policy role is empty for {repo_id}")
        targets[repo_id] = DesiredState(repo_id, visibility, runtime_stage, role)
    if set(targets) != ALLOWED_REPO_IDS:
        missing = sorted(ALLOWED_REPO_IDS - set(targets))
        extra = sorted(set(targets) - ALLOWED_REPO_IDS)
        raise LifecycleError(
            f"policy must enumerate the complete fixed inventory; missing={missing} extra={extra}"
        )

    required_boundaries = {
        "one_target_per_run": True,
        "one_transition_per_apply": True,
        "private_to_public_only": True,
        "runtime_mutation": False,
        "archive": False,
        "delete": False,
        "create": False,
        "rename": False,
        "upload": False,
        "hardware_change": False,
        "storage_change": False,
        "variable_change": False,
        "secret_change": False,
    }
    if policy.get("boundaries") != required_boundaries:
        raise LifecycleError("lifecycle policy safety boundaries changed")
    return policy, targets


class HubSpaceClient:
    """Narrow adapter around supported ``huggingface_hub`` methods."""

    def __init__(self, api: Any) -> None:
        self.api = api

    def verify_operator(self) -> dict[str, str]:
        info = self.api.whoami(cache=False)
        if not isinstance(info, dict) or info.get("type") != "user":
            raise LifecycleError("Hugging Face credential is not a user token")
        auth = info.get("auth") or {}
        access = auth.get("accessToken") if isinstance(auth, dict) else None
        token_role = access.get("role") if isinstance(access, dict) else None
        if token_role not in ALLOWED_ACCESS_TOKEN_ROLES:
            raise LifecycleError("Hugging Face credential is not an approved write token")
        org_role = None
        for org in info.get("orgs") or []:
            if isinstance(org, dict) and org.get("name") == ORGANIZATION:
                org_role = org.get("roleInOrg")
                break
        if org_role != "admin":
            raise LifecycleError("Hugging Face credential is not SZLHOLDINGS admin")
        return {
            "credential_type": "user",
            "access_token_role": str(token_role),
            "organization": ORGANIZATION,
            "organization_role": "admin",
        }

    def read(self, repo_id: str) -> SpaceState:
        info = self.api.space_info(
            repo_id=repo_id,
            expand=["private", "runtime", "sdk", "sha"],
        )
        observed_id = str(getattr(info, "id", "") or getattr(info, "repo_id", ""))
        if observed_id != repo_id:
            raise LifecycleError(
                f"Space identity mismatch: requested={repo_id!r} observed={observed_id!r}"
            )
        private = getattr(info, "private", None)
        if not isinstance(private, bool):
            raise LifecycleError("Hugging Face response omitted boolean private state")
        runtime = getattr(info, "runtime", None)
        sdk = str(getattr(info, "sdk", "") or "").strip().lower()
        if not sdk:
            raise LifecycleError("Hugging Face response omitted sdk")
        return SpaceState(
            repo_id=repo_id,
            visibility="private" if private else "public",
            runtime_stage=normalize_stage(getattr(runtime, "stage", None)),
            revision=normalize_revision(getattr(info, "sha", None)),
            sdk=sdk,
        )

    def set_public(self, repo_id: str) -> None:
        self.api.update_repo_settings(repo_id=repo_id, repo_type="space", private=False)


def next_transition(current: SpaceState, desired: DesiredState) -> Transition | None:
    if desired.visibility != "public":
        raise LifecycleError("controller policy may only request public visibility")
    if current.visibility == "public":
        return None
    if current.runtime_stage != "RUNNING":
        raise LifecycleError(
            "refusing to publish a private Space unless its runtime stage is RUNNING"
        )
    return Transition(
        name="private-to-public",
        method="update_repo_settings",
        reason="allowlisted Space is RUNNING and may be made public",
    )


def compare_expected(
    current: SpaceState,
    *,
    visibility: str | None,
    runtime_stage: str | None,
    revision: str | None,
    require_complete: bool,
) -> None:
    expected = {
        "visibility": visibility,
        "runtime_stage": runtime_stage,
        "revision": revision,
    }
    if require_complete and any(value is None for value in expected.values()):
        missing = sorted(key for key, value in expected.items() if value is None)
        raise LifecycleError(f"apply requires exact expected-before fields: {missing}")
    actual = asdict(current)
    for key, value in expected.items():
        if value is not None and actual[key] != value:
            raise LifecycleError(
                f"expected-before drift for {key}: expected={value!r} observed={actual[key]!r}"
            )


def fetch_github_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise LifecycleError("GitHub API response was not an object")
    return value


def read_local_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip().lower()


def read_live_default_tip(
    environ: Mapping[str, str],
    *,
    fetch_json: Callable[[str, str], dict[str, Any]] = fetch_github_json,
) -> tuple[str, str]:
    repository = environ.get("GITHUB_REPOSITORY", "")
    token = environ.get("GITHUB_TOKEN", "")
    api_url = environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if repository != CONTROL_REPOSITORY:
        raise LifecycleError("cannot read default tip for an unapproved repository")
    if not token:
        raise LifecycleError("GITHUB_TOKEN is required for the exact-main guard")
    repo = fetch_json(f"{api_url}/repos/{repository}", token)
    default_branch = str(repo.get("default_branch") or "")
    if default_branch != "main":
        raise LifecycleError(f"controller default branch changed: {default_branch!r}")
    encoded = urllib.parse.quote(default_branch, safe="")
    tip = fetch_json(f"{api_url}/repos/{repository}/commits/{encoded}", token)
    live_sha = str(tip.get("sha") or "").lower()
    if not EXACT_REVISION.fullmatch(live_sha):
        raise LifecycleError("GitHub API returned a malformed default-branch SHA")
    return default_branch, live_sha


def require_current_protected_main(
    environ: Mapping[str, str],
    *,
    fetch_json: Callable[[str, str], dict[str, Any]] = fetch_github_json,
    local_head: Callable[[], str] = read_local_head,
) -> str:
    event = environ.get("GITHUB_EVENT_NAME", "")
    repository = environ.get("GITHUB_REPOSITORY", "")
    source_sha = environ.get("GITHUB_SHA", "").lower()
    if event != "workflow_dispatch":
        raise LifecycleError("controller runs only from workflow_dispatch")
    if repository != CONTROL_REPOSITORY:
        raise LifecycleError(f"controller repository must be {CONTROL_REPOSITORY}")
    if not EXACT_REVISION.fullmatch(source_sha):
        raise LifecycleError("GITHUB_SHA must be an exact 40-hex revision")
    checked_out_sha = str(local_head() or "").lower()
    if checked_out_sha != source_sha:
        raise LifecycleError("checked-out HEAD differs from GITHUB_SHA")
    default_branch, live_sha = read_live_default_tip(environ, fetch_json=fetch_json)
    if environ.get("GITHUB_REF", "") != f"refs/heads/{default_branch}":
        raise LifecycleError("controller ref is not protected default branch")
    if live_sha != source_sha:
        raise LifecycleError("controller checkout is not the live default-branch tip")
    return source_sha


def transition_readback_matches(
    before: SpaceState, after: SpaceState, transition: Transition
) -> bool:
    return (
        transition.name == "private-to-public"
        and after.repo_id == before.repo_id
        and after.visibility == "public"
        and after.runtime_stage == before.runtime_stage
        and after.revision == before.revision
        and after.sdk == before.sdk
    )


def convergence(state: SpaceState, desired: DesiredState) -> dict[str, Any]:
    visibility_matches = state.visibility == desired.visibility
    runtime_matches = state.runtime_stage == desired.runtime_stage
    return {
        "visibility_matches": visibility_matches,
        "runtime_matches": runtime_matches,
        "full_policy_converged": visibility_matches and runtime_matches,
        "runtime_mutation_in_scope": False,
    }


def error_record(exc: Exception) -> dict[str, Any]:
    """Return safe metadata only; never copy provider bodies or credentials."""

    record: dict[str, Any] = {"class": type(exc).__name__}
    if isinstance(exc, LifecycleError):
        record["detail"] = str(exc)
        return record
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        record["http_status"] = status
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        request_id = headers.get("x-request-id") or headers.get("X-Request-Id")
        if request_id:
            record["request_id"] = str(request_id)[:128]
    return record


def reconcile(
    *,
    client: HubSpaceClient,
    policy_path: Path,
    target: str,
    mode: str,
    requested_transition: str,
    expected_policy_sha256: str | None,
    expected_visibility: str | None,
    expected_runtime_stage: str | None,
    expected_revision: str | None,
    environ: Mapping[str, str],
    main_guard: Callable[[Mapping[str, str]], str] = require_current_protected_main,
    main_after_reader: Callable[[Mapping[str, str]], tuple[str, str]] = read_live_default_tip,
    readback_attempts: int = 6,
    readback_interval: float = 5.0,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    mutation_attempted = False
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generated_at": utc_now(),
        "organization": ORGANIZATION,
        "mode": mode,
        "target": target,
        "requested_transition": requested_transition,
        "expected_policy_sha256": expected_policy_sha256,
        "expected_before": {
            "visibility": expected_visibility,
            "runtime_stage": expected_runtime_stage,
            "revision": expected_revision,
        },
        "controller": {
            "repository": environ.get("GITHUB_REPOSITORY") or CONTROL_REPOSITORY,
            "ref": environ.get("GITHUB_REF") or "LOCAL_UNBOUND",
            "revision": environ.get("GITHUB_SHA") or "LOCAL_UNBOUND",
            "workflow": environ.get("GITHUB_WORKFLOW") or "LOCAL",
            "run_id": environ.get("GITHUB_RUN_ID") or "LOCAL",
            "run_attempt": environ.get("GITHUB_RUN_ATTEMPT") or "LOCAL",
        },
        "boundaries": [
            "Exactly one fixed-inventory Space is inspected per run.",
            "At most one private-to-public transition is applied.",
            "Private, archive, pause, restart, upload, hardware, storage, variable, and secret writes are impossible through this controller.",
            "RUNNING is provider-stage evidence, not product correctness or uptime proof.",
        ],
        "provider_request": {
            "attempted": False,
            "method": None,
            "started_at": None,
            "completed_at": None,
        },
        "readbacks": [],
    }
    try:
        if mode not in {"plan", "apply"}:
            raise LifecycleError(f"unsupported mode: {mode!r}")
        if requested_transition not in {"inspect", "private-to-public"}:
            raise LifecycleError(f"unsupported transition: {requested_transition!r}")
        if target not in ALLOWED_REPO_IDS:
            raise LifecycleError(f"target is not in the fixed inventory: {target!r}")

        policy, targets = load_policy(policy_path)
        digest = policy_digest(policy)
        receipt["policy"] = {
            "path": str(policy_path),
            "sha256": digest,
            "authority": policy["authority"],
        }
        if expected_policy_sha256 is not None:
            expected_digest = normalize_policy_sha256(expected_policy_sha256)
            if expected_digest != digest:
                raise LifecycleError(
                    "expected policy digest differs from the protected policy"
                )
        elif mode == "apply":
            raise LifecycleError("apply requires the exact policy SHA-256 from plan")

        desired = targets[target]
        receipt["desired"] = asdict(desired)
        receipt["operator"] = client.verify_operator()
        before = client.read(target)
        receipt["before"] = asdict(before)
        compare_expected(
            before,
            visibility=expected_visibility,
            runtime_stage=expected_runtime_stage,
            revision=expected_revision,
            require_complete=mode == "apply",
        )
        transition = next_transition(before, desired)
        receipt["planned_transition"] = asdict(transition) if transition else None
        if requested_transition != "inspect":
            if transition is None or requested_transition != transition.name:
                raise LifecycleError(
                    "requested transition does not match current policy and provider state"
                )

        if mode == "plan":
            control_revision = main_guard(environ)
            receipt["controller"]["verified_live_default_revision"] = control_revision
            current_convergence = convergence(before, desired)
            receipt["convergence"] = current_convergence
            if transition is not None:
                result = "PLANNED_VISIBILITY_ACTION"
            elif current_convergence["full_policy_converged"]:
                result = "PLANNED_CONVERGED"
            else:
                result = "PLANNED_VISIBILITY_CONVERGED_RUNTIME_OUT_OF_SCOPE"
            receipt["result"] = result
            receipt["after"] = None
            receipt["exit_code"] = 0
            return receipt, 0

        if transition is None:
            raise LifecycleError(
                "apply refused because visibility is already public; use plan"
            )
        if requested_transition != transition.name:
            raise LifecycleError("apply requires the exact transition from plan")

        control_revision = main_guard(environ)
        receipt["controller"]["live_default_before"] = control_revision
        receipt["provider_request"] = {
            "attempted": True,
            "method": transition.method,
            "started_at": utc_now(),
            "completed_at": None,
        }
        mutation_attempted = True
        provider_error: dict[str, Any] | None = None
        try:
            client.set_public(target)
        except Exception as exc:
            provider_error = error_record(exc)
            receipt["provider_request"]["error"] = provider_error
        receipt["provider_request"]["completed_at"] = utc_now()

        after: SpaceState | None = None
        verified = False
        for attempt in range(1, max(1, readback_attempts) + 1):
            observation: dict[str, Any] = {"attempt": attempt, "observed_at": utc_now()}
            try:
                after = client.read(target)
                observation["state"] = asdict(after)
                verified = transition_readback_matches(before, after, transition)
                observation["transition_verified"] = verified
            except Exception as exc:
                observation["error"] = error_record(exc)
            receipt["readbacks"].append(observation)
            if verified:
                break
            if attempt < max(1, readback_attempts) and readback_interval > 0:
                sleeper(readback_interval)

        try:
            _, main_after = main_after_reader(environ)
            receipt["controller"]["live_default_after"] = main_after
        except Exception as exc:
            receipt["controller"]["live_default_after_error"] = error_record(exc)
            receipt["result"] = "UNKNOWN_AFTER_ATTEMPT"
            receipt["exit_code"] = 2
            return receipt, 2
        if main_after != control_revision:
            receipt["result"] = "CONCURRENT_DRIFT"
            receipt["exit_code"] = 2
            return receipt, 2
        if not verified or after is None:
            receipt["result"] = "UNKNOWN_AFTER_ATTEMPT"
            receipt["exit_code"] = 2
            return receipt, 2

        receipt["after"] = asdict(after)
        receipt["convergence"] = convergence(after, desired)
        receipt["result"] = "VERIFIED"
        if provider_error is not None:
            receipt["provider_request"]["note"] = (
                "The client reported an error, but authenticated readback verified the transition."
            )
        receipt["exit_code"] = 0
        return receipt, 0
    except Exception as exc:
        receipt["result"] = (
            "UNKNOWN_AFTER_ATTEMPT"
            if mutation_attempted
            else (
                "BLOCKED_PRECONDITION"
                if isinstance(exc, LifecycleError)
                else "FAILED_BEFORE_ATTEMPT"
            )
        )
        receipt["error"] = error_record(exc)
        receipt["exit_code"] = 2
        return receipt, 2


def _optional_visibility(value: str) -> str | None:
    if not value or value == "unspecified":
        return None
    if value not in {"public", "private"}:
        raise argparse.ArgumentTypeError("visibility must be unspecified, public, or private")
    return value


def _optional_stage(value: str) -> str | None:
    return normalize_stage(value) if value else None


def _optional_revision(value: str) -> str | None:
    return normalize_revision(value) if value else None


def _optional_policy_sha256(value: str) -> str | None:
    return normalize_policy_sha256(value) if value else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".github/data/hf-space-lifecycle-policy.json"),
    )
    parser.add_argument("--target", required=True, choices=sorted(ALLOWED_REPO_IDS))
    parser.add_argument("--mode", choices=("plan", "apply"), default="plan")
    parser.add_argument(
        "--transition", choices=("inspect", "private-to-public"), default="inspect"
    )
    parser.add_argument("--expected-policy-sha256", type=_optional_policy_sha256)
    parser.add_argument(
        "--expected-visibility", type=_optional_visibility, default=None
    )
    parser.add_argument("--expected-stage", type=_optional_stage, default=None)
    parser.add_argument("--expected-revision", type=_optional_revision, default=None)
    parser.add_argument(
        "--report", type=Path, default=Path("reports/hf-space-lifecycle/receipt.json")
    )
    args = parser.parse_args(argv)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("HF_ORG_TOKEN")
    if not token:
        report = {
            "schema": RECEIPT_SCHEMA,
            "generated_at": utc_now(),
            "organization": ORGANIZATION,
            "mode": args.mode,
            "target": args.target,
            "requested_transition": args.transition,
            "result": "FAILED_BEFORE_ATTEMPT",
            "error": {
                "class": "LifecycleError",
                "detail": "authenticated plan/apply requires the fixed HF_ORG_TOKEN secret",
            },
            "exit_code": 2,
        }
        exit_code = 2
    else:
        try:
            # Do not expose the provider credential to a feature-branch copy.
            require_current_protected_main(os.environ)
            from huggingface_hub import HfApi

            report, exit_code = reconcile(
                client=HubSpaceClient(HfApi(token=token)),
                policy_path=args.policy,
                target=args.target,
                mode=args.mode,
                requested_transition=args.transition,
                expected_policy_sha256=args.expected_policy_sha256,
                expected_visibility=args.expected_visibility,
                expected_runtime_stage=args.expected_stage,
                expected_revision=args.expected_revision,
                environ=os.environ,
            )
        except Exception as exc:
            report = {
                "schema": RECEIPT_SCHEMA,
                "generated_at": utc_now(),
                "organization": ORGANIZATION,
                "mode": args.mode,
                "target": args.target,
                "requested_transition": args.transition,
                "result": (
                    "BLOCKED_PRECONDITION"
                    if isinstance(exc, LifecycleError)
                    else "FAILED_BEFORE_ATTEMPT"
                ),
                "error": error_record(exc),
                "exit_code": 2,
            }
            exit_code = 2

    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
