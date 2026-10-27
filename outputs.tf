output "blog_publish_url" {
  description = "Portfolio backend publish endpoint for this environment."
  value       = var.blog_publish_url
}

output "blog_token_audience" {
  description = "OIDC audience expected by the portfolio backend for this environment."
  value       = var.blog_token_audience
}

output "blog_frontend_base_url" {
  description = "Portfolio frontend base URL for this environment."
  value       = var.blog_frontend_base_url
}
