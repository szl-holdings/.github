#!/usr/bin/env node
/**
 * Convert the raw Responsive Estate v3 browser probe into an actionable v3.1
 * release verdict.
 *
 * The v3 probe intentionally records broad geometry. This normalizer prevents
 * decorative holographic layers and screen-reader-only labels from being
 * treated as product failures while preserving real overflow, unreachable
 * runtimes, undersized controls, and offscreen actionable content as blockers.
 */
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {
  classifyMeasurement,
  surfaceDisposition,
} from "./responsive_audit_policy_v31.mjs";

const DECORATIVE_CLASS = /(?:^|[\s_-])(spectral|hologram|holo|aurora|glow|backdrop|background|noise|particle|beam|scanline|motif|decoration|ornament|ambient|orb)(?:$|[\s_-])/i;
const ASSISTIVE_CLASS = /(?:^|[\s_-])(sr-only|screen-reader|visually-hidden|a11y-hidden)(?:$|[\s_-])/i;
const PRIMARY_TAGS = new Set(["button", "input", "select", "textarea", "summary"]);
const ACTIONABLE_TAGS = new Set([...PRIMARY_TAGS, "a"]);

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function isAssistive(item) {
  return ASSISTIVE_CLASS.test(String(item.className ?? ""));
}

function isDecorative(item) {
  return DECORATIVE_CLASS.test(`${item.id ?? ""} ${item.className ?? ""}`)
    && !ACTIONABLE_TAGS.has(String(item.tag ?? "").toLowerCase());
}

function isActionable(item) {
  const tag = String(item.tag ?? "").toLowerCase();
  return ACTIONABLE_TAGS.has(tag) || String(item.text ?? "").trim().length > 0;
}

function splitOffscreen(items = []) {
  const actionableOffscreen = [];
  const decorativeOffscreen = [];
  const assistiveClipping = [];
  const unclassifiedOffscreen = [];
  for (const item of items) {
    if (isAssistive(item)) assistiveClipping.push(item);
    else if (isDecorative(item)) decorativeOffscreen.push(item);
    else if (isActionable(item)) actionableOffscreen.push(item);
    else unclassifiedOffscreen.push(item);
  }
  return {
    actionableOffscreen,
    decorativeOffscreen,
    assistiveClipping,
    unclassifiedOffscreen,
  };
}

function splitFixed(items = []) {
  const actionableFixedOversize = [];
  const decorativeFixedOversize = [];
  for (const item of items) {
    if (isAssistive(item) || isDecorative(item) || !isActionable(item)) {
      decorativeFixedOversize.push(item);
    } else {
      actionableFixedOversize.push(item);
    }
  }
  return { actionableFixedOversize, decorativeFixedOversize };
}

function splitTargets(items = []) {
  const undersizedPrimaryTargets = [];
  const undersizedLinkTargets = [];
  const advisorySmallLinks = [];
  for (const item of items) {
    const tag = String(item.tag ?? "").toLowerCase();
    const width = Number(item.width ?? 0);
    const height = Number(item.height ?? 0);
    if (tag === "a") {
      if (width < 23.5 || height < 23.5) undersizedLinkTargets.push(item);
      else advisorySmallLinks.push(item);
    } else if (PRIMARY_TAGS.has(tag) || tag) {
      undersizedPrimaryTargets.push(item);
    }
  }
  return { undersizedPrimaryTargets, undersizedLinkTargets, advisorySmallLinks };
}

function normalizeViewport(row, pageErrorCount) {
  const offscreen = splitOffscreen(row.offscreen ?? []);
  const fixed = splitFixed(row.fixedOversize ?? []);
  const targets = splitTargets(row.undersizedTargets ?? []);
  const measurement = {
    ...row,
    ...offscreen,
    ...fixed,
    ...targets,
    pageErrorCount,
  };
  const policy = classifyMeasurement(measurement);
  return {
    ...measurement,
    ...policy,
    decorativeFixedOversize: fixed.decorativeFixedOversize,
    rawPass: row.pass,
  };
}

function normalizeSurface(surface) {
  const pageErrorsByViewport = new Map();
  for (const item of surface.pageErrors ?? []) {
    const name = String(item.viewport ?? "unknown");
    pageErrorsByViewport.set(name, (pageErrorsByViewport.get(name) ?? 0) + 1);
  }
  const viewports = (surface.viewports ?? []).map((row) =>
    normalizeViewport(row, pageErrorsByViewport.get(String(row.name)) ?? 0),
  );
  const disposition = surfaceDisposition(viewports, {
    runtimeStage: surface.stage ?? "UNKNOWN",
    availability: "RAW_PUBLIC_PROBE",
  });
  return {
    ...surface,
    ...disposition,
    viewports,
    rawPass: surface.pass,
  };
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[char],
  );
}

function htmlReport(report) {
  const rows = report.surfaces.map((surface) => {
    const failures = [];
    for (const viewport of surface.viewports) {
      const codes = (viewport.failures ?? []).map((item) => item.code);
      if (codes.length) failures.push(`${viewport.name}: ${codes.join(", ")}`);
    }
    return `<tr><td>${escapeHtml(surface.id)}</td><td>${escapeHtml(surface.sdk || surface.role || "")}</td><td class="${surface.pass ? "pass" : "fail"}">${surface.pass ? "PASS" : "FAIL"}</td><td>${escapeHtml(surface.stage || "")}</td><td>${failures.join("<br>") || "No actionable failures"}</td><td>${surface.warningCount}</td></tr>`;
  }).join("\n");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SZL Responsive Estate v3.1</title><style>body{margin:0;background:#080c14;color:#eef4fb;font:16px/1.5 system-ui,sans-serif}main{width:min(100% - 2rem,1200px);margin:auto;padding:3rem 0}h1{font-size:clamp(2rem,5vw,4.5rem)}table{width:100%;border-collapse:collapse}th,td{padding:.8rem;border-bottom:1px solid #2a3344;text-align:left;vertical-align:top}.pass{color:#75e0bd}.fail{color:#ff9c8f}@media(max-width:700px){table,tbody,tr,td{display:block}thead{position:absolute;clip-path:inset(50%)}tr{padding:1rem 0}td{border:0;padding:.35rem 0}}</style></head><body><main><p>MEASURED browser audit · ${escapeHtml(report.observedAt)}</p><h1>SZL Responsive Estate v3.1</h1><p>${report.passCount}/${report.surfaceCount} surfaces passed. Decorative overflow and assistive clipping are warnings; actionable defects remain blocking.</p><table><thead><tr><th>Surface</th><th>SDK / role</th><th>Status</th><th>Runtime</th><th>Actionable failures</th><th>Warnings</th></tr></thead><tbody>${rows}</tbody></table></main></body></html>`;
}

export function normalizeReport(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.surfaces)) {
    throw new TypeError("raw responsive report must contain a surfaces array");
  }
  const surfaces = raw.surfaces.map(normalizeSurface);
  return {
    schema: "szl.responsive-browser-audit/v3.1",
    sourceSchema: raw.schema ?? null,
    observedAt: raw.observedAt ?? new Date().toISOString(),
    normalizedAt: new Date().toISOString(),
    viewportContract: raw.viewportContract ?? [],
    coreViewportContract: raw.coreViewportContract ?? [],
    policy: {
      decorativeOverflow: "WARNING",
      assistiveClipping: "WARNING",
      nonActionableGeometryOverflow: "WARNING",
      actionableOffscreen: "BLOCKING",
      actionableFixedOversize: "BLOCKING",
      documentOverflowAboveTwoPixels: "BLOCKING",
      primaryTargetBelow44Pixels: "BLOCKING",
      linkTargetBelow24Pixels: "BLOCKING",
      linkBelow44Pixels: "WARNING",
    },
    surfaceCount: surfaces.length,
    passCount: surfaces.filter((surface) => surface.pass).length,
    failCount: surfaces.filter((surface) => !surface.pass).length,
    failureCount: surfaces.reduce((total, surface) => total + surface.failureCount, 0),
    warningCount: surfaces.reduce((total, surface) => total + surface.warningCount, 0),
    surfaces,
  };
}

async function main() {
  const input = arg("--input");
  const jsonOut = arg("--json-out", "reports/responsive-estate-v3.1.json");
  const htmlOut = arg("--html-out", "reports/responsive-estate-v3.1.html");
  if (!input) throw new Error("--input is required");
  const raw = JSON.parse(await fs.readFile(input, "utf8"));
  const report = normalizeReport(raw);
  await fs.mkdir(path.dirname(jsonOut), { recursive: true });
  await fs.mkdir(path.dirname(htmlOut), { recursive: true });
  await fs.writeFile(jsonOut, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await fs.writeFile(htmlOut, htmlReport(report), "utf8");
  console.log(JSON.stringify({
    surfaceCount: report.surfaceCount,
    passCount: report.passCount,
    failCount: report.failCount,
    failureCount: report.failureCount,
    warningCount: report.warningCount,
  }, null, 2));
  process.exitCode = report.failCount === 0 ? 0 : 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 2;
  });
}
