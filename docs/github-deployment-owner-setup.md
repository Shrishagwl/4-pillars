# Repository owner actions

The authenticated account `Anubhavpatr` has repository push access, but no admin
access. All nine required repository variables have been configured; no GitHub
secrets or service-account keys are needed. `GCP_USE_APPLICATION_SECRETS=false`
deploys the implemented scaffold routes without nonexistent secret versions.

GitHub rejected production-environment creation with HTTP 403, "Must have admin
rights to Repository." Main-branch protection returned HTTP 404 with this account.
An owner/admin must run these from the repository root, authenticated as an admin,
or grant this account repository Admin access:

```powershell
gh api --method PUT repos/Shrishagwl/4-pillars/environments/production --input scripts/gcp/github-production-environment.json
gh api --method POST repos/Shrishagwl/4-pillars/environments/production/deployment-branch-policies --input scripts/gcp/github-production-branch.json
gh api --method PUT repos/Shrishagwl/4-pillars/branches/main/protection --input scripts/gcp/github-main-protection.json
```

The environment accepts only the `main` branch. Branch protection requires the
TypeScript, four Python, Docker Compose, and deployment-configuration checks, one
approving review, and an up-to-date branch; it blocks force pushes and deletions
and applies to administrators. The supplied JSON files are reviewable before use.
Do not replace an existing protection policy without reviewing additional settings
that another administrator may have introduced since this inspection.

Review and merge the deployment PR through the protected branch. The first
successful push CI run on main after the deployment workflow exists there triggers
the five-service rollout and private health verification. Re-run CI on the current
main SHA if bootstrap settings are configured after the push. No merge to main is
performed automatically by this setup.

GCP WIF independently enforces the immutable repository/owner IDs, `main`, the
`workflow_run` event, the exact deployment workflow, and the production subject.
The feature-branch PR cannot obtain deployment credentials. Until the admin actions
and workflow merge are complete, CI/CD is prepared, not claimed to be activated.
