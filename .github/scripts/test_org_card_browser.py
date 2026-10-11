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
    args = parser.parse_args()
    site = args.site.resolve()
    assert (site / "index.html").is_file(), "materialized entrypoint missing"
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            specs = [{"name": f"width-{width}", "width": width}
                     for width in (320, 375, 744, 768, 1024, 1440, 1920)]
            specs += [{"name": "touch-375", "width": 375, "touch": True}]
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
                  const navTargets = [...root.querySelectorAll('nav a, .szl-hf-actions a')]
                    .filter(node => node.getClientRects().length)
                    .filter(node => node.getBoundingClientRect().height < 43.5)
                    .map(node => node.textContent.trim());
                  const portfolio = [...root.querySelectorAll('.szl-hf-portfolio-card')];
                  const native = root.querySelector('[aria-labelledby="szl-hf-native-kernels-title"]');
                  return {viewport, scrollWidth: document.documentElement.scrollWidth,
                    overflow, navTargets,
                    portfolio: portfolio.map(node => ({
                      title: node.querySelector('h3').textContent.trim(),
                      background: getComputedStyle(node).backgroundImage})),
                    nativeLinks: native ? [...native.querySelectorAll('a')]
                      .map(node => node.getAttribute('href')) : [],
                    hero: hero ? {width: hero.getBoundingClientRect().width,
                      height: hero.getBoundingClientRect().height,
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
                if layout["navTargets"]:
                    failures.append("primary navigation hit target is below 44px")
                if {card["title"] for card in layout["portfolio"]} != {
                        "Models", "Kernels", "Datasets", "Spaces"}:
                    failures.append("four separate artifact entry points are not rendered")
                expected_native_links = {
                    f"https://huggingface.co/kernels/SZLHOLDINGS/{name}"
                    for name in ("szl-kernels", "szl-lambda-gate", "szl-block-kv", "szl-governed-norm")
                } | {"https://huggingface.co/SZLHOLDINGS/kernels"}
                if set(layout["nativeLinks"]) != expected_native_links:
                    failures.append("native kernel navigation points to the wrong namespace")
                if any(not card["background"].startswith("linear-gradient(rgb(")
                       or "rgba(" in card["background"].split("), linear-gradient(")[0]
                       for card in layout["portfolio"]):
                    failures.append("portfolio reading surface is not painted opaquely")
                if errors:
                    failures.append("page JavaScript error")
                if failures or spec["name"] in ("width-320", "width-1440", "touch-375"):
                    page.screenshot(path=str(args.output / f'{spec["name"]}.png'), full_page=True)
                archive = page.locator("details summary").first
                archive.focus()
                page.keyboard.press("Space")
                archive_focus = archive.evaluate("""node => ({
                  opened: node.parentElement.open,
                  focused: document.activeElement === node,
                  outline: getComputedStyle(node).outlineStyle,
                  width: parseFloat(getComputedStyle(node).outlineWidth)
                })""")
                if not archive_focus["opened"] or not archive_focus["focused"] \
                        or archive_focus["outline"] == "none" or archive_focus["width"] < 2:
                    failures.append("archive disclosure lacks visible native keyboard focus")
                page.keyboard.press("Space")
                page.emulate_media(forced_colors="active")
                forced = page.locator(".szl-hf-portfolio-card").first.evaluate("""node => ({
                  background: getComputedStyle(node).backgroundImage,
                  border: getComputedStyle(node).borderTopStyle,
                  width: parseFloat(getComputedStyle(node).borderTopWidth)
                })""")
                if forced["background"] != "none" or forced["border"] == "none" or forced["width"] < 1:
                    failures.append("forced-color portfolio lacks a solid native border")
                results.append({**spec, **layout, "archiveFocus": archive_focus,
                                "forcedColors": forced, "errors": errors, "failures": failures})
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
