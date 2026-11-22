variable "project_id" {
  description = "Existing, billing-enabled GCP project. This configuration does not create projects."
  type        = string
}

variable "region" {
  type    = string
  default = "australia-southeast1"
}

variable "github_repository" {
  type    = string
  default = "Shrishagwl/4-pillars"
}

variable "github_repository_id" {
  description = "Numeric GitHub repository ID; protects against name reuse."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "Use the numeric repository ID from the GitHub API."
  }
}

variable "github_owner_id" {
  description = "Numeric repository owner ID; protects against organization/user name reuse."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "Use the numeric owner ID from the GitHub API."
  }
}

variable "artifact_repository" {
  type    = string
  default = "four-pillars"
}

variable "service_prefix" {
  type    = string
  default = "four-pillars"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,32}$", var.service_prefix))
    error_message = "Use a lowercase name prefix of at most 33 characters."
  }
}

variable "runtime_sa_prefix" {
  type    = string
  default = "fp"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,13}$", var.runtime_sa_prefix))
    error_message = "Use a lowercase service account prefix of at most 14 characters."
  }
}

variable "secret_prefix" {
  type    = string
  default = "four-pillars"
}

variable "deployer_account_id" {
  type    = string
  default = "four-pillars-deployer"
}

variable "workload_identity_pool_id" {
  type    = string
  default = "four-pillars-github"
}

variable "cloud_sql_instance" {
  description = "Optional existing same-project PROJECT:REGION:INSTANCE; empty selects Neon. No SQL instance is created."
  type        = string
  default     = ""
}
