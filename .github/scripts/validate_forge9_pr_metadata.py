#!/usr/bin/env python3
"""Validate the PR-body evidence required before FORGE-9 attestation."""

from __future__ import annotations

import re
import sys


REQUIREMENTS = (
    (
        "P1 missing Satisfies: AT-n or C-n",
        re.compile(
            r"^[ \t]*Satisfies:[ \t]*(?:AT-[0-9]+|C-[0-9]+)(?:[ \t]|$)",
            re.MULTILINE,
        ),
    ),
    (
        "P2 missing Rollback",
        re.compile(r"^[ \t]*Rollback:[ \t]*\S", re.MULTILINE),
    ),
    (
        "P3 missing Labels",
        re.compile(r"^[ \t]*Labels:[ \t]*\S", re.MULTILINE),
    ),
    (
        "missing Risk: A-D classification",
        re.compile(
            r"^[ \t]*Risk:[ \t]*[ABCD][ \t]*[-\N{EN DASH}\N{EM DASH}]",
            re.MULTILINE,
        ),
    ),
)


def validate(body: str) -> list[str]:
    """Return every missing admission field without interpreting its value."""
    return [message for message, pattern in REQUIREMENTS if not pattern.search(body)]


def main() -> int:
    failures = validate(sys.stdin.read())
    for message in failures:
        print(f"::error::{message}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
