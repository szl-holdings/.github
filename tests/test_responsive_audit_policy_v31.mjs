import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { classifyMeasurement, surfaceDisposition, VIEWPORTS, CORE_VIEWPORTS } from "../scripts/responsive_audit_policy_v31.mjs";
import { normalizeReport } from "../scripts/normalize_responsive_estate_v31.mjs";

function baseline(overrides = {}) {
  return {
    bodyRendered: true, viewportMeta: true, httpStatus: 200, horizontalOverflow: 0,
    undersizedPrimaryTargets: [], undersizedLinkTargets: [], advisorySmallLinks: [],
    actionableOffscreen: [], actionableFixedOversize: [], unclassifiedOffscreen: [],
    unclassifiedFixedOversize: [], decorativeOffscreen: [], decorativeFixedOversize: [],
    assistiveClipping: [], clippedText: [], pageErrorCount: 0,
    ...overrides,
  };
}

function rawReport(kind = "space") {
  return {
    schema: "szl.responsive-browser-audit/v3",
    observedAt: "2026-10-04T06:04:37Z",
    viewportContract: VIEWPORTS,
    coreViewportContract: CORE_VIEWPORTS,
    surfaceCount: 1,
    surfaces: [{
      id: kind === "core" ? "proof-origin" : "SZLHOLDINGS/fixture",
      kind, pass: true, pageErrors: [], errors: [], consoleErrors: [],
      viewports: (kind === "core" ? CORE_VIEWPORTS : VIEWPORTS).map((viewport) => ({
        ...viewport, viewportWidth: viewport.width, httpStatus: 200, bodyRendered: true, viewportMeta: true,
        horizontalOverflow: 0, undersizedTargets: [], fixedOversize: [],
        clippedText: [], offscreen: [], pass: true,
      })),
    }],
  };
}

function element(overrides = {}) {
  return {
    tag: "div", text: "", className: "szl-proof-spectral-layer", role: null,
    ariaHidden: true, tabIndex: -1, interactive: false, focusable: false,
    hasInteractiveDescendant: false, contentEditable: false, primaryControl: false,
    intentionallyClipped: false, width: 600, height: 600,
    ...overrides,
  };
}

function normalizedElement(item, field = "offscreen") {
  const raw = rawReport();
  raw.surfaces[0].viewports[0][field] = [item];
  return normalizeReport(raw).surfaces[0];
}

const codes = (row) => row.failures.map((issue) => issue.code);

test("a complete, measured report preserves its observation time", () => {
  const raw = rawReport();
  const report = normalizeReport(raw);
  assert.equal(report.observedAt, raw.observedAt);
  assert.equal(report.passCount, 1);
  assert.equal(report.failCount, 0);
  assert.equal(report.failureCount, 0);
});

test("observed empty, hidden, noninteractive decoration remains evidence-only", () => {
  for (const field of ["offscreen", "fixedOversize"]) {
    const row = normalizedElement(element(), field);
    assert.equal(row.pass, true);
    assert.equal(row.failureCount, 0);
    assert.equal(row.warningCount, 1);
  }
});

test("observed intentionally clipped noninteractive assistive labels remain warnings", () => {
  const row = normalizedElement(element({
    tag: "span", className: "sr-only", text: "Proof", ariaHidden: false,
    intentionallyClipped: true, width: 1, height: 1,
  }));
  assert.equal(row.pass, true);
  assert.equal(row.viewports[0].warnings[0].code, "ASSISTIVE_TEXT_INTENTIONALLY_CLIPPED");
});

test("decorative names cannot demote meaningful content or controls", () => {
  const candidates = [
    { text: "Account balance" },
    { tag: "button", className: "glow" },
    { role: "button" },
    { role: "tab" },
    { role: "img" },
    { tabIndex: 0 },
    { focusable: true },
    { interactive: true },
    { hasInteractiveDescendant: true },
    { contentEditable: true },
  ];
  for (const candidate of candidates) {
    for (const field of ["offscreen", "fixedOversize"]) {
      const row = normalizedElement(element(candidate), field);
      assert.equal(row.pass, false, JSON.stringify({ candidate, field }));
      assert.ok(codes(row.viewports[0]).includes(field === "offscreen"
        ? "ACTIONABLE_CONTENT_OFFSCREEN" : "ACTIONABLE_FIXED_CONTENT_OVERSIZE"));
    }
  }
});

test("sr-only controls, including custom roles and descendants, remain blockers", () => {
  for (const candidate of [{ tag: "button" }, { role: "button" }, { hasInteractiveDescendant: true }, { tabIndex: 0 }]) {
    const row = normalizedElement(element({
      className: "sr-only", text: "Approve", intentionallyClipped: true,
      width: 1, height: 1, ...candidate,
    }));
    assert.equal(row.pass, false);
    assert.ok(codes(row.viewports[0]).includes("ACTIONABLE_CONTENT_OFFSCREEN"));
  }
});

test("a screen-reader class without observed clipping does not excuse offscreen text", () => {
  const row = normalizedElement(element({ tag: "span", className: "sr-only", text: "Visible warning" }));
  assert.equal(row.pass, false);
});

test("missing semantic evidence does not establish harmless decoration", () => {
  for (const field of ["interactive", "focusable", "hasInteractiveDescendant", "contentEditable", "tabIndex", "ariaHidden", "width", "height"]) {
    const item = element();
    delete item[field];
    const row = normalizedElement(item);
    assert.equal(row.pass, false, field);
    assert.ok(codes(row.viewports[0]).includes("UNCLASSIFIED_CONTENT_OFFSCREEN"));
  }
});

test("primary controls retain the 44px floor, including anchors acting as buttons", () => {
  for (const item of [
    { tag: "button", width: 40, height: 40 },
    { tag: "div", role: "tab", width: 40, height: 40 },
    { tag: "a", role: "button", width: 40, height: 40 },
    { tag: "a", primaryControl: true, width: 40, height: 40 },
  ]) {
    const row = normalizedElement(element(item), "undersizedTargets");
    assert.equal(row.pass, false);
    assert.ok(codes(row.viewports[0]).includes("PRIMARY_TARGET_UNDERSIZED"));
  }
});

test("measured ordinary links use the 24px floor and keep 44px as advisory", () => {
  const link = element({ tag: "a", role: "link", primaryControl: false, width: 80, height: 30 });
  const advisory = normalizedElement(link, "undersizedTargets");
  assert.equal(advisory.pass, true);
  assert.equal(advisory.viewports[0].warnings[0].code, "LINK_BELOW_SZL_TOUCH_IDEAL");
  const blocking = normalizedElement({ ...link, height: 20 }, "undersizedTargets");
  assert.equal(blocking.pass, false);
  assert.ok(codes(blocking.viewports[0]).includes("LINK_TARGET_UNDERSIZED"));
});

test("invalid target geometry cannot become a link warning", () => {
  for (const width of [undefined, null, "40", NaN, -1]) {
    const row = normalizedElement(element({ tag: "a", width, height: 30 }), "undersizedTargets");
    assert.equal(row.pass, false);
  }
});

test("document overflow, unavailable bodies, and runtime errors remain blocking", () => {
  for (const [measurement, code] of [
    [{ horizontalOverflow: 5 }, "DOCUMENT_HORIZONTAL_OVERFLOW"],
    [{ bodyRendered: false }, "BODY_NOT_RENDERED"],
    [{ bodyRendered: "true" }, "BODY_NOT_RENDERED"],
    [{ viewportMeta: false }, "VIEWPORT_META_MISSING"],
    [{ httpStatus: 503 }, "HTTP_ERROR"],
    [{ pageErrorCount: 1 }, "PAGE_RUNTIME_ERROR"],
    [{ error: "navigation timed out" }, "BROWSER_PROBE_ERROR"],
  ]) {
    const result = classifyMeasurement(baseline(measurement));
    assert.equal(result.pass, false);
    assert.ok(codes(result).includes(code));
  }
});

test("missing or malformed HTTP and overflow observations cannot pass", () => {
  for (const httpStatus of [undefined, null, "200", 0, 199, 600, 200.5]) {
    assert.equal(classifyMeasurement(baseline({ httpStatus })).pass, false);
  }
  for (const horizontalOverflow of [undefined, null, "0", NaN, -1]) {
    assert.equal(classifyMeasurement(baseline({ horizontalOverflow })).pass, false);
  }
});

test("empty measurements never become a green surface", () => {
  assert.equal(surfaceDisposition([]).pass, false);
  assert.equal(surfaceDisposition(null).pass, false);
  assert.equal(classifyMeasurement({}).pass, false);
  const raw = rawReport();
  raw.surfaces[0].viewports = [];
  const report = normalizeReport(raw);
  assert.equal(report.failCount, 1);
  assert.equal(report.failureCount, VIEWPORTS.length);
});

test("every assigned viewport and its dimensions must be measured exactly once", () => {
  for (const kind of ["core", "space"]) {
    for (const mutate of [
      (rows) => rows.pop(),
      (rows) => rows.push({ ...rows[0] }),
      (rows) => { rows[0].width = 999; },
      (rows) => { delete rows[0].height; },
      (rows) => { delete rows[0].viewportWidth; },
      (rows) => { rows[0].viewportWidth = 999; },
      (rows) => { rows[0].name = "unassigned"; },
    ]) {
      const raw = rawReport(kind);
      mutate(raw.surfaces[0].viewports);
      assert.equal(normalizeReport(raw).failCount, 1, kind);
    }
  }
});

test("missing measurement arrays are unavailable, never silently empty", () => {
  for (const field of ["offscreen", "fixedOversize", "undersizedTargets", "clippedText"]) {
    const raw = rawReport();
    delete raw.surfaces[0].viewports[0][field];
    assert.equal(normalizeReport(raw).failCount, 1, field);
  }
});

test("surface probe errors and unassigned page errors stay visible and blocking", () => {
  for (const mutate of [
    (surface) => surface.pageErrors.push({ viewport: "compact-phone", message: "TypeError" }),
    (surface) => surface.pageErrors.push({ message: "unassigned error" }),
    (surface) => surface.errors.push({ viewport: "desktop", message: "timeout" }),
    (surface) => { delete surface.pageErrors; },
    (surface) => { delete surface.errors; },
  ]) {
    const raw = rawReport();
    mutate(raw.surfaces[0]);
    assert.equal(normalizeReport(raw).failCount, 1);
  }
});

test("empty estates and altered or absent viewport contracts are rejected", () => {
  for (const mutate of [
    (raw) => { raw.surfaces = []; raw.surfaceCount = 0; },
    (raw) => { delete raw.viewportContract; },
    (raw) => { raw.viewportContract = []; },
    (raw) => { raw.coreViewportContract = VIEWPORTS; },
    (raw) => { raw.surfaces[0].kind = "unknown"; },
    (raw) => { delete raw.surfaces[0].id; },
    (raw) => { raw.surfaces.push(raw.surfaces[0]); raw.surfaceCount = 2; },
    (raw) => { raw.surfaceCount = 2; },
    (raw) => { raw.schema = "unknown"; },
  ]) {
    const raw = rawReport();
    mutate(raw);
    assert.throws(() => normalizeReport(raw), TypeError);
  }
});

test("missing, malformed, and impossible observation timestamps are rejected", () => {
  for (const stamp of [undefined, null, "", "today", "2026-02-30T00:00:00Z", "2026-10-04"]) {
    const raw = rawReport();
    raw.observedAt = stamp;
    assert.throws(() => normalizeReport(raw), /observedAt/);
  }
});

test("CLI exits nonzero for invalid evidence and preserves legitimate failures in artifacts", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "responsive-policy-"));
  const script = fileURLToPath(new URL("../scripts/normalize_responsive_estate_v31.mjs", import.meta.url));
  try {
    const input = path.join(directory, "raw.json");
    const output = path.join(directory, "report.json");
    const html = path.join(directory, "report.html");
    const execute = (raw) => {
      fs.writeFileSync(input, JSON.stringify(raw));
      return spawnSync(process.execPath, [script, "--input", input, "--json-out", output, "--html-out", html], { encoding: "utf8" });
    };
    const invalid = rawReport();
    delete invalid.observedAt;
    assert.equal(execute(invalid).status, 2);
    assert.equal(fs.existsSync(output), false);
    const failed = rawReport();
    failed.surfaces[0].viewports = [];
    assert.equal(execute(failed).status, 1);
    assert.equal(JSON.parse(fs.readFileSync(output, "utf8")).failCount, 1);
    assert.match(fs.readFileSync(html, "utf8"), /VIEWPORT_MEASUREMENT_MISSING/);
    assert.equal(execute(rawReport()).status, 0);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
