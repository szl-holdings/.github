#!/usr/bin/env python3
"""Acquire one valid Hugging Face publisher token without exposing credentials.

The selector prefers a repo-scoped Trusted Publisher token, then validates each
configured fallback independently. An expired earlier secret therefore cannot
mask a later valid organization write token. Reports contain source labels,
status codes, request IDs, and hashes only. The selected token is passed through
one mode-0600 runner-temporary file and never enters the job-wide environment or
uploaded evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


TOKEN_ENV_ORDER: tuple[tuple[str, str], ...] = (
    ("HF_ORG_TOKEN", "HF_ORG_TOKEN_CANDIDATE"),
    ("HF_ORG_TOKEN1", "HF_ORG_TOKEN1_CANDIDATE"),
    ("HF_WRITE_TOKEN", "HF_WRITE_TOKEN_CANDIDATE"),
    ("HF_TOKEN", "HF_TOKEN_CANDIDATE"),
    ("HUGGINGFACE_TOKEN", "HUGGINGFACE_TOKEN_CANDIDATE"),
    ("HUGGING_FACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN_CANDIDATE"),
)
REQUEST_ID = re.compile(r"Request ID:\s*([^\n)]+)", re.IGNORECASE)
TOKEN_LINE = re.compile(r"^hf_[A-Za-z0-9._-]+$")
NEXUS_TARGET = "SZLHOLDINGS/nexus"


class CredentialSelectionError(RuntimeError):
    """No configured credential passed active Hub validation."""

    def __init__(
        self,
        message: str,
        *,
        attempts: Sequence[Attempt] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = tuple(attempts)


class OidcExchangeError(RuntimeError):
    """The GitHub OIDC to Hugging Face token exchange failed."""


@dataclass(frozen=True)
class ValidationResult:
    source: str
    identity_sha256: str
    target_access: str


@dataclass(frozen=True)
class Attempt:
    source: str
    present: bool
    valid: bool
    failure_type: str | None = None
    status_code: int | None = None
    request_id: str | None = None
    failure_sha256: str | None = None
    target_access: str | None = None


def _failure_evidence(source: str, error: BaseException) -> Attempt:
    text = str(error)
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    request_match = REQUEST_ID.search(text)
    return Attempt(
        source=source,
        present=True,
        valid=False,
        failure_type=type(error).__name__,
        status_code=status_code if isinstance(status_code, int) else None,
        request_id=request_match.group(1).strip() if request_match else None,
        failure_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _normalize_token(raw: str) -> str:
    token = str(raw or "").strip()
    if not token or any(character.isspace() for character in token):
        raise CredentialSelectionError("credential is empty or contains whitespace")
    if not TOKEN_LINE.fullmatch(token):
        raise CredentialSelectionError("credential does not match a Hugging Face token shape")
    return token


def acquire_oidc_token(resource: str) -> str:
    """Request a fresh repo-scoped token through the official ``hf`` CLI."""

    environment = os.environ.copy()
    # The OIDC exchange needs runner/OIDC context, never a fallback publisher
    # credential. Strip both the canonical token names and the candidate
    # carriers before crossing the subprocess boundary.
    for source, candidate in TOKEN_ENV_ORDER:
        environment.pop(source, None)
        environment.pop(candidate, None)
    environment["HF_OIDC_RESOURCE"] = resource
    environment["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    process = subprocess.run(
        ["hf", "auth", "token"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    if process.returncode != 0:
        raise OidcExchangeError(process.stderr.strip() or "OIDC exchange failed")
    candidates = [
        line.strip()
        for line in process.stdout.splitlines()
        if TOKEN_LINE.fullmatch(line.strip())
    ]
    if len(candidates) != 1:
        raise OidcExchangeError("OIDC exchange did not return exactly one token")
    return _normalize_token(candidates[0])


def validate_token(
    token: str,
    *,
    source: str,
    target_repo: str,
    target_type: str,
    allow_create: bool,
) -> ValidationResult:
    """Actively validate identity and target write access without caching a token.

    ``RepositoryNotFoundError`` is deliberately fail-closed even when callers set
    ``allow_create``. Hugging Face uses a repository 404 both for a truly missing
    target and for an existing private target the caller cannot access. ``whoami``
    proves authentication, not namespace creation authority, so a 404 cannot be
    promoted into a publish-capable credential without a separate authoritative
    namespace/create check.
    """

    from huggingface_hub import HfApi
    from huggingface_hub.utils import RepositoryNotFoundError

    normalized = _normalize_token(token)
    api = HfApi(token=normalized)
    identity = api.whoami()
    identity_name = str((identity or {}).get("name") or "").strip()
    if not identity_name:
        raise CredentialSelectionError("Hub identity response did not contain a name")

    try:
        api.auth_check(repo_id=target_repo, repo_type=target_type, write=True)
    except RepositoryNotFoundError:
        # A Hub 404 is ambiguous: absent and private/inaccessible repositories are
        # intentionally indistinguishable. Never infer create/recover authority.
        raise

    return ValidationResult(
        source=source,
        identity_sha256=hashlib.sha256(identity_name.encode("utf-8")).hexdigest(),
        target_access="EXISTING_WRITE_CONFIRMED",
    )


def select_credential(
    *,
    resource: str | None,
    target_repo: str,
    target_type: str,
    allow_create: bool,
    environment: Mapping[str, str],
    oidc_supplier: Callable[[str], str] = acquire_oidc_token,
    validator: Callable[..., ValidationResult] = validate_token,
) -> tuple[str, ValidationResult, list[Attempt]]:
    """Return the first actively validated credential in deterministic order."""

    attempts: list[Attempt] = []
    if resource:
        try:
            oidc = oidc_supplier(resource)
            result = validator(
                oidc,
                source="TRUSTED_PUBLISHER",
                target_repo=target_repo,
                target_type=target_type,
                allow_create=False,
            )
            attempts.append(
                Attempt(
                    source=result.source,
                    present=True,
                    valid=True,
                    target_access=result.target_access,
                )
            )
            return oidc, result, attempts
        except Exception as error:  # diagnostic only; fallbacks remain eligible
            attempts.append(_failure_evidence("TRUSTED_PUBLISHER", error))

    for source, variable in TOKEN_ENV_ORDER:
        raw = str(environment.get(variable) or "").strip()
        if not raw:
            attempts.append(Attempt(source=source, present=False, valid=False))
            continue
        try:
            token = _normalize_token(raw)
            result = validator(
                token,
                source=source,
                target_repo=target_repo,
                target_type=target_type,
                allow_create=allow_create,
            )
            attempts.append(
                Attempt(
                    source=result.source,
                    present=True,
                    valid=True,
                    target_access=result.target_access,
                )
            )
            return token, result, attempts
        except Exception as error:
            attempts.append(_failure_evidence(source, error))

    raise CredentialSelectionError(
        "no valid Hugging Face publisher credential",
        attempts=attempts,
    )


def _require_public_exact_nexus(info: object) -> None:
    if (
        getattr(info, "id", None) != NEXUS_TARGET
        or getattr(info, "private", None) is not False
    ):
        raise CredentialSelectionError("exact public Nexus target was not confirmed")


def _assert_public_nexus_policy(path: Path) -> None:
    policy = json.loads(path.read_text(encoding="utf-8"))
    matching = [
        target for target in policy.get("targets", [])
        if target.get("repo_id") == NEXUS_TARGET
    ]
    if (
        policy.get("schema") != "szl.hf.space-lifecycle-policy.v2"
        or policy.get("organization") != "SZLHOLDINGS"
        or policy.get("token_authority", {}).get("required_org_role") != "admin"
        or len(matching) != 1
        or matching[0].get("desired_visibility") != "public"
        or matching[0].get("role") != "bound-service"
    ):
        raise CredentialSelectionError("protected Nexus lifecycle policy does not authorize public recovery")


def _has_org_admin(identity: Mapping[str, object]) -> bool:
    return any(
        isinstance(org, dict)
        and str(org.get("name") or "").casefold() == "szlholdings"
        and org.get("roleInOrg") == "admin"
        for org in (identity.get("orgs") or [])
    )


def _recovery_attempt(source: str, phase: str, error: BaseException) -> dict:
    """Persist error class and HTTP status only, never provider error text."""

    return {
        "source": source,
        "phase": phase,
        "status_code": getattr(getattr(error, "response", None), "status_code", None),
        "error_type": type(error).__name__,
    }


def recover_public_nexus(
    environment: Mapping[str, str],
    *,
    api_factory: Callable[..., object] | None = None,
) -> dict:
    """On explicit dispatch, create only the policy-declared public Nexus Space.

    A Hub 404 can mean absence or an inaccessible private Space. The exact
    namespace/name and ``exist_ok=False`` form the atomic occupied-name guard.
    A successful create is not accepted until authenticated write access and
    exact public target readback both pass.
    """

    if api_factory is None:
        from huggingface_hub import HfApi

        api_factory = HfApi
    attempts: list[dict] = []
    for source, variable in TOKEN_ENV_ORDER:
        raw = str(environment.get(variable) or "").strip()
        if not raw:
            continue
        try:
            api = api_factory(token=_normalize_token(raw))
            identity = api.whoami()
            if not str((identity or {}).get("name") or "").strip():
                raise CredentialSelectionError("Hub identity is unavailable")
        except Exception as error:
            attempts.append(_recovery_attempt(source, "identity", error))
            status = attempts[-1]["status_code"]
            if status in (401, 403) or isinstance(error, CredentialSelectionError):
                continue
            return {"state": "BLOCKED_AUTHORITY_UNCERTAIN", "attempts": attempts}

        try:
            api.auth_check(repo_id=NEXUS_TARGET, repo_type="space", write=True)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status != 404:
                attempts.append(_recovery_attempt(source, "write_check", error))
                if status in (401, 403):
                    continue
                return {"state": "BLOCKED_AUTHORITY_UNCERTAIN", "attempts": attempts}
            if not _has_org_admin(identity):
                attempts.append({
                    "source": source,
                    "phase": "org_admin_check",
                    "status_code": None,
                    "error_type": "OrgAdminUnverified",
                })
                continue
            try:
                api.create_repo(
                    repo_id=NEXUS_TARGET,
                    repo_type="space",
                    space_sdk="docker",
                    private=False,
                    exist_ok=False,
                )
            except Exception as create_error:
                attempts.append(_recovery_attempt(source, "create", create_error))
                create_status = attempts[-1]["status_code"]
                if create_status in (401, 403, 409):
                    continue
                return {"state": "UNKNOWN_AFTER_ATTEMPT", "attempts": attempts}
            try:
                api.auth_check(repo_id=NEXUS_TARGET, repo_type="space", write=True)
                _require_public_exact_nexus(
                    api.repo_info(repo_id=NEXUS_TARGET, repo_type="space")
                )
            except Exception as verify_error:
                attempts.append(
                    _recovery_attempt(source, "post_create_readback", verify_error)
                )
                return {"state": "UNKNOWN_AFTER_ATTEMPT", "attempts": attempts}
            attempts.append({"source": source, "phase": "create_readback", "status_code": 200})
            return {"state": "CREATED_PUBLIC_WRITE_CONFIRMED", "attempts": attempts}

        try:
            _require_public_exact_nexus(
                api.repo_info(repo_id=NEXUS_TARGET, repo_type="space")
            )
        except Exception as error:
            attempts.append(_recovery_attempt(source, "existing_readback", error))
            return {"state": "BLOCKED_EXISTING_TARGET_MISMATCH", "attempts": attempts}
        attempts.append({"source": source, "phase": "existing_readback", "status_code": 200})
        return {"state": "EXISTING_PUBLIC_WRITE_CONFIRMED", "attempts": attempts}
    return {"state": "BLOCKED_NO_TARGET_WRITER", "attempts": attempts}


def _write_report(
    path: Path,
    *,
    target_repo: str,
    target_type: str,
    resource: str | None,
    selected: ValidationResult | None,
    attempts: Sequence[Attempt],
    recovery: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "szl.hf-publisher-credential/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {"repo_id": target_repo, "repo_type": target_type},
        "oidc": {
            "requested": resource is not None,
            "resource": resource,
            "issuer": "https://token.actions.githubusercontent.com",
            "audience": "https://huggingface.co",
        },
        "selected": asdict(selected) if selected is not None else None,
        "attempts": [asdict(attempt) for attempt in attempts],
        "recovery": recovery,
        "token_persisted": False,
        "token_logged": False,
        "token_job_environment_exported": False,
        "token_transport": "RESTRICTED_EPHEMERAL_FILE",
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_token_file(path: Path, token: str) -> None:
    """Create one exclusive mode-0600 token file for command-scoped reads."""

    if "\n" in token or "\r" in token:
        raise CredentialSelectionError("credential contains a newline")
    if not path.parent.is_dir():
        raise CredentialSelectionError("token file parent does not exist")
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp and path.parent.resolve() != Path(runner_temp).resolve():
        raise CredentialSelectionError("token file must be a direct child of RUNNER_TEMP")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CredentialSelectionError("token file already exists") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if path.is_symlink() or (path.stat().st_mode & 0o777) != 0o600:
        path.unlink(missing_ok=True)
        raise CredentialSelectionError("token file permissions are not mode 0600")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument(
        "--target-type",
        required=True,
        choices=("model", "dataset", "space"),
    )
    parser.add_argument("--oidc-resource")
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help=(
            "Reserved compatibility flag. Repository 404 responses still fail closed "
            "because they do not prove target absence or namespace creation authority."
        ),
    )
    parser.add_argument(
        "--recover-exact-public-nexus",
        action="store_true",
        help="Explicit owner dispatch: atomically create the exact public Nexus Docker Space if absent.",
    )
    parser.add_argument("--recovery-policy", type=Path)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)

    attempts: list[Attempt] = []
    selected: ValidationResult | None = None
    recovery: dict | None = None
    try:
        if args.recover_exact_public_nexus:
            if (
                args.target_repo != NEXUS_TARGET
                or args.target_type != "space"
                or args.recovery_policy is None
                or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
                or os.environ.get("GITHUB_REF") != "refs/heads/main"
                or os.environ.get("GITHUB_REPOSITORY") != "szl-holdings/.github"
            ):
                raise CredentialSelectionError("exact owner dispatch boundary failed")
            _assert_public_nexus_policy(args.recovery_policy)
            recovery = recover_public_nexus(os.environ)
            if recovery["state"] not in (
                "CREATED_PUBLIC_WRITE_CONFIRMED",
                "EXISTING_PUBLIC_WRITE_CONFIRMED",
            ):
                raise CredentialSelectionError("Nexus target recovery failed closed")
        token, selected, attempts = select_credential(
            resource=args.oidc_resource,
            target_repo=args.target_repo,
            target_type=args.target_type,
            allow_create=args.allow_create,
            environment=os.environ,
        )
        print(f"::add-mask::{token}")
        _write_report(
            args.report,
            target_repo=args.target_repo,
            target_type=args.target_type,
            resource=args.oidc_resource,
            selected=selected,
            attempts=attempts,
            recovery=recovery,
        )
        _write_token_file(args.token_file, token)
        print(
            "Hugging Face credential validated: "
            f"source={selected.source} target_access={selected.target_access}"
        )
        return 0
    except Exception as error:
        if isinstance(error, CredentialSelectionError) and error.attempts:
            attempts = list(error.attempts)
        _write_report(
            args.report,
            target_repo=args.target_repo,
            target_type=args.target_type,
            resource=args.oidc_resource,
            selected=selected,
            attempts=attempts,
            recovery=recovery,
        )
        print(
            "::error::Hugging Face publisher credential validation failed: "
            f"{type(error).__name__}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
