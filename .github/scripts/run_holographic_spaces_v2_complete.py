#!/usr/bin/env python3
"""Run Holographic Space Fabric v2 with hardened adapters and target gates."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load("szl_holographic_space_runner", ROOT / "run_holographic_spaces_v2.py")
targets = load("szl_holographic_target_contract", ROOT / "holographic_target_contract.py")
targets.install(runner.core)


if __name__ == "__main__":
    try:
        raise SystemExit(runner.core.main())
    except runner.core.RolloutError as exc:
        print(
            json.dumps({"status": "blocked", "error": exc.as_dict()}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(2)
