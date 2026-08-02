terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    bucket = "myzer-state"
    prefix = "blogger-agent/shared/terraform/state"
  }
}


provider "google" {
  project = var.project_id
  region  = var.region
}
