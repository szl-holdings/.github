#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Staging-only canary versus control comparison.

Caps and stop thresholds are fixed before any request and are not raised
while the run is in progress. The tool issues capped GETs only. It refuses
every host when no staging flag is set, and it refuses production denylist
hosts unless that exact target is explicitly marked staging.

Production denylist:

- a-11-oy.com (and www)
- a11oy.net (and www)
- inference.a-11-oy.com
- any other host under those zones
- *.hf.space, including production Spaces

An apex above is never accepted, even if a caller marks it staging.
A denylist host is accepted only when ``staging`` is true, ``target_class``
is ``staging``, and a DNS label is ``staging``, ``stage``, ``preview``, or
ends in ``-staging``, ``-stage``, or ``-preview``.
"""

from __future__ import annotations

import argparse
import math
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from urllib.parse import urlsplit

ABSOLUTE_MAX_RPS = 5.0
ABSOLUTE_MAX_DURATION_S = 30.0
ABSOLUTE_MAX_REQUESTS = 40

_APEX = frozenset(
    {
        "a-11-oy.com",
        "www.a-11-oy.com",
        "a11oy.net",
        "www.a11oy.net",
        "inference.a-11-oy.com",
    }
)
_STAGING_LABELS = frozenset({"staging", "stage", "preview"})
_STAGING_SUFFIXES = ("-staging", "-stage", "-preview")


class Refusal(Exception):
    """The run was refused before traffic, or a cap was illegal."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Sample:
    ok: bool
    latency_ms: float


@dataclass(frozen=True)
class Caps:
    """Hard caps. Construct them before the run; instances are frozen."""

    max_rps: float
    max_duration_s: float
    max_requests: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_requests, int)
            or isinstance(self.max_requests, bool)
            or self.max_rps <= 0
            or self.max_duration_s <= 0
            or self.max_requests <= 0
        ):
            raise Refusal("caps must be positive and set before the run")
        if self.max_rps > ABSOLUTE_MAX_RPS:
            raise Refusal(f"max_rps exceeds absolute ceiling {ABSOLUTE_MAX_RPS}")
        if self.max_duration_s > ABSOLUTE_MAX_DURATION_S:
            raise Refusal(
                f"max_duration_s exceeds absolute ceiling {ABSOLUTE_MAX_DURATION_S}"
            )
        if self.max_requests > ABSOLUTE_MAX_REQUESTS:
            raise Refusal(
                f"max_requests exceeds absolute ceiling {ABSOLUTE_MAX_REQUESTS}"
            )


@dataclass(frozen=True)
class StopThresholds:
    """Stop the run when an observed side crosses either threshold."""

    max_error_rate: float
    max_p95_ms: float

    def __post_init__(self) -> None:
        if not 0 <= self.max_error_rate <= 1:
            raise Refusal("stop error rate must be between 0 and 1")
        if self.max_p95_ms <= 0:
            raise Refusal("stop p95 must be positive")


def hostname_of(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise Refusal("missing url")
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"}:
        raise Refusal("url scheme must be http or https")
    if parts.username is not None or parts.password is not None:
        raise Refusal("url must not carry userinfo")
    if parts.hostname is None:
        raise Refusal("url has no host")
    host = parts.hostname.lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise Refusal("url host is not a valid domain") from exc
    return host


def _staging_named(host: str) -> bool:
    for label in host.split("."):
        if label in _STAGING_LABELS:
            return True
        if any(
            label.endswith(suffix) and len(label) > len(suffix)
            for suffix in _STAGING_SUFFIXES
        ):
            return True
    return False


def on_production_denylist(host: str) -> bool:
    if host in _APEX:
        return True
    if host == "a-11-oy.com" or host.endswith(".a-11-oy.com"):
        return True
    if host == "a11oy.net" or host.endswith(".a11oy.net"):
        return True
    if host == "hf.space" or host.endswith(".hf.space"):
        return True
    return False


def allow_target(
    url: str, *, staging: bool, target_class: Optional[str] = None
) -> str:
    """Return the hostname, or refuse before any request is made."""

    host = hostname_of(url)
    if staging is not True:
        raise Refusal("refusing: no staging flag is set")
    if not on_production_denylist(host):
        return host
    if host in _APEX:
        raise Refusal(f"refusing production host {host}")
    explicit = target_class == "staging" and _staging_named(host)
    if not explicit:
        raise Refusal(f"refusing production denylist host {host}")
    return host


def percentile_95(latencies: Sequence[float]) -> float:
    if not latencies:
        raise Refusal("p95 requires at least one sample")
    ordered = sorted(latencies)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return float(ordered[rank])


def error_rate(samples: Sequence[Sample]) -> float:
    if not samples:
        raise Refusal("error rate requires at least one sample")
    return sum(1 for sample in samples if not sample.ok) / len(samples)


def _summarize(samples: Sequence[Sample]) -> dict:
    if not samples:
        return {"n": 0, "error_rate": None, "p95_ms": None}
    return {
        "n": len(samples),
        "error_rate": error_rate(samples),
        "p95_ms": percentile_95([sample.latency_ms for sample in samples]),
    }


def _tripped(samples: Sequence[Sample], stops: StopThresholds) -> Optional[str]:
    if not samples:
        return None
    if error_rate(samples) > stops.max_error_rate:
        return "error_rate"
    if percentile_95([sample.latency_ms for sample in samples]) > stops.max_p95_ms:
        return "p95"
    return None


def run_comparison(
    *,
    canary_url: str,
    control_url: str,
    staging: bool,
    target_class: Optional[str],
    caps: Caps,
    stops: StopThresholds,
    samples_per_side: int,
    transport: Callable[[str], Sample],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Compare canary and control. Refusal happens before ``transport``."""

    allow_target(canary_url, staging=staging, target_class=target_class)
    allow_target(control_url, staging=staging, target_class=target_class)
    if isinstance(samples_per_side, bool) or not isinstance(samples_per_side, int):
        raise Refusal("samples_per_side must be a positive integer")
    if samples_per_side <= 0:
        raise Refusal("samples_per_side must be positive")
    planned = samples_per_side * 2
    if planned > caps.max_requests:
        raise Refusal("planned requests exceed max_requests")

    canary: list[Sample] = []
    control: list[Sample] = []
    issued = 0
    started = clock()
    interval = 1.0 / caps.max_rps
    stopped: Optional[str] = None
    stop_side: Optional[str] = None

    def _room_for_another() -> bool:
        if issued >= caps.max_requests:
            return False
        if clock() - started >= caps.max_duration_s:
            return False
        return True

    def _pace() -> None:
        earliest = started + issued * interval
        delay = earliest - clock()
        if delay > 0:
            sleep(delay)

    for _ in range(samples_per_side):
        if not _room_for_another():
            stopped = "max_requests" if issued >= caps.max_requests else "max_duration"
            break
        _pace()
        if clock() - started >= caps.max_duration_s:
            stopped = "max_duration"
            break
        canary.append(transport(canary_url))
        issued += 1
        reason = _tripped(canary, stops)
        if reason:
            stopped = reason
            stop_side = "canary"
            break
        if not _room_for_another():
            stopped = "max_requests" if issued >= caps.max_requests else "max_duration"
            break
        _pace()
        if clock() - started >= caps.max_duration_s:
            stopped = "max_duration"
            break
        control.append(transport(control_url))
        issued += 1
        reason = _tripped(control, stops)
        if reason:
            stopped = reason
            stop_side = "control"
            break

    canary_summary = _summarize(canary)
    control_summary = _summarize(control)
    delta_error = None
    delta_p95 = None
    if canary_summary["error_rate"] is not None and control_summary["error_rate"] is not None:
        delta_error = canary_summary["error_rate"] - control_summary["error_rate"]
    if canary_summary["p95_ms"] is not None and control_summary["p95_ms"] is not None:
        delta_p95 = canary_summary["p95_ms"] - control_summary["p95_ms"]
    return {
        "canary": canary_summary,
        "control": control_summary,
        "delta_error_rate": delta_error,
        "delta_p95_ms": delta_p95,
        "issued": issued,
        "stopped": stopped is not None,
        "stop_reason": stopped,
        "stop_side": stop_side,
        "caps": {
            "max_rps": caps.max_rps,
            "max_duration_s": caps.max_duration_s,
            "max_requests": caps.max_requests,
        },
        "stops": {
            "max_error_rate": stops.max_error_rate,
            "max_p95_ms": stops.max_p95_ms,
        },
    }


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):  # noqa: ANN001
        return response

    https_response = http_response


def urllib_transport(url: str, *, timeout: float) -> Sample:
    """One GET. Redirects are not followed. Bodies are discarded."""

    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(
        url, method="GET", headers={"Accept": "application/json", "User-Agent": "szl-release-harness"}
    )
    started = time.perf_counter()
    ok = False
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(65536)
            ok = 200 <= int(response.status) < 300
    except Exception:
        ok = False
    latency_ms = (time.perf_counter() - started) * 1000.0
    return Sample(ok=ok, latency_ms=latency_ms)


def _print_report(report: dict) -> None:
    canary = report["canary"]
    control = report["control"]
    print(
        "canary n={n} error_rate={error_rate} p95_ms={p95_ms}".format(**canary)
    )
    print(
        "control n={n} error_rate={error_rate} p95_ms={p95_ms}".format(**control)
    )
    print(
        "delta_error_rate={delta_error_rate} delta_p95_ms={delta_p95_ms} "
        "issued={issued} stopped={stopped} stop_reason={stop_reason}".format(
            **report
        )
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", action="store_true")
    parser.add_argument("--target-class", choices=("staging",))
    parser.add_argument("--canary", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-rps", type=float)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--stop-error-rate", type=float)
    parser.add_argument("--stop-p95-ms", type=float)
    parser.add_argument("--samples", type=int)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check_only and args.execute:
        print("refusing: choose only one of --check-only and --execute", flush=True)
        return 2
    if not args.check_only and not args.execute:
        print("refusing: pass --check-only or --execute", flush=True)
        return 2
    try:
        canary_host = allow_target(
            args.canary, staging=args.staging, target_class=args.target_class
        )
        control_host = allow_target(
            args.control, staging=args.staging, target_class=args.target_class
        )
    except Refusal as exc:
        print(f"refusing: {exc.reason}", flush=True)
        return 2
    if args.check_only:
        print(f"allowed canary={canary_host} control={control_host}")
        return 0
    if None in {
        args.max_rps,
        args.max_duration,
        args.max_requests,
        args.stop_error_rate,
        args.stop_p95_ms,
        args.samples,
    }:
        print("refusing: caps, stop thresholds, and --samples must be set", flush=True)
        return 2
    try:
        caps = Caps(args.max_rps, args.max_duration, args.max_requests)
        stops = StopThresholds(args.stop_error_rate, args.stop_p95_ms)
        report = run_comparison(
            canary_url=args.canary,
            control_url=args.control,
            staging=True,
            target_class=args.target_class,
            caps=caps,
            stops=stops,
            samples_per_side=args.samples,
            transport=lambda url: urllib_transport(url, timeout=3.0),
        )
    except Refusal as exc:
        print(f"refusing: {exc.reason}", flush=True)
        return 2
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
