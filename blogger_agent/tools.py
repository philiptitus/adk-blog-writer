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
import os

from google.cloud import storage


def save_blog_post_to_file(blog_post: str, filename: str) -> dict:
    """Saves the blog post to a file."""
    with open(filename, "w") as f:
        f.write(blog_post)
    return {"status": "success"}


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
