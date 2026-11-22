# Google Cloud application deployment implementation plan

> Execute inline with `superpowers:executing-plans`. Keep the existing feature checkout and local state; do not create another worktree containing stale infrastructure state.

**Goal:** Replace the five bootstrap images with tested application images, configure private CI/CD, and report the actual supported workflow.

**Architecture:** Preserve the existing five Cloud Run services, registry, service accounts, and WIF. Docker builds immutable release images; the manifest generator owns revisions. Deploy current scaffolds without nonexistent secret versions. CI obtains audience-specific ID tokens through WIF for authenticated health verification.

**Tech stack:** Terraform Google provider, Docker, GitHub Actions OIDC, Python deployment tooling, Fastify, FastAPI.

**Spec:** User's seven-phase application deployment request (2026-11-23).

## Constraints and review focus

- Project `pillars-514405`, region `australia-southeast2`. Never destroy or recreate existing infrastructure unnecessarily.
- Create no state bucket and migrate no state without separate user approval. Preserve the original state and an ACL-restricted backup.
- No service-account keys, fabricated credentials, public backend access, or claims that health-only scaffolds implement business flows.
- Preserve main/push/success/stale-commit guards, exact tested source SHA, and resource-scoped deployment IAM.
- Test missing secret versions, health response identity/version mismatch, redirects or unauthenticated access, and partial rollout failure.
- Repository account currently has push access, no admin access. Report and prepare owner actions for inaccessible settings.

## Task 1: Read-only inventory

- [ ] Inspect docs, source, Dockerfiles, workflows, all live policies and secret version metadata.
- [ ] Verify active project and `terraform plan -detailed-exitcode` returns 0.
- [ ] Record deployable routes versus unfinished application functions.

## Task 2: State protection and migration preparation

- [ ] Make and verify a restricted, Git-ignored local state backup.
- [ ] Prepare a separate bucket bootstrap root with versioning, uniform access, public-access prevention, and deletion protection; prepare inactive GCS backend examples.
- [ ] Request explicit approval naming the bucket and migration. Until answered, keep local backend active.
- [ ] If approved, provision only the state bucket, migrate with locking, compare lineage/resource count, verify a clean plan, and preserve the original snapshot.

## Task 3: Reproducible builds and private deployment

- [ ] Run locked dependency installation, applicable service tests, image builds and local health checks. Diagnose and fix reproducible build blockers with tests where applicable.
- [ ] Add failing manifest tests for deploying scaffolds without unavailable secrets, implement an explicit opt-in for existing secret references, and verify all deployment tests.
- [ ] Tag the exact source release, record immutable image digests, and deploy in dependency order without changing service IAM or names.

## Task 4: CI/CD health verification

- [ ] Add tests for health status, service/version mismatch, HTTP failures, redirect rejection and token redaction; implement the standard-library smoke checker.
- [ ] Add resource-scoped invoker permission for the existing deployment identity on these five services, keeping runtime invocation edges intact.
- [ ] Extend the existing workflow with WIF audience-specific ID-token authentication and health verification for every service. Preserve Terraform template/traffic ignore rules.
- [ ] Configure accessible GitHub variables, environment and branch restrictions. Produce exact commands for owner-only actions. Push a feature branch/PR for review; do not merge main without authorization.

## Task 5: Verify release and service permissions

- [ ] Verify authenticated `/health` service names and release version, unauthenticated rejection, logs, and no Terraform image rollback.
- [ ] Test permitted runtime invocation edges and a denied unrelated edge with short-lived audience-specific tokens; avoid persistent token-creation grants.
- [ ] Deliver a synthetic connectivity-loss callback to private ingest and confirm 202; test invalid input. Document that ingestion stops at logging and no engine/twin/fake business route exists.
- [ ] Record external-callback verification and dashboard-authentication requirements without exposing services.

## Task 6: Final evidence

- [ ] Update the deployment report with release digests/revisions, verification results, remaining owner actions, and state migration disposition.
- [ ] Run relevant tests, configuration validation, `git diff --check`, and final Terraform drift verification.

## Progress

- Initial Terraform drift inspection returned no changes. All five services still use Google's hello image. Docker daemon is now available.
- Only `ci.yml` exists on remote main; deployment files are local uncommitted work from the preceding setup.
- No local `.env` credential file was found. Runtime source does not currently need database/Telstra credentials for its implemented routes.
- Phase 1 complete: live service IAM, registry, WIF and secret metadata inspected;
  no secret payloads read. All four containers have zero versions.
- Restricted local state backup created and SHA-256 verified. Bucket/bootstrap and
  inactive backend examples prepared; explicit migration approval remains pending.
- Added five CI deployment-health invoker grants: 5 added, none changed/destroyed.
- GitHub repository variables configured and re-read successfully. Environment
  creation rejected (403 admin required); branch protection rejected (404).
  Exact owner actions are in `docs/github-deployment-owner-setup.md`.
- Node lint/typecheck/tests/build passed; locked Linux Python checks: engine 65,
  twin 1, template 1, evaluation 2 passed. Deployment tests 15 passed; actionlint
  passed. Initial Twin source copy hit an unreadable host cache; excluding caches
  resolved the environment issue without modifying application source.
- Independent code review found no Critical/Important blockers. Regraded the
  lookalike-domain validation issue as security-important, reproduced with failing
  tests, fixed both URL validators to require `.run.app`, and verified 15/15 green.
- Deferred minor: the existing rollout-failure unit test stops at the first failed
  replacement rather than modeling failure after a successful replacement. The
  sequential loop and subprocess failure propagation are covered, but a later
  partial-rollout test would strengthen coverage. No behavior change was needed.
- Review boundaries resolved: live OIDC/runtime connectivity requires deployment
  verification; unfinished business functionality stays explicitly documented;
  state migration stays gated on the user's separate approval.
