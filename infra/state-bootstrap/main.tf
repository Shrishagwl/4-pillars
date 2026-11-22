# Separate root: run only after approval. Never destroy this bucket to clean up an app.
terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = "pillars-514405"
  region  = "australia-southeast2"
}

variable "state_operator" {
  description = "Human operator allowed to read/write/lock state; never the application deployer."
  type        = string
  default     = "user:anubhav.patra.06@gmail.com"
}

resource "google_storage_bucket" "terraform_state" {
  name                        = "pillars-514405-terraform-state"
  project                     = "pillars-514405"
  location                    = "australia-southeast2"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "state_operator" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectAdmin"
  member = var.state_operator
}
