#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify and selectively repair the two canonical SZL public origins.

The controller proves each origin's root document and its exact local visual
contract. The product front door is the GitHub Pages site published from
``szl-holdings.github.io`` and uses Responsive Apex v3. The independent proof
origin is published from ``a11oy-net`` and uses Spectral Proof v2.

When explicitly authorized, this controller may request only the corresponding
existing GitHub Pages rebuild endpoint. It never edits source, DNS, Cloudflare,
secrets, pages, models, datasets, Hugging Face resources, or application state.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

GITHUB_API = "https://api.github.com"
USER_AGENT = "SZL-Public-Estate-Convergence/3.0"
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
    repair: str


CONTRACTS = (
    OriginContract(
        name="a-11-oy.com",
        root="https://a-11-oy.com/",
        spectral_asset="https://a-11-oy.com/assets/szl-responsive-apex-v3.css",
        controller_asset="https://a-11-oy.com/assets/szl-responsive-apex-v3.js",
        root_literals=(
            "/assets/szl-responsive-apex-v3.css",
            "/assets/szl-responsive-apex-v3.js",
        ),
        spectral_literals=("SZL Apex Responsive Experience v3", "--apex-touch: 44px"),
        controller_literals=("SZL Apex Responsive Experience v3", "__SZL_APEX_RESPONSIVE_V3__"),
        advisory_health="https://a-11-oy.com/origin-status.json",
        repair="PRODUCT_PAGES_BUILD",
    ),
    OriginContract(
        name="a11oy.net",
        root="https://a11oy.net/",
        spectral_asset="https://a11oy.net/assets/szl-spectral-proof-v2.css",
        controller_asset="https://a11oy.net/scripts/szl-flow-proof.js",
        root_literals=("/assets/szl-flow-proof.css",),
        spectral_literals=("SZL Spectral Proof v2", ".szl-proof-spectral-field"),
        controller_literals=("SZL Proof Flow Shell v2", "/assets/szl-spectral-proof-v2.css"),
        advisory_health="https://a11oy.net/health.json",
        repair="A11OY_NET_PAGES_BUILD",
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


def probe(url: str, literals: tuple[str, ...]) -> dict[str, Any]:
    status, raw, headers, final_url = request("GET", url)
    text = raw.decode("utf-8", "replace")
    found = {literal: literal in text for literal in literals}
    return {
        "url": url,
        "final_url": final_url,
        "http_status": status,
        "bytes": len(raw),
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "required_literals": found,
        "verified": status == 200 and bool(raw) and all(found.values()),
    }


def probe_origin(contract: OriginContract) -> dict[str, Any]:
    root = probe(contract.root, contract.root_literals)
    spectral = probe(contract.spectral_asset, contract.spectral_literals)
    controller = probe(contract.controller_asset, contract.controller_literals)
    health_status, health_raw, _, health_final = request("GET", contract.advisory_health)
    return {
        "name": contract.name,
        "root": root,
        "spectral_asset": spectral,
        "controller_asset": controller,
        "advisory_health": {
            "url": contract.advisory_health,
            "final_url": health_final,
            "http_status": health_status,
            "bytes": len(health_raw),
        },
        "operational": root["verified"] and spectral["verified"] and controller["verified"],
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
    if contract.repair == "PRODUCT_PAGES_BUILD":
        status = github_action(
            "POST",
            "/repos/szl-holdings/szl-holdings.github.io/pages/builds",
            token,
        )
        return {"action": contract.repair, "http_status": status, "source_mutation": False}
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
        "schema": "szl.public-estate-convergence/v3",
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
