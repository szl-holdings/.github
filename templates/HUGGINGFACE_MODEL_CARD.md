---
license: {{HF_LICENSE_ID}}
language:
  - {{LANGUAGE_CODE}}
library_name: {{LIBRARY_NAME}}
pipeline_tag: {{PIPELINE_TAG}}
thumbnail: {{ABSOLUTE_THUMBNAIL_URL}}
tags:
  - szl-holdings
  - governed-ai
base_model: {{BASE_MODEL_ID_OR_DELETE}}
datasets:
  - {{DATASET_ID_OR_DELETE}}
model-index:
  - name: {{MODEL_NAME}}
    results:
      - task:
          type: {{PIPELINE_TAG}}
          name: {{TASK_DISPLAY_NAME}}
        dataset:
          type: {{EVALUATION_DATASET_ID}}
          name: {{EVALUATION_DATASET_NAME}}
          split: {{EVALUATION_SPLIT}}
        metrics:
          - type: {{METRIC_ID}}
            value: {{METRIC_VALUE}}
            name: {{METRIC_DISPLAY_NAME}}
---

<!-- markdownlint-disable MD013 MD060 -->

# {{MODEL_NAME}}

> {{ONE_SENTENCE_CAPABILITY_AND_PRIMARY_USER}}

**Release:** `{{IMMUTABLE_REVISION}}` · **Status:** {{STATUS_LABEL}} ·
**License:** {{LICENSE_NAME}}

## Model summary

{{WHAT_THE_MODEL_IS_AND_WHERE_IT_FITS_IN_THE_SZL_ESTATE}}

| Property | Value |
| --- | --- |
| Architecture | {{ARCHITECTURE}} |
| Parameters | {{PARAMETER_COUNT}} |
| Context length | {{CONTEXT_LENGTH}} |
| Precision | {{PRECISION}} |
| Languages | {{LANGUAGES}} |
| Source revision | `{{SOURCE_REVISION}}` |
| Artifact digest | `{{ARTIFACT_DIGEST}}` |

## Intended use

### Supported

- {{INTENDED_USE_1}}
- {{INTENDED_USE_2}}

### Excluded

- {{EXCLUDED_USE_1}}
- {{EXCLUDED_USE_2}}

This model does not independently establish safety, compliance, factual
accuracy, authorization, or fitness for a high-consequence decision.

## Quickstart

Install dependencies:

```bash
{{INSTALL_COMMAND}}
```

Run a minimal, deterministic example:

```python
{{REPRODUCIBLE_INFERENCE_EXAMPLE}}
```

Pin `revision="{{IMMUTABLE_REVISION}}"` in production or evaluation code.

## Training and lineage

| Stage | Source | Revision or digest |
| --- | --- | --- |
| Base model | {{BASE_MODEL_LINK}} | `{{BASE_MODEL_REVISION}}` |
| Dataset | {{DATASET_LINK}} | `{{DATASET_REVISION}}` |
| Training code | {{TRAINING_CODE_LINK}} | `{{TRAINING_CODE_REVISION}}` |
| Receipt | {{TRAINING_RECEIPT_LINK}} | `{{RECEIPT_DIGEST}}` |

Describe preprocessing, filtering, deduplication, sampling, prompt format,
hyperparameters, random seeds, hardware, training duration, and known gaps.
Mark unavailable lineage explicitly; do not infer it.

## Evaluation

| Evaluation | Result | Scope | Reproduce |
|---|---:|---|---|
| {{EVALUATION_NAME}} | {{RESULT_WITH_UNIT}} | {{DATASET_SPLIT_AND_LIMITS}} | {{EVALUATION_COMMAND_OR_LINK}} |

State when and where each result was measured. Separate upstream-reported
benchmarks from SZL measurements and from modeled results.

## Safety, bias, and limitations

- {{LIMITATION_1}}
- {{LIMITATION_2}}
- {{BIAS_OR_COVERAGE_GAP}}
- {{REQUIRED_HUMAN_OR_POLICY_CONTROL}}

## Hardware and deployment

| Mode | Minimum tested hardware | Notes |
|---|---|---|
| {{MODE_1}} | {{HARDWARE_1}} | {{NOTES_1}} |

## Citation

```bibtex
{{BIBTEX_CITATION}}
```

## Support and changes

- Source: {{SOURCE_REPOSITORY}}
- Security: {{SECURITY_POLICY}}
- Issues: {{ISSUE_TRACKER}}
- Changelog: {{CHANGELOG}}
