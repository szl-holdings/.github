#!/usr/bin/env python3
"""Extend Holographic Space Fabric v2 with SZL Public Experience v3.

The extension is additive and source-native. It appends the reviewed responsive
CSS and JavaScript to the existing local Space assets, refreshes already-bound
repositories instead of treating them as terminal, and moves the review branch
to a v3-specific name. It never writes a default branch directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "design" / "responsive-v3"
CSS_MARKER = "SZL Public Experience v3"
JS_MARKER = "__SZL_PUBLIC_EXPERIENCE_V3__"
BRANCH = "design/szl-public-experience-v3"
TARGET_WORKFLOW = ".github/workflows/szl-holographic-space-v2.yml"


def _read_assets() -> tuple[str, str]:
    css = (ASSETS / "szl-responsive-v3.css").read_text(encoding="utf-8").rstrip() + "\n"
    javascript = (ASSETS / "szl-responsive-v3.js").read_text(encoding="utf-8").rstrip() + "\n"
    if CSS_MARKER not in css or JS_MARKER not in javascript:
        raise RuntimeError("responsive v3 asset marker is missing")
    return css, javascript


def _append_once(base: str, addition: str, marker: str) -> str:
    if marker in base:
        return base
    return base.rstrip() + "\n\n" + addition.lstrip()


def _streamlit_helper(core: Any, original: Any) -> str:
    source = original()
    marker = "dataset.szlPublicExperienceV3"
    if marker in source:
        return source
    needle = "document.documentElement.dataset.szlSpaceSlug={slug!r};</script>"
    replacement = (
        "document.documentElement.dataset.szlSpaceSlug={slug!r};"
        "document.documentElement.dataset.szlPublicExperienceV3='true';"
        "document.documentElement.dataset.szlViewportTier="
        "(innerWidth<480?'phone':innerWidth<768?'compact':innerWidth<1024?'tablet':"
        "innerWidth<1440?'desktop':innerWidth<1920?'wide':innerWidth<2560?'theatre':'ultrawide');"
        "</script>"
    )
    if needle not in source:
        raise RuntimeError("Streamlit helper injection point is missing")
    return source.replace(needle, replacement)


def _existing_asset_changes(
    core: Any,
    github: Any,
    repo: Mapping[str, Any],
    plan: Any,
    css: str,
    javascript: str,
) -> list[Any]:
    full_name = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    blobs = github.tree(full_name, default_branch)
    paths = sorted(str(item.get("path")) for item in blobs)
    changes: list[Any] = []

    css_paths = [path for path in paths if path.endswith("szl-space-hologram.css")]
    js_paths = [path for path in paths if path.endswith("szl-space-hologram.js")]
    streamlit_helpers = [path for path in paths if path.endswith("szl_hologram_streamlit.py")]
    gradio_helpers = [path for path in paths if path.endswith("szl_hologram_assets.py")]

    for path in css_paths:
        current, _ = github.file(full_name, path, default_branch)
        if CSS_MARKER not in current:
            changes.append(core.Change(path, css))
    for path in js_paths:
        current, _ = github.file(full_name, path, default_branch)
        if JS_MARKER not in current:
            changes.append(core.Change(path, javascript))
    for path in streamlit_helpers:
        current, _ = github.file(full_name, path, default_branch)
        rendered = core.streamlit_helper()
        if "dataset.szlPublicExperienceV3" not in current or current != rendered:
            changes.append(core.Change(path, rendered))
    for path in gradio_helpers:
        current, _ = github.file(full_name, path, default_branch)
        rendered = core.gradio_helper()
        if current != rendered:
            changes.append(core.Change(path, rendered))

    if changes:
        plan.adapter = "responsive-refresh"
        for candidate in (*core.NEXT_LAYOUTS, *core.STATIC_INDEXES, *core.PYTHON_ENTRIES):
            if candidate in paths:
                plan.entrypoint = candidate
                break
    return changes


def install(core: Any) -> None:
    """Install Public Experience v3 into the rollout core exactly once."""
    if getattr(core, "_szl_public_experience_v3_installed", False):
        return

    responsive_css, responsive_javascript = _read_assets()
    original_read_assets = core.read_assets
    original_plan_repository = core.plan_repository
    original_pr_body = core.pr_body
    original_streamlit_helper = core.streamlit_helper

    def read_assets(root: Path) -> tuple[str, str, str]:
        css, javascript, registry = original_read_assets(root)
        return (
            _append_once(css, responsive_css, CSS_MARKER),
            _append_once(javascript, responsive_javascript, JS_MARKER),
            registry,
        )

    def streamlit_helper() -> str:
        return _streamlit_helper(core, original_streamlit_helper)

    core.read_assets = read_assets
    core.streamlit_helper = streamlit_helper

    def plan_repository(
        github: Any,
        repo: Mapping[str, Any],
        spaces: list[Any],
        score: int,
        reason: str,
        css: str,
        javascript: str,
    ) -> Any:
        plan = original_plan_repository(github, repo, spaces, score, reason, css, javascript)
        if plan.status == "already-integrated":
            changes = _existing_asset_changes(core, github, repo, plan, css, javascript)
            if changes:
                plan.changes = changes
                plan.status = "planned"
        if plan.status == "planned":
            deduped: dict[str, Any] = {}
            for change in plan.changes:
                deduped[change.path] = change
            plan.changes = list(deduped.values())
        return plan

    core.plan_repository = plan_repository

    def pr_body(plan: Any, digest: str) -> str:
        body = original_pr_body(plan, digest)
        return body + """

## SZL Public Experience v3

This rollout also applies the estate-wide responsive contract:

- phone widths from 320px, compact landscape, tablet, desktop, 1440p, 2560p,
  and ultrawide theatre presentation;
- no document-level horizontal overflow; wide tables and code remain locally
  scrollable instead of being clipped;
- dynamic viewport units, mobile safe areas, 44px coarse-pointer controls,
  readable form sizing, media containment, and bounded dialogs;
- reduced-motion, increased-contrast, forced-colors, zoom/reflow, and print
  behavior;
- a concise shared ecosystem rail whose Shadow DOM is independently hardened
  for phone through theatre displays.

The responsive layer is additive. It does not replace the product's own layout,
data, workflows, copy, model behavior, or evidence semantics.
"""

    core.pr_body = pr_body
    core.BRANCH = BRANCH
    core._szl_public_experience_v3_installed = True
