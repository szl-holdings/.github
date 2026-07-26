# Known limitations

- The estate has one human organization member. The policy is explicitly
  solo-operated and does not claim independent human review.
- GitHub records the App review but does not count it toward approval rules that
  require a person with write permission. The non-queued release ruleset
  requires the App-owned `attestation/qillqaq` status, pinned to App ID
  `4395545`. The queued default branch records the status as evidence.
- The public App client ID is a repository Actions variable and the private key
  is a repository Actions secret. The removed local private key cannot be
  recovered; rotation requires generating a new App key.
- The App review and merge-queue path is proven only for this repository;
  estate-wide activation still requires a compatible pilot in each repository.
- Gate mappings in this repository are specific to an organization-governance
  repository. Application repositories require their own real commands.
- GitHub merge queues cannot be enabled in a ruleset that targets wildcard
  refs. `forge9-main` queues the default branch; `forge9-release` protects
  `release/*` with the same gates, staging, and App attestation but no queue.
- A `workflow_run`-driven App status cannot itself be required by the default
  branch queue. GitHub waits for that status before dispatching the
  `merge_group` workflows that trigger its publisher, creating a circular
  dependency. The main ruleset therefore requires the gates and App-pinned
  staging while preserving the App status, review, and signed BAP as evidence.
  A separately hosted webhook service is needed for a queue-blocking App status.
- After that deterministic cycle was removed, GitHub still stopped delivering
  `merge_group` Actions runs for new synthetic queue heads. The active nine-
  check rule is API-identical to historical version `44456196`, which dispatched
  successfully for PR #317. Multiple PR #319 queue heads had zero check suites
  after queue and workflow registration refreshes. This is an external blocker,
  not a passed pilot; see
  `pilots/2026-07-26-merge-group-delivery-blocker.md`.
- GitHub rejected `enqueuePullRequest` for the App installation token despite
  its live merge-queue grant. The App retains attestation and approval duties;
  the ephemeral repository token requests the protected queue after attestation.
- GitHub also rejected queue entry when `required_deployments` was active even
  with a successful exact-head `staging` deployment. Staging is therefore
  enforced by the `deploy/staging` required check pinned to GitHub Actions; the
  workflow still creates deployment evidence and reruns on `merge_group`.
- Required statuses also apply to the synthesized merge-group commit. The
  attestor therefore signs and publishes a second BAP for that SHA; App review
  and the queue request remain PR-head-only operations.
- Commit metadata rules evaluate the full squash message, including the PR
  body. The rulesets enforce the conventional first line and allow the
  remaining body so GitHub's queue-generated commit can pass.
- Twelve archived repositories retain historical ruleset state that cannot be
  edited while archived. They have no active release path.

The `.github` repository is the pilot. Its activation is not complete until
GitHub delivers and passes the required merge-group checks. Estate-wide
completion is claimed only after each active repository has compatible gates
and staging evidence.
