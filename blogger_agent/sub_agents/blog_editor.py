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

from google.adk.agents import Agent

from ..config import config

blog_editor = Agent(
    model=config.critic_model,
    name="blog_editor",
    description="Edits a technical blog post based on user feedback.",
    instruction="""
    You are a professional technical editor. You will be given user feedback describing what to
    change. The current blog post draft — the one and only authoritative version to edit — is:

    ---
    {blog_post}
    ---

    Your task is to edit the above draft based on the provided feedback. Do not invent a new post
    or edit from memory of earlier conversation turns — always start from the draft shown above.
    Unless the feedback explicitly asks to make the post longer or shorter, keep it close to its
    original target of approximately {blog_word_limit} words (a "{blog_length}" post).
    The final output should be the complete revised blog post in Markdown format.
    """,
    output_key="blog_post",
)
