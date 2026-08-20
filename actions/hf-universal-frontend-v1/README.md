# SZL Hugging Face Universal Frontend Contract v1

This composite action verifies a source-native Hugging Face frontend integration without writing to the repository or Hub.

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
    with:
      persist-credentials: false

  - uses: szl-holdings/.github/actions/hf-universal-frontend-v1@<PINNED_COMMIT_SHA>
```

The caller must pin the action to an immutable commit SHA.

Python adapters use a deliberately narrow, statically verifiable form. Import
`Path` from `pathlib`, read the manifest-declared CSS path into one unshadowed
variable, and pass that variable directly to `gradio.Blocks(..., css=...)` (or
another supported Gradio constructor) or to a Streamlit
`markdown(f"<style>{css}</style>", unsafe_allow_html=True)` call. The exact
`# SZL_HF_UNIVERSAL_FRONTEND_V1` marker must be a Python comment.

## Required repository files

- `README.md` with Hugging Face YAML front matter
- `docs/hf-universal-frontend-v1.json`
- the manifest-declared application entry point
- the manifest-declared universal CSS file

## Verified controls

- safe repository-relative managed paths
- exact `szl.hf-universal-frontend/v1` schema
- `remote_mutation: false`
- Static stylesheet links in the HTML namespace, or AST-verified Gradio and
  Streamlit adapters that read and apply the declared CSS file
- short description of no more than 60 characters
- `fullWidth: true` and `header: mini`
- 44-pixel touch-target contract
- five canonical viewport classes
- parsed active overflow, breakpoint, reduced-motion, and
  identifier-wrapping CSS controls (comments, strings, unknown at-rules, and
  non-applying media rules cannot satisfy the contract)
- exact SHA-256 digests for all managed files

The action does not create branches, commits, pull requests, deployments, Space revisions, model changes, dataset changes, collection changes, secrets, signer keys, storage mounts, visibility changes, or hardware allocations.
