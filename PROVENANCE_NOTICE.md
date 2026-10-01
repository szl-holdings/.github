# Provenance NOTICE — SLSA L1 honest

> **SLSA L1 honest.** SZL Holdings' verified supply-chain provenance posture is
> **SLSA Level 1 (honest)**: source and build provenance are documented, and
> DSSE/Cosign signing of Khipu receipts is live. **SLSA L2 (hardened
> build-service provenance) is NOT yet attested** — it is a **roadmap item
> delivered via Wire D**. SLSA L3 is not claimed.

## Correction of sibling commit `f59e9f5e`

The commit
[`f59e9f5e`](https://github.com/szl-holdings/.github/commit/f59e9f5e)
("Add SZLHOLDINGS Cosign public key for DSSE Khipu receipt verification") used
the phrase **"SLSA L2 signed provenance"** in its message. **That wording was a
misstatement.** Commit messages are immutable, so this NOTICE is the durable
correction of record:

- The Cosign public key ([`cosign.pub`](cosign.pub)) and DSSE-signed Khipu
  receipts are **real** and verifiable with `cosign verify-blob`.
- Their existence establishes **SLSA L1 (honest)** — documented provenance plus
  signing. It does **not** by itself establish SLSA L2, which additionally
  requires a hardened, isolated build service attesting the build.
- SZL's posture therefore remains **SLSA L1 honest; L2 roadmap via Wire D**.

This NOTICE supersedes any "SLSA L2" phrasing in `f59e9f5e` and aligns the
provenance claim with the honest posture already stated in
[`README.md`](README.md), [`profile/README.md`](profile/README.md), and
[`TRUST.md`](TRUST.md).

---
Signed-off-by: Yachay <yachay@szlholdings.dev>
Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17 — SLSA L1 honest.
Co-Authored-By: Perplexity Computer Agent

---

## Addendum, 2026-09-26 (not covered by the sign-off above)

This addendum was added in a later commit (see
`git log -- PROVENANCE_NOTICE.md`). It is not part of the signed-off correction
above, and that text is unchanged. Drafted with Claude Code (Claude Opus 5.5)
for owner review; not signed off.

- A receipt verifies only against the key that signed it. On 2026-09-26 the
  a11oy Space reported signing keyid `9926bf69`, and it serves that key at
  `https://a-11-oy.com/cosign.pub`. That key is neither the root
  [`cosign.pub`](cosign.pub) (`d3028f8a`) nor
  [`keys/cosign.pub`](keys/cosign.pub) (`421a1422`), so a11oy receipts signed
  with it do not verify against either file. See
  [`keys/README.md`](keys/README.md#key-status).
- `cosign verify-blob` checks the bytes it is given. For a DSSE envelope those
  must be the DSSE PAE bytes, not the raw payload.
- As of 2026-09-26, publishing one org key is a pending owner key ceremony.
