<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->
## SZL LLM Router · Flagship Inference Control Plane

<table>
<tr>
<td width="64%" valign="top">

**One governed endpoint in front of many brains.** The router selects among sovereign, free-grid, and paid fallback tiers; records why a route was selected; and attaches an independently inspectable receipt to every completed response.

`szl-auto` · `szl-fast` · `szl-large` · `szl-coder`

- **Sovereign-first:** operator-owned GPU routes are attempted before external providers when they are actually reachable.
- **OpenAI-compatible:** clients use the familiar `/v1/chat/completions` contract.
- **Fail-closed provenance:** unavailable providers are skipped or surfaced; no response or signature is fabricated.
- **Receipt-native routing:** model, provider tier, attempts, request digest, cost basis, and routing rationale remain reviewable.

</td>
<td width="36%" valign="top">

**Authority chain**

1. [GitHub source](https://github.com/szl-holdings/szl-router)
2. [Hugging Face runtime](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live)
3. [A11oy operator interface](https://a-11-oy.com/code)
4. [Proof and known bounds](https://a11oy.net)

**Runtime truth:** `LIVE`, `CONFIGURED_UNVERIFIED`, `OFFLINE_UNTIL_KEYED`, or `UNAVAILABLE`—never implied from a polished card.

</td>
</tr>
</table>

> Model output never creates execution authority. Independent policy constrains routing, and a human binds consequential action. Λ uniqueness remains **Conjecture 1 — open**.
<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->
