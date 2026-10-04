import test from "node:test";
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { inspectPage } from "../scripts/audit_responsive_estate_v3.mjs";

test("the real DOM probe distinguishes decoration, custom controls, and assistive labels", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 320, height: 568 } });
    await page.route("**/*", (route) => route.abort());
    await page.setContent(`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>
        body { overflow-x: hidden; }
        .offscreen { position: fixed; left: -160px; width: 100px; height: 50px; }
        .sr-only { position: fixed; left: -100px; width: 1px; height: 1px; padding: 0; border: 0;
          overflow: hidden; white-space: nowrap; clip: rect(0,0,0,0); clip-path: inset(50%); }
      </style></head><body><p>Responsive semantic observation fixture with enough rendered body text.</p>
      <div id="decoration" class="offscreen spectral-layer" aria-hidden="true"></div>
      <svg id="svg-decoration" class="offscreen spectral-layer" aria-hidden="true"></svg>
      <div id="custom" class="offscreen spectral-layer" role="button" tabindex="0"></div>
      <div id="meaningful" class="offscreen orb">Account balance</div>
      <div id="parent" class="offscreen glow" aria-hidden="true"><button aria-label="Approve"></button></div>
      <span id="label" class="sr-only">Assistive description</span>
      <button id="hidden-control" class="sr-only">Approve</button>
      <a id="link-button" role="button" href="#" style="display:inline-block;width:30px;height:30px">Go</a>
      </body></html>`);
    const measurement = await inspectPage(page);
    const offscreen = new Map(measurement.offscreen.map((item) => [item.id, item]));
    assert.equal(offscreen.get("decoration").ariaHidden, true);
    assert.equal(offscreen.get("decoration").interactive, false);
    assert.equal(offscreen.get("decoration").hasInteractiveDescendant, false);
    assert.equal(offscreen.get("svg-decoration").className, "offscreen spectral-layer");
    assert.equal(offscreen.get("svg-decoration").interactive, false);
    assert.equal(offscreen.get("svg-decoration").contentEditable, false);
    assert.equal(offscreen.get("custom").role, "button");
    assert.equal(offscreen.get("custom").focusable, true);
    assert.equal(offscreen.get("custom").interactive, true);
    assert.equal(offscreen.get("meaningful").text, "Account balance");
    assert.equal(offscreen.get("parent").hasInteractiveDescendant, true);
    const fixed = new Map(measurement.fixedOversize.map((item) => [item.id, item]));
    assert.equal(fixed.get("label").intentionallyClipped, true);
    assert.equal(fixed.get("label").interactive, false);
    assert.equal(fixed.get("hidden-control").interactive, true);
    const targets = new Map(measurement.undersizedTargets.map((item) => [item.id, item]));
    assert.equal(targets.get("hidden-control").primaryControl, true);
    assert.equal(targets.get("link-button").primaryControl, true);

    // Decorative rows must not consume a cap that hides a later real control.
    await page.evaluate(() => {
      for (let index = 0; index < 40; index++) {
        const node = document.createElement("div");
        node.className = "offscreen spectral-layer";
        node.setAttribute("aria-hidden", "true");
        document.body.append(node);
      }
      const button = document.createElement("button");
      button.id = "last-control";
      button.className = "offscreen";
      button.textContent = "Last control";
      document.body.append(button);
    });
    const expanded = await inspectPage(page);
    assert.ok(expanded.offscreen.some((item) => item.id === "last-control"));
    assert.ok(expanded.fixedOversize.some((item) => item.id === "last-control"));
  } finally {
    await browser.close();
  }
});
