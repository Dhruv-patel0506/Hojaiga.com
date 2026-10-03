"""
Organ 43 — Fallback Organ (Authentication & Manual Intervention Handler)

Responsibility: If the system is genuinely stuck (e.g., a mandatory 2FA prompt),
this organ halts execution and asks the user for manual authentication.
Handles scenarios that cannot be automated:
  - 2FA/MFA prompts
  - CAPTCHA challenges
  - Session expiration requiring fresh login
  - Security verification dialogs
  - Unknown/unhandled error states

Architecture:
  - Subscribes to escalation events from Navigation Popup Organ
  - Detects authentication-related UI patterns
  - Pauses automation execution
  - Notifies user with clear instructions
  - Waits for manual completion signal
  - Resumes automation after user confirmation
"""

import logging
import os
import sys
import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.organ_02_cns_single_file import EventEnvelope
except ImportError:
    try:
        from organ_02_cns_single_file import EventEnvelope
    except ImportError:
        @dataclass
        class EventEnvelope:
            topic: str
            source_organ: str
            payload: dict[str, Any]
            event_id: str = ""
            timestamp_ms: int = 0
            priority: int = 5
            correlation_id: Optional[str] = None

logger = logging.getLogger("hojaiga.organ43.fallback")


class FallbackReason(Enum):
    """Classification of fallback reasons."""
    AUTHENTICATION_REQUIRED = "authentication_required"
    TWO_FACTOR_AUTH = "two_factor_auth"
    CAPTCHA_CHALLENGE = "captcha_challenge"
    SESSION_EXPIRED = "session_expired"
    SECURITY_VERIFICATION = "security_verification"
    UNKNOWN_ERROR = "unknown_error"
    MANUAL_INTERVENTION_REQUESTED = "manual_intervention_requested"


@dataclass
class FallbackState:
    """Current state of fallback handling."""
    active: bool = False
    reason: Optional[FallbackReason] = None
    context: Optional[Dict[str, Any]] = None
    start_time: float = 0.0
    timeout: float = 300.0  # 5 minutes default timeout
    user_notified: bool = False
    awaiting_confirmation: bool = False


class FallbackOrgan:
    """
    Authentication & Manual Intervention Handler.

    Features:
    - Subscribes to escalation events from Navigation Popup Organ
    - Detects authentication-related UI patterns
    - Pauses automation execution
    - Notifies user with clear instructions
    - Waits for manual completion signal
    - Resumes automation after user confirmation
    """

    # Authentication pattern keywords
    AUTH_PATTERNS = [
        "2fa", "two factor", "two-factor", "verification code", "otp",
        "authenticator", "security code", "enter code", "verify identity",
        "captcha", "recaptcha", "i'm not a robot", "human verification",
        "session expired", "login required", "sign in required",
        "password required", "credential required",
    ]

    def __init__(self, cns_publisher=None, cns_subscriber=None):
        self.cns = cns_publisher
        self.cns_sub = cns_subscriber
        self._state = FallbackState()
        self._lock = threading.Lock()
        self._notification_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._pause_callback: Optional[Callable[[], None]] = None
        self._resume_callback: Optional[Callable[[], None]] = None
        self._visual_cursor = None  # Will be set externally for visual feedback

    def set_visual_cursor(self, visual_cursor):
        """Set visual cursor instance for feedback during fallback handling."""
        self._visual_cursor = visual_cursor

    def set_notification_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Set callback for user notification (e.g., display toast, send alert)."""
        self._notification_callback = callback

    def set_pause_callback(self, callback: Callable[[], None]):
        """Set callback to pause automation execution."""
        self._pause_callback = callback

    def set_resume_callback(self, callback: Callable[[], None]):
        """Set callback to resume automation execution."""
        self._resume_callback = callback

    def start(self):
        """Start fallback monitoring."""
        logger.info("[Fallback] Started fallback monitoring")

    def stop(self):
        """Stop fallback monitoring."""
        with self._lock:
            if self._state.active:
                logger.warning("[Fallback] Stopping while fallback is active - forcing resume")
                self._force_resume()

    def trigger_fallback(self, reason: FallbackReason, context: Optional[Dict[str, Any]] = None, timeout: float = 300.0):
        """Trigger fallback mode for manual intervention."""
        with self._lock:
            if self._state.active:
                logger.warning("[Fallback] Already in fallback mode - ignoring new trigger")
                return

            self._state = FallbackState(
                active=True,
                reason=reason,
                context=context or {},
                start_time=time.time(),
                timeout=timeout,
                user_notified=False,
                awaiting_confirmation=False,
            )

        logger.warning(f"[Fallback] Triggered: {reason.value}")
        
        # Show cursor as buffering during fallback
        if self._visual_cursor:
            self._visual_cursor.set_active_state("ACTIVE")
            self._visual_cursor.set_buffering(True)
        
        self._pause_automation()
        self._notify_user()

    def handle_escalation_event(self, event: EventEnvelope):
        """Handle escalation event from Navigation Popup Organ."""
        payload = event.payload
        pattern = payload.get("pattern", "")
        reason_raw = payload.get("reason", "")

        # Determine fallback reason based on escalation
        if "sign_in" in pattern.lower() or "auth" in pattern.lower():
            reason = FallbackReason.AUTHENTICATION_REQUIRED
        elif "2fa" in reason_raw.lower() or "verification" in reason_raw.lower():
            reason = FallbackReason.TWO_FACTOR_AUTH
        elif "captcha" in reason_raw.lower():
            reason = FallbackReason.CAPTCHA_CHALLENGE
        else:
            reason = FallbackReason.MANUAL_INTERVENTION_REQUESTED

        self.trigger_fallback(reason, payload)

    def detect_authentication_ui(self, screen_state: Dict[str, Any]) -> Optional[FallbackReason]:
        """Detect if current screen requires authentication."""
        elements = screen_state.get("elements", [])
        text_content = " ".join([e.get("text", "") for e in elements]).lower()

        for pattern in self.AUTH_PATTERNS:
            if pattern in text_content:
                # Determine specific reason
                if "2fa" in pattern or "two factor" in pattern or "otp" in pattern:
                    return FallbackReason.TWO_FACTOR_AUTH
                elif "captcha" in pattern or "recaptcha" in pattern:
                    return FallbackReason.CAPTCHA_CHALLENGE
                elif "session expired" in pattern or "login required" in pattern:
                    return FallbackReason.SESSION_EXPIRED
                else:
                    return FallbackReason.AUTHENTICATION_REQUIRED

        return None

    def _pause_automation(self):
        """Pause automation execution."""
        if self._pause_callback:
            try:
                self._pause_callback()
                logger.info("[Fallback] Automation paused")
            except Exception as e:
                logger.error(f"[Fallback] Error pausing automation: {e}")

    def _notify_user(self):
        """Notify user that manual intervention is required."""
        with self._lock:
            if self._state.user_notified:
                return
            self._state.user_notified = True

        message = self._generate_user_message()
        context = {
            "reason": self._state.reason.value if self._state.reason else "unknown",
            "context": self._state.context,
            "timeout": self._state.timeout,
        }

        if self._notification_callback:
            try:
                self._notification_callback(message, context)
                logger.info(f"[Fallback] User notified: {message[:100]}...")
            except Exception as e:
                logger.error(f"[Fallback] Error notifying user: {e}")
        else:
            # Fallback: log to console
            print(f"\n{'='*60}")
            print(f"FALLBACK: Manual Intervention Required")
            print(f"{'='*60}")
            print(message)
            print(f"{'='*60}\n")

    def _generate_user_message(self) -> str:
        """Generate user-friendly message based on fallback reason."""
        if not self._state.reason:
            return "Manual intervention required. Please complete the task on screen."

        reason_messages = {
            FallbackReason.AUTHENTICATION_REQUIRED: (
                "Authentication required. Please log in to continue. "
                "After completing authentication, confirm to resume automation."
            ),
            FallbackReason.TWO_FACTOR_AUTH: (
                "Two-factor authentication required. Please enter the verification code. "
                "After completing 2FA, confirm to resume automation."
            ),
            FallbackReason.CAPTCHA_CHALLENGE: (
                "CAPTCHA challenge detected. Please complete the human verification. "
                "After completing CAPTCHA, confirm to resume automation."
            ),
            FallbackReason.SESSION_EXPIRED: (
                "Session expired. Please log in again. "
                "After completing login, confirm to resume automation."
            ),
            FallbackReason.SECURITY_VERIFICATION: (
                "Security verification required. Please complete the verification steps. "
                "After completion, confirm to resume automation."
            ),
            FallbackReason.UNKNOWN_ERROR: (
                "Unknown error encountered. Please check the screen and resolve any issues. "
                "After resolving, confirm to resume automation."
            ),
            FallbackReason.MANUAL_INTERVENTION_REQUESTED: (
                "Manual intervention requested. Please complete the required action on screen. "
                "After completion, confirm to resume automation."
            ),
        }

        return reason_messages.get(self._state.reason, "Manual intervention required.")

    def confirm_manual_completion(self):
        """User confirms manual task completion - resume automation."""
        with self._lock:
            if not self._state.active:
                logger.warning("[Fallback] Not in fallback mode - ignoring confirmation")
                return

            self._state.awaiting_confirmation = True

        logger.info("[Fallback] User confirmed manual completion - resuming automation")
        self._resume_automation()

    def _resume_automation(self):
        """Resume automation execution."""
        with self._lock:
            self._state.active = False
            self._state.awaiting_confirmation = False

        # Reset cursor after resuming
        if self._visual_cursor:
            self._visual_cursor.set_buffering(False)

        if self._resume_callback:
            try:
                self._resume_callback()
                logger.info("[Fallback] Automation resumed")
            except Exception as e:
                logger.error(f"[Fallback] Error resuming automation: {e}")

        # Emit resume event
        if self.cns:
            try:
                event = EventEnvelope(
                    topic="fallback.resumed",
                    source_organ="organ_43_fallback",
                    payload={
                        "reason": self._state.reason.value if self._state.reason else "unknown",
                        "duration": time.time() - self._state.start_time,
                    },
                    event_id=f"fallback_resumed_{int(time.time() * 1000)}",
                    timestamp_ms=int(time.time() * 1000),
                    priority=5,
                )
                self.cns.publish(event)
            except Exception as e:
                logger.error(f"[Fallback] Failed to emit resume event: {e}")

    def _force_resume(self):
        """Force resume (e.g., on timeout or system shutdown)."""
        logger.warning("[Fallback] Forcing resume")
        self._resume_automation()

    def is_active(self) -> bool:
        """Check if currently in fallback mode."""
        with self._lock:
            return self._state.active

    def get_state(self) -> Dict[str, Any]:
        """Get current fallback state."""
        with self._lock:
            return {
                "active": self._state.active,
                "reason": self._state.reason.value if self._state.reason else None,
                "context": self._state.context,
                "start_time": self._state.start_time,
                "elapsed": time.time() - self._state.start_time if self._state.active else 0,
                "timeout": self._state.timeout,
                "user_notified": self._state.user_notified,
                "awaiting_confirmation": self._state.awaiting_confirmation,
            }

    def check_timeout(self):
        """Check if fallback has timed out and force resume if needed."""
        with self._lock:
            if not self._state.active:
                return

            elapsed = time.time() - self._state.start_time
            if elapsed > self._state.timeout:
                logger.warning(f"[Fallback] Timeout after {elapsed:.1f}s - forcing resume")
                self._force_resume()
