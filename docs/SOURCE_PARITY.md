# SZL source parity

This document records the source authority for the SZL application surfaces
and preserves the observations made on October 27, 2026. Workflow completion
was checked again on November 1, 2026. This is historical evidence, not a
claim about the current default branches or live deployments.

GitHub is the canonical source. Hugging Face is a runtime or artifact surface
whose revision must be compared against an immutable GitHub revision before a
deployment claim is made. A reachable Space, a model card, or a dataset does
not establish source ownership.

## Recorded application source

| Surface | Python backend | Frontend | Packaging |
| --- | --- | --- | --- |
| A11oy | serve.py, requirements-runtime.txt | React/Vite/TypeScript under web/ | Dockerfile |
| Living Anatomy | server.py, living_runtime.py | vendored static HTML/JavaScript atlas | Dockerfile |
| Second Brain | app.py, app_refinement.py | static index.html and chamber.html | Dockerfile |
| Khipu | szl_khipu/http_app.py and package modules | Space presentation under space/ and spaces/ | repository packaging |

The frontend framework remains the framework already used by each product.
The parity contract does not rewrite a working React or static frontend into
Python.

## Historical alignment and completed workflow evidence

- SZLHOLDINGS/a11oy reported source revision
  `2ce00a0430088100a0d5f076d315bfd6e0e8e712` in the recorded readback.
  [Run 40601233480](https://github.com/szl-holdings/a11oy/actions/runs/40601233480)
  completed with **failure**. Its exact runtime/source verification job
  `122530231615` succeeded at `2026-10-27T23:25:26Z`; that job is no longer
  pending. The later execution-evidence collector `122533095547` failed with
  `EXECUTION_EXPORT_COLLECTION_UNAVAILABLE` and `execution_authorized=false`.
  Final live/singleton proof, strict parity, and reauthorization jobs were
  skipped. Successful passive readback does not establish admitted execution
  or overall production readiness.
- At the recorded revisions, selected SZLHOLDINGS/szl-khipu package files
  matched szl-holdings/szl-khipu. Its flattened Space layout is a deployment
  adapter; full runtime qualification was not established.
- At the recorded revisions, selected betterwithage/anatomy files matched
  szl-holdings/anatomy. The Space is outside the SZLHOLDINGS organization;
  the observation grants no transfer or write authority.
- No dedicated SZLHOLDINGS Second Brain Space was observed in that snapshot.
  This is not a current exhaustive inventory. The Second Brain
  datasets are projection artifacts and do not replace the GitHub runtime.

The machine-readable evidence, immutable revisions, paths, and blockers are
in [SOURCE_PARITY_MANIFEST_V1.json](SOURCE_PARITY_MANIFEST_V1.json).
The October observations have not been relabelled as fresh live measurements.
