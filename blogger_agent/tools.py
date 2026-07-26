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

import glob
import mimetypes
import os

from google import genai
from google.cloud import storage

from .config import config


def save_blog_post_to_gcs(blog_post: str, filename: str, bucket_name: str) -> dict:
    """Saves the blog post to a file in a Google Cloud Storage bucket.

    Args:
        blog_post: The blog post content to save.
        filename: The destination object name (path) within the bucket,
            e.g. "posts/my-post.md".
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix).
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(filename)
    blob.upload_from_string(blog_post, content_type="text/markdown")
    return {"status": "success", "gcs_uri": f"gs://{bucket_name}/{filename}"}


def generate_blog_image(prompt: str, bucket_name: str, destination_filename: str) -> dict:
    """Generates an image with Gemini's image model and uploads it to GCS.

    Args:
        prompt: A detailed description of the image to generate.
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix).
        destination_filename: The destination object name (path) within the
            bucket, e.g. "images/my-post/diagram-1.png".
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
    blob.make_public()
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }


def upload_local_image_to_gcs(
    local_path: str, bucket_name: str, destination_filename: str
) -> dict:
    """Uploads a user-provided local image file to GCS.

    Args:
        local_path: Path to the image file on the local filesystem.
        bucket_name: The name of the GCS bucket to upload to (without the
            "gs://" prefix).
        destination_filename: The destination object name (path) within the
            bucket, e.g. "images/my-post/photo-1.jpg".
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
    blob.make_public()
    return {
        "status": "success",
        "gcs_uri": f"gs://{bucket_name}/{destination_filename}",
        "image_url": blob.public_url,
    }


def analyze_codebase(directory: str) -> dict:
    """Analyzes the codebase in the given directory."""
    files = glob.glob(os.path.join(directory, "**"), recursive=True)
    codebase_context = ""
    for file in files:
        if os.path.isfile(file):
            codebase_context += f"""- **{file}**:"""
            try:
                with open(file, encoding="utf-8") as f:
                    codebase_context += f.read()
            except UnicodeDecodeError:
                with open(file, encoding="latin-1") as f:
                    codebase_context += f.read()
    return {"codebase_context": codebase_context}
