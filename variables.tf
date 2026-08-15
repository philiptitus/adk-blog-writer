variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region for Cloud Run, the service account, and Secret Manager resources."
}

variable "gcs_bucket_base" {
  type        = string
  description = "Base name for the GCS bucket that holds blog drafts/images; the environment is appended (e.g. blogs-dev, blogs-prod)."
  default     = "blogs"
}

variable "image" {
  type        = string
  description = "Container image to deploy to Cloud Run. Defaults to a placeholder for the first apply, before a real image has been built and pushed."
  default     = "us-docker.pkg.dev/cloudrun/container/hello:latest"
}

variable "blog_publish_url" {
  type        = string
  description = "Full URL of the portfolio backend's agent blog-publish endpoint for this environment."
  default     = ""
}

variable "blog_token_audience" {
  type        = string
  description = "Audience string the backend expects on this environment's OIDC token."
  default     = ""
}

variable "blog_frontend_base_url" {
  type        = string
  description = "Base URL of this environment's portfolio frontend, used to build the published post's public link (e.g. https://filipio.com for prod, a dev frontend URL for dev). Falls back to https://filipio.com in code if unset."
  default     = ""
}

variable "environment" {
  type        = string
  description = "Deployment environment. Must be \"dev\" or \"prod\" — selects the Terraform workspace and scopes every resource name."

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be either \"dev\" or \"prod\"."
  }
}
