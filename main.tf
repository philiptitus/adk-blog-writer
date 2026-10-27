# Per-environment resources, driven by `terraform workspace select dev|prod`.
# Every environment-scoped resource name is built here in one place.
locals {
  app_name = "blogger-agent"

  gcs_bucket_name        = "${var.gcs_bucket_base}-${var.environment}"
  cloud_run_service_name = "${local.app_name}-${var.environment}"
  service_account_id     = "${local.app_name}-sa-${var.environment}"
}

resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Bucket for blog post drafts and generated/mirrored images. Publicly
# readable so images embedded in published posts always render. Location
# and UBLA/public-access settings match blogs-dev's existing configuration
# so the dev workspace can `terraform import` it without a forced replace.
resource "google_storage_bucket" "blog_posts" {
  name          = local.gcs_bucket_name
  project       = var.project_id
  location      = "US"
  force_destroy = true

  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
}

resource "google_storage_bucket_iam_member" "blog_posts_public_read" {
  bucket = google_storage_bucket.blog_posts.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_service_account" "app_sa" {
  project      = var.project_id
  account_id   = local.service_account_id
  display_name = "blogger-agent runtime SA (${var.environment})"
}

resource "google_storage_bucket_iam_member" "app_sa_storage" {
  bucket = google_storage_bucket.blog_posts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_cloud_run_v2_service" "app" {
  name                = local.cloud_run_service_name
  project             = var.project_id
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.app_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }

    }
  }

  # GitHub Actions owns all container environment variables, including runtime
  # secrets. Keeping them out of Terraform avoids storing their values in state.
  lifecycle {
    ignore_changes = [template[0].containers[0].env]
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_cloud_run_v2_service_iam_member" "app_public" {
  project  = var.project_id
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
