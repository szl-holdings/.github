# T01 ouroboros-thesis v13 — Fix Squad A STATUS

**Track:** 01 ouroboros-thesis v13  
**Author:** Stephen P. Lutar Jr. &lt;stephen@szlholdings.com&gt; ORCID 0009-0001-0110-4173  
**Doctrine binding:** v2  
**Date:** 2026-05-13  
**Produced by:** GAP-03 Builder (Phase 1 Audit remediation)  
**Audit source:** `audit_phase1/AUDIT_REPORT.md` §2 Track 01 + §1 GAP-03  
**Status:** CONDITIONAL_PASS — 4 of 9 axes below 0.90; re-loop required (see §Remediation)

---

## Fixes Applied (4 structural fixes, 0 bandaids)

### Fix 1 — License slug: `Apache-2.0` → `cc-by-4.0` (BLOCKER)

**File:** `fix_squads/01_thesis/A/zenodo_metadata.json`  
**Problem:** Initial deposit metadata carried `"Apache-2.0"` license, which is not correct for a thesis document; the Zenodo vocabulary requires lowercase `cc-by-4.0` for a CC BY 4.0 work.  
**Fix:** `"license": "cc-by-4.0"` — confirmed in zenodo_metadata.json line 43.  
**Verification:** `replay_run_1.txt` CHECK 1: `license: cc-by-4.0` PASS.

### Fix 2 — Relation type: `isPartOf` → `cites`; add 1× `isVersionOf` (MAJOR)

**File:** `fix_squads/01_thesis/A/zenodo_metadata.json`  
**Problem:** Prior-version Λ entries used `"relation": "isPartOf"`, which is semantically incorrect (this thesis cites the Λ chain; it is not a part of it). The concept DOI entry had no `isVersionOf` relation.  
**Fix:** All 10 prior Λ version entries changed to `"relation": "cites"`; the concept DOI (10.5281/zenodo.20162352) uses `"relation": "isVersionOf"`.  
**Verification:** `replay_run_1.txt` CHECK 1: `cites count: 10` PASS, `isVersionOf count: 1` PASS, `isPartOf count: 0` PASS.

### Fix 3 — Semantic Scholar IDs mislabelled as DOIs: `doi:287071995` → `S2-ID:287071995`; `doi:287121524` → `S2-ID:287121524` (MAJOR)

**File:** `fix_squads/01_thesis/A/thesis_v13_bundle.md`  
**Problem:** Two inline citations used `doi:287071995` and `doi:287121524`, which are Semantic Scholar corpus IDs, not DOIs. The `doi:` prefix implies a resolvable Digital Object Identifier.  
**Fix:**  
- Line 410: `S2-ID:287071995 — NOTE: This is a Semantic Scholar corpus ID, not a DOI`  
- Line 1170: `S2-ID:287121524 — NOTE: This is a Semantic Scholar corpus ID, not a DOI`  
**Verification:** `replay_run_1.txt` CHECK 3: `doi:287 count: 0` PASS — no Semantic Scholar IDs mislabelled as `doi:`.

### Fix 4 — Chapter 8 reordering: Ch8 placed after Ch7 in ascending sequence (MAJOR)

**File:** `fix_squads/01_thesis/A/thesis_v13_bundle.md`  
**Problem:** Chapter 8 ("Multi-Tenant Approval Orchestration") was not in ascending numeric order relative to Chapter 7 ("Surface Audit").  
**Fix:** Chapter ordering restored to `[1, 2, 3, 4, 5, 6, 7, 8]` with correct line number positions.  
**Verification:** `replay_run_1.txt` CHECK 4: `Chapter number sequence: [1, 2, 3, 4, 5, 6, 7, 8]` PASS.

---

## 5× Replay Verification

**Replay harness:** `fix_squads/01_thesis/A/replay_run_{1-5}.txt`  
**Seeds:** 42, 137, 256, 512, 1024 (seed variation affects only sampled line positions within chapters — structural checks are seed-independent by design)

| Run | Seed | Outcome |
|---|---|---|
| replay_run_1.txt | 42 | All checks: PASS |
| replay_run_2.txt | 137 | All checks: PASS |
| replay_run_3.txt | 256 | All checks: PASS |
| replay_run_4.txt | 512 | All checks: PASS |
| replay_run_5.txt | 1024 | All checks: PASS |

**Fixed files SHA256 (from replay_run_1.txt, seed=42):**

```
thesis_v13_bundle.md:  d2acd136423b25f64f0a5ffb53f76e8a6888acf0b6f9e0af1ead61ef32b71298
zenodo_metadata.json:  589629e10cfa7ac527d5d3f911d81b5e654acb32d27035e37c5931d380e195b2
```

All 5 runs share the same structural PASS result. The SHA256 for `thesis_v13_bundle.md` (`d2acd136...`) is the canonical post-fix digest referenced throughout the audit.

---

## Doctrine Grade

See `T01_doctrine_self_grade.md`.

**Overall: CONDITIONAL_PASS** — composite mean 0.911 across 9 axes; conjunctive gate fails because 4 axes are below the 0.90 floor (horizon=0.88, resonance=0.86, invariance=0.88, ontologicalGrounding=0.89).

---

## Honest Disclosure: 4 Sub-0.90 Axes (CONDITIONAL annotations)

The following axes scored below the Doctrine v2 floor of 0.90. These scores are reported as-measured; no inflation applied. The thesis correctly carries a `[CONDITIONAL_PASS]` annotation in its front matter.

| Axis | Score | Doctrine Floor | Gap | Root Cause |
|---|---|---|---|---|
| horizon | 0.88 | 0.90 | −0.02 | Forward-pointer sections at chapter ends are present but incomplete; file paths, owners, and timelines are not uniformly provided |
| resonance | 0.86 | 0.90 | −0.04 | Executive/developer/operator audience stratification is not fully realized; some sections default to a single technical register |
| invariance | 0.88 | 0.90 | −0.02 | Cross-paraphrase stability evidence for key claims is asserted but not demonstrated with paired-prompt output |
| ontologicalGrounding | 0.89 | 0.90 | −0.01 | Several `[INTERNAL]` SHA references exist whose resolution status is not independently verified; one DOI (prefix 10.63412) is marked `[UNVERIFIED]` |

---

## Honest [UNVERIFIED] Carryovers

| ID | Location | Description |
|---|---|---|
| UV-01-01 | thesis_v13_bundle.md front matter | `zenodo_version_doi: "[UNVERIFIED — to be assigned by Zenodo on v13 mint]"` — v13-specific DOI not yet minted |
| UV-01-02 | Ch4 XXXXX DOI (2 instances) | DOI for Egyptian-math Zenodo deposit not yet minted; `XXXXX` placeholder present |
| UV-01-03 | Multiple chapters | Zenodo concept DOI 10.5281/zenodo.20162352 used as anchor — no v13-specific DOI |
| UV-01-04 | Bhattacharya 2026 cite | DOI prefix 10.63412 is not a recognized registrant; explicitly marked `[UNVERIFIED — DOI not confirmed to resolve]` |

---

## Remediation Path (required before PASS)

**Assigned to:** GAP-02 squad (re-loop, parallel track)  
**Cross-reference:** `audit_phase1/AUDIT_REPORT.md` §6 GAP-02

The following targeted re-loop actions are required to raise the 4 CONDITIONAL axes to ≥0.90:

1. **horizon (0.88 → ≥0.90):** Add explicit forward-pointer sections at the end of each chapter with file paths (relative to monorepo root), owners (Stephen P. Lutar Jr. / SZL Holdings), and timeline (Series A data-room target). One paragraph per chapter is sufficient.

2. **resonance (0.86 → ≥0.90):** Add explicit audience stratification — label each major section with `[EXECUTIVE]`, `[DEVELOPER]`, or `[OPERATOR]` markers; ensure Ch1 and Ch5 each carry a standalone executive brief paragraph (≤ 200 words, no undefined acronyms in the first 50 words).

3. **invariance (0.88 → ≥0.90):** Add a §Cross-Paraphrase Stability note in Ch1 demonstrating that key claims (Λ₁₀ floor, Doctrine v2 binding, CONDITIONAL_PASS definition) are stated consistently across at least 2 differently-phrased expositions in the document.

4. **ontologicalGrounding (0.89 → ≥0.90):** Resolve or explicitly `[UNVERIFIED]`-tag every `[INTERNAL]` SHA reference; mint UV-01-01 v13 DOI and replace placeholder once available.

Until the re-loop completes, the thesis artifact must not be presented as a PASS in any investor disclosure or public repository.

---

*Signed: GAP-03 Builder (inline, 2026-05-14)*  
*Doctrine v2 binding — no hallucinations, no bandaids*  
*Stephen P. Lutar Jr. &lt;stephen@szlholdings.com&gt; ORCID 0009-0001-0110-4173 — SZL Holdings*
