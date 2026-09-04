#!/usr/bin/env python3
"""Remove only the exact unused imports identified on PR #641."""

from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path(".github/scripts/publish_vertical_frontier.py")
REPLACEMENTS = (
    ("from dataclasses import dataclass\n", ""),
    (
        "from typing import Any, Final, Iterable, Mapping, Sequence\n",
        "from typing import Any, Final, Iterable, Mapping\n",
    ),
    ("from urllib.error import HTTPError, URLError\n", ""),
)


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        count = source.count(old)
        if count != 1:
            raise SystemExit(
                f"refusing drifted import cleanup: expected one {old.strip()!r}, found {count}"
            )
        source = source.replace(old, new, 1)

    for symbol in ("dataclass", "Sequence", "HTTPError", "URLError"):
        if symbol in source:
            raise SystemExit(f"unused symbol remains after cleanup: {symbol}")

    ast.parse(source, filename=str(TARGET))
    TARGET.write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
