# Resources genuinely shared across the dev and prod environments live here,
# in a separate, non-workspaced Terraform root with its own state — kept out
# of the per-environment workspace so destroying one environment can never
# take out infrastructure the other environment depends on.

resource "google_project_service" "artifact_registry_api" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "blogger_agent" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"

  depends_on = [google_project_service.artifact_registry_api]
}
