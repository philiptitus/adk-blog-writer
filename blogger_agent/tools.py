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

import io
import logging
import os
from urllib.parse import urlparse

import requests
from google import genai
from google.adk.tools import ToolContext
from google.cloud import storage
from PIL import Image

from .config import (
    BLOG_LENGTH_WORD_LIMITS,
    DEFAULT_BLOG_DRAFTS_PATH,
    DEFAULT_GCS_BUCKET,
    IMAGE_SEARCH_RESULT_COUNT,
    IMAGE_SEARCH_SAFESEARCH,
    MAX_IMAGE_WIDTH_PX,
    config,
)

logger = logging.getLogger(__name__)

_MAX_IMAGE_DOWNLOAD_BYTES = 15_000_000  # 15 MB safety cap for mirrored images


def _resize_if_too_wide(image_bytes: bytes, max_width: int = MAX_IMAGE_WIDTH_PX) -> bytes:
    """Downscales an image to max_width (preserving aspect ratio) if wider.

    Markdown has no syntax for display width, so this shrinks the actual
    file instead. Returns the original bytes unchanged if they aren't a
    format Pillow can decode, or if the image is already narrow enough.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception:
        logger.warning(
            "resize_if_too_wide: could not decode image (%d bytes) with Pillow, "
            "uploading unresized",
            len(image_bytes),
            exc_info=True,
        )
        return image_bytes

    if image.width <= max_width:
        logger.info(
            "resize_if_too_wide: %dx%d already <= max width %d, no resize needed",
            image.width,
            image.height,
            max_width,
        )
        return image_bytes

    new_height = round(image.height * (max_width / image.width))
    resized = image.resize((max_width, new_height), Image.LANCZOS)

    buffer = io.BytesIO()
    resized.save(buffer, format=image.format or "PNG")
    resized_bytes = buffer.getvalue()
    logger.info(
        "resize_if_too_wide: resized %dx%d -> %dx%d (%d bytes -> %d bytes)",
        image.width,
        image.height,
        max_width,
        new_height,
        len(image_bytes),
        len(resized_bytes),
    )
    return resized_bytes


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

    image_bytes = _resize_if_too_wide(image_bytes)

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
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "error_message": (
                "Public image search is not configured: set the "
                "SERPAPI_API_KEY environment variable."
            ),
        }

    response = requests.get(
        "https://serpapi.com/search",
        params={
            "engine": "google_images",
            "q": query,
            "api_key": api_key,
            "safe": IMAGE_SEARCH_SAFESEARCH,
        },
        timeout=10,
    )
    if response.status_code != 200:
        return {
            "status": "error",
            "error_message": f"Image search failed: {response.text[:300]}",
        }

    results = response.json().get("images_results", [])[:IMAGE_SEARCH_RESULT_COUNT]
    if not results:
        return {
            "status": "error",
            "error_message": f"No public images found for '{query}'.",
        }

    return {
        "status": "success",
        "results": [
            {
                "image_url": item.get("original"),
                "title": item.get("title"),
                "source_page": item.get("link"),
            }
            for item in results
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
    image_bytes = _resize_if_too_wide(b"".join(chunks))

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_filename)
    blob.upload_from_string(image_bytes, content_type=content_type)
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }
