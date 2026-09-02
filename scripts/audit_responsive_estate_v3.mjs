#!/usr/bin/env node
/**
 * Browser-level responsive audit for every public SZLHOLDINGS Space plus the
 * product front door, canonical runtime, and independent proof origin.
 */
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const VIEWPORTS = [
  { name: "compact-phone", width: 320, height: 568 },
  { name: "modern-phone", width: 375, height: 812 },
  { name: "phone-landscape", width: 812, height: 375 },
  { name: "desktop", width: 1440, height: 900 },
  { name: "theatre", width: 2560, height: 1440 },
];

const CORE_VIEWPORTS = [
  ...VIEWPORTS,
  { name: "large-phone", width: 430, height: 932 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "full-hd", width: 1920, height: 1080 },
  { name: "ultrawide", width: 3440, height: 1440 },
];

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const jsonOut = arg("--json-out", "reports/responsive-estate-v3.json");
const htmlOut = arg("--html-out", "reports/responsive-estate-v3.html");
const evidenceDir = arg("--evidence-dir", "reports/responsive-estate-v3-evidence");
const concurrency = Math.max(1, Math.min(6, Number(arg("--concurrency", "3")) || 3));

function spaceUrl(repoId) {
  const [owner, name] = repoId.split("/", 2);
  const normalized = `${owner}-${name}`.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-");
  return `https://${normalized}.hf.space/`;
}

async function inventory() {
  const response = await fetch("https://huggingface.co/api/spaces?author=SZLHOLDINGS&limit=100&full=true", {
    headers: { "user-agent": "szl-responsive-estate-v3/1.0" },
  });
  if (!response.ok) throw new Error(`Hugging Face inventory HTTP ${response.status}`);
  const spaces = await response.json();
  const core = [
    { id: "product-front-door", url: "https://a-11-oy.com/", kind: "core", role: "static-product-front-door" },
    { id: "proof-origin", url: "https://a11oy.net/", kind: "core", role: "independent-proof-origin" },
    { id: "canonical-runtime", url: "https://szlholdings-a11oy.hf.space/", kind: "core", role: "live-application-runtime" },
  ];
  const seen = new Set(core.map((item) => item.url));
  const rows = [...core];
  for (const item of spaces) {
    if (!item?.id || !String(item.id).startsWith("SZLHOLDINGS/")) continue;
    const url = spaceUrl(String(item.id));
    if (seen.has(url)) continue;
    seen.add(url);
    rows.push({
      id: String(item.id),
      url,
      kind: "space",
      sdk: item.sdk ?? null,
      stage: item.runtime?.stage ?? null,
      sha: item.sha ?? null,
      role: "hugging-face-space",
    });
  }
  return rows;
}

function safeName(value) {
  return value.toLowerCase().replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 100);
}

async function inspectPage(page) {
  return page.evaluate(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const rectData = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        id: element.id || null,
        className: typeof element.className === "string" ? element.className.slice(0, 140) : null,
        text: (element.getAttribute("aria-label") || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 100),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    };

    const vw = window.innerWidth;
    const docWidth = Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0);
    const targetSelector = [
      "button",
      "input:not([type='hidden']):not([type='checkbox']):not([type='radio'])",
      "select",
      "textarea",
      "summary",
      "[role='button']",
      "[role='tab']",
      "nav a",
      "a.button",
      "a.btn",
      "[data-testid='stButton'] button",
      ".gr-button",
    ].join(",");
    const targets = [...document.querySelectorAll(targetSelector)].filter((element) => visible(element) && !element.matches(":disabled,[aria-disabled='true']"));
    const undersizedTargets = targets
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width < 43.5 || rect.height < 43.5;
      })
      .slice(0, 30)
      .map(rectData);

    const candidates = [...document.querySelectorAll("body *")].filter(visible);
    const offscreen = candidates
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        if (rect.width <= 1 || rect.height <= 1) return false;
        if (rect.right <= vw + 2 && rect.left >= -2) return false;
        const style = getComputedStyle(element);
        const selfScrollable = ["auto", "scroll"].includes(style.overflowX);
        if (selfScrollable) return false;
        let parent = element.parentElement;
        while (parent && parent !== document.body) {
          const parentStyle = getComputedStyle(parent);
          if (["auto", "scroll"].includes(parentStyle.overflowX)) return false;
          parent = parent.parentElement;
        }
        return true;
      })
      .slice(0, 30)
      .map(rectData);

    const fixedOversize = candidates
      .filter((element) => {
        const style = getComputedStyle(element);
        if (!["fixed", "sticky"].includes(style.position)) return false;
        const rect = element.getBoundingClientRect();
        return rect.width > vw + 2 || rect.left < -2 || rect.right > vw + 2;
      })
      .slice(0, 20)
      .map(rectData);

    const clippedText = candidates
      .filter((element) => {
        const style = getComputedStyle(element);
        if (!element.textContent?.trim()) return false;
        return element.scrollWidth > element.clientWidth + 2 && style.overflowX === "hidden" && style.whiteSpace === "nowrap";
      })
      .slice(0, 20)
      .map(rectData);

    const computedBody = document.body ? getComputedStyle(document.body) : null;
    const animationCount = candidates.filter((element) => {
      const style = getComputedStyle(element);
      return style.animationName && style.animationName !== "none";
    }).length;
    const markerCount = document.querySelectorAll([
      "[data-szl-space]",
      "[data-szl-holo]",
      "[data-szl-hologram-v2]",
      "[data-szl-viewport]",
      "[data-szl-responsive-apex-v3]",
      "link[href*='szl-responsive']",
      "link[href*='szl-holo']",
    ].join(",")).length;

    return {
      url: location.href,
      title: document.title,
      viewportMeta: Boolean(document.querySelector('meta[name="viewport"]')),
      viewportWidth: vw,
      documentWidth: docWidth,
      horizontalOverflow: Math.max(0, Math.round(docWidth - vw)),
      bodyRendered: Boolean(document.body && document.body.innerText.trim().length >= 20),
      bodyFontSize: computedBody ? Number.parseFloat(computedBody.fontSize) : null,
      targetCount: targets.length,
      undersizedTargets,
      offscreen,
      fixedOversize,
      clippedText,
      headingCount: document.querySelectorAll("h1,h2,h3").length,
      navigationLinkCount: document.querySelectorAll("nav a").length,
      formControlCount: document.querySelectorAll("button,input,select,textarea").length,
      canvasCount: document.querySelectorAll("canvas").length,
      animationCount,
      responsiveMarkerCount: markerCount,
      reducedMotionQuerySupported: typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").media !== "not all",
    };
  });
}

async function auditSurface(browser, surface) {
  const rows = [];
  const errors = [];
  const pageErrors = [];
  const consoleErrors = [];
  const viewports = surface.kind === "core" ? CORE_VIEWPORTS : VIEWPORTS;
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: "no-preference",
      colorScheme: "dark",
      locale: "en-US",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => pageErrors.push({ viewport: viewport.name, message: String(error.message || error).slice(0, 500) }));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push({ viewport: viewport.name, message: message.text().slice(0, 500) });
    });
    let response = null;
    try {
      response = await page.goto(surface.url, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForTimeout(surface.kind === "core" ? 1800 : 2400);
      const measurement = await inspectPage(page);
      const result = {
        ...viewport,
        httpStatus: response?.status() ?? null,
        finalUrl: page.url(),
        ...measurement,
      };
      const failed =
        !result.bodyRendered ||
        !result.viewportMeta ||
        result.horizontalOverflow > 1 ||
        result.undersizedTargets.length > 0 ||
        result.offscreen.length > 0 ||
        result.fixedOversize.length > 0 ||
        (result.httpStatus !== null && result.httpStatus >= 400);
      result.pass = !failed;
      rows.push(result);
      if (failed && (viewport.name === "compact-phone" || viewport.name === "theatre")) {
        const target = path.join(evidenceDir, `${safeName(surface.id)}-${viewport.name}.png`);
        await fs.mkdir(path.dirname(target), { recursive: true });
        await page.screenshot({ path: target, fullPage: true });
      }
    } catch (error) {
      errors.push({ viewport: viewport.name, message: String(error?.message || error).slice(0, 1000) });
      rows.push({ ...viewport, httpStatus: response?.status() ?? null, finalUrl: page.url(), pass: false, error: String(error?.message || error).slice(0, 1000) });
    } finally {
      await context.close();
    }
  }
  return {
    ...surface,
    pass: rows.every((row) => row.pass),
    viewports: rows,
    errors,
    pageErrors,
    consoleErrors,
  };
}

async function pooled(items, worker, limit) {
  const output = new Array(items.length);
  let cursor = 0;
  async function run() {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      output[index] = await worker(items[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => run()));
  return output;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function htmlReport(report) {
  const rows = report.surfaces.map((surface) => {
    const failing = surface.viewports.filter((row) => !row.pass);
    const detail = failing.map((row) => `${row.name}: overflow=${row.horizontalOverflow ?? "?"}, small=${row.undersizedTargets?.length ?? "?"}, offscreen=${row.offscreen?.length ?? "?"}, HTTP=${row.httpStatus ?? "?"}`).join("<br>");
    return `<tr><td>${escapeHtml(surface.id)}</td><td>${escapeHtml(surface.sdk || surface.role || "")}</td><td class="${surface.pass ? "pass" : "fail"}">${surface.pass ? "PASS" : "FAIL"}</td><td>${escapeHtml(surface.stage || "")}</td><td>${detail || "All audited viewports passed"}</td></tr>`;
  }).join("\n");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SZL Responsive Estate v3</title><style>
body{margin:0;background:#080c14;color:#eef4fb;font:16px/1.5 system-ui,sans-serif}main{width:min(100% - 2rem,1200px);margin:auto;padding:3rem 0}h1{font-size:clamp(2rem,5vw,4.5rem)}table{width:100%;border-collapse:collapse}th,td{padding:.8rem;border-bottom:1px solid #2a3344;text-align:left;vertical-align:top}.pass{color:#75e0bd}.fail{color:#ff9c8f}code{overflow-wrap:anywhere}@media(max-width:700px){table,tbody,tr,td{display:block}thead{position:absolute;clip-path:inset(50%)}tr{padding:1rem 0}td{border:0;padding:.35rem 0}}
</style></head><body><main><p>MEASURED browser audit · ${escapeHtml(report.observedAt)}</p><h1>SZL Responsive Estate v3</h1><p>${report.passCount}/${report.surfaceCount} public surfaces passed every assigned viewport.</p><table><thead><tr><th>Surface</th><th>SDK / role</th><th>Status</th><th>Runtime stage</th><th>Failures</th></tr></thead><tbody>${rows}</tbody></table></main></body></html>`;
}

async function main() {
  await fs.mkdir(path.dirname(jsonOut), { recursive: true });
  await fs.mkdir(path.dirname(htmlOut), { recursive: true });
  await fs.mkdir(evidenceDir, { recursive: true });
  const surfaces = await inventory();
  const browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage"] });
  let results;
  try {
    results = await pooled(surfaces, (surface) => auditSurface(browser, surface), concurrency);
  } finally {
    await browser.close();
  }
  const report = {
    schema: "szl.responsive-browser-audit/v3",
    observedAt: new Date().toISOString(),
    viewportContract: VIEWPORTS,
    coreViewportContract: CORE_VIEWPORTS,
    surfaceCount: results.length,
    passCount: results.filter((surface) => surface.pass).length,
    failCount: results.filter((surface) => !surface.pass).length,
    surfaces: results,
  };
  await fs.writeFile(jsonOut, JSON.stringify(report, null, 2) + "\n", "utf8");
  await fs.writeFile(htmlOut, htmlReport(report), "utf8");
  console.log(JSON.stringify({ surfaceCount: report.surfaceCount, passCount: report.passCount, failCount: report.failCount }, null, 2));
  if (report.failCount > 0) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
