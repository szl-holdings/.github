/**
 * Pure, deterministic policy for the browser-level responsive audit.
 *
 * The browser probe records geometry and semantics. This module decides which
 * observations are release-blocking and which are evidence-only warnings. A
 * decorative holographic layer, an intentional screen-reader-only label, and a
 * genuinely clipped control must never be collapsed into the same predicate.
 */

export const POLICY_SCHEMA = "szl.responsive-audit-policy/v3.1";
export const MAX_HORIZONTAL_OVERFLOW_PX = 2;
export const MIN_PRIMARY_TARGET_PX = 43.5;
export const MIN_LINK_TARGET_PX = 23.5;

function issue(code, detail = {}) {
  return { code, ...detail };
}

export function classifyMeasurement(measurement) {
  const failures = [];
  const warnings = [];

  if (!measurement.bodyRendered) failures.push(issue("BODY_NOT_RENDERED"));
  if (!measurement.viewportMeta) failures.push(issue("VIEWPORT_META_MISSING"));
  if (measurement.httpStatus !== null && measurement.httpStatus >= 400) {
    failures.push(issue("HTTP_ERROR", { status: measurement.httpStatus }));
  }
  if ((measurement.horizontalOverflow ?? 0) > MAX_HORIZONTAL_OVERFLOW_PX) {
    failures.push(
      issue("DOCUMENT_HORIZONTAL_OVERFLOW", {
        pixels: measurement.horizontalOverflow,
        maximum: MAX_HORIZONTAL_OVERFLOW_PX,
      }),
    );
  }

  for (const target of measurement.undersizedPrimaryTargets ?? []) {
    failures.push(issue("PRIMARY_TARGET_UNDERSIZED", { target }));
  }
  for (const target of measurement.undersizedLinkTargets ?? []) {
    failures.push(issue("LINK_TARGET_UNDERSIZED", { target }));
  }
  for (const target of measurement.advisorySmallLinks ?? []) {
    warnings.push(issue("LINK_BELOW_SZL_TOUCH_IDEAL", { target }));
  }
  for (const element of measurement.actionableOffscreen ?? []) {
    failures.push(issue("ACTIONABLE_CONTENT_OFFSCREEN", { element }));
  }
  for (const element of measurement.actionableFixedOversize ?? []) {
    failures.push(issue("ACTIONABLE_FIXED_CONTENT_OVERSIZE", { element }));
  }

  for (const element of measurement.decorativeOffscreen ?? []) {
    warnings.push(issue("DECORATIVE_LAYER_OFFSCREEN", { element }));
  }
  for (const element of measurement.assistiveClipping ?? []) {
    warnings.push(issue("ASSISTIVE_TEXT_INTENTIONALLY_CLIPPED", { element }));
  }
  for (const element of measurement.unclassifiedOffscreen ?? []) {
    warnings.push(issue("NON_ACTIONABLE_GEOMETRY_OFFSCREEN", { element }));
  }
  for (const element of measurement.clippedText ?? []) {
    warnings.push(issue("CLIPPED_TEXT_REVIEW", { element }));
  }

  if ((measurement.pageErrorCount ?? 0) > 0) {
    failures.push(issue("PAGE_RUNTIME_ERROR", { count: measurement.pageErrorCount }));
  }

  return {
    schema: POLICY_SCHEMA,
    pass: failures.length === 0,
    failures,
    warnings,
  };
}

export function surfaceDisposition(viewports, lifecycle = {}) {
  const failed = viewports.filter((row) => !row.pass);
  const runtimeStage = String(lifecycle.runtimeStage ?? "UNKNOWN").toUpperCase();
  const availability = lifecycle.availability ?? "OBSERVED";

  return {
    pass: failed.length === 0,
    failedViewportCount: failed.length,
    failureCount: viewports.reduce((total, row) => total + (row.failures?.length ?? 0), 0),
    warningCount: viewports.reduce((total, row) => total + (row.warnings?.length ?? 0), 0),
    runtimeStage,
    availability,
  };
}
