#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One disclosure boundary for the public CI issue, JSON, log and summary.

All repositories are still swept. Non-public failures affect totals and issue
state, but never contribute identifiers, workflow text or links to this view.
Visibility is checked again for each public detail immediately before rendering;
that observation is bounded, not an atomic guarantee about future visibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from typing import Any, Callable, Mapping, Sequence

ORG = "szl-holdings"
DISPOSITIONS = ("ACTIONABLE", "FOUNDER-GATED", "INTENTIONAL", "INFRA")
PROVENANCE = {
    "protected_default_branch": "default_branch_protection_unverified",
    "github_managed_dynamic": "github_managed_dynamic",
}
NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")


class PublicationError(ValueError):
    """Fail closed without reflecting private provider data in diagnostics."""


@dataclass(frozen=True)
class PublicDigest:
    body: str
    red_runs: dict[str, list[dict[str, Any]]]
    dispositions: dict[str, int]
    red_total: int
    restricted_red_total: int


def _public(metadata: Mapping[str, Any], name: str) -> bool:
    if not isinstance(metadata, Mapping):
        raise PublicationError("repository visibility response is malformed")
    if metadata.get("name") != name or metadata.get("full_name") != f"{ORG}/{name}":
        raise PublicationError("repository identity did not match")
    private, visibility = metadata.get("private"), metadata.get("visibility")
    if type(private) is not bool:
        raise PublicationError("repository visibility is unknown")
    if private is False and visibility == "public":
        return True
    if private is True and visibility in {"private", "internal"}:
        return False
    raise PublicationError("repository visibility is inconsistent or unknown")


def _number(value: Any, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0:
        raise PublicationError("numeric evidence field is invalid")
    return value


def _cell(value: Any) -> str:
    text = html.escape(str(value), quote=True)
    return text.replace("\n", " ").replace("\r", " ").replace("|", "&#124;").replace("`", "&#96;")


def public_digest(
    reds: Mapping[str, Sequence[Any]],
    repositories: Sequence[Mapping[str, Any]],
    *,
    coverage: Mapping[str, Any],
    authentication_mode: str,
    classify: Callable[..., tuple[str, str]],
    visibility_reader: Callable[[str], Mapping[str, Any]],
) -> PublicDigest:
    """Render only public detail while preserving estate-wide failure counts.

    The legacy sweep's source-lane name is not evidence of protection. Externally
    it is explicitly marked unverified; this module never asserts policy state.
    """
    inventory: dict[str, Mapping[str, Any]] = {}
    public: dict[str, bool] = {}
    for metadata in repositories:
        if not isinstance(metadata, Mapping):
            raise PublicationError("repository inventory is malformed")
        name = metadata.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in {".", ".."}:
            raise PublicationError("repository inventory identity is invalid")
        if name.lower() in inventory:
            raise PublicationError("repository inventory contains duplicate identities")
        inventory[name.lower()] = metadata
        public[name] = _public(metadata, name)
    if _number(coverage.get("organization_repositories")) != len(inventory):
        raise PublicationError("publication inventory coverage did not match")

    counts = dict.fromkeys(DISPOSITIONS, 0)
    published: dict[str, list[dict[str, Any]]] = {}
    rows: list[str] = []
    restricted = 0
    for name in sorted(reds):
        if name not in public:
            raise PublicationError("red workflow lacks repository visibility evidence")
        allowed = public[name]
        items = reds[name]
        if allowed and items:
            current = visibility_reader(name)
            allowed = _public(current, name)
            before_id = inventory[name.lower()].get("id")
            if before_id is not None and current.get("id") != before_id:
                raise PublicationError("repository identity changed before publication")
        for red in items:
            if red.repository != name:
                raise PublicationError("red workflow repository identity did not match")
            disposition, note = classify(
                name, red.workflow, event=red.event, run_number=red.run_number,
                run_id=red.run_id, run_attempt=red.run_attempt,
            )
            if disposition not in counts:
                raise PublicationError("workflow disposition is unknown")
            counts[disposition] += 1
            if not allowed:
                restricted += 1
                continue
            if red.provenance not in PROVENANCE:
                raise PublicationError("workflow evidence lane is unknown")
            run_id = _number(red.run_id, nullable=True)
            run_number = _number(red.run_number, nullable=True)
            run_attempt = _number(red.run_attempt, nullable=True)
            # Never publish a provider-supplied URL with a foreign host or path.
            url = f"https://github.com/{ORG}/{name}/actions/runs/{run_id}" if run_id else None
            record = {
                "repository": name,
                "workflow": red.workflow,
                "provenance": PROVENANCE[red.provenance],
                "conclusion": red.conclusion,
                "run_id": run_id,
                "run_attempt": run_attempt,
                "run_number": run_number,
                "event": red.event,
                "url": url,
            }
            published.setdefault(name, []).append(record)
            link = f"[run {run_id}]({url})" if url else "run link unavailable"
            rows.append(
                f"- **{_cell(name)} / {_cell(red.workflow)}**: {_cell(red.conclusion)}; "
                f"{disposition}; `{record['provenance']}`; {link}. {_cell(note)}"
            )

    total = sum(counts.values())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    active = _number(coverage.get("active_repositories"))
    archived = _number(coverage.get("archived_repositories"))
    queried = _number(coverage.get("queried_active_repositories"))
    source = _number(coverage.get("default_branch_workflows", coverage.get("active_workflows", 0)))
    dynamic = _number(coverage.get("github_managed_dynamic_workflows", 0))
    registered = _number(coverage.get("registered_active_workflows", source + dynamic))
    excluded = _number(coverage.get("excluded_non_default_workflows", 0))
    lines = [
        "_Auto-generated by `.github/workflows/ci-health-digest.yml`. " + f"Observation: **{now}**._",
        "",
        f"Coverage: **{len(inventory)} repositories** ({active} active, {archived} archived); "
        f"**{queried} active repositories queried**; **{source} default-branch workflow files** "
        f"and **{dynamic} GitHub-managed dynamic workflows** inspected. "
        f"Registered active entries: **{registered}**; excluded non-default files: **{excluded}**.",
        "",
        f"Authentication mode: `{_cell(authentication_mode)}`; credential value recorded: `false`.",
        "",
        f"**{total} red workflow(s)** across the observed estate — "
        f"**{counts['ACTIONABLE']} ACTIONABLE**, {counts['FOUNDER-GATED']} founder-gated, "
        f"{counts['INTENTIONAL']} intentional, {counts['INFRA']} infra.",
        "",
        f"Public detail: **{total - restricted}** red workflows. "
        f"Restricted detail withheld: **{restricted}** red workflows; those failures remain in all totals and issue-state decisions.",
        "",
        "Branch protection is **NOT VERIFIED** by this digest. Default-branch file existence and "
        "branch-bound runs do not establish enforced branch policies or current-head CI success.",
        "",
    ]
    lines.extend(rows)
    if total == 0:
        lines.append("No red latest workflow runs were observed in the completed sweep. This is not a release or runtime qualification.")
    lines.extend([
        "", "---",
        "Repository visibility was re-read before publishing public workflow detail. This is a bounded "
        "observation, not an atomic guarantee of future visibility. Private/internal identifiers, workflow "
        "names and run links are excluded from this public issue, report, log and summary. "
        "Classification policy and fail-closed collection are unchanged. No raw private details are persisted by this publisher.",
    ])
    return PublicDigest("\n".join(lines), published, counts, total, restricted)
