/** Deterministic, fail-closed policy for measured responsive browser evidence. */

export const POLICY_SCHEMA = "szl.responsive-audit-policy/v3.1";
export const MAX_HORIZONTAL_OVERFLOW_PX = 2;
export const MIN_PRIMARY_TARGET_PX = 43.5;
export const MIN_LINK_TARGET_PX = 23.5;

// The probe and normalizer use the same assigned viewport contract. A report
// cannot shrink its own contract to make incomplete measurements pass.
export const VIEWPORTS = Object.freeze([
  { name: "compact-phone", width: 320, height: 568 },
  { name: "modern-phone", width: 375, height: 812 },
  { name: "phone-landscape", width: 812, height: 375 },
  { name: "desktop", width: 1440, height: 900 },
  { name: "theatre", width: 2560, height: 1440 },
].map(Object.freeze));
export const CORE_VIEWPORTS = Object.freeze([
  ...VIEWPORTS,
  { name: "large-phone", width: 430, height: 932 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "full-hd", width: 1920, height: 1080 },
  { name: "ultrawide", width: 3440, height: 1440 },
].map(Object.freeze));

function issue(code, detail = {}) {
  return { code, ...detail };
}

export function classifyMeasurement(measurement) {
  const failures = [...(measurement.measurementErrors ?? [])];
  const warnings = [];

  if (measurement.bodyRendered !== true) failures.push(issue("BODY_NOT_RENDERED"));
  if (measurement.viewportMeta !== true) failures.push(issue("VIEWPORT_META_MISSING"));
  if (!Number.isInteger(measurement.httpStatus) || measurement.httpStatus < 200 || measurement.httpStatus > 599) {
    failures.push(issue("HTTP_STATUS_UNAVAILABLE"));
  } else if (measurement.httpStatus >= 400) {
    failures.push(issue("HTTP_ERROR", { status: measurement.httpStatus }));
  }
  if (!Number.isFinite(measurement.horizontalOverflow) || measurement.horizontalOverflow < 0) {
    failures.push(issue("HORIZONTAL_OVERFLOW_UNAVAILABLE"));
  } else if (measurement.horizontalOverflow > MAX_HORIZONTAL_OVERFLOW_PX) {
    failures.push(issue("DOCUMENT_HORIZONTAL_OVERFLOW", {
      pixels: measurement.horizontalOverflow,
      maximum: MAX_HORIZONTAL_OVERFLOW_PX,
    }));
  }
  if (measurement.error) failures.push(issue("BROWSER_PROBE_ERROR", { error: measurement.error }));

  const observations = [
    ["undersizedPrimaryTargets", "PRIMARY_TARGET_UNDERSIZED", failures, "target"],
    ["undersizedLinkTargets", "LINK_TARGET_UNDERSIZED", failures, "target"],
    ["advisorySmallLinks", "LINK_BELOW_SZL_TOUCH_IDEAL", warnings, "target"],
    ["actionableOffscreen", "ACTIONABLE_CONTENT_OFFSCREEN", failures, "element"],
    ["actionableFixedOversize", "ACTIONABLE_FIXED_CONTENT_OVERSIZE", failures, "element"],
    ["unclassifiedOffscreen", "UNCLASSIFIED_CONTENT_OFFSCREEN", failures, "element"],
    ["unclassifiedFixedOversize", "UNCLASSIFIED_FIXED_CONTENT_OVERSIZE", failures, "element"],
    ["decorativeOffscreen", "DECORATIVE_LAYER_OFFSCREEN", warnings, "element"],
    ["decorativeFixedOversize", "DECORATIVE_FIXED_LAYER_OVERSIZE", warnings, "element"],
    ["assistiveClipping", "ASSISTIVE_TEXT_INTENTIONALLY_CLIPPED", warnings, "element"],
    ["clippedText", "CLIPPED_TEXT_REVIEW", warnings, "element"],
  ];
  for (const [field, code, output, detail] of observations) {
    if (!Array.isArray(measurement[field])) {
      failures.push(issue("MEASUREMENT_ARRAY_UNAVAILABLE", { field }));
      continue;
    }
    for (const value of measurement[field]) output.push(issue(code, { [detail]: value }));
  }

  if (!Number.isInteger(measurement.pageErrorCount) || measurement.pageErrorCount < 0) {
    failures.push(issue("PAGE_ERROR_COUNT_UNAVAILABLE"));
  } else if (measurement.pageErrorCount > 0) {
    failures.push(issue("PAGE_RUNTIME_ERROR", { count: measurement.pageErrorCount }));
  }

  return { schema: POLICY_SCHEMA, pass: failures.length === 0, failures, warnings };
}

export function surfaceDisposition(viewports, lifecycle = {}, expectedViewports = VIEWPORTS) {
  const failures = [...(lifecycle.failures ?? [])];
  const rows = Array.isArray(viewports) ? viewports : [];
  if (!Array.isArray(viewports)) failures.push(issue("VIEWPORT_MEASUREMENTS_UNAVAILABLE"));
  if (!Array.isArray(expectedViewports) || expectedViewports.length === 0) {
    failures.push(issue("VIEWPORT_CONTRACT_UNAVAILABLE"));
    expectedViewports = VIEWPORTS;
  }
  const expected = new Map(expectedViewports.map((row) => [row.name, row]));
  const observed = new Set();
  for (const row of rows) {
    const name = row?.name;
    if (!expected.has(name)) {
      failures.push(issue("UNEXPECTED_VIEWPORT", { viewport: name ?? null }));
    } else if (observed.has(name)) {
      failures.push(issue("DUPLICATE_VIEWPORT", { viewport: name }));
    } else {
      const dimensions = expected.get(name);
      if (row.width !== dimensions.width || row.height !== dimensions.height) {
        failures.push(issue("VIEWPORT_DIMENSIONS_MISMATCH", { viewport: name }));
      }
    }
    observed.add(name);
    if (row?.pass !== true && !row?.failures?.length) {
      failures.push(issue("VIEWPORT_NOT_PASSED", { viewport: name ?? null }));
    }
  }
  for (const name of expected.keys()) {
    if (!observed.has(name)) failures.push(issue("VIEWPORT_MEASUREMENT_MISSING", { viewport: name }));
  }
  const failed = rows.filter((row) => row?.pass !== true);
  return {
    pass: failures.length === 0 && failed.length === 0,
    failures,
    failedViewportCount: failed.length,
    failureCount: failures.length + rows.reduce((total, row) => total + (row?.failures?.length ?? 0), 0),
    warningCount: rows.reduce((total, row) => total + (row?.warnings?.length ?? 0), 0),
    runtimeStage: String(lifecycle.runtimeStage ?? "UNKNOWN").toUpperCase(),
    availability: lifecycle.availability ?? "OBSERVED",
  };
}
