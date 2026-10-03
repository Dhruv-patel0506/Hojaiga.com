"""
OpenAI API - GPT Vision Analysis (Clicky-style)

OpenAI API helper for vision analysis.
Converted from OpenAIAPI.swift to Windows Python.
"""

import asyncio
import base64
import json
import time
from typing import List, Tuple, Optional
import requests

from ..utils.logger import setup_logger


class OpenAIAPI:
    """OpenAI API helper for vision analysis."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        """
        Initialize the OpenAI API client.

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-4o)
        """
        self.api_key = api_key
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = model

        self.logger = setup_logger("OpenAIAPI")

        # Session configuration
        self.session = requests.Session()
        self.session.timeout = 120

        # Warm up TLS connection
        self._warm_up_tls_connection()

    def _warm_up_tls_connection(self):
        """Send a no-op HEAD request to establish TLS session."""
        try:
            self.session.head(self.api_url, timeout=10)
            self.logger.info("TLS connection warmed up")
        except Exception as e:
            self.logger.warning(f"TLS warmup failed (non-critical): {e}")

    async def analyze_image(
        self,
        images: List[Tuple[bytes, str]],
        system_prompt: str,
        conversation_history: List[Tuple[str, str]] = None,
        user_prompt: str = ""
    ) -> Tuple[str, float]:
        """
        Send a vision request to OpenAI with labeled images.

        Args:
            images: List of (image_data, label) tuples
            system_prompt: System prompt
            conversation_history: List of (user, assistant) message pairs
            user_prompt: User prompt

        Returns:
            Tuple of (response_text, duration_seconds)
        """
        if conversation_history is None:
            conversation_history = []

        start_time = time.time()

        # Build messages array
        messages = []

        # Add system message
        messages.append({
            "role": "system",
            "content": system_prompt
        })

        # Add conversation history
        for user_placeholder, assistant_response in conversation_history:
            messages.append({
                "role": "user",
                "content": user_placeholder
            })
            messages.append({
                "role": "assistant",
                "content": assistant_response
            })

        # Build current message with all labeled images + prompt
        content_blocks = []

        for image_data, label in images:
            content_blocks.append({
                "type": "text",
                "text": label
            })
            content_blocks.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"
                }
            })

        content_blocks.append({
            "type": "text",
            "text": user_prompt
        })

        messages.append({
            "role": "user",
            "content": content_blocks
        })

        # Build request body
        body = {
            "model": self.model,
            "max_completion_tokens": 600,
            "messages": messages
        }

        body_data = json.dumps(body)
        payload_mb = len(body_data) / 1_048_576.0
        self.logger.info(f"OpenAI request: {payload_mb:.1f}MB, {len(images)} image(s)")

        # Send request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = self.session.post(
                self.api_url,
                headers=headers,
                data=body_data,
                timeout=120
            )

            if response.status_code not in range(200, 300):
                error_msg = response.text[:200] if response.text else "Unknown error"
                raise Exception(f"OpenAI API error: {response.status_code} - {error_msg}")

            # Parse response
            result = response.json()

            choices = result.get("choices", [])
            if not choices:
                raise Exception("Invalid response format: no choices")

            first_choice = choices[0]
            message = first_choice.get("message", {})
            text = message.get("content", "")

            if not text:
                raise Exception("Invalid response format: no content")

            duration = time.time() - start_time
            return text, duration

        except Exception as e:
            self.logger.error(f"OpenAI API request failed: {e}")
            raise
