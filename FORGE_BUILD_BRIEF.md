# FORGE_BUILD_BRIEF.md

> **Canonical execution brief for Forge (SZL build agent) and any delegated builder
> (Replit, Opus-tier coding agents, human devs).** One source of truth so parallel
> agents ship aligned, honest, verifiable work. Authored under Doctrine v11.

**Status:** ACTIVE · **Doctrine:** v11 LOCKED · **Last aligned:** 2026-06-13

---

## 0. Non-negotiable ground rules (read before any commit)

1. **Source of truth for all numbers/formulas** is
   [`szl-holdings/lutar-lean@main`](https://github.com/szl-holdings/lutar-lean) and
   [`.github/.github/data/lean_numbers.json`](https://github.com/szl-holdings/.github/blob/main/.github/data/lean_numbers.json).
   **Never invent or estimate a count or a formula.** Read it from there.
   Current canonical (measured 2026-05-31, kernel `c7c0ba17`):
   - **749** declarations · **14** unique axioms (15 raw, 1 dup) · **163** sorries
     (112 baseline + 51 Putnam; 146 non-comment)
   - **8** formulas locked-proven: `F1, F4, F7, F11, F12, F18, F19, F22`
   - **Λ-uniqueness = Conjecture 1** — NOT a theorem. Never write "Λ proven".
   - DOI `10.5281/zenodo.20434276`
2. **Honesty doctrine (HONESTY OVER CHECKLIST).** SLSA posture = **L1 honest
   (L2 roadmap)**. Do **not** claim SLSA L2-verified / L3 / FedRAMP / Iron Bank /
   CMMC as achieved. Cosign-signed + Rekor-logged is true today; say only that.
   When a service is down, show its real state (LIVE / PAUSED-503) — never
   fabricate data to fill a tab.
3. **Crypto facts.** a11oy signs receipts with **ECDSA P-256 (secp256r1)**,
   verified against a11oy's own `/cosign.pub`. The shared `szl-receipts` chain
   authority signs the chain with **Ed25519**. These are two distinct layers —
   do not "unify" them without proving cross-verification first.
4. **Deploy boundary.** Work lives in **GitHub + Hugging Face + Replit**. Do **NOT**
   push to Hetzner, `a11oy.net` DNS, or any production host without an explicit
   human approval gate. Open PRs; let CI/CD deploy. No prod changes from a
   one-line mandate.
5. **Repo conventions (from `.github/AGENTS.md`).**
   - Conventional Commits (`feat: fix: chore: docs: ci: refactor: test:`)
   - DCO sign-off on every commit (`git commit -s`)
   - All GitHub Actions **SHA-pinned** (enforced by `pin-check.yml`)
   - Squash-merge into `main`; one feature branch per task
   - Never force-merge past a failing **required** check. If a check is failing
     for an infra reason (e.g. stale scanner DB), fix the infra — don't override.

---

## 1. Organize & align (do first)

- Inventory every `szl-holdings/*` repo, `stephenlutar2-hash/*`, and HF Space
  under `SZLHOLDINGS`. Produce `coordination/REPO_INVENTORY.md` (repo, purpose,
  last-release, live URL, owner).
- **Version alignment pass:** every repo that cites kernel commit, doctrine
  version, or the 749/14/163 numbers must match `lean_numbers.json` exactly.
  Open one `chore(align): sync doctrine v11 + canonical numbers` PR per drifted repo.
- Reconcile naming: prefer **"service"** over legacy "organ" in new docs (matches
  current `hatun-mcp` + `developers` main).

## 2. CI / supply chain (in progress)

- ✅ **Grype CVE gate** stale-DB fix — `szl-uds-deployment` PR #73 (install grype
  + `grype db update` before scan). Unblocks #51, #57.
- Audit every repo's scanner workflows for the same stale-embedded-DB pattern;
  apply the #73 fix where present.
- Keep all SLSA/cosign/Rekor language **L1-honest** per rule 2.

## 3. anatomy → v2 interactive 3D (flagship visual)

Rebuild the anatomy 3D model into a **genius-grade interactive, dissectible** viewer.
- Stack: **react-three-fiber + three.js + drei**, Vite, TypeScript. Deploy preview
  to Replit web app and/or an HF Space.
- Features that "no one has dreamed of" but are real and shippable:
  - **Layered dissection:** skin → fascia → muscle → skeletal → organ, each a
    toggleable layer with opacity + click-to-isolate.
  - **Clip-plane scalpel:** draggable cross-section plane to "cut" and inspect interior.
  - **Label graph:** labels sourced from the anatomy genome-labels dataset; hover =
    definition, click = isolate + cite source.
  - **Receipt overlay:** every "what changed / why" interaction emits a Khipu-style
    provenance entry (ties the viewer to the platform's trust thesis).
  - **Real-time binding:** model state + labels fetched live from the anatomy API;
    honest empty-state when offline.
  - Mobile + desktop; keyboard + touch; WCAG-AA contrast.
- Land as PRs in the anatomy repo; do not overwrite v1 until v2 preview is approved.

## 4. Wire each app tab to real-time data

For each flagship (**a11oy, killinchu, sentra, rosie, amaru**):
- Each UI tab binds to its **live** `/api/<service>/v1/...` endpoint and the
  Hatun-MCP `tools/list` (verified: **25 static tools** = 19 `szl_*` + 6 governance).
- Honest reachability per rule 2: LIVE shows live data; PAUSED/503 shows the real
  state and a "restart needed" note — never mock data.

## 5. UDS payload + mesh

- Make the UDS bundle + `szl-mesh` deploy-ready and version-aligned.
- Keep signing/attestation honest (cosign-signed, Rekor, L1). a11oy key-init = P-256
  (already merged: `szl-uds-deployment` #71).

## 6. Definition of done (every task)

- [ ] Branch + Conventional-Commit title + DCO sign-off
- [ ] All **required** checks green for a real reason (no overrides)
- [ ] Numbers/claims trace to `lean_numbers.json` / lutar-lean
- [ ] No SLSA-L2+/compliance overclaim; honest reachability states
- [ ] PR description explains problem → fix → impact
- [ ] Nothing deployed to prod infra without human approval

---

*Co-Authored-By: Forge (SZL agent) · Doctrine v11.*
