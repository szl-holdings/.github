# Public model evidence contract

The scheduled `HF Model Evidence Audit` collects public SZLHOLDINGS model-type
repositories at immutable Hub revisions. Its reports identify artifact types,
structured scores, unsafe serialized metadata, unqualified claims and collection
gaps. It makes no Hub writes. The workflow stores a report and updates one GitHub
issue; its enforced result stays red while findings remain.

This replaces the unmerged implementation in PR #516. Conventional sharded
PyTorch files are weight artifacts. A result filename, an empty YAML marker or a
card with no scores cannot qualify a release. Each claim's qualification is
evaluated locally, so a disclaimer about a baseline cannot excuse another claim.

## Accepted evaluation shapes

- Current [Hub evaluation results](https://huggingface.co/docs/hub/eval-results):
  root `.eval_results/*.yaml` or `.yml` files with nonempty `dataset.id` and
  `dataset.task_id`, plus a finite numeric `value` (booleans and numeric strings
  are rejected). Optional verification tokens are never verified by this audit.
- Legacy `model-index` in Hub `cardData` or `model-index.yaml` / `.yml`: at least
  one model name and result with a task type, dataset type and metric type/value.
- `eval_results.json` or `results.json`: the same legacy `model-index` shape, or
  an `eval_results` list with `task_type`, `dataset_type`, `metric_type` and a
  finite numeric `metric_value`. Arbitrary JSON score dictionaries are not
  silently interpreted as comparable benchmarks.

All result files and the card are read at the repository revision recorded in
the report. A malformed, absent or empty result file creates a warning and cannot
meet the result requirement. A valid result can still be synthetic, owner
reported or weak; evidence shape is not independent quality certification.

## Artifact-specific boundaries

Checkpoints, adapters, GGUF derivatives and ONNX exports need validated structured
scores when `--require-structured-eval-for-weights` is enabled. NPZ archives are
classified separately as numeric fixtures or embedding tables. Software kernels
have their own correctness, tolerance, device, timing and package contracts;
neither category receives a transformer evaluation violation solely because it
has no transformer checkpoint. The report explicitly queues their own contract
review and grants no model release qualification from their listing.

`training_args.bin`, pickle and joblib files are flagged without deserialization.
The collector never loads weights or executes repository code. Ordinary PyTorch
weight files still require a suitable tensor-only loader at consumption time.

Unqualified SOTA, fully-trained or frontier claims remain findings even when
structured scores exist. A score record alone cannot establish comparative
leadership, training completeness or runtime readiness.

## Run and interpret

Install the Linux CPython 3.12 dependency with the hash-locked requirement, then:

```sh
python -I -B .github/scripts/test_hf_model_evidence_audit.py
python -I -B .github/scripts/hf_model_evidence_audit.py \
  --org SZLHOLDINGS --min-models 40 \
  --require-structured-eval-for-weights --enforce
```

Exit 0 means the bounded public evidence-shape census completed without enforced
findings. Exit 1 means it completed with findings. Exit 2 means collection was
incomplete. Private inventories, model inference, training, paid compute,
deployment and quality benchmarks belong to separate workflows. The public
collector deliberately uses no Hugging Face token. A 1000-item listing ceiling,
identity changes, duplicate IDs, response limits and coverage collapse fail
collection rather than publish a partial success.
