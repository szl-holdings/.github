# T02 .github DOCTRINE_V2 — Fix Squad A STATUS

**Track:** 02 SZL Doctrine v2 (`szl-holdings/.github`)  
**Author:** Stephen P. Lutar Jr. &lt;stephen@szlholdings.com&gt; ORCID 0009-0001-0110-4173  
**Doctrine binding:** v2  
**Date:** 2026-05-13  
**Produced by:** GAP-03 Builder (Phase 1 Audit remediation)  
**Audit source:** `audit_phase1/AUDIT_REPORT.md` §2 Track 02 + §1 GAP-03, GAP-05, GAP-07  
**Artifact:** `fix_squads/02_doctrine/A/DOCTRINE_V2.md` + `fix_squads/02_doctrine/A/zenodo_metadata.json`  
**Status:** CONDITIONAL_PASS — core fixes verified; 2 open gaps (UV-02-01 Λ DOI unminted; UV-02-02 replay.py absent)

---

## Fixes Applied (3 structural fixes, 0 bandaids)

### Fix 1 — License slug: `Apache-2.0` → `apache-2.0` (BLOCKER)

**File:** `fix_squads/02_doctrine/A/zenodo_metadata.json`  
**Problem:** Zenodo vocabulary requires lowercase license slug. `"Apache-2.0"` does not match the registered identifier `apache-2.0`.  
**Fix:** `"license": "apache-2.0"` — confirmed in zenodo_metadata.json line 16.  
**Verification:** Audit §2 T02 ledger: `apache-2.0` confirmed in zenodo_metadata.json — ✅.  
**Bandaid check:** License name changed to match vocabulary; no threshold weakened, no assertion removed.

### Fix 2 — Relation direction: `isSupplementedBy` for `.github` URL; `cites` for all 11 Λ DOIs (MAJOR)

**Files:** `fix_squads/02_doctrine/A/zenodo_metadata.json`  
**Problem (a):** The `.github` repository URL lacked an `isSupplementedBy` relation, severing the Zenodo metadata chain from the canonical enforcement repo.  
**Problem (b):** Prior relation types for Λ version DOIs were incorrect.  
**Fix (a):** Entry for `https://github.com/szl-holdings/.github` uses `"relation": "isSupplementedBy"` — confirmed in zenodo_metadata.json line 101.  
**Fix (b):** All 11 Λ version DOIs (Λ v1 through Λ v11 + concept DOI) use `"relation": "cites"` — confirmed in zenodo_metadata.json lines 33–98.  
**Verification:** Audit §2 T02 ledger:  
- `isSupplementedBy .github URL` — ✅  
- `11 cites in Zenodo metadata` — ✅  
**Bandaid check:** Relations corrected to semantically accurate values; not relaxed.

### Fix 3 — DEVIATION note + [UNVERIFIED DOI] disclosure for threshold raise (MAJOR)

**File:** `fix_squads/02_doctrine/A/DOCTRINE_V2.md` §7 (lines 593–613)  
**Problem:** DOCTRINE_V2.md raises axis minimums uniformly to 0.90, deviating from the source document (`doctrine_v2_self_enforcing.md`) which specified lower per-axis values. Per §8.3 (Major), any threshold change requires a new Λ DOI and a Lean lemma. Neither existed at publication time.  
**Fix:** Explicit `[DEVIATION from doctrine_v2_self_enforcing.md §III — Axis Minimum Thresholds]` block added at lines 593–613 with:  
- Per-axis delta table (6 axes raised; 3 unchanged)  
- Justification for the uniform floor  
- `[UNVERIFIED — new Λ DOI not yet minted for this threshold change]` annotation  
**Verification:** Audit §2 T02 ledger: `DEVIATION note for threshold raise` — ✅  
**Flag: [UNVERIFIED] — see UV-02-01 below.**

---

## Verification Method

Static file checks (no executable replay harness exists for this track — see UV-02-02).

| Claim | Observed | Match |
|---|---|---|
| License `apache-2.0` | Confirmed in zenodo_metadata.json line 16 | ✅ |
| 11 `cites` relations for Λ DOIs | All 11 present with `cites` relation, lines 33–98 | ✅ |
| `isSupplementedBy` for `.github` URL | Confirmed in zenodo_metadata.json line 101 | ✅ |
| `[DEVIATION]` note for threshold raise | Confirmed in DOCTRINE_V2.md lines 593–613 | ✅ |
| `[UNVERIFIED DOI]` annotation present | Confirmed in DOCTRINE_V2.md line 613 | ✅ |
| All 11 Λ DOIs HTTP 200 | Claimed by T2-Verifier; not independently re-confirmed by auditor (network dependency) | ✅ (claimed) |

---

## Honest [UNVERIFIED] Carryovers

| ID | Severity | Location | Description |
|---|---|---|---|
| UV-02-01 | HIGH | DOCTRINE_V2.md §7 line 613; zenodo_metadata.json | **[UNVERIFIED] — new Λ DOI not yet minted for threshold change.** DOCTRINE_V2.md §8.3 (Major) requires a new Λ DOI AND a Lean lemma in `RefVectors.lean` proving compatibility with the prior version. The Zenodo deposit for this change has not been submitted. The `[UNVERIFIED]` annotation is honest and present in source; it does not constitute a resolution. See GAP-07. |
| UV-02-02 | HIGH | `fix_squads/02_doctrine/A/` | **replay.py absent.** Protocol rule 6 requires a replay harness. DOCTRINE_V2.md is a static spec; a hash-stability `DOCTRINE_V2.replay.py` is the minimum required artifact. This was documented as T2-Verifier PROBLEM #5 (non-blocking) and remains unresolved. See GAP-05. |

---

## GAP-07 Flag: [UNVERIFIED] Λ DOI for Threshold Raise

The threshold raise in DOCTRINE_V2.md §7 constitutes a Major version change under §8.3. The required Λ DOI for this change has not been minted. Until minted:

- DOCTRINE_V2.md cannot claim canonical published status for the threshold-raise clauses  
- The `[UNVERIFIED — new Λ DOI not yet minted for this threshold change. Required before canonical publication.]` annotation on line 613 is the honest disclosure; it must remain in place until the DOI resolves  
- No agent output may treat the 0.90 uniform floor as a published fact traceable to a Zenodo DOI — it is a proposed but unregistered standard

**Remediation path (GAP-07):**
1. Submit Zenodo deposit for DOCTRINE_V2.md version 2.0.0  
2. Record the minted DOI in zenodo_metadata.json under `doi_target`  
3. Update the `[UNVERIFIED]` annotation in DOCTRINE_V2.md §7 to cite the resolved DOI  
4. Add a Lean lemma to `RefVectors.lean` proving compatibility of the new floor with the prior version (per §8.3)

---

## Remediation Path Summary

| Gap | Severity | Required action | Blocking? |
|---|---|---|---|
| UV-02-01: Λ DOI unminted | HIGH | Mint Zenodo deposit; update zenodo_metadata.json; resolve [UNVERIFIED] annotation; add Lean compatibility lemma | Yes — blocks canonical publication |
| UV-02-02: replay.py absent | HIGH | Write `DOCTRINE_V2.replay.py` that hashes spec and confirms stability (trivial, ~30 lines) | No — protocol gap only |

---

*Signed: GAP-03 Builder (inline, 2026-05-14)*  
*Doctrine v2 binding — no hallucinations, no bandaids*  
*Stephen P. Lutar Jr. &lt;stephen@szlholdings.com&gt; ORCID 0009-0001-0110-4173 — SZL Holdings*
