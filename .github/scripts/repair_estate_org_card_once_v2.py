#!/usr/bin/env python3
"""Run the organization-card repair and normalize generated Markdown bytes."""
from __future__ import annotations

import runpy
from pathlib import Path


try:
    runpy.run_path(
        ".github/scripts/repair_estate_org_card_once.py",
        run_name="__main__",
    )
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise

workcell = Path("audit/ESTATE_ALIGNMENT_CURRENT_MAIN_SUCCESSOR_2026-09-05.md")
workcell.write_text(
    workcell.read_text(encoding="utf-8").rstrip() + "\n",
    encoding="utf-8",
)
