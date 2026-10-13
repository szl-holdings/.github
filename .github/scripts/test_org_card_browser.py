#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure the materialized static front door in an isolated local browser.

This is a source presentation test. External requests are blocked, no Hub API
is called, and the report makes no statement about a deployed Space.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

def main() -> int:
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path,
                        help="Optional installed browser for local observations; CI uses pinned Chromium")
    args = parser.parse_args()
    site = args.site.resolve()
    assert (site / "index.html").is_file(), "materialized entrypoint missing"
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        launch_options = {"headless": True}
        if args.browser_executable:
            launch_options["executable_path"] = str(args.browser_executable)
        browser = playwright.chromium.launch(**launch_options)
        try:
            specs = [{"name": f"width-{width}", "width": width}
                     for width in (320, 375, 744, 768, 900, 1024, 1180, 1440, 1920)]
            specs += [{"name": "touch-375", "width": 375, "touch": True}]
            specs += [{"name": f"archive-open-{width}", "width": width, "open_archive": True}
                      for width in (320, 1440)]
            # The public Hub profile removes conditional CSS groups. Its card
            # container can also be narrower than the browser viewport. Verify
            # the retained top-level styles at the actual content width. Each
            # Hub fixture declares the host width its page gutter must leave.
            specs += [{"name": f"hub-{width}", "width": width, "hub": True,
                       "expected_host_width": host_width}
                      for width, host_width in ((320, 246), (375, 301), (390, 316), (640, 566))]
            specs += [{"name": "hub-narrow-desktop", "width": 1440,
                       "hub": True, "container_width": 316, "expected_host_width": 316}]
            for spec in specs:
                page = browser.new_page(viewport={"width": spec["width"], "height": 1000},
                                        reduced_motion="reduce", has_touch=spec.get("touch", False),
                                        is_mobile=spec.get("touch", False))
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                # The embeddable card uses absolute self-hosted asset URLs.
                # Fulfill those exact URLs from the candidate source fixture;
                # this never reads a live or previously deployed asset.
                def candidate_asset(route):
                    path = site / urlsplit(route.request.url).path.lstrip("/")
                    if not path.resolve().is_relative_to(site) or not path.is_file():
                        route.abort()
                        return
                    route.fulfill(body=path.read_bytes(), content_type=mimetypes.guess_type(path)[0]
                                  or "application/octet-stream")
                page.route("https://szlholdings-readme.static.hf.space/**", candidate_asset)
                page.goto((site / "index.html").as_uri())
                page.locator("#szl-hf-org-card").wait_for()
                removed_groups = 0
                if spec.get("hub"):
                    removed_groups = page.evaluate(HUB_FIXTURE_SCRIPT, {
                        "containerWidth": spec.get("container_width"), "hostId": HUB_HOST_ID})
                if spec.get("open_archive"):
                    page.locator("details.szl-hf-archive").evaluate("node => { node.open = true; }")
                page.evaluate("document.fonts.ready")
                page.evaluate("window.scrollTo(0, 0)")
                layout = measure_layout(page, spec)
                failures = layout_failures(spec, layout, removed_groups, errors)
                controls = []
                if spec.get("hub"):
                    # Negative controls mutate this exact fixture, rerun the
                    # production measurement and evaluator, then restore it.
                    controls = run_negative_controls(page, spec, layout, removed_groups, errors)
                    failures += [f"negative control did not behave as expected: {control['name']}"
                                 for control in controls if not control["passed"]]
                results.append({**spec, **layout, "conditional_css_removed": removed_groups,
                                "errors": errors, "failures": failures,
                                "negative_controls": controls})
                if failures or spec["name"] in ("width-320", "width-1440", "touch-375",
                                               "hub-390", "hub-narrow-desktop"):
                    page.screenshot(path=str(args.output / f'{spec["name"]}.png'), full_page=True)
                page.close()
        finally:
            browser.close()
    report = {"schema": "szl.org-card-browser-observation/v1",
              "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "scope": "MATERIALIZED_SOURCE_PRESENTATION_ONLY",
              "provider_requests": False, "deployment_observed": False,
              "containment_tolerance_px": CONTAINMENT_TOLERANCE_PX,
              "results": results}
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    failed = [result for result in results if result["failures"]]
    if failed:
        print(json.dumps(failed, indent=2))
        return 1
    control_count = sum(len(result["negative_controls"]) for result in results)
    print(f"org-card browser: {len(results)} responsive contexts pass; "
          f"{control_count} containment negative controls behave as expected")
    return 0


# Existing tolerance for subpixel layout. It applies to the viewport, the
# card host, the card root and every visible descendant alike.
CONTAINMENT_TOLERANCE_PX = 2
HOST_WIDTH_TOLERANCE_PX = 0.5
CONTROL_ESCAPE_PX = 12
CONTROL_PAGE_SCROLL_PX = 600
HUB_HOST_ID = "szl-hf-hub-host"

VIEWPORT_REASON = "content leaves the viewport"
HOST_IDENTITY_REASON = "card host identity is missing or ambiguous"
HOST_WIDTH_MISSING_REASON = "Hub fixture lacks a positive expected host width"
HOST_WIDTH_REASON = "Hub host width differs from the declared host width"
ROOT_CONTAINMENT_REASON = "card root leaves its host"
CONTENT_CONTAINMENT_REASON = "visible content leaves the card host bounds"
SCROLL_REASON = "card host or content scrolls or clips horizontally"
BADGE_REASON = "a card badge is hidden or excluded from containment"

HUB_FIXTURE_SCRIPT = """({containerWidth, hostId}) => {
  let removed = 0;
  for (const sheet of document.styleSheets) {
    for (let i = sheet.cssRules.length - 1; i >= 0; i--) {
      if (sheet.cssRules[i].type !== CSSRule.STYLE_RULE) {
        sheet.deleteRule(i); removed++;
      }
    }
  }
  const root = document.querySelector('#szl-hf-org-card');
  const host = document.createElement('div');
  host.id = hostId;
  host.style.width = containerWidth ? `${containerWidth}px` : 'calc(100% - 74px)';
  host.style.margin = '0 auto';
  root.replaceWith(host); host.append(root);
  document.body.style.margin = '0';
  return removed;
}"""

MEASURE_SCRIPT = """({hostSelector, tolerance}) => {
  const root = document.querySelector('#szl-hf-org-card');
  const viewport = window.innerWidth;
  const box = rect => ({left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
    width: rect.width, height: rect.height});
  // Host, card root and every content rectangle are read in one synchronous
  // turn, so scrolling or layout cannot move one of them between readings.
  const hostCandidates = hostSelector ? [...document.querySelectorAll(hostSelector)]
    : [document.documentElement];
  const host = hostCandidates.length === 1 ? hostCandidates[0] : null;
  const hostFound = Boolean(host) && (!hostSelector || root.parentElement === host);
  const hostRect = host ? box(host.getBoundingClientRect()) : null;
  const rootRect = box(root.getBoundingClientRect());
  const bounds = hostRect ? {
    left: Math.max(rootRect.left, hostRect.left), right: Math.min(rootRect.right, hostRect.right),
    top: Math.max(rootRect.top, hostRect.top), bottom: Math.min(rootRect.bottom, hostRect.bottom)} : null;
  const escapes = (rect, limits) => ({left: limits.left - rect.left, right: rect.right - limits.right,
    top: limits.top - rect.top, bottom: rect.bottom - limits.bottom});
  const exceeds = (rect, limits) => Object.values(escapes(rect, limits)).some(value => value > tolerance);
  const skip = root.querySelector('.szl-hf-skip');
  // The skip link is intentionally parked offscreen only until it is focused.
  const skipExempt = node => Boolean(skip) && document.activeElement !== skip && skip.contains(node);
  const rendered = node => {
    // Closed disclosure descendants can retain layout rectangles without being painted.
    if (!node.getClientRects().length || !node.checkVisibility()) return false;
    const style = getComputedStyle(node);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.visibility !== 'collapse';
  };
  const painted = rect => rect.width > 0 && rect.height > 0;
  const content = [];
  for (const node of root.querySelectorAll('*')) {
    if (skipExempt(node) || !rendered(node)) continue;
    const rect = node.getBoundingClientRect();
    if (painted(rect)) content.push({kind: 'element', node, rect, text: (node.textContent || '').trim()});
  }
  const range = document.createRange();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    const parent = text.parentElement;
    if (!text.textContent.trim() || !parent || skipExempt(parent) || !rendered(parent)) continue;
    range.selectNodeContents(text);
    for (const rect of range.getClientRects()) {
      if (painted(rect)) content.push({kind: 'text', node: parent, rect, text: text.textContent.trim()});
    }
  }
  const diagnose = item => ({kind: item.kind, tag: item.node.tagName,
    class: item.node.getAttribute('class') || '', text: item.text.slice(0, 64), box: box(item.rect),
    probe: Boolean(item.node.closest('[data-szl-probe]'))});
  const overflow = content.filter(item => item.rect.left < -tolerance || item.rect.right > viewport + tolerance);
  const offenders = bounds ? content.filter(item => exceeds(item.rect, bounds)) : [];
  const metrics = node => node ? {scrollWidth: node.scrollWidth, clientWidth: node.clientWidth} : null;
  const scrolling = [];
  const checkScroll = (node, role) => {
    if (node.scrollWidth > node.clientWidth + tolerance) {
      scrolling.push({role, tag: node.tagName, class: node.getAttribute('class') || '',
        scrollWidth: node.scrollWidth, clientWidth: node.clientWidth});
    }
  };
  if (host) checkScroll(host, 'host');
  checkScroll(root, 'root');
  for (const item of content) {
    if (item.kind === 'element' && getComputedStyle(item.node).overflowX !== 'visible') {
      checkScroll(item.node, 'clipping or scrolling descendant');
    }
  }
  const measured = new Set(content.filter(item => item.kind === 'element').map(item => item.node));
  // Every badge counts, whether or not a narrower readability selector covers it.
  const badges = [...root.querySelectorAll('.szl-hf-badge')];
  const containment = {
    hostSelector, hostCount: hostCandidates.length, hostFound, host: hostRect, root: rootRect, bounds,
    rootInsideHost: Boolean(hostRect) && !exceeds(rootRect, hostRect),
    rootEscape: hostRect ? escapes(rootRect, hostRect) : null,
    measuredCount: content.length, offenderCount: offenders.length,
    probeOffenderCount: offenders.filter(item => item.node.closest('[data-szl-probe]')).length,
    offenders: offenders.slice(0, 25).map(item => ({...diagnose(item), escape: escapes(item.rect, bounds)})),
    scrollMetrics: {host: metrics(host), root: metrics(root), document: metrics(document.documentElement)},
    scrollingCount: scrolling.length, scrolling: scrolling.slice(0, 25),
    badges: {total: badges.length, measured: badges.filter(node => measured.has(node)).length,
      contained: badges.filter(node => measured.has(node) && bounds
        && !exceeds(node.getBoundingClientRect(), bounds)).length},
    skip: skip ? {focused: document.activeElement === skip, exempt: skipExempt(skip),
      measured: measured.has(skip), box: box(skip.getBoundingClientRect())} : null,
    pageScroll: {x: window.scrollX, y: window.scrollY}};
  const hero = root.querySelector('img.szl-hf-hero-mark');
  const copy = root.querySelector('.szl-hf-hero-copy');
  const readable = [...root.querySelectorAll('.szl-hf-section-head > *, .szl-hf-step, .szl-hf-counts li')]
    .filter(node => node.getClientRects().length)
    .map(node => ({class: node.className, width: node.getBoundingClientRect().width}));
  const renderedCount = selector => [...root.querySelectorAll(selector)]
    .filter(node => node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden').length;
  const gridColumns = Object.fromEntries(['steps', 'portfolio', 'counts'].map(name => {
    const grid = root.querySelector(`.szl-hf-${name}`);
    return [name, grid ? getComputedStyle(grid).gridTemplateColumns.split(/\\s+/).length : 0];
  }));
  const navTargets = [...root.querySelectorAll('nav a, .szl-hf-actions a')]
    .filter(node => node.getClientRects().length)
    .filter(node => node.getBoundingClientRect().height < 43.5)
    .map(node => node.textContent.trim());
  return {viewport, scrollWidth: document.documentElement.scrollWidth,
    overflow: overflow.slice(0, 25).map(diagnose), overflowCount: overflow.length,
    containment, navTargets, cardWidth: rootRect.width,
    heroCopy: copy ? copy.getBoundingClientRect().toJSON() : null,
    readable, gridColumns, stepCount: renderedCount('.szl-hf-step'),
    headingCount: renderedCount('.szl-hf-section-head h2'),
    hero: hero ? {width: hero.getBoundingClientRect().width,
      height: hero.getBoundingClientRect().height,
      top: hero.getBoundingClientRect().top,
      loaded: hero.complete && hero.naturalWidth > 0} : null,
    counts: [...root.querySelectorAll('[data-szl-inventory-kind]')]
      .map(node => ({kind: node.dataset.szlInventoryKind,
        count: Number(node.querySelector('strong').textContent)}))};
}"""

SNAPSHOT_SCRIPT = """hostId => {
  window.__szlControlUndo = [];
  window.__szlBaselineDom = document.getElementById(hostId).outerHTML;
  return window.__szlBaselineDom.length;
}"""

CONTROL_SCRIPT = """plan => {
  const root = document.querySelector('#szl-hf-org-card');
  const host = document.getElementById(plan.hostId);
  const undo = window.__szlControlUndo;
  const remember = (node, name) => undo.push([node, name, node.getAttribute(name)]);
  const setStyle = (node, styles) => {
    remember(node, 'style');
    // Build the mutation off-node: a live CSSStyleDeclaration can recreate an
    // empty style attribute after removeAttribute, defeating exact restoration.
    const declaration = document.createElement('div').style;
    declaration.cssText = node.getAttribute('style') || '';
    Object.assign(declaration, styles);
    node.setAttribute('style', declaration.cssText);
  };
  const probe = node => { remember(node, 'data-szl-probe'); node.setAttribute('data-szl-probe', 'true'); };
  const badge = [...root.querySelectorAll('.szl-hf-badge')][plan.target ?? 0];
  const rectOf = node => node.getBoundingClientRect();
  const limits = () => {
    const outer = rectOf(host), card = rectOf(root);
    return {left: Math.max(outer.left, card.left), right: Math.min(outer.right, card.right)};
  };
  if (plan.clip === 'host') setStyle(host, {overflow: 'hidden'});
  if (plan.clip === 'root') setStyle(root, {overflow: 'hidden'});
  if (plan.op === 'shift') {
    probe(badge);
    const bounds = limits(), before = rectOf(badge);
    const dx = plan.edge === 'right' ? bounds.right + plan.offset - before.right
      : bounds.left - plan.offset - before.left;
    setStyle(badge, {transform: `translateX(${dx}px)`});
    const after = rectOf(badge), now = limits();
    return plan.edge === 'right' ? after.right - now.right : now.left - after.left;
  }
  if (plan.op === 'expand-root') {
    setStyle(root, {width: `${host.clientWidth + plan.offset}px`});
    return rectOf(root).right - rectOf(host).right;
  }
  if (plan.op === 'fractional-host') {
    setStyle(host, {width: `${rectOf(host).width + plan.offset}px`});
    return rectOf(host).width;
  }
  if (plan.op === 'scroll-root') {
    setStyle(root, {overflowX: 'auto'});
    setStyle(badge, {minWidth: `${root.clientWidth + plan.offset}px`});
    return root.scrollWidth - root.clientWidth;
  }
  if (plan.op === 'clip-badge') {
    setStyle(badge, {overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: '24px'});
    return badge.scrollWidth - badge.clientWidth;
  }
  if (plan.op === 'park-badge') {
    probe(badge);
    setStyle(badge, {position: 'absolute', left: '-9999px', top: '0px'});
    return rectOf(badge).right < 0 ? 1 : 0;
  }
  if (plan.op === 'hide-badge') {
    setStyle(badge, {display: 'none'});
    return badge.getClientRects().length === 0 ? 1 : 0;
  }
  if (plan.op === 'closed-disclosure' || plan.op === 'open-disclosure') {
    const disclosure = document.createElement('details');
    disclosure.innerHTML = '<summary>Containment fixture</summary><div data-szl-probe="true" style="position:absolute;left:-200px;top:0;width:100px;height:20px">Disclosure probe</div>';
    disclosure.open = plan.op === 'open-disclosure';
    root.append(disclosure);
    undo.push([disclosure, null, null]);
    return disclosure.open === (plan.op === 'open-disclosure') ? 1 : 0;
  }
  if (plan.op === 'duplicate-host') {
    const twin = document.createElement('div');
    twin.id = plan.hostId;
    document.body.append(twin);
    undo.push([twin, null, null]);
    return document.querySelectorAll(`#${plan.hostId}`).length === 2 ? 1 : 0;
  }
  if (plan.op === 'scroll-page') {
    window.scrollTo(0, plan.offset);
    return window.scrollY;
  }
  if (plan.op === 'focus-skip') {
    const skip = root.querySelector('.szl-hf-skip');
    skip.focus({preventScroll: true});
    return document.activeElement === skip ? 1 : 0;
  }
  throw new Error(`unknown negative control ${plan.op}`);
}"""

RESTORE_SCRIPT = """hostId => {
  for (const [node, name, value] of window.__szlControlUndo.reverse()) {
    if (name === null) node.remove();
    else if (value === null) node.removeAttribute(name);
    else node.setAttribute(name, value);
  }
  window.__szlControlUndo = [];
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  window.scrollTo(0, 0);
  const host = document.getElementById(hostId);
  return {dom: Boolean(host) && document.querySelectorAll(`#${hostId}`).length === 1
      && host.outerHTML === window.__szlBaselineDom,
    scrollX: window.scrollX, scrollY: window.scrollY,
    focusCleared: !document.activeElement || document.activeElement === document.body};
}"""


def measure_layout(page, spec):
    """Run the production layout measurement once for the current DOM."""
    return page.evaluate(MEASURE_SCRIPT, {
        "hostSelector": f"#{HUB_HOST_ID}" if spec.get("hub") else None,
        "tolerance": CONTAINMENT_TOLERANCE_PX})


def positive_width(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def containment_failures(spec, containment):
    """Judge host-relative containment; the viewport check stays separate."""
    failures = []
    if spec.get("hub"):
        expected = spec.get("expected_host_width")
        if not positive_width(expected):
            failures.append(HOST_WIDTH_MISSING_REASON)
        elif (not containment["host"]
              or abs(containment["host"]["width"] - expected) > HOST_WIDTH_TOLERANCE_PX):
            failures.append(HOST_WIDTH_REASON)
    if not containment["hostFound"]:
        failures.append(HOST_IDENTITY_REASON)
        return failures
    if not containment["rootInsideHost"]:
        failures.append(ROOT_CONTAINMENT_REASON)
    if containment["offenderCount"]:
        failures.append(CONTENT_CONTAINMENT_REASON)
    if containment["scrollingCount"]:
        failures.append(SCROLL_REASON)
    if containment["badges"]["measured"] != containment["badges"]["total"]:
        failures.append(BADGE_REASON)
    return failures


def layout_failures(spec, layout, removed_groups, errors):
    """Production evaluator shared by the real layouts and negative controls."""
    failures = []
    if layout["overflowCount"] or layout["scrollWidth"] > spec["width"] + CONTAINMENT_TOLERANCE_PX:
        failures.append(VIEWPORT_REASON)
    failures += containment_failures(spec, layout["containment"])
    if not layout["hero"] or not layout["hero"]["loaded"]:
        failures.append("shared mark is not loaded")
    if len(layout["counts"]) != 4:
        failures.append("four namespace counters are not rendered")
    if layout["stepCount"] != 6 or layout["headingCount"] == 0:
        failures.append("six-stage evidence loop or section headings are missing")
    if layout["navTargets"]:
        failures.append("primary navigation hit target is below 44px")
    if errors:
        failures.append("page JavaScript error")
    if spec.get("hub"):
        if removed_groups == 0:
            failures.append("Hub fixture did not remove conditional CSS")
        minimum = min(120, layout["cardWidth"] - 100)
        if any(item["width"] < minimum for item in layout["readable"]):
            failures.append("Hub content is compressed into unreadable columns")
        if layout["cardWidth"] <= 316 and any(value != 1 for value in layout["gridColumns"].values()):
            failures.append("narrow Hub grids must have one readable column")
        copy = layout["heroCopy"]
        if not copy or copy["width"] < min(240, layout["cardWidth"] - 80):
            failures.append("Hub hero text is compressed")
        if copy and layout["hero"] and copy["top"] > layout["hero"]["top"] + 2:
            failures.append("decorative mark precedes the Hub message")
    elif spec["width"] in (1180, 1440, 1920) and layout["gridColumns"]["portfolio"] != 2:
        failures.append("wide portfolio must retain a balanced two-column layout")
    return failures


def control_plans(badge_count):
    """DOM mutations whose outcome the production measurement must report."""
    plans = []
    for index in range(badge_count):
        for edge in ("right", "left"):
            plans.append({"name": f"badge-{index}-{edge}-escape-inside-viewport", "op": "shift",
                          "target": index, "edge": edge, "offset": CONTROL_ESCAPE_PX,
                          "expect": [CONTENT_CONTAINMENT_REASON], "inside_viewport": True})
    last = max(badge_count - 1, 0)
    for edge in ("right", "left"):
        plans.append({"name": f"boundary-{edge}-1.5px-within-tolerance", "op": "shift", "target": 0,
                      "edge": edge, "offset": 1.5, "expect": []})
        plans.append({"name": f"boundary-{edge}-2.5px-beyond-tolerance", "op": "shift", "target": 0,
                      "edge": edge, "offset": 2.5, "expect": [CONTENT_CONTAINMENT_REASON],
                      "inside_viewport": True})
    plans += [
        {"name": "fractional-host-width-rounding", "op": "fractional-host", "offset": 0.375,
         "expect": []},
        {"name": "expanded-root-inside-viewport", "op": "expand-root", "offset": CONTROL_ESCAPE_PX,
         "expect": [ROOT_CONTAINMENT_REASON], "inside_viewport": True},
        {"name": "clipped-host-right-escape", "op": "shift", "clip": "host", "target": last,
         "edge": "right", "offset": CONTROL_ESCAPE_PX, "expect": [CONTENT_CONTAINMENT_REASON],
         "inside_viewport": True},
        {"name": "clipped-root-left-escape", "op": "shift", "clip": "root", "target": last,
         "edge": "left", "offset": CONTROL_ESCAPE_PX, "expect": [CONTENT_CONTAINMENT_REASON],
         "inside_viewport": True},
        {"name": "horizontally-scrolling-root", "op": "scroll-root", "target": 0,
         "offset": 24, "expect": [SCROLL_REASON]},
        {"name": "clipped-badge-text", "op": "clip-badge", "target": last, "expect": [SCROLL_REASON]},
        {"name": "absolute-offscreen-badge-not-exempt", "op": "park-badge", "target": last,
         "expect": [CONTENT_CONTAINMENT_REASON, VIEWPORT_REASON]},
        {"name": "hidden-badge-not-omitted", "op": "hide-badge", "target": last,
         "expect": [BADGE_REASON]},
        {"name": "closed-disclosure-content-is-not-painted", "op": "closed-disclosure", "expect": []},
        {"name": "opened-disclosure-content-is-measured", "op": "open-disclosure",
         "expect": [CONTENT_CONTAINMENT_REASON, VIEWPORT_REASON]},
        {"name": "ambiguous-host-identity", "op": "duplicate-host", "expect": [HOST_IDENTITY_REASON]},
        {"name": "page-scrolled-rects-read-together", "op": "scroll-page",
         "offset": CONTROL_PAGE_SCROLL_PX, "expect": []},
        {"name": "skip-link-exemption-ends-on-focus", "op": "focus-skip", "expect": []},
    ]
    return plans


def control_took_effect(plan, achieved) -> bool:
    if not isinstance(achieved, (int, float)) or isinstance(achieved, bool):
        return False
    if plan["op"] == "shift":
        return abs(achieved - plan["offset"]) <= 0.25
    if plan["op"] == "expand-root":
        return abs(achieved - plan["offset"]) <= HOST_WIDTH_TOLERANCE_PX
    if plan["op"] == "fractional-host":
        return achieved % 1 != 0
    if plan["op"] in ("scroll-root", "clip-badge"):
        return achieved > CONTAINMENT_TOLERANCE_PX
    if plan["op"] == "scroll-page":
        return achieved > 0
    return achieved == 1


def control_verdict(plan, achieved, layout, observed, baseline_failures) -> bool:
    if not control_took_effect(plan, achieved):
        return False
    containment = layout["containment"]
    if plan["op"] == "focus-skip":
        skip = containment["skip"] or {}
        return skip.get("focused") is True and skip.get("exempt") is False and skip.get("measured") is True
    if not plan["expect"]:
        return observed == baseline_failures
    if not set(plan["expect"]) <= set(observed):
        return False
    if plan.get("inside_viewport") and VIEWPORT_REASON in observed:
        return False
    if plan["op"] in ("shift", "park-badge", "open-disclosure") and not containment["probeOffenderCount"]:
        return False
    return True


def containment_signature(layout):
    containment = layout["containment"]
    return ({key: containment["host"][key] for key in ("left", "right", "width")},
            {key: containment["root"][key] for key in ("left", "right", "width")},
            containment["measuredCount"], containment["offenderCount"],
            containment["scrollingCount"], containment["badges"], layout["overflowCount"])


def run_negative_controls(page, spec, baseline, removed_groups, errors):
    """Exercise the production measurement on deliberate faults, then restore."""
    baseline_failures = layout_failures(spec, baseline, removed_groups, errors)
    controls = []
    for name, value in (("expected-host-width-missing", None), ("expected-host-width-zero", 0),
                        ("expected-host-width-negative", -316), ("expected-host-width-boolean", True)):
        observed = layout_failures({**spec, "expected_host_width": value}, baseline, removed_groups, errors)
        controls.append({"name": name, "expect": [HOST_WIDTH_MISSING_REASON], "observed": observed,
                         "passed": HOST_WIDTH_MISSING_REASON in observed})
    mismatch = {**spec, "expected_host_width": spec.get("expected_host_width", 0) + 3}
    observed = layout_failures(mismatch, baseline, removed_groups, errors)
    controls.append({"name": "expected-host-width-mismatch", "expect": [HOST_WIDTH_REASON],
                     "observed": observed, "passed": HOST_WIDTH_REASON in observed})
    badge_count = baseline["containment"]["badges"]["total"]
    if not badge_count:
        controls.append({"name": "badge-controls-available", "expect": ["at least one badge"],
                         "observed": [], "passed": False})
        return controls
    page.evaluate(SNAPSHOT_SCRIPT, HUB_HOST_ID)
    for plan in control_plans(badge_count):
        achieved = page.evaluate(CONTROL_SCRIPT, {**plan, "hostId": HUB_HOST_ID})
        layout = measure_layout(page, spec)
        observed = layout_failures(spec, layout, removed_groups, errors)
        restore = page.evaluate(RESTORE_SCRIPT, HUB_HOST_ID)
        restored = (restore["dom"] and restore["scrollX"] == 0 and restore["scrollY"] == 0
                    and restore["focusCleared"])
        containment = layout["containment"]
        controls.append({"name": plan["name"], "expect": plan["expect"], "achieved": achieved,
                         "observed": observed, "offenders": containment["offenders"][:4],
                         "scrolling": containment["scrolling"][:4], "skip": containment["skip"],
                         "restored": restored,
                         "passed": restored and control_verdict(plan, achieved, layout, observed,
                                                                baseline_failures)})
        if not restored:
            break
    after = measure_layout(page, spec)
    controls.append({"name": "fixture-restored-after-controls", "expect": [], "observed": [],
                     "passed": containment_signature(after) == containment_signature(baseline)})
    return controls


if __name__ == "__main__":
    raise SystemExit(main())
