#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify and selectively repair the two canonical SZL public origins.

The controller proves each origin from the bytes served by that origin. The
product front door is ``a-11-oy.com`` with canonical source
``szl-holdings/a11oy@main``; its deployment authority is external to this
controller, so product drift is observe-only until a bounded deploy action is
explicitly bound here. The independent proof origin ``a11oy.net`` is published
from ``a11oy-net`` and keeps its existing GitHub Pages rebuild path.

When explicitly authorized, this controller may request only a repair action
that is declared on the corresponding origin contract. It never edits source,
DNS, Cloudflare, secrets, pages, models, datasets, Hugging Face resources, or
application state.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

GITHUB_API = "https://api.github.com"
USER_AGENT = "SZL-Public-Estate-Convergence/3.1"
TOKEN_NAMES = ("SZL_GITHUB_TOKEN", "GH_CONTROL_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


class ConvergenceError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class OriginContract:
    name: str
    root: str
    spectral_asset: str
    controller_asset: str
    root_literals: tuple[str, ...]
    spectral_literals: tuple[str, ...]
    controller_literals: tuple[str, ...]
    advisory_health: str
    health_literals: tuple[str, ...]
    repair: str | None
    root_stylesheet: str | None = None


CONTRACTS = (
    OriginContract(
        name="a-11-oy.com",
        root="https://a-11-oy.com/",
        spectral_asset="https://a-11-oy.com/static/3d/holographic.html",
        controller_asset="https://a-11-oy.com/api/a11oy/v1/honest",
        root_literals=(
            "TASK-FIRST ENTRY POINTS",
            "Choose the view that matches your job.",
        ),
        spectral_literals=("A11oy Holographic Operations", "Evidence status"),
        controller_literals=('"organ":"a11oy"', '"locked_formula_count":8'),
        advisory_health="https://a-11-oy.com/healthz",
        health_literals=('"status":"ok"', '"organ":"a11oy"'),
        repair=None,
    ),
    OriginContract(
        name="a11oy.net",
        root="https://a11oy.net/",
        spectral_asset="https://a11oy.net/assets/szl-spectral-proof-v2.css",
        controller_asset="https://a11oy.net/scripts/szl-flow-proof.js",
        root_literals=(),
        spectral_literals=("SZL Spectral Proof v2", ".szl-proof-spectral-field"),
        controller_literals=("SZL Proof Flow Shell v2", "/assets/szl-spectral-proof-v2.css"),
        advisory_health="https://a11oy.net/health.json",
        health_literals=(),
        repair="A11OY_NET_PAGES_BUILD",
        root_stylesheet="/assets/szl-flow-proof.css",
    ),
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def token_from_environment() -> tuple[str | None, str | None]:
    for name in TOKEN_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return None, None


def request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int | None, bytes, Mapping[str, str], str | None]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json, application/json, text/html, text/css, */*",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read(2_000_000), dict(response.headers.items()), response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2_000_000), dict(exc.headers.items()), exc.geturl()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, b"", {}, None


class StylesheetLinks(HTMLParser):
    """Read actual links, never matching a URL inside prose, comments or scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str | None]] = []
        self.ambiguous = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "base":
            self.ambiguous = True
        if tag != "link":
            return
        attributes = dict(attrs)
        if attributes.get("data-szl-proof-flow-asset") == "style":
            if len(attributes) != len(attrs):
                self.ambiguous = True
            self.links.append(attributes)

    handle_startendtag = handle_starttag


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON value")


def _exact_response(url: str, content_type: str) -> bytes:
    status, raw, headers, final_url = request("GET", url)
    actual_type = (headers.get("Content-Type") or headers.get("content-type") or "")
    if (status != 200 or not raw or len(raw) >= 2_000_000 or final_url != url
            or actual_type.split(";", 1)[0].strip().lower() != content_type):
        raise ValueError("missing, redirected or invalid binding response")
    return raw


def _json_response(url: str) -> dict[str, Any]:
    value = json.loads(_exact_response(url, "application/json"),
                       object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("binding response must be a JSON object")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid content digest")
    return value


def pages_stylesheet_binding(root: str, raw: bytes, canonical: str) -> dict[str, Any]:
    """Bind the real stylesheet link to the exact deployed Pages manifest.

    This observes one deployed artifact. Its source witness does not prove that
    the revision is still protected main or establish product runtime readiness.
    No URLs supplied by HTML or JSON are fetched: all requests use fixed paths
    or the single admitted content-addressed CSS filename on this origin.
    """
    try:
        if root != "https://a11oy.net/" or canonical != "/assets/szl-flow-proof.css":
            raise ValueError("unsupported Pages stylesheet contract")
        manifest_url = root + "frontend-assets.json"
        manifest = _json_response(manifest_url)
        witness = _json_response(root + ".well-known/szl-source.json")
        revision = manifest.get("source_revision")
        if (manifest.get("schema") != "szl.frontend-asset-manifest/v1"
                or manifest.get("scope") != "STATIC_FRONTEND_ASSET_DELIVERY_ONLY"
                or manifest.get("canonical_assets_preserved") is not True
                or not isinstance(revision, str)
                or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or witness.get("schema_version") != "a11oy-static-source-witness/v1"
                or witness.get("surface") != root.rstrip("/")
                or witness.get("source_repository") != "https://github.com/szl-holdings/a11oy-net"
                or witness.get("source_revision") != revision
                or witness.get("artifact_kind") != "STATIC_GITHUB_PAGES"
                or witness.get("artifact_binding") != "EXACT_SOURCE_REVISION"):
            raise ValueError("manifest and canonical source witness disagree")
        document = manifest["documents"]["index.html"]
        if hashlib.sha256(raw).hexdigest() != _digest(document["served_sha256"]):
            raise ValueError("served root differs from the Pages manifest")
        asset = manifest["assets"][canonical.lstrip("/")]
        source_digest = _digest(asset["source_sha256"])
        served_digest = _digest(asset["served_sha256"])
        served_path = "assets/szl-flow-proof." + served_digest + ".css"
        if asset.get("source_path") != canonical.lstrip("/") or asset.get("served_path") != served_path:
            raise ValueError("stylesheet path is not the manifest's exact content address")
        parser = StylesheetLinks()
        parser.feed(raw.decode("utf-8"))
        parser.close()
        if parser.ambiguous or len(parser.links) != 1:
            raise ValueError("stylesheet link is missing or ambiguous")
        link = parser.links[0]
        if ((link.get("rel") or "").lower().split() != ["stylesheet"]
                or link.get("href") not in {"/" + served_path, root + served_path}
                or "disabled" in link or (link.get("media") or "all").lower() != "all"):
            raise ValueError("root does not load the manifest's exact stylesheet")
        source_bytes = _exact_response(root.rstrip("/") + canonical, "text/css")
        served_bytes = _exact_response(root + served_path, "text/css")
        if (hashlib.sha256(source_bytes).hexdigest() != source_digest
                or hashlib.sha256(served_bytes).hexdigest() != served_digest):
            raise ValueError("stylesheet bytes differ from the Pages manifest")
        return {"verified": True, "manifest_url": manifest_url,
                "source_revision": revision, "source_path": canonical,
                "served_path": "/" + served_path, "served_sha256": served_digest,
                "scope": "DEPLOYED_STATIC_ARTIFACT_ONLY"}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        return {"verified": False, "reason": str(exc) or type(exc).__name__}


def probe(url: str, literals: tuple[str, ...], *, pages_stylesheet: str | None = None) -> dict[str, Any]:
    status, raw, headers, final_url = request("GET", url)
    text = raw.decode("utf-8", "replace")
    found = {literal: literal in text for literal in literals}
    result = {
        "url": url,
        "final_url": final_url,
        "http_status": status,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "required_literals": found,
        "verified": status == 200 and bool(raw) and all(found.values()),
    }
    if pages_stylesheet is not None:
        content_type = (result["content_type"] or "").split(";", 1)[0].strip().lower()
        binding = (pages_stylesheet_binding(url, raw, pages_stylesheet)
                   if result["verified"] and final_url == url and content_type == "text/html"
                   else {"verified": False, "reason": "root response is unavailable or redirected"})
        result["pages_stylesheet"] = binding
        result["verified"] = bool(result["verified"] and binding["verified"])
    return result


def probe_origin(contract: OriginContract) -> dict[str, Any]:
    root = probe(contract.root, contract.root_literals, pages_stylesheet=contract.root_stylesheet)
    spectral = probe(contract.spectral_asset, contract.spectral_literals)
    controller = probe(contract.controller_asset, contract.controller_literals)
    health = probe(contract.advisory_health, contract.health_literals)
    return {
        "name": contract.name,
        "root": root,
        "spectral_asset": spectral,
        "controller_asset": controller,
        "advisory_health": health,
        "operational": (
            root["verified"]
            and spectral["verified"]
            and controller["verified"]
            and health["verified"]
        ),
    }


def github_action(
    method: str,
    path: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
) -> int:
    status, raw, _, _ = request(method, GITHUB_API + path, token=token, payload=payload)
    if status not in {200, 201, 202, 204}:
        detail = raw.decode("utf-8", "replace")[:500]
        raise ConvergenceError(f"GitHub control request {path} returned HTTP {status}: {detail}")
    return int(status)


def request_repair(contract: OriginContract, token: str) -> dict[str, Any]:
    if contract.repair == "A11OY_NET_PAGES_BUILD":
        status = github_action(
            "POST",
            "/repos/szl-holdings/a11oy-net/pages/builds",
            token,
        )
        return {"action": contract.repair, "http_status": status, "source_mutation": False}
    raise ConvergenceError(f"unsupported repair action: {contract.repair}")


def verify_all() -> list[dict[str, Any]]:
    return [probe_origin(contract) for contract in CONTRACTS]


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=360)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    if not 30 <= args.wait_seconds <= 900:
        raise SystemExit("--wait-seconds must be between 30 and 900")

    token, token_name = token_from_environment()
    before = verify_all()
    repairs: list[dict[str, Any]] = []
    if args.repair:
        for contract, observed in zip(CONTRACTS, before, strict=True):
            if observed["operational"]:
                continue
            if contract.repair is None:
                repairs.append(
                    {
                        "origin": contract.name,
                        "action": "OBSERVE_ONLY",
                        "state": "NO_BOUNDED_REPAIR",
                        "source_mutation": False,
                    }
                )
                continue
            if not token:
                repairs.append(
                    {
                        "origin": contract.name,
                        "action": contract.repair,
                        "state": "BLOCKED_NO_TOKEN",
                    }
                )
                continue
            try:
                receipt = request_repair(contract, token)
                repairs.append({"origin": contract.name, "state": "REQUESTED", **receipt})
            except ConvergenceError as exc:
                repairs.append(
                    {
                        "origin": contract.name,
                        "action": contract.repair,
                        "state": "REQUEST_FAILED",
                        "error": str(exc),
                    }
                )

    after = before
    if any(row.get("state") == "REQUESTED" for row in repairs):
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            time.sleep(15)
            after = verify_all()
            if all(row["operational"] for row in after):
                break

    complete = all(row["operational"] for row in after)
    report = {
        "schema": "szl.public-estate-convergence/v3.1",
        "generated_at": utc_now(),
        "repair_requested": args.repair,
        "token_available": bool(token),
        "token_source_name": token_name,
        "token_value_recorded": False,
        "source_mutation": False,
        "dns_mutation": False,
        "cloudflare_mutation": False,
        "before": before,
        "repairs": repairs,
        "after": after,
        "summary": {
            "origins_total": len(after),
            "origins_operational": sum(1 for row in after if row["operational"]),
            "origins_not_operational": sum(1 for row in after if not row["operational"]),
            "complete": complete,
        },
    }
    write_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if complete or args.allow_incomplete:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
