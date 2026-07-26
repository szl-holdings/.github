#!/usr/bin/env python3
"""Run one repository-defined FORGE-9 gate without shell interpolation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: forge9_gate_runner.py gate/name", file=sys.stderr)
        return 2
    gate = sys.argv[1]
    config_path = Path(__file__).with_name("gates.json")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot load {config_path}: {exc}", file=sys.stderr)
        return 2

    commands = config.get(gate)
    if not isinstance(commands, list) or not commands:
        print(
            f"{gate} has no verified commands; refusing a placeholder pass",
            file=sys.stderr,
        )
        return 1

    for index, argv in enumerate(commands, start=1):
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(item, str) and item for item in argv)
        ):
            print(f"{gate} command {index} must be a non-empty argv array", file=sys.stderr)
            return 2
        print(f"{gate}: running command {index}: {argv!r}")
        completed = subprocess.run(argv, check=False)
        if completed.returncode:
            print(
                f"{gate}: command {index} failed with {completed.returncode}",
                file=sys.stderr,
            )
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
