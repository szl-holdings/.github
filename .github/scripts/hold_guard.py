#!/usr/bin/env python3
"""Fail a pull request, or its merge-queue group, while it is marked HOLD.

HOLD used to exist only as prose and hand-copied local lists, so GitHub knew
nothing about it and every HOLD pull request merged. This guard gives HOLD a
machine-checked meaning that a required status check can enforce.

A pull request is HELD when either of these is true:

* it carries a label whose normalized name is one of ``HOLD_LABELS``
  (case-insensitive; spaces, underscores and hyphens are interchangeable, so
  ``HOLD``, ``hold``, ``Do Not Merge`` and ``do_not_merge`` all count); or
* its title contains ``[HOLD]``, ``[DNM]``, ``[do not merge]`` (any case,
  optional inner spaces) or the standalone word ``DNM``.

Prose such as "under HOLD" in a title is deliberately NOT a marker: HOLD must
be declared explicitly with a label or the bracketed title marker. Nor is
``dnm`` inside an identifier such as a package name (``dnm-lib``,
``@scope/dnm``, ``dnm_utils``), so a dependency bump cannot be held by accident.

The guard evaluates the event payload AND a live read of the pull request, and
fails if either shows a marker. The live read covers the merge-queue event,
whose payload has no labels or title, and a label added after the triggering
event. It performs one read-only REST request per run and needs only
``pull-requests: read``. It never checks out or executes pull-request content.

Exit codes:
  0 -- the pull request carries no HOLD marker
  1 -- a HOLD marker is present; the merge must stay blocked
  2 -- the guard could not evaluate (unsupported event, malformed payload,
       missing token, API failure). This is a failure, never a silent pass.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HOLD_LABELS = frozenset({"hold", "hold-for-owner", "do-not-merge", "dnm"})

TITLE_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[\s*hold\s*\]", re.IGNORECASE), "[HOLD]"),
    (
        re.compile(
            r"\[\s*(?:dnm|do[\s_-]*not[\s_-]*merge)\s*\]", re.IGNORECASE
        ),
        "[DNM] / [do not merge]",
    ),
    # The bare word DNM counts only when it stands alone. A letter, digit,
    # underscore, hyphen, dot, slash or @ next to it makes it part of an
    # identifier (a Dependabot "bump dnm-lib" or "@scope/dnm"), not a marker.
    (re.compile(r"(?<![\w./@-])dnm(?![\w./@-])", re.IGNORECASE), "DNM"),
)

PULL_REQUEST_EVENTS = frozenset({"pull_request", "pull_request_target"})
MERGE_GROUP_EVENT = "merge_group"
MERGE_QUEUE_REF = re.compile(
    r"^refs/heads/gh-readonly-queue/(?P<base>.+)/"
    r"pr-(?P<number>[1-9][0-9]*)-(?P<sha>[0-9a-f]{40})$"
)
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LABEL_SEPARATORS = re.compile(r"[\s_-]+")
TRANSIENT_HTTP = frozenset({429, 500, 502, 503, 504})
FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_SECONDS = 20

EXIT_CLEAR = 0
EXIT_HELD = 1
EXIT_UNVERIFIED = 2


class GuardError(Exception):
    """The guard cannot reach a verdict; the caller must fail closed."""


def normalize_label(name: str) -> str:
    return LABEL_SEPARATORS.sub("-", name.strip().lower()).strip("-")


def label_names(labels: object) -> list[str]:
    if not isinstance(labels, list):
        raise GuardError("pull request labels are not a list")
    names: list[str] = []
    for label in labels:
        if isinstance(label, Mapping):
            name = label.get("name")
        else:
            name = label
        if not isinstance(name, str):
            raise GuardError("a pull request label has no string name")
        names.append(name)
    return names


def hold_reasons(title: object, labels: Iterable[str]) -> list[str]:
    """Return one human-readable reason per HOLD marker found."""

    if not isinstance(title, str):
        raise GuardError("pull request title is not a string")
    reasons: list[str] = []
    for name in labels:
        if normalize_label(name) in HOLD_LABELS:
            reasons.append(f"label {name!r}")
    for pattern, marker in TITLE_MARKERS:
        if pattern.search(title):
            reasons.append(f"title marker {marker}")
    return reasons


def load_event(event_path: str | None) -> dict[str, Any]:
    if not event_path:
        raise GuardError("GITHUB_EVENT_PATH is not set")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardError(f"cannot read the event payload: {exc}") from exc
    if not isinstance(event, dict):
        raise GuardError("the event payload is not a JSON object")
    return event


def positive_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GuardError(f"{what} is not a positive integer")
    return value


def merge_group_pull_number(event: Mapping[str, Any]) -> int:
    if event.get("action") != "checks_requested":
        raise GuardError(
            f"unsupported merge_group action {event.get('action')!r}"
        )
    group = event.get("merge_group")
    if not isinstance(group, Mapping):
        raise GuardError("merge_group payload is missing")
    head_ref = group.get("head_ref")
    match = MERGE_QUEUE_REF.fullmatch(head_ref) if isinstance(head_ref, str) else None
    if match is None:
        raise GuardError(f"unrecognized merge-queue ref {head_ref!r}")
    if group.get("base_ref") != f"refs/heads/{match.group('base')}":
        raise GuardError("merge-queue ref does not match the group's base ref")
    return int(match.group("number"))


def fetch_pull(
    api_url: str,
    repository: str,
    number: int,
    token: str,
    *,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Read the live pull request with a bounded retry on transient errors."""

    url = f"{api_url.rstrip('/')}/repos/{repository}/pulls/{number}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-holdings-hold-guard",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    last_error = "no attempt made"
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with opener(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                body = response.read()
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in TRANSIENT_HTTP:
                break
        except (URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            try:
                data = json.loads(body)
            except (ValueError, UnicodeDecodeError) as exc:
                raise GuardError(f"live pull request is not JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise GuardError("live pull request is not a JSON object")
            return data
        if attempt < FETCH_ATTEMPTS:
            sleep(2.0 * attempt)
    raise GuardError(f"cannot read live pull request #{number}: {last_error}")


def annotation(text: str) -> str:
    """Escape untrusted text so it cannot start a new workflow command."""

    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def evaluate(
    event_name: str,
    event: Mapping[str, Any],
    live_pull: Callable[[int], Mapping[str, Any]],
) -> tuple[int, list[str]]:
    """Return the pull-request number and every HOLD reason found."""

    reasons: list[str] = []
    if event_name in PULL_REQUEST_EVENTS:
        pull = event.get("pull_request")
        if not isinstance(pull, Mapping):
            raise GuardError(f"{event_name} payload has no pull_request object")
        number = positive_int(pull.get("number"), "pull request number")
        reasons.extend(
            f"{reason} (event payload)"
            for reason in hold_reasons(pull.get("title"), label_names(pull.get("labels")))
        )
    elif event_name == MERGE_GROUP_EVENT:
        number = merge_group_pull_number(event)
    else:
        raise GuardError(
            f"unsupported event {event_name!r}; call this guard only from "
            "pull_request or merge_group workflows"
        )

    live = live_pull(number)
    if live.get("number") != number:
        raise GuardError(
            f"live read returned pull request {live.get('number')!r}, expected #{number}"
        )
    reasons.extend(
        f"{reason} (live pull request)"
        for reason in hold_reasons(live.get("title"), label_names(live.get("labels")))
    )
    return number, reasons


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    fetch: Callable[..., Mapping[str, Any]] = fetch_pull,
) -> int:
    del argv  # The guard takes no arguments; all inputs come from the event.
    env = os.environ if environ is None else environ
    try:
        event_name = env.get("GITHUB_EVENT_NAME", "")
        event = load_event(env.get("GITHUB_EVENT_PATH"))
        repository = env.get("GITHUB_REPOSITORY", "")
        if not REPOSITORY.fullmatch(repository):
            raise GuardError(f"GITHUB_REPOSITORY {repository!r} is malformed")
        api_url = env.get("GITHUB_API_URL") or "https://api.github.com"
        if not api_url.startswith("https://"):
            raise GuardError("GITHUB_API_URL must be an https URL")
        token = env.get("GITHUB_TOKEN", "")
        if not token:
            raise GuardError("GITHUB_TOKEN is not set; the live read is mandatory")

        def live_pull(number: int) -> Mapping[str, Any]:
            return fetch(api_url, repository, number, token)

        number, reasons = evaluate(event_name, event, live_pull)
    except GuardError as exc:
        print(
            f"::error title=hold-guard could not evaluate::{annotation(str(exc))}"
        )
        print("hold-guard: NOT VERIFIED -- failing closed.", file=sys.stderr)
        return EXIT_UNVERIFIED

    if reasons:
        for reason in reasons:
            print(
                f"::error title=HOLD::{annotation(f'{repository}#{number} is on HOLD: {reason}')}"
            )
        print(
            f"hold-guard: {repository}#{number} is HELD. Remove every HOLD "
            "label and title marker to release it; this check re-runs on "
            "label and title changes."
        )
        return EXIT_HELD

    print(f"hold-guard: {repository}#{number} carries no HOLD marker.")
    return EXIT_CLEAR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
