import test from "node:test";
import assert from "node:assert/strict";
import {
  classifyMeasurement,
  surfaceDisposition,
} from "../scripts/responsive_audit_policy_v31.mjs";
import { normalizeReport } from "../scripts/normalize_responsive_estate_v31.mjs";

function baseline(overrides = {}) {
  return {
    bodyRendered: true,
    viewportMeta: true,
    httpStatus: 200,
    horizontalOverflow: 0,
    undersizedPrimaryTargets: [],
    undersizedLinkTargets: [],
    advisorySmallLinks: [],
    actionableOffscreen: [],
    actionableFixedOversize: [],
    decorativeOffscreen: [],
    assistiveClipping: [],
    unclassifiedOffscreen: [],
    clippedText: [],
    pageErrorCount: 0,
    ...overrides,
  };
}

test("decorative holographic overflow is evidence-only", () => {
  const result = classifyMeasurement(
    baseline({ decorativeOffscreen: [{ className: "szl-proof-spectral-layer" }] }),
  );
  assert.equal(result.pass, true);
  assert.equal(result.failures.length, 0);
  assert.equal(result.warnings[0].code, "DECORATIVE_LAYER_OFFSCREEN");
});

test("screen-reader-only clipping is evidence-only", () => {
  const result = classifyMeasurement(
    baseline({ assistiveClipping: [{ className: "sr-only" }] }),
  );
  assert.equal(result.pass, true);
  assert.equal(result.warnings[0].code, "ASSISTIVE_TEXT_INTENTIONALLY_CLIPPED");
});

test("actionable offscreen content blocks release", () => {
  const result = classifyMeasurement(
    baseline({ actionableOffscreen: [{ tag: "button", text: "Approve" }] }),
  );
  assert.equal(result.pass, false);
  assert.equal(result.failures[0].code, "ACTIONABLE_CONTENT_OFFSCREEN");
});

test("primary controls keep the 44px SZL standard", () => {
  const result = classifyMeasurement(
    baseline({ undersizedPrimaryTargets: [{ tag: "button", width: 40, height: 40 }] }),
  );
  assert.equal(result.pass, false);
  assert.equal(result.failures[0].code, "PRIMARY_TARGET_UNDERSIZED");
});

test("text links use the WCAG 24px floor and preserve 44px as warning", () => {
  const advisory = classifyMeasurement(
    baseline({ advisorySmallLinks: [{ tag: "a", width: 80, height: 30 }] }),
  );
  assert.equal(advisory.pass, true);
  assert.equal(advisory.warnings[0].code, "LINK_BELOW_SZL_TOUCH_IDEAL");

  const blocking = classifyMeasurement(
    baseline({ undersizedLinkTargets: [{ tag: "a", width: 20, height: 20 }] }),
  );
  assert.equal(blocking.pass, false);
  assert.equal(blocking.failures[0].code, "LINK_TARGET_UNDERSIZED");
});

test("real document overflow remains blocking", () => {
  const result = classifyMeasurement(baseline({ horizontalOverflow: 5 }));
  assert.equal(result.pass, false);
  assert.equal(result.failures[0].code, "DOCUMENT_HORIZONTAL_OVERFLOW");
});

test("surface disposition aggregates failures without converting warnings", () => {
  const first = { ...classifyMeasurement(baseline()), name: "desktop" };
  const second = {
    ...classifyMeasurement(baseline({ decorativeOffscreen: [{ tag: "div" }] })),
    name: "phone",
  };
  const disposition = surfaceDisposition([first, second], {
    runtimeStage: "RUNNING",
    availability: "OBSERVED",
  });
  assert.equal(disposition.pass, true);
  assert.equal(disposition.failureCount, 0);
  assert.equal(disposition.warningCount, 1);
});

test("raw spectral layers and sr-only labels no longer manufacture red surfaces", () => {
  const raw = {
    schema: "szl.responsive-browser-audit/v3",
    observedAt: "2026-10-04T06:04:37Z",
    surfaces: [
      {
        id: "proof-origin",
        role: "independent-proof-origin",
        pass: false,
        pageErrors: [],
        viewports: [
          {
            name: "compact-phone",
            width: 320,
            height: 568,
            httpStatus: 200,
            bodyRendered: true,
            viewportMeta: true,
            horizontalOverflow: 0,
            undersizedTargets: [],
            fixedOversize: [],
            clippedText: [{ tag: "span", className: "sr-only", width: 1, height: 1 }],
            offscreen: [
              { tag: "div", className: "szl-proof-spectral-layer", text: "", width: 600, height: 600 },
              { tag: "span", className: "sr-only", text: "Proof", width: 1, height: 1 },
            ],
          },
        ],
      },
    ],
  };
  const normalized = normalizeReport(raw);
  assert.equal(normalized.passCount, 1);
  assert.equal(normalized.failCount, 0);
  assert.equal(normalized.surfaces[0].pass, true);
  assert.ok(normalized.surfaces[0].warningCount >= 2);
});

test("raw real overflow and offscreen button remain red", () => {
  const raw = {
    schema: "szl.responsive-browser-audit/v3",
    surfaces: [
      {
        id: "product",
        pass: false,
        pageErrors: [],
        viewports: [
          {
            name: "compact-phone",
            httpStatus: 200,
            bodyRendered: true,
            viewportMeta: true,
            horizontalOverflow: 10,
            undersizedTargets: [],
            fixedOversize: [],
            clippedText: [],
            offscreen: [{ tag: "button", className: "cta", text: "Launch", width: 80, height: 44 }],
          },
        ],
      },
    ],
  };
  const normalized = normalizeReport(raw);
  assert.equal(normalized.failCount, 1);
  const codes = normalized.surfaces[0].viewports[0].failures.map((item) => item.code);
  assert.deepEqual(codes, ["DOCUMENT_HORIZONTAL_OVERFLOW", "ACTIONABLE_CONTENT_OFFSCREEN"]);
});
