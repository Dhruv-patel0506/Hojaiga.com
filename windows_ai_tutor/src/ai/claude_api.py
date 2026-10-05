"""
Claude API - Vision API with Streaming Support (Clicky-style)

Claude API helper with streaming for progressive text display.
Converted from ClaudeAPI.swift to Windows Python.
"""

import requests
import json
from typing import Optional, Callable, List
from PyQt5.QtCore import QObject, pyqtSignal
import threading

from ..utils.logger import setup_logger


class ClaudeAPI(QObject):
    """
    Claude API helper with streaming support.
    Handles vision requests with progressive text display.
    """

    # Signals
    text_chunk = pyqtSignal(str)  # Streaming text chunk
    response_complete = pyqtSignal(str)  # Complete response
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, proxy_url: str, model: str = "claude-sonnet-4-6"):
        """
        Initialize the Claude API client.

        Args:
            proxy_url: URL of the proxy endpoint
            model: Claude model to use
        """
        super().__init__()

        self.logger = setup_logger("ClaudeAPI")
        self.api_url = proxy_url
        self.model = model

        # Session configuration
        self.session = requests.Session()
        self.session.timeout = 120

        self.logger.info(f"Claude API initialized with model: {model}")

    def _detect_image_media_type(self, image_data: bytes) -> str:
        """
        Detect the MIME type of image data by inspecting the first bytes.

        Args:
            image_data: Raw image data

        Returns:
            str: MIME type ('image/png' or 'image/jpeg')
        """
        # PNG files start with the 8-byte signature: 89 50 4E 47 0D 0A 1A 0A
        if len(image_data) >= 4:
            png_signature = bytes([0x89, 0x50, 0x4E, 0x47])
            if image_data[:4] == png_signature:
                return "image/png"
        # Default to JPEG
        return "image/jpeg"

    def send_vision_request(
        self,
        user_message: str,
        images: List[bytes],
        on_text_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Send a vision request to Claude with streaming.

        Args:
            user_message: User's message
            images: List of image data (JPEG/PNG)
            on_text_chunk: Callback for streaming text chunks

        Returns:
            str: Complete response text
        """
        self.logger.info(f"Sending vision request with {len(images)} image(s)")

        # Build request
        request_data = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message}
                    ]
                }
            ]
        }

        # Add images
        for image_data in images:
            media_type = self._detect_image_media_type(image_data)
            import base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            request_data["messages"][0]["content"].append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_image
                }
            })

        try:
            response = self.session.post(
                self.api_url,
                json=request_data,
                stream=True
            )
            response.raise_for_status()

            # Process streaming response
            full_response = ""
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data)
                            if "delta" in chunk_data.get("content", [{}])[0]:
                                text = chunk_data["content"][0]["delta"]["text"]
                                full_response += text
                                if on_text_chunk:
                                    on_text_chunk(text)
                                self.text_chunk.emit(text)
                        except json.JSONDecodeError:
                            pass

            self.response_complete.emit(full_response)
            self.logger.info(f"Vision request completed, response length: {len(full_response)}")
            return full_response

        except Exception as e:
            self.logger.error(f"Vision request failed: {e}")
            self.error_occurred.emit(f"API error: {str(e)}")
            raise

    def send_text_request(
        self,
        user_message: str,
        on_text_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Send a text-only request to Claude with streaming.

        Args:
            user_message: User's message
            on_text_chunk: Callback for streaming text chunks

        Returns:
            str: Complete response text
        """
        self.logger.info("Sending text request")

        # Build request
        request_data = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        }

        try:
            response = self.session.post(
                self.api_url,
                json=request_data,
                stream=True
            )
            response.raise_for_status()

            # Process streaming response
            full_response = ""
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data)
                            if "delta" in chunk_data.get("content", [{}])[0]:
                                text = chunk_data["content"][0]["delta"]["text"]
                                full_response += text
                                if on_text_chunk:
                                    on_text_chunk(text)
                                self.text_chunk.emit(text)
                        except json.JSONDecodeError:
                            pass

            self.response_complete.emit(full_response)
            self.logger.info(f"Text request completed, response length: {len(full_response)}")
            return full_response

        except Exception as e:
            self.logger.error(f"Text request failed: {e}")
            self.error_occurred.emit(f"API error: {str(e)}")
            raise
