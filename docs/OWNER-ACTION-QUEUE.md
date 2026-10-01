# Owner action queue — the things only the owner can do

Each item lists the exact path and the command that proves it worked. Nothing here is delegable: each touches a credential, a key, an org-level setting, or owner hardware by design. State verified 2026-09-30 (receipt: szl-hf-frontier `payloads/SZL-HF-FRONTIER-1-EXECUTION-RECEIPT-2026-09-30.md`).

## 1. Cloudflare — one API token, two effects (5 minutes)

A names-only audit of all 103 active repositories found **no Cloudflare credential anywhere** (no `CLOUDFLARE*`, `CF_*`, or `WRANGLER*` secret at repo, environment, or visible-org scope). The Pipedream connector still fails (`9106`): an API Token was saved into the API-**Key** connector, which expects the Global API Key plus account email.

- Fix (GitHub Actions path, preferred): from a clone of `a11oy` in administrator PowerShell 5.1, run `.\ops\windows\authorize-cloudflare-production.ps1`. It opens the token page, takes the token through a hidden prompt, verifies both zones, stores `CLOUDFLARE_API_TOKEN` in the `production` environment, and dispatches **Repair Cloudflare Product Edge — production authority**. Token contract: Account › Workers Scripts › Edit; Zone › Workers Routes › Edit, DNS › Edit, Zone › Read — resources `a-11-oy.com` and `a11oy.net` (see `docs/CLOUDFLARE_WINDOWS_AUTHORIZATION.md`).
- Fix (connector path, optional): reconnect the Cloudflare connector with the **Global API Key + account email**, or as an API-Token connector if offered.
- Verify: the controller run's receipt shows `status` other than `UNAVAILABLE` and `https://a-11-oy.com/spectral` and `/controller` stop returning 404 (the two Worker routes the controller owns). `gdw.a-11-oy.com` now answers 401 (tunnel up, auth required) rather than 530.

## 2. David dataset reader token (2 minutes)

`david-leads/ops/credential-rotation.md` requires `DAVID_DATASET_READ_TOKEN` to be a **fine-grained** Hugging Face token with read access to `SZLHOLDINGS/david-leads-data` only; the repository `HF_TOKEN` is the publisher and must not double as the reader. The live-lanes canary is red for exactly this reason (`FORM5500_VERIFIED_SNAPSHOT_UNAVAILABLE`, `rotation_generation: null`); the dataset itself is fresh (deploy-time admission passed 2026-09-30).

- Fix: run `payloads/runbooks/SZL-DAVID-READER-TOKEN.ps1` from szl-hf-frontier in administrator PowerShell 5.1. It opens the fine-grained token page, takes the token hidden, proves `fineGrained` role and dataset read with the same checks the rotation makes, runs `gh secret set DAVID_DATASET_READ_TOKEN --repo szl-holdings/david-leads --env david-space-credential-rotation`, and dispatches **Rotate David Space credentials**.
- Then: approve the environment deployment under Actions (reviewer: the owner account).
- Verify: the next **David frontier live-lanes canary** run is green and its artifact shows `rotation_generation` bound.

## 3. khipu-abstain DPO lane on the 5050 laptop (one paste, ~30 minutes GPU)

No self-hosted runner exists in the org, so the only CUDA path is the owner laptop.

- Run: `payloads/runbooks/SZL-KHIPU-DPO-RUNBOOK.ps1` (pinned to szl-forge `huggingface@36e0bf89`; pipeline SHA-256 `31d5d1bb…`, ingest tool `e5a1551f…`, both byte-verified before anything runs). It trains an isolated challenger, measures the sealed held-out set against khipu-r3, and stages an immutable evidence bundle with a derived state block. No token is needed; it publishes nothing.
- Hand back: the printed `bundle-<stamp>\receipts\khipu-abstain\<run_id>\` directory as a pull request into szl-forge. Promotion stays `NOT_PROMOTABLE` until the canonical Forge gate says otherwise.

## 4. Hugging Face token hygiene (WO6) and private Spaces (10 minutes)

- Revoke the two tokens exposed on 2026-09-12 (`hf_nGHC…`, `hf_rpzm…`) at https://huggingface.co/settings/tokens. Every write path in the estate records `wo6_status` honestly until this is confirmed; nothing here can verify it.
- Private Spaces still awaiting a visibility decision: `hatun-mcp`, `nexus`, `szl-real-estate`, `vessels` (`immune`, `szl-model-inference-lab`, `yarqa` are public). The staged vessels card (`killinchu/docs/hf-cards/SZLHOLDINGS-vessels.README.md`, "CONSOLIDATED") is not yet on the Space; the token blocker is gone (`HF_ORG_TOKEN` works from workflows), so this is now a decision, not a credential.

## 5. SZL-Nemo v3 signing ceremony

Issues szl-gpu-bridge#93 and #20 remain open and `EXPIRED_AWAITING_ENGINE_SIGNATURE`.

- Step 1: regenerate the reviewed jobspecs with fresh `expires_at` using the repo's own controller (never hand-edit hashes).
- Step 2: sign on the enrolled owner laptop (pinned engine DSSE key or enrolled keyId).
- Verify: the issue status flips off EXPIRED and a queue envelope appears signed by the pinned engine key.

## 6. GitHub org settings (admin:org)

- Org code scanning (`#523`, `#586`): org Settings → Code security → enable default setup.
- Optional: an org-level fine-grained token with `runners`/`secrets` read so estate audits can see org secrets and runner groups without an owner session.
- Done since the last queue: repository descriptions (`#617` closed; 0 active repos without a description).

## Closed by the 2026-09-30 wave (for the record)

- WO1 card reconciliation: all eight repos reconciled (three Hub PRs merged under owner authorization; WILLAY's reviewed curated card published by byte-exact PR, revision `432646a2`); a daily drift gate in szl-forge keeps it closed.
- david-leads `/v0` wired and live; a-11-oy.com apex proxied and green; a daily public-surface watch notifies only on failure.
