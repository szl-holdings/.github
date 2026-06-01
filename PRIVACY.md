# PRIVACY.md — SZL Holdings Public Privacy Posture

**Updated:** 2026-06-02
**GDPR contact:** stephenlutar2@gmail.com

---

## What SZL Holdings Collects

| Data type | Source | Purpose |
|---|---|---|
| Khipu chain receipts | Flagship HF Spaces (a11oy, amaru, sentra, rosie, killinchu) | Audit trail of governance decisions; cryptographically signed DSSE envelopes |
| GitHub interactions | GitHub API | Repository management, CI/CD, issue tracking |
| HF Space interactions | Hugging Face API | Space deployment, build logs, runtime metrics |

---

## What SZL Holdings Does NOT Collect

- **PII from end users of flagship Spaces** — All HF Spaces are public and unauthenticated. No user accounts, no login, no cookies, no tracking pixels. Callers are anonymous.
- **Browsing history or behavioral profiles** — No analytics beyond server-side request logs retained per HF's standard policy.
- **Financial data** — No payment processing on any flagship surface.

---

## Sub-Processors

| Sub-processor | Purpose | Privacy policy |
|---|---|---|
| Hugging Face | Space hosting, build infrastructure | <https://huggingface.co/privacy> |
| GitHub | Source control, CI/CD, org profile | <https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement> |
| Zenodo (CERN) | DOI registration, thesis archival | <https://about.zenodo.org/privacy-policy/> |

---

## Retention

| Data | Retention |
|---|---|
| Khipu chain receipts | Indefinite — receipts are the audit trail; deletion would break chain integrity |
| HF Space server logs | 90 days (HF platform default) |
| GitHub audit logs | Per GitHub org plan |
| Telemetry | 90 days |

---

## GDPR Rights

**Controller:** SZL Holdings (Stephen Lutar, sole founder)
**GDPR contact:** stephenlutar2@gmail.com

Because the public flagships collect no end-user PII, Article 17 (right to erasure) requests from flagship users will receive a signed receipt confirming that no personal data is held. Submit erasure requests to:

```
POST https://SZLHOLDINGS-rosie.hf.space/api/rosie/v2/unay/erase
Body: { "caller_id": "<identifier>", "confirmation": "DELETE-MY-DATA" }
```

The response is a Wire D DSSE-signed receipt acknowledging the request, regardless of whether any data exists.

For GitHub or Zenodo data, contact those sub-processors directly via their GDPR portals.

---

## Jurisdiction

SZL Holdings is a US-based entity. Where EU/UK GDPR applies, SZL Holdings honors data subject rights to the extent technically feasible given the public, unauthenticated nature of the flagship surfaces.

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
