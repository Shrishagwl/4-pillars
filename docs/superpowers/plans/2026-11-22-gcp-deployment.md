# Issue #5 implementation plan

**Goal:** Deploy the five existing backends after successful main-branch CI, without provisioning cloud resources during implementation.

**Architecture:** Terraform manages APIs, Artifact Registry, private bootstrap Cloud Run services, per-service identities, secret containers and repository-restricted WIF. GitHub Actions owns subsequent service revisions through a tested manifest generator. PostgreSQL is externally provisioned Neon (economical default) or Cloud SQL with its authenticated socket connector. Firebase Hosting remains unchanged.

**Constraints:** Preserve CI, Dockerfiles, Compose and application scope. No credentials in source, state or logs. Work on `feature/issue-5-gcp-deployment`; no push, merge or cloud mutation.

## Work

- [x] Add deployment manifest tests, then implement environment/secret references, dependency URLs, limits and optional Cloud SQL mounts.
- [x] Add Terraform infrastructure and a CI-success-gated OIDC workflow using immutable image digests.
- [x] Document setup, database schema isolation, authenticated callers, rollback, costs and manual approval boundary.
- [x] Run available local checks and report unavailable tools/integrations explicitly; add Terraform/actionlint checks to GitHub before deployment.

## Review focus

- A PR/fork, failed CI run or stale main commit must not deploy.
- Each service accesses only its own secrets and permitted downstream services.
- WIF credentials, Terraform state and local configuration must not enter Docker build contexts.
- Partial deployments and rollback preserve secret versions and immutable images.
- Current health checks prove process readiness only: database writes, Pub/Sub and outbound clients remain application work in existing issues.

## Decisions

- Use the clean existing checkout on the requested feature branch.
- Choose private services by default; public Telstra callbacks and dashboard access require application authentication before deliberate exposure.
- Do not create Cloud SQL by default: its ongoing instance/storage costs conflict with the economical default. Supply a reproducible optional setup recipe instead.
- Terraform bootstraps private placeholder services to establish URLs and resource-scoped deployment IAM. It ignores revision templates/traffic afterward; the deployment script owns them explicitly.

## Validation record (2026-11-22)

- Deployment tests: 9 passed. Initial tests failed on the missing module before implementation.
- Existing Python suites: engine 65 passed; twin 1 passed; FastAPI template 1 passed; eval 1 passed, 1 skipped.
- These Python runs used preinstalled Python 3.12.7, FastAPI 0.115.12 and pytest 8.3.5, not the uv-locked CI environment. uv installation was blocked by network restrictions.
- All three workflow YAML files parsed; embedded Bash scripts passed `bash -n`. Main/push/success/fork guards, reusable validation gating and permissions checked structurally.
- All five rendered manifests match Compose environment names, with PORT supplied by Cloud Run. Compose configuration validation passed.
- `git diff --check` passed; existing CI, Compose, Dockerfiles and application source remain unchanged.
- Node install failed with network EACCES; lint/tests/typecheck/build could not pass without dependencies. Docker build failed accessing Docker configuration/buildx; the daemon was also unavailable.
- Terraform was subsequently found at `C:/Users/anubh/Downloads/terraform_1.17.2_windows_386/terraform.exe`. Ran `terraform fmt` and confirmed `fmt -check` passes. Provider initialization failed because the sandbox denied network access to `registry.terraform.io`; provider validation and plan/apply remain unverified. Actionlint is still unavailable locally.
- Independent review: no blocking findings; missing Terraform JSON variable exclusions were found, confirmed and fixed. Final workflow delta reviewed without findings.
- No cloud resources, external settings, secret versions, GitHub variables, commits, pushes or merges were created.
- Deployment was authorized for `pillars-514405`, but the execution sandbox denies access to the running Docker daemon and the Google Cloud credentials database. The SDK is installed at `C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd`. No cloud operation succeeded.

## Authorized Terraform execution (2026-11-22)

- The user's subsequent request to connect to GCP and do all Terraform supersedes
  the earlier no-cloud-mutation constraint for infrastructure provisioning.
- Used approved execution outside the sandbox to access the installed GCP
  credentials and provider registry. Verified project `pillars-514405` is ACTIVE
  and billing-enabled. No new authentication credentials or service account keys
  were created.
- Used `australia-southeast2`, matching the existing gcloud region, rather than
  the generic Sydney example. Resolved GitHub repository ID `1454645919` and owner
  ID `162850908` from the GitHub API for federation restrictions.
- Generated ignored local `infra/gcp/terraform.tfvars` and the version-controlled
  provider lockfile selecting `hashicorp/google` `7.46.2`.
- `terraform init`, `fmt -check`, and `validate` passed. Deployment tests passed
  9/9 when run from the repository root; an initial invocation from `infra/gcp`
  failed because the project module was outside Python's import path.
- Reviewed and applied `bootstrap.tfplan`: 48 added, 0 changed, 0 destroyed.
- Fresh drift verification with `terraform plan -detailed-exitcode` returned 0:
  no changes. GCP confirms all five bootstrap revisions are Ready. Unauthenticated
  HTTP requests to all five service URLs returned 403.
- State, actual variables, and saved plan remain local and Git-ignored. Secret
  values, PostgreSQL setup, GitHub configuration, application deployment, and a
  shared remote-state backend were not created by this infrastructure execution.
