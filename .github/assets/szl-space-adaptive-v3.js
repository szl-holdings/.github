/*
 * SZL Space Adaptive Theatre v3
 * Generic progressive controller for source-owned Hugging Face applications.
 * No fetch, tracking, cookies, storage, or fabricated operational state.
 */
(function () {
  "use strict";

  if (window.__SZL_SPACE_ADAPTIVE_V3__) return;
  window.__SZL_SPACE_ADAPTIVE_V3__ = true;

  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var coarse = window.matchMedia("(pointer: coarse)");
  var state = { raf: 0, mode: "", orientation: "", motion: "", observer: null };

  function viewport() {
    var visual = window.visualViewport;
    return {
      width: Math.max(1, Math.round(visual ? visual.width : window.innerWidth)),
      height: Math.max(1, Math.round(visual ? visual.height : window.innerHeight)),
    };
  }

  function modeFor(width) {
    if (width < 640) return "mobile";
    if (width < 1024) return "tablet";
    if (width < 1680) return "desktop";
    return "theatre";
  }

  function constrained() {
    var connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    var memory = Number(navigator.deviceMemory || 0);
    var cores = Number(navigator.hardwareConcurrency || 0);
    return Boolean(connection && connection.saveData) || (memory > 0 && memory <= 2) || (cores > 0 && cores <= 2);
  }

  function motionFor() {
    if (reduced.matches || constrained()) return "quiet";
    if (coarse.matches || window.innerWidth < 900) return "balanced";
    return "full";
  }

  function emit(name, detail) {
    try { window.dispatchEvent(new CustomEvent(name, { detail: detail })); }
    catch (_) { return; }
  }

  function update() {
    state.raf = 0;
    var size = viewport();
    var mode = modeFor(size.width);
    var orientation = size.width >= size.height ? "landscape" : "portrait";
    var motion = motionFor();
    root.style.setProperty("--szl-space-vw", (size.width / 100).toFixed(3) + "px");
    root.style.setProperty("--szl-space-vh", (size.height / 100).toFixed(3) + "px");
    root.dataset.szlSpaceAdaptiveV3 = "ready";
    root.dataset.szlSpaceDisplayMode = mode;
    root.dataset.szlSpaceOrientation = orientation;
    root.dataset.szlSpaceMotion = motion;
    if (mode !== state.mode || orientation !== state.orientation || motion !== state.motion) {
      state.mode = mode;
      state.orientation = orientation;
      state.motion = motion;
      emit("szl:space-displaymode", { mode: mode, orientation: orientation, motion: motion, width: size.width, height: size.height });
    }
  }

  function schedule() {
    if (state.raf) return;
    state.raf = window.requestAnimationFrame(update);
  }

  function visible(element) {
    var style = window.getComputedStyle(element);
    var rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }

  function normalizeScrollableData() {
    document.querySelectorAll("table").forEach(function (table) {
      if (table.parentElement && table.parentElement.matches(".szl-space-table-wrap,[data-szl-space-scrollable='table']")) return;
      var wrapper = document.createElement("div");
      wrapper.className = "szl-space-table-wrap";
      wrapper.dataset.szlSpaceScrollable = "table";
      wrapper.tabIndex = 0;
      wrapper.setAttribute("role", "region");
      wrapper.setAttribute("aria-label", table.getAttribute("aria-label") || "Scrollable data table");
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    });
    document.querySelectorAll("pre").forEach(function (pre) {
      pre.dataset.szlSpaceScrollable = "code";
      if (!pre.hasAttribute("tabindex")) pre.tabIndex = 0;
      if (!pre.hasAttribute("aria-label")) pre.setAttribute("aria-label", "Scrollable code or record");
    });
  }

  function labelIconControls() {
    document.querySelectorAll("button,[role='button'],a").forEach(function (control) {
      if (!visible(control)) return;
      var text = (control.textContent || "").trim();
      if (text || control.hasAttribute("aria-label") || control.hasAttribute("aria-labelledby")) return;
      var title = (control.getAttribute("title") || "").trim();
      if (title) control.setAttribute("aria-label", title);
    });
  }

  function observePanels() {
    if (!("IntersectionObserver" in window) || reduced.matches) return;
    var panels = Array.prototype.slice.call(document.querySelectorAll(
      ".szl-space-card,.szl-holo-card,.szl-panel,.panel,.card,[data-szl-space-panel],main > section"
    )).filter(visible).slice(0, 40);
    if (!panels.length) return;
    state.observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        entry.target.dataset.szlSpaceInview = entry.isIntersecting ? "true" : "false";
        if (entry.isIntersecting) state.observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    panels.forEach(function (panel) {
      panel.classList.add("szl-space-enter");
      panel.dataset.szlSpaceInview = "false";
      state.observer.observe(panel);
    });
  }

  function localAnchor(event) {
    var anchor = event.target.closest && event.target.closest("a[href^='#']");
    if (!anchor) return;
    var href = anchor.getAttribute("href");
    if (!href || href === "#") return;
    var target;
    try { target = document.querySelector(href); }
    catch (_) { return; }
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: reduced.matches ? "auto" : "smooth", block: "start" });
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    history.replaceState(null, "", href);
  }

  function keepFocusVisible() {
    document.addEventListener("focusin", function (event) {
      var target = event.target;
      if (!(target instanceof HTMLElement)) return;
      window.requestAnimationFrame(function () {
        var rect = target.getBoundingClientRect();
        if (rect.top < 16 || rect.bottom > window.innerHeight - 16) {
          target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
        }
      });
    });
  }

  function start() {
    if (!document.body) return;
    update();
    normalizeScrollableData();
    labelIconControls();
    observePanels();
    keepFocusVisible();
    window.addEventListener("resize", schedule, { passive: true });
    window.addEventListener("orientationchange", schedule, { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", schedule, { passive: true });
      window.visualViewport.addEventListener("scroll", schedule, { passive: true });
    }
    [reduced, coarse].forEach(function (query) {
      if (query.addEventListener) query.addEventListener("change", schedule);
      else if (query.addListener) query.addListener(schedule);
    });
    document.addEventListener("click", localAnchor);
    emit("szl:space-adaptive-ready", { version: "3.0.0", mode: state.mode, orientation: state.orientation, motion: state.motion });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());
