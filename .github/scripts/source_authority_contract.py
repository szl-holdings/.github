#!/usr/bin/env python3
"""Bind rollout automation to the reviewed Space presentation authority.

The base rollout controller intentionally excludes central repositories from
heuristic and provider-derived matching. This extension preserves that safety
boundary while making the protected local source map truly authoritative: only
a locally reviewed mapping can bypass the central-repository exclusion, no
declared local target falls back to a heuristic candidate, and generated
publisher surfaces are recorded as publisher-managed instead of receiving a
guessed frontend edit in a product repository.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

PUBLISHER_MANAGED_STATUS = "publisher-managed"
PUBLISHER_OWNERSHIP = "publisher-generated-flagship"
CORE_MANAGED_SPACES = frozenset({"a11oy"})


def _active_repository(repo: Mapping[str, Any]) -> bool:
    return not any(
        (
            repo.get("archived"),
            repo.get("disabled"),
            repo.get("fork"),
        )
    )


def _repository_is_excluded(core: Any, full_name: str) -> bool:
    return full_name.split("/", 1)[-1] in core.EXCLUDED_REPOS


def _source_entries(core: Any) -> dict[str, dict[str, Any]]:
    path = Path(core.LOCAL_SOURCE_MAP)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "szl.public-space-source-map/v1":
        raise core.RolloutError(
            "LOCAL_SOURCE_MAP_SCHEMA_INVALID",
            str(payload.get("schema")),
        )
    values = payload.get("sources")
    if not isinstance(values, list):
        raise core.RolloutError(
            "LOCAL_SOURCE_MAP_INVALID",
            "sources must be a list",
        )

    entries: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, dict):
            raise core.RolloutError(
                "LOCAL_SOURCE_MAP_INVALID",
                "source entries must be objects",
            )
        slug = core._space_slug(item.get("space"))
        repo = core._canonical_repo(item.get("repo"))
        if not slug or not repo:
            raise core.RolloutError(
                "LOCAL_SOURCE_MAP_INVALID",
                json.dumps(item, sort_keys=True),
            )
        normalized = dict(item)
        normalized["space"] = slug
        normalized["repo"] = repo
        previous = entries.get(slug)
        if previous and previous != normalized:
            raise core.RolloutError("LOCAL_SOURCE_MAP_CONFLICT", slug)
        entries[slug] = normalized
    return entries


def _append_group(
    grouped: dict[str, tuple[list[Any], int, str]],
    repository: str,
    space: Any,
    score: int,
    reason: str,
) -> None:
    current = grouped.get(repository)
    if current:
        spaces, previous_score, previous_reason = current
        spaces.append(space)
        grouped[repository] = (
            spaces,
            max(previous_score, score),
            previous_reason + "; " + reason,
        )
    else:
        grouped[repository] = ([space], score, reason)


def install(core: Any) -> None:
    """Install exact source-authority resolution and publisher boundaries once."""
    if getattr(core, "_szl_source_authority_contract_installed", False):
        return

    original_group_mappings = core.group_mappings
    original_plan_repository = core.plan_repository

    def group_mappings(
        spaces: Sequence[Any],
        repos: list[dict[str, Any]],
        explicit: Mapping[str, str],
    ) -> tuple[
        dict[str, tuple[list[Any], int, str]],
        list[dict[str, Any]],
    ]:
        local_entries = _source_entries(core)
        reviewed_exact: list[tuple[Any, dict[str, Any]]] = []
        heuristic_spaces: list[Any] = []
        unmapped: list[dict[str, Any]] = []

        for space in spaces:
            slug = core.normalize(space.slug)
            if slug in CORE_MANAGED_SPACES:
                unmapped.append(
                    {
                        "slug": space.slug,
                        "sdk": space.sdk,
                        "stage": space.stage,
                        "reason": (
                            "core product Space is managed outside the vertical "
                            "rollout controller"
                        ),
                    }
                )
                continue

            entry = local_entries.get(slug)
            if entry is None:
                # Provider metadata can still improve ordinary matching, but it
                # remains inside the base controller's excluded-repository
                # boundary and therefore cannot acquire local review authority.
                heuristic_spaces.append(space)
                continue

            repository = str(entry["repo"])
            if _repository_is_excluded(core, repository):
                if entry.get("ownership") != PUBLISHER_OWNERSHIP:
                    raise core.RolloutError(
                        "LOCAL_EXCLUDED_REPOSITORY_UNAUTHORIZED",
                        (
                            f"{space.slug} maps to excluded repository "
                            f"{repository} without publisher ownership"
                        ),
                    )
                source_root = entry.get("source_root")
                if not isinstance(source_root, str) or not source_root:
                    raise core.RolloutError(
                        "PUBLISHER_ENTRYPOINT_UNDECLARED",
                        f"{space.slug} has no publisher source_root",
                    )
            reviewed_exact.append((space, entry))

        grouped, heuristic_unmapped = original_group_mappings(
            heuristic_spaces,
            repos,
            explicit,
        )
        unmapped.extend(heuristic_unmapped)

        available = {
            str(repo.get("full_name") or ""): repo
            for repo in repos
            if _active_repository(repo) and repo.get("full_name")
        }
        for space, entry in reviewed_exact:
            slug = core.normalize(space.slug)
            repository = str(entry["repo"])
            repo = available.get(repository)
            if repo is None:
                unmapped.append(
                    {
                        "slug": space.slug,
                        "sdk": space.sdk,
                        "stage": space.stage,
                        "reason": (
                            "declared local source repository is unavailable; "
                            "heuristic fallback is forbidden"
                        ),
                        "declared_repository": repository,
                    }
                )
                continue
            score, reason = core.mapping_score(
                space,
                repo,
                {slug: repository},
            )
            if score != 1000:
                raise core.RolloutError(
                    "LOCAL_SOURCE_MAP_NOT_AUTHORITATIVE",
                    f"{space.slug} did not receive the canonical mapping score",
                )
            _append_group(grouped, repository, space, score, reason)
        return grouped, unmapped

    core.group_mappings = group_mappings

    def plan_repository(
        github: Any,
        repo: Mapping[str, Any],
        spaces: list[Any],
        score: int,
        reason: str,
        css: str,
        javascript: str,
    ) -> Any:
        entries = _source_entries(core)
        full_name = str(repo.get("full_name") or "")
        managed: list[tuple[Any, dict[str, Any]]] = []
        ordinary: list[Any] = []
        for space in spaces:
            entry = entries.get(core.normalize(space.slug))
            if (
                entry
                and entry.get("repo") == full_name
                and entry.get("ownership") == PUBLISHER_OWNERSHIP
            ):
                managed.append((space, entry))
            else:
                ordinary.append(space)

        if not managed:
            return original_plan_repository(
                github,
                repo,
                spaces,
                score,
                reason,
                css,
                javascript,
            )
        if ordinary:
            raise core.RolloutError(
                "MIXED_PUBLISHER_AUTHORITY",
                (
                    f"{full_name} mixes publisher-generated and directly "
                    "adaptable Spaces in one rollout plan"
                ),
            )

        default_branch = str(repo.get("default_branch") or "main")
        plan = core.Plan(full_name, default_branch, spaces, score, reason)
        paths = {
            str(item.get("path") or "")
            for item in github.tree(full_name, default_branch)
        }
        entrypoints: list[str] = []
        for space, entry in managed:
            source_root = entry.get("source_root")
            if not isinstance(source_root, str) or not source_root:
                raise core.RolloutError(
                    "PUBLISHER_ENTRYPOINT_UNDECLARED",
                    f"{space.slug} has no publisher source_root",
                )
            if source_root not in paths:
                raise core.RolloutError(
                    "PUBLISHER_ENTRYPOINT_MISSING",
                    f"{full_name}:{source_root} does not exist",
                )
            entrypoints.append(source_root)

        plan.status = PUBLISHER_MANAGED_STATUS
        plan.adapter = "publisher-generator"
        plan.entrypoint = ", ".join(sorted(set(entrypoints)))
        plan.changes = []
        plan.error = None
        return plan

    core.plan_repository = plan_repository
    core._szl_source_authority_contract_installed = True
