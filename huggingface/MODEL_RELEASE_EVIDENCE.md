# Hugging Face model release evidence

The `SZLHOLDINGS` Hugging Face Models tab contains several artifact classes.
A count from that tab must not be presented as a count of fully trained models.
Checkpoints, adapters, quantizations, NumPy demonstrations, software kernels,
documentation, and roadmap reservations are separate categories.

## Release boundary

A weighted artifact is not evidence-complete until its public package binds:

- an immutable Hub revision and the SHA-256 of every released binary;
- the exact base model and base revision;
- tokenizer, processor, chat-template, and configuration hashes;
- versioned dataset bytes, licenses, split membership, and leakage controls;
- source revision, recipe, dependency lock or image digest, seed, precision, and
  hardware;
- held-out evaluation inputs, raw outputs, scorer source, runtime, decoding
  configuration, failures, and uncertainty where applicable;
- Hub-standard `model-index` or `eval_results` metadata for discovery; and
- a safe serialization policy. Pickle-style trainer metadata is not an
  inference dependency.

Alternative adapters or quantizations need unambiguous identities. Keep one
canonical default artifact per model ID, or publish variants under separate IDs
or immutable releases with an explicit selector.

## What the automated gate proves

The `HF Model Evidence Audit` workflow reads public model repositories without
mutating them. At each exact Hub revision it records artifact type, weight
files, structured result metadata, unsafe executable-style files, and
unqualified frontier claims. It fails closed when collection coverage drops,
when weighted repositories lack structured results, when executable trainer
metadata is published, or when an unqualified frontier claim lacks structured
results.

Passing this static gate does not prove state-of-the-art quality, independent
validation, deployment, runtime health, or production readiness. Those claims
require the same public harness against named baselines plus separately bound
deployment and runtime evidence.

## Current migration rule

Existing gaps remain visible as a red scheduled issue until remediated; they are
not allowlisted into a false pass. Repositories that intentionally contain only
kernels, documentation, or roadmap material are classified as non-weight
assets and do not need fabricated training evidence. Their software contracts,
benchmarks, packaging, and source-to-Hub parity remain separate gates.
