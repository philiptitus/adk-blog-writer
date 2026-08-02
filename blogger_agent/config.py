# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from dataclasses import dataclass

import google.auth

# To use AI Studio credentials:
# 1. Create a .env file in the /app directory with:
#    GOOGLE_GENAI_USE_VERTEXAI=FALSE
#    GOOGLE_API_KEY=PASTE_YOUR_ACTUAL_API_KEY_HERE
# 2. This will override the default Vertex AI configuration
_, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


@dataclass
class ResearchConfiguration:
    """Configuration for research-related models and parameters.

    Attributes:
        critic_model (str): Model for evaluation tasks.
        worker_model (str): Model for working/generation tasks.
        max_search_iterations (int): Maximum search iterations allowed.
    """

    critic_model: str = "gemini-2.5-pro"
    worker_model: str = "gemini-2.5-flash"
    image_model: str = "gemini-2.5-flash-image"
    max_search_iterations: int = 5


config = ResearchConfiguration()


# --- Blog length settings ---
# Edit these numbers to change how many words each length option targets.
# "medium" is used automatically whenever the user doesn't specify a length.
BLOG_LENGTH_WORD_LIMITS: dict[str, int] = {
    "short": 600,
    "medium": 1200,
    "long": 2000,
}
DEFAULT_BLOG_LENGTH: str = "medium"


# --- Storage settings ---
# Default GCS bucket used for saving blog posts and images. Edit this to
# point at a different bucket; the agent will use it automatically without
# asking, unless the user explicitly requests a different bucket.
DEFAULT_GCS_BUCKET: str = "blogs-dev"

# Path (object prefix) within the bucket where finished blog posts are saved.
# Edit this to change where posts land; the agent never asks the user for a
# path, it always saves under this prefix.
DEFAULT_BLOG_DRAFTS_PATH: str = "drafts"


# --- GitHub MCP settings ---
# Remote GitHub MCP server used for codebase-aware blog posts. Requires a
# GITHUB_PERSONAL_ACCESS_TOKEN env var (a public-repo-read-only token is
# enough). See https://github.com/github/github-mcp-server for details.
GITHUB_MCP_SERVER_URL: str = "https://api.githubcopilot.com/mcp/"


# --- Public image search settings (SerpApi, Google Images engine) ---
# Used to find existing public images (e.g. "Nike logo") instead of
# generating one. Requires a SERPAPI_API_KEY env var — free tier (250
# searches/month, no card required) at https://serpapi.com/.
IMAGE_SEARCH_RESULT_COUNT: int = 3
# SerpApi's "safe" param: "active" or "off".
IMAGE_SEARCH_SAFESEARCH: str = "active"


# --- Blog image sizing ---
# Every image (generated or mirrored from a search result) is downscaled to
# this max width before upload, preserving aspect ratio — markdown has no
# way to express a display width itself, so this is done to the file.
# Edit this number to change the default width for all blog images.
MAX_IMAGE_WIDTH_PX: int = 1200
