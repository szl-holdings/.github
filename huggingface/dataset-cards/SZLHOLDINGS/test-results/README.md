---
license: apache-2.0
pretty_name: SZL test-results — anatomy alive-harness runs (DSSE-signed)
configs:
- config_name: default
  data_files:
  - split: train
    path: harness_runs.jsonl
tags:
- szl
- governed-ai
- dsse
- test-results
- provenance
task_categories:
- other
size_categories:
- n<1K
---

# SZL test-results — anatomy alive-harness sink

Public, DSSE-signed results sink for the SZL **anatomy alive-harness**. This
dataset was retired earlier in 2026 and stood back up on **2026-07-21** as the
harness's fail-closed publishing target — restoring the public proof loop
behind every "harness verified" claim in the estate.

## What a run is

`anatomy_alive_v6.py` (in this repo) drives live assertions across the whole
substrate — organ liveness, live formula-gate executions, the yuyay_v3 13-axis
schema, Wire D traceparent propagation, the Hatun MCP gateway and its real
ECDSA-P256 DSSE signer, anatomy-map doctrine invariants on three surfaces, and
the Khipu receipt chain. Every assertion is a real HTTP probe or a real
cryptographic verification at the recorded timestamp; counts are derived from
the assertion records, never hand-typed.

## Files

| File | Meaning |
|---|---|
| `harness_runs.jsonl` | One line per published run: `{run, dsse}` — the compact run record plus its DSSE envelope |
| `runs/<stamp>.evidence.json` | Full per-assertion evidence for that run |
| `runs/<stamp>.dsse.json` | The DSSE envelope alone |
| `anatomy_alive_v6.py` | The harness itself (reproduce a run yourself) |
| `publish_harness_run.py` | The fail-closed publisher (verify-then-publish) |
| `PUBKEY_szlholdings-ec-p256.pem` | Copy of the committed org public key |

## Trust model (honest, binding)

- Run records are DSSE (PAE v1) signed by the **live Hatun MCP gateway**
  (`dsse_sign` tool, ECDSA-P256, keyid `szlholdings-ec-p256`). The signing key
  never touches the publisher.
- The publisher is **fail-closed**: it verifies the gateway's signature against
  the *committed* public key
  ([`hatun-mcp/PUBKEY_szlholdings-ec-p256.pem`](https://github.com/szl-holdings/hatun-mcp/blob/main/PUBKEY_szlholdings-ec-p256.pem))
  before any upload, and re-verifies after upload. Nothing unsigned or
  unverified is ever published. A gateway in placeholder-signer mode aborts the
  publish.
- `run.evidence_sha256` binds each signed record to its full evidence file.
- A signature proves the record was signed by the holder of the org key at
  publish time — it does not upgrade any doctrine claim. Λ remains
  **Conjecture 1**; locked-proven formulas remain exactly 8.

## Verify a record yourself

```python
import base64, json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

rec = json.loads(open("harness_runs.jsonl").readlines()[-1])
env = rec["dsse"]
payload = base64.b64decode(env["payload"])
pae = b"DSSEv1 %d %s %d %s" % (len(env["payloadType"].encode()),
      env["payloadType"].encode(), len(payload), payload)
pub = serialization.load_pem_public_key(open("PUBKEY_szlholdings-ec-p256.pem","rb").read())
pub.verify(base64.b64decode(env["signatures"][0]["sig"]), pae, ec.ECDSA(hashes.SHA256()))
print("OK:", json.loads(payload))
```

## Lineage

Predecessor harness: `run_anatomy_alive.py`
([`.github/coordination/anatomy_alive/`](https://github.com/szl-holdings/.github/tree/main/coordination/anatomy_alive),
2026-05-30 closeout — L1/L2/L5/L6 PASS, L3/L4 STAGED, L7 NOT-YET-WIRED). The v6
harness replaces STAGED labels with live probes of the now-running substrate.
