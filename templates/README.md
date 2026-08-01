# Public surface templates

These templates make every SZL repository and Hugging Face artifact easy to
evaluate for investors, operators, researchers, and developers. They define a
common information architecture without forcing unrelated projects into the
same technical stack.

| Template | Use it for |
| --- | --- |
| [`REPO_README.md`](./REPO_README.md) | Public or internal GitHub repository front doors |
| [`HUGGINGFACE_MODEL_CARD.md`](./HUGGINGFACE_MODEL_CARD.md) | Model repositories on Hugging Face |
| [`HUGGINGFACE_DATASET_CARD.md`](./HUGGINGFACE_DATASET_CARD.md) | Dataset repositories on Hugging Face |
| [`HUGGINGFACE_SPACE_CARD.md`](./HUGGINGFACE_SPACE_CARD.md) | Space README and runtime contract |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Repository contribution policy |
| [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) | Community participation rules |
| [`SECURITY.md`](./SECURITY.md) | Vulnerability reporting and response |

## Adoption contract

1. Copy the relevant template into the target repository.
2. Replace every `{{PLACEHOLDER}}`; unresolved placeholders fail review.
3. Delete sections that genuinely do not apply. Do not invent metrics,
   customers, evaluations, security controls, or operational state.
4. Link every status or performance claim to its owning evidence.
5. Run the target repository's native checks and validate every copied command.
6. Publish through a protected pull request with normal review.

The complete hierarchy, vocabulary, accessibility target, and rollout gate are
defined in
[`PUBLIC_EXPERIENCE_STANDARD.md`](../docs/PUBLIC_EXPERIENCE_STANDARD.md).

Hugging Face `{{HF_LICENSE_ID}}` values use the Hub's lower-case repository
card identifiers, such as `apache-2.0` or `cc-by-4.0`, not display-case SPDX
spelling. Confirm every value in the
[Hugging Face license registry](https://huggingface.co/docs/hub/en/repositories-licenses).

These templates are starting points. The target repository remains the source
of truth for its license, maturity, support model, and runtime behavior.
