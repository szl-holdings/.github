#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Complete the v3 measured-state migration and remove legacy count assertions."""
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / ".github/scripts/estate_alignment_contract.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected one replacement anchor, found {count}: {old!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    module = runpy.run_path(
        str(ROOT / ".github/scripts/reconcile_estate_alignment_live_v3.py")
    )
    result = module["main"]()
    if result not in (None, 0):
        raise SystemExit(result)

    replace_once(
        CONTROLLER,
        '    for marker in ("16 portfolio Spaces", "44 models", "33 datasets"):',
        '    for marker in ("17 portfolio Spaces", "45 models", "34 datasets"): ',
    )
    text = CONTROLLER.read_text(encoding="utf-8")
    generated = '    for marker in ("17 portfolio Spaces", "45 models", "34 datasets"): \n'
    final = '    for marker in ("17 portfolio Spaces", "45 models", "34 datasets"):\n'
    if generated not in text:
        raise SystemExit("generated document-validator marker missing")
    CONTROLLER.write_text(text.replace(generated, final, 1), encoding="utf-8")

    text = CONTROLLER.read_text(encoding="utf-8")
    for stale in ("16 portfolio Spaces", "44 models", "33 datasets"):
        if stale in text:
            raise SystemExit(f"stale alignment marker remains: {stale}")
    for current in ("17 portfolio Spaces", "45 models", "34 datasets"):
        if current not in text:
            raise SystemExit(f"current alignment marker missing: {current}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
