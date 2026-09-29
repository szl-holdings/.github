/*
 * SZL Holographic Space Fabric v2
 * Shared navigation/accessibility with deterministic, per-Space identity.
 * No network access, analytics, storage, cookies, or application-state mutation.
 * SPDX-License-Identifier: Apache-2.0
 */
(function () {
  "use strict";
  if (window.__SZL_SPACE_HOLO_V2__) return;
  window.__SZL_SPACE_HOLO_V2__ = true;

  var VERSION = "2.0.0";
  // SZL Kanchay v1.0.0 (tokens.json). Every Space shares the a11oy ground roles:
  // color-a11oy-bg #0a0f1e, color-a11oy-surface #1b222c, color-a11oy-text #f5f7fa,
  // color-a11oy-text-sub #c9d2df. Accents come only from the Kanchay scales:
  // hatun #d7b96b (300) #e4cf99 (200) #cda64a (400), yuyay #5cc4bf (300) #8fd9d5 (200)
  // #34aaa4 (400), yawar #e57373 (300) #f0a3a3 (200); no violet or blue-violet. Each accent
  // is 6.4:1 or better on the ground. The motif (geometry) is each Space's differentiator.
  var CURATED = {
    "a11oy": ["A11oy", "command-grid", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#5cc4bf"],
    "a11oy-enterprise": ["A11oy Enterprise", "command-grid", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#5cc4bf"],
    "lyte": ["Lyte", "signal-aurora", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#d7b96b"],
    "lyte-lattice": ["Lyte Lattice", "signal-aurora", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#d7b96b"],
    "vessels": ["Vessels", "bathymetric-radar", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#8fd9d5", "#34aaa4"],
    "terra": ["Terra", "parcel-topography", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#cda64a", "#8fd9d5"],
    "szl-real-estate": ["Terra Real Estate", "parcel-topography", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#cda64a", "#8fd9d5"],
    "aegis": ["Aegis", "threat-lattice", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e57373", "#d7b96b"],
    "prism-counsel": ["PRISM Counsel", "case-lines", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#8fd9d5"],
    "counsel": ["PRISM Counsel", "case-lines", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#8fd9d5"],
    "carlota-jo": ["Carlota Jo", "editorial-orbit", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#f0a3a3", "#e4cf99"],
    "nexus": ["Nexus", "graph-mesh", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#e4cf99"],
    "a11oy-factory": ["A11oy Factory", "build-circuit", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#34aaa4"],
    "szl-command-lab": ["SZL Command Lab", "build-circuit", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#34aaa4"],
    "ouroboros": ["Ouroboros", "recursive-weave", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#8fd9d5"],
    "szl-khipu": ["SZL KHIPU", "recursive-weave", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#8fd9d5"],
    "killinchu": ["Killinchu", "agent-swarm", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#f0a3a3", "#5cc4bf"],
    "immune": ["IMMUNE", "cell-membrane", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#e57373"],
    "governed-receipt-verifier": ["Governed Receipt Verifier", "checksum-ledger", "#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#8fd9d5", "#d7b96b"]
  };
  var PALETTES = [
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#d7b96b"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#5cc4bf"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#8fd9d5", "#cda64a"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#34aaa4"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e57373", "#d7b96b"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#f0a3a3", "#8fd9d5"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#34aaa4", "#e4cf99"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#cda64a", "#8fd9d5"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#8fd9d5", "#e57373"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#d7b96b", "#f0a3a3"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#5cc4bf", "#e57373"],
    ["#0a0f1e", "#1b222c", "#f5f7fa", "#c9d2df", "#e4cf99", "#5cc4bf"]
  ];
  var MOTIFS = ["command-grid", "signal-aurora", "bathymetric-radar", "parcel-topography", "threat-lattice", "case-lines", "editorial-orbit", "graph-mesh", "build-circuit", "recursive-weave", "agent-swarm", "cell-membrane", "checksum-ledger"];
  var LINKS = [
    ["Command", "https://a-11-oy.com"],
    ["Proof", "https://a11oy.net"],
    ["Spaces", "https://huggingface.co/SZLHOLDINGS"],
    ["Source", "https://github.com/szl-holdings"]
  ];

  function slug(value) {
    return String(value || "").normalize("NFKD").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 96);
  }
  function hash(value) {
    var result = 0x811c9dc5;
    String(value || "szl-space").split("").forEach(function (character) {
      result ^= character.charCodeAt(0);
      result = Math.imul(result, 0x01000193) >>> 0;
    });
    return result >>> 0;
  }
  function spaceSlug() {
    var declared = document.documentElement.dataset.szlSpaceSlug || document.body && document.body.dataset ? document.body.dataset.szlSpaceSlug : "";
    if (declared) return slug(declared);
    var host = location.hostname.toLowerCase();
    var match = host.match(/^(?:szlholdings|szl-holdings)-(.+)\.hf\.space$/);
    if (match) return slug(match[1]);
    var title = slug(document.title.replace(/\s*[|·—-]\s*(hugging face|spaces?|szl holdings).*$/i, ""));
    return title || slug(host) || "szl-space";
  }
  function labelFor(id) {
    return id.split("-").filter(Boolean).map(function (part) { return part.charAt(0).toUpperCase() + part.slice(1); }).join(" ") || "SZL Space";
  }
  function resolveIdentity() {
    var id = spaceSlug();
    var keys = Object.keys(CURATED);
    var curatedKey = CURATED[id] ? id : keys.find(function (key) { return id.indexOf(key) >= 0 || key.indexOf(id) >= 0; });
    if (curatedKey) {
      var values = CURATED[curatedKey];
      return { id: id, label: values[0], motif: values[1], background: values[2], surface: values[3], foreground: values[4], muted: values[5], accent: values[6], accent2: values[7], source: "curated" };
    }
    var seed = hash(id);
    var palette = PALETTES[seed % PALETTES.length];
    return { id: id, label: labelFor(id), motif: MOTIFS[(seed >>> 8) % MOTIFS.length], background: palette[0], surface: palette[1], foreground: palette[2], muted: palette[3], accent: palette[4], accent2: palette[5], source: "deterministic" };
  }
  function applyIdentity(identity) {
    var root = document.documentElement;
    root.dataset.szlSpaceHoloV2 = "true";
    root.dataset.szlSpaceSlug = identity.id;
    root.dataset.szlSpaceMotif = identity.motif;
    root.dataset.szlSpaceThemeSource = identity.source;
    [["--szl-space-bg", identity.background], ["--szl-space-surface", identity.surface], ["--szl-space-fg", identity.foreground], ["--szl-space-muted", identity.muted], ["--szl-space-accent", identity.accent], ["--szl-space-accent-2", identity.accent2]].forEach(function (row) { root.style.setProperty(row[0], row[1]); });
  }
  function ambient() {
    if (document.getElementById("szl-space-holo-v2-ambient")) return;
    var node = document.createElement("div");
    node.id = "szl-space-holo-v2-ambient";
    node.setAttribute("aria-hidden", "true");
    ["field", "orbit", "beam", "scan", "nodes"].forEach(function (part) {
      var layer = document.createElement("span");
      layer.className = "szl-space-" + part;
      node.appendChild(layer);
    });
    document.body.insertBefore(node, document.body.firstChild);
  }
  function skipLink() {
    if (document.querySelector("[data-szl-space-skip]")) return;
    var main = document.querySelector("main, [role='main'], .gradio-container, [data-testid='stAppViewContainer']");
    if (!main) return;
    if (!main.id) main.id = "szl-space-main";
    var link = document.createElement("a");
    link.href = "#" + main.id;
    link.className = "szl-space-skip-link";
    link.dataset.szlSpaceSkip = "true";
    link.textContent = "Skip to main content";
    document.body.insertBefore(link, document.body.firstChild);
  }
  function defineBar(identity) {
    if (!window.customElements || customElements.get("szl-space-ecosystem-bar")) return;
    function SpaceBar() { return Reflect.construct(HTMLElement, [], SpaceBar); }
    SpaceBar.prototype = Object.create(HTMLElement.prototype);
    SpaceBar.prototype.constructor = SpaceBar;
    Object.setPrototypeOf(SpaceBar, HTMLElement);
    SpaceBar.prototype.connectedCallback = function () {
      if (this.shadowRoot) return;
      var shadow = this.attachShadow({ mode: "open" });
      shadow.innerHTML = '<style>:host{all:initial;display:block;position:relative;z-index:2147483000;color-scheme:dark;font-family:Inter,system-ui,sans-serif}*{box-sizing:border-box}.bar{min-height:50px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:14px;padding:8px clamp(12px,2.3vw,30px);color:var(--szl-space-fg,#f5f7fa);background:color-mix(in srgb,var(--szl-space-bg,#0a0f1e) 88%,transparent);border-bottom:1px solid color-mix(in srgb,var(--szl-space-accent,#d7b96b) 25%,transparent);box-shadow:0 14px 40px color-mix(in srgb,var(--szl-space-bg,#0a0f1e) 27%,transparent);backdrop-filter:blur(18px) saturate(130%)}.identity{min-width:0;display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none}.mark{width:24px;height:24px;flex:none;border:1px solid color-mix(in srgb,var(--szl-space-accent) 70%,var(--szl-space-fg) 12%);border-radius:8px;background:radial-gradient(circle at 28% 25%,var(--szl-space-accent),transparent 35%),linear-gradient(145deg,color-mix(in srgb,var(--szl-space-accent-2) 70%,transparent),transparent 72%);box-shadow:0 0 25px color-mix(in srgb,var(--szl-space-accent) 28%,transparent);transform:rotate(8deg)}.copy{min-width:0;display:grid;gap:1px}.eyebrow{color:var(--szl-space-muted);font-size:9px;letter-spacing:.19em;text-transform:uppercase}.label{overflow:hidden;font-size:13px;font-weight:740;text-overflow:ellipsis;white-space:nowrap}nav{display:flex;gap:4px}nav a{min-height:34px;display:inline-flex;align-items:center;padding:6px 10px;border:1px solid transparent;border-radius:999px;color:var(--szl-space-muted);font-size:11px;font-weight:660;letter-spacing:.04em;text-decoration:none}nav a:hover,nav a:focus-visible,nav a[aria-current=page]{color:var(--szl-space-fg);border-color:color-mix(in srgb,var(--szl-space-accent) 38%,transparent);background:color-mix(in srgb,var(--szl-space-accent) 10%,transparent);outline:none}nav a:focus-visible,button:focus-visible,.identity:focus-visible{outline:3px solid var(--szl-space-focus,#34aaa4);outline-offset:2px}button{display:none;width:40px;height:36px;align-items:center;justify-content:center;border:1px solid color-mix(in srgb,var(--szl-space-accent) 32%,transparent);border-radius:10px;color:var(--szl-space-fg);background:transparent;cursor:pointer}@media(max-width:700px){button{display:inline-flex}nav{position:absolute;top:calc(100% + 7px);right:10px;min-width:190px;display:none;flex-direction:column;padding:8px;border:1px solid color-mix(in srgb,var(--szl-space-accent) 28%,transparent);border-radius:14px;background:color-mix(in srgb,var(--szl-space-bg) 96%,var(--szl-space-fg) 2%);box-shadow:0 20px 52px color-mix(in srgb,var(--szl-space-bg) 53%,transparent)}nav[data-open=true]{display:flex}nav a{min-height:42px}}@media(prefers-reduced-motion:reduce){.mark{transform:none}}@media(forced-colors:active){.bar,nav a,button,.mark{border:1px solid CanvasText}.mark{background:CanvasText}}</style><div class="bar" role="banner"><a class="identity" href="https://a-11-oy.com" aria-label="Open A11oy Command"><span class="mark" aria-hidden="true"></span><span class="copy"><span class="eyebrow">SZL holographic fabric</span><span class="label"></span></span></a><button type="button" aria-label="Open ecosystem navigation" aria-expanded="false">Menu</button><nav aria-label="SZL ecosystem" data-open="false"></nav></div>';
      shadow.querySelector(".label").textContent = identity.label;
      var nav = shadow.querySelector("nav");
      LINKS.forEach(function (row) {
        var link = document.createElement("a");
        link.href = row[1];
        link.textContent = row[0];
        if (new URL(row[1]).hostname === location.hostname) link.setAttribute("aria-current", "page");
        nav.appendChild(link);
      });
      var button = shadow.querySelector("button");
      button.addEventListener("click", function () {
        var open = nav.dataset.open !== "true";
        nav.dataset.open = String(open);
        button.setAttribute("aria-expanded", String(open));
        button.textContent = open ? "Close" : "Menu";
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && nav.dataset.open === "true") {
          nav.dataset.open = "false";
          button.setAttribute("aria-expanded", "false");
          button.textContent = "Menu";
          button.focus();
        }
      });
    };
    customElements.define("szl-space-ecosystem-bar", SpaceBar);
  }
  function pointerEngine(reduced) {
    var fine = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    if (reduced || !fine) return;
    var root = document.documentElement;
    var frame = 0;
    var x = innerWidth / 2;
    var y = innerHeight / 3;
    function draw() {
      frame = 0;
      root.style.setProperty("--szl-space-x", x.toFixed(1) + "px");
      root.style.setProperty("--szl-space-y", y.toFixed(1) + "px");
      root.style.setProperty("--szl-space-nx", (((x / Math.max(innerWidth, 1)) - .5) * 2).toFixed(4));
      root.style.setProperty("--szl-space-ny", (((y / Math.max(innerHeight, 1)) - .5) * 2).toFixed(4));
    }
    addEventListener("pointermove", function (event) { x = event.clientX; y = event.clientY; if (!frame) frame = requestAnimationFrame(draw); }, { passive: true });
    draw();
  }
  function lowPower() {
    return Boolean(navigator.connection && navigator.connection.saveData) || Number(navigator.hardwareConcurrency || 8) <= 4 || Number(navigator.deviceMemory || 8) <= 4;
  }
  function boot() {
    if (!document.body) return;
    var identity = resolveIdentity();
    var reduced = Boolean(matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
    applyIdentity(identity);
    document.documentElement.dataset.szlSpacePower = lowPower() ? "low" : "full";
    document.documentElement.dataset.szlSpaceState = document.hidden ? "paused" : "active";
    ambient();
    skipLink();
    defineBar(identity);
    if (!document.documentElement.hasAttribute("data-szl-space-no-shell") && !document.querySelector("szl-space-ecosystem-bar")) document.body.insertBefore(document.createElement("szl-space-ecosystem-bar"), document.body.firstChild);
    pointerEngine(reduced);
    document.addEventListener("visibilitychange", function () { document.documentElement.dataset.szlSpaceState = document.hidden ? "paused" : "active"; });
    document.dispatchEvent(new CustomEvent("szl:space-hologram-ready", { detail: Object.freeze({ version: VERSION, slug: identity.id, motif: identity.motif, source: identity.source, power: document.documentElement.dataset.szlSpacePower }) }));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
}());
