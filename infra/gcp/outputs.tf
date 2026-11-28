output "github_variables" {
  description = "Set these non-secret repository/environment variables in GitHub."
  value = {
    GCP_PROJECT_ID                 = var.project_id
    GCP_REGION                     = var.region
    GCP_ARTIFACT_REPOSITORY        = var.artifact_repository
    GCP_WORKLOAD_IDENTITY_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOY_SERVICE_ACCOUNT     = google_service_account.deployer.email
    GCP_SERVICE_PREFIX             = var.service_prefix
    GCP_RUNTIME_SA_PREFIX          = var.runtime_sa_prefix
    GCP_SECRET_PREFIX              = var.secret_prefix
    GCP_CLOUD_SQL_INSTANCE         = local.cloud_sql_connection
    GCP_PUBSUB_TOPIC               = google_pubsub_topic.meter_silent.name
  }
}

output "service_urls" {
  value = { for name, service in google_cloud_run_v2_service.backend : name => service.uri }
}

output "secret_names" {
  value = { for name, secret in google_secret_manager_secret.credentials : name => secret.secret_id }
}

output "cloud_sql_connection" {
  value = local.cloud_sql_connection
}
