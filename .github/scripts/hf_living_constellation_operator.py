#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit and repair the public SZLHOLDINGS Hugging Face Space fleet.

The operator is deliberately narrow:

* enumerate the current public organization Space inventory from the Hub API;
* restart only Spaces already allocated to the organization and only when their
  observed runtime stage is restart-eligible;
* never change hardware, storage, visibility, secrets, source, card content,
  model weights, datasets, or repository allocation;
* read back the runtime stage and probe the public application origin;
* emit an exact, secret-free JSON receipt and fail closed when any public Space
  is not demonstrably reachable.

A restart is an operational action, not proof that source and runtime are equal.
Source/runtime identity remains governed by each canonical publisher.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

API = "https://huggingface.co/api"
ORG = "SZLHOLDINGS"
USER_AGENT = "SZL-Living-Constellation-Operator/2.0"

HEALTHY_STAGES = frozenset({"RUNNING"})
TRANSITIONAL_STAGES = frozenset(
    {
        "BUILDING",
        "RUNNING_BUILDING",
        "STARTING",
        "RESTARTING",
        "APP_STARTING",
        "CREATING",
    }
)
RESTART_ELIGIBLE_STAGES = frozenset(
    {
        "PAUSED",
        "SLEEPING",
        "STOPPED",
        "ERROR",
        "RUNTIME_ERROR",
        "BUILD_ERROR",
        "CONFIG_ERROR",
        "NO_APP_FILE",
        "UNKNOWN",
        "UNAVAILABLE",
    }
)
TOKEN_NAMES = (
    "HF_ORG_TOKEN",
    "HF_ORG_TOKEN1",
    "HF_TOKEN",
    "HF_WRITE_TOKEN",
    "HUGGINGFACE_TOKEN",
)
SECRET_PATTERN = re.compile(r"hf_[A-Za-z0-9]{12,}")


class OperatorError(RuntimeError):
    """Fail-closed operator error."""


@dataclasses.dataclass(frozen=True)
class Space:
    repo_id: str
    slug: str
    sdk: str
    stage: str
    private: bool
    host_candidates: tuple[str, ...]


@dataclasses.dataclass
class SpaceResult:
    repo_id: str
    slug: str
    sdk: str
    initial_stage: str
    final_stage: str
    restart_attempted: bool = False
    restart_http_status: int | None = None
    runtime_url: str | None = None
    runtime_http_status: int | None = None
    operational: bool = False
    state: str = "UNVERIFIED"
    blockers: list[str] = dataclasses.field(default_factory=list)
    polls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_stage(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    rendered = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return rendered or "UNAVAILABLE"


def token_from_environment() -> tuple[str | None, str | None]:
    for name in TOKEN_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return None, None


def redact(value: Any) -> Any:
    """Recursively remove token-shaped strings before evidence is persisted."""
    if isinstance(value, str):
        return SECRET_PATTERN.sub("[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    return value


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes, Mapping[str, str]]:
    body = None
    headers = {
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OperatorError(f"request failed for {url}: {exc}") from exc


def _json(method: str, url: str, *, token: str | None = None) -> tuple[int, Any]:
    status, raw, _ = _request(method, url, token=token)
    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorError(f"non-JSON response from {url} (HTTP {status})") from exc


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "spaces", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise OperatorError("Hub Space inventory response has an unsupported shape")


def _nested(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def host_candidates(repo_id: str, sdk: str, raw: Mapping[str, Any]) -> tuple[str, ...]:
    owner, slug = repo_id.split("/", 1)
    normalized = re.sub(r"[^a-z0-9-]+", "-", f"{owner}-{slug}".lower()).strip("-")
    candidates: list[str] = []
    for key in ("host", "url", "runtimeUrl", "runtime_url"):
        value = raw.get(key)
        if isinstance(value, str) and value.startswith("https://"):
            candidates.append(value.rstrip("/") + "/")
    runtime = raw.get("runtime")
    if isinstance(runtime, Mapping):
        for key in ("host", "url", "runtimeUrl", "runtime_url"):
            value = runtime.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                candidates.append(value.rstrip("/") + "/")
    if sdk.lower() == "static":
        candidates.append(f"https://{normalized}.static.hf.space/")
    candidates.append(f"https://{normalized}.hf.space/")
    return tuple(dict.fromkeys(candidates))


def parse_space(raw: Mapping[str, Any]) -> Space | None:
    repo_id = raw.get("id") or raw.get("repo_id") or raw.get("name")
    if not isinstance(repo_id, str) or "/" not in repo_id:
        return None
    owner, slug = repo_id.split("/", 1)
    if owner.casefold() != ORG.casefold():
        return None
    private = bool(raw.get("private"))
    card = raw.get("cardData") if isinstance(raw.get("cardData"), Mapping) else {}
    sdk = str(raw.get("sdk") or card.get("sdk") or "unknown").strip().lower()
    stage = normalize_stage(
        _nested(raw, "runtime", "stage")
        or raw.get("runtimeStage")
        or raw.get("stage")
    )
    return Space(
        repo_id=repo_id,
        slug=slug,
        sdk=sdk,
        stage=stage,
        private=private,
        host_candidates=host_candidates(repo_id, sdk, raw),
    )


def inventory(token: str | None) -> list[Space]:
    query = urllib.parse.urlencode(
        {"author": ORG, "limit": 100, "full": "true", "sort": "lastModified", "direction": -1}
    )
    status, payload = _json("GET", f"{API}/spaces?{query}", token=token)
    if status != 200:
        raise OperatorError(f"Hub Space inventory returned HTTP {status}")
    spaces = [space for raw in _items(payload) if (space := parse_space(raw)) is not None]
    public_spaces = sorted((space for space in spaces if not space.private), key=lambda item: item.repo_id.casefold())
    if not public_spaces:
        raise OperatorError("Hub returned no public SZLHOLDINGS Spaces")
    if len({space.repo_id.casefold() for space in public_spaces}) != len(public_spaces):
        raise OperatorError("Hub Space inventory contains duplicate canonical identities")
    return public_spaces


def fetch_space(repo_id: str, token: str | None) -> Space:
    encoded = urllib.parse.quote(repo_id, safe="/")
    status, payload = _json("GET", f"{API}/spaces/{encoded}", token=token)
    if status != 200 or not isinstance(payload, Mapping):
        raise OperatorError(f"{repo_id} detail returned HTTP {status}")
    space = parse_space(payload)
    if space is None:
        raise OperatorError(f"{repo_id} detail did not preserve canonical identity")
    return space


def restart_space(repo_id: str, token: str) -> int:
    encoded = urllib.parse.quote(repo_id, safe="/")
    status, raw, _ = _request("POST", f"{API}/spaces/{encoded}/restart", token=token)
    if status not in {200, 201, 202, 204, 409}:
        detail = raw.decode("utf-8", "replace")[:400]
        raise OperatorError(f"{repo_id} restart returned HTTP {status}: {redact(detail)}")
    return status


def probe_runtime(candidates: Iterable[str]) -> tuple[str | None, int | None, list[str]]:
    blockers: list[str] = []
    for url in candidates:
        try:
            status, raw, headers = _request("GET", url, timeout=25.0)
        except OperatorError as exc:
            blockers.append(str(exc))
            continue
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
        if status == 200 and raw and ("text/html" in content_type or b"<html" in raw[:8192].lower()):
            return url, status, blockers
        blockers.append(f"{url} returned HTTP {status} with {len(raw)} bytes")
    return None, None, blockers


def wait_for_terminal(
    repo_id: str,
    token: str | None,
    *,
    deadline: float,
    initial_hosts: tuple[str, ...],
) -> tuple[str, tuple[str, ...], int]:
    stage = "UNAVAILABLE"
    hosts = initial_hosts
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        current = fetch_space(repo_id, token)
        stage = current.stage
        hosts = tuple(dict.fromkeys((*current.host_candidates, *initial_hosts)))
        if stage in HEALTHY_STAGES:
            return stage, hosts, polls
        if stage not in TRANSITIONAL_STAGES and polls >= 2:
            return stage, hosts, polls
        time.sleep(min(20.0, 3.0 + polls * 1.5))
    return stage, hosts, polls


def operate_one(
    space: Space,
    *,
    token: str | None,
    repair: bool,
    wait_seconds: int,
) -> SpaceResult:
    result = SpaceResult(
        repo_id=space.repo_id,
        slug=space.slug,
        sdk=space.sdk,
        initial_stage=space.stage,
        final_stage=space.stage,
    )
    stage = space.stage
    hosts = space.host_candidates

    if repair and stage in RESTART_ELIGIBLE_STAGES:
        if not token:
            result.blockers.append("repair requested but no supported Hugging Face token is configured")
        else:
            result.restart_attempted = True
            try:
                result.restart_http_status = restart_space(space.repo_id, token)
            except OperatorError as exc:
                result.blockers.append(str(exc))

    if stage not in HEALTHY_STAGES or result.restart_attempted:
        try:
            stage, hosts, polls = wait_for_terminal(
                space.repo_id,
                token,
                deadline=time.monotonic() + wait_seconds,
                initial_hosts=hosts,
            )
            result.final_stage = stage
            result.polls = polls
        except OperatorError as exc:
            result.blockers.append(str(exc))

    if result.final_stage in HEALTHY_STAGES:
        url, status, blockers = probe_runtime(hosts)
        result.runtime_url = url
        result.runtime_http_status = status
        result.blockers.extend(blockers[-2:] if url else blockers)
        result.operational = bool(url and status == 200)
    else:
        result.blockers.append(f"runtime stage is {result.final_stage}")

    if result.operational:
        result.state = "OPERATIONAL"
    elif result.final_stage in TRANSITIONAL_STAGES:
        result.state = "TRANSITIONAL_TIMEOUT"
    elif result.restart_attempted:
        result.state = "REPAIR_FAILED"
    else:
        result.state = "NOT_OPERATIONAL"
    result.blockers = [str(redact(item)) for item in dict.fromkeys(result.blockers)]
    return result


def summarize(results: list[SpaceResult]) -> dict[str, Any]:
    states: dict[str, int] = {}
    stages: dict[str, int] = {}
    for result in results:
        states[result.state] = states.get(result.state, 0) + 1
        stages[result.final_stage] = stages.get(result.final_stage, 0) + 1
    operational = sum(1 for result in results if result.operational)
    return {
        "total_public_spaces": len(results),
        "operational": operational,
        "not_operational": len(results) - operational,
        "restart_attempted": sum(1 for result in results if result.restart_attempted),
        "states": dict(sorted(states.items())),
        "final_stages": dict(sorted(stages.items())),
        "complete": operational == len(results),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = redact(dict(report))
    path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=720)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    if not 30 <= args.wait_seconds <= 1800:
        raise SystemExit("--wait-seconds must be between 30 and 1800")
    if not 1 <= args.workers <= 12:
        raise SystemExit("--workers must be between 1 and 12")

    token, token_name = token_from_environment()
    started = utc_now()
    try:
        spaces = inventory(token)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    operate_one,
                    space,
                    token=token,
                    repair=args.repair,
                    wait_seconds=args.wait_seconds,
                ): space.repo_id
                for space in spaces
            }
            results: list[SpaceResult] = []
            for future in concurrent.futures.as_completed(futures):
                repo_id = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # fail closed while retaining the rest of the fleet receipt
                    results.append(
                        SpaceResult(
                            repo_id=repo_id,
                            slug=repo_id.split("/", 1)[-1],
                            sdk="unknown",
                            initial_stage="UNAVAILABLE",
                            final_stage="UNAVAILABLE",
                            state="OPERATOR_ERROR",
                            blockers=[str(redact(exc))],
                        )
                    )
        results.sort(key=lambda item: item.repo_id.casefold())
        report = {
            "schema": "szl.hf-living-constellation-operator/v2",
            "organization": ORG,
            "started_at": started,
            "finished_at": utc_now(),
            "repair_requested": args.repair,
            "token_available": bool(token),
            "token_source_name": token_name,
            "token_value_recorded": False,
            "hardware_mutation": False,
            "source_mutation": False,
            "summary": summarize(results),
            "spaces": [result.as_dict() for result in results],
        }
    except Exception as exc:
        report = {
            "schema": "szl.hf-living-constellation-operator/v2",
            "organization": ORG,
            "started_at": started,
            "finished_at": utc_now(),
            "repair_requested": args.repair,
            "token_available": bool(token),
            "token_source_name": token_name,
            "token_value_recorded": False,
            "hardware_mutation": False,
            "source_mutation": False,
            "summary": {"complete": False, "operator_error": True},
            "error": str(redact(exc)),
            "spaces": [],
        }
        write_report(args.report, report)
        print(json.dumps(redact(report), indent=2, sort_keys=True))
        return 2

    write_report(args.report, report)
    print(json.dumps(redact(report), indent=2, sort_keys=True))
    if report["summary"]["complete"] or args.allow_incomplete:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
