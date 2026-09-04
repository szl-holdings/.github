/*
 * SZL Frontier Design Kernel v1.0.0
 * Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
 *
 * Progressive enhancement only: no CDN, eval, analytics, cookies, storage,
 * network fetch, innerHTML, framework dependency, or mutation authority.
 */
(function () {
  "use strict";

  var VERSION = "1.0.0";
  var BRANDS = {
    a11oy: {
      name: "A11oy",
      mark: "◈",
      descriptor: "Governed command fabric",
      home: "https://a-11-oy.com/"
    },
    killinchu: {
      name: "Killinchu",
      mark: "▲",
      descriptor: "Aerial intelligence & defense",
      home: "https://killinchu.net/"
    },
    hatun: {
      name: "Hatun",
      mark: "◎",
      descriptor: "Sovereign orchestration layer",
      home: "https://a-11-oy.com/wires"
    }
  };

  function safeBrand(value) {
    value = String(value || "").toLowerCase().trim();
    return Object.prototype.hasOwnProperty.call(BRANDS, value) ? value : "a11oy";
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (typeof text === "string") node.textContent = text;
    return node;
  }

  function externalLink(label, href, current) {
    var link = element("a", "szl-frontier-rail__link", label);
    link.href = href;
    link.rel = "noopener noreferrer";
    if (current) {
      link.setAttribute("aria-current", "page");
      link.removeAttribute("target");
    } else {
      link.target = "_blank";
    }
    return link;
  }

  function buildRail(brandKey) {
    var brand = BRANDS[brandKey];
    var rail = element("header", "szl-frontier-rail");
    rail.id = "szl-frontier-rail";
    rail.setAttribute("data-szl-frontier-version", VERSION);
    rail.setAttribute("data-scrolled", "false");
    rail.setAttribute("aria-label", "SZL ecosystem navigation");

    var inner = element("div", "szl-frontier-rail__inner");
    var identity = externalLink(brand.name, brand.home, true);
    identity.className = "szl-frontier-rail__brand";

    var mark = element("span", "szl-frontier-rail__mark", brand.mark);
    mark.setAttribute("aria-hidden", "true");
    var brandLabel = element("span", "", brand.name);
    identity.replaceChildren(mark, brandLabel);

    var descriptor = element(
      "span",
      "szl-frontier-rail__descriptor",
      brand.descriptor
    );

    var navigation = element("nav", "szl-frontier-rail__nav");
    navigation.setAttribute("aria-label", "SZL products");
    Object.keys(BRANDS).forEach(function (key) {
      navigation.appendChild(
        externalLink(BRANDS[key].name, BRANDS[key].home, key === brandKey)
      );
    });

    var state = element("span", "szl-frontier-chip", "Public surface");
    state.setAttribute("title", "The page shell loaded. This is not a backend health claim.");

    inner.appendChild(identity);
    inner.appendChild(descriptor);
    inner.appendChild(navigation);
    inner.appendChild(state);
    rail.appendChild(inner);
    return rail;
  }

  function installRevealObserver() {
    var targets = Array.prototype.slice.call(
      document.querySelectorAll("[data-szl-frontier-reveal]")
    );
    if (!targets.length) return;

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (_error) {
      reduceMotion = false;
    }

    if (reduceMotion || !("IntersectionObserver" in window)) {
      targets.forEach(function (target) {
        target.setAttribute("data-visible", "true");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.setAttribute("data-visible", "true");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    targets.forEach(function (target) { observer.observe(target); });
  }

  function installScrollState(rail) {
    var queued = false;
    function update() {
      rail.setAttribute("data-scrolled", window.scrollY > 8 ? "true" : "false");
      queued = false;
    }
    function onScroll() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(update);
    }
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  function promoteExplicitComponents() {
    document.querySelectorAll("[data-szl-card]").forEach(function (node) {
      node.classList.add("szl-frontier-card");
    });
    document.querySelectorAll("[data-szl-button]").forEach(function (node) {
      node.classList.add("szl-frontier-button");
    });
    document.querySelectorAll("[data-szl-button='quiet']").forEach(function (node) {
      node.classList.add("szl-frontier-button--quiet");
    });
  }

  function boot() {
    if (!document.body) return;
    var brandKey = safeBrand(document.body.getAttribute("data-szl-frontier"));
    document.body.setAttribute("data-szl-frontier", brandKey);
    document.body.classList.add("szl-frontier");

    var rail = document.getElementById("szl-frontier-rail");
    if (!rail) {
      rail = buildRail(brandKey);
      document.body.insertBefore(rail, document.body.firstChild);
    }

    promoteExplicitComponents();
    installRevealObserver();
    installScrollState(rail);

    var detail = Object.freeze({
      schema: "szl.frontier-design.ready/v1",
      version: VERSION,
      brand: brandKey,
      authority: "PRESENTATION_ONLY"
    });
    window.SZL_FRONTIER_DESIGN = detail;
    document.dispatchEvent(new CustomEvent("szl:frontier-ready", { detail: detail }));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
