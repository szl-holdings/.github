/*
 * SZL Public Experience v3.1
 * Viewport-aware, dependency-free adaptation for Holographic Space Fabric v2.
 * No network, analytics, cookies, storage, or product-state mutation.
 * SPDX-License-Identifier: Apache-2.0
 */
(function () {
  "use strict";

  if (window.__SZL_PUBLIC_EXPERIENCE_V3__) return;
  window.__SZL_PUBLIC_EXPERIENCE_V3__ = true;

  var ROOT = document.documentElement;
  var raf = 0;
  var observer = null;
  var stopObserverTimer = 0;
  var settleTimer = 0;
  var TARGET_SELECTOR = [
    "a[href]",
    "button",
    "input:not([type='hidden'])",
    "select",
    "textarea",
    "summary",
    "[role='button']",
    "[role='tab']",
    "[role='menuitem']",
    "[role='option']",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  function viewportWidth() {
    return Math.max(1, Math.round((window.visualViewport && window.visualViewport.width) || window.innerWidth || ROOT.clientWidth || 1));
  }

  function viewportHeight() {
    return Math.max(1, Math.round((window.visualViewport && window.visualViewport.height) || window.innerHeight || ROOT.clientHeight || 1));
  }

  function tier(width) {
    if (width < 480) return "phone";
    if (width < 768) return "compact";
    if (width < 1024) return "tablet";
    if (width < 1440) return "desktop";
    if (width < 1920) return "wide";
    if (width < 2560) return "theatre";
    return "ultrawide";
  }

  function orientation(width, height) {
    return width >= height ? "landscape" : "portrait";
  }

  function visible(node, style, rect) {
    if (!node || !style || !rect) return false;
    if (node.closest && node.closest("[aria-hidden='true']")) return false;
    if (node.hasAttribute && node.hasAttribute("disabled")) return false;
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) > 0 && style.pointerEvents !== "none" &&
      rect.width > 0 && rect.height > 0;
  }

  function inlineProseLink(node, style) {
    return node.tagName === "A" && style.display === "inline" &&
      Boolean(node.closest("p,li,dd,dt,figcaption,blockquote"));
  }

  function enhanceHitTarget(node) {
    if (!node || node.nodeType !== 1 || !node.matches(TARGET_SELECTOR)) return;
    if (node.dataset.szlTouchTargetV31 === "true") return;
    var style = window.getComputedStyle(node);
    var rect = node.getBoundingClientRect();
    if (!visible(node, style, rect) || inlineProseLink(node, style)) return;
    if (rect.width + 0.5 < 44 || rect.height + 0.5 < 44) {
      node.dataset.szlTouchTargetV31 = "true";
    }
  }

  function enhanceHitTargets(scope) {
    var root = scope && scope.querySelectorAll ? scope : document;
    if (scope && scope.nodeType === 1 && scope.matches && scope.matches(TARGET_SELECTOR)) {
      enhanceHitTarget(scope);
    }
    root.querySelectorAll(TARGET_SELECTOR).forEach(enhanceHitTarget);
  }

  function applyViewportState() {
    raf = 0;
    var width = viewportWidth();
    var height = viewportHeight();
    ROOT.dataset.szlPublicExperienceV3 = "true";
    ROOT.dataset.szlPublicExperienceVersion = "3.1";
    ROOT.dataset.szlViewportTier = tier(width);
    ROOT.dataset.szlViewportOrientation = orientation(width, height);
    ROOT.style.setProperty("--szl-viewport-width", width + "px");
    ROOT.style.setProperty("--szl-viewport-height", height + "px");
    enhanceHitTargets(document);
  }

  function scheduleViewportState() {
    if (raf) return;
    raf = window.requestAnimationFrame(applyViewportState);
  }

  function responsiveBarStyle() {
    return [
      ":host{position:sticky!important;top:0!important;inline-size:100%!important;max-inline-size:100%!important;z-index:2147483000!important}",
      ".bar{min-height:56px!important;padding-block:8px!important;padding-inline:max(clamp(12px,2.3vw,30px),env(safe-area-inset-left,0px)) max(clamp(12px,2.3vw,30px),env(safe-area-inset-right,0px))!important}",
      "nav a,button{box-sizing:border-box!important;min-width:44px!important;min-height:44px!important;touch-action:manipulation!important}",
      "nav{max-width:100%!important}",
      "@media(max-width:700px){.bar{grid-template-columns:minmax(0,1fr) auto!important;gap:8px!important}.identity{min-width:0!important}.label{max-width:min(58vw,360px)!important}.eyebrow{font-size:8px!important}button{display:inline-flex!important}nav{position:fixed!important;top:calc(64px + env(safe-area-inset-top,0px))!important;right:max(8px,env(safe-area-inset-right,0px))!important;left:max(8px,env(safe-area-inset-left,0px))!important;max-height:min(72dvh,540px)!important;overflow:auto!important;overscroll-behavior:contain!important;padding:8px!important;border-radius:14px!important}nav a{justify-content:flex-start!important;padding-inline:14px!important}}",
      "@media(max-width:420px){.bar{min-height:54px!important;padding-block:5px!important}.copy{gap:0!important}.label{font-size:12px!important}.mark{width:22px!important;height:22px!important}nav{top:calc(60px + env(safe-area-inset-top,0px))!important}}",
      "@media(min-width:1440px){.bar{min-height:60px!important;padding-inline:max(40px,env(safe-area-inset-left,0px)) max(40px,env(safe-area-inset-right,0px))!important}nav a{padding-inline:14px!important}}",
      "@media(min-width:1920px){.bar{min-height:64px!important;padding-inline:max(64px,env(safe-area-inset-left,0px)) max(64px,env(safe-area-inset-right,0px))!important}.label{font-size:14px!important}nav{gap:8px!important}nav a{min-height:48px!important;padding-inline:18px!important;font-size:12px!important}}",
      "@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}",
      "@media(forced-colors:active){.bar,nav,nav a,button{forced-color-adjust:auto!important}}"
    ].join("");
  }

  function enhanceBar(bar) {
    if (!bar || !bar.shadowRoot || bar.dataset.szlResponsiveV31 === "true") return;
    var prior = bar.shadowRoot.querySelector("style[data-szl-responsive-v3]");
    if (prior) prior.remove();
    var style = document.createElement("style");
    style.dataset.szlResponsiveV31 = "true";
    style.textContent = responsiveBarStyle();
    bar.shadowRoot.appendChild(style);
    bar.dataset.szlResponsiveV31 = "true";

    var nav = bar.shadowRoot.querySelector("nav");
    var button = bar.shadowRoot.querySelector("button");
    if (nav) {
      nav.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
          nav.dataset.open = "false";
          if (button) {
            button.setAttribute("aria-expanded", "false");
            button.textContent = "Menu";
          }
        });
      });
    }
  }

  function enhanceBars() {
    document.querySelectorAll("szl-space-ecosystem-bar").forEach(enhanceBar);
  }

  function settle() {
    enhanceBars();
    enhanceHitTargets(document);
  }

  function startObserver() {
    settle();
    if (!window.MutationObserver || observer) return;
    observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (!node || node.nodeType !== 1) return;
          if (node.matches && node.matches("szl-space-ecosystem-bar")) enhanceBar(node);
          if (node.querySelectorAll) node.querySelectorAll("szl-space-ecosystem-bar").forEach(enhanceBar);
          enhanceHitTargets(node);
        });
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    stopObserverTimer = window.setTimeout(function () {
      if (observer) observer.disconnect();
      observer = null;
      stopObserverTimer = 0;
      settle();
    }, 30000);
  }

  function initialize() {
    applyViewportState();
    startObserver();
    if (window.customElements && customElements.whenDefined) {
      customElements.whenDefined("szl-space-ecosystem-bar").then(settle).catch(function () {});
    }
    settleTimer = window.setTimeout(settle, 300);
  }

  window.addEventListener("resize", scheduleViewportState, { passive: true });
  window.addEventListener("orientationchange", scheduleViewportState, { passive: true });
  window.addEventListener("load", settle, { once: true });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", scheduleViewportState, { passive: true });
    window.visualViewport.addEventListener("scroll", scheduleViewportState, { passive: true });
  }
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) scheduleViewportState();
  });
  window.addEventListener("pagehide", function () {
    if (observer) observer.disconnect();
    if (stopObserverTimer) window.clearTimeout(stopObserverTimer);
    if (settleTimer) window.clearTimeout(settleTimer);
    if (raf) window.cancelAnimationFrame(raf);
  }, { once: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
}());
