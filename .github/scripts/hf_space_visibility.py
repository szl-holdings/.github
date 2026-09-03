"""Keep the Hugging Face organization-card Space publicly readable.

Hugging Face renders an organization card only when a public Space named
``README`` exists in the organization. This helper makes the visibility
contract explicit, then verifies the Space metadata without authentication so
a protected/private regression cannot silently remove the front door.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 1_000_000


class VisibilityContractError(RuntimeError):
    """Raised when the organization-card Space is not verifiably public."""


@dataclass(frozen=True)
class VisibilityReport:
    schema: str
    repo_id: str
    requested_visibility: str
    authenticated_visibility: str
    unauthenticated_status: int
    unauthenticated_visibility: str
    unauthenticated_readable: bool
    changed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"


def _visibility_from_info(info: Any) -> str:
    visibility = getattr(info, "visibility", None)
    if isinstance(visibility, str) and visibility:
        return visibility.casefold()
    private = getattr(info, "private", None)
    if private is True:
        return "private"
    if private is False:
        return "public-or-protected"
    return "unknown"


def _metadata_visibility(payload: dict[str, Any]) -> str:
    visibility = payload.get("visibility")
    if isinstance(visibility, str) and visibility:
        return visibility.casefold()
    private = payload.get("private")
    if private is True:
        return "private"
    if private is False:
        return "public"
    return "unknown"


def _trusted_huggingface_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == "huggingface.co"
        and parsed.username is None
        and parsed.password is None
    )


def fetch_public_metadata(
    repo_id: str,
    opener: Callable[..., Any] = urlopen,
) -> tuple[int, dict[str, Any], str]:
    """Fetch Space metadata without a token and enforce origin/size bounds."""

    url = f"https://huggingface.co/api/spaces/{quote(repo_id, safe='/')}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "szl-hf-org-card-visibility/1",
        },
    )
    with opener(request, timeout=20) as response:
        status = int(getattr(response, "status", response.getcode()))
        final_url = response.geturl()
        if not _trusted_huggingface_url(final_url):
            raise VisibilityContractError(
                "unauthenticated metadata request left the Hugging Face origin"
            )
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise VisibilityContractError("unauthenticated metadata response is oversized")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VisibilityContractError(
            "unauthenticated metadata response is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise VisibilityContractError("unauthenticated metadata response is not an object")
    return status, payload, final_url


def _metadata_matches_public_repo(payload: dict[str, Any], repo_id: str) -> tuple[bool, str]:
    observed_id = payload.get("id") or payload.get("repo_id")
    if not isinstance(observed_id, str) or observed_id.casefold() != repo_id.casefold():
        return False, "unknown"
    visibility = _metadata_visibility(payload)
    # An explicit public value is ideal. Older Hub responses expose only
    # private=false; unauthenticated success plus that flag is still a valid
    # public-readability proof. Unknown metadata fails closed.
    return visibility == "public", visibility


def _set_public(api: Any, repo_id: str) -> None:
    try:
        api.update_repo_settings(
            repo_id=repo_id,
            repo_type="space",
            visibility="public",
        )
    except TypeError as exc:
        raise VisibilityContractError(
            "installed huggingface_hub lacks protected/public visibility support"
        ) from exc


def ensure_public_space(
    repo_id: str,
    token: str,
    *,
    wait_seconds: int = 90,
    check_only: bool = False,
    api_factory: Callable[..., Any] | None = None,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> VisibilityReport:
    """Set public visibility and prove unauthenticated readability."""

    if not repo_id or "/" not in repo_id:
        raise VisibilityContractError("repo_id must be namespace/name")
    if not token:
        raise VisibilityContractError("HF_TOKEN is required")
    if wait_seconds < 1 or wait_seconds > 600:
        raise VisibilityContractError("wait_seconds must be between 1 and 600")

    if api_factory is None:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise VisibilityContractError("huggingface_hub is required") from exc
        api_factory = HfApi

    api = api_factory(token=token)
    before = api.repo_info(repo_id=repo_id, repo_type="space")
    before_visibility = _visibility_from_info(before)
    changed = False
    if not check_only:
        _set_public(api, repo_id)
        changed = before_visibility != "public"

    after = api.repo_info(repo_id=repo_id, repo_type="space")
    authenticated_visibility = _visibility_from_info(after)
    if authenticated_visibility in {"private", "protected", "unknown"}:
        raise VisibilityContractError(
            "authenticated repository metadata does not report a public Space"
        )

    deadline = time.monotonic() + wait_seconds
    last_status = 0
    last_visibility = "unknown"
    last_error = ""
    while time.monotonic() < deadline:
        try:
            status, payload, _ = fetch_public_metadata(repo_id, opener=opener)
            last_status = status
            matches, last_visibility = _metadata_matches_public_repo(payload, repo_id)
            if status == 200 and matches:
                return VisibilityReport(
                    schema="szl.hf-space-visibility/v1",
                    repo_id=repo_id,
                    requested_visibility="public",
                    authenticated_visibility=authenticated_visibility,
                    unauthenticated_status=status,
                    unauthenticated_visibility=last_visibility,
                    unauthenticated_readable=True,
                    changed=changed,
                )
            last_error = "public metadata did not identify a public target Space"
        except (HTTPError, URLError, TimeoutError, VisibilityContractError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, HTTPError):
                last_status = exc.code
        sleeper(3)

    raise VisibilityContractError(
        "Space did not become publicly readable without authentication "
        f"(status={last_status}, visibility={last_visibility}, last={last_error})"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enforce and verify public visibility for a Hugging Face Space."
    )
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--wait-seconds", type=int, default=90)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get("HF_TOKEN", "")
    try:
        report = ensure_public_space(
            args.repo_id,
            token,
            wait_seconds=args.wait_seconds,
            check_only=args.check_only,
        )
    except VisibilityContractError as exc:
        print(f"error: {exc}")
        return 2
    encoded = report.to_json()
    print(encoded, end="")
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
