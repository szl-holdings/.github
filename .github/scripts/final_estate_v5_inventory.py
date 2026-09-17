#!/usr/bin/env python3
"""Read-only public PR evidence for the existing v5 reconciler.

A positive search is enough to reject a zero-PR claim. An empty search is not
proof of absence: only a coverage-checked per-repository census may authorize
that narrowly defined claim. No issue/PR mutation or provider operation occurs
here. Sequential readbacks are observations, not an atomic GitHub lease.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

ORG = "szl-holdings"
API = "https://api.github.com"
WEB = "https://github.com"
REPO = re.compile(r"^szl-holdings/[A-Za-z0-9_.-]+$")
PAGE_SIZE = 100
MAX_REPOSITORIES = 1000
MAX_PULL_REQUESTS = 1000
MAX_REQUESTS = 512
TIME_BUDGET_SECONDS = 480.0


class CensusError(RuntimeError):
    """A fixed diagnostic code; never include provider bodies or credentials."""


@dataclass(frozen=True)
class Observation:
    items: list[dict[str, Any]]
    evidence: dict[str, Any]


def _integer(value: Any, code: str, *, minimum: int = 0, maximum: int = 1000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CensusError(code)
    return value


def _repository_name(value: Any) -> bool:
    return isinstance(value, str) and REPO.fullmatch(value) is not None and value.rsplit("/", 1)[-1] not in (".", "..")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PublicPullRequestObserver:
    def __init__(self, request: Callable[..., Any], *, clock: Callable[[], float] = time.monotonic) -> None:
        self.request = request
        self.clock = clock
        self.started = clock()
        self.calls = 0
        self.started_at = datetime.now(timezone.utc).isoformat()

    def _get(self, path: str, **params: Any) -> Any:
        if self.calls >= MAX_REQUESTS or self.clock() - self.started > TIME_BUDGET_SECONDS:
            raise CensusError("PUBLIC_PR_OBSERVATION_BUDGET")
        self.calls += 1
        try:
            response = self.request("GET", path, params=params or None)
            payload = response.json()
        except Exception:
            raise CensusError("PUBLIC_PR_READ_UNAVAILABLE") from None
        if self.clock() - self.started > TIME_BUDGET_SECONDS:
            raise CensusError("PUBLIC_PR_OBSERVATION_BUDGET")
        return payload

    def _pr(self, value: Any, *, repository: str | None = None) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise CensusError("PUBLIC_PR_ITEM_SCHEMA")
        number = _integer(value.get("number"), "PUBLIC_PR_NUMBER", minimum=1, maximum=2**53 - 1)
        _integer(value.get("id"), "PUBLIC_PR_ID", minimum=1, maximum=2**53 - 1)
        if value.get("state") != "open":
            raise CensusError("PUBLIC_PR_STATE")
        if repository is None:
            repo_url = value.get("repository_url")
            prefix = API + "/repos/"
            if not isinstance(repo_url, str) or not repo_url.startswith(prefix):
                raise CensusError("PUBLIC_PR_REPOSITORY")
            repository = repo_url[len(prefix):]
            if not _repository_name(repository):
                raise CensusError("PUBLIC_PR_REPOSITORY")
            discriminator = value.get("pull_request")
            if not isinstance(discriminator, dict) or discriminator.get("url") != f"{API}/repos/{repository}/pulls/{number}":
                raise CensusError("PUBLIC_PR_DISCRIMINATOR")
        else:
            base = value.get("base")
            base_repo = base.get("repo") if isinstance(base, dict) else None
            if not isinstance(base_repo, dict) or base_repo.get("full_name") != repository or base_repo.get("private") is not False:
                raise CensusError("PUBLIC_PR_BASE_REPOSITORY")
            if value.get("url") != f"{API}/repos/{repository}/pulls/{number}":
                raise CensusError("PUBLIC_PR_API_IDENTITY")
        if value.get("html_url") != f"{WEB}/{repository}/pull/{number}":
            raise CensusError("PUBLIC_PR_WEB_IDENTITY")
        if type(value.get("draft")) is not bool:
            raise CensusError("PUBLIC_PR_DRAFT_SCHEMA")
        # Expose only the public fields used by the existing report. No bodies.
        return {
            "id": value["id"], "number": number,
            "repository_url": f"{API}/repos/{repository}",
            "title": value.get("title") if isinstance(value.get("title"), str) else None,
            "html_url": value["html_url"], "draft": value["draft"],
            "updated_at": value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
        }

    def _search(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        identities: set[int] = set()
        locations: set[tuple[str, int]] = set()
        total: int | None = None
        for page in range(1, MAX_PULL_REQUESTS // PAGE_SIZE + 1):
            payload = self._get("/search/issues", q=f"org:{ORG} is:pr is:open is:public", per_page=PAGE_SIZE, page=page)
            if not isinstance(payload, dict) or payload.get("incomplete_results") is not False:
                raise CensusError("PUBLIC_PR_SEARCH_INCOMPLETE")
            observed = _integer(payload.get("total_count"), "PUBLIC_PR_SEARCH_TOTAL", maximum=MAX_PULL_REQUESTS)
            if total is not None and observed != total:
                raise CensusError("PUBLIC_PR_SEARCH_MOVED")
            total = observed
            rows = payload.get("items")
            remaining = total - len(result)
            if not isinstance(rows, list) or len(rows) != min(PAGE_SIZE, remaining):
                raise CensusError("PUBLIC_PR_SEARCH_CARDINALITY")
            for row in rows:
                item = self._pr(row)
                key = (item["repository_url"], item["number"])
                if item["id"] in identities or key in locations:
                    raise CensusError("PUBLIC_PR_SEARCH_DUPLICATE")
                identities.add(item["id"])
                locations.add(key)
                result.append(item)
            if len(result) == total:
                return result
        raise CensusError("PUBLIC_PR_SEARCH_BOUND")

    def _org_count(self) -> int:
        payload = self._get(f"/orgs/{ORG}")
        if not isinstance(payload, dict) or payload.get("login") != ORG:
            raise CensusError("PUBLIC_PR_ORGANIZATION_IDENTITY")
        return _integer(payload.get("public_repos"), "PUBLIC_PR_REPOSITORY_COUNT", minimum=1, maximum=MAX_REPOSITORIES)

    def _repositories(self, expected: int) -> tuple[tuple[int, str], ...]:
        rows: list[tuple[int, str]] = []
        ids: set[int] = set()
        names: set[str] = set()
        for page in range(1, MAX_REPOSITORIES // PAGE_SIZE + 2):
            payload = self._get(f"/orgs/{ORG}/repos", type="public", per_page=PAGE_SIZE, page=page, sort="full_name", direction="asc")
            if not isinstance(payload, list) or len(payload) > PAGE_SIZE:
                raise CensusError("PUBLIC_PR_REPOSITORY_LIST_SCHEMA")
            for item in payload:
                if not isinstance(item, dict) or item.get("private") is not False or item.get("visibility") not in (None, "public"):
                    raise CensusError("PUBLIC_PR_REPOSITORY_VISIBILITY")
                owner = item.get("owner")
                name = item.get("full_name")
                identity = _integer(item.get("id"), "PUBLIC_PR_REPOSITORY_ID", minimum=1, maximum=2**53 - 1)
                if not isinstance(owner, dict) or owner.get("login") != ORG or not _repository_name(name):
                    raise CensusError("PUBLIC_PR_REPOSITORY_IDENTITY")
                if identity in ids or name in names:
                    raise CensusError("PUBLIC_PR_REPOSITORY_DUPLICATE")
                ids.add(identity)
                names.add(name)
                rows.append((identity, name))
                if len(rows) > expected:
                    raise CensusError("PUBLIC_PR_REPOSITORY_COVERAGE")
            if len(payload) < PAGE_SIZE:
                if len(rows) != expected or not {f"{ORG}/.github", f"{ORG}/a11oy"}.issubset(names):
                    raise CensusError("PUBLIC_PR_REPOSITORY_COVERAGE")
                return tuple(sorted(rows))
        raise CensusError("PUBLIC_PR_REPOSITORY_BOUND")

    def _repository_prs(self, repository: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        ids: set[int] = set()
        numbers: set[int] = set()
        for page in range(1, MAX_PULL_REQUESTS // PAGE_SIZE + 2):
            payload = self._get(f"/repos/{repository}/pulls", state="open", per_page=PAGE_SIZE, page=page, sort="created", direction="asc")
            if not isinstance(payload, list) or len(payload) > PAGE_SIZE:
                raise CensusError("PUBLIC_PR_REPOSITORY_PULL_SCHEMA")
            for row in payload:
                item = self._pr(row, repository=repository)
                if item["id"] in ids or item["number"] in numbers:
                    raise CensusError("PUBLIC_PR_REPOSITORY_PULL_DUPLICATE")
                ids.add(item["id"])
                numbers.add(item["number"])
                output.append(item)
                if len(output) > MAX_PULL_REQUESTS:
                    raise CensusError("PUBLIC_PR_REPOSITORY_PULL_BOUND")
            if len(payload) < PAGE_SIZE:
                return output
        raise CensusError("PUBLIC_PR_REPOSITORY_PULL_BOUND")

    def observe(self) -> Observation:
        search = self._search()
        evidence: dict[str, Any] = {
            "schema": "szl.public-pr-observation/v1", "organization": ORG,
            "visibility_scope": "public", "started_at": self.started_at,
            "search_count": len(search), "zero_closure_authorized": False,
            "atomic_snapshot": False, "source_content_audit": False,
        }
        if search:
            evidence.update(method="validated-positive-search", requests_attempted=self.calls,
                            finished_at=datetime.now(timezone.utc).isoformat())
            return Observation(search, evidence)

        # Repository-scoped tokens must demonstrate coverage; HTTP 200 is not
        # evidence that all of the organization's repositories were visible.
        count = self._org_count()
        repositories = self._repositories(count)
        collected: list[dict[str, Any]] = []
        global_ids: set[int] = set()
        for _, repository in repositories:
            for item in self._repository_prs(repository):
                if item["id"] in global_ids:
                    raise CensusError("PUBLIC_PR_CENSUS_DUPLICATE")
                global_ids.add(item["id"])
                collected.append(item)
                if len(collected) > MAX_PULL_REQUESTS:
                    raise CensusError("PUBLIC_PR_CENSUS_BOUND")
        if self._org_count() != count or self._repositories(count) != repositories:
            raise CensusError("PUBLIC_PR_REPOSITORIES_MOVED")
        if collected:
            evidence.update(method="repository-census-search-disagrees", search_disagrees=True)
        else:
            # A second empty read across every enumerated repository catches
            # source movement observable during this bounded sequential pass.
            for _, repository in repositories:
                if self._repository_prs(repository):
                    raise CensusError("PUBLIC_PR_ZERO_MOVED")
            if self._org_count() != count or self._repositories(count) != repositories:
                raise CensusError("PUBLIC_PR_REPOSITORIES_MOVED")
            evidence.update(method="double-read-public-repository-census", zero_closure_authorized=True,
                            public_repositories_queried_twice=count)
        evidence.update(public_repositories_enumerated=count,
                        repository_membership_sha256=_digest(repositories),
                        requests_attempted=self.calls,
                        finished_at=datetime.now(timezone.utc).isoformat())
        return Observation(collected, evidence)
