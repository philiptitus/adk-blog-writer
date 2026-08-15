# Integration Plan: Publishing to the Portfolio Website

## Context

This agent (`blogger-agent`, Cloud Run, dev/prod via Terraform in this repo) currently ends its workflow by calling `save_blog_post_to_gcs`, which writes the finished Markdown post to a private-ish `drafts/` path in the `blogs-{env}` GCS bucket. Nothing reads that bucket back out — it's a dead end. The goal is to add a second, real publish path: a new tool the agent calls to actually put the post live on the portfolio website's blog (`filipio.com/blog/...`), backed by the Django backend in the sibling `PortfolioV2/server` repo.

That backend repo already has a purpose-built endpoint for exactly this (`POST /api/agent/blogs/`), authenticated via Google-signed OIDC identity tokens rather than a shared secret — no API key to leak or rotate, and dev/prod are cryptographically isolated from each other (a token minted by this agent's dev service account is rejected by prod, and vice versa). That endpoint is done and deployed; this plan covers only what needs to change **in this repo** to call it, plus the small amount of two-way coordination needed (this repo needs the backend's URL; the backend repo needs this agent's service account email).

## The compatibility gaps to close

Three things about this agent's current output don't match what the backend endpoint expects, and all three need to be handled in the new publish tool rather than by changing how the agent writes posts:

1. **Format mismatch**: this agent produces raw Markdown (`blog_post` state key, a plain string). The backend's `body` field is rendered as raw HTML on the frontend (`dangerouslySetInnerHTML`) — sending Markdown straight through would show literal `##` and `**` characters on the live site instead of formatted text. **The publish tool must convert Markdown → HTML before sending.**
2. **Schema mismatch**: this agent has never had a structured output — no title/category/description fields exist anywhere in the codebase today, only one opaque Markdown blob. The backend needs `name`, `description`, `body`, `category` as separate fields. **The publish tool's parameters force the LLM to supply these explicitly as tool-call arguments**, rather than trying to parse them back out of the Markdown after the fact.
3. **Category is a closed set**: the backend's `Blog.category` is a Django `choices` field — anything else gets rejected with a 400. The tool's docstring must spell out the exact allowed values so the LLM picks one that will actually validate.

## Required changes in this repo

### 1. New tool: `publish_blog_post` in `blogger_agent/tools.py`

```python
import os
import markdown as md

import google.auth.transport.requests
import google.oauth2.id_token

_BLOG_CATEGORIES = (
    "DATA SCIENCE.AI AND ML",
    "WEB DEVELOPMENT",
    "MOBILE DEVELOPMENT",
    "CYBERSECURITY",
    "CLOUD COMPUTING",
    "GAME DEVELOPMENT",
    "OTHER",
)


def publish_blog_post(
    title: str,
    description: str,
    body_markdown: str,
    category: str,
    image_url: str = "",
    png_url: str = "",
    author: str = "AI Agent",
) -> dict:
    """Publishes a finished blog post live on the portfolio website.

    Only call this after the user has approved the final edited post — it
    makes the post publicly visible immediately. Use save_blog_post_to_gcs
    instead if the user just wants a draft saved, not published.

    Args:
        title: The post's title/headline.
        description: A one-to-two sentence summary shown as a preview.
            Keep it under 500 characters — longer text is truncated.
        body_markdown: The full post body in Markdown, same content you'd
            pass to save_blog_post_to_gcs. This function converts it to
            HTML before sending, since the website renders it as raw HTML,
            not Markdown.
        category: Must be exactly one of: "DATA SCIENCE.AI AND ML",
            "WEB DEVELOPMENT", "MOBILE DEVELOPMENT", "CYBERSECURITY",
            "CLOUD COMPUTING", "GAME DEVELOPMENT", "OTHER". Any other value
            is rejected by the website.
        image_url: Public URL of the featured/cover image, if one was
            generated or found for this post (e.g. via generate_blog_image
            or search_public_images). Leave empty if there isn't one.
        png_url: Public URL of a secondary supplementary image, if any.
        author: Byline shown on the post. Defaults to "AI Agent".

    Returns:
        dict with "status" ("success" or "error"). On success, also
        includes "slug" and "url" for the live post.
    """
    publish_url = os.environ.get("BLOG_PUBLISH_URL")
    audience = os.environ.get("BLOG_TOKEN_AUDIENCE")
    if not publish_url or not audience:
        return {
            "status": "error",
            "message": "BLOG_PUBLISH_URL/BLOG_TOKEN_AUDIENCE are not configured on this deployment.",
        }
    if category not in _BLOG_CATEGORIES:
        return {
            "status": "error",
            "message": f"category must be one of {_BLOG_CATEGORIES}, got {category!r}.",
        }

    auth_req = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(auth_req, audience)

    body_html = md.markdown(body_markdown, extensions=["fenced_code", "tables"])

    resp = requests.post(
        publish_url,
        json={
            "name": title,
            "description": description[:500],
            "body": body_html,
            "category": category,
            "image_url": image_url,
            "png_url": png_url,
            "author": author,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if resp.status_code == 201:
        data = resp.json()
        slug = data.get("slug", "")
        return {"status": "success", "slug": slug, "url": f"https://filipio.com/blog/{slug}"}
    return {"status": "error", "message": f"{resp.status_code}: {resp.text}"}
```

Notes on why it's shaped this way:
- `google.auth`/`google.oauth2.id_token` need **no credentials file and no new IAM role** — on Cloud Run, `fetch_id_token` pulls the runtime service account's identity straight from the metadata server automatically. Nothing else in this repo's Terraform needs to change for auth to work.
- Mirrors the existing `save_blog_post_to_gcs` signature style (plain function, typed args, dict return, `FunctionTool`-friendly docstring) rather than introducing a new pattern.
- Fails closed and cheaply: missing env vars or a bad category are caught before any network call.

### 2. Register the tool and update agent instructions (`blogger_agent/agent.py`)

Add `FunctionTool(publish_blog_post)` to `interactive_blogger_agent`'s tool list, alongside the existing `FunctionTool(save_blog_post_to_gcs)`. Update the root agent's instruction text so the "Export" step of the conversation flow offers **two** distinct choices instead of one — currently it only ever asks to save to GCS:

> - "Save a draft" → `save_blog_post_to_gcs` (existing behavior, unchanged)
> - "Publish it live" → `publish_blog_post` — and before calling it, the agent must ask the user (or infer from context) for a `category` from the fixed list, since the post has no category today.

### 3. New dependency

Add to `pyproject.toml`:
```
"markdown>=3.7",
```
`google-auth` is already present as a **transitive** dependency (pulled in by `google-adk`/`google-cloud-*`), but since the new tool imports `google.auth`/`google.oauth2.id_token` directly, add it explicitly too so it doesn't silently disappear if the dependency graph changes later:
```
"google-auth>=2.35.0",
```
Then `uv lock` to refresh `uv.lock`.

### 4. Terraform: two new plain env vars

These aren't secrets (they're the backend's own public-ish URL/audience string, not this agent's identity), so — unlike the backend repo's agent-SA-email variables, which the user deliberately kept out of git — these are fine directly in this repo's tfvars.

`variables.tf`:
```hcl
variable "blog_publish_url" {
  type        = string
  description = "Full URL of the portfolio backend's agent blog-publish endpoint for this environment"
  default     = ""
}

variable "blog_token_audience" {
  type        = string
  description = "Audience string the backend expects on this environment's OIDC token"
  default     = ""
}
```

`main.tf`, inside the Cloud Run service's container block, alongside the existing plain env vars:
```hcl
env {
  name  = "BLOG_PUBLISH_URL"
  value = var.blog_publish_url
}
env {
  name  = "BLOG_TOKEN_AUDIENCE"
  value = var.blog_token_audience
}
```

`dev.tfvars`:
```hcl
blog_publish_url    = "https://portfolio-dev-yfdoo3vmfq-ew.a.run.app/api/agent/blogs/"
blog_token_audience = "portfolio-backend-agent-dev"
```

`prod.tfvars`:
```hcl
blog_publish_url    = "https://portfolio-yfdoo3vmfq-ew.a.run.app/api/agent/blogs/"
blog_token_audience = "portfolio-backend-agent-prod"
```

Use the backend's default `*.run.app` URL, **not** its custom domain (`pservice.mrphilip.cv`) — that domain's DNS isn't reliably resolvable for server-to-server calls from within Cloud Run's own network (this exact failure already happened once going the other direction, frontend → backend, and was fixed the same way).

## Coordination step with the `server` repo (the other half of this integration)

This agent's Cloud Run service account emails are already fully determined by this repo's own Terraform naming convention — no need to look them up:
- dev: `blogger-agent-sa-dev@fiona-464509.iam.gserviceaccount.com`
- prod: `blogger-agent-sa-prod@fiona-464509.iam.gserviceaccount.com`

In the `portfolioV3server` GitHub repo, under **Settings → Secrets and variables → Actions → Variables**, set:
| Variable | Value |
|---|---|
| `AGENT_SERVICE_ACCOUNT_EMAIL_DEV` | `blogger-agent-sa-dev@fiona-464509.iam.gserviceaccount.com` |
| `AGENT_SERVICE_ACCOUNT_EMAIL_PROD` | `blogger-agent-sa-prod@fiona-464509.iam.gserviceaccount.com` |
| `AGENT_TOKEN_AUDIENCE_DEV` | `portfolio-backend-agent-dev` |
| `AGENT_TOKEN_AUDIENCE_PROD` | `portfolio-backend-agent-prod` |

The audience strings must match **exactly** between the two repos (this repo's `blog_token_audience` tfvars values above, and the backend's `AGENT_TOKEN_AUDIENCE_*` variables) — they're arbitrary strings, but both sides have to agree on the same one per environment or every token gets rejected on audience mismatch. Until the backend repo's variables are set, the endpoint fails closed (rejects everything) rather than failing open, so there's no ordering risk either direction.

## Testing

1. Deploy this repo's `develop` branch first (dev env) with the new tool + tfvars wired in.
2. Set the four GitHub Actions variables in the backend repo, then push a no-op commit to `portfolioV3server`'s `develop` to pick them up (or just wait for the next real push).
3. From the deployed agent (via ADK web UI or a test conversation), walk through the full flow to a finished post, then trigger `publish_blog_post` with a `category` value.
4. Confirm: `200`/`201` response with a `slug`, the post appears at `https://portfolio-dev-yfdoo3vmfq-ew.a.run.app/api/blogs/<slug>/`, and the body renders as formatted HTML (not literal Markdown) on the frontend-dev site.
5. Confirm isolation: manually fetch a token for the **prod** audience from the **dev** agent's SA (or vice versa) and confirm the backend returns `401` — proves the environment boundary actually holds before trusting it in prod.
6. Repeat against `main`/prod once dev is verified.

## Open questions worth deciding before rollout (not blocking the implementation above)

- **Autonomy vs. review**: right now, whatever the agent publishes goes live immediately (`is_active` defaults to `True` on the backend). If bad/hallucinated content publishing itself is a concern, the tool could pass `"is_active": false` and require a manual flip to live in Django admin — this is a one-line change to the JSON payload above whenever you want it, not a structural change.
- **Session persistence**: `Docs/DEPLOYMENT.md` already flags that ADK's in-memory session store won't survive Cloud Run's ephemeral/multi-instance environment. If a publish conversation spans multiple turns and the instance recycles mid-flow, the agent could lose its place before reaching the publish step. Not new to this change, but worth keeping in mind if publish failures correlate with long conversations.
