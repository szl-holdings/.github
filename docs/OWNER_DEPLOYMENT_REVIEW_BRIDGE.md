# Owner deployment review bridge

The archive portfolio restoration workflow uses the `production` GitHub
environment. That environment requires a reviewer before the job can access its
stored credentials and mutate repository archive state.

For the solo-builder estate, the owner can issue that review through a GitHub
issue without removing, weakening, or bypassing the environment rule. The bridge
is deliberately restricted to one workflow and one environment:

```text
repository:    szl-holdings/.github
workflow:      .github/workflows/archive-portfolio-governor-v2.yml
branch:        main
trigger event: push
environment:   production
owner:         stephenlutar2-hash
```

## Command format

The issue title must be exactly:

```text
Approve deployment review: archive-portfolio-v2
```

The issue body must contain exactly one fenced JSON object:

```json
{
  "schema": "szl.deployment-approval/v1",
  "repository": "szl-holdings/.github",
  "workflow_run_id": 123456789,
  "environment_id": 123456789,
  "environment_name": "production",
  "head_sha": "0123456789abcdef0123456789abcdef01234567",
  "workflow_path": ".github/workflows/archive-portfolio-governor-v2.yml",
  "decision": "approved",
  "reason": "Execute the reviewed four-source archive restoration wave."
}
```

The actual run ID, environment ID, and protected-main SHA must come from live
provider readback. The bridge rejects placeholders and stale values.

## Admission checks

Before the review endpoint can be called, the bridge proves:

1. the issue was authored by the exact estate owner;
2. the title, schema, key set, repository, workflow path, decision, and
   environment name are exact;
3. the run was triggered by `push` on `main` from the declared SHA;
4. protected `main` still points to that exact SHA;
5. the run is waiting on one and only one pending deployment;
6. the pending deployment has the declared `production` environment ID;
7. GitHub reports that the selected owner credential can approve;
8. the command and resulting receipt contain no credential-shaped material.

After approval, the bridge re-reads the pending deployment set and workflow run.
The exact environment must no longer be pending and the run identity must remain
unchanged.

## Authority and mutation boundary

The workflow's normal `GITHUB_TOKEN` has read-only source access and issue-write
access. Deployment review is attempted only with an existing owner PAT selected
from the repository secret store. No token is printed, uploaded, placed in a job
summary, or copied into the issue receipt.

The bridge can review the pending deployment. It cannot:

- edit the environment or its reviewers;
- start an unrelated workflow;
- approve another workflow, repository, environment, branch, or SHA;
- change repository archive state directly;
- write source or modify protections/rulesets;
- mutate GitHub secrets;
- mutate Hugging Face;
- turn a source merge or deployment approval into a runtime-success claim.

## Receipt

Every admitted or blocked command emits
`szl.deployment-review-receipt/v1`, uploads it as a 90-day workflow artifact, and
posts a compact, secret-free result on the owner issue. Successful commands are
closed only after the provider review is read back. Blocked commands remain open
with the exact bounded failure reason.
