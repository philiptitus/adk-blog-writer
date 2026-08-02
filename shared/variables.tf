variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region for the Artifact Registry repository."
}

variable "artifact_repo" {
  type        = string
  description = "Artifact Registry repository ID, shared across dev and prod."
  default     = "blogger-agent"
}
