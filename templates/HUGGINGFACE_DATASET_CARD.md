---
license: {{HF_LICENSE_ID}}
language:
  - {{LANGUAGE_CODE}}
task_categories:
  - {{TASK_CATEGORY}}
pretty_name: {{DATASET_NAME}}
thumbnail: {{ABSOLUTE_THUMBNAIL_URL}}
size_categories:
  - {{SIZE_CATEGORY}}
tags:
  - szl-holdings
  - governed-ai
---

<!-- markdownlint-disable MD013 -->
<!-- szl-responsive-card:v1 -->

# {{DATASET_NAME}}

> {{ONE_SENTENCE_CONTENT_AND_PURPOSE}}

**Release:** `{{IMMUTABLE_REVISION}}` · **Status:** {{STATUS_LABEL}} ·
**License:** {{LICENSE_NAME}}

## At a glance

{{WHAT_THE_DATASET_CONTAINS_WHO_CREATED_IT_AND_WHAT_IT_SUPPORTS}}

- **Rows or artifacts:** {{COUNT}}
- **Splits:** {{SPLITS}}
- **Formats:** {{FORMATS}}
- **Languages:** {{LANGUAGES}}
- **Source revision:** `{{SOURCE_REVISION}}`
- **Manifest digest:** `{{MANIFEST_DIGEST}}`

## Supported and excluded uses

### Supported

- {{INTENDED_USE_1}}
- {{INTENDED_USE_2}}

### Excluded

- {{EXCLUDED_USE_1}}
- {{EXCLUDED_USE_2}}

## Load the data

```python
{{REPRODUCIBLE_LOAD_EXAMPLE}}
```

Pin the exact dataset revision in reproducible work.

## Structure

### Splits

- **`{{SPLIT_NAME}}`:** {{RECORD_COUNT}} records. {{SPLIT_PURPOSE}}

### Fields

- **`{{FIELD_NAME}}`** (`{{FIELD_TYPE}}`, nullable: {{YES_OR_NO}}):
  {{FIELD_DESCRIPTION}}

## Provenance and governance

Document collection sources, dates, licenses, consent, attribution,
preprocessing, filtering, deduplication, synthetic generation, and derivation.

- **Raw input:** {{RAW_SOURCE_LINK}} at `{{RAW_SOURCE_DIGEST}}`
- **Transformation:** {{PIPELINE_LINK}} at `{{PIPELINE_REVISION}}`
- **Validation:** {{VALIDATION_LINK}} with receipt `{{VALIDATION_RECEIPT}}`

### Privacy and PII

{{PII_REVIEW_REMOVAL_RETENTION_AND_CONTACT_PROCESS}}

## Validation

- **Schema:** {{RESULT}}. Evidence: {{EVIDENCE_LINK}}
- **Integrity:** {{RESULT}}. Evidence: {{EVIDENCE_LINK}}
- **Contamination or leakage:** {{RESULT}}. Evidence: {{EVIDENCE_LINK}}

## Known gaps and bias

- {{GAP_1}}
- {{GAP_2}}
- {{BIAS_OR_REPRESENTATION_LIMIT}}

## Update policy

{{VERSIONING_CADENCE_COMPATIBILITY_AND_RETENTION_POLICY}}

## Citation and support

```bibtex
{{BIBTEX_CITATION}}
```

- Source: {{SOURCE_REPOSITORY}}
- Security or privacy: {{SECURITY_POLICY}}
- Issues: {{ISSUE_TRACKER}}
- Changelog: {{CHANGELOG}}
