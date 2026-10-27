# SZL source parity

This document records the source authority for the SZL application surfaces.

GitHub is the canonical source. Hugging Face is a runtime or artifact surface
whose revision must be compared against an immutable GitHub revision before a
deployment claim is made. A reachable Space, a model card, or a dataset does
not establish source ownership.

## Verified application source

| Surface | Python backend | Frontend | Packaging |
| --- | --- | --- | --- |
| A11oy | serve.py, requirements-runtime.txt | React/Vite/TypeScript under web/ | Dockerfile |
| Living Anatomy | server.py, living_runtime.py | vendored static HTML/JavaScript atlas | Dockerfile |
| Second Brain | app.py, app_refinement.py | static index.html and chamber.html | Dockerfile |
| Khipu | szl_khipu/http_app.py and package modules | Space presentation under space/ and spaces/ | repository packaging |

The frontend framework remains the framework already used by each product.
The parity contract does not rewrite a working React or static frontend into
Python.

## Current alignment

- SZLHOLDINGS/a11oy is source-bound to szl-holdings/a11oy and its observed
  runtime revision matches the recorded key-file snapshot.
- SZLHOLDINGS/szl-khipu is source-bound to szl-holdings/szl-khipu; its
  flattened Space layout is a deployment adapter.
- betterwithage/anatomy matches szl-holdings/anatomy, but the Space is
  outside the SZLHOLDINGS organization. It remains read-only until ownership
  is explicitly resolved.
- No dedicated SZLHOLDINGS Second Brain Space was observed. The Second Brain
  datasets are projection artifacts and do not replace the GitHub runtime.

The machine-readable evidence, revisions, paths, and blockers are in
SOURCE_PARITY_MANIFEST_V1.json.
