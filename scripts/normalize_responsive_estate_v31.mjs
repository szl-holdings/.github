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
  VIEWPORTS,
  CORE_VIEWPORTS,
  MIN_LINK_TARGET_PX,
  MIN_PRIMARY_TARGET_PX,
} from "./responsive_audit_policy_v31.mjs";

const DECORATIVE_CLASS = /(?:^|[\s_-])(spectral|hologram|holo|aurora|glow|backdrop|background|noise|particle|beam|scanline|motif|decoration|ornament|ambient|orb)(?:$|[\s_-])/i;
const ASSISTIVE_CLASS = /(?:^|[\s_-])(sr-only|screen-reader|visually-hidden|a11y-hidden)(?:$|[\s_-])/i;
const PRIMARY_TAGS = new Set(["button", "input", "select", "textarea", "summary"]);
const ACTIONABLE_TAGS = new Set([...PRIMARY_TAGS, "a"]);
const PRESENTATIONAL_ROLES = new Set(["", "none", "presentation"]);

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function hasControlSemantics(item) {
  return ACTIONABLE_TAGS.has(String(item.tag ?? "").toLowerCase())
    || item.interactive === true || item.focusable === true
    || item.hasInteractiveDescendant === true || item.contentEditable === true
    || (Number.isInteger(item.tabIndex) && item.tabIndex >= 0)
    || !PRESENTATIONAL_ROLES.has(String(item.role ?? "").trim().toLowerCase());
}

function observedNonInteractive(item) {
  return !hasControlSemantics(item) && item.interactive === false
    && item.focusable === false && item.hasInteractiveDescendant === false
    && item.contentEditable === false && Number.isInteger(item.tabIndex) && item.tabIndex < 0
    && Number.isFinite(item.width) && item.width > 0 && Number.isFinite(item.height) && item.height > 0;
}

function isAssistive(item) {
  return observedNonInteractive(item) && item.intentionallyClipped === true
    && ASSISTIVE_CLASS.test(String(item.className ?? ""))
    && String(item.text ?? "").trim().length > 0;
}

function isDecorative(item) {
  return observedNonInteractive(item) && item.ariaHidden === true
    && String(item.text ?? "").trim().length === 0
    && DECORATIVE_CLASS.test(`${item.id ?? ""} ${item.className ?? ""}`);
}

function isActionable(item) {
  return hasControlSemantics(item) || String(item.text ?? "").trim().length > 0;
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
  const assistiveClipping = [];
  const unclassifiedFixedOversize = [];
  for (const item of items) {
    if (isAssistive(item)) assistiveClipping.push(item);
    else if (isDecorative(item)) decorativeFixedOversize.push(item);
    else if (isActionable(item)) actionableFixedOversize.push(item);
    else unclassifiedFixedOversize.push(item);
  }
  return { actionableFixedOversize, decorativeFixedOversize, assistiveClipping, unclassifiedFixedOversize };
}

function splitTargets(items = []) {
  const undersizedPrimaryTargets = [];
  const undersizedLinkTargets = [];
  const advisorySmallLinks = [];
  for (const item of items) {
    const tag = String(item.tag ?? "").toLowerCase();
    const { width, height } = item;
    // An anchor exposed as a button or tab retains the primary-control floor.
    const link = tag === "a" && item.primaryControl === false
      && ["", "link"].includes(String(item.role ?? "").toLowerCase());
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      undersizedPrimaryTargets.push(item);
    } else if (link) {
      if (width < MIN_LINK_TARGET_PX || height < MIN_LINK_TARGET_PX) undersizedLinkTargets.push(item);
      else if (width < MIN_PRIMARY_TARGET_PX || height < MIN_PRIMARY_TARGET_PX) advisorySmallLinks.push(item);
    } else if (width < MIN_PRIMARY_TARGET_PX || height < MIN_PRIMARY_TARGET_PX) {
      undersizedPrimaryTargets.push(item);
    }
  }
  return { undersizedPrimaryTargets, undersizedLinkTargets, advisorySmallLinks };
}

function normalizeViewport(row, pageErrorCount) {
  if (!row || typeof row !== "object" || Array.isArray(row)) throw new TypeError("viewport measurement must be an object");
  const measurementErrors = [];
  if (!Number.isInteger(row.viewportWidth) || row.viewportWidth !== row.width) {
    measurementErrors.push({ code: "OBSERVED_VIEWPORT_WIDTH_MISMATCH" });
  }
  function observations(field) {
    if (!Array.isArray(row[field]) || row[field].some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
      measurementErrors.push({ code: "RAW_MEASUREMENT_ARRAY_UNAVAILABLE", field });
      return [];
    }
    return row[field];
  }
  const offscreen = splitOffscreen(observations("offscreen"));
  const fixed = splitFixed(observations("fixedOversize"));
  const targets = splitTargets(observations("undersizedTargets"));
  const clippedText = observations("clippedText");
  const measurement = {
    ...row,
    ...offscreen,
    ...fixed,
    ...targets,
    assistiveClipping: [...offscreen.assistiveClipping, ...fixed.assistiveClipping],
    clippedText,
    measurementErrors,
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
  if (!surface || typeof surface !== "object" || !["core", "space"].includes(surface.kind)) {
    throw new TypeError("surface must declare its core or space viewport assignment");
  }
  const expectedViewports = surface.kind === "core" ? CORE_VIEWPORTS : VIEWPORTS;
  const expectedNames = new Set(expectedViewports.map((row) => row.name));
  const failures = [];
  const pageErrorsByViewport = new Map();
  if (!Array.isArray(surface.pageErrors)) {
    failures.push({ code: "PAGE_ERRORS_UNAVAILABLE" });
  } else {
    for (const item of surface.pageErrors) {
      const name = String(item?.viewport ?? "unknown");
      if (!expectedNames.has(name)) failures.push({ code: "UNASSIGNED_PAGE_RUNTIME_ERROR", viewport: name });
      pageErrorsByViewport.set(name, (pageErrorsByViewport.get(name) ?? 0) + 1);
    }
  }
  if (!Array.isArray(surface.errors)) failures.push({ code: "BROWSER_ERRORS_UNAVAILABLE" });
  else if (surface.errors.length) failures.push({ code: "SURFACE_BROWSER_PROBE_ERROR", count: surface.errors.length });
  if (!Array.isArray(surface.viewports)) failures.push({ code: "VIEWPORT_MEASUREMENTS_UNAVAILABLE" });
  const viewports = (Array.isArray(surface.viewports) ? surface.viewports : []).map((row) =>
    normalizeViewport(row, pageErrorsByViewport.get(String(row.name)) ?? 0),
  );
  const disposition = surfaceDisposition(viewports, {
    runtimeStage: surface.stage ?? "UNKNOWN",
    availability: "RAW_PUBLIC_PROBE",
    failures,
  }, expectedViewports);
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
    const failures = surface.failures.map((item) => escapeHtml(`${item.code}${item.viewport ? `: ${item.viewport}` : ""}`));
    for (const viewport of surface.viewports) {
      const codes = (viewport.failures ?? []).map((item) => item.code);
      if (codes.length) failures.push(escapeHtml(`${viewport.name}: ${codes.join(", ")}`));
    }
    return `<tr><td>${escapeHtml(surface.id)}</td><td>${escapeHtml(surface.sdk || surface.role || "")}</td><td class="${surface.pass ? "pass" : "fail"}">${surface.pass ? "PASS" : "FAIL"}</td><td>${escapeHtml(surface.stage || "")}</td><td>${failures.join("<br>") || "No actionable failures"}</td><td>${surface.warningCount}</td></tr>`;
  }).join("\n");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SZL Responsive Estate v3.1</title><style>body{margin:0;background:#080c14;color:#eef4fb;font:16px/1.5 system-ui,sans-serif}main{width:min(100% - 2rem,1200px);margin:auto;padding:3rem 0}h1{font-size:clamp(2rem,5vw,4.5rem)}table{width:100%;border-collapse:collapse}th,td{padding:.8rem;border-bottom:1px solid #2a3344;text-align:left;vertical-align:top}.pass{color:#75e0bd}.fail{color:#ff9c8f}@media(max-width:700px){table,tbody,tr,td{display:block}thead{position:absolute;clip-path:inset(50%)}tr{padding:1rem 0}td{border:0;padding:.35rem 0}}</style></head><body><main><p>MEASURED browser audit · ${escapeHtml(report.observedAt)}</p><h1>SZL Responsive Estate v3.1</h1><p>${report.passCount}/${report.surfaceCount} surfaces passed. Decorative overflow and assistive clipping are warnings; actionable defects remain blocking.</p><table><thead><tr><th>Surface</th><th>SDK / role</th><th>Status</th><th>Runtime</th><th>Actionable failures</th><th>Warnings</th></tr></thead><tbody>${rows}</tbody></table></main></body></html>`;
}

export function normalizeReport(raw) {
  if (!raw || typeof raw !== "object" || raw.schema !== "szl.responsive-browser-audit/v3"
      || !Array.isArray(raw.surfaces) || raw.surfaces.length === 0) {
    throw new TypeError("raw v3 responsive report must contain a non-empty surfaces array");
  }
  const stamp = raw.observedAt;
  if (typeof stamp !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(stamp)
      || !Number.isFinite(Date.parse(stamp)) || new Date(stamp).toISOString().slice(0, 19) !== stamp.slice(0, 19)) {
    throw new TypeError("raw report must preserve a valid observedAt UTC timestamp");
  }
  for (const [field, expected] of [["viewportContract", VIEWPORTS], ["coreViewportContract", CORE_VIEWPORTS]]) {
    const supplied = raw[field];
    if (!Array.isArray(supplied) || supplied.length !== expected.length
        || supplied.some((row, index) => !row || ["name", "width", "height"].some((key) => row[key] !== expected[index][key]))) {
      throw new TypeError(`raw ${field} does not match the assigned viewport contract`);
    }
  }
  const ids = new Set();
  for (const surface of raw.surfaces) {
    if (typeof surface?.id !== "string" || !surface.id.trim() || ids.has(surface.id)) {
      throw new TypeError("surface identities must be present and unique");
    }
    ids.add(surface.id);
  }
  if (raw.surfaceCount !== raw.surfaces.length) {
    throw new TypeError("raw surfaceCount must match the measured surfaces");
  }
  const surfaces = raw.surfaces.map(normalizeSurface);
  return {
    schema: "szl.responsive-browser-audit/v3.1",
    sourceSchema: raw.schema ?? null,
    observedAt: raw.observedAt,
    normalizedAt: new Date().toISOString(),
    viewportContract: raw.viewportContract,
    coreViewportContract: raw.coreViewportContract,
    policy: {
      decorativeOverflow: "WARNING",
      assistiveClipping: "WARNING",
      unclassifiedGeometryOverflow: "BLOCKING",
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
