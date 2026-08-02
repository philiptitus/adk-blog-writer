FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY blogger_agent/ ./blogger_agent/

ENV PORT=8080
EXPOSE 8080

# Run from /app (the parent of blogger_agent/) with no explicit agents-dir
# argument, matching how `uv run adk web` already discovers `blogger_agent`
# locally by scanning the current directory for an agent.py exposing
# root_agent. Verify this against the actual container logs on first deploy
# to dev — this is the one invocation detail not verified locally (network
# issue prevented a local `adk api_server --help` check).
CMD ["sh", "-c", "uv run adk api_server --host 0.0.0.0 --port ${PORT:-8080}"]
