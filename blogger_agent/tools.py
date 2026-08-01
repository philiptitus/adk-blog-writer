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
from urllib.parse import urlparse

import requests
from google import genai
from google.adk.tools import ToolContext
from google.cloud import storage

from .config import (
    BLOG_LENGTH_WORD_LIMITS,
    DEFAULT_BLOG_DRAFTS_PATH,
    DEFAULT_GCS_BUCKET,
    IMAGE_SEARCH_RESULT_COUNT,
    IMAGE_SEARCH_RIGHTS_FILTER,
    config,
)

_MAX_IMAGE_DOWNLOAD_BYTES = 15_000_000  # 15 MB safety cap for mirrored images


def set_blog_length(length: str, tool_context: ToolContext) -> dict:
    """Records the desired blog post length for this session.

    Args:
        length: One of "short", "medium", or "long".
    """
    length = length.lower().strip()
    if length not in BLOG_LENGTH_WORD_LIMITS:
        return {
            "status": "error",
            "error_message": (
                f"Unknown length '{length}'. Choose one of: "
                f"{', '.join(BLOG_LENGTH_WORD_LIMITS)}."
            ),
        }
    tool_context.state["blog_length"] = length
    tool_context.state["blog_word_limit"] = BLOG_LENGTH_WORD_LIMITS[length]
    return {
        "status": "success",
        "blog_length": length,
        "word_limit": BLOG_LENGTH_WORD_LIMITS[length],
    }


def save_blog_post_to_gcs(
    blog_post: str, filename: str, bucket_name: str = DEFAULT_GCS_BUCKET
) -> dict:
    """Saves the blog post to a file in a Google Cloud Storage bucket.

    The post is always stored under the configured drafts path — do not
    include any directory in `filename`, just the file's base name.

    Args:
        blog_post: The blog post content to save.
        filename: The file's base name, e.g. "my-post.md" (no path).
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix). Defaults to the configured bucket; only pass
            this if the user explicitly asks for a different bucket.
    """
    object_name = f"{DEFAULT_BLOG_DRAFTS_PATH.strip('/')}/{filename.lstrip('/')}"
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(blog_post, content_type="text/markdown")
    return {"status": "success", "gcs_uri": f"gs://{bucket_name}/{object_name}"}


def generate_blog_image(
    prompt: str,
    destination_filename: str,
    bucket_name: str = DEFAULT_GCS_BUCKET,
) -> dict:
    """Generates an image with Gemini's image model and uploads it to GCS.

    Args:
        prompt: A detailed description of the image to generate.
        destination_filename: The destination object name (path) within the
            bucket, e.g. "images/my-post/diagram-1.png".
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix). Defaults to the configured bucket; only pass
            this if the user explicitly asks for a different bucket.
    """
    client = genai.Client()
    response = client.models.generate_content(
        model=config.image_model,
        contents=prompt,
    )

    image_bytes = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_bytes = part.inline_data.data
            break

    if image_bytes is None:
        return {"status": "error", "error_message": "No image was generated."}

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_filename)
    blob.upload_from_string(image_bytes, content_type="image/png")
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }


def search_public_images(query: str) -> dict:
    """Searches the public web for an existing image (e.g. a brand logo or a
    known landmark/person) instead of generating a new one.

    Args:
        query: What to search for, e.g. "Nike logo" or "Golden Gate Bridge".
    """
    api_key = os.environ.get("GOOGLE_CSE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return {
            "status": "error",
            "error_message": (
                "Public image search is not configured: set the "
                "GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID environment variables."
            ),
        }

    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "searchType": "image",
        "num": IMAGE_SEARCH_RESULT_COUNT,
        "safe": "active",
    }
    if IMAGE_SEARCH_RIGHTS_FILTER:
        params["rights"] = IMAGE_SEARCH_RIGHTS_FILTER

    response = requests.get(
        "https://www.googleapis.com/customsearch/v1", params=params, timeout=10
    )
    if response.status_code != 200:
        return {
            "status": "error",
            "error_message": f"Image search failed: {response.text[:300]}",
        }

    items = response.json().get("items", [])
    if not items:
        return {
            "status": "error",
            "error_message": f"No reusable public images found for '{query}'.",
        }

    return {
        "status": "success",
        "results": [
            {
                "image_url": item.get("link"),
                "title": item.get("title"),
                "source_page": item.get("image", {}).get("contextLink"),
                "mime_type": item.get("mime"),
            }
            for item in items
        ],
    }


def mirror_public_image_to_gcs(
    image_url: str,
    destination_filename: str,
    bucket_name: str = DEFAULT_GCS_BUCKET,
) -> dict:
    """Downloads a public image URL (e.g. from `search_public_images`) and
    stores a permanent copy in GCS, so the blog post doesn't depend on a
    third-party site staying up.

    Args:
        image_url: Direct URL of the image to mirror.
        destination_filename: The destination object name (path) within the
            bucket, e.g. "images/my-post/logo-1.png".
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix). Defaults to the configured bucket; only pass
            this if the user explicitly asks for a different bucket.
    """
    if urlparse(image_url).scheme != "https":
        return {
            "status": "error",
            "error_message": "Only https:// image URLs are supported.",
        }

    try:
        response = requests.get(image_url, timeout=10, stream=True)
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Failed to fetch image: {e}"}

    if response.status_code != 200:
        return {
            "status": "error",
            "error_message": f"Failed to fetch image: HTTP {response.status_code}",
        }

    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        return {
            "status": "error",
            "error_message": (
                f"URL did not return an image (content-type: "
                f"{content_type or 'unknown'})."
            ),
        }

    chunks = []
    total_bytes = 0
    for chunk in response.iter_content(chunk_size=65536):
        total_bytes += len(chunk)
        if total_bytes > _MAX_IMAGE_DOWNLOAD_BYTES:
            return {
                "status": "error",
                "error_message": "Image exceeds the size limit for mirroring.",
            }
        chunks.append(chunk)
    image_bytes = b"".join(chunks)

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_filename)
    blob.upload_from_string(image_bytes, content_type=content_type)
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }
