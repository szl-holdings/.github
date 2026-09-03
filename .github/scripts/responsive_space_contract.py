#!/usr/bin/env python3
"""Extend Holographic Space Fabric v2 with SZL Public Experience v3.

The extension is additive and source-native. It appends the reviewed responsive
CSS and JavaScript to existing trusted product assets, refreshes centrally
managed Holo assets, and moves the review branch to a v3-specific name. It never
writes a default branch directly or replaces product-owned information
architecture, workflows, evidence semantics, or visual identity.
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
CUSTOM_ASSET_PAIRS = (
    ("app/static/holo.css", "app/static/holo.js"),
    ("static/szl-universal-frontend.css", "static/truth-cop.js"),
    ("space/szl-holo-v2.css", "space/szl-holo-v2.js"),
)
GENERATED_CSS_SUFFIX = "szl-space-hologram.css"
GENERATED_JS_SUFFIX = "szl-space-hologram.js"


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
        "document.documentElement.dataset.szlSpaceHoloV2='true';"
        "document.documentElement.dataset.szlPublicExperienceV3='true';"
        "document.documentElement.dataset.szlViewportTier="
        "(innerWidth<480?'phone':innerWidth<768?'compact':innerWidth<1024?'tablet':"
        "innerWidth<1440?'desktop':innerWidth<1920?'wide':innerWidth<2560?'theatre':'ultrawide');"
        "document.documentElement.dataset.szlZoomTier='normal';"
        "if(!String(document.title||'').trim()){document.title=String({slug!r}).replace(/[_-]+/g,' ').replace(/\\b\\w/g,function(c){return c.toUpperCase();})+' · SZL Holdings';}"
        "</script>"
    )
    if needle not in source:
        raise RuntimeError("Streamlit helper injection point is missing")
    return source.replace(needle, replacement)


def _entrypoint(paths: set[str], core: Any) -> str | None:
    preferred = (
        "app/static/index.html",
        "static/index.html",
        "space/index.html",
        *core.NEXT_LAYOUTS,
        *core.STATIC_INDEXES,
        *core.PYTHON_ENTRIES,
    )
    return next((candidate for candidate in preferred if candidate in paths), None)


def _custom_pairs(paths: set[str]) -> list[tuple[str, str]]:
    pairs = [pair for pair in CUSTOM_ASSET_PAIRS if pair[0] in paths and pair[1] in paths]
    generated_css = sorted(path for path in paths if path.endswith(GENERATED_CSS_SUFFIX))
    generated_js = set(path for path in paths if path.endswith(GENERATED_JS_SUFFIX))
    for css_path in generated_css:
        js_path = css_path[: -len(GENERATED_CSS_SUFFIX)] + GENERATED_JS_SUFFIX
        if js_path in generated_js:
            pairs.append((css_path, js_path))
    return pairs


def _existing_asset_changes(
    core: Any,
    github: Any,
    repo: Mapping[str, Any],
    plan: Any,
    combined_css: str,
    combined_javascript: str,
    responsive_css: str,
    responsive_javascript: str,
) -> list[Any]:
    """Refresh an already reviewed asset host without adding a second shell.

    Centrally generated `szl-space-hologram.*` files are replaced by the newest
    combined Holo + responsive bytes. Product-owned asset hosts receive only the
    additive responsive layer, preserving their own palette, motifs, and logic.
    """
    full_name = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    blobs = github.tree(full_name, default_branch)
    paths = {str(item.get("path")) for item in blobs}
    changes: list[Any] = []

    for css_path, js_path in _custom_pairs(paths):
        current_css, _ = github.file(full_name, css_path, default_branch)
        current_js, _ = github.file(full_name, js_path, default_branch)
        generated = css_path.endswith(GENERATED_CSS_SUFFIX) and js_path.endswith(GENERATED_JS_SUFFIX)
        next_css = combined_css if generated else _append_once(current_css, responsive_css, CSS_MARKER)
        next_js = combined_javascript if generated else _append_once(current_js, responsive_javascript, JS_MARKER)
        if next_css != current_css:
            changes.append(core.Change(css_path, next_css))
        if next_js != current_js:
            changes.append(core.Change(js_path, next_js))

    streamlit_helpers = sorted(path for path in paths if path.endswith("szl_hologram_streamlit.py"))
    gradio_helpers = sorted(path for path in paths if path.endswith("szl_hologram_assets.py"))
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
        plan.adapter = "responsive-existing-host"
        plan.entrypoint = _entrypoint(paths, core)
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
        existing = _existing_asset_changes(
            core,
            github,
            repo,
            plan,
            css,
            javascript,
            responsive_css,
            responsive_javascript,
        )
        if existing:
            # Prefer a reviewed existing asset host over creating a duplicate
            # navigation shell or second theme runtime in the same product.
            plan.changes = existing
            plan.status = "planned"
        elif plan.status == "already-integrated":
            plan.status = "already-integrated"
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

## SZL Public Experience v3.1

This rollout also applies the estate-wide responsive contract:

- phone widths from 320px, compact landscape, tablet, desktop, 1440p, 2560p,
  and ultrawide theatre presentation;
- no document-level horizontal overflow; wide tables and code remain locally
  scrollable instead of being clipped;
- dynamic viewport units, mobile safe areas, 48px coarse-pointer controls,
  readable form sizing, media containment, and bounded dialogs;
- 200% and 400% zoom reflow with shared chrome prevented from becoming a
  viewport-blocking fixed overlay;
- reduced-motion, increased-contrast, forced-colors, zoom/reflow, and print
  behavior;
- a non-destructive fallback title for otherwise untitled public Spaces;
- a concise shared ecosystem rail whose Shadow DOM is independently hardened
  for phone through theatre displays;
- stable `user`, `developer`, `investor`, and `operator` audience state through
  a local data attribute, without changing product behavior or making claims.

The responsive layer is additive. It does not replace the product's own layout,
data, workflows, copy, model behavior, or evidence semantics. When a reviewed
product-owned asset host already exists, this PR refreshes that host rather than
creating a second navigation or visual runtime.
"""

    core.pr_body = pr_body
    core.BRANCH = BRANCH
    core._szl_public_experience_v3_installed = True
