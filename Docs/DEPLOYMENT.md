# Deploying to Cloud Run

Infrastructure is managed with Terraform, mirroring the structure of the `PortfolioV2/Assistant` template: a single workspace-driven root config for per-environment resources (`dev`/`prod`), plus a separate `shared/` root for the one resource genuinely shared across environments (the Artifact Registry repo).

## Layout

- `main.tf`, `variables.tf`, `providers.tf`, `dev.tfvars`, `prod.tfvars`, `terraform.tfvars` — per-environment resources (GCS bucket, service account, Cloud Run service), selected via `terraform workspace select dev|prod`.
- `shared/` — a separate, non-workspaced Terraform root holding only the Artifact Registry repository. Applied once, manually, before the first real deploy — kept separate so destroying one environment's workspace can never take out infrastructure the other environment depends on.
- `Dockerfile` — single-stage, `uv`-based build, serves the agent via `adk web`.
- `.github/workflows/workflow.yaml` — PR validation without deployment credentials; plan/apply + build/deploy on trusted pushes to `main` (prod) or `develop` (dev).
- `.github/workflows/destroy.yaml` — manual, environment-scoped teardown with a typed confirmation.
- `.github/workflows/apply-shared.yaml` — manual, one-off: applies `shared/`.

## Config / Secrets

| Env var | Source | Purpose |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | GitHub Actions deploy workflow | Vertex AI project |
| `GOOGLE_GENAI_USE_VERTEXAI` | GitHub Actions deploy workflow | Use Vertex backend for Gemini |
| `BLOGGER_GCS_BUCKET` | GitHub Actions deploy workflow | Selects the provisioned bucket for the environment |
| `BLOG_PUBLISH_URL` | Terraform environment variables, applied by GitHub Actions | Portfolio backend publish endpoint |
| `BLOG_TOKEN_AUDIENCE` | Terraform environment variables, applied by GitHub Actions | OIDC audience expected by the portfolio backend |
| `BLOG_FRONTEND_BASE_URL` | Terraform environment variables, applied by GitHub Actions | Base URL used to construct the published post link |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub Actions environment secret, copied to Cloud Run during deploy | GitHub MCP server auth (optional — degrades softly if missing) |
| `SERPAPI_API_KEY` | GitHub Actions environment secret, copied to Cloud Run during deploy | SerpApi image search (optional — degrades softly if missing) |

Before deploying, create GitHub Actions environments named `dev` and `prod`. Add `BLOGGER_GITHUB_PAT` and `SERPAPI_API_KEY` as secrets in each environment; `BLOGGER_GITHUB_PAT` is passed to the app as `GITHUB_PERSONAL_ACCESS_TOKEN`. Use the corresponding runtime keys for each environment. Keep `GOOGLE_CREDENTIALS` in its existing GitHub repository-secret location; the workflows continue using that same secret for Google Cloud deployment authentication. Configure `dev` to allow deployments from `develop` and `main` (the destroy workflow runs from `main`); configure `prod` to allow deployments from `main`. Require reviewer approval for `prod` where the repository's GitHub plan supports it. Protect both branches against unreviewed changes, especially changes to workflow files.

The pull-request job only runs Terraform formatting and validation with the backend disabled; it does not receive deployment credentials. The deploy job runs only for pushes to `main` or `develop`, and GitHub's environment gate controls when it can access the environment secrets. The manual shared-infrastructure and destroy workflows also use these protected environments and must be dispatched from `main`.

**Security trade-off:** GitHub Actions does not provide secrets directly to a running Cloud Run service. This workflow copies the values into ordinary Cloud Run environment variables, so they are not stored in Terraform state or intentionally printed in workflow logs, but they are visible to principals with permission to inspect Cloud Run service/revision configuration. Restrict Cloud Run read/update IAM permissions accordingly. This does not provide the same runtime secret isolation as Secret Manager. The Cloud Run service is publicly invokable, but callers cannot read its environment variables merely by invoking it. The deployment workflow also still uses the `GOOGLE_CREDENTIALS` service-account key; limit that identity to deployment permissions and consider replacing the key with GitHub OIDC/Workload Identity Federation.

Terraform ignores changes to Cloud Run container environment variables to avoid managing the runtime API keys in Terraform state. The deployment workflow incrementally updates the Cloud Run environment, including the public publishing configuration read from Terraform outputs, without replacing other variables. To change publishing URLs/audience, update the appropriate `dev.tfvars` or `prod.tfvars`; the next deployment will apply those values.

**Migration from Secret Manager:** Add the existing values to the matching GitHub environment secrets before deploying this change. The workflow first replaces any legacy Secret Manager-backed Cloud Run environment variables with the GitHub-provided values, then runs Terraform, so the revision no longer requires Secret Manager accessor permission. New services skip this one-time migration and receive their environment after Terraform creates them. The next Terraform apply removes the Terraform-managed Secret Manager containers and access grants. After migration, rotate the credentials if the old values may have been exposed. Old Cloud Run revisions can retain their prior environment-variable values, so restrict revision inspection and remove old revisions when they are no longer needed.

## Deploying

Push to `develop` for a dev deploy, `main` for prod — CI validates pull requests without deployment credentials, then handles legacy-secret migration → plan → apply (baseline) → configure Cloud Run environment → build/push image → apply (deploy image) on trusted pushes. The environment is configured before the new image is deployed so the application revision starts with its required configuration. Before the very first deploy ever, run the **"One-off: Apply shared Artifact Registry"** workflow manually once.

## Destroying

Run the **"Terraform Destroy"** workflow manually — pick `dev` or `prod` from the dropdown, then type the environment name again to confirm.

## Deferred: Session Storage

ADK's default in-memory session store does not survive Cloud Run's ephemeral, multi-instance filesystem — sessions can be lost on restart or when a request lands on a different instance. This is a known, explicitly deferred limitation for now (kept out of this migration to control scope and cost) — revisit with a dedicated `SessionService` backend (`DatabaseSessionService` + Cloud SQL, or `VertexAiSessionService`) before relying on this for production multi-turn conversations at scale.
