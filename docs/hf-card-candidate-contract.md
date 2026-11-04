# HF card candidate contract

The effect gate now provides `hf_card_candidate_contract(workflow_bytes,
config_bytes)` as an offline implementation component for the future HF card
profile. It checks the two existing declared Space targets, their source-repo
mapping, manual apply guard, apply-only OIDC permission declaration, and the
exact receipt artifact family and path. It also binds the result to the exact
workflow and configuration bytes with SHA-256 digests.

The result always says `NOT_ADMITTED`. `preconditions_matched: true` only means
those declarative preconditions match. It is not an approval, effect declaration,
permission exemption, or proof of runtime behavior. The admission path does not
call this helper. Existing unknowns and the publisher's DENY remain unchanged.

This first component rejects expanded, renamed, duplicate, model, dataset,
private-marked, and body-replacement target declarations; broader permissions;
auto-apply guards; extra jobs; and changed artifact destinations. The pinned
workflow parser keeps YAML scalar text, so this component requires its exact
lowercase `false` and `90` spellings.

## Run the candidate inspection

From the repository root, this reads local source only and prints a candidate
report. No Hub request, token exchange, workflow dispatch, or file write occurs.

```python
import importlib.util
import json
import sys
from pathlib import Path

path = Path(".github/scripts/control_plane_effect_gate.py")
spec = importlib.util.spec_from_file_location("effect_gate", path)
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
report = gate.hf_card_candidate_contract(
    Path(gate.HF_CARD_WORKFLOW).read_bytes(),
    Path(gate.HF_CARD_CONFIG).read_bytes(),
)
print(json.dumps(report, indent=2))
```

## Still required before admission

The next implementation must bind dynamic HTTP method/destination and the
README-only payload; prove the shell's protected-ref, reviewed-plan, and exact
post-write readback boundaries; establish per-target OIDC credential confinement
and the hash-locked dependency closure; and classify the remaining effects.
A real exact-source owner decision is still required afterward. No policy pins,
owner receipt, workflow permissions, or active declarations change here.

Run the candidate controls with:

```sh
python .github/scripts/test_control_plane_effect_gate.py HfCardCandidateContractTests
```

The full effect-gate suite also runs these tests. Its regression control confirms
that candidate inspection neither removes existing unknowns nor grants an OIDC
permission exemption.
