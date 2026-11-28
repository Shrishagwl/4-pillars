# Backend deployment to Google Cloud

Issue #5 deploys `ingest-api`, `telstra-gateway`, `telstra-fake`, `engine` and
`twin` into one existing Google Cloud project and one Artifact Registry repository.
The React dashboard stays on **Firebase Hosting**. This configuration does not
provision Firebase, Pub/Sub, application database migrations or Telstra subscriptions.

The configured deployment target is `pillars-514405` (project number
`456555007600`) in `australia-southeast2` (Melbourne), matching the existing
Google Cloud CLI configuration. The commands below use `australia-southeast1`
as a generic example; substitute `australia-southeast2` for this deployment.
Local project settings are in the ignored `infra/gcp/terraform.tfvars`.
The generated `.terraform.lock.hcl` pins the Google provider to `7.46.2`.

## Application release verified (2026-11-23)

The five services now run application images built from source commit
`4d1840877c2d7c287c887b2bbeb15ac9d6fb7c9e`. Each image was built with the original
Dockerfile, pushed to the existing registry, and deployed by immutable digest.
All original Cloud Run service UIDs are preserved; each ready application revision
receives 100% traffic. No service was destroyed, recreated or made public.

| Service | Ready revision | Image digest (`sha256:`) |
|---|---|---|
| telstra-fake | `four-pillars-telstra-fake-00002-jw4` | `faba05c84896e9f06ee2afcd95778d8f65af40c1e6fb62d0be15e2e4afb77d56` |
| telstra-gateway | `four-pillars-telstra-gateway-00002-b58` | `33193975f287685b589a026f0941b29ec2571afc0b94e14e0442cb557ce99376` |
| engine | `four-pillars-engine-00002-hzz` | `63d581c9e9230d05752557609985137784c6bc73a11d02e46ab8b4f098de7539` |
| ingest-api | `four-pillars-ingest-api-00002-b2r` | `2d08f0d529d6c33f5715b30cabd0e33105c0d41ff65c7ddeac50ccfb188ec0ec` |
| twin | `four-pillars-twin-00002-62h` | `356f4cf7df58ca91d3c56c192552d780c3848f471a1a7ca00179b7183404fcca` |

Registry image path: `australia-southeast2-docker.pkg.dev/pillars-514405/four-pillars/SERVICE@sha256:DIGEST`.
The existing service URLs remain valid; use `terraform output service_urls` to
retrieve them. Runtime limits remain zero minimum/two maximum instances per revision,
one vCPU, 512 MiB, concurrency 20 and a 60-second request timeout.

Live verification on 2026-11-23 Sydney time:

- All five `/health` responses returned 200 with the exact service and release SHA,
  using short-lived audience-specific ID tokens as the deployment service account.
- Unauthenticated requests returned 403 for every service.
- All five permitted runtime identity edges returned 200: ingest to engine, engine
  to gateway, gateway to fake, twin to fake, and twin to ingest.
- The unrelated fake identity was rejected by engine with 403; a token with the
  wrong audience was rejected by ingest with 401.
- A synthetic `LOSS_OF_CONNECTIVITY` report was submitted to the private ingestion
  callback using the twin identity. It returned 202 with `accepted: 1`; reason
  code 99 was rejected with 400. Request/subscription ID:
  `deployment-smoke-670a9c12-cb10-4517-9e95-e639dfde86ac`.
- Cloud Logging contains the accepted report and no error entries in the
  verification window. Tokens were held only in memory. Temporary conditional
  `roles/iam.serviceAccountOpenIdTokenCreator` grants, bounded by a 30-minute expiry,
  were removed after verification. Fresh grants initially required IAM propagation;
  no broader token-creation role was granted.
- A final refreshed Terraform plan returned exit code 0 with no changes after the
  application rollout. All six identities were independently checked after cleanup;
  no temporary verification bindings remain. A separate full-hour error-log query
  covers the rollout and verification window.

These requests verify IAM and implemented endpoints. They do not demonstrate a
business event traveling through all five applications. The implemented capability
boundary is:

| Application | Implemented in this release | Still unfinished |
|---|---|---|
| Ingest API | Health, callback schema validation, acceptance and logging | Persistence and publication/forwarding to engine |
| Decision Engine | Health; 65 tested pure clustering/scoring/decision tests | HTTP event route and gateway/database integration |
| Telstra Gateway | Health; private fake URL configured | Telstra API proxy and outbound authenticated client |
| Fake Telstra | Health | Fake API responses and subscriptions |
| Digital Twin | Health; private ingest/fake URLs configured | Simulator and event-generation routes |
| React dashboard | Existing static placeholder builds | Authorized backend data API and incident/map UI |

The operator-generated synthetic event stops at ingest logging. No verdict,
database persistence, or simulator completion is claimed. Existing fake URLs are
configured without fabricated Telstra credentials. All four secret containers
remain empty and are not mounted; real secret integration stays opt-in.

CI/CD changes are in [PR #61](https://github.com/Shrishagwl/4-pillars/pull/61).
The seven PR checks passed: TypeScript; Python engine, twin, template and evaluation;
Docker Compose build/start/health; and deployment configuration validation.
Local deployment tooling has 15 passing tests. All nine required non-secret GitHub
variables are configured. Five service-scoped CI invocation bindings were added
with Terraform (53 total resources). Images and traffic remain ignored by Terraform.

The deployment workflow is on the feature branch, not merged into main. GitHub
production-environment and branch-protection settings require an admin; this
account's attempts returned 403 and 404 respectively. See the exact
[owner setup commands](github-deployment-owner-setup.md). Automatic production
deployment and a GitHub-issued WIF exchange cannot be claimed verified before
those settings and the workflow merge. No service-account key was created.

State remains local. Both the original 48-resource state and the subsequent
53-resource state have hash-verified snapshots in `.tools/state-backups/`, with
access limited to the operator, the local agent account and SYSTEM. Original
snapshots are preserved. The private/versioned bucket and inactive backend
configuration are prepared, but explicit bucket/migration approval is pending;
see [state migration](terraform-state-migration.md).

## External access remains gated

Telstra callbacks currently require a Google IAM identity, so the live external
Telstra platform cannot call this private endpoint directly. Before public callback
onboarding, implement a dedicated edge that verifies the vendor's documented
callback authentication, validates subscription ownership and replay protection,
and applies rate/payload limits. Its dedicated identity should invoke only ingest
with a target-audience Google ID token. Confirm the actual supported Telstra
authentication mechanism before implementing that edge; it does not exist here.

The static dashboard has no authorized data route yet. A suitable next step is an
application backend that verifies Firebase user identity, enforces per-user access,
and calls private services with its own scoped runtime identity. Browser CORS alone
does not grant authorization, and a browser Firebase token is not a substitute for
Cloud Run service-account IAM authentication. Keep internal services private while
building this boundary; no unauthenticated callback or dashboard bypass was added.
See [Cloud Run service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
and [Firebase token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
for the distinct service and user identity boundaries.

## Provisioning record (2026-11-22)

The user subsequently authorized connecting to GCP and applying Terraform.
The saved plan applied successfully: **48 added, 0 changed, 0 destroyed**.
All five private bootstrap services report Ready, and each rejects unauthenticated
HTTP requests with 403. A subsequent `terraform plan -detailed-exitcode` returned
exit code 0 with no changes. `terraform fmt -check`, `terraform validate`, and all
nine deployment manifest tests passed.

The registry is `australia-southeast2-docker.pkg.dev/pillars-514405/four-pillars`.
The deployment identity is
`four-pillars-deployer@pillars-514405.iam.gserviceaccount.com`; the WIF provider is
`projects/456555007600/locations/global/workloadIdentityPools/four-pillars-github/providers/github`.
Federation is restricted to repository ID `1454645919`, owner ID `162850908`, and
the production deployment workflow described below. No service account key was created.

Terraform state currently remains local at `infra/gcp/terraform.tfstate`, excluded
from Git and Docker build contexts along with the local variables and saved plan.
Preserve this state file for future Terraform operations; do not initialize a fresh
state against the same resources. A shared GCS backend has not been provisioned.

At the end of initial provisioning the services ran Google's hello bootstrap
image, secret containers had no versions, and application deployment and GitHub
configuration were still pending. Retrieve the exact
non-secret deployment values with `terraform output github_variables` and the
service endpoints with `terraform output service_urls` from `infra/gcp`.

**Approval boundary:** reviewing files and running local checks creates no cloud
resources. Obtain approval for the costs below before creating a project, enabling
billing/APIs, running `terraform apply`, adding secrets or running a deployment.
The application deployment request separately authorizes deployment and CI/CD IAM
changes. State-bucket creation and state migration require separate approval;
see [the prepared migration](terraform-state-migration.md).

## Costs and limits — read before provisioning

- Cloud Run uses request-based billing, zero minimum instances, one vCPU and
  512 MiB per instance, concurrency 20, a 60-second request timeout and a maximum
  of two instances **per service/revision** by default. Idle services scale to zero;
  requests, startup, egress and logging can still incur charges. During deployment,
  old and new revisions may coexist and instance limits are not a hard spending cap.
- Artifact Registry charges for stored images beyond its allowance. Five new images
  per deployment accumulate. Review storage weekly and remove images older than your
  rollback window only after checking deployed revisions. Keep at least the last
  two working releases. No automatic deletion is configured, to protect rollback.
- Secret Manager charges for active secret versions/access beyond its allowance.
  Disable old versions only after the rollback window closes.
- Neon is the default economical option: choose its Free plan if its current limits
  fit the demo. A paid Neon plan, regional egress and excess usage can add costs.
- Cloud SQL has ongoing instance and storage charges even when Cloud Run scales
  to zero. It is optional and **not provisioned by Terraform**. A small zonal shared
  core instance is suitable for a demo, not production reliability. Backups and
  storage are separately billable. Review the regional price before choosing it.
- Set a billing budget with alerts (for example USD 5/10/20) before deployment;
  budgets notify, they do not stop spending. GitHub Actions, Firebase Hosting and
  retained workflow artifacts have their own allowances.

Use current regional prices rather than assuming the free allowances apply:
[Cloud Run](https://cloud.google.com/run/pricing),
[Artifact Registry](https://cloud.google.com/artifact-registry/pricing),
[Secret Manager](https://cloud.google.com/secret-manager/pricing),
[Cloud SQL](https://cloud.google.com/sql/pricing), [Neon](https://neon.com/pricing).

## What exists and who manages it

The existing CI workflow is unchanged. It tests TypeScript/Python, builds Compose,
starts all containers and checks their health. `deploy.yml` listens for completion
of **CI**, accepts only successful same-repository `push` runs on `main`, and checks
out the exact tested SHA. PR runs, forks, failures and superseded commits do not
deploy. The reusable `deployment-checks.yml` also tests the deployment code, lints
both new workflows and validates Terraform on PRs and before deployment. It has no
cloud credentials. The workflow must exist on the default branch before `workflow_run` fires.
Branch protection should require CI before merging; protect deployment files with
review because code on main can execute using the deployment identity.

Terraform owns APIs, registry, identities, WIF, secret containers, Cloud Run service
identities/IAM and private bootstrap services. The bootstrap image is Google's hello
container: **Terraform apply alone does not deploy this application**. No secret
versions are needed for these placeholders. After bootstrap, Terraform deliberately
ignores Cloud Run revision templates and traffic; `scripts/gcp/deploy.py` owns those.
Change runtime limits/settings in the workflow variables/script, not Terraform's
bootstrap template. Change service account prefixes in both Terraform and GitHub
variables, then redeploy. Terraform keeps deletion protection on the services.

The workflow builds the original Dockerfiles before generating WIF credentials,
pushes SHA-tagged images and deploys their immutable digests. It renders all manifests
before mutating services, then deploys in dependency order and waits for readiness.
After rollout, a verification matrix obtains audience-specific WIF ID tokens and
checks each private `/health` response for the expected service and exact commit SHA.
HTTP startup/liveness probes use `/health`. Manifests and image digests are retained
as a workflow artifact for 30 days; they contain references, never secret payloads.
The deployment is sequential, not a cross-service transaction. If one service fails,
earlier services may already have updated; use the rollback procedure below.

## 1. Initial GCP and Terraform setup (manual, after approval)

Prerequisites: a billing-enabled project you control, Google Cloud CLI, Terraform
1.6+, Docker, Python 3.12+, GitHub repository administration access and `psql`.
Use a dedicated project. The setup operator needs permission to enable services,
create Artifact Registry repositories, Cloud Run services, service accounts, WIF
pools/providers and secrets, and set their IAM policies. Typical temporary setup
roles are Service Usage Admin, Artifact Registry Admin, Cloud Run Admin, Service
Account Admin/User, Workload Identity Pool Admin, Secret Manager Admin and Project
IAM Admin. These are operator permissions, **not CI permissions**. Remove temporary
setup grants when finished; comply with your organization's IAM policies.

The APIs enabled are Cloud Run, Artifact Registry, Secret Manager, IAM, IAM
Credentials, Security Token Service, Resource Manager, SQL Admin and Cloud Logging.
Builds run on GitHub runners; Cloud Build and a VPC connector are not needed.

```bash
gcloud auth login
gcloud auth application-default login
gh api repos/Shrishagwl/4-pillars --jq '{repository_id: .id, owner_id: .owner.id}'
cd infra/gcp
cp terraform.tfvars.example terraform.tfvars
# Edit project_id, region and the two numeric GitHub IDs. No credentials go here.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=bootstrap.tfplan
# Review the plan and costs; run ONLY after approval:
terraform apply bootstrap.tfplan
terraform output github_variables
terraform output service_urls
```

Use the same region for Cloud Run, Artifact Registry and, if chosen, Cloud SQL.
Keep `.terraform.lock.hcl` under version control once generated. Terraform state,
plans and actual `.tfvars` files are ignored. Keep state private and backed up;
for team use, configure a GCS backend with versioning and restricted access before
applying. Creating that bucket is a separate approved operation. Never put secret
payloads into Terraform variables/resources or commit state.

The deployer receives Artifact Registry Writer on this repository, Cloud Run
Developer on these five services, and Service Account User on their five runtime
identities. It cannot create unrelated services, read secret payloads or change IAM.
It also receives Run Invoker on these five services for authenticated release checks.
Each runtime identity receives Secret Accessor only on its own secrets. Only the
two database services receive Cloud SQL Client if `cloud_sql_instance` is set.
The normal Google-managed Cloud Run service agent pulls same-project images.

## 2. PostgreSQL setup

Use one dedicated database with **different login roles and schemas** for ingest
and engine. Do not reuse the local Compose password or database owner credentials.
The application does not yet implement persistence: the current `/health` endpoint
does not verify database connectivity. Existing persistence work must use these
URLs and add its own migrations/readiness checks.

### Neon (default)

Create/select a Neon project and database near the Cloud Run region after approval.
Use the direct endpoint for setup and the initial hackathon runtime configuration;
role defaults avoid pooled connection startup-parameter limitations if pooling is
added later. Connect as database owner using `psql` with verified TLS. Do not paste
passwords into command lines or shell history; let `psql` prompt or use a protected
password file outside this checkout.

```bash
psql 'host=YOUR_NEON_HOST dbname=pillars user=YOUR_OWNER sslmode=verify-full sslrootcert=system' \
  -f infra/gcp/database.sql
psql 'host=YOUR_NEON_HOST dbname=pillars user=YOUR_OWNER sslmode=verify-full sslrootcert=system'
# In the interactive psql session:
\password pillars_ingest
\password pillars_engine
```

`sslrootcert=system` requires a sufficiently recent libpq. For older clients, supply
the trusted CA bundle path and `sslmode=verify-full`. Future application drivers must
verify the hostname/certificate using their trust store; never disable certificate
verification. See [Neon secure connections](https://neon.com/docs/connect/connect-securely).

Store these URL shapes in Secret Manager, with URL-encoded passwords:

```text
postgresql://pillars_ingest:ENCODED_PASSWORD@NEON_HOST/pillars?sslmode=verify-full&options=-csearch_path%3Dingest
postgresql://pillars_engine:ENCODED_PASSWORD@NEON_HOST/pillars?sslmode=verify-full&options=-csearch_path%3Dengine
```

The SQL also sets role-level `search_path` and revokes cross-schema access. It is
intended for a fresh dedicated database; it does not transfer ownership of existing
tables from another application's roles. Test each login with `SHOW search_path;`
and verify it cannot create/read objects in the other schema. Preserve the existing
Compose initialization (`db/init/01-schemas.sql`); cloud setup does not change it.

### Cloud SQL alternative (optional and billable)

After reviewing regional costs and obtaining approval, the operator can create a
small PostgreSQL instance. This example uses public IP with **no authorized networks**;
the authenticated Cloud SQL connector provides encrypted access. It does not expose
port 5432 to the internet through an allowlist.

```bash
gcloud sql instances create pillars-postgres --project=PROJECT_ID \
  --region=australia-southeast1 --database-version=POSTGRES_17 \
  --edition=ENTERPRISE --tier=db-f1-micro --availability-type=zonal \
  --storage-type=SSD --storage-size=10 --no-storage-auto-increase \
  --backup-start-time=16:00 --deletion-protection
gcloud sql databases create pillars --instance=pillars-postgres --project=PROJECT_ID
```

Set the admin password through the Cloud Console. Use Cloud SQL Auth Proxy v2
locally with your operator identity, then run the same `database.sql` and interactive
`\password` commands via the proxy. The operator needs Cloud SQL Client. Set
`cloud_sql_instance = "PROJECT_ID:australia-southeast1:pillars-postgres"` in Terraform,
review/apply its IAM changes, and set the matching `GCP_CLOUD_SQL_INSTANCE` GitHub
variable. Cloud Run mounts the authenticated connector socket only for ingest/engine.

Store driver-compatible socket URLs such as:

```text
postgresql://pillars_ingest:ENCODED_PASSWORD@/pillars?host=/cloudsql/PROJECT_ID:australia-southeast1:pillars-postgres&options=-csearch_path%3Dingest
postgresql://pillars_engine:ENCODED_PASSWORD@/pillars?host=/cloudsql/PROJECT_ID:australia-southeast1:pillars-postgres&options=-csearch_path%3Dengine
```

The local Unix socket is protected by IAM and the connector encrypts the network
connection; it does not require client-side TLS on that socket. Cloud SQL Client
authorizes the connector, while the database password authorizes the database role.
If your organization requires private IP instead, configure VPC egress separately
before deployment; this configuration does not provision a VPC connector.
See [Cloud SQL from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run).

## 3. Add Secret Manager versions (manual)

Terraform creates four empty secret containers. The current scaffold deployment
defaults `GCP_USE_APPLICATION_SECRETS=false` and mounts none: implemented routes do
not use a database or Telstra credentials. Do not add dummy passwords to satisfy
deployment. Set the flag to `true` only after real application integration exists
and valid pinned versions have been added to all referenced containers. Names are:

| Secret | Runtime variable | Reader |
|---|---|---|
| `four-pillars-ingest-database-url` | `DATABASE_URL` | ingest-api |
| `four-pillars-engine-database-url` | `DATABASE_URL` | engine |
| `four-pillars-telstra-client-id` | `TELSTRA_CLIENT_ID` | telstra-gateway |
| `four-pillars-telstra-client-secret` | `TELSTRA_CLIENT_SECRET` | telstra-gateway |

Use Secret Manager's console or upload a protected file outside the repository:

```bash
gcloud secrets versions add four-pillars-ingest-database-url \
  --project=PROJECT_ID --data-file=/secure/path/ingest-url.txt
```

Repeat for each secret. Files must contain only the value, with no trailing newline.
Do not echo credentials, enable shell tracing, or put values in GitHub variables.
In fake mode, leave unavailable Telstra credentials unconfigured and secret mounts
disabled. Real sandbox integration is still #36. The gateway points to the private
fake service by default; both currently implement only health routes.

`GCP_SECRET_VERSION` defaults to `1` and must be numeric. To rotate an individual
secret without advancing all four, update the corresponding version reference in
`scripts/gcp/deploy.py` and its test; the common variable is for coordinated versions.
Never use `latest`: previous Cloud Run revisions must retain reproducible references
for rollback. Keep old referenced versions enabled until rollback is no longer needed.

## 4. GitHub configuration and Workload Identity Federation

Create a GitHub environment named `production`, restricted to the main branch.
Required reviewers are optional: enabling them adds a human approval to every
deployment; leave them off if every successful main push should deploy automatically.

Terraform establishes trust using the immutable numeric repository and owner IDs,
`refs/heads/main`, the `workflow_run` event, the exact `deploy.yml` workflow path and
the `production` environment subject. Fork/PR tokens cannot use this identity.
The workflow requests `id-token: write`; Google exchanges that short-lived OIDC token
through `roles/iam.workloadIdentityUser`. No service-account JSON key is needed.
See [Google's deployment federation guide](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

Set repository variables (or variables on `production`) from `terraform output github_variables`:

| Variable | Requirement/default |
|---|---|
| `GCP_PROJECT_ID` | Required project ID |
| `GCP_REGION` | Required; e.g. `australia-southeast1` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Required full provider resource name from Terraform |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | Required deployer email from Terraform |
| `GCP_ARTIFACT_REPOSITORY` | `four-pillars` |
| `GCP_SERVICE_PREFIX` | `four-pillars` |
| `GCP_RUNTIME_SA_PREFIX` | `fp` |
| `GCP_SECRET_PREFIX` | `four-pillars` |
| `GCP_SECRET_VERSION` | `1`; all referenced versions must exist and be enabled |
| `GCP_USE_APPLICATION_SECRETS` | `false` for current scaffolds; opt in only with valid versions |
| `GCP_MAX_INSTANCES` | `2`, per revision; allowed range 1–100, keep low for a demo |
| `GCP_CLOUD_SQL_INSTANCE` | Empty for Neon; otherwise `PROJECT:REGION:INSTANCE` |
| `GCP_LOG_LEVEL` | `info` |

**GitHub secrets required: none.** Its built-in `GITHUB_TOKEN` reads the latest main
SHA; application secrets remain in Secret Manager. Prefixes and repository settings
must match Terraform. WIF/IAM propagation can take several minutes after bootstrap.

## 5. Networking and service authentication

All five services require Cloud Run IAM authentication. Ingress is `all` so normal
Cloud Run HTTPS URLs are reachable without a paid VPC connector; IAM rejects
unauthenticated requests. No `allUsers` grants or public access flags are configured.

| Caller | Target | Environment variable |
|---|---|---|
| ingest-api | engine | `ENGINE_URL` |
| engine | telstra-gateway | `GATEWAY_URL` |
| telstra-gateway | telstra-fake | `TELSTRA_BASE_URL` |
| twin | telstra-fake | `TELSTRA_FAKE_URL` |
| twin | ingest-api | `INGEST_URL` |

Terraform grants each caller `roles/run.invoker` only on those targets. The script
discovers actual URLs from Cloud Run before deployment; Compose hostnames are never
used in cloud manifests. `PORT=8080` is supplied by Cloud Run; all existing servers
already honor `PORT` and bind to `0.0.0.0`. `APP_VERSION` is baked into each image as
the tested commit SHA. `LOG_LEVEL` and secret references are supplied at deployment.

**Application boundary:** outbound HTTP integrations and database persistence are
largely still scaffolds in this repository; ingest currently logs callbacks and
has TODOs for persistence (#14) and Pub/Sub (#22). This change provisions identities,
URLs and permissions; it does not claim those application flows now work. When those
clients are implemented, they must obtain a Google ID token with the target service's
base URL as audience, then send `X-Serverless-Authorization: Bearer ID_TOKEN`.
Use the runtime service account via the metadata server or Google auth libraries,
cache/refresh tokens, and omit cloud authentication for local Compose HTTP URLs.
An IAM binding alone does not add that header to application requests.
See [Cloud Run service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service).

The current unauthenticated Telstra callback and dashboard browser cannot call
private ingest directly. Keep the demo private and use an authenticated proxy for
testing. Before public use, implement callback verification and browser authentication/
CORS (or an authenticated backend proxy) and deliberately approve the ingress policy.
Do not make every backend public to bypass authentication. Firebase Hosting is
unchanged; the deployment does not silently add public access or move the dashboard.

## 6. Deploy, verify and roll back

Once bootstrap, secret versions and GitHub variables are configured, merge the
reviewed feature through your normal PR process. A successful CI run for a push to
main automatically deploys all five images. Rerun CI for the current main SHA to
retry after fixing setup. Older completed runs are skipped if main has advanced.
Deployments are serialized and never canceled mid-rollout by a newer push.

For each service, inspect the ready revision and image:

```bash
gcloud run services describe four-pillars-ingest-api --project=PROJECT_ID \
  --region=australia-southeast1 \
  --format='yaml(status.conditions,status.latestReadyRevisionName,status.traffic)'
```

An operator with Run Viewer and Run Invoker on the service can use an authenticated
local proxy (the CI identity now has scoped invocation grants for release checks):

```bash
gcloud run services proxy four-pillars-ingest-api --project=PROJECT_ID \
  --region=australia-southeast1 --port=8081
# In another terminal:
curl --fail http://localhost:8081/health
```

Repeat for each service. Check `ok`, the service name and the deployed SHA in `version`.
An unauthenticated request to the direct Cloud Run URL should fail (normally 403).
Verify permitted calls with target-audience ID tokens from each caller's identity,
and verify an unrelated identity is rejected. This requires approved operator
impersonation rights or an actual authenticated client; do not grant broad token
creation privileges to CI merely to run smoke tests. Test PostgreSQL separately with
the two database roles and TLS/connector settings. A green `/health` proves process
readiness only, not end-to-end Telstra, database or Pub/Sub functionality.

For a fast per-service rollback, list revisions and route traffic to a known good one:

```bash
gcloud run revisions list --service=four-pillars-ingest-api \
  --project=PROJECT_ID --region=australia-southeast1
gcloud run services update-traffic four-pillars-ingest-api \
  --to-revisions=KNOWN_GOOD_REVISION=100 --project=PROJECT_ID --region=australia-southeast1
```

Repeat for all services changed by a failed release, using the same known-good
release's revisions. Prior revisions retain their image digests, URLs and pinned
secret versions. Coordinate with repository maintainers so a queued deployment
does not undo the rollback. Then revert/fix the offending commit through a PR;
the next main deployment directs 100% traffic to its new ready revision.

If a revision is no longer available, download a known-good `deployment-SHA` artifact,
review its manifest secret versions and service account references, then apply each
saved service JSON with `gcloud run services replace FILE --project=PROJECT_ID --region=REGION`.
This requires the referenced image digests and secret versions to still exist.

## Local validation

```bash
python -m unittest discover -s scripts/gcp/tests -v
actionlint .github/workflows/deploy.yml .github/workflows/deployment-checks.yml
terraform -chdir=infra/gcp fmt -check
terraform -chdir=infra/gcp init -backend=false
terraform -chdir=infra/gcp validate
docker compose config --quiet
npm ci
npm run lint && npm run typecheck && npm test && npm run build
docker compose build
docker compose up -d --wait --wait-timeout 120
# Check localhost ports 8081 through 8085 at /health, and dashboard port 3000.
docker compose down
```

Run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .` and
`uv run pytest` in `services/engine`, `services/twin`, `templates/fastapi-service`
and `eval`, matching existing CI. Do not remove persistent local volumes during
validation. Without Docker's daemon, cloud credentials and approved provisioning,
container builds/startup, actual OIDC/IAM, Cloud Run rollout and database connections
remain unverified. Local manifest tests do not substitute for those integrations.

## Live path setup (#14, #16, #22) - steps after `terraform apply`

`infra/gcp/data.tf` adds the smallest Cloud SQL instance (Postgres 17, `db-f1-micro`, 10 GB HDD,
zonal, no backups), the `meter-silent` topic with a push subscription to the engine (OIDC, 5
tries then the `meter-silent-dead-letter` topic), and makes ingest-api public, because Telstra's
callbacks and the dashboard can't send Google ID tokens. Writes on ingest-api other than the LoC
callback need the `ingest-admin-key` secret in `x-api-key`.

`main.tf` also fixes the deploy login: this repo's GitHub OIDC tokens use the newer immutable
subject (`repo:Shrishagwl@162850908/4-pillars@1454645919:environment:production`), which the
old condition rejected ("The given credential is rejected by the attribute condition").

Passwords never go through Terraform. After `terraform apply`, run (as a project owner):

```bash
INSTANCE=$(terraform -chdir=infra/gcp output -raw cloud_sql_connection)
gcloud sql users create pillars_ingest --instance four-pillars-db --password "$(openssl rand -base64 24)"
gcloud sql users create pillars_engine --instance four-pillars-db --password "$(openssl rand -base64 24)"
# Then add one version to each secret, typed in, never committed:
#   four-pillars-ingest-database-url: postgres://pillars_ingest:<pw>@/pillars?host=/cloudsql/$INSTANCE&options=-csearch_path%3Dingest
#   four-pillars-engine-database-url: postgresql://pillars_engine:<pw>@/pillars?host=/cloudsql/$INSTANCE&options=-csearch_path%3Dengine
#   four-pillars-ingest-admin-key:    any long random string
gcloud secrets versions add four-pillars-ingest-database-url --data-file=-
gcloud secrets versions add four-pillars-engine-database-url --data-file=-
gcloud secrets versions add four-pillars-ingest-admin-key --data-file=-
```

Then set these GitHub variables and re-run CI on main to deploy:

| Variable | Value |
|---|---|
| `GCP_CLOUD_SQL_INSTANCE` | the instance connection name (`terraform output github_variables`) |
| `GCP_PUBSUB_TOPIC` | `meter-silent` |
| `GCP_USE_APPLICATION_SECRETS` | `true` |
| `GCP_ENABLED_SECRETS` | `ingest-database-url,engine-database-url,ingest-admin-key` (add the Telstra ones once they have versions, #36) |

Each service creates its own schema and tables on start (the migrations from #14).
