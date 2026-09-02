#!/usr/bin/env python3
"""Attach a self-contained green gate to every generated Space rollout PR."""
from __future__ import annotations

import json
import textwrap
from typing import Any


def target_contract(entrypoint: str | None) -> str:
    """Return a dependency-light target repository GitHub Actions contract."""
    template = r'''
name: SZL Holographic Space v2 Contract

on:
  pull_request:
  push:
    branches: [main, master]

permissions:
  contents: read

jobs:
  holographic-contract:
    runs-on: ubuntu-latest
    timeout-minutes: 12
    steps:
      - name: Checkout exact candidate
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
      - name: Verify local holographic assets and source binding
        shell: bash
        env:
          SZL_HOLO_ENTRYPOINT: __ENTRYPOINT__
        run: |
          set -euo pipefail
          mapfile -t css_files < <(find . -type f -name 'szl-space-hologram.css' -not -path './.git/*' | sort)
          if [ "${#css_files[@]}" -lt 1 ]; then echo 'missing holographic CSS'; exit 1; fi
          for file in "${css_files[@]}"; do
            grep -q 'prefers-reduced-motion' "$file"
            grep -q 'forced-colors' "$file"
            grep -q 'data-szl-space-motif' "$file"
            if grep -Eq '@import|https?://(cdn|unpkg|jsdelivr)' "$file"; then echo "external runtime asset in $file"; exit 1; fi
          done
          mapfile -t js_files < <(find . -type f -name 'szl-space-hologram.js' -not -path './.git/*' | sort)
          for file in "${js_files[@]}"; do
            node --check "$file"
            if grep -Eq 'fetch\(|XMLHttpRequest|sendBeacon|localStorage|sessionStorage|document\.cookie' "$file"; then echo "prohibited client behavior in $file"; exit 1; fi
          done
          mapfile -t py_files < <(find . -type f \( -name 'szl_hologram_assets.py' -o -name 'szl_hologram_streamlit.py' \) -not -path './.git/*' | sort)
          if [ -n "$SZL_HOLO_ENTRYPOINT" ] && [[ "$SZL_HOLO_ENTRYPOINT" == *.py ]]; then py_files+=("$SZL_HOLO_ENTRYPOINT"); fi
          if [ "${#py_files[@]}" -gt 0 ]; then python -m py_compile "${py_files[@]}"; fi
          if [ -n "$SZL_HOLO_ENTRYPOINT" ]; then
            test -f "$SZL_HOLO_ENTRYPOINT"
            grep -Eq 'szl-space-hologram|SZL Holographic Space Fabric v2|szl_hologram' "$SZL_HOLO_ENTRYPOINT"
          fi
          git diff --check
'''
    return textwrap.dedent(template).lstrip().replace(
        "__ENTRYPOINT__", json.dumps(entrypoint or "")
    )


def install(core: Any) -> None:
    """Wrap ``core.plan_repository`` exactly once and append the gate file."""
    if getattr(core, "_szl_target_contract_installed", False):
        return
    original = core.plan_repository

    def plan_with_target_contract(*args: Any, **kwargs: Any):
        plan = original(*args, **kwargs)
        if plan.status == "planned" and not any(
            change.path == ".github/workflows/szl-holographic-space-v2.yml"
            for change in plan.changes
        ):
            plan.changes.append(
                core.Change(
                    ".github/workflows/szl-holographic-space-v2.yml",
                    target_contract(plan.entrypoint),
                )
            )
        return plan

    core.plan_repository = plan_with_target_contract
    core._szl_target_contract_installed = True
