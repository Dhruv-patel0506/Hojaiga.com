"""
Clicky Analytics - Usage Tracking (Clicky-style)

Centralized analytics wrapper for usage tracking.
Converted from ClickyAnalytics.swift to Windows Python.
Note: For local/private use, this is disabled by default.
"""

from typing import Optional
from ..utils.logger import setup_logger


class ClickyAnalytics:
    """
    Clicky analytics manager.
    Tracks usage events (optional - disabled by default for privacy).
    """

    _enabled = False
    _api_key = ""
    _host = ""

    @classmethod
    def configure(cls, enabled: bool = False, api_key: str = "", host: str = ""):
        """
        Configure analytics.

        Args:
            enabled: Whether analytics is enabled
            api_key: Analytics API key
            host: Analytics host URL
        """
        cls._enabled = enabled
        cls._api_key = api_key
        cls._host = host

        logger = setup_logger("ClickyAnalytics")
        if enabled:
            logger.info("Analytics enabled")
        else:
            logger.info("Analytics disabled (default for privacy)")

    @classmethod
    def _track(cls, event_name: str, properties: Optional[dict] = None):
        """Internal track method."""
        if not cls._enabled:
            return

        logger = setup_logger("ClickyAnalytics")
        logger.info(f"Event: {event_name}, Properties: {properties}")

        # In a real implementation, this would send to PostHog or similar
        # For local use, we just log

    # MARK: - App Lifecycle

    @classmethod
    def track_app_opened(cls, version: str = "unknown"):
        """Track app opened event."""
        cls._track("app_opened", {"app_version": version})

    # MARK: - Onboarding

    @classmethod
    def track_onboarding_started(cls):
        """Track onboarding started."""
        cls._track("onboarding_started")

    @classmethod
    def track_onboarding_replayed(cls):
        """Track onboarding replayed."""
        cls._track("onboarding_replayed")

    @classmethod
    def track_onboarding_video_completed(cls):
        """Track onboarding video completed."""
        cls._track("onboarding_video_completed")

    @classmethod
    def track_onboarding_demo_triggered(cls):
        """Track onboarding demo triggered."""
        cls._track("onboarding_demo_triggered")

    # MARK: - Permissions

    @classmethod
    def track_all_permissions_granted(cls):
        """Track all permissions granted."""
        cls._track("all_permissions_granted")

    @classmethod
    def track_permission_granted(cls, permission: str):
        """Track permission granted."""
        cls._track("permission_granted", {"permission": permission})

    # MARK: - Voice Interaction

    @classmethod
    def track_push_to_talk_started(cls):
        """Track push-to-talk started."""
        cls._track("push_to_talk_started")

    @classmethod
    def track_push_to_talk_released(cls):
        """Track push-to-talk released."""
        cls._track("push_to_talk_released")

    @classmethod
    def track_user_message_sent(cls, transcript: str):
        """Track user message sent."""
        cls._track("user_message_sent", {
            "transcript": transcript,
            "character_count": len(transcript)
        })

    @classmethod
    def track_ai_response_received(cls, response: str):
        """Track AI response received."""
        cls._track("ai_response_received", {
            "response": response,
            "character_count": len(response)
        })

    @classmethod
    def track_element_pointed(cls, element_label: Optional[str] = None):
        """Track element pointed."""
        cls._track("element_pointed", {
            "element_label": element_label or "unknown"
        })

    # MARK: - Errors

    @classmethod
    def track_response_error(cls, error: str):
        """Track response error."""
        cls._track("response_error", {"error": error})

    @classmethod
    def track_tts_error(cls, error: str):
        """Track TTS error."""
        cls._track("tts_error", {"error": error})
