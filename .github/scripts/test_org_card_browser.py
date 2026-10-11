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
            # The public Hub profile removes conditional CSS groups. Its card
            # container can also be narrower than the browser viewport. Verify
            # the retained top-level styles at the actual content width.
            specs += [{"name": f"hub-{width}", "width": width, "hub": True}
                      for width in (320, 375, 390, 640)]
            specs += [{"name": "hub-narrow-desktop", "width": 1440,
                       "hub": True, "container_width": 316}]
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
                    removed_groups = page.evaluate("""containerWidth => {
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
                      host.style.width = containerWidth ? `${containerWidth}px` : 'calc(100% - 74px)';
                      host.style.margin = '0 auto';
                      root.replaceWith(host); host.append(root);
                      document.body.style.margin = '0';
                      return removed;
                    }""", spec.get("container_width"))
                page.evaluate("document.fonts.ready")
                page.evaluate("window.scrollTo(0, 0)")
                layout = page.evaluate("""() => {
                  const root = document.querySelector('#szl-hf-org-card');
                  const viewport = window.innerWidth;
                  const nodes = [...root.querySelectorAll('*')].filter(node => {
                    const style = getComputedStyle(node);
                    return node.getClientRects().length && style.position !== 'absolute'
                      && style.visibility !== 'hidden' && style.display !== 'none';
                  });
                  const overflow = nodes.filter(node => {
                    const rect = node.getBoundingClientRect();
                    return rect.width && (rect.left < -2 || rect.right > viewport + 2);
                  }).map(node => ({tag: node.tagName, class: String(node.className),
                    text: (node.textContent || '').trim().slice(0, 64),
                    box: node.getBoundingClientRect().toJSON()}));
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
                    overflow, navTargets, cardWidth: root.getBoundingClientRect().width,
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
                }""")
                failures = []
                if layout["overflow"] or layout["scrollWidth"] > spec["width"] + 2:
                    failures.append("content leaves the viewport")
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
                results.append({**spec, **layout, "conditional_css_removed": removed_groups,
                                "errors": errors, "failures": failures})
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
              "results": results}
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    failed = [result for result in results if result["failures"]]
    if failed:
        print(json.dumps(failed, indent=2))
        return 1
    print(f"org-card browser: {len(results)} responsive contexts pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
