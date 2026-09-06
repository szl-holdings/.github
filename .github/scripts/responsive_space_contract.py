#!/usr/bin/env python3
"""Extend Holographic Space Fabric v2 with SZL Public Experience v3.

The extension is additive and source-native. It appends the reviewed responsive
CSS and JavaScript to existing trusted product assets, refreshes centrally
managed Holo assets, honors reviewed nested static entrypoints, and moves the
review branch to a v3-specific name. It never writes a default branch directly
or replaces product-owned information architecture, workflows, evidence
semantics, or visual identity.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "design" / "responsive-v3"
CSS_MARKER = "SZL Public Experience v3"
JS_MARKER = "__SZL_PUBLIC_EXPERIENCE_V3__"
BRANCH = "design/szl-public-experience-v3"
TARGET_WORKFLOW = ".github/workflows/szl-holographic-space-v2.yml"
PUBLISHER_OWNERSHIP = "publisher-generated-flagship"
CUSTOM_ASSET_PAIRS = (
    ("app/static/holo.css", "app/static/holo.js"),
    ("static/szl-universal-frontend.css", "static/truth-cop.js"),
    ("space/szl-holo-v2.css", "space/szl-holo-v2.js"),
    ("frontend/szl-holo-v2.css", "frontend/szl-holo-v2.js"),
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
        "frontend/index.html",
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


def _source_entries(core: Any) -> dict[str, dict[str, Any]]:
    """Read the protected source map without importing a later-installed wrapper."""

    source_map = getattr(core, "LOCAL_SOURCE_MAP", None)
    if source_map is None:
        return {}
    path = Path(source_map)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "szl.public-space-source-map/v1":
        raise core.RolloutError(
            "LOCAL_SOURCE_MAP_SCHEMA_INVALID",
            str(payload.get("schema")),
        )
    values = payload.get("sources")
    if not isinstance(values, list):
        raise core.RolloutError("LOCAL_SOURCE_MAP_INVALID", "sources must be a list")

    entries: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise core.RolloutError(
                "LOCAL_SOURCE_MAP_INVALID",
                "source entries must be objects",
            )
        slug = core._space_slug(value.get("space"))
        repository = core._canonical_repo(value.get("repo"))
        if not slug or not repository:
            raise core.RolloutError(
                "LOCAL_SOURCE_MAP_INVALID",
                json.dumps(value, sort_keys=True),
            )
        normalized = dict(value)
        normalized["space"] = slug
        normalized["repo"] = repository
        previous = entries.get(slug)
        if previous and previous != normalized:
            raise core.RolloutError("LOCAL_SOURCE_MAP_CONFLICT", slug)
        entries[slug] = normalized
    return entries


def _safe_static_root(core: Any, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise core.RolloutError(
            "EXPLICIT_STATIC_ROOT_INVALID",
            "source_root must be a non-empty string",
        )
    rendered = value.strip()
    path = PurePosixPath(rendered)
    if (
        path.is_absolute()
        or "\\" in rendered
        or ".." in path.parts
        or path.suffix.lower() != ".html"
    ):
        raise core.RolloutError(
            "EXPLICIT_STATIC_ROOT_INVALID",
            rendered,
        )
    return str(path)


def _explicit_static_root(
    core: Any,
    repo: Mapping[str, Any],
    spaces: list[Any],
) -> str | None:
    entries = _source_entries(core)
    full_name = str(repo.get("full_name") or "")
    roots: set[str] = set()
    for space in spaces:
        entry = entries.get(core.normalize(space.slug))
        if not entry or entry.get("repo") != full_name:
            continue
        if entry.get("ownership") == PUBLISHER_OWNERSHIP:
            continue
        source_root = entry.get("source_root")
        if source_root is None:
            continue
        if not isinstance(source_root, str):
            raise core.RolloutError(
                "EXPLICIT_STATIC_ROOT_INVALID",
                f"{space.slug} source_root must be a string",
            )
        if not source_root.strip().lower().endswith(".html"):
            continue
        roots.add(_safe_static_root(core, source_root))
    if not roots:
        return None
    if len(roots) != 1:
        raise core.RolloutError(
            "EXPLICIT_STATIC_ROOT_CONFLICT",
            f"{full_name} declares multiple static roots: {sorted(roots)}",
        )
    return next(iter(roots))


def _asset_change(
    core: Any,
    github: Any,
    full_name: str,
    default_branch: str,
    paths: set[str],
    path: str,
    desired: str,
) -> Any | None:
    if path not in paths:
        return core.Change(path, desired)
    current, _ = github.file(full_name, path, default_branch)
    return core.Change(path, desired) if current != desired else None


def _explicit_static_changes(
    core: Any,
    github: Any,
    repo: Mapping[str, Any],
    spaces: list[Any],
    combined_css: str,
    combined_javascript: str,
) -> tuple[str, list[Any]] | None:
    root = _explicit_static_root(core, repo, spaces)
    if root is None:
        return None

    full_name = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    paths = {
        str(item.get("path") or "")
        for item in github.tree(full_name, default_branch)
    }
    if root not in paths:
        raise core.RolloutError(
            "EXPLICIT_STATIC_ROOT_MISSING",
            f"{full_name}:{root} does not exist",
        )

    current, _ = github.file(full_name, root, default_branch)
    patched = core.adapt_static(
        current,
        "./szl-space-hologram.css",
        "./szl-space-hologram.js",
        spaces[0].slug,
    )
    parent = PurePosixPath(root).parent
    prefix = "" if str(parent) == "." else f"{parent}/"
    css_path = prefix + GENERATED_CSS_SUFFIX
    js_path = prefix + GENERATED_JS_SUFFIX
    changes: list[Any] = []
    css_change = _asset_change(
        core,
        github,
        full_name,
        default_branch,
        paths,
        css_path,
        combined_css,
    )
    js_change = _asset_change(
        core,
        github,
        full_name,
        default_branch,
        paths,
        js_path,
        combined_javascript,
    )
    if css_change is not None:
        changes.append(css_change)
    if js_change is not None:
        changes.append(js_change)
    if patched != current:
        changes.append(core.Change(root, patched))
    return root, changes


def _existing_asset_changes(
    core: Any,
    github: Any,
    repo: Mapping[str, Any],
    plan: Any,
    combined_css: str,
    combined_javascript: str,
    responsive_css: str,
    responsive_javascript: str,
) -> list[Any] | None:
    """Refresh a reviewed asset host, distinguishing absence from a no-op.

    ``None`` means no recognized host. An empty list means its assets are
    already current and must not fall through to another shell adapter.

    Centrally generated `szl-space-hologram.*` files are replaced by the newest
    combined Holo + responsive bytes. Product-owned asset hosts receive only the
    additive responsive layer, preserving their own palette, motifs, and logic.
    """

    full_name = str(repo["full_name"])
    default_branch = str(repo.get("default_branch") or "main")
    blobs = github.tree(full_name, default_branch)
    paths = {str(item.get("path")) for item in blobs}
    changes: list[Any] = []

    pairs = _custom_pairs(paths)
    for css_path, js_path in pairs:
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

    if pairs or streamlit_helpers or gradio_helpers:
        plan.adapter = "responsive-existing-host"
        plan.entrypoint = _entrypoint(paths, core)
        return changes
    return None


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
        plan = original_plan_repository(
            github,
            repo,
            spaces,
            score,
            reason,
            css,
            javascript,
        )
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
        if existing is not None:
            # Prefer a reviewed existing asset host over creating a duplicate
            # navigation shell or second theme runtime in the same product.
            plan.changes = existing
            plan.status = "planned" if existing else "already-integrated"
        else:
            explicit = _explicit_static_changes(
                core,
                github,
                repo,
                spaces,
                css,
                javascript,
            )
            if explicit is not None:
                root, changes = explicit
                plan.adapter = "responsive-explicit-static"
                plan.entrypoint = root
                plan.changes = changes
                plan.status = "planned" if changes else "already-integrated"
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
creating a second navigation or visual runtime. Reviewed nested static roots are
used exactly as declared in the protected source map; the controller never
guesses a sibling page.
"""

    core.pr_body = pr_body
    core.BRANCH = BRANCH
    core._szl_public_experience_v3_installed = True
