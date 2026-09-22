# Yarqa

**Plug-flow compartmentalization for compartmental models.** Clean-room implementation, Apache-2.0.

Yarqa is the SZL compartmental-flow kernel published as a public Space: a FastAPI
service in front of the `yarqa` Python package, served with a sovereign static
front end that vendors THREE r160 and loads zero CDN assets.

## What is in this repository

| Component | Contents |
|---|---|
| `yarqa/` package | `core`, `surrogate`, `meshio`, `chain`, `provenance`, `attestation`, `signing`, `agentic`, `cli` |
| `space/` app | `app.py` FastAPI entrypoint, `feeds.py`, vendored static assets, tests |
| Build | digest-pinned `python:3.11-slim`, hash-locked `requirements.lock`, `pip check` in the image |
| Runtime | uvicorn on port 7860, non-root `yarqa` user, container `HEALTHCHECK` against `/livez` |

Declared package version: `yarqa 0.5.0`, requires Python >= 3.9, single runtime
dependency `numpy>=1.23`.

## Runtime contract

`GET /livez` answers a liveness object carrying `service: yarqa-space`,
`check: liveness`, and the resolved `yarqa_version`. The container healthcheck
fails closed if any of those fields is absent, so a serving container is not
reported healthy on a partial boot.

When the image is built with `SZL_GIT_SHA`, the value is validated as a
40-character lowercase hex revision and written read-only to
`/usr/share/szl/source-revision`, binding the running container to an exact
source commit.

## Truth states

| Claim | State |
|---|---|
| Package and space source present in this repository | MEASURED |
| Apache-2.0 licensing | MEASURED (declared in `pyproject.toml` and the Dockerfile SPDX header) |
| Container liveness contract | MEASURED (enforced by `HEALTHCHECK`) |
| Throughput, tokens/s, CUDA or SageAttention acceleration | UNAVAILABLE — not claimed and not measured here |
| Energy or joule accounting | UNAVAILABLE — never fabricated |

Reachability of a running Space is not a production certificate, and a passing
liveness check does not authorize a consequential workload.

## Governance

- Hub Space repository: `SZLHOLDINGS/yarqa`
- Source of truth: [github.com/szl-holdings/yarqa](https://github.com/szl-holdings/yarqa)
- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE
- Receipts remain UNSIGNED_HONEST until the DSSE lane signs

Apache-2.0. Copyright 2026 SZL Holdings.
