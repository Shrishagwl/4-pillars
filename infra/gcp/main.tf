locals {
  services = toset(["ingest-api", "telstra-gateway", "telstra-fake", "engine", "twin"])
  secret_owners = {
    ingest-database-url   = "ingest-api"
    engine-database-url   = "engine"
    telstra-client-id     = "telstra-gateway"
    telstra-client-secret = "telstra-gateway"
    ingest-admin-key      = "ingest-api" # also readable by twin, see below
  }
  invocations = {
    ingest-engine  = { caller = "ingest-api", target = "engine" }
    engine-gateway = { caller = "engine", target = "telstra-gateway" }
    gateway-fake   = { caller = "telstra-gateway", target = "telstra-fake" }
    twin-fake      = { caller = "twin", target = "telstra-fake" }
    twin-ingest    = { caller = "twin", target = "ingest-api" }
    engine-ingest  = { caller = "engine", target = "ingest-api" } # reads the meter list
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com",
    "iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com", "sqladmin.googleapis.com", "logging.googleapis.com",
    "pubsub.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.artifact_repository
  format        = "DOCKER"
  description   = "Four Pillars backend images; retain digests needed for rollback"
  depends_on    = [google_project_service.required]
}

resource "google_service_account" "deployer" {
  account_id   = var.deployer_account_id
  display_name = "GitHub backend deployer (no keys)"
  depends_on   = [google_project_service.required]
}

resource "google_service_account" "runtime" {
  for_each     = local.services
  account_id   = "${var.runtime_sa_prefix}-${each.value}"
  display_name = "${each.value} Cloud Run runtime"
  depends_on   = [google_project_service.required]
}

resource "google_artifact_registry_repository_iam_member" "push" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "act_as" {
  for_each           = local.services
  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_secret_manager_secret" "credentials" {
  for_each  = local.secret_owners
  secret_id = "${var.secret_prefix}-${each.key}"
  replication {
    auto {}
  }
  # Payloads are added manually, never through Terraform (including its state).
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = local.secret_owners
  secret_id = google_secret_manager_secret.credentials[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime[each.value].email}"
}

resource "google_project_iam_member" "cloud_sql_client" {
  for_each = var.create_cloud_sql || var.cloud_sql_instance != "" ? toset(["ingest-api", "engine"]) : toset([])
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

# Bootstrap only. GitHub owns revision templates and traffic after the first deploy.
# Private placeholders allow IAM to be resource-scoped before CI can deploy code.
resource "google_cloud_run_v2_service" "backend" {
  for_each            = local.services
  name                = "${var.service_prefix}-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  template {
    service_account = google_service_account.runtime[each.key].email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      ports {
        container_port = 8080
      }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = false
      }
    }
  }
  lifecycle {
    ignore_changes = [template, traffic, client, client_version]
  }
  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service_iam_member" "deploy" {
  for_each = local.services
  location = var.region
  name     = google_cloud_run_v2_service.backend[each.key].name
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_service_iam_member" "invoke" {
  for_each = local.invocations
  location = var.region
  name     = google_cloud_run_v2_service.backend[each.value.target].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime[each.value.caller].email}"
}

# The existing deployer can verify private /health after a rollout. This grants
# invocation only on these five services, not project-wide, and no secret reads.
resource "google_cloud_run_v2_service_iam_member" "deployment_health" {
  for_each = local.services
  location = var.region
  name     = google_cloud_run_v2_service.backend[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.workload_identity_pool_id
  display_name              = "Four Pillars GitHub"
  depends_on                = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
  }
  # workflow_run executes on the default branch; the workflow separately verifies
  # the successful upstream run came from a push to this repository's main.
  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_owner_id}'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.event_name == 'workflow_run'",
    "assertion.workflow_ref == '${var.github_repository}/.github/workflows/deploy.yml@refs/heads/main'",
    # GitHub now issues "immutable" subjects (repo:OWNER@OWNER_ID/REPO@REPO_ID:...) for this
    # repo; accept that form as well as the classic one, both pinned to the production env.
    join("", [
      "assertion.sub in [",
      "'repo:${var.github_repository}:environment:production', ",
      "'repo:${local.github_owner}@${var.github_owner_id}/${local.github_repo}@${var.github_repository_id}:environment:production'",
      "]",
    ]),
  ])
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "federation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}
