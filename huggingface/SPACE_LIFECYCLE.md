# Hugging Face Space lifecycle authority

**Status: August 31 publication controller retired on 2026-10-02.** The
protected `.github` source used to offer a manual `private-to-public` transition
for every Space in an old 46-Space inventory. That inventory is a historical
observation, not the current keep/retire decision. In particular, it included
`SZLHOLDINGS/terra-assurance`, which the later consolidation treats as a
duplicate to retire.

The [A11oy keep list at `059dc5b`](https://github.com/szl-holdings/a11oy/blob/059dc5bdd9358e8c51af442d7f052ea2d2d9b74b/docs/series-a/hf-space-keep-list.yaml)
records the newer owner decision: eight organization Spaces and one
creator-profile Space are retained; other observed Spaces are paused and made
private before any gated deletion. Its counts describe the September 4 census,
not a live inventory. `SZLHOLDINGS/terra` is a keeper;
`SZLHOLDINGS/terra-assurance` is not. [IMMUNE issue #124](https://github.com/szl-holdings/immune/issues/124)
tracks finalization of the three named private duplicates: `terra-assurance`,
`counsel-assurance`, and `puriq-markets`.

The old workflow, controller script, and active policy path have been removed.
The [August 31 policy](archive/hf-space-lifecycle-policy-2026-08-31.json) is
preserved as the same Git blob under `huggingface/archive/` (LF blob SHA-256
`f4e6d68427fd240d682b9f01a41adace5859abebe12ec5b27eabc11abb46f4fd`).
It was based on authenticated inventory run `33352706604`, source
`ab1e0669b4ac5715e4e26fdbb529db70e6affc33`, artifact `9744148627`,
and artifact digest
`sha256:baac9ac6941a491887d3f28bf6533e2f61000b8722fb2e10dfcdae1b59a2a435`.
The repository test suite now guards against restoring the old workflow or
reconnecting that archived controller.

This source retirement does not mutate Hugging Face, delete a Space, or prove
that a Space is healthy. Existing runs created from old commits need their own
terminal readback; deleting the workflow from main does not invalidate an
already queued run. At this audit, [run `33975602488`](https://github.com/szl-holdings/.github/actions/runs/33975602488)
still appeared as waiting for a production environment decision at old source
`e25adbe3d39b988ced35740a6b58cbfc5ffa920b`. GitHub's cancel endpoint
reported it as completed and its environment rejection endpoint returned 422,
so the API evidence is inconsistent. Do not approve that obsolete run; verify
its terminal state separately in GitHub.

Retirement of the three duplicate Spaces remains a separate provider action.
For each exact target, the gate requires captured source, product, and evidence;
removal of any active publisher; a verified replacement; proof that no unique
secret dependency remains; and a secret-free retirement receipt. The legacy
IMMUNE finalizer contains 49 potential victims and must not be used to execute
the three-target issue. Any new finalizer needs exact target admission and
post-action provider readback before a deletion can be claimed complete.

GitHub `szl-holdings` remains canonical source and governance. Hugging Face
`SZLHOLDINGS` holds the published models, kernels, datasets, and Spaces.
`a-11-oy.com` is the application origin; `a11oy.net` is the dated public proof
inventory. Source merge, provider publication, runtime health, and served site
bytes are separate checks.
