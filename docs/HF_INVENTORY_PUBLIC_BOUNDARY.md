# Public and private Hugging Face inventory evidence

The official estate collector uses native `/api/kernels` discovery and
`HfApi.kernel_info` plus immutable `repo_type="kernel"` file readback. A model
repository labeled `library_name: kernels` remains a separate repository.
Observed build files do not establish compatibility, performance, or execution.

The native discovery adapter validates the exact HTTPS management origin and
path before using its bearer session. Redirects, unexpected query fields,
pagination cycles, duplicate records, malformed records, duplicate JSON keys,
nonfinite JSON numbers, and mismatched readback identities fail collection.
The adapter bounds pages, records, response bytes, file entries, and read timeouts.
Failure is preserved as an unknown category rather than a zero-asset claim.

The complete authenticated report is an operator record. Publish mode first
checks that the evidence dataset is private. Public Actions artifacts, issues,
and job summaries consume only an allowlisted projection of assets whose
visibility was explicitly observed as public. Collection notes, buckets, private
identifiers, raw errors, and operator action details are withheld. A hash of the
complete private report is also withheld.

The projection can be produced locally without authentication or network access:

```sh
python .github/scripts/hf_official_estate_inventory_compat.py \
  --public-projection reports/hf-official-estate-inventory-latest.json \
  --output reports/hf-official-estate-inventory-public.json
```

Older public issue bodies and Actions artifacts are not repaired by a source
change alone. Preserve their operator evidence and review each affected public
record separately. The collector does not change asset visibility, restart
Spaces, publish kernels or models, or certify full organization coverage.
