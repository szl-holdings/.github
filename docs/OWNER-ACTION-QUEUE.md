# Owner action queue — the four things only the owner can do

Each item lists the exact path and the command that proves it worked. Nothing here is delegable: each touches a credential, a key, or an org-level setting by design.

## 1. Cloudflare connector (2 minutes)

The Pipedream connector fails every call with `400 / 6003 / 6103 Invalid format for X-Auth-Key` — an API Token was saved into an API Key connector.

- Fix: reconnect as a Cloudflare **API Token** connector (Bearer), from dashboard → My Profile → API Tokens. Permissions: Zone:Read, DNS:Edit, Zone Rulesets:Edit. Zone resources: `a-11-oy.com` AND `a11oy.net`.
- Verify: `curl -H "Authorization: Bearer $CF_API_TOKEN" https://api.cloudflare.com/client/v4/zones` returns both zones as active.
- Unblocks: `a-11-oy.com/spectral` + `/controller` 404s and the `gdw.a-11-oy.com` 530 tunnel diagnosis.

## 2. Hugging Face write token + private Spaces (5 minutes)

Session OAuth lacks org-Space write (proven: authorization error on a PR-scoped write attempt).

- Fix: https://huggingface.co/settings/tokens → new token, write scope, SZLHOLDINGS org.
- Then: apply the staged vessels card (`killinchu/docs/hf-cards/SZLHOLDINGS-vessels.README.md` — already on main) and decide the five private Spaces: `hatun-mcp`, `immune`, `szl-model-inference-lab`, `yarqa`, plus `nexus` / `szl-real-estate`. Flip only builds that are complete and honest.
- Verify: the vessels Space card shows "CONSOLIDATED" and each flipped Space loads logged-out.

## 3. SZL-Nemo v3 (the signing ceremony)

Issues szl-gpu-bridge#93 and #20 are EXPIRED_AWAITING_ENGINE_SIGNATURE — both jobspecs expired in August.

- Step 1: regenerate the reviewed jobspecs with fresh `expires_at` using the repo's own controller (never hand-edit hashes).
- Step 2: sign on the enrolled owner laptop (pinned engine DSSE key or enrolled keyId).
- Verify: the issue status flips off EXPIRED and a queue envelope appears signed by the pinned engine key.

## 4. GitHub org leftovers (10 minutes)

- Repo descriptions (`.github#617`): `gh api -X PATCH repos/szl-holdings/<repo> -f description="<honest description>"` per the issue list.
- Org code scanning (`#523`/`#586`): org Settings → Code security → enable default setup (needs admin:org).
