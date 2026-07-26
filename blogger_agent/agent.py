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

import datetime

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from .config import config
from .sub_agents import (
    blog_editor,
    robust_blog_planner,
    robust_blog_writer,
    social_media_writer,
)
from .tools import (
    analyze_codebase,
    generate_blog_image,
    save_blog_post_to_gcs,
    upload_local_image_to_gcs,
)

# --- AGENT DEFINITIONS ---

interactive_blogger_agent = Agent(
    name="interactive_blogger_agent",
    model=config.worker_model,
    description="The primary technical blogging assistant. It collaborates with the user to create a blog post.",
    instruction=f"""
    You are a technical blogging assistant. Your primary function is to help users create technical blog posts.

    Your workflow is as follows:
    1.  **Analyze Codebase (Optional):** If the user provides a directory, you will analyze the codebase to understand its structure and content. To do this, use the `analyze_codebase` tool.
    2.  **Plan:** You will generate a blog post outline and present it to the user. To do this, use the `robust_blog_planner` tool.
    3.  **Refine:** The user can provide feedback to refine the outline. You will continue to refine the outline until it is approved by the user.
    4.  **Write:** Once the user approves the outline, you will write the blog post. To do this, use the `robust_blog_writer` tool. Be then open for feedback.
    5.  **Edit:** After the first draft is written, you will present it to the user and ask for feedback. You will then revise the blog post based on the feedback (delegate to `blog_editor`). This process will be repeated until the user is satisfied with the result.
    6.  **Images:** Once the user is happy with the written content, ask if they'd like to add images (up to 5 total). Images are only ever added one at a time:
        - Ask the user for the GCS bucket name to use for image uploads (reuse it for the rest of the session unless they say otherwise).
        - For each image (max 5), ask the user to describe where in the post it goes and whether it should be:
          a. **Generated** — ask for a description of the image, then call `generate_blog_image` with that prompt, the bucket name, and a unique `destination_filename` (e.g. "images/<slug>/image-<n>.png").
          b. **Uploaded** — ask for the local file path, then call `upload_local_image_to_gcs` with that path, the bucket name, and a unique `destination_filename`.
        - After each successful call, insert a Markdown image tag (`![alt text](image_url)`) at the location the user specified by delegating to `blog_editor` with feedback describing exactly where to insert the returned `image_url`.
        - Stop after 5 images or as soon as the user says they're done, whichever comes first.
        - If the user doesn't want images, skip this step entirely.
    7.  **Social Media:** After the user approves the blog post, you will ask if they want to generate social media posts to promote the article. If the user agrees to create a social media post, use the `social_media_writer` tool.
    8.  **Export:** When the user approves the final version, ask for the GCS bucket name (reuse the one from the Images step if applicable) and the destination filename (object path), then use the `save_blog_post_to_gcs` tool. Saving only happens to Google Cloud Storage — there is no local-file export option.

    Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
    """,
    sub_agents=[
        robust_blog_writer,
        robust_blog_planner,
        blog_editor,
        social_media_writer,
    ],
    tools=[
        FunctionTool(save_blog_post_to_gcs),
        FunctionTool(analyze_codebase),
        FunctionTool(generate_blog_image),
        FunctionTool(upload_local_image_to_gcs),
    ],
    output_key="blog_outline",
)


root_agent = interactive_blogger_agent
