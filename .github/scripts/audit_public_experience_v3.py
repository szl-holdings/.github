#!/usr/bin/env python3
"""Browser-verify the SZL public estate from phone through theatre displays.

The auditor measures the two canonical public origins and every public
SZLHOLDINGS Hugging Face Space. It performs GET-only browser navigation, records
exact failures, saves screenshots only for failed cases, and never changes
source, runtime configuration, hardware, visibility, secrets, models, or data.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "szl.public-experience-audit/v3"
HF_API = "https://huggingface.co/api/spaces"
ORG = "SZLHOLDINGS"
USER_AGENT = "SZL-Public-Experience-Audit/3.0"


@dataclasses.dataclass(frozen=True)
class ViewportCase:
    name: str
    width: int
    height: int
    touch: bool = False
    reduced_motion: str = "no-preference"
    zoom: float = 1.0


VIEWPORTS: tuple[ViewportCase, ...] = (
    ViewportCase("phone-320", 320, 800, True),
    ViewportCase("phone-375", 375, 812, True),
    ViewportCase("tablet-768", 768, 1024, True),
    ViewportCase("desktop-1024", 1024, 768),
    ViewportCase("desktop-1440", 1440, 900),
    ViewportCase("theatre-2560", 2560, 1440),
    ViewportCase("ultrawide-3440", 3440, 1440),
    ViewportCase("reduced-motion-375", 375, 812, True, "reduce"),
    ViewportCase("zoom-200", 1280, 900, False, "no-preference", 2.0),
    ViewportCase("zoom-400", 1280, 900, False, "no-preference", 4.0),
)


@dataclasses.dataclass(frozen=True)
class Target:
    name: str
    role: str
    candidates: tuple[str, ...]
    require_v3: bool
    sdk: str = ""
    stage: str = ""


@dataclasses.dataclass
class CaseResult:
    target: str
    role: str
    case: str
    requested_url: str
    final_url: str | None = None
    http_status: int | None = None
    title: str = ""
    viewport_width: int = 0
    viewport_height: int = 0
    scroll_width: int = 0
    overflow_px: int = 0
    text_characters: int = 0
    main_landmark: bool = False
    v3_marker: bool = False
    interactive_count: int = 0
    small_target_count: int = 0
    small_targets: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    blocking_overlays: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    page_errors: list[str] = dataclasses.field(default_factory=list)
    console_errors: list[str] = dataclasses.field(default_factory=list)
    failures: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)
    screenshot: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["passed"] = self.passed
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def static_host(slug: str) -> str:
    return f"https://szlholdings-{normalize_slug(slug)}.static.hf.space/"


def dynamic_host(slug: str) -> str:
    return f"https://szlholdings-{normalize_slug(slug)}.hf.space/"


def space_candidates(slug: str, sdk: str) -> tuple[str, ...]:
    dynamic = dynamic_host(slug)
    if sdk.strip().lower() == "static":
        return (static_host(slug), dynamic)
    return (dynamic,)


def _request_json(url: str, *, timeout: int = 45) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def discover_public_spaces(*, max_spaces: int = 100) -> list[Target]:
    query = urllib.parse.urlencode(
        {"author": ORG, "limit": max(1, min(max_spaces, 100)), "full": "true"}
    )
    values = _request_json(f"{HF_API}?{query}")
    if not isinstance(values, list):
        raise RuntimeError("Hugging Face Space inventory was not a list")
    targets: list[Target] = []
    for row in values:
        if not isinstance(row, Mapping) or row.get("private") is True:
            continue
        repo_id = str(row.get("id") or "")
        if not repo_id.lower().startswith(ORG.lower() + "/"):
            continue
        slug = repo_id.split("/", 1)[1]
        sdk = str(row.get("sdk") or ((row.get("cardData") or {}).get("sdk") if isinstance(row.get("cardData"), Mapping) else "") or "")
        runtime = row.get("runtime") if isinstance(row.get("runtime"), Mapping) else {}
        stage = str((runtime or {}).get("stage") or row.get("stage") or "UNAVAILABLE")
        targets.append(
            Target(
                name=repo_id,
                role="hugging-face-space",
                candidates=space_candidates(slug, sdk),
                require_v3=True,
                sdk=sdk,
                stage=stage,
            )
        )
    return sorted(targets, key=lambda target: target.name.lower())


def canonical_targets() -> list[Target]:
    return [
        Target(
            name="a-11-oy.com",
            role="static-product-front-door",
            candidates=("https://a-11-oy.com/",),
            require_v3=False,
        ),
        Target(
            name="a11oy.net",
            role="independent-proof-origin",
            candidates=("https://a11oy.net/",),
            require_v3=False,
        ),
    ]


def sanitize(value: str) -> str:
    rendered = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return rendered[:120] or "surface"


def classify_findings(
    metrics: Mapping[str, Any],
    *,
    touch: bool,
    require_v3: bool,
    page_errors: Sequence[str] = (),
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    status = metrics.get("http_status")
    if status != 200:
        failures.append(f"root returned HTTP {status if status is not None else 'UNAVAILABLE'}")
    if not str(metrics.get("title") or "").strip():
        failures.append("document title is empty")
    if int(metrics.get("text_characters") or 0) < 12:
        failures.append("surface has less than 12 meaningful text characters")
    overflow = int(metrics.get("overflow_px") or 0)
    if overflow > 2:
        failures.append(f"document-level horizontal overflow is {overflow}px")
    if require_v3 and not bool(metrics.get("v3_marker")):
        failures.append("Public Experience v3 marker is absent")
    small = int(metrics.get("small_target_count") or 0)
    if touch and small:
        failures.append(f"{small} visible touch target(s) are smaller than 44×44px")
    overlays = metrics.get("blocking_overlays") or []
    if overlays:
        failures.append(f"{len(overlays)} interactive fixed overlay(s) cover more than 88% of the viewport")
    if page_errors:
        failures.append(f"{len(page_errors)} uncaught page error(s)")
    if not bool(metrics.get("main_landmark")):
        warnings.append("no main landmark was detected")
    console_errors = metrics.get("console_errors") or []
    if console_errors:
        warnings.append(f"{len(console_errors)} console error message(s) were observed")
    return failures, warnings


MEASURE_SCRIPT = r"""
() => {
  const root = document.documentElement;
  const body = document.body;
  const vw = Math.max(1, root.clientWidth || window.innerWidth || 1);
  const vh = Math.max(1, window.innerHeight || root.clientHeight || 1);
  const scrollWidth = Math.max(root.scrollWidth, body ? body.scrollWidth : 0);
  const visible = (node, style, rect) => {
    if (!node || !style || !rect) return false;
    if (node.closest('[aria-hidden="true"]')) return false;
    if (node.hasAttribute('disabled')) return false;
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      Number(style.opacity || 1) > 0 && style.pointerEvents !== 'none' &&
      rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 &&
      rect.top < vh && rect.left < vw;
  };
  const focusable = Array.from(document.querySelectorAll(
    'a[href],button,input:not([type="hidden"]),select,textarea,summary,' +
    '[role="button"],[tabindex]:not([tabindex="-1"])'
  ));
  const smallTargets = [];
  let interactiveCount = 0;
  for (const node of focusable) {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    if (!visible(node, style, rect)) continue;
    interactiveCount += 1;
    const inlineProseLink = node.tagName === 'A' && style.display === 'inline' &&
      Boolean(node.closest('p,li,dd,dt,figcaption,blockquote'));
    if (!inlineProseLink && (rect.width + 0.5 < 44 || rect.height + 0.5 < 44)) {
      smallTargets.push({
        tag: node.tagName.toLowerCase(),
        text: String(node.getAttribute('aria-label') || node.textContent || '').trim().slice(0, 80),
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10
      });
    }
  }
  const blockingOverlays = [];
  for (const node of Array.from(document.querySelectorAll('body *'))) {
    const style = getComputedStyle(node);
    if (!['fixed', 'sticky'].includes(style.position) || style.pointerEvents === 'none') continue;
    const rect = node.getBoundingClientRect();
    if (!visible(node, style, rect)) continue;
    const coverage = Math.max(0, rect.width) * Math.max(0, rect.height) / (vw * vh);
    if (coverage > 0.88 && !node.matches('dialog,[role="dialog"],[aria-modal="true"]')) {
      blockingOverlays.push({
        tag: node.tagName.toLowerCase(),
        id: node.id || '',
        className: typeof node.className === 'string' ? node.className.slice(0, 100) : '',
        coverage: Math.round(coverage * 1000) / 1000
      });
      if (blockingOverlays.length >= 5) break;
    }
  }
  const text = String(body ? body.innerText : '').replace(/\s+/g, ' ').trim();
  return {
    title: String(document.title || '').trim(),
    viewport_width: vw,
    viewport_height: vh,
    scroll_width: scrollWidth,
    overflow_px: Math.max(0, Math.round(scrollWidth - vw)),
    text_characters: text.length,
    main_landmark: Boolean(document.querySelector('main,[role="main"],.gradio-container,[data-testid="stAppViewContainer"]')),
    v3_marker: root.dataset.szlPublicExperienceV3 === 'true',
    interactive_count: interactiveCount,
    small_target_count: smallTargets.length,
    small_targets: smallTargets.slice(0, 12),
    blocking_overlays: blockingOverlays
  };
}
"""


async def audit_case(
    browser: Any,
    target: Target,
    case: ViewportCase,
    *,
    timeout_ms: int,
    screenshots_dir: Path,
    semaphore: asyncio.Semaphore,
) -> CaseResult:
    async with semaphore:
        result = CaseResult(
            target=target.name,
            role=target.role,
            case=case.name,
            requested_url=target.candidates[0],
        )
        context = await browser.new_context(
            viewport={"width": case.width, "height": case.height},
            device_scale_factor=1,
            is_mobile=case.touch and case.width < 768,
            has_touch=case.touch,
            reduced_motion=case.reduced_motion,
            color_scheme="dark",
        )
        page = await context.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)[:500]))
        page.on(
            "console",
            lambda message: console_errors.append(message.text[:500])
            if message.type == "error"
            else None,
        )
        response = None
        navigation_error = None
        for candidate in target.candidates:
            result.requested_url = candidate
            try:
                response = await page.goto(
                    candidate,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                if response is not None and response.status == 200:
                    break
            except Exception as exc:  # Playwright exposes several transport subclasses.
                navigation_error = str(exc)[:800]
                response = None
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
        except Exception:
            pass
        await page.wait_for_timeout(900)
        if case.zoom != 1.0:
            await page.evaluate(
                "value => { document.documentElement.style.zoom = String(value); }",
                case.zoom,
            )
            await page.wait_for_timeout(250)

        result.final_url = page.url or None
        result.http_status = response.status if response is not None else None
        metrics: dict[str, Any]
        try:
            metrics = await page.evaluate(MEASURE_SCRIPT)
        except Exception as exc:
            metrics = {
                "title": "",
                "viewport_width": case.width,
                "viewport_height": case.height,
                "scroll_width": 0,
                "overflow_px": 0,
                "text_characters": 0,
                "main_landmark": False,
                "v3_marker": False,
                "interactive_count": 0,
                "small_target_count": 0,
                "small_targets": [],
                "blocking_overlays": [],
            }
            page_errors.append(f"measurement failed: {exc}"[:500])
        metrics["http_status"] = result.http_status
        metrics["console_errors"] = console_errors
        if navigation_error and result.http_status != 200:
            page_errors.append("navigation: " + navigation_error)

        result.title = str(metrics.get("title") or "")
        result.viewport_width = int(metrics.get("viewport_width") or case.width)
        result.viewport_height = int(metrics.get("viewport_height") or case.height)
        result.scroll_width = int(metrics.get("scroll_width") or 0)
        result.overflow_px = int(metrics.get("overflow_px") or 0)
        result.text_characters = int(metrics.get("text_characters") or 0)
        result.main_landmark = bool(metrics.get("main_landmark"))
        result.v3_marker = bool(metrics.get("v3_marker"))
        result.interactive_count = int(metrics.get("interactive_count") or 0)
        result.small_target_count = int(metrics.get("small_target_count") or 0)
        result.small_targets = list(metrics.get("small_targets") or [])
        result.blocking_overlays = list(metrics.get("blocking_overlays") or [])
        result.page_errors = page_errors
        result.console_errors = console_errors
        result.failures, result.warnings = classify_findings(
            metrics,
            touch=case.touch,
            require_v3=target.require_v3,
            page_errors=page_errors,
        )

        if result.failures:
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            screenshot = screenshots_dir / f"{sanitize(target.name)}--{sanitize(case.name)}.png"
            try:
                await page.screenshot(path=str(screenshot), full_page=False)
                result.screenshot = screenshot.as_posix()
            except Exception as exc:
                result.warnings.append(f"failure screenshot unavailable: {exc}"[:500])
        await context.close()
        return result


def build_report(targets: Sequence[Target], results: Sequence[CaseResult]) -> dict[str, Any]:
    failed = [row for row in results if not row.passed]
    target_failures = sorted({row.target for row in failed})
    return {
        "schema": SCHEMA,
        "observed_at": utc_now(),
        "organization": ORG,
        "token_value_recorded": False,
        "targets": len(targets),
        "cases": len(results),
        "summary": {
            "passed_cases": len(results) - len(failed),
            "failed_cases": len(failed),
            "passing_targets": len(targets) - len(target_failures),
            "failing_targets": len(target_failures),
            "failing_target_names": target_failures,
        },
        "target_inventory": [dataclasses.asdict(target) for target in targets],
        "results": [row.as_dict() for row in results],
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# SZL Public Experience v3 live audit",
        "",
        f"Observed: `{report.get('observed_at')}`",
        "",
        f"- Targets: **{report.get('targets', 0)}**",
        f"- Browser cases: **{report.get('cases', 0)}**",
        f"- Passing cases: **{summary.get('passed_cases', 0)}**",
        f"- Failed cases: **{summary.get('failed_cases', 0)}**",
        f"- Fully passing targets: **{summary.get('passing_targets', 0)}**",
        f"- Targets with exceptions: **{summary.get('failing_targets', 0)}**",
        "",
    ]
    failures = [row for row in report.get("results", []) if not row.get("passed")]
    if failures:
        lines.extend(("## Exact exceptions", ""))
        for row in failures:
            lines.append(
                f"- **{row.get('target')} · {row.get('case')}** — "
                + "; ".join(row.get("failures") or ["unknown failure"])
            )
    else:
        lines.extend(("## Result", "", "Every measured case passed.", ""))
    lines.extend(
        (
            "## Truth boundary",
            "",
            "This receipt proves only the GET-only browser measurements recorded above. "
            "It does not prove model quality, data freshness, receipt truth, source parity, "
            "or availability outside the observation window.",
            "",
        )
    )
    return "\n".join(lines)


async def run_audit(args: argparse.Namespace) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("playwright is required for live audit mode") from exc

    targets = canonical_targets()
    if args.include_spaces:
        targets.extend(discover_public_spaces(max_spaces=args.max_spaces))
    if args.target_regex:
        pattern = re.compile(args.target_regex, re.IGNORECASE)
        targets = [target for target in targets if pattern.search(target.name)]
    if not targets:
        raise SystemExit("no public targets were selected")

    screenshots_dir = Path(args.screenshots_dir)
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        tasks = [
            audit_case(
                browser,
                target,
                case,
                timeout_ms=args.timeout_ms,
                screenshots_dir=screenshots_dir,
                semaphore=semaphore,
            )
            for target in targets
            for case in VIEWPORTS
        ]
        results = await asyncio.gather(*tasks)
        await browser.close()

    report = build_report(targets, results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["failed_cases"] == 0 else 1


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output", default="reports/public-experience-v3.json")
    value.add_argument("--markdown", default="reports/public-experience-v3.md")
    value.add_argument("--screenshots-dir", default="reports/public-experience-v3-screenshots")
    value.add_argument("--include-spaces", action=argparse.BooleanOptionalAction, default=True)
    value.add_argument("--max-spaces", type=int, default=100)
    value.add_argument("--target-regex", default="")
    value.add_argument("--timeout-ms", type=int, default=30000)
    value.add_argument("--concurrency", type=int, default=6)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return asyncio.run(run_audit(args))


if __name__ == "__main__":
    raise SystemExit(main())
