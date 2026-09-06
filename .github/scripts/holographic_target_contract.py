#!/usr/bin/env python3
"""Attach a self-contained Public Experience v3 gate to generated Space PRs."""
from __future__ import annotations

import json
import textwrap
from typing import Any, Sequence


def target_contract(
    entrypoint: str | None,
    asset_paths: Sequence[str] = (),
) -> str:
    """Return a dependency-light target repository GitHub Actions contract.

    The rollout planner already knows the exact reviewed asset host it is
    changing. Carry those repository-relative paths into the target gate rather
    than rediscovering one hard-coded filename family inside the candidate
    checkout. This preserves product-owned hosts such as ``szl-holo-v2.*``
    without weakening the responsive, local-asset, or source-binding checks.
    """

    declared_assets = sorted(
        {
            str(path)
            for path in asset_paths
            if str(path).lower().endswith((".css", ".js"))
        }
    )
    template = r'''
name: SZL Public Experience v3 Contract

on:
  pull_request:
  push:
    branches: [main, master]

permissions:
  contents: read

jobs:
  public-experience-contract:
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
      - name: Verify local responsive assets and source binding
        shell: bash
        env:
          SZL_HOLO_ENTRYPOINT: __ENTRYPOINT__
        run: |
          set -euo pipefail
          python - <<'PY'
          from pathlib import Path
          import os
          import py_compile
          import subprocess

          raw_asset_paths = __ASSET_PATHS__
          asset_paths = []
          for raw in raw_asset_paths:
              path = Path(raw)
              if path.is_absolute() or '\\' in raw or '..' in path.parts:
                  raise SystemExit(f'unsafe declared holographic asset path: {raw}')
              asset_paths.append(path)
          missing_assets = [str(path) for path in asset_paths if not path.is_file()]
          if missing_assets:
              raise SystemExit(f'missing declared holographic assets: {missing_assets}')

          css_files = sorted(path for path in asset_paths if path.suffix.lower() == '.css')
          if not css_files:
              raise SystemExit('missing holographic CSS')
          css_required = (
              'SZL Public Experience v3',
              '--szl-touch-target',
              '100dvh',
              'safe-area-inset',
              'overflow-x: clip',
              'max-width: 479px',
              'min-width: 768px',
              'min-width: 1440px',
              'min-width: 1920px',
              'min-width: 2560px',
              'prefers-reduced-motion',
              'prefers-contrast',
              'forced-colors',
              '@media print',
          )
          for path in css_files:
              text = path.read_text(encoding='utf-8')
              missing = [item for item in css_required if item not in text]
              if missing:
                  raise SystemExit(f'{path}: missing responsive contracts: {missing}')
              prohibited = ('@import', 'cdn.', 'unpkg.', 'jsdelivr.')
              if any(item in text for item in prohibited):
                  raise SystemExit(f'{path}: external runtime asset')
              if text.count('{') != text.count('}'):
                  raise SystemExit(f'{path}: unbalanced CSS braces')

          js_files = sorted(path for path in asset_paths if path.suffix.lower() == '.js')
          prohibited_js = (
              'fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage',
              'sessionStorage', 'document.cookie',
          )
          for path in js_files:
              text = path.read_text(encoding='utf-8')
              for marker in (
                  '__SZL_PUBLIC_EXPERIENCE_V3__',
                  'szlPublicExperienceV3',
                  'szlViewportTier',
                  'visualViewport',
                  'requestAnimationFrame',
              ):
                  if marker not in text:
                      raise SystemExit(f'{path}: missing {marker}')
              if any(item in text for item in prohibited_js):
                  raise SystemExit(f'{path}: prohibited client behavior')
              subprocess.run(['node', '--check', str(path)], check=True)

          py_files = sorted(
              path for path in Path('.').rglob('*.py')
              if path.name in {
                  'szl_hologram_assets.py',
                  'szl_hologram_streamlit.py',
              } and '.git' not in path.parts
          )
          entrypoint = os.environ.get('SZL_HOLO_ENTRYPOINT', '')
          if entrypoint and entrypoint.endswith('.py'):
              py_files.append(Path(entrypoint))
          for path in dict.fromkeys(py_files):
              py_compile.compile(str(path), doraise=True)

          if entrypoint:
              target = Path(entrypoint)
              if not target.is_file():
                  raise SystemExit(f'missing entrypoint: {entrypoint}')
              text = target.read_text(encoding='utf-8')
              source_markers = (
                  'szl-space-hologram',
                  'SZL Holographic Space Fabric v2',
                  'szl_hologram',
                  'data-szl-holo-space-v2',
              )
              asset_names = tuple(path.name for path in asset_paths)
              if not any(marker in text for marker in (*source_markers, *asset_names)):
                  raise SystemExit(f'{entrypoint}: source binding missing')
          PY
          git diff --check
'''
    return (
        textwrap.dedent(template)
        .lstrip()
        .replace("__ENTRYPOINT__", json.dumps(entrypoint or ""))
        .replace("__ASSET_PATHS__", json.dumps(declared_assets))
    )


def install(core: Any) -> None:
    """Wrap ``core.plan_repository`` exactly once and append the gate file."""
    if getattr(core, "_szl_target_contract_installed", False):
        return
    original = core.plan_repository

    def plan_with_target_contract(*args: Any, **kwargs: Any):
        plan = original(*args, **kwargs)
        if plan.status == "planned":
            workflow_path = ".github/workflows/szl-holographic-space-v2.yml"
            asset_paths = sorted(
                {
                    change.path
                    for change in plan.changes
                    if change.path.lower().endswith((".css", ".js"))
                }
            )
            rendered = target_contract(plan.entrypoint, asset_paths)
            existing = next(
                (change for change in plan.changes if change.path == workflow_path),
                None,
            )
            if existing is None:
                plan.changes.append(core.Change(workflow_path, rendered))
            else:
                plan.changes = [
                    core.Change(workflow_path, rendered)
                    if change.path == workflow_path
                    else change
                    for change in plan.changes
                ]
        return plan

    core.plan_repository = plan_with_target_contract
    core._szl_target_contract_installed = True
