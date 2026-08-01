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

import mimetypes
import os

from google import genai
from google.adk.tools import ToolContext
from google.cloud import storage

from .config import (
    BLOG_LENGTH_WORD_LIMITS,
    DEFAULT_BLOG_DRAFTS_PATH,
    DEFAULT_GCS_BUCKET,
    config,
)


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


def upload_local_image_to_gcs(
    local_path: str,
    destination_filename: str,
    bucket_name: str = DEFAULT_GCS_BUCKET,
) -> dict:
    """Uploads a user-provided local image file to GCS.

    Args:
        local_path: Path to the image file on the local filesystem.
        destination_filename: The destination object name (path) within the
            bucket, e.g. "images/my-post/photo-1.jpg".
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix). Defaults to the configured bucket; only pass
            this if the user explicitly asks for a different bucket.
    """
    if not os.path.isfile(local_path):
        return {"status": "error", "error_message": f"File not found: {local_path}"}

    content_type, _ = mimetypes.guess_type(local_path)
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_filename)
    blob.upload_from_filename(
        local_path, content_type=content_type or "application/octet-stream"
    )
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }
