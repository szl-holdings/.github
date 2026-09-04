#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Browser-verify the public SZL estate for users, developers, and investors.

This auditor is read-only. It never logs in, submits a form, mutates a provider,
changes DNS, writes a Space, or treats a failed request as a zero-result claim.
Every case records the rendered URL, viewport, effective zoom, source markers,
accessibility findings, screenshot digest, and browser errors.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

SCHEMA = "szl.public-experience-v4/v1"
USER_AGENT = "SZL-Public-Experience-v4/1.0"
TIMEOUT_MS = 45_000
TOUCH_MIN = 44.0
OVERFLOW_TOLERANCE = 3.0
MAX_PAGE_BYTES = 8_000_000

TARGETS: tuple[dict[str, Any], ...] = (
    {
        "id": "product",
        "url": "https://a-11-oy.com/",
        "kind": "website",
        "required_markers": ("SZL",),
    },
    {
        "id": "proof",
        "url": "https://a11oy.net/",
        "kind": "website",
        "required_markers": ("SZL",),
    },
    {
        "id": "a11oy",
        "url": "https://szlholdings-a11oy.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "killinchu",
        "url": "https://szlholdings-killinchu.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "david-leads",
        "url": "https://szlholdings-david-leads.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "terra",
        "url": "https://szlholdings-terra.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "sentra",
        "url": "https://szlholdings-sentra.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "counsel",
        "url": "https://szlholdings-counsel.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "finance",
        "url": "https://szlholdings-finance.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "vessels",
        "url": "https://szlholdings-vessels.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
    {
        "id": "lyte",
        "url": "https://szlholdings-lyte.hf.space/",
        "kind": "space",
        "required_markers": ("data-szl-public-experience-v3",),
    },
)


@dataclass(frozen=True)
class Case:
    name: str
    width: int
    height: int
    zoom: float = 1.0
    reduced_motion: bool = False
    coarse_pointer: bool = False

    @property
    def effective_width(self) -> float:
        return self.width / self.zoom


CASES: tuple[Case, ...] = (
    Case("phone-320", 320, 568, coarse_pointer=True),
    Case("phone-375", 375, 812, coarse_pointer=True),
    Case("tablet-768", 768, 1024, coarse_pointer=True),
    Case("desktop-1440", 1440, 900),
    Case("reflow-200", 640, 900, zoom=2.0),
    Case("reflow-400", 1280, 900, zoom=4.0),
    Case("reduced-motion-phone", 375, 812, reduced_motion=True, coarse_pointer=True),
)

INTERACTIVE_SELECTOR = ",".join(
    (
        "a[href]",
        "button",
        "input:not([type='hidden'])",
        "select",
        "textarea",
        "summary",
        "[role='button']",
        "[role='link']",
        "[tabindex]:not([tabindex='-1'])",
    )
)

DEVELOPER_PATTERN = re.compile(
    r"\b(api|developer|docs?|source|github|build(?:\s+identity)?|json|schema)\b",
    re.IGNORECASE,
)
PROOF_PATTERN = re.compile(
    r"\b(investor|proof|evidence|receipt|attestation|status|trust|governance)\b",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "target"


def _failure(code: str, detail: str, *, evidence: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code, "detail": detail}
    if evidence is not None:
        row["evidence"] = evidence
    return row


async def _page_metrics(page: Page) -> Mapping[str, Any]:
    return await page.evaluate(
        """
        ({ selector, touchMin }) => {
          const root = document.documentElement;
          const body = document.body;
          const visible = (element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
          };
          const text = String(body?.innerText || '').replace(/\s+/g, ' ').trim();
          const interactives = [...document.querySelectorAll(selector)]
            .filter(visible)
            .map((element, index) => {
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              const label = String(
                element.getAttribute('aria-label') ||
                element.getAttribute('title') ||
                element.innerText ||
                element.getAttribute('value') ||
                element.getAttribute('href') ||
                element.tagName
              ).replace(/\s+/g, ' ').trim().slice(0, 160);
              return {
                index,
                tag: element.tagName.toLowerCase(),
                id: element.id || null,
                className: typeof element.className === 'string'
                  ? element.className.slice(0, 180) : null,
                role: element.getAttribute('role'),
                href: element.getAttribute('href'),
                label,
                width: Math.round(rect.width * 10) / 10,
                height: Math.round(rect.height * 10) / 10,
                position: style.position,
                tooSmall: rect.width + 0.1 < touchMin || rect.height + 0.1 < touchMin,
              };
            });
          const anchors = [...document.querySelectorAll('a[href]')]
            .filter(visible)
            .map((anchor) => ({
              href: anchor.href,
              text: String(anchor.innerText || anchor.getAttribute('aria-label') || '')
                .replace(/\s+/g, ' ').trim().slice(0, 200),
            }));
          const animated = [...document.querySelectorAll('body *')]
            .filter(visible)
            .map((element) => {
              const style = getComputedStyle(element);
              const parseTimes = (value) => String(value || '')
                .split(',')
                .map((part) => part.trim())
                .map((part) => part.endsWith('ms') ? Number.parseFloat(part) / 1000 : Number.parseFloat(part))
                .filter(Number.isFinite);
              const duration = Math.max(0, ...parseTimes(style.animationDuration), ...parseTimes(style.transitionDuration));
              return {
                tag: element.tagName.toLowerCase(),
                id: element.id || null,
                className: typeof element.className === 'string' ? element.className.slice(0, 160) : null,
                seconds: duration,
              };
            })
            .filter((item) => item.seconds > 0.1)
            .slice(0, 30);
          const overlays = [...document.querySelectorAll('body *')]
            .filter(visible)
            .map((element) => {
              const style = getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              const viewportArea = Math.max(1, innerWidth * innerHeight);
              return {
                tag: element.tagName.toLowerCase(),
                id: element.id || null,
                className: typeof element.className === 'string' ? element.className.slice(0, 160) : null,
                role: element.getAttribute('role'),
                position: style.position,
                areaRatio: (rect.width * rect.height) / viewportArea,
                pointerEvents: style.pointerEvents,
              };
            })
            .filter((item) => ['fixed', 'sticky'].includes(item.position) && item.areaRatio > 0.85 && item.pointerEvents !== 'none')
            .slice(0, 20);
          return {
            title: document.title,
            language: root.lang || null,
            bodyTextLength: text.length,
            bodyTextSample: text.slice(0, 800),
            h1Count: document.querySelectorAll('h1').length,
            mainCount: document.querySelectorAll('main,[role="main"]').length,
            viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
            geometry: {
              rootClientWidth: root.clientWidth,
              rootScrollWidth: root.scrollWidth,
              bodyClientWidth: body?.clientWidth || 0,
              bodyScrollWidth: body?.scrollWidth || 0,
              rootClientHeight: root.clientHeight,
              rootScrollHeight: root.scrollHeight,
            },
            publicExperienceV3: root.dataset.szlPublicExperienceV3 || null,
            publicExperienceMarkerPresent: root.outerHTML.includes('data-szl-public-experience-v3'),
            developerLinks: anchors.filter((item) => /\b(api|developer|docs?|source|github|build(?:\s+identity)?|json|schema)\b/i.test(`${item.text} ${item.href}`)).slice(0, 20),
            proofLinks: anchors.filter((item) => /\b(investor|proof|evidence|receipt|attestation|status|trust|governance)\b/i.test(`${item.text} ${item.href}`)).slice(0, 20),
            externalHttpLinks: anchors.filter((item) => item.href.startsWith('http://')).slice(0, 20),
            interactives,
            undersized: interactives.filter((item) => item.tooSmall).slice(0, 50),
            animated,
            overlays,
            media: {
              reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
              coarsePointer: matchMedia('(pointer: coarse)').matches,
              forcedColors: matchMedia('(forced-colors: active)').matches,
            },
          };
        }
        """,
        {"selector": INTERACTIVE_SELECTOR, "touchMin": TOUCH_MIN},
    )


async def _keyboard_probe(page: Page) -> Mapping[str, Any]:
    sequence: list[dict[str, Any]] = []
    for _ in range(24):
        await page.keyboard.press("Tab")
        active = await page.evaluate(
            """
            () => {
              const element = document.activeElement;
              if (!element || element === document.body || element === document.documentElement) {
                return { tag: null, id: null, label: null, focusVisible: false };
              }
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              return {
                tag: element.tagName.toLowerCase(),
                id: element.id || null,
                label: String(element.getAttribute('aria-label') || element.innerText || element.getAttribute('href') || '')
                  .replace(/\s+/g, ' ').trim().slice(0, 140),
                focusVisible: element.matches(':focus-visible'),
                inViewport: rect.bottom >= 0 && rect.top <= innerHeight && rect.right >= 0 && rect.left <= innerWidth,
                outlineStyle: style.outlineStyle,
                outlineWidth: style.outlineWidth,
              };
            }
            """
        )
        if active.get("tag") is not None:
            sequence.append(dict(active))
    unique = {
        (row.get("tag"), row.get("id"), row.get("label")) for row in sequence
    }
    return {
        "steps": len(sequence),
        "unique_focus_targets": len(unique),
        "focus_visible_steps": sum(bool(row.get("focusVisible")) for row in sequence),
        "offscreen_steps": sum(not bool(row.get("inViewport")) for row in sequence),
        "sequence": sequence,
    }


async def audit_case(
    browser: Browser,
    target: Mapping[str, Any],
    case: Case,
    output_dir: Path,
) -> dict[str, Any]:
    context: BrowserContext = await browser.new_context(
        viewport={"width": case.width, "height": case.height},
        user_agent=USER_AGENT,
        reduced_motion="reduce" if case.reduced_motion else "no-preference",
        color_scheme="dark",
        service_workers="block",
    )
    page = await context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    browser_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    page.on("pageerror", lambda error: browser_errors.append(str(error)[:500]))
    page.on(
        "console",
        lambda message: console_errors.append(message.text[:500])
        if message.type == "error"
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            {
                "url": request.url[:500],
                "failure": str(request.failure or "UNAVAILABLE")[:300],
            }
        ),
    )

    result: dict[str, Any] = {
        "target": target["id"],
        "requested_url": target["url"],
        "kind": target["kind"],
        "case": asdict(case),
        "effective_width": case.effective_width,
        "observed_at": utc_now(),
        "passed": False,
        "failures": [],
        "warnings": [],
    }
    try:
        response = await page.goto(
            str(target["url"]),
            wait_until="domcontentloaded",
            timeout=TIMEOUT_MS,
        )
        result["http_status"] = response.status if response else None
        result["final_url"] = page.url
        if response is None or response.status != 200:
            result["failures"].append(
                _failure(
                    "HTTP_NOT_200",
                    f"root returned {response.status if response else 'no response'}",
                )
            )
            return result

        await page.wait_for_timeout(1_200)
        if case.zoom != 1.0:
            await page.evaluate(
                "zoom => { document.documentElement.style.zoom = String(zoom); }",
                case.zoom,
            )
            await page.wait_for_timeout(350)

        metrics = dict(await _page_metrics(page))
        result["metrics"] = metrics
        result["browser_errors"] = browser_errors
        result["console_errors"] = console_errors
        result["failed_requests"] = failed_requests[:50]

        if not str(metrics.get("title") or "").strip():
            result["failures"].append(_failure("EMPTY_TITLE", "document title is empty"))
        if int(metrics.get("bodyTextLength") or 0) < 120:
            result["failures"].append(
                _failure("INSUFFICIENT_TEXT", "rendered page has less than 120 characters")
            )
        if int(metrics.get("h1Count") or 0) < 1:
            result["failures"].append(_failure("MISSING_H1", "no rendered h1"))
        if int(metrics.get("mainCount") or 0) < 1:
            result["failures"].append(_failure("MISSING_MAIN", "no main landmark"))
        if not str(metrics.get("language") or "").strip():
            result["failures"].append(_failure("MISSING_LANGUAGE", "html lang is absent"))

        geometry = metrics.get("geometry") or {}
        overflow = max(
            float(geometry.get("rootScrollWidth") or 0)
            - float(geometry.get("rootClientWidth") or 0),
            float(geometry.get("bodyScrollWidth") or 0)
            - float(geometry.get("bodyClientWidth") or 0),
        )
        result["horizontal_overflow_px"] = round(overflow, 1)
        if overflow > OVERFLOW_TOLERANCE:
            result["failures"].append(
                _failure(
                    "DOCUMENT_HORIZONTAL_OVERFLOW",
                    f"document is {overflow:.1f}px wider than its client width",
                    evidence=geometry,
                )
            )

        page_html = await page.content()
        for marker in target.get("required_markers") or ():
            if marker not in page_html:
                result["failures"].append(
                    _failure("MISSING_REQUIRED_MARKER", f"missing {marker}")
                )

        undersized = metrics.get("undersized") or []
        # At desktop, inline text links may use the WCAG spacing exception. At
        # touch/coarse and reflow geometries, all rendered controls must expose a
        # direct 44px hit box because spacing is not independently attested here.
        if undersized and (case.coarse_pointer or case.zoom > 1.0 or case.width <= 768):
            result["failures"].append(
                _failure(
                    "UNDERSIZED_INTERACTIVE_TARGETS",
                    f"{len(undersized)} visible targets are smaller than {TOUCH_MIN}px",
                    evidence=undersized,
                )
            )
        elif undersized:
            result["warnings"].append(
                _failure(
                    "DESKTOP_TARGET_SPACING_NOT_ATTESTED",
                    f"{len(undersized)} desktop targets use less than a direct {TOUCH_MIN}px hit box",
                    evidence=undersized,
                )
            )

        overlays = metrics.get("overlays") or []
        if overlays:
            result["failures"].append(
                _failure(
                    "INTERACTIVE_VIEWPORT_OVERLAY",
                    "fixed or sticky interactive chrome covers more than 85% of the viewport",
                    evidence=overlays,
                )
            )

        if not metrics.get("developerLinks"):
            result["failures"].append(
                _failure(
                    "DEVELOPER_PATH_NOT_DISCOVERABLE",
                    "no visible API, source, build, docs, schema, or GitHub link",
                )
            )
        if not metrics.get("proofLinks"):
            result["failures"].append(
                _failure(
                    "INVESTOR_PROOF_PATH_NOT_DISCOVERABLE",
                    "no visible proof, evidence, receipt, status, trust, or governance link",
                )
            )
        if metrics.get("externalHttpLinks"):
            result["failures"].append(
                _failure(
                    "INSECURE_EXTERNAL_LINK",
                    "rendered page contains an http:// link",
                    evidence=metrics["externalHttpLinks"],
                )
            )

        if case.reduced_motion:
            if not (metrics.get("media") or {}).get("reducedMotion"):
                result["failures"].append(
                    _failure("REDUCED_MOTION_NOT_EMULATED", "browser media state mismatch")
                )
            if metrics.get("animated"):
                result["failures"].append(
                    _failure(
                        "LONG_MOTION_WITH_REDUCED_MOTION",
                        "visible animation or transition exceeds 100ms",
                        evidence=metrics["animated"],
                    )
                )

        if case.name in {"phone-375", "desktop-1440"}:
            keyboard = dict(await _keyboard_probe(page))
            result["keyboard"] = keyboard
            if keyboard["unique_focus_targets"] < 2:
                result["failures"].append(
                    _failure("KEYBOARD_PATH_MISSING", "fewer than two unique focus targets")
                )
            if keyboard["focus_visible_steps"] < 1:
                result["failures"].append(
                    _failure("FOCUS_NOT_VISIBLE", "no :focus-visible state observed")
                )
            if keyboard["offscreen_steps"] > 2:
                result["failures"].append(
                    _failure(
                        "KEYBOARD_FOCUS_OFFSCREEN",
                        f"{keyboard['offscreen_steps']} tab stops remained outside the viewport",
                    )
                )

        if browser_errors:
            result["failures"].append(
                _failure("UNCAUGHT_PAGE_ERROR", browser_errors[0], evidence=browser_errors)
            )
        if console_errors:
            result["warnings"].append(
                _failure("CONSOLE_ERRORS", console_errors[0], evidence=console_errors[:20])
            )
        if failed_requests:
            result["warnings"].append(
                _failure(
                    "FAILED_SUBRESOURCE_REQUESTS",
                    f"{len(failed_requests)} requests failed",
                    evidence=failed_requests[:20],
                )
            )

        screenshot_name = f"{safe_name(str(target['id']))}--{safe_name(case.name)}.png"
        screenshot_path = output_dir / "screenshots" / screenshot_name
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_bytes = await page.screenshot(
            path=str(screenshot_path),
            full_page=True,
            animations="disabled",
        )
        result["screenshot"] = {
            "file": str(screenshot_path.relative_to(output_dir)),
            "bytes": len(screenshot_bytes),
            "sha256": sha256_bytes(screenshot_bytes),
        }
        if len(screenshot_bytes) > MAX_PAGE_BYTES:
            result["warnings"].append(
                _failure(
                    "LARGE_SCREENSHOT",
                    f"full-page PNG is {len(screenshot_bytes)} bytes",
                )
            )

        result["passed"] = not result["failures"]
        return result
    except Exception as exc:  # each target/case remains independently visible
        result["failures"].append(
            _failure("AUDIT_EXCEPTION", f"{type(exc).__name__}: {exc}")
        )
        result["browser_errors"] = browser_errors
        result["console_errors"] = console_errors
        result["failed_requests"] = failed_requests[:50]
        return result
    finally:
        await context.close()


async def run_audit(
    targets: Sequence[Mapping[str, Any]],
    cases: Sequence[Case],
    output_dir: Path,
    concurrency: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)

        async def bounded(target: Mapping[str, Any], case: Case) -> dict[str, Any]:
            async with semaphore:
                return await audit_case(browser, target, case, output_dir)

        results = await asyncio.gather(
            *(bounded(target, case) for target in targets for case in cases)
        )
        await browser.close()

    target_summary: dict[str, Any] = {}
    for target in targets:
        target_results = [row for row in results if row["target"] == target["id"]]
        target_summary[str(target["id"])] = {
            "passed": all(row["passed"] for row in target_results),
            "cases": len(target_results),
            "failed_cases": sum(not row["passed"] for row in target_results),
            "failure_codes": sorted(
                {
                    failure["code"]
                    for row in target_results
                    for failure in row.get("failures") or []
                }
            ),
        }

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "auditor": {
            "user_agent": USER_AGENT,
            "timeout_ms": TIMEOUT_MS,
            "touch_min_px": TOUCH_MIN,
            "overflow_tolerance_px": OVERFLOW_TOLERANCE,
            "read_only": True,
            "provider_mutations": False,
        },
        "summary": {
            "passed": all(row["passed"] for row in results),
            "targets": len(targets),
            "cases": len(results),
            "passed_cases": sum(row["passed"] for row in results),
            "failed_cases": sum(not row["passed"] for row in results),
        },
        "targets": target_summary,
        "results": results,
    }
    canonical = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    report["proof_chain_sha256"] = sha256_bytes(canonical)
    return report


def write_markdown(report: Mapping[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# SZL Public Experience v4 — Audience Readiness",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Status:** **{'PASS' if summary['passed'] else 'FAIL'}**",
        f"**Proof Chain:** `{report['proof_chain_sha256']}`",
        "",
        "| Target | Result | Failed cases | Failure codes |",
        "|---|---:|---:|---|",
    ]
    for target, row in report["targets"].items():
        lines.append(
            f"| {target} | **{'PASS' if row['passed'] else 'FAIL'}** | "
            f"{row['failed_cases']}/{row['cases']} | "
            f"{', '.join(row['failure_codes']) or '—'} |"
        )
    lines += [
        "",
        "## Acceptance boundary",
        "",
        "A target passes only when all configured cases return HTTP 200, render a title, language, h1 and main landmark, contain document overflow, expose usable touch and keyboard paths, respect reduced motion, avoid blocking overlays, and make both developer and investor/proof evidence discoverable. Provider failure remains a failure or warning; it is never converted into a green source claim.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def select_by_name(values: Iterable[Any], names: set[str], key: str) -> list[Any]:
    if not names:
        return list(values)
    return [value for value in values if str(value[key] if isinstance(value, Mapping) else value.name) in names]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="public-experience-v4")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--soft", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = select_by_name(TARGETS, set(args.target), "id")
    cases = select_by_name(CASES, set(args.case), "name")
    if not targets or not cases:
        raise SystemExit("target/case selection is empty")
    output_dir = Path(args.output_dir)
    report = asyncio.run(
        run_audit(targets, cases, output_dir, max(1, min(args.concurrency, 6)))
    )
    json_path = output_dir / "public-experience-v4.json"
    md_path = output_dir / "public-experience-v4.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, md_path)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["passed"] or args.soft else 1


if __name__ == "__main__":
    sys.exit(main())
