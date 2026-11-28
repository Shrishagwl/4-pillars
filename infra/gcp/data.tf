# Cloud SQL and Pub/Sub for the live path (#14, #22). Smallest options everywhere.
#
# No passwords here: the two database users and their DATABASE_URL secret versions are added
# by hand (see docs/gcp-deployment.md), so no secret ever lands in Terraform state.

locals {
  # The instance we created, or the one passed in.
  cloud_sql_connection = var.create_cloud_sql ? google_sql_database_instance.main[0].connection_name : var.cloud_sql_instance
  github_owner         = split("/", var.github_repository)[0]
  github_repo          = split("/", var.github_repository)[1]
}

resource "google_sql_database_instance" "main" {
  count               = var.create_cloud_sql ? 1 : 0
  name                = "${var.service_prefix}-db"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = true
  settings {
    edition           = "ENTERPRISE"
    tier              = var.cloud_sql_tier # shared-core, the cheapest tier
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false
    backup_configuration {
      enabled = false # demo data only; turn on for anything real
    }
    ip_configuration {
      # Public IP with no authorised networks: only the Cloud SQL connector (IAM) gets in.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_sql_database" "pillars" {
  count    = var.create_cloud_sql ? 1 : 0
  name     = "pillars"
  instance = google_sql_database_instance.main[0].name
}

# ingest-api publishes each stored LoC event here; Pub/Sub pushes it to the engine.
resource "google_pubsub_topic" "meter_silent" {
  name                       = "meter-silent"
  message_retention_duration = "86400s"
  depends_on                 = [google_project_service.required]
}

# Messages the engine can't read end up here after 5 tries instead of retrying forever.
resource "google_pubsub_topic" "meter_silent_dead_letter" {
  name       = "meter-silent-dead-letter"
  depends_on = [google_project_service.required]
}

resource "google_service_account" "pubsub_push" {
  account_id   = "${var.runtime_sa_prefix}-pubsub-push"
  display_name = "Pub/Sub push to the engine"
  depends_on   = [google_project_service.required]
}

resource "google_pubsub_subscription" "meter_silent_engine" {
  name                       = "meter-silent-engine"
  topic                      = google_pubsub_topic.meter_silent.id
  ack_deadline_seconds       = 30
  message_retention_duration = "86400s"
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.backend["engine"].uri}/pubsub/push"
    oidc_token {
      service_account_email = google_service_account.pubsub_push.email
      audience              = google_cloud_run_v2_service.backend["engine"].uri
    }
  }
  retry_policy {
    minimum_backoff = "5s"
    maximum_backoff = "300s"
  }
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.meter_silent_dead_letter.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_topic_iam_member" "ingest_publishes" {
  topic  = google_pubsub_topic.meter_silent.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.runtime["ingest-api"].email}"
}

resource "google_cloud_run_v2_service_iam_member" "push_invokes_engine" {
  location = var.region
  name     = google_cloud_run_v2_service.backend["engine"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

# Pub/Sub's own service agent needs these to move undeliverable messages to the dead-letter topic.
data "google_project" "this" {
  project_id = var.project_id
}

locals {
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "agent_dead_letters" {
  topic  = google_pubsub_topic.meter_silent_dead_letter.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_acks" {
  subscription = google_pubsub_subscription.meter_silent_engine.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

# Telstra's callbacks and the dashboard can't send Google ID tokens, so ingest-api has to be
# reachable from the internet. Its write routes other than the callback check an API key.
resource "google_cloud_run_v2_service_iam_member" "ingest_public" {
  count    = var.ingest_public ? 1 : 0
  location = var.region
  name     = google_cloud_run_v2_service.backend["ingest-api"].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# The twin registers meters and starts scenarios on ingest-api, so it needs ingest's API key.
resource "google_secret_manager_secret_iam_member" "twin_reads_ingest_key" {
  secret_id = google_secret_manager_secret.credentials["ingest-admin-key"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["twin"].email}"
}
