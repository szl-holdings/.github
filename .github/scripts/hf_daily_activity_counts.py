#!/usr/bin/env python3
"""Count SZLHOLDINGS Hub repos for the daily activity receipt.

Dataset, model, and Space listings follow every ``Link: rel="next"`` page.
A single ``limit`` is not the full inventory: the Hub defaults to a short
page and puts the rest behind a cursor. The next URL is accepted only when
it stays on ``https://huggingface.co/api/<kind>`` and still filters
``author=SZLHOLDINGS`` (the Hub org id; ``szl-holdings`` is the GitHub org
and returns no datasets). The bearer token is never sent to another host
or to an unfiltered listing.

The daily workflow passes ``HF_TOKEN`` on every page. Authenticated pages
include private repos, and those rows are counted with the public ones.
There is no public-only filter. Without the token the count step does not
run.

Collections are a different endpoint. ``namespace=`` does not filter to the
org, and its next link drops the query, so this script keeps the historical
single request instead of paging the public trending feed.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ORG = "SZLHOLDINGS"
API_HOST = "huggingface.co"
PAGE_LIMIT = 100
MAX_PAGES = 40
MAX_PAGE_BYTES = 5_000_000
MAX_LINK_CHARS = 8192
AUTHOR_KINDS = ("datasets", "models", "spaces")

_LINK_PART = re.compile(r'\s*<([^<>]+)>\s*;\s*rel\s*=\s*"([^"\r\n]+)"\s*')


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"HF API redirect {code} refused")


def parse_next_link(header: str) -> str | None:
    """Return the single ``rel=next`` URL, or None when the page is the last."""
    if not isinstance(header, str):
        raise RuntimeError("HF pagination link rejected")
    if len(header) > MAX_LINK_CHARS:
        raise RuntimeError("HF pagination link exceeded bound")
    if header.strip() == "":
        return None
    found: list[str] = []
    for part in header.split(","):
        match = _LINK_PART.fullmatch(part)
        if match is None:
            raise RuntimeError("HF pagination link malformed")
        rels = match.group(2).lower().split()
        if "next" not in rels:
            continue
        found.append(match.group(1))
    if len(found) > 1:
        raise RuntimeError("HF pagination returned multiple next links")
    return found[0] if found else None


def assert_author_listing(url: str, kind: str) -> None:
    """Reject any listing URL that is not an author-filtered Hub page."""
    if kind not in AUTHOR_KINDS:
        raise RuntimeError("HF listing kind rejected")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc != API_HOST:
        raise RuntimeError("HF listing host rejected")
    if parts.username or parts.password or parts.fragment:
        raise RuntimeError("HF listing URL rejected")
    if parts.path != f"/api/{kind}":
        raise RuntimeError("HF listing path rejected")
    query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    if query.get("author") != [ORG]:
        raise RuntimeError("HF listing author filter rejected")


def list_author_repos(
    kind: str,
    get,
    token: str | None,
    *,
    page_limit: int = PAGE_LIMIT,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """Return every repo summary for ``kind`` under ``ORG``.

    Private rows are kept. The caller decides whether ``token`` is sent;
    the workflow always sends ``HF_TOKEN``.
    """
    if isinstance(page_limit, bool) or not isinstance(page_limit, int):
        raise RuntimeError("HF page limit rejected")
    if not 1 <= page_limit <= PAGE_LIMIT:
        raise RuntimeError("HF page limit rejected")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise RuntimeError("HF page bound rejected")
    url = f"https://{API_HOST}/api/{kind}?author={ORG}&limit={page_limit}"
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    items: list[dict] = []
    for _ in range(max_pages):
        assert_author_listing(url, kind)
        if url in seen_urls:
            raise RuntimeError("HF pagination cycle")
        seen_urls.add(url)
        status, body, link = get(url, token)
        if status != 200:
            raise RuntimeError(f"HF API HTTP {status}")
        if not isinstance(body, (bytes, bytearray)) or len(body) > MAX_PAGE_BYTES:
            raise RuntimeError("HF API page exceeded byte bound")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError("HF API page was not JSON") from None
        if not isinstance(payload, list):
            raise RuntimeError("HF API page was not a list")
        for item in payload:
            if not isinstance(item, dict):
                raise RuntimeError("HF API record was not an object")
            repo_id = item.get("id")
            if not isinstance(repo_id, str) or not repo_id.startswith(f"{ORG}/"):
                raise RuntimeError("HF API record id rejected")
            if repo_id in seen_ids:
                raise RuntimeError("HF API duplicate record")
            seen_ids.add(repo_id)
            items.append(item)
        nxt = parse_next_link(link if isinstance(link, str) else "")
        if nxt is None:
            return items
        url = nxt
    raise RuntimeError("HF pagination page bound exceeded")


def count_collections(get, token: str | None) -> int:
    """Return the historical single-page collections response length.

    This request is intentionally not paged. ``namespace`` is not the owner
    filter, and following ``rel=next`` walks unrelated Hub collections.
    """
    url = f"https://{API_HOST}/api/collections?namespace={ORG}&limit=20"
    status, body, _link = get(url, token)
    if status != 200:
        raise RuntimeError(f"HF API HTTP {status}")
    if not isinstance(body, (bytes, bytearray)) or len(body) > MAX_PAGE_BYTES:
        raise RuntimeError("HF API page exceeded byte bound")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError("HF API page was not JSON") from None
    if not isinstance(payload, list):
        raise RuntimeError("HF collections response was not a list")
    return len(payload)


def collect_counts(get, token: str | None) -> dict[str, int | str]:
    datasets = list_author_repos("datasets", get, token)
    models = list_author_repos("models", get, token)
    spaces = list_author_repos("spaces", get, token)
    return {
        "spaces": len(spaces),
        "datasets": len(datasets),
        "models": len(models),
        "collections": count_collections(get, token),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def http_get(url: str, token: str | None) -> tuple[int, bytes, str]:
    """GET one Hub URL. Redirects are refused so the token cannot leave the host."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "szl-hf-daily-activity",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_RefuseRedirect)
    try:
        with opener.open(request, timeout=45) as response:
            status = getattr(response, "status", 200)
            link = response.headers.get("Link") or ""
            body = response.read(MAX_PAGE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HF API HTTP {exc.code}") from None
    if len(body) > MAX_PAGE_BYTES:
        raise RuntimeError("HF API page exceeded byte bound")
    return status, body, link


def main() -> int:
    token = os.environ.get("HF_TOKEN") or None
    counts = collect_counts(http_get, token)
    print(json.dumps(counts, indent=2))
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            for key in ("spaces", "datasets", "models", "collections", "date"):
                handle.write(f"{key}={counts[key]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
