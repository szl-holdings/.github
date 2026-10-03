// Daily badge-drift refresher for SZLHOLDINGS dataset cards.
// Recomputes each dataset's file count (recursive live tree) and license
// (README front-matter) and rewrites ONLY the files/license badge values when
// they drifted. Body text is never touched — the edit is a targeted regex on
// the shields.io badge URL inside the existing badge row.
//
// Badge format matches .agents/estate-audit/hf-dataset-card-upgrade.mjs:
//   files   -> 5b8dee, flat-square
//   license -> 7e8aa3, flat-square
//
// FAIL-CLOSED: missing token, non-JSON tree, or a failed commit exits 1 —
// drift is never silently left in place while the job reports green.
//
// Usage: HF_TOKEN=... node hf_dataset_badge_refresh.mjs [--publish]
//   default = dry run (report drift, commit nothing)

import { pathToFileURL } from "node:url";

const TOKEN = process.env.HF_TOKEN || process.env.HUGGINGFACE_API_TOKEN;
const HF = TOKEN ? { Authorization: "Bearer " + TOKEN } : {};
const PUBLISH = process.argv.includes("--publish");
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Lake README.md is part of one atomic, source-owned closed publication.
// A cross-estate badge commit would create a second writer and invalidate the
// index/predecessor closure. Other datasets remain in the existing refresher
// while their publication ownership is inventoried separately.
export const SOURCE_OWNED_DATASETS = new Set([
  "SZLHOLDINGS/szl-lake",
]);

const SOURCE_OWNED_DATASET_KEYS = new Set(
  [...SOURCE_OWNED_DATASETS].map(id => id.toLowerCase()),
);

export function isSourceOwnedDataset(id) {
  return typeof id === "string" && SOURCE_OWNED_DATASET_KEYS.has(id.toLowerCase());
}

export function assertBadgeWriteAllowed(id) {
  if (isSourceOwnedDataset(id)) {
    throw new Error(`${id}: badge write refused; dataset is source-owned`);
  }
}

// Same value-escaping as the upgrade builder (shields.io path segment)
const esc = s => s.replace(/-/g, "--").replace(/ /g, "%20").replace(/·/g, "%C2%B7");

const FILES_RE = /(\[!\[files\]\(https:\/\/img\.shields\.io\/badge\/files-)([^-]*(?:--[^-]*)*)(-5b8dee\?style=flat-square\))/;
const LICENSE_RE = /(\[!\[license\]\(https:\/\/img\.shields\.io\/badge\/license-)([^-]*(?:--[^-]*)*)(-7e8aa3\?style=flat-square\))/;

async function jfetch(url) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const r = await fetch(url, { headers: HF });
    if (r.status === 429) { await sleep(2000 * (attempt + 1)); continue; }
    return r;
  }
  throw new Error("429 persisted: " + url);
}

async function listDatasets() {
  const out = [];
  let url = "https://huggingface.co/api/datasets?author=SZLHOLDINGS&limit=100";
  while (url) {
    const r = await jfetch(url);
    if (!r.ok) throw new Error(`dataset list HTTP ${r.status}`);
    for (const d of await r.json()) out.push(d.id);
    const link = r.headers.get("link");
    url = link && link.includes('rel="next"') ? link.match(/<([^>]+)>;\s*rel="next"/)[1] : null;
  }
  return out;
}

// Recursive file count from the live tree (matches the original badge semantics)
async function countFiles(id) {
  let url = `https://huggingface.co/api/datasets/${id}/tree/main?limit=1000&recursive=true`;
  let files = 0;
  while (url) {
    const r = await jfetch(url);
    const j = await r.json();
    if (!Array.isArray(j)) throw new Error(`tree ${id}: ${JSON.stringify(j).slice(0, 120)}`);
    for (const e of j) if (e.type !== "directory") files++;
    const link = r.headers.get("link");
    url = link && link.includes('rel="next"') ? link.match(/<([^>]+)>;\s*rel="next"/)[1] : null;
  }
  return files;
}

export async function publishReadmeCommit({
  id,
  content,
  nfiles,
  license,
  fetch = globalThis.fetch,
  headers = HF,
}) {
  assertBadgeWriteAllowed(id);
  const body = [
    JSON.stringify({ key: "header", value: { summary: `docs: refresh badge stats (files=${nfiles}, license=${license})`, description: "Automated badge-row refresh from the live tree; body preserved verbatim." } }),
    JSON.stringify({ key: "file", value: { path: "README.md", content: Buffer.from(content).toString("base64"), encoding: "base64" } }),
  ].join("\n");
  return fetch(`https://huggingface.co/api/datasets/${id}/commit/main`, { method: "POST", headers: { ...headers, "Content-Type": "application/x-ndjson" }, body });
}

async function main() {
  if (!TOKEN) {
    console.error("FATAL: HF_TOKEN is not set — cannot audit private datasets or commit. Refusing to run public-only.");
    process.exitCode = 1;
    return;
  }

  let drifted = 0, checked = 0, skipped = 0, failed = 0;
  const ids = await listDatasets();
  console.log(`datasets: ${ids.length}`);
  for (const id of ids) {
    const d = id.split("/")[1];
    if (isSourceOwnedDataset(id)) {
      console.log(`SKIP ${d}: source-owned atomic publisher`);
      skipped++;
      continue;
    }
    try {
      const rr = await jfetch(`https://huggingface.co/datasets/${id}/raw/main/README.md`);
      if (!rr.ok) { console.log(`SKIP ${d}: README HTTP ${rr.status}`); skipped++; continue; }
      const txt = await rr.text();
      if (!FILES_RE.test(txt)) { console.log(`SKIP ${d}: no house files badge`); skipped++; continue; }
      checked++;
      const nfiles = await countFiles(id);
      const lic = (txt.match(/^license:\s*(\S+)/m) || [])[1] || "other";
      let out = txt.replace(FILES_RE, (_, a, cur, z) => a + esc(String(nfiles)) + z);
      out = out.replace(LICENSE_RE, (_, a, cur, z) => a + esc(lic) + z);
      if (out === txt) { console.log(`ok   ${d}: files=${nfiles}, license=${lic}`); continue; }
      drifted++;
      const oldFiles = (txt.match(FILES_RE) || [])[2];
      const oldLic = (txt.match(LICENSE_RE) || [])[2];
      console.log(`DRIFT ${d}: files ${oldFiles} -> ${esc(String(nfiles))}, license ${oldLic} -> ${esc(lic)}${PUBLISH ? "" : " (dry run)"}`);
      if (PUBLISH) {
        const r = await publishReadmeCommit({
          id, content: out, nfiles, license: lic,
        });
        console.log(`  publish ${d}: ${r.status}${r.ok ? "" : " " + (await r.text()).slice(0, 200)}`);
        if (!r.ok) failed++;
        await sleep(400);
      }
    } catch (e) {
      console.error(`ERROR ${d}: ${e.message}`);
      failed++;
    }
    await sleep(200);
  }
  console.log(`summary: checked=${checked} drifted=${drifted} skipped=${skipped} failed=${failed}`);
  if (failed > 0) process.exitCode = 1;
}

const invokedPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (import.meta.url === invokedPath) await main();
