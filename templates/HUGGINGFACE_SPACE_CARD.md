---
title: {{SPACE_TITLE}}
short_description: {{SHORT_DESCRIPTION}}
emoji: {{EMOJI}}
colorFrom: {{COLOR_FROM}}
colorTo: {{COLOR_TO}}
sdk: {{SDK}}
sdk_version: {{GRADIO_VERSION_OR_DELETE}}
app_file: {{GRADIO_OR_STATIC_APP_FILE_OR_DELETE}}
app_port: {{DOCKER_APP_PORT_OR_DELETE}}
base_path: {{NON_STATIC_BASE_PATH_OR_DELETE}}
pinned: false
license: {{HF_LICENSE_ID}}
thumbnail: {{ABSOLUTE_THUMBNAIL_URL}}
models:
  - {{MODEL_ID_OR_DELETE}}
datasets:
  - {{DATASET_ID_OR_DELETE}}
tags:
  - szl-holdings
  - governed-ai
---

<!-- markdownlint-disable MD025 -->

# {{SPACE_TITLE}}

> {{ONE_SENTENCE_DEMONSTRATION_AND_AUDIENCE}}

**Runtime status:** {{STATUS_BEHAVIOR_OR_STATUS_ENDPOINT}} ·
**Source:** {{SOURCE_REPOSITORY}} at `{{SOURCE_REVISION}}`

Before publication, delete metadata fields that do not apply. `sdk_version` is
Gradio-only; Docker Spaces use `app_port`; static Spaces use `app_file` and may
add `app_build_command`.

## What this demonstrates

{{TWO_TO_FOUR_SENTENCES_DESCRIBING_THE_REAL_USER_FLOW}}

This Space demonstrates {{EXPLICIT_SCOPE}}. It does not claim
{{EXPLICIT_NON_CLAIM}}.

## Try the primary flow

1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

Expected result: {{EXPECTED_RESULT_AND_EVIDENCE}}

## Immutable dependencies

| Dependency | Repository | Revision |
| --- | --- | --- |
| Model | {{MODEL_ID_OR_NONE}} | `{{MODEL_REVISION_OR_NONE}}` |
| Dataset | {{DATASET_ID_OR_NONE}} | `{{DATASET_REVISION_OR_NONE}}` |
| Application | {{SOURCE_REPOSITORY}} | `{{SOURCE_REVISION}}` |

## Runtime and evidence behavior

- Health or status source: {{STATUS_ENDPOINT_OR_METHOD}}
- Evidence label: {{PROVED_MEASURED_REPORTED_MODELED_CONJECTURE_ROADMAP}}
- Receipt behavior: {{WHAT_MINTS_A_RECEIPT_AND_WHAT_DOES_NOT}}
- Failure behavior: {{HOW_UNAVAILABLE_OR_DEGRADED_IS_DISPLAYED}}

## Privacy and data handling

{{INPUT_LOGGING_RETENTION_TELEMETRY_THIRD_PARTIES_AND_DELETION_BEHAVIOR}}

Do not enter secrets, regulated data, or personal information unless this
section explicitly documents an approved handling contract.

## Run locally

```bash
{{CLONE_INSTALL_AND_RUN_COMMANDS}}
```

## Limits

- {{LIMIT_1}}
- {{LIMIT_2}}
- {{OPERATIONAL_OR_SAFETY_BOUNDARY}}

## Support

- Documentation: {{DOCS_LINK}}
- Source and issues: {{SOURCE_REPOSITORY}}
- Security: {{SECURITY_POLICY}}
