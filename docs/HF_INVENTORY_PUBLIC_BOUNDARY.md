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

The complete authenticated report is an operator record. Publish mode rechecks
protected GitHub main and the exact checkout immediately before writing. It
requires a private `SZLHOLDINGS/szl-evidence` dataset with an immutable starting
revision. One `create_commit` call, guarded by `parent_commit`, updates `latest`
and adds a new history path containing the source revision and report digest.
An existing history path or concurrent parent change fails without retrying.
The publisher requires the reviewed Hub 1.23.0 client and its post-submission
operation flags. That client can otherwise return a newer head without sending
a commit when a concurrent writer has already added identical bytes. This
read-only no-op result is blocked; it is not evidence that our expected-parent
commit ran, and it does not trigger a retry.
Both files are read back at the returned commit and compared byte for byte;
dataset identity, privacy, head, and protected source are checked again before
success. The temporary private readback cache is removed on every exit. JSON
payloads are limited to 8 MiB. This verifies the observed transaction; an
independent administrator can still change dataset visibility concurrently.

Public Actions artifacts and job summaries consume only an allowlisted projection of assets whose
visibility was explicitly observed as public. Collection notes, buckets, private
identifiers, raw errors, and operator action details are withheld. A hash of the
complete private report is also withheld.

Candidate validation runs without organization credentials on pull requests and
merge groups. The protected inventory workflow has a separate credential-free
test job, then exposes HF credentials only to its collector step. Both workflows
install the reviewed `huggingface_hub==1.23.0` and `requests==2.32.5` clients.
The test runner rejects configured HF credentials, disables Hub networking, and
blocks Python socket connections before importing its fixed suite list. Its
publisher calls use only fake clients; the static declaration identifies that
SDK call site as a test-harness effect, not live evidence publication authority.
The collector CLI requires `--publish --expected-before --readback` to enter its
publication path. Failed collection or failed readback remains a failed job;
only a sanitized public failure projection may be uploaded. The issue mirror
and its write permission remain absent.

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
