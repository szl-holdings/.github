# Executable archive recovery — September 8, 2026

The authenticated organization inventory contained 123 repositories, of which 30
were archived before this recovery. The four original portfolio restorations,
including `szl-router`, were already active. The owner requested recovery and
modernization of useful archived components and their ecosystem integration.

Two source comparisons justify expanding the bounded restoration set from four
to six. Both repositories were restored with an `archived=false` GitHub readback
on September 8. This policy update reconciles the maintained source registry
with that authorized recovery; it grants no visibility, protection, history or
Hugging Face mutation.

| Source reviewed | Distinct executable role | Comparison and integration |
|---|---|---|
| [vsp-otel at b81c286](https://github.com/szl-holdings/vsp-otel/tree/b81c28666ecf411d50556531ca23e3981447f5fb) | OTLP collector, signed-span exporter and Helm package | 92 files, 37 executable blobs; 25 have no identical blob among the 19 inspected active successors. README explicitly identifies platform as a partial mirror. Collector source remains here; substrate supplies common contracts and Lyte consumes observability evidence. |
| [szl-build-env at ccc1250](https://github.com/szl-holdings/szl-build-env/tree/ccc12507daf2668de8c387baede2e344d24be745) | Local development topology and runtime acceptance kit | 45 files, including 13 executable blobs with no identical active successor copy. Owns DSSE verification, exact route acknowledgement and connected Jaeger trace checks. Forge retains training and publication authority. |

Blob comparisons establish missing identical copies; they do not prove that no
semantically similar implementation exists. The source-local README and actual
collector, verifier and deployment entrypoints establish the recovery roles.

`szl-router` remains the gateway source authority; A11oy remains the canonical
model/policy consumer. Build acceptance must check gateway GitHub revision,
configuration admission and completed inference receipts separately. Telemetry
must report failed forwarding and signing configuration honestly before runtime
promotion. No new Hugging Face Space is introduced by these restorations.

The remaining 28 archives retain their existing consolidation or historical
disposition in this bounded wave. Reusable lab, sampler, proof-service and kernel
verification code needs further source comparisons against its actual maintained
owner. Immutable preprints and event evidence are preserved. These dispositions
do not establish that all useful code has already migrated.

Build-env's historical five-service deployment remains subject to its explicit
image identity, GHCR access, fan-out and OTLP runtime prerequisites. A passing
offline test or an unarchive operation does not satisfy those requirements.
