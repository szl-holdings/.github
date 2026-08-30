# Hugging Face Spaces consolidation plan — `SZLHOLDINGS`

**Status:** proposed · **Derived from:** full read-only audit of all 45 Spaces on
2026-08-30 (2,043 file entries listed, 1,766 files retrieved and scanned,
91 cross-Space identical-file groups found) · **Related:** #511

The org runs **45 Spaces**. Grouping them by byte-identical file content — not by
name similarity — shows twelve clusters where several Spaces are the same
artifact published more than once. Executing this plan leaves **26 Spaces**, with
no loss of published surface: every fold-in target already contains a superset of
the folded-in content, or the content moves in as a route/tab.

Every canonical choice below is justified by evidence in the repo trees, not by
preference.

---

## Why consolidate at all

Three concrete costs, all measured:

1. **Duplicated maintenance surface.** `a11oy` and `killinchu` share **49
   byte-identical files**, including `_vendor_blobs.py` and
   `live_snapshots/kev.json`. A fix to either is a fix to one copy.
2. **Estate-manifest drift.** `szl-estate-os`'s `Estate readiness evidence`
   workflow fails on its aggregate gate. Its live audit walks the GitHub org, the
   HF org and both domains against `estate/manifest.json`; 45 Spaces of which 38
   are private is exactly the kind of divergence that gate is designed to catch.
3. **Apparent size vs real surface.** Eight of the 45 are single-page static
   viewers of 6–8 files each, all sharing the same `style.css` and
   `SZL_ESTATE_MANAGED.json`. They read as eight products and behave as one.

---

## The twelve groups

### A — Single-page static receipt and gate viewers → `governed-receipt-verifier`

| Fold in | Files / size |
|---|---|
| `szl-provctl-live` | 8 / 40 KB |
| `receipt-chain-live` | 7 / 38 KB |
| `energy-attest-holo` | 8 / 34 KB |
| `governed-norm-holo` | 6 / 20 KB |
| `lambda-gate-holo` | 6 / 22 KB |
| `szl-blocked-live` | 6 / 20 KB |
| `szl-govsign-live` | 6 / 20 KB |
| `szl-quant-live` | 4 / 8 KB |

**Evidence:** all eight are `index.html` + an identical `style.css` +
`SZL_ESTATE_MANAGED.json` + `.well-known/szl-source.json`. The `style.css` in
`energy-attest-holo`, `receipt-chain-live` and `szl-provctl-live` is
byte-identical.

**Canonical:** `governed-receipt-verifier` — already public, and the only member
that ships an actual verifier (`verify.py`, a JSON schema, and valid/tampered
example receipts). The other eight become routes or tabs of it.

### B — Static estate and kernel hubs → `szl-estate-live`

Fold in `szl-forge-lab` (19 files), `energy-attested-runs` (12), and
`guardrail-receipt` (18). **Keep `szl-kernels-live`** — its kernel-contract
content is genuinely distinct. `energy-attested-runs` and `guardrail-receipt`
already share a schema file with `governed-receipt-verifier`.

**Canonical:** `szl-estate-live` (49 files, 459 KB) as the estate index.

### C — Merge sink → decide or drop

`evidence-studio`'s README calls it the "canonical merge sink for holographic and
receipt Spaces. One writer." It holds **7 files / 11 KB**. Either execute that
plan and make it the group-A/B target instead of `governed-receipt-verifier`, or
archive it. Do not leave a declared merge sink empty.

### D — IMMUNE → `immune`

`immune` (public, built Node investor demo) vs `immune-lattice` (private; README:
"Python kernel of github.com/szl-holdings/immune"). The kernel's source of truth
is the GitHub repo, so the HF mirror is a third copy.

**Canonical:** `immune`. Archive `immune-lattice`.

### E — Experimental surfaces → `szl-experiments`

`experiments` vs `szl-experiments`: same README text, **3 byte-identical files**
(`formulas/szl_unified_formulas.py`, `formulas/szl_chain_of_title.py`,
`RESTORED.md`), `app.py` Jaccard similarity 0.40, and 8 further files shared with
`a11oy`/`killinchu`.

**Canonical:** `szl-experiments` (namespaced). Archive `experiments`.

### F — KHIPU → `szl-khipu`

`szl-atelier` and `szl-khipu` share **11 byte-identical kernel files**
(`kit/kernels/*.py` == `szl_khipu/*.py`). `khipu-lab` is the same
`Dockerfile` + `server.py` + `index.html` skeleton with nothing added.

**Canonical:** `szl-khipu`. Archive `khipu-lab`. `szl-atelier` should import or
link the kernels rather than vendoring an eleventh copy.

### G — A11oy factory → `a11oy-factory`

`a11oy-factory` and `lyte-services` share **6 byte-identical files** — the entire
`a11oy_factory/` package (`compiler.py`, `cells.py`, `jobs.py`, `organs.py`,
`__init__.py`, `__main__.py`). `lyte-services`'s own README says
"BIND_AS_A11OY_PACKAGE. Not a second flagship."

**Canonical:** `a11oy-factory`. Archive `lyte-services`.

### H — Counsel vertical → `ayllu`

Both READMEs are titled "Ayllu Counsel". `counsel` is a 6-file / 15 KB adapter
pointing at GitHub `a11oy/verticals/counsel`; `ayllu` is 87 files with the full
agent and decision ledger.

**Canonical:** `ayllu`. Archive `counsel`.

### I — Terra / real-estate vertical → `terra-assurance`

Both are thin adapters over the same GitHub `a11oy/verticals/terra`.
`terra-assurance` ships `cases.json` evals and the kernel; `szl-real-estate`
(13 files / 17 KB) shares a file with `szl-sovereign-os`.

**Canonical:** `terra-assurance`. Archive `szl-real-estate`.

### J — Brain / retrieval → de-duplicate the corpus

The 538 KB `data/brain-corpus.public.jsonl` exists byte-identically in `ayllu`,
in `second-brain`, **and again** at `second-brain/hub/brain-corpus.public.jsonl`.
Three copies of the same corpus.

**Canonical:** `second-brain` as the HF public projection; GitHub stays source of
truth. Drop the copies in `ayllu` and `second-brain/hub/`.

### K — Docker "gateway skeleton" Spaces → keep the distinct products

Eleven Spaces share the same `Dockerfile` + `server.py` + `index.html` +
`SPACE_PROVENANCE.json` pattern. Keep the ones that are real products
(`llm-router-live`, `sda`, `cosmos`, `anatomy`). Archive `holographic`
(41 days stale, superseded by `szl-estate-live`/`anatomy`) and `nexus`
(6 files, one 26 KB `server.py`).

### L — Monorepo twins → extract, don't merge

`a11oy` and `killinchu` are both public, both 1,000–1,800 files, and share **49
byte-identical files** including the same `_vendor_blobs.py` and
`live_snapshots/kev.json` lineage.

**Do not merge these.** `killinchu` is the defense/counter-UAS demo and has its
own audience (2 likes, the only Space with any). Instead extract the shared 49
files into a package that both consume — this is the same fix as
`szl-holdings/szl-substrate` on the GitHub side.

---

## Net effect

| | Count |
|---|---|
| Spaces today | 45 |
| Archived by this plan | 19 |
| **Spaces after** | **26** |

Archive list: `szl-provctl-live`, `receipt-chain-live`, `energy-attest-holo`,
`governed-norm-holo`, `lambda-gate-holo`, `szl-blocked-live`, `szl-govsign-live`,
`szl-quant-live`, `szl-forge-lab`, `energy-attested-runs`, `guardrail-receipt`,
`immune-lattice`, `experiments`, `khipu-lab`, `lyte-services`, `counsel`,
`szl-real-estate`, `holographic`, `nexus`.

`evidence-studio` is deliberately not on that list — see group C, it needs a
decision first.

---

## Order of execution

Do these in order. Steps 1–2 are prerequisites, not optional.

1. **Fold content in before archiving anything.** Every archive above assumes the
   canonical Space already serves the folded-in surface. Verify per group, then
   archive.
2. **Update `estate/manifest.json` in `szl-holdings/szl-estate-os`** in the same
   change. Archiving a Space that the manifest still expects will trade one red
   `Estate readiness evidence` run for another.
3. Groups A and B first — largest count reduction, lowest risk, all static.
4. Groups D–I next — one archive each, all with an unambiguous canonical.
5. Group J — pure de-duplication, no archive.
6. Group K — `holographic` and `nexus`.
7. Group L — extraction work, schedule separately; it is a refactor, not a
   cleanup.
8. Group C last, once the merge-sink decision is made.

## Prerequisite: visibility and archive permissions

30 of the 45 Spaces are private, and the archive actions above require
`manage-repos` on the Hugging Face token. A token limited to `read-repos` +
`contribute-repos` can read and write files but **cannot** change visibility or
archive a Space. Whoever executes this needs an org token with `manage-repos`.

## Prerequisite: secret review before any private → public flip

The audit scanned all 1,766 retrieved files with 20 credential regexes, an
entropy pass, and filename passes for `.env*`/`*.pem`/`*.key`/`id_rsa*`.
**Zero real credentials were found.** Verdicts: 0 DO_NOT_PUBLISH,
9 NEEDS_REVIEW, 36 SAFE_TO_PUBLISH.

The 9 NEEDS_REVIEW, with the reason each needs a human rather than a scanner:

| Space | Why |
|---|---|
| `david-leads` | Commercially sensitive broker/lead-desk logic (`app/real_leads.py`, `app/tax_leads.py`, `app/wealth990.py`, `app/dealdesk_schema.sql`). No credentials — a business-confidentiality call. |
| `hatun-mcp` | Public MCP gateway; bearer-auth design and client configs are committed. Token values are placeholders (`szl_YOUR_KEY`) and `PUBKEY_szlholdings-ec-p256.pem` is a **public** key, but publishing exposes the auth surface. |
| `second-brain` | Ships a 538 KB corpus plus `train/train.jsonl`; self-labelled "public projection" but not fully machine-read. |
| `anatomy` | Two largest UI files could not be retrieved — coverage incomplete. |
| `experiments`, `szl-experiments` | Near-duplicates; decide the canonical before publishing either. |
| `a11oy-factory`, `szl-command-lab`, `yarqa` | Owner's personal email in `Signed-off-by:` trailers inside source files. |

**One privacy item spans the estate.** The owner's personal address appears in
DCO `Signed-off-by:` trailers embedded in source files across 10 Spaces
(`a11oy` 30 files, `killinchu` 9, `szl-command-lab` 7, `hatun-mcp` 2,
`a11oy-factory` 2, and one each in `yarqa`, `szl-khipu`, `szl-experiments`,
`second-brain`, `experiments`). It is already public via `a11oy`, `killinchu`
and `szl-khipu`. Flipping more Spaces widens it. Switching the DCO identity to a
role address before the flip is the cheap fix.

---

## Sources

- Space listing, visibility, SDK, last-modified: <https://huggingface.co/SZLHOLDINGS>
- File trees: `hf_fs ls hf://spaces/SZLHOLDINGS/<name> --recursive`
- Public-Space liveness: HTTP 200 verified on `szlholdings-{a11oy,killinchu,szl-khipu,immune}.hf.space` and `szlholdings-{governed-receipt-verifier,szl-atelier,readme}.static.hf.space`
- Estate readiness gate that consolidation must stay in step with: [szl-estate-os estate-readiness.yml](https://github.com/szl-holdings/szl-estate-os/blob/main/.github/workflows/estate-readiness.yml)
