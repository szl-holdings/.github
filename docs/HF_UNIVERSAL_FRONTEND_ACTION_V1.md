# Organization-wide Hugging Face Universal Frontend Action v1

## Architecture

Each Space repository owns its framework-native adapter, application source, card metadata, and canonical deployment workflow. The organization repository owns one reusable, read-only verifier:

```text
source-native adapter
+ repository manifest
+ pinned organization verifier
+ protected merge
+ existing Space writer
+ estate-wide live census
```

This prevents two failure modes:

1. copying one application shell across unrelated Static, Gradio, Streamlit, React, and Docker architectures;
2. allowing local verifier forks to drift until identical claims have different meanings.

## Trust boundary

The shared action verifies only committed repository state. It has no network dependency and requires no token, secret, Hub credential, or write permission.

It validates:

- safe repository-relative managed paths
- exact evidence schema
- explicit non-mutation boundary
- framework-native CSS binding
- Hugging Face card metadata boundaries
- five canonical viewport classes
- 44-pixel touch targets
- horizontal-overflow prohibition
- reduced-motion and technical-identifier wrapping controls
- exact managed-file SHA-256 digests

It does not prove live runtime readiness. Live readiness remains the responsibility of the estate-wide browser census and source/runtime revision readback.

## Pinning policy

Callers must pin the action to a full immutable commit SHA. Floating references such as `main`, tags without immutable policy, or version branches are not admissible in protected CI.

## Promotion policy

The action is read-only. It may not create branches, commits, pull requests, releases, deployments, Hub revisions, model updates, dataset updates, collection changes, secrets, signer keys, storage mounts, visibility changes, or hardware allocations.
