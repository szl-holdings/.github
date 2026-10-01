<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11 LOCKED 749/14/163 · Λ Conjecture 1 · SLSA L1 honest (L2 roadmap) -->

# SZL Holdings — Cosign Public Key for DSSE Verification

This directory publishes a **public** SZL Holdings organization cosign key.
It is **not** the key the a11oy Space reported for signing when checked on
2026-09-26, and it is **not** the repository-root key. Read
[Key status](#key-status) before you verify anything against it. The a11oy
runtime receipt key (`9926bf69`) is published separately as
[`a11oy-runtime-receipts.pub`](./a11oy-runtime-receipts.pub); choosing a single
canonical org key is still an owner key ceremony.

> **PUBLIC KEY ONLY.** This directory holds public keys only. A public-git scan
> recorded at 2026-08-29T18:00Z found no committed private key
> ([`estate.json`](https://github.com/szl-holdings/a11oy-net/blob/1bc2b21b956285ff2d3df2cb47250a81c3abf29e/estate.json)
> `keys.private_keys_in_public_git` = 0; its note lists the scope: szl-receipt,
> szl-govsign, a11oy, killinchu, .github/keys, developers/VERIFY.md and
> szl-lake). This README did not re-run that scan.
> Where the private halves of `421a1422` (this directory's file) and `d3028f8a`
> (the root `cosign.pub`) are held is **NOT MEASURED**. Earlier versions of this
> README said this directory's private key exists only as the org runtime secret
> `SZL_COSIGN_PRIVATE_KEY_PEM` (alias `SZL_COSIGN_PRIVATE_PEM`) and the
> in-cluster Kubernetes secret `szl-cosign` (key `cosign.key`); that was not
> re-checked. Do not treat `SZL_COSIGN_PRIVATE_PEM` as an alias for this key.
> On 2026-09-26T02:37Z, `GET /api/a11oy/v1/signing-status` on the a11oy Space
> reported `dsse_keyid` `9926bf69` and `key_source`
> `persistent:env:SZL_COSIGN_PRIVATE_PEM`. That is the Space's report about
> itself; nothing was signed for that check, and the secret name was not
> verified (a11oy's own `ayllu/keys/README.md` names it
> `SZL_COSIGN_PRIVATE_KEY_PEM`).
> The top-level envelopes of the 2026-07-21 a11oy receipts verify under
> `9926bf69`, not under this directory's key (see [Key status](#key-status)).
> See the Cosign Bootstrap runbook.

## Files

| File | Contents |
|---|---|
| [`cosign.pub`](./cosign.pub) | Org cosign **public** key `421a1422` (ECDSA P-256, SubjectPublicKeyInfo PEM). Last changed 2026-06-09 (`320d55f`). |
| [`a11oy-runtime-receipts.pub`](./a11oy-runtime-receipts.pub) | a11oy runtime receipt **public** key `9926bf69` (ECDSA P-256, SPKI DER SHA-256 `8e2d106c…`). Byte-identical to `https://a-11-oy.com/cosign.pub` and `https://szlholdings-a11oy.hf.space/cosign.pub` when added on 2026-09-27. Use it to verify a11oy decision receipts; it is not a release-signing key. |

This file does **not** mirror the repository-root [`/cosign.pub`](../cosign.pub).
The root key was rotated on 2026-06-14 (`e942dc4`) and again on 2026-06-27
(`30cad24`); this copy was not updated. Per-organ public keys (used by the
Khipu 3-of-4 consensus quorum) live under [`/cosign-keys/`](../cosign-keys/).

## Key facts

- **Algorithm:** ECDSA over the NIST **P-256** curve, signatures over **SHA-256**
  of the DSSE PAE bytes.
- **keyid label:** `szlholdings-cosign`. The same label has been used with
  more than one key (the 2026-07-21 a11oy receipts below carry it and were
  signed with `9926bf69`). It does not identify a key.
- **Fingerprints below:** "keyid" is the SHA-256 of the PEM text with leading
  and trailing whitespace removed (the value the a11oy Space reports as
  `dsse_keyid`), shown as its first 8 hex characters. It changes with PEM line
  wrapping, and it is not `sha256sum` of the file. "SPKI DER" is the SHA-256 of
  the DER public key (`openssl pkey -pubin -outform DER | sha256sum`), which
  does not depend on PEM line wrapping.

## Key status

This table lists every key that has been this repository's root `cosign.pub`
or `keys/cosign.pub`, and the key served by the a11oy product origin. It does
not list the per-organ keys under [`/cosign-keys/`](../cosign-keys/), or the
"Org Dev Public Key" quoted in
[`coordination/UDS_RELEASE_TAG_RECONCILIATION.md`](../coordination/UDS_RELEASE_TAG_RECONCILIATION.md)
since 2026-05-30 (`591da94`; SPKI DER SHA-256 `c35f086d…`). When checked on
2026-09-26, that dev key verified none of the four envelopes in the two
2026-07-21 a11oy receipts described below. History is from this repository's
git log. Live GETs were run on 2026-09-26 at 02:37:38Z.

| keyid | SPKI DER SHA-256 | Where it was published | Status |
|---|---|---|---|
| `a4d73120` | `daa4aeca263251e97125fd227ff82e024a64ec970d1c74828463ffba097cb40b` | root `cosign.pub` from 2026-06-01 (`f59e9f5`); `keys/cosign.pub` from 2026-06-03 (`2efaf04`). Served at `SZLHOLDINGS/szl-lake` `keys/org-cosign.pub` and at `https://szlholdings-killinchu.hf.space/cosign.pub` (both 02:37Z; which key killinchu signs with was not measured). | Replaced here on 2026-06-09. Before this correction, this README listed its fingerprints (PEM file `b066de40…`, SPKI DER `daa4aeca…`) as the fingerprints of this directory's file. |
| `421a1422` | `fc7e0c26b91ca8cae14bf773c3dd8da7cdfe2aa99432abd6604abd67a7b53567` | root `cosign.pub` from 2026-06-09 (`6da2a72`); `keys/cosign.pub` from 2026-06-09 (`320d55f`). | Still the file in this directory. |
| `76199818` | `a1f6d3233442cdad0801c702e0ff77aa45fd1ba45f532e3919c80d520b2826ab` | root `cosign.pub` from 2026-06-14 (`e942dc4`). | Replaced on 2026-06-27. |
| `d3028f8a` | `580ed9a9bd9f7c9f4f49ec9564b81ba8b3d80f3f21d0e5200c38514be94ad3a8` | root `cosign.pub` from 2026-06-27 (`30cad24`). Also embedded as `COSIGN_PUBLIC_PEM` in `szl_dsse.py` at `szl-holdings/a11oy@28acdc52` and served at the a11oy Space `/khipu/pubkey.pem` (02:37Z). | Current root key. |
| `9926bf69` | `8e2d106c6995e11dbf7cbedfa9e5800bb50c82a635756e40dcd330364f6ea8ba` | Published here as [`keys/a11oy-runtime-receipts.pub`](./a11oy-runtime-receipts.pub) since 2026-09-27 (before that, not published in this repository). Served at `https://a-11-oy.com/cosign.pub` and `https://szlholdings-a11oy.hf.space/cosign.pub` (02:37Z), which is the signing product origin itself. Also committed in `szl-holdings/a11oy` at `ayllu/keys/council-runtime-2026-07-21.pub` since `0d3a2d4c` (2026-07-21), with the same SPKI DER; that copy is wrapped at 76 columns, so its keyid-style hash is `75dc678a…`. a11oy's `ayllu/keys/README.md` says that copy was recovered from two live a11oy signatures by ECDSA public-key recovery, and that verifying against it does not prove custody of the published org key. Full keyid `9926bf69b799ea663fc5cf5a8c5d8f594d99d7b323700d6a20b803bd4c9f4e15`. | Key the a11oy Space reported for signing (see below). |

What was observed on 2026-09-26:

- `GET https://szlholdings-a11oy.hf.space/api/a11oy/v1/signing-status` at
  02:37:38Z returned `dsse_keyid` `9926bf69b799ea66` and `key_source`
  `persistent:env:SZL_COSIGN_PRIVATE_PEM`. This is reported by the Space
  about itself. No signing endpoint was called, so nothing signed that day
  was checked.
- The two 2026-07-21 a11oy decision receipts
  (`ayllu/decisions/2026-07-21-inaugural-charter.json` and
  `ayllu/decisions/2026-07-21-post-rebuild-continuity.json` at
  `szl-holdings/a11oy@28acdc52`) each carry two DSSE envelopes. Both were
  checked with ECDSA-P256-SHA256 over the DSSE PAE against ten keys: the five
  in the table above and the five `cosign-keys/*.pub` files.
  - The top-level `receipt` envelope (keyid label `szlholdings-cosign`)
    verified against `9926bf69` only, in both files. It failed against the
    other nine keys.
  - The nested `contract.routing.receipt` envelope (keyid label
    `a11oy-inimage-ecdsa-p256`, `key_scope` `PROCESS_BOOT_EPHEMERAL`) failed
    against all ten keys, in both files. It is labelled `key_scope`
    `PROCESS_BOOT_EPHEMERAL`; the key that signed it was not identified.

Receipts signed with `9926bf69` do **not** verify against the root
`cosign.pub` or `keys/cosign.pub`. Publishing one org key is an owner key
ceremony that had not happened as of 2026-09-26. Check an envelope against
the key that signed it, and state which key you used.

## What gets signed

Each receipt is wrapped in a DSSE (Dead-Simple-Signing-Envelope) using the
in-toto **Pre-Authentication Encoding** (PAE):

```
PAE(type, body) = "DSSEv1" SP LEN(type) SP type SP LEN(body) SP body
SIGNATURE       = ECDSA-P256-SHA256( PAE("application/vnd.szl.khipu+json", canonical_json(receipt)) )
```

A signed envelope looks like:

```json
{
  "payloadType": "application/vnd.szl.khipu+json",
  "payload": "<base64 canonical-json receipt>",
  "signatures": [{ "sig": "<base64 ECDSA-P256-SHA256>", "keyid": "szlholdings-cosign" }],
  "signed": true,
  "honesty": "REAL — ECDSA-P256-SHA256 over DSSE PAE; verifiable by `cosign verify-blob`"
}
```

> **Honesty contract.** If the signing secret is absent, organs emit
> `"signatures": []` with `"signed": false` and an explicit `"honesty": "UNSIGNED …"`
> marker. SZL organs **never fabricate** a signature.

## How to verify (consumers)

Use the key that signed the envelope, and say which key you used. The examples
below name this directory's `cosign.pub` (`421a1422`). For the a11oy receipts
in [Key status](#key-status), use the `9926bf69` key instead; neither the root
`cosign.pub` nor `keys/cosign.pub` verifies them.

### Option 1 — cosign CLI

```bash
# 1. Rebuild the DSSE PAE bytes from the envelope you received (the decoded
#    payload alone does not verify), and extract the signature:
python3 -c "import base64,json,sys; e=json.load(open('envelope.json')); t=e['payloadType'].encode(); b=base64.b64decode(e['payload']); sys.stdout.buffer.write(b'DSSEv1 %d %s %d %s' % (len(t), t, len(b), b))" > pae.bin
jq -r '.signatures[0].sig' envelope.json > sig.b64

# 2. Verify the PAE bytes against the key that signed the envelope:
cosign verify-blob --key cosign.pub --signature sig.b64 pae.bin
```

> Note: cosign checks the exact blob bytes you pass. SZL organs sign the
> **DSSE PAE** of the canonical-JSON payload
> (`DSSEv1 SP LEN(type) SP type SP LEN(body) SP body`), so pass `pae.bin`, not
> the decoded payload. The `honesty` string in the 2026-07-21 a11oy
> envelopes says "verifiable by `cosign verify-blob --key cosign.pub`"; that
> holds only with the PAE bytes and the key that signed the envelope.
>
> The `cosign` command above was not run when this section was last edited
> (2026-09-26); cosign was not installed. The same `pae.bin` and signature were
> checked with OpenSSL instead (`base64 -d sig.b64 > sig.der`, then
> `openssl dgst -sha256 -verify <key> -signature sig.der pae.bin`), on the
> top-level `receipt` envelope of
> `ayllu/decisions/2026-07-21-inaugural-charter.json` at
> `szl-holdings/a11oy@28acdc52`. It printed `Verified OK` with the `9926bf69`
> key, and `Verification failure` with the root `cosign.pub` and with the
> decoded payload in place of `pae.bin`.
>
> Transparency log, not tested here: cosign 2.x is understood to require a
> Rekor transparency-log entry by default, and these envelopes are not known to
> have one. The command above may therefore fail until you add
> `--insecure-ignore-tlog=true`, which checks the signature against the key
> alone. No cosign version was run with or without that flag. Record the
> cosign version and flags you used.
>
> Option 2 performs the PAE reconstruction for you.

### Option 2 — Python (`cryptography`), the canonical path

```python
import base64, json, hashlib
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature

PUB = open("cosign.pub", "rb").read()

def pae(payload_type: str, body: bytes) -> bytes:
    t = payload_type.encode("utf-8")
    return (b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" "
            + str(len(body)).encode() + b" " + body)

def verify(envelope: dict) -> bool:
    body = base64.b64decode(envelope["payload"])
    msg  = pae(envelope["payloadType"], body)
    pub  = load_pem_public_key(PUB)
    for s in envelope.get("signatures", []):
        try:
            pub.verify(base64.b64decode(s["sig"]), msg, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            pass
    return False
```

### Option 3 — organ `/khipu/verify` endpoint

Each organ exposes `szl_dsse.verify_envelope(env)` (and a `/khipu/verify` route)
that performs the PAE reconstruction and ECDSA check against the organ's own
configured public key(s), returning a structured verdict. No network call
required. Those keys are not necessarily the file in this directory (see
[Key status](#key-status)).

## Rotation

To rotate: generate a new key-pair locally, replace both `/cosign.pub` and
`keys/cosign.pub`, update the embedded `COSIGN_PUBLIC_PEM` in each organ's
`szl_dsse.py`, and update the `SZL_COSIGN_PRIVATE_KEY_PEM` org secret +
`szl-cosign` Kubernetes secret, and every runtime secret that is meant to sign
as the org key. On 2026-09-26T02:37Z the a11oy Space reported, through
`GET /api/a11oy/v1/signing-status`, `dsse_keyid` `9926bf69` and `key_source`
`persistent:env:SZL_COSIGN_PRIVATE_PEM`. That is a self-report; nothing was
signed for that check. The 2026-07-21 a11oy receipts verify under `9926bf69`.
A key ceremony must either publish that key or rotate the Space's signing
secret to the published org key. Old receipts remain verifiable with the prior
public key (keep an archive of retired public keys). Add each new and retired
key to [Key status](#key-status), and update `SZLHOLDINGS/szl-lake`
`keys/org-cosign.pub` in the same change.

## Verify an a11oy receipt against the runtime key

```python
# pip install cryptography
import base64, json, sys
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key

key = load_pem_public_key(open("keys/a11oy-runtime-receipts.pub", "rb").read())
env = json.load(open(sys.argv[1]))          # a DSSE envelope: payloadType, payload, signatures
payload, ptype = base64.b64decode(env["payload"]), env["payloadType"].encode()
pae = b"DSSEv1 %d %s %d %s" % (len(ptype), ptype, len(payload), payload)
for s in env["signatures"]:
    key.verify(base64.b64decode(s["sig"]), pae, ec.ECDSA(hashes.SHA256()))   # raises if invalid
print("OK")
```

Checked on 2026-09-27: the top-level envelopes of `szl-holdings/a11oy`
`ayllu/decisions/2026-07-21-inaugural-charter.json` and
`2026-07-21-post-rebuild-continuity.json` verify under this key; their inner
envelopes do not (they carry a different signer).
