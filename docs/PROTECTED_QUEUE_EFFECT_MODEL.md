# Protected queue effect model

The queue controller is a fixed reviewed graph, not a general exception for
GitHub writes. The analyzer binds its complete workflow bytes through
`QUEUE_SOURCE_SHA256`. The policy separately binds the shared admission verifier
and both executable test files. Updating a policy digest cannot make a different
queue graph admissible; the analyzer's trust root and its tests must be reviewed
as well. An owner decision cannot override DENY.

The controller runs only after the named gate completes successfully for a pull
request. Checkout now uses the immutable `github.sha` supplied for `workflow_run`,
with credential persistence disabled, instead of resolving the mutable default
branch again. The write-capable queue credential is introduced only after the
trusted source tests. The shared admission verifier receives a separate read-only
token and runs with the write token removed.

| Operation | Bounded resource | Logical call sites |
| --- | --- | ---: |
| Checkout | This governance repository's trusted controller revision | 1 |
| GraphQL reads | This repository's PR and queue state | 4 |
| Enqueue | This repository's selected PR, with expected head | 1 |
| Dequeue on authority drift | The same selected PR | 1 |
| Upload receipt | Queue artifact namespace, run and attempt scoped | 1 |
| Runner guard configuration | Current hosted runner | 1 |
| Runner guard telemetry | This repository's StepSecurity monitoring | 1 |

The four external-write sites are enqueue, dequeue, artifact upload, and runner
telemetry. They count logical invocation sites, not network retries or telemetry
packets. No merge, ref update, repository write, admin bypass, or arbitrary
GraphQL mutation is admitted by this model. REST evidence reads remain in the
exact reviewed shell/source set; arbitrary shell or Python behavior is not proved
by the parser.

The GraphQL recognizer accepts six literal documents and exact argument vectors.
It rejects mutation aliases, additional fields, substituted IDs or heads, extra
query flags, alternate hosts, input files, and executable redirection paths.
Unknown documents remain a non-waivable error. The complete source profile binds
where the accepted variables originate: same-repository PR selection, exact head,
base and body checks, current gate generation, App status and review, admission
fingerprint, pre-mutation verification, and post-mutation drift cleanup.

Receipt names include both run ID and run attempt. Reruns preserve earlier
receipts without overwrite or deletion authority.

## Evidence and remaining boundary

Offline tests exercise successful admission, HOLD/BLOCK and evidence drift before
mutation, write-token removal, exact operation inventory, malformed GraphQL,
foreign checkout, credential changes, and policy repinning attacks. These tests
do not enqueue a real PR or establish live credential availability.

The attestor is deliberately outside this declaration. Its App-token creation,
cosign/OIDC certificate and transparency writes, App review and status writes,
artifact upload, and protected merge request still need their own explicit
bounded model and transitive action review. Until that work is complete, the
combined PR remains DENY even though the queue's individual static analysis can
ALLOW. No owner acceptance or merge is implied by an individual workflow result.

## Attestor review checkpoint

The existing release-branch merge request now supplies `--match-head-commit`
with the attested head. Its earlier head read could otherwise race a branch
update before the final CLI command. An offline execution regression reproduces
that race and verifies rejection at the command boundary. The main branch still
uses only the separate queue controller. See the
[GitHub CLI merge contract](https://cli.github.com/manual/gh_pr_merge).

The pinned App-token action was inspected at commit
`bcd2ba49218906704ab6c1aa796996da409d3eb1`. Its repository-scoped token creation
also has a post-job `DELETE /installation/token` attempt; revocation failure is
only a warning, so the future model must not claim verified cleanup. The current
workflow explicitly restricts its repository and App permissions. Adding an
owner-only target, arbitrary repository list, alternate API host, enterprise
target, or skipped revocation must stay outside that model.

The pinned cosign installer at `6f9f17788090df1f26f669e9d70d6ae9567deba6`
defaults to cosign `v3.0.6` and verifies the Linux AMD64 binary against SHA-256
`c956e5dfcac53d52bcf058360d579472f0c1d2d9b69f55209e256fe7783f4c74`.
Its default installation path performs a release download and local tool setup.
Custom releases, `main`, alternate install paths, or sudo enable additional
branches and are not covered by that default-path review. Signing-service and
OIDC effects still require cosign binary/source closure review before admission.

| Remaining attestor component | Evidence still needed before a declaration |
| --- | --- |
| App token | Exact create/revoke operations, token lifetime, repository and permission bounds, bundled runtime closure |
| Cosign install | Exact fixed release/checksum and reviewed default installation path |
| Cosign sign | OIDC, certificate, transparency and any timestamp/trust-metadata service effects for the exact binary |
| App approval/status | Exact PR/head/status resources, current admission fingerprint, generation and body binding |
| Signed artifact | Exact artifact namespace, retained evidence and retry behavior |
| Release merge request | Exact expected head and protected release target; no admin or force path |
