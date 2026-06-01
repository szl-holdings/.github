# Codex-Kernel v1.0.0 — Reproducible Bit-Exact Attestation

> **Org-wide single source of truth.** This is the canonical attestation that every SZL Holdings investor, bank, insurance, and compliance packet cites by URL:
> <https://github.com/szl-holdings/.github/blob/main/proof-artifacts/codex-kernel-v1.0.0-attestation.md>

**Status (honest):** Codex-Kernel **v1.0.0** — Latest release on the `szl-holdings/platform` repository, tagged May 2026. Platform tag `v1.0.0-codex-kernel`, commit SHA `03784d5`. This is an internal, self-attested reproducibility artifact, **not** a third-party certification.

**Release URL:** <https://github.com/szl-holdings/platform/releases/tag/v1.0.0-codex-kernel>

## Release pack SHA256 (integrity)

| File | SHA256 |
|---|---|
| `codex-kernel-release-v1.0.0.zip` | `6136f3b3ec277a4e4cc8a1157d5afe6633821b29a4133d94a19b843dc9b03f8c` |
| `codex-kernel-release-v1.0.0.tar.gz` | `3ec84df164108795878f5c20f7974d295ab8908513d496e018100c20513a8a19` |

## Verified reproducible runs (bit-exact)

| Run | final_state_hash | ledger_digest | stop_reason |
|---|---|---|---|
| Dresden-Venus | `fe20ecc47445dbd887b5b14ef26ed981` | `4d0a943cef5b8fa605919db38df5e8e7` | convergence |
| SZL governed-ops | `ca0910f40dd2e24d9f98437242f9717c` | `77a5642066d5992f1ea2444863a0f146` | convergence |

Both runs reproduce bit-for-bit from the release pack and terminate on `convergence`. Test suite: **18/18 green**.

## One-line verifier recipe

```bash
curl -L https://github.com/szl-holdings/platform/releases/download/v1.0.0-codex-kernel/codex-kernel-release-v1.0.0.tar.gz | sha256sum  # expect 3ec84df1…3a8a19
```

The release `PROOF.md` ships the full 3-command verification recipe that re-runs both bundles and re-derives the hashes above.

## Compliance alignment

Aligned with **EU AI Act Article 12** (record-keeping / automatic logging) and the **NIST AI Risk Management Framework (AI RMF)**. The bit-exact ledger digests provide the immutable run records these frameworks call for.

---
*Provenance: figures sourced verbatim from the SZL platform deep-dive ledger (2026-06-01). No number herein is fabricated. Authored by Yachay (CTO, SZL Holdings); co-authored by Perplexity Computer.*
