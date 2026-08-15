# Deploying to Cloud Run

Infrastructure is managed with Terraform, mirroring the structure of the `PortfolioV2/Assistant` template: a single workspace-driven root config for per-environment resources (`dev`/`prod`), plus a separate `shared/` root for the one resource genuinely shared across environments (the Artifact Registry repo).

## Layout

- `main.tf`, `variables.tf`, `providers.tf`, `dev.tfvars`, `prod.tfvars`, `terraform.tfvars` — per-environment resources (GCS bucket, service account, Secret Manager containers, Cloud Run service), selected via `terraform workspace select dev|prod`.
- `shared/` — a separate, non-workspaced Terraform root holding only the Artifact Registry repository. Applied once, manually, before the first real deploy — kept separate so destroying one environment's workspace can never take out infrastructure the other environment depends on.
- `Dockerfile` — single-stage, `uv`-based build, serves the agent via `adk api_server`.
- `.github/workflows/workflow.yaml` — main CI/CD: plan on every push/PR, apply + build + deploy on push to `main` (prod) or `develop` (dev).
- `.github/workflows/destroy.yaml` — manual, environment-scoped teardown with a typed confirmation.
- `.github/workflows/apply-shared.yaml` — manual, one-off: applies `shared/`.

## Config / Secrets

| Env var | Source | Purpose |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Terraform (plain env var) | Vertex AI project |
| `GOOGLE_GENAI_USE_VERTEXAI` | Terraform (plain env var) | Use Vertex backend for Gemini |
| `BLOGGER_GCS_BUCKET` | Terraform (plain env var, from the provisioned bucket) | Overrides the default `blogs-dev` bucket per environment |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Cloud Run native Secret Manager mount (`secret_key_ref`) | GitHub MCP server auth (optional — degrades softly if missing) |
| `SERPAPI_API_KEY` | Cloud Run native Secret Manager mount (`secret_key_ref`) | SerpApi image search (optional — degrades softly if missing) |

Secrets are Terraform-created as **empty containers only** (`google_secret_manager_secret`, no version) — values are added manually, once per environment:

```bash
gcloud secrets versions add github-personal-access-token-dev --data-file=- <<< "$GITHUB_PAT"
gcloud secrets versions add serpapi-api-key-dev --data-file=- <<< "$SERPAPI_KEY"
# repeat with -prod suffix for prod
```

**Bootstrapping order matters on a brand-new environment**: Cloud Run's native secret mounting means a revision referencing a secret with zero versions will fail to deploy. On the very first apply for a new environment, apply everything except the Cloud Run service first (`-target=...`), populate the secrets, then run a full apply.

## Deploying

Push to `develop` for a dev deploy, `main` for prod — CI handles plan → apply (baseline) → build/push image → apply (deploy image) automatically. Before the very first deploy ever, run the **"One-off: Apply shared Artifact Registry"** workflow manually once.

## Destroying

Run the **"Terraform Destroy"** workflow manually — pick `dev` or `prod` from the dropdown, then type the environment name again to confirm.

## Deferred: Session Storage

ADK's default in-memory session store does not survive Cloud Run's ephemeral, multi-instance filesystem — sessions can be lost on restart or when a request lands on a different instance. This is a known, explicitly deferred limitation for now (kept out of this migration to control scope and cost) — revisit with a dedicated `SessionService` backend (`DatabaseSessionService` + Cloud SQL, or `VertexAiSessionService`) before relying on this for production multi-turn conversations at scale.
