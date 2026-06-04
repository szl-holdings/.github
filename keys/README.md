<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11 LOCKED 749/14/163 · Λ Conjecture 1 · SLSA L1 honest (L2 roadmap) -->

# SZL Holdings — Cosign Public Key for DSSE Verification

This directory publishes the **public** half of the SZL Holdings organization
cosign signing key. Downstream consumers use it to verify the DSSE envelopes /
Khipu receipts emitted by the five flagship organs
(`a11oy`, `sentra`, `amaru`, `killinchu`, `rosie`) and the UDS bundles.

> **PUBLIC KEY ONLY.** The corresponding **private** key is never committed to any
> repository. It exists only as the org runtime secret `SZL_COSIGN_PRIVATE_KEY_PEM`
> (alias `SZL_COSIGN_PRIVATE_PEM`) and the in-cluster Kubernetes secret
> `szl-cosign` (key `cosign.key`). See the Cosign Bootstrap runbook.

## Files

| File | Contents |
|---|---|
| [`cosign.pub`](./cosign.pub) | Org cosign **public** key (ECDSA P-256, SubjectPublicKeyInfo PEM) |

This mirrors the canonical public key published at the repository root
([`/cosign.pub`](../cosign.pub)). Per-organ public keys (used by the Khipu
3-of-4 consensus quorum) live under [`/cosign-keys/`](../cosign-keys/).

## Key facts

- **Algorithm:** ECDSA over the NIST **P-256** curve, signatures over **SHA-256**
  of the DSSE PAE bytes.
- **keyid:** `szlholdings-cosign`
- **Public-key fingerprint (SHA-256 of the PEM file):**
  `b066de4081a3a49dd98d830ee68938facb86ffa5a658e71ddfe27b00b00f5dd2`
- **Public-key fingerprint (SHA-256 of the SPKI DER):**
  `daa4aeca263251e97125fd227ff82e024a64ec970d1c74828463ffba097cb40b`

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

### Option 1 — cosign CLI

```bash
# 1. Extract the payload and signature from the envelope you received:
jq -r .payload    envelope.json | base64 -d > payload.bin
jq -r '.signatures[0].sig' envelope.json       > sig.b64

# 2. Verify against this published public key:
cosign verify-blob --key cosign.pub --signature sig.b64 payload.bin
```

`cosign verify-blob` reconstructs the same ECDSA-P256-SHA256 check and prints
`Verified OK` on success.

> Note: cosign signs/verifies the raw blob bytes. SZL organs sign the **DSSE PAE**
> of the canonical-JSON payload. To verify with `cosign verify-blob` directly,
> the blob you pass must be the exact PAE bytes
> (`DSSEv1 SP LEN(type) SP type SP LEN(body) SP body`). For convenience, prefer
> Option 2, which performs the PAE reconstruction for you.

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
that performs the PAE reconstruction and ECDSA check against this same embedded
public key, returning a structured verdict. No network call required.

## Rotation

To rotate: generate a new key-pair locally, replace both `/cosign.pub` and
`keys/cosign.pub`, update the embedded `COSIGN_PUBLIC_PEM` in each organ's
`szl_dsse.py`, and update the `SZL_COSIGN_PRIVATE_KEY_PEM` org secret +
`szl-cosign` Kubernetes secret. Old receipts remain verifiable with the prior
public key (keep an archive of retired public keys).
