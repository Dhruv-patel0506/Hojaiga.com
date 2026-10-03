"""
ElevenLabs TTS Client - Text-to-Speech (Clicky-style)

Streams text-to-speech audio from ElevenLabs and plays it back.
Converted from ElevenLabsTTSClient.swift to Windows Python.
"""

from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal
import requests
import json
import pygame
import io

from ..utils.logger import setup_logger


class ElevenLabsTTSClient(QObject):
    """
    ElevenLabs TTS client.
    Streams text-to-speech audio and plays it back.
    """

    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()

    def __init__(self, proxy_url: str = ""):
        """
        Initialize the ElevenLabs TTS client.

        Args:
            proxy_url: URL of the proxy server (Cloudflare Worker)
        """
        super().__init__()

        self.logger = setup_logger("ElevenLabsTTSClient")
        self.proxy_url = proxy_url

        # Audio player
        self._audio_player = None
        self._is_playing = False

        # Initialize pygame mixer for audio playback
        try:
            pygame.mixer.init()
            self.logger.info("Pygame mixer initialized for TTS playback")
        except Exception as e:
            self.logger.error(f"Failed to initialize pygame mixer: {e}")

        self.logger.info("ElevenLabs TTS client initialized")

    def speak_text(self, text: str):
        """
        Send text to ElevenLabs TTS and play the resulting audio.

        Args:
            text: Text to speak
        """
        if not self.proxy_url:
            self.logger.warning("No proxy URL configured for ElevenLabs TTS")
            return

        self.logger.info(f"Speaking text: {text[:50]}...")

        try:
            # Prepare request
            request_data = {
                "text": text,
                "model_id": "eleven_flash_v2_5",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }

            # Send request to proxy
            response = requests.post(
                self.proxy_url,
                json=request_data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg"
                },
                timeout=30
            )

            if response.status_code == 200:
                # Play audio
                self._play_audio_data(response.content)
                self.logger.info(f"Playing {len(response.content) / 1024:.1f}KB audio")
            else:
                self.logger.error(f"TTS API error: {response.status_code} - {response.text[:200]}")

        except Exception as e:
            self.logger.error(f"Error speaking text: {e}")

    def _play_audio_data(self, audio_data: bytes):
        """Play audio data using pygame."""
        try:
            # Load audio from bytes
            audio_file = io.BytesIO(audio_data)
            self._audio_player = pygame.mixer.Sound(audio_file)
            self._audio_player.play()
            self._is_playing = True
            self.playback_started.emit()

            # Wait for playback to finish
            while pygame.mixer.get_busy():
                pygame.time.wait(100)

            self._is_playing = False
            self.playback_finished.emit()

        except Exception as e:
            self.logger.error(f"Error playing audio: {e}")
            self._is_playing = False

    @property
    def is_playing(self) -> bool:
        """Check if TTS audio is currently playing."""
        return self._is_playing

    def stop_playback(self):
        """Stop any in-progress playback immediately."""
        if self._audio_player:
            self._audio_player.stop()
            self._audio_player = None
        self._is_playing = False
        self.logger.info("TTS playback stopped")
