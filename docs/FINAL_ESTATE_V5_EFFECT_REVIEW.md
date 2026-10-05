# Final-estate v5 read-only verification boundary

The v5 verifier consumes existing evidence; it does not publish a release. Its
operational workflow keeps the existing push/main, completed HF Release
Readiness Terminal, and manual trigger lanes. Its pull-request workflow keeps
the active v5 source tests on pull requests to main. Three path filters naming
deleted v4 owners are removed; the deleted owners are not restored.

## Source and verdict

The checkout uses the checker's supported event-SHA expression. Before reading
estate evidence, the verifier requires the canonical repository, main ref,
supported event, exact nonzero event/evidence SHA, actual local Git HEAD, and
the same SHA from the protected main branch API. A workflow-run event must name
HF Release Readiness Terminal. The same source check runs after observations.
A stale upstream SHA, unprotected branch, missing source, local mismatch,
unavailable read, or main movement makes the report NOT_VERIFIED. These are
bounded observations, not an atomic lease or deployment authority.

All existing evidence, release-revision consistency, decommission, A11oy source,
public endpoint, and public PR census gates remain. The liveness gate now checks
the actual PROCESS_ALIVE response, the exact process-only scope, and strict
false production_ready and receipt_minted values. Liveness never substitutes
for readiness. Failed upstream conclusions still prevent success.

## Removed issue publication

The operational workflow no longer has issues:write, passes no --publish-issue
argument, and has no issue publication step. The v5 CLI rejects that former
argument, and GitHubClient has no issue-upsert method. Its transport rejects
every method except GET and rejects request bodies. Existing reconciliation
issues are not updated, reopened, closed, or created by this workflow.

The pure issue_body formatter remains for source compatibility; it has no
transport or publication call. A repository-wide consumer search found no
consumer of the old v5 run-ID artifact names or automatic report-issue updates.
The HF readiness test workflow does consume the v5 workflow's trigger contract;
that coverage is retained. Its actual dependency chain is reviewed in
HF_RELEASE_SOURCE_EFFECT_REVIEW.md; the checker and trigger selection are unchanged.

## Requests, credentials, and bounds

Only the operational verifier receives the existing GITHUB_TOKEN with
contents:read and actions:read. No custom secret, HF credential, GitHub issue write permission,
dispatch, approval, deployment, or provider mutation is introduced. Checkout
uses its declared read access and does not persist credentials. The PR test
commands receive no explicitly supplied credential and invoke no verifier CLI.

Authenticated GETs use only api.github.com: three fixed evidence issues, the
A11oy main commit, the controller's protected main, and the existing public
szl-holdings organization/search/repository-pull census endpoints, and the fixed
finalizer workflow run/artifact endpoints described below. The public
probe set remains the eight fixed URLs in PROBES on a-11-oy.com, a11oy.net, and
szlholdings-a11oy.hf.space. Each probe makes at most one HEAD and one GET.
Redirects are not followed; a redirect is unavailable contract evidence, never
a green response. Ambient proxy/netrc credentials are disabled on both clients.

There are at most 532 authenticated requests: the census retains its existing
512-call/480-second observation bounds and the remaining reads cover source and
evidence. Decoded response bodies and the JSON report are each capped at 2 MiB.
Requests use 10-second connect and 20-second read timeouts, with an additional
60-second body deadline checked between chunks and on completion. These are
not hard real-time process deadlines; the workflow's 30-minute job timeout is
the outer bound. There are no retry loops. Incomplete, oversized, unavailable,
or out-of-scope responses fail; oversized reports fail before file creation.

## Artifacts and exact declarations

The only declared external write for each workflow is one upload of its own
run-scoped artifact. The literal names are final-estate-reconciliation-v5 and
final-estate-reconciliation-v5-pr. GitHub scopes these artifacts to their run;
the name no longer embeds a run ID. Missing files fail upload. Report paths and
the existing 90/30-day retention periods are unchanged. Human-readable output
is a local GitHub step-summary file generated through bounded Python under
bash; it does not send an issue, discussion, or message.

The five new declarations cover this complete workflow dependency chain and
preserve all seventeen prior declarations, policy dates, default denial,
wildcard denial, trusted tool digests, and the unchanged checker. Both v5
closures contain thirteen source/workflow files. Every byte and unknown
identity is pinned. The read transports are reviewed source, not a claim that
the bounded checker formally proves arbitrary Python behavior. A trust-root
review remains required for the policy edit.

## Publication artifact evidence replaces issue 301

HF Release Finalization no longer creates, updates, closes, or reopens its
publication issue. Final-estate's publication gate now reads the exact native
artifact instead of issue 301. The existing readiness issue 257 remains owned
by the unchanged HF Release Readiness Terminal workflow. No issue fallback is
accepted for publication, and pre-existing issue 301 is left untouched.

The reader requires the newest finalizer run on main to have the exact current
controller SHA, canonical repository/workflow/event, successful terminal state,
and positive run and attempt IDs. A newer failed or pending run blocks an
older successful artifact. The unique, unexpired literal-name artifact must
have a complete native listing, native run/source binding, a bounded size, and
a SHA-256 digest. A separate anonymous session downloads the signed HTTPS
artifact URL only from GitHub's supported Azure blob or Actions host suffixes;
no GitHub bearer token is forwarded, and no further redirect is followed.

The ZIP digest, exact single report member, JSON uniqueness/finiteness, v2
schema, report generation, and embedded run/attempt/source binding must all
match. A final native run read rejects a changed attempt. Repeated evidence
reads must retain the same run/artifact/digest. Existing publication-result and
release-revision consistency validators still determine the verdict. Missing,
old, failed, oversized, foreign, or changed evidence cannot qualify the estate.

## Offline qualification and native obligations

The v5 suites cover liveness/readiness separation, controller source movement,
strict protection, read-only transport scope, redirects, byte/call/deadline
limits, failure-report retention, rejected former publication arguments, and
native artifact provenance, digest, archive, and attempt controls. The fixed
HF terminal test runner adds real network/DNS/process denial controls before
its existing twelve source tests. Source-acquisition tests and the existing
actual Git transport fixture suite are also run locally.

The three full finalizer suites require PyArrow, which is absent from every
retained local interpreter checked. They were not mocked, skipped as passing,
or represented as locally qualified. The existing native PR workflow retains
its dependency installation and all three suites; those results are required
before protected admission. The handoff records exact counts and receipts for
all completed local checks. No local result establishes live estate health,
a successful hosted workflow, or a provider release.
