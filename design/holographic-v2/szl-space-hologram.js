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
  var CURATED = {
    "a11oy": ["A11oy", "command-grid", "#05090f", "#0d1722", "#f3f8ff", "#9eb0c2", "#55ebd1", "#6f8cff"],
    "a11oy-enterprise": ["A11oy Enterprise", "command-grid", "#05090f", "#101723", "#f5f8ff", "#a1b0c2", "#5ee7d3", "#7d8fff"],
    "lyte": ["Lyte", "signal-aurora", "#04110f", "#0c211d", "#effffb", "#98b9b0", "#52ffd0", "#78a8ff"],
    "lyte-lattice": ["Lyte Lattice", "signal-aurora", "#04110f", "#0c211d", "#effffb", "#98b9b0", "#52ffd0", "#78a8ff"],
    "vessels": ["Vessels", "bathymetric-radar", "#03101b", "#0b2133", "#f0fbff", "#9ab5c5", "#5ce1ff", "#2a78ff"],
    "terra": ["Terra", "parcel-topography", "#07110c", "#122118", "#f6fff7", "#a8b8a9", "#80e89a", "#dda85e"],
    "szl-real-estate": ["Terra Real Estate", "parcel-topography", "#07110c", "#122118", "#f6fff7", "#a8b8a9", "#80e89a", "#dda85e"],
    "aegis": ["Aegis", "threat-lattice", "#120707", "#251111", "#fff5f3", "#c3a5a1", "#ff655e", "#ffb34d"],
    "prism-counsel": ["PRISM Counsel", "case-lines", "#090c17", "#151a2b", "#f8f9ff", "#aaafc3", "#7aa7ff", "#d7c4ff"],
    "counsel": ["PRISM Counsel", "case-lines", "#090c17", "#151a2b", "#f8f9ff", "#aaafc3", "#7aa7ff", "#d7c4ff"],
    "carlota-jo": ["Carlota Jo", "editorial-orbit", "#140b18", "#28142f", "#fff7ff", "#c3a9c5", "#e2a8ff", "#ef9b67"],
    "nexus": ["Nexus", "graph-mesh", "#080a19", "#15172d", "#f7f7ff", "#a9abc6", "#9a8cff", "#53e9ff"],
    "a11oy-factory": ["A11oy Factory", "build-circuit", "#090d08", "#171e13", "#fafff5", "#abb6a4", "#c9ff5c", "#7e9cff"],
    "szl-command-lab": ["SZL Command Lab", "build-circuit", "#090d08", "#171e13", "#fafff5", "#abb6a4", "#c9ff5c", "#7e9cff"],
    "ouroboros": ["Ouroboros", "recursive-weave", "#100c07", "#21180e", "#fffaf0", "#c1b49d", "#ffd36e", "#c094ff"],
    "szl-khipu": ["SZL KHIPU", "recursive-weave", "#100c07", "#21180e", "#fffaf0", "#c1b49d", "#ffd36e", "#c094ff"],
    "killinchu": ["Killinchu", "agent-swarm", "#110716", "#25102d", "#fff6ff", "#c4a5c8", "#ff74d4", "#68e8ff"],
    "immune": ["IMMUNE", "cell-membrane", "#061217", "#10272b", "#f1feff", "#9bb9bb", "#50e3d4", "#ff7f78"],
    "governed-receipt-verifier": ["Governed Receipt Verifier", "checksum-ledger", "#0b1013", "#172126", "#f5fbf8", "#a5b5ae", "#77d6a3", "#d7b96b"]
  };
  var PALETTES = [
    ["#07131a", "#102633", "#f2fbff", "#9ab4c2", "#64dcff", "#a88bff"],
    ["#130a10", "#291522", "#fff6fb", "#c2a2b3", "#ff7bc3", "#ffb56b"],
    ["#07140d", "#12281a", "#f5fff7", "#9db8a4", "#72efa0", "#5ad6ff"],
    ["#130e06", "#2a1d0e", "#fffaf0", "#c2b297", "#ffc66d", "#ff7d73"],
    ["#090a18", "#171932", "#f6f6ff", "#a6a8c4", "#878cff", "#54e4d7"],
    ["#0f0715", "#24102f", "#fff6ff", "#bca6c5", "#d88cff", "#74c6ff"],
    ["#061315", "#10272b", "#f1feff", "#9bb9bb", "#50e3d4", "#b4ed70"],
    ["#140808", "#2d1414", "#fff6f4", "#c2a3a0", "#ff6c63", "#e9cf6f"],
    ["#0a1115", "#16242c", "#f5fbff", "#a3b2bb", "#83c7ff", "#8df0bd"],
    ["#111006", "#282512", "#fffef0", "#beb99b", "#e5f36b", "#e8a85f"],
    ["#0b0714", "#1c122c", "#faf6ff", "#aea2c0", "#b697ff", "#ff82ad"],
    ["#07120f", "#12251f", "#f2fff9", "#9db6aa", "#75e8b4", "#c1a0ff"]
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
      shadow.innerHTML = '<style>:host{all:initial;display:block;position:relative;z-index:2147483000;color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}.bar{min-height:50px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:14px;padding:8px clamp(12px,2.3vw,30px);color:var(--szl-space-fg,#fff);background:color-mix(in srgb,var(--szl-space-bg,#05090f) 88%,transparent);border-bottom:1px solid color-mix(in srgb,var(--szl-space-accent,#55ebd1) 25%,transparent);box-shadow:0 14px 40px #0004;backdrop-filter:blur(18px) saturate(130%)}.identity{min-width:0;display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none}.mark{width:24px;height:24px;flex:none;border:1px solid color-mix(in srgb,var(--szl-space-accent) 70%,white 12%);border-radius:8px;background:radial-gradient(circle at 28% 25%,var(--szl-space-accent),transparent 35%),linear-gradient(145deg,color-mix(in srgb,var(--szl-space-accent-2) 70%,transparent),transparent 72%);box-shadow:0 0 25px color-mix(in srgb,var(--szl-space-accent) 28%,transparent);transform:rotate(8deg)}.copy{min-width:0;display:grid;gap:1px}.eyebrow{color:var(--szl-space-muted);font-size:9px;letter-spacing:.19em;text-transform:uppercase}.label{overflow:hidden;font-size:13px;font-weight:740;text-overflow:ellipsis;white-space:nowrap}nav{display:flex;gap:4px}nav a{min-height:34px;display:inline-flex;align-items:center;padding:6px 10px;border:1px solid transparent;border-radius:999px;color:var(--szl-space-muted);font-size:11px;font-weight:660;letter-spacing:.04em;text-decoration:none}nav a:hover,nav a:focus-visible,nav a[aria-current=page]{color:var(--szl-space-fg);border-color:color-mix(in srgb,var(--szl-space-accent) 38%,transparent);background:color-mix(in srgb,var(--szl-space-accent) 10%,transparent);outline:none}button{display:none;width:40px;height:36px;align-items:center;justify-content:center;border:1px solid color-mix(in srgb,var(--szl-space-accent) 32%,transparent);border-radius:10px;color:var(--szl-space-fg);background:transparent;cursor:pointer}@media(max-width:700px){button{display:inline-flex}nav{position:absolute;top:calc(100% + 7px);right:10px;min-width:190px;display:none;flex-direction:column;padding:8px;border:1px solid color-mix(in srgb,var(--szl-space-accent) 28%,transparent);border-radius:14px;background:color-mix(in srgb,var(--szl-space-bg) 96%,white 2%);box-shadow:0 20px 52px #0008}nav[data-open=true]{display:flex}nav a{min-height:42px}}@media(prefers-reduced-motion:reduce){.mark{transform:none}}@media(forced-colors:active){.bar,nav a,button,.mark{border:1px solid CanvasText}.mark{background:CanvasText}}</style><div class="bar" role="banner"><a class="identity" href="https://a-11-oy.com" aria-label="Open A11oy Command"><span class="mark" aria-hidden="true"></span><span class="copy"><span class="eyebrow">SZL holographic fabric</span><span class="label"></span></span></a><button type="button" aria-label="Open ecosystem navigation" aria-expanded="false">Menu</button><nav aria-label="SZL ecosystem" data-open="false"></nav></div>';
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
